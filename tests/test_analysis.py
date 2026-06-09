"""Tests for the LangGraph analysis flow and slow track."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app import deps
from app.models import AlertPayload, NewsItem, SentimentResult, Subscription
from config.settings import Settings


@pytest.fixture(autouse=True)
def setup_deps():
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.active_subscriptions = {}
    deps.news_queue = None
    deps.scored_queue = None
    deps.alert_queue = None
    deps.dedup_cache = {}
    deps.active_connections = {}
    yield
    deps.active_subscriptions.clear()


class TestShouldTriggerDeepAnalysis:
    @pytest.mark.unit
    def test_no_keywords_no_trigger(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.5,
        )
        assert should_trigger_deep_analysis(-0.8, []) is False

    @pytest.mark.unit
    def test_keywords_match_and_threshold_crossed(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.5,
        )
        assert should_trigger_deep_analysis(-0.8, ["美联储"]) is True

    @pytest.mark.unit
    def test_keywords_match_but_threshold_not_crossed(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["美联储"], threshold=-0.9,
        )
        assert should_trigger_deep_analysis(-0.5, ["美联储"]) is False

    @pytest.mark.unit
    def test_no_subscriptions(self):
        from app.analysis.slow_track import should_trigger_deep_analysis
        assert should_trigger_deep_analysis(-0.8, ["美联储"]) is False


class TestAnalysisState:
    @pytest.mark.unit
    def test_analysis_state_typed_dict(self):
        from app.analysis.langgraph_flow import AnalysisState
        state: AnalysisState = {
            "news_title": "测试",
            "news_snippet": "内容",
            "sentiment_score": -0.5,
            "sentiment_label": "negative",
            "keywords_matched": ["降息"],
            "web_context": "",
            "context_summary": "",
            "risk_assessment": "",
            "final_report": "",
            "error": None,
        }
        assert state["news_title"] == "测试"
        assert state["error"] is None


class TestBuildGraph:
    @pytest.mark.unit
    def test_build_graph_creates_valid_graph(self):
        from app.analysis.langgraph_flow import build_graph
        graph = build_graph()
        assert graph is not None

    @pytest.mark.unit
    def test_get_compiled_graph(self):
        from app.analysis.langgraph_flow import get_compiled_graph, _compiled_graph
        # Reset cached graph
        import app.analysis.langgraph_flow as flow_mod
        flow_mod._compiled_graph = None
        compiled = get_compiled_graph()
        assert compiled is not None

    @pytest.mark.unit
    def test_should_continue_no_error(self):
        from app.analysis.langgraph_flow import _should_continue
        assert _should_continue({"error": None}) == "next"

    @pytest.mark.unit
    def test_should_continue_with_error(self):
        from app.analysis.langgraph_flow import _should_continue
        assert _should_continue({"error": "something failed"}) == "compose_report"


class TestSearchWebContext:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_search_web_context_handles_failure(self):
        from app.analysis.langgraph_flow import search_web_context
        state = {"news_title": "测试新闻", "keywords_matched": ["关键词"]}
        result = await search_web_context(state)
        # Should return web_context key, may be empty due to network issues
        assert "web_context" in result

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_search_web_context_uses_title(self):
        from app.analysis.langgraph_flow import search_web_context
        state = {"news_title": "美联储降息", "keywords_matched": []}
        result = await search_web_context(state)
        assert "web_context" in result

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_search_web_context_uses_keywords_fallback(self):
        from app.analysis.langgraph_flow import search_web_context
        state = {"news_title": "", "keywords_matched": ["降息", "美联储", "利率"]}
        result = await search_web_context(state)
        assert "web_context" in result


class TestGatherContext:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_gather_context_handles_api_failure(self):
        from app.analysis.langgraph_flow import gather_context
        import app.analysis.langgraph_flow as flow_mod

        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("API unavailable")
        flow_mod._cached_client = mock_client

        try:
            state = {
                "news_title": "测试新闻",
                "news_snippet": "内容",
                "sentiment_score": -0.5,
                "sentiment_label": "negative",
                "keywords_matched": ["降息"],
                "web_context": "",
            }
            result = await gather_context(state)
            assert "context_summary" in result
            assert "error" in result
        finally:
            flow_mod._cached_client = None


class TestAssessRisk:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_assess_risk_skips_on_error(self):
        from app.analysis.langgraph_flow import assess_risk
        state = {"error": "previous failure", "context_summary": "", "sentiment_score": -0.5}
        result = await assess_risk(state)
        assert result == {}

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_assess_risk_handles_api_failure(self):
        from app.analysis.langgraph_flow import assess_risk
        import app.analysis.langgraph_flow as flow_mod

        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("API unavailable")
        flow_mod._cached_client = mock_client

        try:
            state = {
                "context_summary": "背景",
                "sentiment_score": -0.5,
                "error": None,
            }
            result = await assess_risk(state)
            assert "risk_assessment" in result
            assert "error" in result
        finally:
            flow_mod._cached_client = None


class TestComposeReport:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_compose_report_with_error_state(self):
        from app.analysis.langgraph_flow import compose_report
        import app.analysis.langgraph_flow as flow_mod

        mock_client = AsyncMock()
        mock_client.analyze.return_value = "部分研报内容"
        flow_mod._cached_client = mock_client

        try:
            state = {
                "news_title": "测试",
                "sentiment_score": -0.5,
                "sentiment_label": "negative",
                "context_summary": "背景",
                "risk_assessment": "风险",
                "error": "partial failure",
            }
            result = await compose_report(state)
            assert "final_report" in result
        finally:
            flow_mod._cached_client = None


class TestRetryAnalyze:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_retry_analyze_succeeds_first_try(self):
        from app.analysis.langgraph_flow import _retry_analyze
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "成功分析"

        result = await _retry_analyze(mock_client, "system", "user", timeout=5, retries=1)
        assert result == "成功分析"
        assert mock_client.analyze.call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_retry_analyze_retries_on_failure(self):
        from app.analysis.langgraph_flow import _retry_analyze, MAX_RETRIES
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = [RuntimeError("fail"), RuntimeError("fail"), "成功"]

        result = await _retry_analyze(mock_client, "system", "user", timeout=5, retries=2)
        assert result == "成功"
        assert mock_client.analyze.call_count == 3

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_retry_analyze_exhausted(self):
        from app.analysis.langgraph_flow import _retry_analyze
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="failed after"):
            await _retry_analyze(mock_client, "system", "user", timeout=5, retries=1)
        assert mock_client.analyze.call_count == 2
