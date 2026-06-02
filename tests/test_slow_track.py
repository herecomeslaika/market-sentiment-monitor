"""Tests for the slow track consumer logic."""
import asyncio
from collections import OrderedDict

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app import deps
from app.models import AlertPayload, NewsItem, SentimentResult, Subscription
from config.settings import Settings


@pytest.fixture(autouse=True)
def setup_deps():
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.news_queue = asyncio.Queue(maxsize=100)
    deps.scored_queue = asyncio.Queue(maxsize=100)
    deps.alert_queue = asyncio.Queue(maxsize=50)
    deps.dedup_cache = OrderedDict()
    deps.active_connections = {}
    deps.active_subscriptions = {}
    yield
    deps.active_subscriptions.clear()
    deps.dedup_cache.clear()


def _make_sentiment(title: str = "美联储降息", score: float = -0.8) -> SentimentResult:
    item = NewsItem(source="test", title=title, title_hash="hash_x")
    return SentimentResult(news_item=item, score=score, label="negative", confidence=0.9)


class TestSlowTrackAlertLevel:
    """Test alert level assignment logic (extracted from slow_track_consumer)."""

    def test_critical_level(self):
        score = -0.8
        if score <= -0.7:
            level = "critical"
        elif score <= -0.4:
            level = "warning"
        else:
            level = "info"
        assert level == "critical"

    def test_warning_level(self):
        score = -0.5
        if score <= -0.7:
            level = "critical"
        elif score <= -0.4:
            level = "warning"
        else:
            level = "info"
        assert level == "warning"

    def test_info_level(self):
        score = -0.2
        if score <= -0.7:
            level = "critical"
        elif score <= -0.4:
            level = "warning"
        else:
            level = "info"
        assert level == "info"


class TestDeepAnalysisTrigger:
    def test_trigger_with_keywords_and_threshold(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.5,
        )
        assert should_trigger_deep_analysis(-0.8, ["美联储"]) is True

    def test_no_trigger_without_keywords(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.5,
        )
        assert should_trigger_deep_analysis(-0.8, []) is False

    def test_no_trigger_without_subscriptions(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        assert should_trigger_deep_analysis(-0.8, ["美联储"]) is False

    def test_no_trigger_score_above_threshold(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.9,
        )
        assert should_trigger_deep_analysis(-0.5, ["美联储"]) is False


class TestRunDeepAnalysis:
    @pytest.mark.asyncio
    async def test_run_deep_analysis_timeout(self):
        from app.analysis.slow_track import run_deep_analysis_from_state
        state = {
            "news_title": "美联储降息",
            "news_snippet": "",
            "sentiment_score": -0.8,
            "sentiment_label": "negative",
            "keywords_matched": ["美联储"],
            "context_summary": "",
            "risk_assessment": "",
            "final_report": "",
            "error": None,
        }

        with patch("app.analysis.langgraph_flow.get_compiled_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke.side_effect = asyncio.TimeoutError()
            mock_graph.return_value = mock_compiled

            result = await run_deep_analysis_from_state(state, retries=0)
            assert result is None

    @pytest.mark.asyncio
    async def test_run_deep_analysis_exception(self):
        from app.analysis.slow_track import run_deep_analysis_from_state
        state = {
            "news_title": "美联储降息",
            "news_snippet": "",
            "sentiment_score": -0.8,
            "sentiment_label": "negative",
            "keywords_matched": ["美联储"],
            "context_summary": "",
            "risk_assessment": "",
            "final_report": "",
            "error": None,
        }

        with patch("app.analysis.langgraph_flow.get_compiled_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke.side_effect = RuntimeError("API error")
            mock_graph.return_value = mock_compiled

            result = await run_deep_analysis_from_state(state, retries=0)
            assert result is None

    @pytest.mark.asyncio
    async def test_run_deep_analysis_success(self):
        from app.analysis.slow_track import run_deep_analysis_from_state
        state = {
            "news_title": "美联储降息",
            "news_snippet": "",
            "sentiment_score": -0.8,
            "sentiment_label": "negative",
            "keywords_matched": ["美联储"],
            "context_summary": "",
            "risk_assessment": "",
            "final_report": "",
            "error": None,
        }

        with patch("app.analysis.langgraph_flow.get_compiled_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke.return_value = {
                "final_report": "这是一份研报",
                "error": None,
            }
            mock_graph.return_value = mock_compiled

            result = await run_deep_analysis_from_state(state, retries=0)
            assert result == "这是一份研报"

    @pytest.mark.asyncio
    async def test_run_deep_analysis_partial_report(self):
        from app.analysis.slow_track import run_deep_analysis_from_state
        state = {
            "news_title": "美联储降息",
            "news_snippet": "",
            "sentiment_score": -0.8,
            "sentiment_label": "negative",
            "keywords_matched": ["美联储"],
            "context_summary": "",
            "risk_assessment": "",
            "final_report": "",
            "error": None,
        }

        with patch("app.analysis.langgraph_flow.get_compiled_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke.return_value = {
                "final_report": "部分研报",
                "error": "gather_context failed",
            }
            mock_graph.return_value = mock_compiled

            result = await run_deep_analysis_from_state(state, retries=0)
            assert result == "部分研报"
