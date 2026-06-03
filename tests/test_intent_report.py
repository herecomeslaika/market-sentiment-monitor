"""Tests for intent-based report generation module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import NewsItem


class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_extract_bilingual_keywords(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '["降息","银行","LPR","rate cut","interest rate","bank","Fed"]'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.intent_report.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息对银行的影响")
            assert len(result) >= 3
            assert any(k.isascii() for k in result)  # Has English keywords
            assert any(not k.isascii() for k in result)  # Has Chinese keywords

    @pytest.mark.asyncio
    async def test_extract_fallback_on_failure(self):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = Exception("API error")
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.intent_report.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息对银行的影响")
            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_extract_handles_markdown_json(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '```json\n["降息","银行","rate cut"]\n```'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.intent_report.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息影响")
            assert len(result) >= 2


class TestSearchRecentNews:
    @pytest.mark.asyncio
    async def test_search_finds_matching_news(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.intent_report import search_recent_news
            results = await search_recent_news(["降息"], hours=168)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_empty_keywords(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.intent_report import search_recent_news
            results = await search_recent_news([], hours=168)
            assert isinstance(results, list)


class TestCrawlFreshNews:
    @pytest.mark.asyncio
    async def test_crawl_filters_by_keyword(self):
        mock_items = [
            NewsItem(source="test", title="Fed rate cut signals", url="", content_snippet="test", title_hash="h1"),
            NewsItem(source="test", title="Apple releases new iPhone", url="", content_snippet="test", title_hash="h2"),
        ]
        with patch("app.crawler.sources.fetch_all_sources", return_value=mock_items):
            from app.analysis.intent_report import crawl_fresh_news
            results = await crawl_fresh_news(["rate cut", "fed"])
            assert len(results) >= 1
            assert any("rate cut" in r["title"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_crawl_case_insensitive(self):
        mock_items = [
            NewsItem(source="test", title="FED RATE CUT SIGNALS", url="", content_snippet="test", title_hash="h1"),
        ]
        with patch("app.crawler.sources.fetch_all_sources", return_value=mock_items):
            from app.analysis.intent_report import crawl_fresh_news
            results = await crawl_fresh_news(["fed", "rate cut"])
            assert len(results) >= 1