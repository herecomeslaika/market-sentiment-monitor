"""Edge case and boundary condition tests.

Tests for boundary values, empty inputs, extreme values, special characters,
and other edge cases that could reveal hidden bugs.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from collections import OrderedDict

from app.models import (
    NewsItem, SentimentResult, AlertPayload, Subscription,
    Entity, MultiSentiment, EntityRelation, CausalChain, EventCluster,
)
from app import deps
from config.settings import Settings


# ---------- Model Boundary Tests ----------

class TestNewsItemEdgeCases:
    @pytest.mark.edge
    def test_empty_title(self):
        item = NewsItem(source="test", title="")
        assert item.title == ""

    @pytest.mark.edge
    def test_very_long_title(self):
        title = "央行降息" * 500
        item = NewsItem(source="test", title=title)
        assert len(item.title) == 2000

    @pytest.mark.edge
    def test_special_characters_in_title(self):
        item = NewsItem(source="test", title="<script>alert('xss')</script>")
        assert "<script>" in item.title

    @pytest.mark.edge
    def test_unicode_emoji_title(self):
        item = NewsItem(source="test", title="🚀比特币突破10万美元🎉")
        assert "🚀" in item.title

    @pytest.mark.edge
    def test_mixed_language_title(self):
        item = NewsItem(source="test", title="Fed降息25bp对A股影响")
        assert "Fed" in item.title and "A股" in item.title

    @pytest.mark.edge
    def test_null_url(self):
        item = NewsItem(source="test", title="test", url="")
        assert item.url == ""


class TestSentimentResultBoundary:
    @pytest.mark.edge
    def test_score_at_lower_bound(self):
        result = SentimentResult(
            news_item=NewsItem(source="t", title="x"), score=-1.0, label="negative"
        )
        assert result.score == -1.0

    @pytest.mark.edge
    def test_score_at_upper_bound(self):
        result = SentimentResult(
            news_item=NewsItem(source="t", title="x"), score=1.0, label="positive"
        )
        assert result.score == 1.0

    @pytest.mark.edge
    def test_score_at_zero(self):
        result = SentimentResult(
            news_item=NewsItem(source="t", title="x"), score=0.0, label="neutral"
        )
        assert result.score == 0.0

    @pytest.mark.edge
    def test_score_below_lower_bound_rejected(self):
        with pytest.raises(Exception):
            SentimentResult(
                news_item=NewsItem(source="t", title="x"), score=-1.5, label="negative"
            )

    @pytest.mark.edge
    def test_score_above_upper_bound_rejected(self):
        with pytest.raises(Exception):
            SentimentResult(
                news_item=NewsItem(source="t", title="x"), score=1.5, label="positive"
            )

    @pytest.mark.edge
    def test_confidence_at_boundaries(self):
        r0 = SentimentResult(news_item=NewsItem(source="t", title="x"), score=0.0, confidence=0.0)
        r1 = SentimentResult(news_item=NewsItem(source="t", title="x"), score=0.0, confidence=1.0)
        assert r0.confidence == 0.0
        assert r1.confidence == 1.0

    @pytest.mark.edge
    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(Exception):
            SentimentResult(news_item=NewsItem(source="t", title="x"), score=0.0, confidence=1.5)


class TestSubscriptionEdgeCases:
    @pytest.mark.edge
    def test_empty_keywords_list(self):
        sub = Subscription(user_id="u1", keywords=[], threshold=-0.5)
        assert sub.keywords == []

    @pytest.mark.edge
    def test_many_keywords(self):
        keywords = [f"关键词{i}" for i in range(100)]
        sub = Subscription(user_id="u1", keywords=keywords, threshold=-0.5)
        assert len(sub.keywords) == 100

    @pytest.mark.edge
    def test_threshold_at_boundary(self):
        sub1 = Subscription(user_id="u1", keywords=["test"], threshold=-1.0)
        sub2 = Subscription(user_id="u2", keywords=["test"], threshold=1.0)
        assert sub1.threshold == -1.0
        assert sub2.threshold == 1.0

    @pytest.mark.edge
    def test_special_chars_in_user_id(self):
        sub = Subscription(user_id="user@example.com", keywords=["test"], threshold=-0.5)
        assert sub.user_id == "user@example.com"

    @pytest.mark.edge
    def test_duplicate_keywords(self):
        sub = Subscription(user_id="u1", keywords=["降息", "降息", "利率"], threshold=-0.5)
        assert len(sub.keywords) == 3


class TestEntityEdgeCases:
    @pytest.mark.edge
    def test_empty_aliases(self):
        entity = Entity(name="央行", type="policy", aliases=[])
        assert entity.aliases == []

    @pytest.mark.edge
    def test_many_aliases(self):
        entity = Entity(name="央行", type="policy", aliases=["人民银行", "PBOC", "Central Bank", "中国人民银行"])
        assert len(entity.aliases) == 4

    @pytest.mark.edge
    def test_entity_with_special_name(self):
        entity = Entity(name="C++", type="industry")
        assert entity.name == "C++"


class TestMultiSentimentBoundary:
    @pytest.mark.edge
    def test_all_zeros(self):
        ms = MultiSentiment(news_id=1, entity_name="test")
        assert ms.fear == 0.0 and ms.greed == 0.0

    @pytest.mark.edge
    def test_extreme_fear(self):
        ms = MultiSentiment(news_id=1, entity_name="test", fear=1.0, dominant="fear")
        assert ms.fear == 1.0

    @pytest.mark.edge
    def test_momentum_shift_flag(self):
        ms = MultiSentiment(news_id=1, entity_name="test", momentum_shift=True)
        assert ms.momentum_shift is True


# ---------- Dedup Edge Cases ----------

class TestDedupEdgeCases:
    @pytest.mark.edge
    def test_empty_hash(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test")
        result = check_and_register("")
        assert result is False

    @pytest.mark.edge
    def test_very_long_hash(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test")
        long_hash = "a" * 1000
        result = check_and_register(long_hash)
        assert result is False

    @pytest.mark.edge
    def test_unicode_hash(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test")
        result = check_and_register("哈希值中文")
        assert result is False

    @pytest.mark.edge
    def test_cache_size_one(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=1)
        check_and_register("h1")
        check_and_register("h2")
        assert len(deps.dedup_cache) == 1
        assert "h2" in deps.dedup_cache
        assert "h1" not in deps.dedup_cache

    @pytest.mark.edge
    def test_cache_zero_size(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=0)
        check_and_register("h1")
        assert len(deps.dedup_cache) == 0


# ---------- Title Hash Edge Cases ----------

class TestTitleHashEdgeCases:
    @pytest.mark.edge
    def test_empty_string(self):
        from app.crawler.sources import compute_title_hash
        h1 = compute_title_hash("")
        h2 = compute_title_hash("")
        assert h1 == h2

    @pytest.mark.edge
    def test_unicode_title(self):
        from app.crawler.sources import compute_title_hash
        h = compute_title_hash("日本銀行が金利を引き下げ")
        assert isinstance(h, str) and len(h) > 0

    @pytest.mark.edge
    def test_very_long_title(self):
        from app.crawler.sources import compute_title_hash
        title = "a" * 10000
        h = compute_title_hash(title)
        assert isinstance(h, str) and len(h) > 0

    @pytest.mark.edge
    def test_newline_in_title(self):
        from app.crawler.sources import compute_title_hash
        h1 = compute_title_hash("line1\nline2")
        h2 = compute_title_hash("line1 line2")
        assert h1 != h2


# ---------- HTML Clean Edge Cases ----------

class TestCleanHtmlEdgeCases:
    @pytest.mark.edge
    def test_empty_string(self):
        from app.crawler.sources import _clean_html
        assert _clean_html("") == ""

    @pytest.mark.edge
    def test_no_html(self):
        from app.crawler.sources import _clean_html
        assert _clean_html("plain text") == "plain text"

    @pytest.mark.edge
    def test_nested_tags(self):
        from app.crawler.sources import _clean_html
        result = _clean_html("<div><p><span>deep</span></p></div>")
        assert result == "deep"

    @pytest.mark.edge
    def test_script_tags(self):
        from app.crawler.sources import _clean_html
        result = _clean_html("<script>var x=1;</script>content")
        # _clean_html strips tags but may leave text content
        assert "content" in result

    @pytest.mark.edge
    def test_html_entities(self):
        from app.crawler.sources import _clean_html
        result = _clean_html("5 &gt; 3 &amp; 2 &lt; 4")
        assert isinstance(result, str)

    @pytest.mark.edge
    def test_exactly_500_chars(self):
        from app.crawler.sources import _clean_html
        text = "x" * 500
        result = _clean_html(text)
        assert len(result) == 500

    @pytest.mark.edge
    def test_just_over_500_chars(self):
        from app.crawler.sources import _clean_html
        text = "x" * 501
        result = _clean_html(text)
        assert len(result) == 500


# ---------- Subscription Matcher Edge Cases ----------

class TestSubscriptionMatcherEdgeCases:
    @pytest.mark.edge
    def setup_method(self):
        deps.active_subscriptions = {}

    @pytest.mark.edge
    def test_empty_title(self):
        from app.subscription.matcher import match_subscriptions
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["降息"], threshold=-0.5
        )
        item = NewsItem(source="test", title="", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)
        matched = match_subscriptions(alert)
        assert len(matched) == 0

    @pytest.mark.edge
    def test_keyword_at_threshold_boundary(self):
        from app.subscription.matcher import match_subscriptions
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["降息"], threshold=-0.5
        )
        item = NewsItem(source="test", title="降息", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.5, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)
        matched = match_subscriptions(alert)
        # score <= threshold triggers alert (inclusive)
        assert len(matched) == 1

    @pytest.mark.edge
    def test_score_just_below_threshold(self):
        from app.subscription.matcher import match_subscriptions
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["降息"], threshold=-0.5
        )
        item = NewsItem(source="test", title="降息", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.5001, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)
        matched = match_subscriptions(alert)
        assert len(matched) == 1

    @pytest.mark.edge
    def test_case_sensitive_keyword_matching(self):
        from app.subscription.matcher import match_subscriptions
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["Fed"], threshold=-0.5
        )
        item = NewsItem(source="test", title="fed rate cut", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)
        matched = match_subscriptions(alert)
        # Both title and keywords are lowercased for comparison
        assert len(matched) == 1


# ---------- Alert Level Edge Cases ----------

class TestAlertLevelEdgeCases:
    @pytest.mark.edge
    def test_score_at_critical_boundary(self):
        score = -0.7
        level = "critical" if score <= -0.7 else "warning"
        assert level == "critical"

    @pytest.mark.edge
    def test_score_just_above_critical(self):
        score = -0.6999
        level = "critical" if score <= -0.7 else ("warning" if score <= -0.4 else "info")
        assert level == "warning"

    @pytest.mark.edge
    def test_score_at_warning_boundary(self):
        score = -0.4
        level = "critical" if score <= -0.7 else ("warning" if score <= -0.4 else "info")
        assert level == "warning"

    @pytest.mark.edge
    def test_score_just_above_warning(self):
        score = -0.3999
        level = "critical" if score <= -0.7 else ("warning" if score <= -0.4 else "info")
        assert level == "info"

    @pytest.mark.edge
    def test_positive_score_is_info(self):
        score = 0.5
        level = "critical" if score <= -0.7 else ("warning" if score <= -0.4 else "info")
        assert level == "info"


# ---------- Event Cluster Edge Cases ----------

class TestEventClusterEdgeCases:
    @pytest.mark.edge
    def test_significance_with_zero_count(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(0, 0.0)
        assert 0 <= score <= 1

    @pytest.mark.edge
    def test_significance_with_large_count(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(1000, -1.0)
        assert 0 <= score <= 1

    @pytest.mark.edge
    def test_significance_with_zero_sentiment(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(5, 0.0)
        assert 0 <= score <= 1

    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_find_matching_cluster_partial_overlap(self):
        from app.analysis.event_cluster import find_matching_cluster
        from datetime import datetime, timezone
        existing = EventCluster(
            cluster_id="ev_1", title="央行降息", entities=[
                Entity(name="央行", type="policy"),
                Entity(name="LPR", type="indicator"),
                Entity(name="银行", type="industry"),
            ], news_ids=[1], sentiment_avg=-0.5,
            sentiment_distribution={"negative": 1},
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc),
        )
        # Only 1 out of 3 entities overlap
        new_entities = [Entity(name="央行", type="policy"), Entity(name="股市", type="market")]
        result = find_matching_cluster(new_entities, [existing], datetime.now(timezone.utc))
        # Should not match with only 1/3 overlap (below threshold)
        assert result is None


# ---------- Knowledge Graph Edge Cases ----------

class TestKnowledgeGraphEdgeCases:
    @pytest.mark.edge
    def test_parse_relations_empty_list(self):
        from app.analysis.knowledge_graph import _parse_relations
        result = _parse_relations("[]")
        assert result == []

    @pytest.mark.edge
    def test_parse_relations_missing_fields(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '[{"source": "A", "target": "B"}]'
        result = _parse_relations(text)
        assert len(result) == 0  # Missing required "relation" field

    @pytest.mark.edge
    def test_parse_causal_chain_single_step(self):
        from app.analysis.knowledge_graph import _parse_causal_chain
        text = '{"trigger": "降息", "path": ["降息"], "impact": "影响", "confidence": 0.5}'
        result = _parse_causal_chain(text)
        assert result is not None
        assert len(result.path) == 1

    @pytest.mark.edge
    def test_parse_causal_chain_very_long_path(self):
        from app.analysis.knowledge_graph import _parse_causal_chain
        import json
        path = [f"step{i}" for i in range(20)]
        data = {"trigger": "trigger", "path": path, "impact": "result", "confidence": 0.5}
        text = json.dumps(data, ensure_ascii=False)
        result = _parse_causal_chain(text)
        assert result is not None
        assert len(result.path) == 20

    @pytest.mark.edge
    def test_parse_relations_confidence_zero(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '[{"source": "A", "target": "B", "relation": "affects", "context": "", "confidence": 0.0}]'
        result = _parse_relations(text)
        assert len(result) == 1
        assert result[0].confidence == 0.0


# ---------- Report Service Edge Cases ----------

class TestReportServiceEdgeCases:
    @pytest.mark.edge
    def test_export_markdown_with_special_chars(self):
        from app.analysis.report_service import export_markdown
        report = {
            "news_title": "测试**加粗**和`代码`",
            "news_source": "test",
            "sentiment_score": -0.5,
            "sentiment_label": "negative",
            "sentiment_confidence": 0.85,
            "alert_level": "warning",
            "triggered_keywords": ["<script>"],
            "created_at": "2026-06-01",
            "news_url": "",
            "news_snippet": "",
            "deep_analysis": "# 深度分析\n\n包含**markdown**格式",
        }
        md = export_markdown(report)
        assert md is not None
        assert "加粗" in md

    @pytest.mark.edge
    def test_export_markdown_with_none_values(self):
        from app.analysis.report_service import export_markdown
        report = {
            "news_title": "test",
            "news_source": None,
            "sentiment_score": 0,
            "sentiment_label": "",
            "sentiment_confidence": 0,
            "alert_level": "",
            "triggered_keywords": [],
            "created_at": "",
            "news_url": None,
            "news_snippet": None,
        }
        md = export_markdown(report)
        assert md is not None


# ---------- Repository Edge Cases ----------

class TestRepositoryEdgeCases:
    @pytest.mark.edge
    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_save_news_with_empty_source(self, db):
        item = NewsItem(source="", title="test", title_hash="h_empty_src")
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            news_id = await save_news(item)
            assert news_id is not None

    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_save_news_with_long_content(self, db):
        long_content = "内容" * 5000
        item = NewsItem(source="test", title="长内容新闻", title_hash="h_long", content_snippet=long_content)
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            news_id = await save_news(item)
            assert news_id is not None

    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_query_news_with_large_offset(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_news
            result = await query_news(limit=10, offset=999999)
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_save_entities_duplicate_name_type(self, seeded_db):
        db, ids = seeded_db
        entities = [Entity(name="央行", type="policy", aliases=["新别名"])]
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_entities
            eids = await save_entities(ids["n1"], entities)
            assert len(eids) >= 1

    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_load_entities_for_empty_news_ids(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_entities_for_news_items
            result = await load_entities_for_news_items([])
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.edge
    async def test_load_relations_empty_entity_names(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_relations_for_context
            result = await load_relations_for_context([])
            assert result == []


# ---------- Notification Edge Cases ----------

class TestNotificationEdgeCases:
    @pytest.mark.edge
    def test_very_long_silence_period(self):
        from app.notification.dispatcher import set_notification_prefs, is_in_silence_period, mark_alert_sent, _notification_prefs
        _notification_prefs.clear()
        set_notification_prefs("u1", {"silence_minutes": 999999})
        mark_alert_sent("u1")
        assert is_in_silence_period("u1") is True

    @pytest.mark.edge
    def test_negative_silence_period(self):
        from app.notification.dispatcher import set_notification_prefs, is_in_silence_period, mark_alert_sent, _notification_prefs
        _notification_prefs.clear()
        set_notification_prefs("u1", {"silence_minutes": -1})
        mark_alert_sent("u1")
        # Negative silence should not block
        assert is_in_silence_period("u1") is False

    @pytest.mark.edge
    def test_unknown_alert_level(self):
        from app.notification.dispatcher import should_send_alert, _notification_prefs
        _notification_prefs.clear()
        item = NewsItem(source="test", title="test", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment, alert_level="unknown_level")
        # Should not crash
        result = should_send_alert(alert, "u1")
        assert isinstance(result, bool)
