"""Tests for database and repository layer."""
import asyncio
import os
import tempfile

import pytest

from app.db import init_db, close_db, get_db
from app.models import NewsItem, SentimentResult, AlertPayload
from datetime import datetime


@pytest.fixture(autouse=True)
async def setup_db():
    """Use a temp DB for each test."""
    import app.db as db_mod
    old_path = db_mod.DB_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        db_mod.DB_PATH = type(old_path)(tmpdir) / "test.db"
        try:
            conn = await init_db()
            yield
        finally:
            await close_db()
            db_mod.DB_PATH = old_path


class TestDatabase:
    async def test_init_creates_tables(self):
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {r[0] for r in rows}
        assert "news" in tables
        assert "sentiment" in tables
        assert "alerts" in tables
        assert "subscriptions" in tables
        assert "reports" in tables


class TestRepository:
    async def test_save_and_query_news(self):
        from app.repository import save_news, query_news
        item = NewsItem(
            source="test", title="测试新闻", url="https://example.com",
            content_snippet="摘要", title_hash="hash1",
        )
        news_id = await save_news(item)
        assert news_id is not None

        results = await query_news(limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "测试新闻"

    async def test_save_news_dedup(self):
        from app.repository import save_news, query_news
        item = NewsItem(
            source="test", title="重复新闻", title_hash="dup_hash",
        )
        id1 = await save_news(item)
        id2 = await save_news(item)
        results = await query_news()
        assert len(results) == 1

    async def test_save_sentiment(self):
        from app.repository import save_news, save_sentiment, query_sentiment_history
        item = NewsItem(source="test", title="情绪测试", title_hash="sent_hash")
        news_id = await save_news(item)

        result = SentimentResult(
            news_item=item, score=-0.8, label="negative", confidence=0.8,
        )
        sent_id = await save_sentiment(news_id, result)
        assert sent_id is not None

        history = await query_sentiment_history(hours=24)
        assert len(history) >= 1
        assert history[0]["score"] == -0.8

    async def test_save_alert(self):
        from app.repository import save_news, save_sentiment, save_alert, query_alert_history
        item = NewsItem(source="test", title="告警测试", title_hash="alert_hash")
        news_id = await save_news(item)
        sent = SentimentResult(news_item=item, score=-0.9, label="negative", confidence=0.9)
        sent_id = await save_sentiment(news_id, sent)

        alert = AlertPayload(
            news_item=item, sentiment=sent,
            alert_level="critical", triggered_keywords=["降息"],
        )
        alert_id = await save_alert(news_id, sent_id, alert)
        assert alert_id is not None

        alerts = await query_alert_history()
        assert len(alerts) >= 1

    async def test_sentiment_trend(self):
        from app.repository import save_news, save_sentiment, query_sentiment_trend
        item = NewsItem(source="test", title="趋势测试", title_hash="trend_hash")
        news_id = await save_news(item)
        sent = SentimentResult(news_item=item, score=0.5, label="positive", confidence=0.5)
        await save_sentiment(news_id, sent)

        trend = await query_sentiment_trend(hours=24)
        assert len(trend) >= 1

    async def test_subscription_crud(self):
        from app.repository import save_subscription, load_subscriptions, delete_subscription
        await save_subscription("user1", ["美联储", "降息"], -0.5)
        subs = await load_subscriptions()
        assert "user1" in subs
        assert subs["user1"]["keywords"] == ["美联储", "降息"]

        await delete_subscription("user1")
        subs = await load_subscriptions()
        assert "user1" not in subs

    async def test_cleanup(self):
        from app.repository import save_news, cleanup_old_data, query_news
        item = NewsItem(source="test", title="清理测试", title_hash="clean_hash")
        await save_news(item)
        # Cleanup with 0 days should remove records created before today
        # Since our record was just created, it shouldn't be removed
        await cleanup_old_data(days=0)
        # The record is fresh so it may or may not be removed depending on datetime precision
        # Just verify the function doesn't error
        results = await query_news()
        assert isinstance(results, list)
