# LinkedIn post draft — `mcp-fb-publisher` launch

> **STATUS: DRAFT — NOT PUBLISHED YET.** Tini reviews + adjusts tone + posts personally.
> Photo: real shoot of Tini (per `linkedin-launch-2026-05-01.md` law — no AI portraits on LinkedIn).
> Target audience: B2B decision-makers, MCP/agent builders, Anthropic ecosystem watchers.
> Length target: ~1500 words (long-form post, max LinkedIn allows). Trim before posting if needed.
> #BuiltOnClaudeCode hashtag mandatory.

---

## Headline / hook (first 3 lines = above the fold)

> I run 5 Facebook Pages from a small studio in the South Pacific.
> Last month an agent tried to post the exact same launch announcement twice in 48 hours.
> Today I open-sourced the MCP server I wrote so it cannot happen again.

---

## Body

### The setup

I have a small studio that ships software end-to-end for SMBs around the Pacific — local driving school, a media page, a dev studio brand, a community page, a marketing-test page. Each one has its own voice. Each one has a different posting cadence. Each one has its own list of competitor names that must never appear in copy.

When I started letting an agent draft and publish posts directly, four failure modes hit me in the first month:

1. **Token expired silently.** Meta long-lived tokens last 60 days. The agent tries to post at midnight, gets a 400 back, the post never lands, nobody notices for three days.
2. **Replay / near-duplicate.** Same angle posted twice in 14 days because the agent had no memory of last week's output. Reach drops, audience tunes out.
3. **Image-required violation.** One brand mandates a visual on every post (engagement on text-only posts is half what it is on image posts in my niche). The agent shipped a text-only post on a Friday afternoon. Reach was a third of normal.
4. **Banned topic leaked.** A draft mentioned a competitor brand in a comparison the agent thought was clever. It was not.

After the fourth incident I stopped pretending these were edge cases. They are the default failure mode when you let an LLM drive the Meta Graph API without scaffolding. So I wrote the scaffolding.

### What it is

