"""Integration-ish tests for the MCP tool functions.

We import the underlying coroutines directly (not via the MCP transport) and
mock the Meta API + image provider. Network never touched.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from mcp_fb_publisher import server as srv
from mcp_fb_publisher.config import Config
from mcp_fb_publisher.meta_client import MetaClient


@pytest.fixture(autouse=True)
def _setup_env_and_config(monkeypatch: pytest.MonkeyPatch, sample_config: Config):
    monkeypatch.setenv("META_USER_TOKEN", "test_token")
    # Inject a deterministic config singleton
    srv._config = sample_config
    yield
    srv._config = None


def _mock_handler_factory(recent_posts: list[dict[str, Any]] | None = None, publish_id: str = "ok_1"):
    """Build a handler that simulates Meta Graph API responses."""
    if recent_posts is None:
        recent_posts = []

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "/feed" in url and req.method == "GET":
            return httpx.Response(200, json={"data": recent_posts})
        if "/feed" in url or "/photos" in url:
            return httpx.Response(200, json={"id": publish_id, "post_id": publish_id})
        if "debug_token" in url:
            return httpx.Response(200, json={"data": {"is_valid": True, "expires_at": 9999999999, "scopes": []}})
        return httpx.Response(404, text="not mocked")

    return handler


def _patch_meta_client(monkeypatch: pytest.MonkeyPatch, handler):
    """Patch _get_meta_client so the server uses a MockTransport client."""

    def factory(token_override: str | None = None) -> MetaClient:
        token = token_override or os.environ.get("META_USER_TOKEN") or "x"
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        return MetaClient(access_token=token, client=client)

    monkeypatch.setattr(srv, "_get_meta_client", factory)


# ----- fb_validate_pre_publish -----


@pytest.mark.asyncio
async def test_validate_unknown_page_blocks(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory())
    out = await srv.fb_validate_pre_publish(
        page_id="9999999999",
        message="Hello world",
        image_url="https://example.com/img.png",
        fetch_recent=False,
    )
    assert out["verdict"] == "block"
    assert any("not found" in e for e in out["errors"])


@pytest.mark.asyncio
async def test_validate_clean_message_passes(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory())
    out = await srv.fb_validate_pre_publish(
        page_id="1111111111",
        message="We are launching the new collection on Friday, save the date!",
        image_url="https://example.com/img.png",
        fetch_recent=False,
    )
    assert out["verdict"] == "go"


@pytest.mark.asyncio
async def test_validate_blocks_banned_topic(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory())
    out = await srv.fb_validate_pre_publish(
        page_id="1111111111",
        message="Check out our forbidden_word special drop today!",
        image_url="https://example.com/img.png",
        fetch_recent=False,
    )
    assert out["verdict"] == "block"


@pytest.mark.asyncio
async def test_validate_blocks_missing_image(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory())
    out = await srv.fb_validate_pre_publish(
        page_id="1111111111",
        message="Long enough message but image missing oh no",
        image_url=None,
        fetch_recent=False,
    )
    assert out["verdict"] == "block"


@pytest.mark.asyncio
async def test_validate_with_fetch_recent_dup(monkeypatch: pytest.MonkeyPatch):
    """Anti-dup catches a near-identical recent post."""
    msg = "Big sale this weekend on all baking supplies, free delivery in town"
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    handler = _mock_handler_factory(
        recent_posts=[{"id": "p_old", "message": msg, "created_time": yesterday}]
    )
    _patch_meta_client(monkeypatch, handler)
    out = await srv.fb_validate_pre_publish(
        page_id="1111111111",
        message=msg,
        image_url="https://example.com/img.png",
        fetch_recent=True,
    )
    assert out["verdict"] == "block"
    assert any("anti_duplicate" in c["name"] and not c["ok"] for c in out["checks"])


# ----- fb_anti_duplicate_check -----


@pytest.mark.asyncio
async def test_anti_dup_no_recent(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory(recent_posts=[]))
    out = await srv.fb_anti_duplicate_check(
        page_id="1111111111",
        message="some new message we have never posted before",
    )
    assert out["is_duplicate"] is False
    assert out["posts_compared"] == 0


@pytest.mark.asyncio
async def test_anti_dup_finds_match(monkeypatch: pytest.MonkeyPatch):
    msg = "Great news team we shipped feature X to all customers worldwide"
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    handler = _mock_handler_factory(
        recent_posts=[{"id": "p_dup", "message": msg, "created_time": yesterday}]
    )
    _patch_meta_client(monkeypatch, handler)
    out = await srv.fb_anti_duplicate_check(
        page_id="1111111111",
        message=msg,
    )
    assert out["is_duplicate"] is True
    assert out["closest_post_id"] == "p_dup"


# ----- fb_publish_post -----


@pytest.mark.asyncio
async def test_publish_blocks_when_validation_fails(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory())
    out = await srv.fb_publish_post(
        page_id="1111111111",
        message="message but no image and image_required=True",
        image_url=None,
    )
    assert out["ok"] is False
    assert out["error"] == "validation_blocked"
    assert "validation" in out


@pytest.mark.asyncio
async def test_publish_succeeds_when_clean(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory(publish_id="1111_777"))
    out = await srv.fb_publish_post(
        page_id="1111111111",
        message="Brand new feature: pickup at our front desk starting today!",
        image_url="https://example.com/img.png",
    )
    assert out["ok"] is True
    assert out["post_id"] == "1111_777"


@pytest.mark.asyncio
async def test_publish_skip_validation(monkeypatch: pytest.MonkeyPatch):
    _patch_meta_client(monkeypatch, _mock_handler_factory(publish_id="raw_1"))
    out = await srv.fb_publish_post(
        page_id="1111111111",
        message="anything goes here",
        image_url=None,
        skip_validation=True,
    )
    assert out["ok"] is True
    assert "validation" not in out


# ----- fb_generate_post_with_image -----


@pytest.mark.asyncio
async def test_generate_image_dispatches_to_provider(monkeypatch: pytest.MonkeyPatch):
    from mcp_fb_publisher import server as s

    async def fake_gen(prompt, providers, *, provider=None):
        from mcp_fb_publisher.image_providers import GeneratedImage

        return GeneratedImage(
            url="https://cdn.example.com/fake.png",
            provider=provider or "openai",
            model="fake-model",
            prompt=prompt,
        )

    monkeypatch.setattr(s, "gen_image_impl", fake_gen)
    out = await s.fb_generate_post_with_image(
        page_id="1111111111",
        prompt="A neon sign that says hello",
        image_provider="openai",
    )
    assert out["image_url"].startswith("https://cdn.example.com/")
    assert out["provider"] == "openai"
    assert out["page_id"] == "1111111111"
