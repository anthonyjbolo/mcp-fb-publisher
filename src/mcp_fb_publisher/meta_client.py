"""Thin async client around the Meta Graph API for posting and reading.

Only the surface needed by the 4 MCP tools is implemented. Error handling is
defensive and never leaks the access token in messages.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

GRAPH_BASE = "https://graph.facebook.com/v21.0"


class MetaError(Exception):
    """Wraps an error returned by the Meta Graph API."""


@dataclass
class PublishResult:
    ok: bool
    post_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class TokenInfo:
    valid: bool
    expires_at: int  # unix seconds, 0 if missing
    days_left: int  # negative if expired
    scopes: list[str]
    error: str | None = None


@dataclass
class FeedPost:
    id: str
    message: str
    created_time: str  # ISO-8601 UTC


def _redact_token(text: str, token: str) -> str:
    if token and token in text:
        return text.replace(token, "***REDACTED***")
    return text


class MetaClient:
    """Async Meta Graph API client. Re-uses a single httpx.AsyncClient."""

    def __init__(
        self,
        access_token: str,
        *,
        graph_base: str = GRAPH_BASE,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self._token = access_token
        self._base = graph_base
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> MetaClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---------------- Token ----------------

    async def debug_token(self) -> TokenInfo:
        """Hit /debug_token. Always uses the same token as both target and auth."""
        try:
            r = await self._client.get(
                f"{self._base}/debug_token",
                params={"input_token": self._token, "access_token": self._token},
            )
        except httpx.HTTPError as e:
            return TokenInfo(False, 0, -1, [], error=f"network: {e.__class__.__name__}")

        if r.status_code != 200:
            return TokenInfo(
                False,
                0,
                -1,
                [],
                error=f"http {r.status_code}: {_redact_token(r.text[:200], self._token)}",
            )
        data = r.json().get("data", {}) or {}
        valid = bool(data.get("is_valid", False))
        expires = int(data.get("expires_at", 0) or 0)
        scopes = list(data.get("scopes") or [])
        # days_left computed against "now" by caller if needed; here keep raw
        days_left = (expires - int(time.time())) // 86400 if expires else -1
        return TokenInfo(valid=valid, expires_at=expires, days_left=days_left, scopes=scopes)

    # ---------------- Publish ----------------

    async def publish_post(
        self,
        page_id: str,
        message: str,
        *,
        page_access_token: str | None = None,
        image_url: str | None = None,
        scheduled_at: int | None = None,
    ) -> PublishResult:
        """Publish a post on the Facebook page.

        - If `image_url` is provided, calls /<page_id>/photos with `caption` and `url`.
        - Otherwise calls /<page_id>/feed with `message`.
        - `scheduled_at` (unix seconds, must be 10min..6mo from now per Meta docs)
          flips the post to scheduled-published mode.
        - `page_access_token` overrides the user token. Required by Meta for page
          publishing in production. We pass through whatever the caller gives.
        """
        token = page_access_token or self._token
        params: dict[str, Any] = {"access_token": token}
        if image_url:
            url = f"{self._base}/{page_id}/photos"
            params["url"] = image_url
            params["caption"] = message
        else:
            url = f"{self._base}/{page_id}/feed"
            params["message"] = message

        if scheduled_at is not None:
            params["published"] = "false"
            params["scheduled_publish_time"] = str(int(scheduled_at))

        try:
            r = await self._client.post(url, data=params)
        except httpx.HTTPError as e:
            return PublishResult(ok=False, error=f"network: {e.__class__.__name__}")

        if r.status_code != 200:
            return PublishResult(
                ok=False,
                error=f"http {r.status_code}: {_redact_token(r.text[:300], token)}",
            )
        data = r.json()
        post_id = data.get("post_id") or data.get("id")
        return PublishResult(ok=True, post_id=str(post_id) if post_id else None, raw=data)

    # ---------------- Read feed ----------------

    async def fetch_recent_posts(
        self,
        page_id: str,
        *,
        page_access_token: str | None = None,
        limit: int = 50,
        since_unix: int | None = None,
    ) -> list[FeedPost]:
        """Fetch up to `limit` recent posts from the page feed.

        Used by the anti-duplicate tool. Returns posts with non-empty messages.
        """
        token = page_access_token or self._token
        params: dict[str, Any] = {
            "access_token": token,
            "fields": "id,message,created_time",
            "limit": str(limit),
        }
        if since_unix is not None:
            params["since"] = str(since_unix)

        try:
            r = await self._client.get(f"{self._base}/{page_id}/feed", params=params)
        except httpx.HTTPError as e:
            raise MetaError(f"network: {e.__class__.__name__}") from e

        if r.status_code != 200:
            raise MetaError(
                f"http {r.status_code}: {_redact_token(r.text[:300], token)}"
            )
        data = r.json()
        out: list[FeedPost] = []
        for item in data.get("data", []) or []:
            msg = item.get("message") or ""
            if not msg:
                continue
            out.append(
                FeedPost(
                    id=str(item.get("id", "")),
                    message=str(msg),
                    created_time=str(item.get("created_time", "")),
                )
            )
        return out
