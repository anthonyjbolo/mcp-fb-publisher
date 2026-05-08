"""Shared fixtures.

CRITICAL: These tests MUST NOT make real network calls. We use httpx.MockTransport
to mock the entire Meta Graph API surface.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from mcp_fb_publisher.config import Config, Defaults, ImageProviders, PageConfig
from mcp_fb_publisher.meta_client import MetaClient


@pytest.fixture
def sample_config() -> Config:
    return Config(
        defaults=Defaults(
            language="en",
            brand_voice="Direct, no fluff.",
            banned_topics=["forbidden_word"],
            image_required=True,
            anti_duplicate_lookback_days=14,
        ),
        pages={
            "test_page": PageConfig(
                page_id="1111111111",
                name="Test Page",
                banned_topics=["another_banned"],
                image_required=True,
            ),
            "no_image_page": PageConfig(
                page_id="2222222222",
                name="Text-only Page",
                image_required=False,
            ),
        },
        image_providers=ImageProviders(),
    )


def make_mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient backed by a MockTransport — zero network."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.fixture
def mock_meta_client_factory():
    """Returns a factory that builds a MetaClient with a custom mock handler."""

    def _factory(handler: Callable[[httpx.Request], httpx.Response], token: str = "test_token"):
        client = make_mock_client(handler)
        return MetaClient(access_token=token, client=client)

    return _factory
