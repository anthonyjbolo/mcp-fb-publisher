"""Configuration loader.

A `config.yaml` describes pages, brand voices, banned topics and image-provider
preferences. The format is designed so the same shape can be embedded in a JSON
secret (cf. the original Edge Function pattern).

Example minimal config (see `config.example.yaml` for the full one):

```yaml
defaults:
  language: en
  brand_voice: |
    Direct, professional, no fluff.
  banned_topics: []
  image_required: true
  anti_duplicate_lookback_days: 14

pages:
  my_page:
    page_id: "1234567890"
    name: "My Page"
    auto_reply_enabled: false

image_providers:
  default: openai
  openai:
    model: gpt-image-1
  fal:
    model: fal-ai/flux-pro/v1.1
```
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PageConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    page_id: str
    name: str
    brand_voice: str | None = None
    language: str | None = None
    banned_topics: list[str] = Field(default_factory=list)
    white_keywords: list[str] = Field(default_factory=list)
    image_required: bool | None = None
    anti_duplicate_lookback_days: int | None = None
    auto_reply_enabled: bool = False


class Defaults(BaseModel):
    model_config = ConfigDict(extra="allow")

    language: str = "en"
    brand_voice: str = "Direct, professional, no fluff."
    banned_topics: list[str] = Field(default_factory=list)
    white_keywords: list[str] = Field(default_factory=list)
    image_required: bool = True
    anti_duplicate_lookback_days: int = 14


class ImageProviderOpenAI(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = "gpt-image-1"
    size: str = "1024x1024"


class ImageProviderFal(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = "fal-ai/flux-pro/v1.1"
    image_size: str = "square_hd"


class ImageProviders(BaseModel):
    model_config = ConfigDict(extra="allow")
    default: str = "openai"
    openai: ImageProviderOpenAI = Field(default_factory=ImageProviderOpenAI)
    fal: ImageProviderFal = Field(default_factory=ImageProviderFal)


class Config(BaseModel):
    model_config = ConfigDict(extra="allow")

    defaults: Defaults = Field(default_factory=Defaults)
    pages: dict[str, PageConfig] = Field(default_factory=dict)
    image_providers: ImageProviders = Field(default_factory=ImageProviders)

    def resolve_page(self, page_id: str) -> tuple[str, PageConfig] | None:
        """Find a page by Meta page_id and merge defaults into it.

        Returns (slug, merged_page_config) or None.
        """
        for slug, cfg in self.pages.items():
            if cfg.page_id == page_id:
                merged_data = self.defaults.model_dump()
                merged_data.update({k: v for k, v in cfg.model_dump().items() if v not in (None, [], "")})
                # Preserve list fields union when relevant
                merged_data["banned_topics"] = list(
                    {*self.defaults.banned_topics, *cfg.banned_topics}
                )
                merged_data["white_keywords"] = list(
                    {*self.defaults.white_keywords, *cfg.white_keywords}
                )
                return slug, PageConfig(**merged_data)
        return None


def load_config(path: str | Path | None = None) -> Config:
    """Load config from YAML file or env var `MCP_FB_PUBLISHER_CONFIG`.

    Resolution order:
      1. Explicit `path` argument.
      2. `MCP_FB_PUBLISHER_CONFIG` env var (file path).
      3. `MCP_FB_PUBLISHER_CONFIG_JSON` env var (raw JSON, useful for serverless).
      4. `./config.yaml` in current working directory.
    """
    if path is None:
        path = os.environ.get("MCP_FB_PUBLISHER_CONFIG")

    if path is None:
        raw_json = os.environ.get("MCP_FB_PUBLISHER_CONFIG_JSON")
        if raw_json:
            data: dict[str, Any] = yaml.safe_load(raw_json)
            return Config(**data)

    if path is None:
        candidate = Path("config.yaml")
        if candidate.exists():
            path = candidate

    if path is None:
        # Empty config still valid (no pages registered)
        return Config()

    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config(**data)
