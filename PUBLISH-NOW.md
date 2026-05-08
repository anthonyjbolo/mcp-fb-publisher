# PUBLISH-NOW — final 3 steps Tini

> Auto-mode could not complete the push because:
> - `gh` CLI is currently authenticated as **TnTnc1** (private TNZ namespace).
> - The garde-fou explicitly forbids pushing this OSS repo to TnTnc1.
> - The personal GitHub account **anthonyjbolo** does not exist yet (verified via `gh api users/anthonyjbolo` → 404).
>
> So everything is built, tested, committed locally. You complete the public release in 3 steps below.

## Status of the local repo

```
~/Documents/TNZ/oss/mcp-fb-publisher/
├── 23 files
├── 1 git commit on branch main
├── 52/52 tests passing, 84% coverage
├── ruff clean
├── wheel builds (mcp_fb_publisher-0.1.0-py3-none-any.whl)
├── server.json valid
└── LICENSE MIT, README polished, ARCHITECTURE.md mermaid OK
```

## Step 1 — Create the personal GitHub account (~2 min)

Open https://github.com/signup in TNZ Browser and create the account `anthonyjbolo`.

Use the personal email (NOT `tinz@tnzlab.com` — keep tnzlab as the org email). Suggested: `anthonyj.bolo@gmail.com`.

> Why `anthonyjbolo` not `anthonybolo`: both are free, `anthonyjbolo` matches the namespace already encoded in `pyproject.toml`, `README.md` badges, `server.json` (`io.github.anthonyjbolo/...`) and the LinkedIn draft. Renaming = 7 file changes. If you really want `anthonybolo`, run before pushing:
> ```bash
> cd ~/Documents/TNZ/oss/mcp-fb-publisher
> grep -rl anthonyjbolo . | xargs sed -i '' 's/anthonyjbolo/anthonybolo/g'
> git add . && git commit --amend --no-edit
> ```

## Step 2 — Auth + create + push (~3 min)

Switch `gh` to the personal account:

```bash
gh auth login --hostname github.com --git-protocol https --web
# Pick "Login with a web browser", paste the one-time code in the new account.
gh auth status
# Should show TWO accounts; the new one (anthonyjbolo) becomes Active.
```

Then create the public repo and push:

```bash
cd ~/Documents/TNZ/oss/mcp-fb-publisher
gh repo create anthonyjbolo/mcp-fb-publisher \
    --public \
    --source=. \
    --remote=origin \
    --description "MCP server for safe multi-page Facebook publishing with brand voice, banned-topic and anti-duplication guardrails. #BuiltOnClaudeCode" \
    --push
```

Verify:

```bash
gh repo view anthonyjbolo/mcp-fb-publisher --json url,visibility,description
# visibility should be PUBLIC.
```

CI will trigger automatically on push. Watch:

```bash
gh run list --repo anthonyjbolo/mcp-fb-publisher
```

## Step 3 — Submit to MCP registry (~5 min)

The official MCP registry is currently in preview (https://modelcontextprotocol.io/registry). Submission is via a CLI tool, not a PR.

```bash
# 1. Install the publisher CLI (Homebrew or download binary)
brew install mcp-publisher

# 2. Validate server.json against the schema
cd ~/Documents/TNZ/oss/mcp-fb-publisher
mcp-publisher validate ./server.json

# 3. Login with the GitHub account that owns the namespace
mcp-publisher login github
# Browser opens. Log in as anthonyjbolo. The CLI verifies you own io.github.anthonyjbolo/*

# 4. Publish
mcp-publisher publish ./server.json
```

The server will appear at `https://registry.modelcontextprotocol.io/v0/servers?search=mcp-fb-publisher` once propagated (usually <1h).

## Step 4 — (Optional but recommended) Publish to PyPI

Letting users `pip install mcp-fb-publisher` makes the registry entry actually useful.

```bash
# Already built locally:
ls dist/
# mcp_fb_publisher-0.1.0-py3-none-any.whl
# mcp_fb_publisher-0.1.0.tar.gz

# Create PyPI account at https://pypi.org/account/register/ if you don't have one.
# Then create an API token at https://pypi.org/manage/account/token/.
# Save it in 1Password / .brain/.env (NOT committed).

pip install --user twine
TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-AgENd... twine upload dist/*
```

After upload:

```bash
pip install mcp-fb-publisher  # works for everyone immediately
```

If you skip PyPI, change `server.json`'s `packages[0].registryType` to `"github"` and point at the source release.

## Step 5 — Post LinkedIn (after CI green + registry live)

`LINKEDIN-DRAFT.md` is in the repo. Tini reviews + adjusts tone + posts personally per the linkedin-launch-2026-05-01.md rules:

- Real photo (not Iris).
- LinkedIn first, FB/IG mirror only after the post settles (anonymity rule).
- GitHub link as the FIRST COMMENT, not in the body (algo penalty).
- Tag `@TNZ Lab` company page.
- Hashtag `#BuiltOnClaudeCode` mandatory.

## What I did not do (per garde-fous)

- No `gh repo create` under the wrong namespace.
- No `pypi.org` account creation under your name (needs your password / 2FA).
- No publishing the LinkedIn post.
- No edits to `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/Documents/TNZ/.brain/HOT.md`, `MEMORY.md`, `~/Documents/TNZ/.brain/.env`.
- No touching TNZ Compta or `cortex_router_calls` (C8 sister-chantier turf).

## Rollback

If anything goes wrong with the public push:

```bash
gh repo delete anthonyjbolo/mcp-fb-publisher --yes   # nukes the GitHub side
# Local repo is unaffected; you can re-push after fixes.
```
