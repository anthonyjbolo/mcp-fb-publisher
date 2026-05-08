"""Validator unit tests — pure functions, zero network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp_fb_publisher.config import PageConfig
from mcp_fb_publisher.meta_client import FeedPost
from mcp_fb_publisher.validator import (
    check_anti_duplicate,
    check_banned_topics,
    check_image_required,
    check_message_length,
    jaccard_similarity,
    validate_pre_publish,
)

# ----- jaccard -----


def test_jaccard_identical():
    a = "the quick brown fox jumps over the lazy dog and runs fast"
    assert jaccard_similarity(a, a, n=4) == 1.0


def test_jaccard_disjoint():
    a = "we just shipped a new feature for our customers today"
    b = "totally unrelated topic about cooking pasta with tomato sauce"
    assert jaccard_similarity(a, b, n=4) < 0.1


def test_jaccard_accent_insensitive():
    """Normalisation strips accents — French test."""
    a = "Lancement de l'application Élégance pour les boulangers"
    b = "Lancement de l application Elegance pour les boulangers"
    assert jaccard_similarity(a, b, n=4) > 0.9


def test_jaccard_empty():
    assert jaccard_similarity("", "anything", n=4) == 0.0
    assert jaccard_similarity("anything", "", n=4) == 0.0


# ----- image required -----


def test_image_required_pass_when_present():
    page = PageConfig(page_id="1", name="P", image_required=True)
    c = check_image_required("hi", "https://example.com/img.png", page)
    assert c.ok


def test_image_required_block_when_missing():
    page = PageConfig(page_id="1", name="P", image_required=True)
    c = check_image_required("hi there", None, page)
    assert not c.ok
    assert "image required" in c.detail.lower()


def test_image_optional_pass_when_missing():
    page = PageConfig(page_id="1", name="P", image_required=False)
    c = check_image_required("hi", None, page)
    assert c.ok


# ----- banned topics -----


def test_banned_topic_detected_substring():
    page = PageConfig(page_id="1", name="P", banned_topics=["secret_codename"])
    c = check_banned_topics("Excited to announce the secret_codename launch!", page)
    assert not c.ok


def test_banned_topic_accent_insensitive():
    page = PageConfig(page_id="1", name="P", banned_topics=["bénin"])
    c = check_banned_topics("La situation est BENIN aujourd'hui", page)
    assert not c.ok


def test_banned_topic_clean_passes():
    page = PageConfig(page_id="1", name="P", banned_topics=["forbidden"])
    c = check_banned_topics("Totally clean post about nothing forbid... wait", page)
    # "forbid" is substring of "forbidden" — should NOT match (banned is "forbidden")
    assert c.ok


def test_banned_topic_no_config_passes():
    page = PageConfig(page_id="1", name="P", banned_topics=[])
    c = check_banned_topics("anything goes", page)
    assert c.ok


# ----- length -----


def test_length_too_short():
    c = check_message_length("hi")
    assert not c.ok


def test_length_too_long():
    c = check_message_length("x" * 70000)
    assert not c.ok


def test_length_ok():
    c = check_message_length("This is a totally fine length message.")
    assert c.ok


# ----- anti-duplicate -----


def _post(msg: str, days_ago: int = 1, post_id: str = "p") -> FeedPost:
    ts = datetime.now(UTC) - timedelta(days=days_ago)
    return FeedPost(id=post_id, message=msg, created_time=ts.isoformat())


def test_anti_duplicate_blocks_near_duplicate():
    candidate = "Big sale this weekend on all baking supplies, free delivery in town"
    recent = [_post(candidate, days_ago=2, post_id="123")]
    c = check_anti_duplicate(candidate, recent, lookback_days=14, similarity_threshold=0.5)
    assert not c.ok
    assert "123" in c.detail


def test_anti_duplicate_allows_different_message():
    candidate = "We are hiring two senior bakers in Paris, French speakers welcome"
    recent = [_post("Totally different sale on cookies this Friday only", days_ago=2)]
    c = check_anti_duplicate(candidate, recent, lookback_days=14, similarity_threshold=0.5)
    assert c.ok


def test_anti_duplicate_ignores_old_posts():
    candidate = "Big sale this weekend on all baking supplies, free delivery in town"
    recent = [_post(candidate, days_ago=30)]  # outside 14-day window
    c = check_anti_duplicate(candidate, recent, lookback_days=14, similarity_threshold=0.5)
    assert c.ok


def test_anti_duplicate_empty_recent():
    c = check_anti_duplicate("anything", [], lookback_days=14)
    assert c.ok


# ----- end-to-end validate_pre_publish -----


def test_validate_pre_publish_go():
    page = PageConfig(page_id="1", name="P", banned_topics=["secret"], image_required=True)
    res = validate_pre_publish(
        "We launched a great new feature today, check it out friends!",
        "https://example.com/img.png",
        page,
        recent_posts=[],
    )
    assert res.ok
    assert res.verdict == "go"


def test_validate_pre_publish_block_image():
    page = PageConfig(page_id="1", name="P", image_required=True)
    res = validate_pre_publish("A nice long enough message", None, page, recent_posts=[])
    assert not res.ok
    assert any(c.name == "image_required" and not c.ok for c in res.checks)


def test_validate_pre_publish_block_banned():
    page = PageConfig(page_id="1", name="P", banned_topics=["secret"])
    res = validate_pre_publish(
        "We unveil our SECRET project today, hooray!",
        "https://example.com/img.png",
        page,
        recent_posts=[],
    )
    assert not res.ok


def test_validate_pre_publish_block_dup():
    page = PageConfig(page_id="1", name="P", anti_duplicate_lookback_days=14)
    msg = "Big sale this weekend on all baking supplies, free delivery in town"
    res = validate_pre_publish(
        msg,
        "https://example.com/img.png",
        page,
        recent_posts=[_post(msg, days_ago=1)],
    )
    assert not res.ok


def test_validate_pre_publish_skipped_when_recent_none():
    page = PageConfig(page_id="1", name="P")
    res = validate_pre_publish(
        "Long enough perfectly fine message here",
        "https://example.com/img.png",
        page,
        recent_posts=None,
    )
    assert res.ok
    assert any(c.name == "anti_duplicate" and "skipped" in c.detail for c in res.checks)
