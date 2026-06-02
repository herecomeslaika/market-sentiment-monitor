"""Tests for the intent-driven report generation module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import NewsItem
from config.settings import Settings


@pytest.fixture
def mock_db():
    import aiosqlite
    from app.db import SCHEMA

    db = None

    async def _init():
        nonlocal db
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA)
        await db.commit()
        return db

    async def _get():
        return db

    async def _close():
        nonlocal db
        if db:
            await db.close()
            db = None

    return _init, _get, _close


class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_fallback_on_api_failure(self):
        mock_client = MagicMock()
        mock_client.analyze = AsyncMock(side_effect=Exception("API error"))
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息对银行股的影响")
            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_fallback_splits_intent(self):
        mock_client = MagicMock()
        mock_client.analyze = AsyncMock(side_effect=RuntimeError("fail"))
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息 银行股 LPR")
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_parses_json_response(self):
        mock_client = MagicMock()
        mock_client.analyze = AsyncMock(return_value='["降息", "银行股", "LPR"]')
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息对银行股的影响")
            assert "降息" in result
            assert "银行股" in result


class TestSearchRecentNews:
    @pytest.mark.asyncio
    async def test_returns_matching_news(self, mock_db):
        init, get_db, close = mock_db
        db = await init()
        await db.execute(
            "INSERT INTO news (source, title, title_hash) VALUES (?, ?, ?)",
            ("test", "央行宣布降息", "hash1"),
        )
        await db.execute(
            "INSERT INTO news (source, title, title_hash) VALUES (?, ?, ?)",
            ("test", "股市大涨", "hash2"),
        )
        await db.commit()

        with patch("app.repository.get_db", get_db):
            from app.analysis.intent_report import search_recent_news
            results = await search_recent_news(["降息"], hours=48)
            assert len(results) >= 1
            assert "降息" in results[0]["title"]
        await close()

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.intent_report import search_recent_news
            results = await search_recent_news(["不存在的关键词"], hours=24)
            assert results == []
        await close()


class TestCrawlFreshNews:
    @pytest.mark.asyncio
    async def test_filters_by_keywords(self):
        mock_items = [
            NewsItem(source="test", title="央行降息利好银行", title_hash="h1"),
            NewsItem(source="test", title="科技股大涨", title_hash="h2"),
        ]
        with patch("app.crawler.sources.fetch_all_sources", new_callable=AsyncMock, return_value=mock_items):
            from app.analysis.intent_report import crawl_fresh_news
            results = await crawl_fresh_news(["降息"])
            assert len(results) == 1
            assert "降息" in results[0]["title"]


class TestRun:
    @pytest.mark.asyncio
    async def test_no_news_returns_error(self, mock_db):
        init, get_db, close = mock_db
        await init()
        mock_kw = AsyncMock(return_value=["不存在的关键词"])
        mock_crawl = AsyncMock(return_value=[])
        with patch("app.repository.get_db", get_db), \
             patch("app.analysis.intent_report.extract_keywords", mock_kw), \
             patch("app.analysis.intent_report.crawl_fresh_news", mock_crawl):
            from app.analysis.intent_report import run
            result = await run("不存在的主题")
            assert result is not None
            assert "error" in result
        await close()