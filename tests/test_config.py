"""Config loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_fb_publisher.config import Config, load_config


def test_load_yaml(tmp_path: Path):
    cfg_text = """
defaults:
  language: en
  brand_voice: "Be concise."
  banned_topics: [competitor_x]
  image_required: true

pages:
  main:
    page_id: "1234"
    name: "Main"
    banned_topics: [secret]
"""
    p = tmp_path / "config.yaml"
    p.write_text(cfg_text)
    cfg = load_config(p)
    assert "main" in cfg.pages
    assert cfg.pages["main"].page_id == "1234"


def test_resolve_page_merges_defaults(tmp_path: Path):
    cfg_text = """
defaults:
  banned_topics: [global_banned]
  image_required: true
  anti_duplicate_lookback_days: 14

pages:
  marketing:
    page_id: "999"
    name: "Marketing"
    banned_topics: [page_specific]
"""
    p = tmp_path / "config.yaml"
    p.write_text(cfg_text)
    cfg = load_config(p)
    match = cfg.resolve_page("999")
    assert match is not None
    slug, page = match
    assert slug == "marketing"
    assert "global_banned" in page.banned_topics
    assert "page_specific" in page.banned_topics
    assert page.image_required is True
    assert page.anti_duplicate_lookback_days == 14


def test_resolve_page_unknown_returns_none():
    cfg = Config()
    assert cfg.resolve_page("does_not_exist") is None


def test_load_config_from_env_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "MCP_FB_PUBLISHER_CONFIG_JSON",
        '{"pages": {"x": {"page_id": "42", "name": "X"}}}',
    )
    monkeypatch.delenv("MCP_FB_PUBLISHER_CONFIG", raising=False)
    cfg = load_config()
    assert cfg.pages["x"].page_id == "42"


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_empty_config_is_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """No config at all -> empty Config (no pages)."""
    monkeypatch.delenv("MCP_FB_PUBLISHER_CONFIG", raising=False)
    monkeypatch.delenv("MCP_FB_PUBLISHER_CONFIG_JSON", raising=False)
    monkeypatch.chdir(tmp_path)  # no config.yaml here
    cfg = load_config()
    assert cfg.pages == {}


def test_example_config_is_valid():
    """Sanity-check the bundled example file actually parses."""
    repo_root = Path(__file__).resolve().parent.parent
    example = repo_root / "config.example.yaml"
    cfg = load_config(example)
    assert "marketing_main" in cfg.pages
    assert cfg.image_providers.default in ("openai", "fal")
