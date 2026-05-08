"""FastMCP server exposing 4 tools for safe Facebook Page publishing.

Tools:
    fb_publish_post              -> publish via Meta Graph API
    fb_validate_pre_publish      -> dry-run all guard-rails (image, banned, dup)
    fb_anti_duplicate_check      -> compare against recent feed posts
    fb_generate_post_with_image  -> generate image (OpenAI / fal) + return URL

Run:
    mcp-fb-publisher
or
    python -m mcp_fb_publisher.server

Environment:
    META_USER_TOKEN              long-lived Meta user/page token (REQUIRED at publish-time)
    MCP_FB_PUBLISHER_CONFIG      path to config.yaml (optional, see config.py for fallbacks)
    OPENAI_API_KEY               for OpenAI image provider (optional)
    FAL_KEY                      for fal.ai image provider (optional)
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import UTC
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Config, load_config
from .image_providers import generate_image as gen_image_impl
from .meta_client import MetaClient
from .validator import validate_pre_publish

log = logging.getLogger("mcp_fb_publisher")
logging.basicConfig(level=os.environ.get("MCP_FB_PUBLISHER_LOG", "INFO"))


# --- Singletons (lazy) ---

_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _get_meta_client(token_override: str | None = None) -> MetaClient:
    token = token_override or os.environ.get("META_USER_TOKEN") or ""
    if not token:
        raise RuntimeError(
            "META_USER_TOKEN env var is required to call Meta Graph API. "
            "Set it before invoking publish-related tools."
        )
    return MetaClient(access_token=token)


# --- MCP server ---

mcp = FastMCP("mcp-fb-publisher")


@mcp.tool()
async def fb_publish_post(
    page_id: str,
    message: str,
    image_url: str | None = None,
    scheduled_at: int | None = None,
    page_access_token: str | None = None,
    skip_validation: bool = False,
) -> dict[str, Any]:
    """Publish a post on a Facebook Page via Meta Graph API.

    Args:
        page_id: Numeric Meta Page ID.
        message: Post message body.
        image_url: Optional public URL of an image. If config requires images,
            this MUST be provided (validation will block otherwise).
        scheduled_at: Optional unix timestamp (seconds). If set, the post is
            scheduled instead of published immediately. Meta requires
            10 minutes <= delta <= 6 months.
        page_access_token: Optional page-scoped token. Required by Meta in
            production for posting on a Page (the env-level token is usually
            a user token; you can derive a page token from /me/accounts).
        skip_validation: If True, bypasses the pre-publish validator (image
            required, banned topics, anti-duplicate). Default False — strongly
            recommended to keep validation on.

    Returns:
        Dict with `ok`, `post_id` (if success), `error` (if failure),
        and a `validation` block when validation ran.
    """
    config = get_config()
    page_match = config.resolve_page(page_id)
    validation_block: dict[str, Any] | None = None

    if not skip_validation and page_match:
        _, page_cfg = page_match
        async with _get_meta_client(page_access_token) as client:
            try:
                recent = await client.fetch_recent_posts(
                    page_id, page_access_token=page_access_token, limit=50
                )
            except Exception as e:
                log.warning("anti-dup fetch failed, continuing without it: %s", e)
                recent = None
            result = validate_pre_publish(message, image_url, page_cfg, recent_posts=recent)
            validation_block = {
                "verdict": result.verdict,
                "checks": [asdict(c) for c in result.checks],
                "errors": result.errors,
            }
            if not result.ok:
                return {
                    "ok": False,
                    "error": "validation_blocked",
                    "validation": validation_block,
                }

    async with _get_meta_client(page_access_token) as client:
        res = await client.publish_post(
            page_id,
            message,
            page_access_token=page_access_token,
            image_url=image_url,
            scheduled_at=scheduled_at,
        )
    out: dict[str, Any] = {"ok": res.ok, "post_id": res.post_id, "error": res.error}
    if validation_block:
        out["validation"] = validation_block
    return out


@mcp.tool()
async def fb_validate_pre_publish(
    page_id: str,
    message: str,
    image_url: str | None = None,
    fetch_recent: bool = True,
    page_access_token: str | None = None,
) -> dict[str, Any]:
    """Run all guard-rails BEFORE publishing.

    Checks:
        - image_required (per-page config)
        - banned_topics (substring, accent-insensitive)
        - length (10..63206 chars)
        - anti_duplicate (Jaccard 4-grams vs recent posts, lookback per config)

    Args:
        page_id: Numeric Meta Page ID.
        message: Candidate post text.
        image_url: Optional candidate image URL.
        fetch_recent: If True (default), fetches recent posts from Meta to run
            the anti-duplicate check. Set False to skip network.
        page_access_token: Optional page-scoped token (used only if fetch_recent).

    Returns:
        Dict with `verdict` ("go"|"block"), per-check details, errors.
    """
    config = get_config()
    page_match = config.resolve_page(page_id)
    if not page_match:
        return {
            "verdict": "block",
            "checks": [],
            "errors": [f"page_id {page_id} not found in config; add it under `pages:`"],
        }
    _, page_cfg = page_match

    recent = None
    if fetch_recent:
        try:
            async with _get_meta_client(page_access_token) as client:
                recent = await client.fetch_recent_posts(
                    page_id, page_access_token=page_access_token, limit=50
                )
        except Exception as e:
            log.warning("fetch_recent_posts failed: %s", e)
            recent = None

    result = validate_pre_publish(message, image_url, page_cfg, recent_posts=recent)
    return {
        "verdict": result.verdict,
        "checks": [asdict(c) for c in result.checks],
        "errors": result.errors,
        "warnings": result.warnings,
    }


@mcp.tool()
async def fb_anti_duplicate_check(
    page_id: str,
    message: str,
    lookback_days: int = 14,
    similarity_threshold: float = 0.5,
    page_access_token: str | None = None,
) -> dict[str, Any]:
    """Compare a candidate message against recent posts on the page.

    Args:
        page_id: Numeric Meta Page ID.
        message: Candidate text to score.
        lookback_days: Max age of posts to compare against (default 14).
        similarity_threshold: Jaccard threshold above which it's "too similar"
            (default 0.5; 0.0=identical, 1.0=nothing in common — careful, that's
            inverted intuitively. 0.5 = ~half the 4-grams overlap).
        page_access_token: Optional page-scoped token.

    Returns:
        Dict with `is_duplicate`, `closest_post_id`, `closest_similarity`,
        `posts_compared`, `lookback_days`.
    """
    from datetime import datetime, timedelta

    from .validator import jaccard_similarity

    async with _get_meta_client(page_access_token) as client:
        recent = await client.fetch_recent_posts(
            page_id, page_access_token=page_access_token, limit=50
        )

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    in_window = []
    for p in recent:
        try:
            ts = datetime.fromisoformat(p.created_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.now(UTC)
        if ts >= cutoff:
            in_window.append(p)

    best: tuple[float, str, str] = (0.0, "", "")
    for p in in_window:
        sim = jaccard_similarity(message, p.message, n=4)
        if sim > best[0]:
            best = (sim, p.id, p.created_time)

    return {
        "is_duplicate": best[0] >= similarity_threshold,
        "closest_post_id": best[1] or None,
        "closest_post_created_time": best[2] or None,
        "closest_similarity": round(best[0], 4),
        "posts_compared": len(in_window),
        "lookback_days": lookback_days,
        "similarity_threshold": similarity_threshold,
    }


@mcp.tool()
async def fb_generate_post_with_image(
    page_id: str,
    prompt: str,
    image_provider: str | None = None,
) -> dict[str, Any]:
    """Generate an image for a candidate post and return a usable URL.

    Does NOT publish. Caller is expected to take the returned image_url and
    pass it to `fb_publish_post` (or further validate via
    `fb_validate_pre_publish`). This separation lets the LLM iterate on the
    visual without burning Meta API quota.

    Args:
        page_id: Numeric Meta Page ID (used only to resolve provider defaults).
        prompt: Image generation prompt (English recommended).
        image_provider: "openai" | "fal". Defaults to config.image_providers.default.

    Returns:
        Dict with `image_url`, `provider`, `model`, `prompt`.
    """
    config = get_config()
    img = await gen_image_impl(prompt, config.image_providers, provider=image_provider)
    return {
        "image_url": img.url,
        "provider": img.provider,
        "model": img.model,
        "prompt": img.prompt,
        "page_id": page_id,
    }


# --- Entry point ---


def main() -> None:  # pragma: no cover
    """Run the MCP server over stdio (default) or sse if MCP_TRANSPORT=sse."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
