"""Tests for repository layer with in-memory database."""
import pytest
from unittest.mock import patch

from app.models import (
    NewsItem, SentimentResult, AlertPayload, Entity, MultiSentiment,
    EntityRelation,
)


class TestSaveAndLoadNews:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_news_returns_id(self, db):
        item = NewsItem(source="test", title="新闻标题", title_hash="hash_test")
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            news_id = await save_news(item)
            assert news_id is not None and news_id > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_news_dedup(self, db):
        item = NewsItem(source="test", title="重复新闻", title_hash="hash_dup")
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            id1 = await save_news(item)
            id2 = await save_news(item)
            assert id1 == id2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_news_by_id(self, seeded_db):
        db, ids = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_news_by_id
            result = await load_news_by_id(ids["n1"])
            assert result["title"] == "央行宣布降息25个基点"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_news_not_found(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_news_by_id
            assert await load_news_by_id(99999) is None


class TestSentimentPersistence:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_sentiment_returns_id(self, seeded_db):
        db, ids = seeded_db
        result = SentimentResult(news_item=NewsItem(source="t", title="x"), score=-0.5, label="negative", confidence=0.85)
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_sentiment
            assert await save_sentiment(ids["n1"], result) is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_sentiment_trend(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_sentiment_trend
            data = await query_sentiment_trend(hours=168)
            assert "trend" in data and "momentum_shifts" in data
            assert isinstance(data["trend"], list)
            # MA should be computed for each trend point
            if data["trend"]:
                assert "ma_score" in data["trend"][0]


class TestEntityPersistence:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_entities(self, seeded_db):
        db, ids = seeded_db
        entities = [Entity(name="工商银行", type="company", aliases=["ICBC"]), Entity(name="银行业", type="industry")]
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_entities
            eids = await save_entities(ids["n1"], entities)
            assert len(eids) == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_query_hot_entities(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_hot_entities
            results = await query_hot_entities(limit=10)
            assert len(results) >= 3 and results[0]["name"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_entities_for_news(self, seeded_db):
        db, ids = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_entities_for_news
            results = await load_entities_for_news(ids["n1"])
            assert len(results) >= 2


class TestMultiSentimentPersistence:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_multi_sentiment(self, seeded_db):
        db, ids = seeded_db
        ms = MultiSentiment(news_id=ids["n1"], entity_name="央行", fear=0.7, greed=0.1, optimism=0.2, uncertainty=0.6, dominant="fear", momentum=0.3, momentum_shift=True)
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_multi_sentiment
            await save_multi_sentiment(ms)
            rows = await db.execute_fetchall("SELECT * FROM multi_sentiment WHERE entity_name = '央行'")
            assert len(rows) >= 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_last_multi_sentiment(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_last_multi_sentiment
            result = await load_last_multi_sentiment("央行")
            assert result is not None and "fear" in result


class TestReportPersistence:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_and_load_report(self, db):
        alert = AlertPayload(
            news_item=NewsItem(source="test", title="测试新闻"),
            sentiment=SentimentResult(news_item=NewsItem(source="test", title="x"), score=0.5, label="positive"),
            alert_level="info", triggered_keywords=["关键词"], deep_analysis="测试研报",
        )
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_report, load_report
            await save_report("r_test123", alert)
            result = await load_report("r_test123")
            assert result["deep_analysis"] == "测试研报" and result["alert_level"] == "info"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_report_with_references(self, db):
        alert = AlertPayload(
            news_item=NewsItem(source="test", title="测试"),
            sentiment=SentimentResult(news_item=NewsItem(source="test", title="x"), score=0.3, label="neutral"),
        )
        refs = [{"title": "参考1", "source": "s1", "url": "http://example.com"}]
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_report, load_report
            await save_report("r_ref", alert, referenced_news=refs)
            result = await load_report("r_ref")
            assert len(result["referenced_news"]) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_report_not_found(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_report
            assert await load_report("nonexistent") is None


class TestRelationPersistence:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_and_load_relations(self, db):
        relations = [EntityRelation(source="央行", target="LPR", relation="affects", confidence=0.8)]
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_relations, load_relations_for_context
            await save_relations(relations, news_id=1)
            results = await load_relations_for_context(["央行"])
            assert len(results) >= 1


class TestSubscriptionPersistence:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_save_and_load_subscriptions(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_subscription, load_subscriptions
            await save_subscription("u1", ["降息", "利率"], -0.5)
            result = await load_subscriptions()
            assert "u1" in result and "降息" in result["u1"]["keywords"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_subscription(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_subscription, delete_subscription, load_subscriptions
            await save_subscription("u1", ["降息"], -0.5)
            await delete_subscription("u1")
            assert "u1" not in await load_subscriptions()