[`mcp-fb-publisher`](https://github.com/anthonyjbolo/mcp-fb-publisher) is an MCP server (Model Context Protocol — Anthropic's open standard for tool-use). It exposes 4 tools to any MCP-compatible LLM:

- `fb_publish_post` — publishes (or schedules) a post to a Facebook Page via Meta Graph API.
- `fb_validate_pre_publish` — runs all guardrails as a dry-run, returns `verdict: go|block` plus per-check details.
- `fb_anti_duplicate_check` — compares a candidate against the page's recent posts using Jaccard similarity over word 4-grams.
- `fb_generate_post_with_image` — generates an image (OpenAI `gpt-image-1` or fal.ai `flux-pro`) and returns a URL ready to post.

Every publish call goes through validation by default. The validator is **pure Python, offline, deterministic** — no LLM in the loop, no extra API key, runs in 5ms in CI.

You drop a `config.yaml` describing your pages, your brand voices, your banned topics, your image policy. You set `META_USER_TOKEN` in env. You wire it into Claude Desktop or Claude Code in 30 seconds. Then you ask Claude things like:

> *"Post on the marketing page: 'Summer collection drops Friday'. Generate the image first, validate, then publish."*

Claude calls `fb_generate_post_with_image` → `fb_validate_pre_publish` → `fb_publish_post`, and you watch the chain run.

### The 4 fails it actually prevents

#### Fail 1 — Token expiry

Meta tokens silently expire. The library's `MetaClient.debug_token()` returns `days_left`. I run a daily cron that pings ntfy when `days_left < 7`. The OSS version doesn't ship the cron (out of scope), but the primitive is there for anyone to wire up. **Catching this fail saves: 3 days of dead automation per quarter.**

#### Fail 2 — Replay / near-duplicate

This is the one I lost the most sleep on. The OSS version implements **Jaccard similarity over word 4-grams** after normalization (lowercase, strip accents, drop URLs, drop punctuation). Default threshold = 0.5. Lookback window per page (14 days for evergreen content, 7 days for promos).

I considered embeddings. I rejected them for v1 for three reasons: deterministic in tests, no extra API key, sub-5ms latency. If you want semantic comparison on top, the tool returns the closest post ID and the score so your agent can chain a second LLM call. **Catching this fail saves: ~30% reach loss when audience hits "seen this already" pattern.**

#### Fail 3 — Image required

Per-page boolean. Banal but not negotiable. If your brand mandates an image and the agent skipped it, the publish call returns:

```json
{"ok": false, "error": "validation_blocked",
 "validation": {"verdict": "block", "errors": ["Image required by config but no image_url provided."]}}
```

The agent is now forced to call `fb_generate_post_with_image` (or hand-pick a URL), then retry. **Catching this fail saves: about half the reach on text-only mistakes in image-heavy niches.**

#### Fail 4 — Banned topic leak

Substring check, accent-insensitive, lowercased. Yes — substring is dumb. Yes — it's what works in production. Configure it once with the names that must never appear, forget about it. The validator returns the exact word that triggered the block. **Catching this fail saves: at minimum one awkward post you have to delete in front of customers.**

### Why open-source it

Three reasons:

1. **The pattern is generic.** Every operator running multi-page social automation hits the same four fails. There is nothing TNZ-specific in `mcp-fb-publisher` — it's a Meta Graph API wrapper with deterministic guardrails. Keeping it private would be hoarding.
2. **MCP needs more reference servers in production-y domains.** The official registry has filesystem, fetch, weather, sqlite. We need more "ship to a real platform with real guardrails" examples. This is one.
3. **It forces my own quality bar up.** Code I open-source gets better tests, better docs, better licensing hygiene. Code I keep private decays.

### Live demo

I run this server in production behind one of our public test pages, [Atelier 687](https://www.facebook.com/atelier687). It's the studio's marketing-experiment page. You'll see the cadence: one post per day, image always present, no two posts within 14 days hit the same angle. That cadence is enforced by the same code you can pull from PyPI right now.

### Spec sheet

- **Stack**: Python 3.12+, FastMCP (Anthropic's official Python SDK), `httpx` async, Pydantic 2 for config.
- **Tests**: 52 tests, 84% coverage, zero real network calls (everything mocked via `httpx.MockTransport`).
- **CI**: GitHub Actions, Python 3.12 + 3.13 matrix, ruff + pytest + build artifact.
- **License**: MIT.
- **Deps**: minimal — `mcp[cli]`, `httpx`, `pydantic`, `pyyaml`. Optional `openai` / `fal-client` extras.
- **MCP Registry**: submitted as `io.github.anthonyjbolo/mcp-fb-publisher` (preview registry, namespace authenticated via GitHub).

### What's next

- Instagram Graph API support (the validator already works; only the publish path needs adapting).
- Token rotation helper as a 5th tool.
- Optional ntfy webhook on publish failure.

If you run multi-page social automation, try it. If you find a fail mode I missed, open an issue. If you want help wiring it into a bigger agent stack, my DMs are open.

Code: https://github.com/anthonyjbolo/mcp-fb-publisher

Anthony Bolo
Founder, TNZ Lab

#MCP #Anthropic #ClaudeCode #OpenSource #SocialMediaAutomation #BuiltOnClaudeCode

---

## Notes for Tini before publishing

- **Photo**: use the LinkedIn-approved real shoot (the one Iris already prepared as a placeholder is OK only if you have nothing else; LinkedIn law is real photo).
- **Page tag**: tag `@TNZ Lab` company page in the post.
- **First comment**: drop the GitHub link as the first comment to boost reach (LinkedIn algo penalizes external links in the body).
- **Companion graphic**: optional 1080x1080 image with the 4 fails as bullet points. Use Atelier 687's brand palette, not a generic stock graphic.
- **Reposting**: re-share on FB / Insta only AFTER LinkedIn engagement settles (per linkedin-launch-2026-05-01.md — anonymity rule).
- **CRITICAL — laws verified**:
  - No mention of Konduir / Konduir Pro / Konduir Code / driving-school SaaS anywhere in this draft. Verified by ctrl-F.
  - No mention of AI / LLM / Claude in customer-facing posts on the test page (Atelier 687) when the demo runs.
  - "Anthony" alone in the FB cold lane is irrelevant here — LinkedIn explicitly allows full identity.
  - No fake testimonials.
- **Tracking**: log the post URL in `~/Documents/TNZ/.brain/HOT.md` after Tini publishes — useful for the C8 Claude ROI dashboard (sister chantier).
