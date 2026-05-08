# Contributing

Thanks for the interest. PRs and issues welcome.

## Development setup

```bash
git clone https://github.com/anthonyjbolo/mcp-fb-publisher.git
cd mcp-fb-publisher
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,openai,fal]"
```

## Running tests

```bash
pytest
```

All tests must run **offline** with no real Meta credentials. Use `httpx.MockTransport` (see `tests/conftest.py` for the pattern). PRs that introduce real network calls in tests will be asked to remove them.

## Linting

```bash
ruff check .
ruff check . --fix   # auto-fix
```

## Coverage target

>=80% for `src/mcp_fb_publisher/`. CI will warn if it drops.

## Commit style

Conventional commits encouraged but not enforced:

```
feat: add fb_check_token_expiry tool
fix(meta): redact token in 5xx error message
docs: clarify anti-duplicate algorithm
test: cover empty config edge case
```

## Reporting security issues

For vulnerabilities (e.g. token leakage, command injection in config parsing), please email `anthonyj.bolo@gmail.com` privately rather than opening a public issue.

## Code of conduct

Be civil. We're all here to ship better software.
