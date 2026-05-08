"""MetaClient tests — all network calls mocked via httpx.MockTransport."""

from __future__ import annotations

import json
import time

import httpx
import pytest


@pytest.mark.asyncio
async def test_publish_post_text_only(mock_meta_client_factory):
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"id": "1111_5555"})

    client = mock_meta_client_factory(handler)
    res = await client.publish_post("1111", "Hello world")
    await client.aclose()

    assert res.ok
    assert res.post_id == "1111_5555"
    assert "/1111/feed" in captured["url"]
    assert "message=Hello+world" in captured["body"] or "Hello%20world" in captured["body"]


@pytest.mark.asyncio
async def test_publish_post_with_image(mock_meta_client_factory):
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"post_id": "abc_999", "id": "999"})

    client = mock_meta_client_factory(handler)
    res = await client.publish_post(
        "1111", "Caption here", image_url="https://example.com/img.png"
    )
    await client.aclose()

    assert res.ok
    assert res.post_id == "abc_999"
    assert "/1111/photos" in captured["url"]
    assert "url=" in captured["body"]
    assert "caption=" in captured["body"]


@pytest.mark.asyncio
async def test_publish_post_scheduled(mock_meta_client_factory):
    captured: dict = {}
    future = int(time.time()) + 3600

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"id": "scheduled_1"})

    client = mock_meta_client_factory(handler)
    res = await client.publish_post("1111", "Scheduled text", scheduled_at=future)
    await client.aclose()

    assert res.ok
    assert "scheduled_publish_time" in captured["body"]
    assert "published=false" in captured["body"]


@pytest.mark.asyncio
async def test_publish_post_handles_meta_error(mock_meta_client_factory):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "(#100) Invalid parameter"}},
        )

    client = mock_meta_client_factory(handler)
    res = await client.publish_post("1111", "Bad post")
    await client.aclose()

    assert not res.ok
    assert res.error and "400" in res.error


@pytest.mark.asyncio
async def test_publish_post_redacts_token_in_error(mock_meta_client_factory):
    """Token must NEVER leak in returned error messages."""
    secret = "super_secret_token_xyz"

    def handler(req: httpx.Request) -> httpx.Response:
        # The Meta API echoing back the token is a known footgun
        return httpx.Response(400, text=f"error using token {secret}")

    client = mock_meta_client_factory(handler, token=secret)
    res = await client.publish_post("1111", "x" * 20)
    await client.aclose()

    assert not res.ok
    assert secret not in (res.error or "")
    assert "REDACTED" in (res.error or "")


@pytest.mark.asyncio
async def test_debug_token_valid(mock_meta_client_factory):
    expires = int(time.time()) + 60 * 86400  # 60 days

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "is_valid": True,
                    "expires_at": expires,
                    "scopes": ["pages_manage_posts", "pages_read_engagement"],
                }
            },
        )

    client = mock_meta_client_factory(handler)
    info = await client.debug_token()
    await client.aclose()

    assert info.valid
    assert info.expires_at == expires
    assert info.days_left in (59, 60)
    assert "pages_manage_posts" in info.scopes


@pytest.mark.asyncio
async def test_debug_token_expired(mock_meta_client_factory):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"is_valid": False, "expires_at": int(time.time()) - 100, "scopes": []}},
        )

    client = mock_meta_client_factory(handler)
    info = await client.debug_token()
    await client.aclose()

    assert not info.valid
    assert info.days_left < 0


@pytest.mark.asyncio
async def test_fetch_recent_posts(mock_meta_client_factory):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "p1", "message": "First post", "created_time": "2026-05-01T10:00:00+0000"},
                    {"id": "p2", "message": "", "created_time": "2026-05-02T10:00:00+0000"},  # skipped (no msg)
                    {"id": "p3", "message": "Third", "created_time": "2026-05-03T10:00:00+0000"},
                ]
            },
        )

    client = mock_meta_client_factory(handler)
    posts = await client.fetch_recent_posts("1111")
    await client.aclose()

    assert len(posts) == 2
    assert posts[0].id == "p1"
    assert posts[1].id == "p3"


@pytest.mark.asyncio
async def test_meta_client_requires_token():
    from mcp_fb_publisher.meta_client import MetaClient

    with pytest.raises(ValueError):
        MetaClient(access_token="")


@pytest.mark.asyncio
async def test_publish_post_uses_page_token(mock_meta_client_factory):
    """When page_access_token is provided, it must be sent (not the user token)."""
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content.decode()
        return httpx.Response(200, json={"id": "ok"})

    client = mock_meta_client_factory(handler, token="USER_TOKEN")
    await client.publish_post("1111", "x" * 20, page_access_token="PAGE_TOKEN")
    await client.aclose()

    assert "PAGE_TOKEN" in captured["body"]
    assert "USER_TOKEN" not in captured["body"]


@pytest.mark.asyncio
async def test_meta_returns_non_json_error_gracefully(mock_meta_client_factory):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>internal server error</html>")

    client = mock_meta_client_factory(handler)
    res = await client.publish_post("1111", "x" * 20)
    await client.aclose()

    assert not res.ok
    assert "500" in (res.error or "")
    # Make sure no JSON-decoding error escaped
    json.dumps({"error": res.error})  # serializable
