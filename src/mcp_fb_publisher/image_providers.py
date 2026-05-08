"""Pluggable image generation providers (OpenAI, fal.ai).

Each provider returns a public URL that Meta Graph API can fetch via
`/<page>/photos?url=...&caption=...`. Providers are imported lazily so the
main package has no hard dependency on either SDK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .config import ImageProviders


class ImageProviderError(Exception):
    """Raised when an image-generation call fails or the provider isn't installed."""


@dataclass
class GeneratedImage:
    url: str
    provider: str
    model: str
    prompt: str


async def generate_image(
    prompt: str,
    providers: ImageProviders,
    *,
    provider: str | None = None,
) -> GeneratedImage:
    """Generate an image and return a public URL usable by Meta Graph API.

    `provider` defaults to `providers.default` ("openai" or "fal").
    """
    name = (provider or providers.default).lower()
    if name == "openai":
        return await _generate_openai(prompt, providers)
    if name == "fal":
        return await _generate_fal(prompt, providers)
    raise ImageProviderError(f"Unknown provider: {name}. Supported: openai, fal.")


async def _generate_openai(prompt: str, providers: ImageProviders) -> GeneratedImage:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ImageProviderError(
            "OPENAI_API_KEY missing in environment. Install with `pip install mcp-fb-publisher[openai]`."
        )
    try:
        from openai import AsyncOpenAI  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImageProviderError(
            "OpenAI SDK not installed. Run `pip install mcp-fb-publisher[openai]`."
        ) from e

    client = AsyncOpenAI(api_key=api_key)
    cfg = providers.openai
    resp = await client.images.generate(model=cfg.model, prompt=prompt, size=cfg.size, n=1)
    if not resp.data:
        raise ImageProviderError("OpenAI returned no image.")
    item = resp.data[0]
    url = getattr(item, "url", None)
    if not url:
        raise ImageProviderError(
            "OpenAI returned base64 instead of url. Use response_format='url' "
            "or upload the bytes to your own storage first."
        )
    return GeneratedImage(url=url, provider="openai", model=cfg.model, prompt=prompt)


async def _generate_fal(prompt: str, providers: ImageProviders) -> GeneratedImage:
    api_key = os.environ.get("FAL_KEY")
    if not api_key:
        raise ImageProviderError(
            "FAL_KEY missing in environment. Install with `pip install mcp-fb-publisher[fal]`."
        )
    try:
        import fal_client  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImageProviderError(
            "fal-client not installed. Run `pip install mcp-fb-publisher[fal]`."
        ) from e

    cfg = providers.fal
    handler = await fal_client.submit_async(
        cfg.model,
        arguments={"prompt": prompt, "image_size": cfg.image_size},
    )
    result = await handler.get()
    images = result.get("images") or []
    if not images:
        raise ImageProviderError("fal.ai returned no image.")
    url = images[0].get("url")
    if not url:
        raise ImageProviderError("fal.ai response missing 'url' field.")
    return GeneratedImage(url=url, provider="fal", model=cfg.model, prompt=prompt)
