# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-08

Initial public release.

### Added
- 4 MCP tools: `fb_publish_post`, `fb_validate_pre_publish`, `fb_anti_duplicate_check`, `fb_generate_post_with_image`.
- YAML / JSON config loader with per-page brand voice, banned topics, image policy.
- Async `MetaClient` wrapper around Meta Graph API v21.0 with token redaction in errors.
- Validator: image-required, banned topics (accent-insensitive substring), length, anti-duplicate (Jaccard 4-grams).
- Image providers: OpenAI (`gpt-image-1`) + fal.ai (`flux-pro/v1.1`), lazy-imported.
- 52 tests, 84% coverage, all offline (httpx MockTransport).
- GitHub Actions CI: Python 3.12 + 3.13 matrix, ruff + pytest + build.
- MIT license.
- `server.json` for MCP registry submission.
