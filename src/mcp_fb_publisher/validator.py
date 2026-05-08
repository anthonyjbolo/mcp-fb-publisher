"""Pre-publish validation: image-required, banned topics, anti-duplicate.

The validator is intentionally LLM-free so it can run anywhere (no API keys
needed) and produce reproducible results in CI tests. If a caller wants
LLM-grade brand-voice scoring, they can layer it on top.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .config import PageConfig
from .meta_client import FeedPost


@dataclass
class ValidationCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ValidationResult:
    verdict: str  # "go" | "block"
    checks: list[ValidationCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "go"


# ------------- Helpers -------------


def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace, drop URLs and punctuation."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shingles(text: str, n: int = 4) -> set[str]:
    """Word-level n-grams (default 4-grams). Used for fast cheap similarity."""
    words = _normalize(text).split()
    if len(words) < n:
        # treat whole thing as a single shingle to still allow comparison
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard_similarity(a: str, b: str, n: int = 4) -> float:
    """Jaccard similarity over word n-grams. 0.0..1.0. Symmetric."""
    sa = _shingles(a, n)
    sb = _shingles(b, n)
    if not sa or not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    if not union:
        return 0.0
    return len(inter) / len(union)


# ------------- Checks -------------


def check_image_required(message: str, image_url: str | None, page: PageConfig) -> ValidationCheck:
    required = page.image_required if page.image_required is not None else True
    if required and not image_url:
        return ValidationCheck(
            "image_required",
            ok=False,
            detail="Image required by config but no image_url provided.",
        )
    return ValidationCheck("image_required", ok=True, detail="image attached" if image_url else "image not required")


def check_banned_topics(message: str, page: PageConfig) -> ValidationCheck:
    if not page.banned_topics:
        return ValidationCheck("banned_topics", ok=True, detail="no banned topics configured")
    norm = _normalize(message)
    hits = [t for t in page.banned_topics if _normalize(t) and _normalize(t) in norm]
    if hits:
        return ValidationCheck(
            "banned_topics",
            ok=False,
            detail=f"banned topic(s) detected: {', '.join(hits)}",
        )
    return ValidationCheck("banned_topics", ok=True, detail="clean")


def check_message_length(message: str, *, min_chars: int = 10, max_chars: int = 63206) -> ValidationCheck:
    """Meta hard limit is 63206 chars; we also reject empty/very short."""
    n = len(message or "")
    if n < min_chars:
        return ValidationCheck("length", ok=False, detail=f"too short ({n} < {min_chars})")
    if n > max_chars:
        return ValidationCheck("length", ok=False, detail=f"too long ({n} > {max_chars})")
    return ValidationCheck("length", ok=True, detail=f"{n} chars")


def check_anti_duplicate(
    message: str,
    recent_posts: list[FeedPost],
    *,
    lookback_days: int,
    similarity_threshold: float = 0.5,
) -> ValidationCheck:
    """Compare against recent posts using Jaccard 4-grams.

    Returns BLOCK if any post within `lookback_days` exceeds threshold.
    """
    if not recent_posts:
        return ValidationCheck("anti_duplicate", ok=True, detail="no recent posts to compare")

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    candidates: list[FeedPost] = []
    for p in recent_posts:
        try:
            ts = datetime.fromisoformat(p.created_time.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        except (ValueError, AttributeError):
            ts = datetime.now(UTC)
        if ts >= cutoff:
            candidates.append(p)

    if not candidates:
        return ValidationCheck("anti_duplicate", ok=True, detail=f"no posts in last {lookback_days}d")

    best_match: tuple[float, FeedPost] | None = None
    for p in candidates:
        sim = jaccard_similarity(message, p.message, n=4)
        if best_match is None or sim > best_match[0]:
            best_match = (sim, p)

    assert best_match is not None
    sim, p = best_match
    if sim >= similarity_threshold:
        return ValidationCheck(
            "anti_duplicate",
            ok=False,
            detail=(
                f"too similar to existing post {p.id} (jaccard={sim:.2f}, "
                f"created={p.created_time}). Threshold={similarity_threshold:.2f}"
            ),
        )
    return ValidationCheck(
        "anti_duplicate",
        ok=True,
        detail=f"closest jaccard={sim:.2f} below {similarity_threshold:.2f}",
    )


# ------------- Public API -------------


def validate_pre_publish(
    message: str,
    image_url: str | None,
    page: PageConfig,
    recent_posts: list[FeedPost] | None = None,
    *,
    similarity_threshold: float = 0.5,
) -> ValidationResult:
    """Run all sync checks. `recent_posts` is optional; if None, anti-dup is skipped.

    Caller is expected to fetch recent posts via MetaClient when network is OK.
    """
    checks: list[ValidationCheck] = [
        check_image_required(message, image_url, page),
        check_banned_topics(message, page),
        check_message_length(message),
    ]

    if recent_posts is not None:
        lookback = page.anti_duplicate_lookback_days or 14
        checks.append(
            check_anti_duplicate(
                message, recent_posts, lookback_days=lookback, similarity_threshold=similarity_threshold
            )
        )
    else:
        checks.append(
            ValidationCheck(
                "anti_duplicate",
                ok=True,
                detail="skipped (no recent_posts provided)",
            )
        )

    failed = [c for c in checks if not c.ok]
    return ValidationResult(
        verdict="block" if failed else "go",
        checks=checks,
        errors=[c.detail for c in failed],
    )
