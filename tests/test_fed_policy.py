"""Tests for Fed monetary policy tracker module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import NewsItem


class TestSearchFedNews:
    @pytest.mark.asyncio
    async def test_search_finds_fed_news(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.fed_policy import search_fed_news
            results = await search_fed_news(hours=168)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_returns_empty_for_no_match(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.fed_policy import search_fed_news
            results = await search_fed_news(hours=168)
            assert isinstance(results, list)
            assert len(results) == 0


class TestCrawlFedNews:
    @pytest.mark.asyncio
    async def test_crawl_filters_fed_keywords(self):
        mock_items = [
            NewsItem(source="cnbc", title="Fed signals rate cut in September", url="", content_snippet="test", title_hash="h1"),
            NewsItem(source="test", title="Apple releases new iPhone", url="", content_snippet="test", title_hash="h2"),
        ]
        with patch("app.crawler.sources.fetch_all_sources", return_value=mock_items):
            from app.analysis.fed_policy import crawl_fed_news
            results = await crawl_fed_news()
            assert len(results) >= 1
            assert any("Fed" in r["title"] for r in results)

    @pytest.mark.asyncio
    async def test_crawl_handles_failure(self):
        with patch("app.crawler.sources.fetch_all_sources", side_effect=Exception("Network error")):
            from app.analysis.fed_policy import crawl_fed_news
            results = await crawl_fed_news()
            assert results == []


class TestGeneratePolicySummary:
    @pytest.mark.asyncio
    async def test_generate_valid_summary(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"rate_trend":"cutting","policy_stance":"dovish","qt_qe_status":"QT ongoing","rate_level":"5.00%-5.25%","summary":"美联储进入降息周期","key_events":["FOMC signals rate cut"],"outlook":"预计下半年降息","sources":["CNBC"]}'
        news = [{"title": "Fed signals rate cut", "source": "CNBC", "content_snippet": "test"}]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            result = await generate_policy_summary(news)
            assert result is not None
            assert result["rate_trend"] == "cutting"
            assert result["policy_stance"] == "dovish"

    @pytest.mark.asyncio
    async def test_generate_handles_markdown_json(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '```json\n{"rate_trend":"hiking","policy_stance":"hawkish","qt_qe_status":"QE ongoing","rate_level":"","summary":"test","key_events":[],"outlook":"","sources":[]}\n```'
        news = [{"title": "Fed rate hike", "source": "test", "content_snippet": ""}]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            result = await generate_policy_summary(news)
            assert result is not None
            assert result["rate_trend"] == "hiking"

    @pytest.mark.asyncio
    async def test_generate_handles_malformed_response(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "不是JSON格式"
        news = [{"title": "Fed news", "source": "test", "content_snippet": ""}]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            result = await generate_policy_summary(news)
            assert result is not None
            assert result["rate_trend"] == "unclear"

    @pytest.mark.asyncio
    async def test_generate_empty_news_returns_none(self):
        from app.analysis.fed_policy import generate_policy_summary
        result = await generate_policy_summary([])
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_handles_timeout(self):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = TimeoutError()
        news = [{"title": "Fed news", "source": "test", "content_snippet": ""}]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            result = await generate_policy_summary(news)
            assert result is None


class TestGetFedPolicy:
    @pytest.mark.asyncio
    async def test_returns_cached_if_fresh(self, db):
        from app.repository import save_fed_policy_summary
        with patch("app.repository.get_db", return_value=db):
            await save_fed_policy_summary({
                "summary": "cached test",
                "rate_trend": "cutting",
                "policy_stance": "dovish",
                "qt_qe_status": "QT ongoing",
                "key_events": [],
                "news_count": 5,
            })

        with patch("app.analysis.fed_policy.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import get_fed_policy
            result = await get_fed_policy(refresh=False)
            assert result is not None
            assert result["summary"] == "cached test"

    @pytest.mark.asyncio
    async def test_returns_no_data_when_empty(self, db):
        with patch("app.analysis.fed_policy.search_fed_news", return_value=[]), \
             patch("app.analysis.fed_policy.crawl_fed_news", return_value=[]), \
             patch("app.repository.get_db", return_value=db):
            from app.analysis.fed_policy import get_fed_policy
            result = await get_fed_policy(refresh=True)
            assert result is not None
            assert result["rate_trend"] == "no data"
