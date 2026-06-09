"""Tests for report service module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import NewsItem, SentimentResult, AlertPayload


class TestExportMarkdown:
    @pytest.mark.integration
    def test_export_full_report(self):
        from app.analysis.report_service import export_markdown
        report = {
            "news_title": "央行宣布降息",
            "news_source": "新浪财经",
            "sentiment_score": -0.5,
            "sentiment_label": "negative",
            "sentiment_confidence": 0.85,
            "alert_level": "warning",
            "triggered_keywords": ["降息", "央行"],
            "created_at": "2026-06-01 10:00:00",
            "news_url": "https://example.com",
            "news_snippet": "人民银行宣布下调LPR利率",
            "deep_analysis": "央行降息对市场的影响分析...",
        }
        md = export_markdown(report)
        assert md is not None
        assert "# 央行宣布降息" in md
        assert "新浪财经" in md
        assert "-0.500" in md
        assert "降息" in md
        assert "深度研报" in md
        assert "人民银行" in md

    @pytest.mark.integration
    def test_export_empty_report(self):
        from app.analysis.report_service import export_markdown
        assert export_markdown(None) is None
        assert export_markdown({}) is None

    @pytest.mark.integration
    def test_export_report_with_url(self):
        from app.analysis.report_service import export_markdown
        report = {
            "news_title": "测试",
            "news_source": "test",
            "sentiment_score": 0.5,
            "sentiment_label": "positive",
            "sentiment_confidence": 0.9,
            "alert_level": "info",
            "triggered_keywords": [],
            "created_at": "2026-06-01",
            "news_url": "https://example.com/article",
            "news_snippet": "新闻摘要内容",
        }
        md = export_markdown(report)
        assert "https://example.com/article" in md
        assert "新闻摘要内容" in md


class TestFollowupQuestion:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_followup_no_report(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.report_service import followup_question
            result = await followup_question("nonexistent", "追问问题")
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_followup_with_report(self, seeded_db):
        db, ids = seeded_db
        # Save a report first
        alert = AlertPayload(
            news_item=NewsItem(source="test", title="央行降息"),
            sentiment=SentimentResult(news_item=NewsItem(source="test", title="x"), score=-0.5, label="negative"),
            deep_analysis="央行降息利好债券市场",
        )
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_report
            await save_report("r_followup_test", alert)

        mock_client = AsyncMock()
        mock_client.analyze.return_value = "降息对银行股的影响更大"

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.report_service.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.report_service import followup_question
            result = await followup_question("r_followup_test", "降息对银行股有什么影响")
            assert result is not None
            assert "银行股" in result


class TestMultiModelCompare:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_compare_no_report(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.report_service import multi_model_compare
            result = await multi_model_compare("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_compare_with_report(self, seeded_db):
        db, ids = seeded_db
        alert = AlertPayload(
            news_item=NewsItem(source="test", title="降息利好"),
            sentiment=SentimentResult(news_item=NewsItem(source="test", title="x"), score=0.5, label="positive"),
            deep_analysis="降息利好分析",
        )
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_report
            await save_report("r_compare_test", alert)

        mock_client = AsyncMock()
        mock_client.analyze.return_value = "相反视角：降息可能引发通胀风险"

        mock_settings = MagicMock()
        mock_settings.deepseek_api_key = "test-key"
        mock_settings.deepseek_model = "deepseek-chat"
        mock_settings.deepseek_temperature = 0.7
        mock_settings.deepseek_max_tokens = 2048

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.report_service.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = mock_settings
            from app.analysis.report_service import multi_model_compare
            result = await multi_model_compare("r_compare_test")
            assert result is not None
            assert "contrarian_view" in result