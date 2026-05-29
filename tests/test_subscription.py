"""Tests for subscription matcher."""
import pytest

from app import deps
from app.models import AlertPayload, NewsItem, SentimentResult, Subscription
from app.subscription.matcher import match_subscriptions


def _make_alert(title: str, score: float) -> AlertPayload:
    item = NewsItem(source="test", title=title, title_hash="x")
    sentiment = SentimentResult(news_item=item, score=score, label="negative" if score < 0 else "positive")
    return AlertPayload(news_item=item, sentiment=sentiment)


class TestMatchSubscriptions:
    def setup_method(self):
        deps.active_subscriptions = {}

    def test_keyword_match_and_threshold(self):
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储", "降息"], threshold=-0.5
        )
        alert = _make_alert("美联储宣布降息25个基点", -0.8)
        matched = match_subscriptions(alert)
        assert len(matched) == 1
        sub, kws = matched[0]
        assert "降息" in kws

    def test_keyword_match_but_threshold_not_crossed(self):
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.9
        )
        alert = _make_alert("美联储发布声明", -0.5)
        matched = match_subscriptions(alert)
        assert len(matched) == 0

    def test_no_keyword_match(self):
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["比特币"], threshold=-0.5
        )
        alert = _make_alert("美联储宣布降息", -0.8)
        matched = match_subscriptions(alert)
        assert len(matched) == 0

    def test_multiple_subscriptions(self):
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.5
        )
        deps.active_subscriptions["u2"] = Subscription(
            user_id="u2", keywords=["降息"], threshold=-0.3
        )
        alert = _make_alert("美联储降息", -0.6)
        matched = match_subscriptions(alert)
        assert len(matched) == 2

    def test_positive_score_negative_threshold(self):
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["利好"], threshold=-0.5
        )
        alert = _make_alert("利好消息", 0.6)
        # Positive score doesn't cross negative threshold
        matched = match_subscriptions(alert)
        assert len(matched) == 0

    def test_empty_subscriptions(self):
        alert = _make_alert("测试", -0.8)
        matched = match_subscriptions(alert)
        assert len(matched) == 0

    def test_multiple_keyword_match(self):
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储", "降息", "基点"], threshold=-0.5
        )
        alert = _make_alert("美联储宣布降息25个基点", -0.8)
        matched = match_subscriptions(alert)
        assert len(matched) == 1
        _, kws = matched[0]
        assert len(kws) == 3
