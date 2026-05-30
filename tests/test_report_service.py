"""Tests for the report service module."""
import pytest
from unittest.mock import AsyncMock, patch

from app import deps
from app.models import AlertPayload, NewsItem, SentimentResult
from config.settings import Settings


def _make_alert(title: str = "测试新闻", deep_analysis: str | None = "深度研报内容") -> AlertPayload:
    item = NewsItem(source="test", title=title, title_hash="test_hash")
    sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
    return AlertPayload(
        news_item=item, sentiment=sentiment,
        alert_level="critical", triggered_keywords=["降息"],
        deep_analysis=deep_analysis,
    )


@pytest.fixture
def mock_db():
    """Provide an in-memory SQLite DB for report tests."""
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


class TestStoreAndGetReport:
    @pytest.mark.asyncio
    async def test_store_report_returns_id(self, mock_db):
        init, get_db, close = mock_db
        db = await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report
            alert = _make_alert()
            report_id = await store_report(alert)
            assert report_id.startswith("r_")
        await close()

    @pytest.mark.asyncio
    async def test_get_report_exists(self, mock_db):
        init, get_db, close = mock_db
        db = await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report, get_report
            alert = _make_alert()
            report_id = await store_report(alert)
            result = await get_report(report_id)
            assert result is not None
            assert result["alert_level"] == "critical"
            assert result["news_title"] == "测试新闻"
            assert "降息" in result["triggered_keywords"]
        await close()

    @pytest.mark.asyncio
    async def test_get_report_not_exists(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import get_report
            result = await get_report("nonexistent_id")
            assert result is None
        await close()


class TestExportMarkdown:
    @pytest.mark.asyncio
    async def test_export_markdown_exists(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report, get_report, export_markdown
            alert = _make_alert()
            report_id = await store_report(alert)
            report = await get_report(report_id)
            md = export_markdown(report)
            assert md is not None
            assert "测试新闻" in md
            assert "深度研报内容" in md
            assert "降息" in md
        await close()

    @pytest.mark.asyncio
    async def test_export_markdown_not_exists(self):
        from app.analysis.report_service import export_markdown
        md = export_markdown(None)
        assert md is None

    @pytest.mark.asyncio
    async def test_export_markdown_no_deep_analysis(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report, get_report, export_markdown
            alert = _make_alert(deep_analysis=None)
            report_id = await store_report(alert)
            report = await get_report(report_id)
            md = export_markdown(report)
            assert md is not None
            assert "深度研报" not in md
        await close()

    @pytest.mark.asyncio
    async def test_export_markdown_with_url(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report, get_report, export_markdown
            alert = _make_alert()
            alert.news_item.url = "https://example.com/news"
            report_id = await store_report(alert)
            report = await get_report(report_id)
            md = export_markdown(report)
            assert "https://example.com/news" in md
        await close()

    @pytest.mark.asyncio
    async def test_export_markdown_with_snippet(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report, get_report, export_markdown
            alert = _make_alert()
            alert.news_item.content_snippet = "这是一段新闻摘要"
            report_id = await store_report(alert)
            report = await get_report(report_id)
            md = export_markdown(report)
            assert "新闻摘要" in md
            assert "这是一段新闻摘要" in md
        await close()


class TestFollowupQuestion:
    @pytest.mark.asyncio
    async def test_followup_no_report(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import followup_question
            result = await followup_question("nonexistent", "问题")
            assert result is None
        await close()

    @pytest.mark.asyncio
    async def test_followup_no_deep_analysis(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report, followup_question
            alert = _make_alert(deep_analysis=None)
            report_id = await store_report(alert)
            result = await followup_question(report_id, "问题")
            assert result is None
        await close()


class TestQueryReports:
    @pytest.mark.asyncio
    async def test_query_reports_empty(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.repository import query_reports
            results = await query_reports()
            assert results == []
        await close()

    @pytest.mark.asyncio
    async def test_query_reports_with_data(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report
            from app.repository import query_reports
            alert = _make_alert()
            await store_report(alert)
            results = await query_reports()
            assert len(results) == 1
            assert results[0]["alert_level"] == "critical"
        await close()

    @pytest.mark.asyncio
    async def test_query_reports_filter_level(self, mock_db):
        init, get_db, close = mock_db
        await init()
        with patch("app.repository.get_db", get_db):
            from app.analysis.report_service import store_report
            from app.repository import query_reports
            alert_critical = _make_alert(title="严重新闻")
            alert_critical.alert_level = "critical"
            alert_warning = _make_alert(title="警告新闻")
            alert_warning.alert_level = "warning"
            await store_report(alert_critical)
            await store_report(alert_warning)
            results = await query_reports(level="warning")
            assert len(results) == 1
            assert results[0]["alert_level"] == "warning"
        await close()
