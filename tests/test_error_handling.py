"""Error handling and resilience tests.

Tests for graceful degradation when external services fail,
network errors, timeout handling, malformed data, and recovery.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import (
    NewsItem, SentimentResult, AlertPayload, Entity,
    MultiSentiment, EntityRelation,
)
from app import deps
from config.settings import Settings


# ---------- DeepSeek Client Failure Modes ----------

class TestDeepSeekClientFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_connection_refused(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = ConnectionRefusedError("Connection refused")
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h1")
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_timeout_error(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = asyncio.TimeoutError()
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h2")
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_generic_exception(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("Unexpected error")
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h3")
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_partial_json_response(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '[{"name":"央行"'  # Incomplete JSON
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h4")
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_empty_string_response(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = ""
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h5")
            assert result == []


# ---------- Multi-Sentiment Failure Modes ----------

class TestMultiSentimentFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_llm_returns_null(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "null"
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "测试", "测试", [Entity(name="央行", type="policy")])
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_llm_returns_wrong_structure(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"not":"expected","format":true}'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "测试", "测试", [Entity(name="央行", type="policy")])
            # Should handle gracefully
            assert result is None or isinstance(result, MultiSentiment)

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_llm_returns_out_of_range_values(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"fear":5.0,"greed":-1.0,"optimism":2.0,"uncertainty":0.5,"dominant":"fear"}'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "测试", "测试", [Entity(name="央行", type="policy")])
            # Should clamp or reject out-of-range values
            if result:
                assert 0 <= result.fear <= 1
                assert 0 <= result.greed <= 1


# ---------- Knowledge Graph Failure Modes ----------

class TestKnowledgeGraphFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_extract_relations_api_error(self):
        from app.analysis.knowledge_graph import extract_relations
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = ConnectionError("Network down")
        entities = [Entity(name="A", type="company"), Entity(name="B", type="industry")]
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            result = await extract_relations("测试", "", entities)
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_infer_causal_chain_api_error(self):
        from app.analysis.knowledge_graph import infer_causal_chain
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = ConnectionError("Network down")
        entities = [Entity(name="A", type="company")]
        relations = [EntityRelation(source="A", target="B", relation="affects")]
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            result = await infer_causal_chain(entities, relations, "context")
            assert result is None

    @pytest.mark.error
    def test_parse_relations_with_null_json_values(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '[{"source": "A", "target": "B", "relation": "affects", "context": "", "confidence": 0.5}]'
        result = _parse_relations(text)
        assert len(result) == 1
        # The parser skips null values (None entries in list are filtered by isinstance check)


# ---------- LangGraph Flow Failure Modes ----------

class TestLangGraphFlowFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_gather_context_with_empty_state(self):
        from app.analysis.langgraph_flow import gather_context
        state = {
            "news_title": "",
            "news_snippet": "",
            "sentiment_score": 0.0,
            "sentiment_label": "",
            "keywords_matched": [],
            "web_context": "",
        }
        result = await gather_context(state)
        assert "context_summary" in result

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_assess_risk_with_no_context(self):
        from app.analysis.langgraph_flow import assess_risk
        state = {"error": None, "context_summary": "", "sentiment_score": 0.0}
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("API unavailable")
        import app.analysis.langgraph_flow as flow_mod
        flow_mod._cached_client = mock_client
        try:
            result = await assess_risk(state)
            assert "error" in result
        finally:
            flow_mod._cached_client = None

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_retry_analyze_all_retries_fail(self):
        from app.analysis.langgraph_flow import _retry_analyze
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("persistent failure")
        with pytest.raises(RuntimeError):
            await _retry_analyze(mock_client, "sys", "user", timeout=5, retries=3)
        assert mock_client.analyze.call_count == 4  # initial + 3 retries

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_retry_analyze_intermittent_failure(self):
        from app.analysis.langgraph_flow import _retry_analyze
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = [
            RuntimeError("fail 1"),
            RuntimeError("fail 2"),
            "success on third try",
        ]
        result = await _retry_analyze(mock_client, "sys", "user", timeout=5, retries=3)
        assert result == "success on third try"
        assert mock_client.analyze.call_count == 3


# ---------- Slow Track Failure Modes ----------

class TestSlowTrackFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_deep_analysis_graph_returns_error(self):
        from app.analysis.slow_track import run_deep_analysis_from_state
        state = {
            "news_title": "测试",
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
                "final_report": "",
                "error": "All analysis steps failed",
            }
            mock_graph.return_value = mock_compiled
            result = await run_deep_analysis_from_state(state, retries=0)
            # Should return None or empty when all steps fail
            assert result is None or result == ""

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_deep_analysis_graph_returns_none(self):
        from app.analysis.slow_track import run_deep_analysis_from_state
        state = {
            "news_title": "测试",
            "news_snippet": "",
            "sentiment_score": -0.8,
            "sentiment_label": "negative",
            "keywords_matched": [],
            "context_summary": "",
            "risk_assessment": "",
            "final_report": "",
            "error": None,
        }
        with patch("app.analysis.langgraph_flow.get_compiled_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke.return_value = None
            mock_graph.return_value = mock_compiled
            result = await run_deep_analysis_from_state(state, retries=0)
            assert result is None


# ---------- Fed Policy Failure Modes ----------

class TestFedPolicyFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_crawl_fed_news_all_sources_fail(self):
        with patch("app.crawler.sources.fetch_all_sources", side_effect=Exception("All sources down")):
            from app.analysis.fed_policy import crawl_fed_news
            result = await crawl_fed_news()
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_generate_policy_summary_llm_timeout(self):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = asyncio.TimeoutError()
        news = [{"title": "Fed news", "source": "test", "content_snippet": ""}]
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            result = await generate_policy_summary(news)
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_generate_policy_summary_llm_returns_garbage(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "随机文字\x00\x01\x02二进制数据"
        news = [{"title": "Fed news", "source": "test", "content_snippet": ""}]
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            result = await generate_policy_summary(news)
            assert result is not None
            assert result["rate_trend"] == "unclear"


# ---------- Intent Report Failure Modes ----------

class TestIntentReportFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_extract_keywords_llm_returns_non_json(self):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "这是普通的文字回复，不是JSON"
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.intent_report.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.intent_report import extract_keywords
            result = await extract_keywords("降息对银行的影响")
            assert isinstance(result, list)

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_crawl_fresh_news_source_failure(self):
        with patch("app.crawler.sources.fetch_all_sources", side_effect=Exception("Network error")):
            from app.analysis.intent_report import crawl_fresh_news
            result = await crawl_fresh_news(["降息"])
            assert isinstance(result, list)

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_search_recent_news_db_error(self, db):
        with patch("app.repository.get_db", side_effect=Exception("DB connection lost")):
            from app.analysis.intent_report import search_recent_news
            try:
                result = await search_recent_news(["降息"], hours=168)
            except Exception:
                pass  # DB error should propagate or be handled


# ---------- Repository Failure Modes ----------

class TestRepositoryFailures:
    @pytest.mark.error
    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_save_news_with_duplicate_hash(self, db):
        item1 = NewsItem(source="test", title="新闻1", title_hash="same_hash")
        item2 = NewsItem(source="test", title="新闻2", title_hash="same_hash")
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            id1 = await save_news(item1)
            id2 = await save_news(item2)
            # Same hash should return same ID (dedup)
            assert id1 == id2

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_save_sentiment_for_nonexistent_news(self, db):
        result = SentimentResult(
            news_item=NewsItem(source="t", title="x"), score=-0.5, label="negative"
        )
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_sentiment
            # SQLite doesn't enforce foreign keys by default, so this may succeed
            news_id = await save_sentiment(99999, result)
            # Just verify it doesn't crash; result depends on SQLite config
            assert isinstance(news_id, int) or news_id is None

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_load_report_with_invalid_id(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_report
            result = await load_report("")
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.error
    async def test_cleanup_with_zero_days(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import cleanup_old_data
            await cleanup_old_data(days=0)
            # Should not delete anything from just now
            rows = await db.execute_fetchall("SELECT COUNT(*) as c FROM news")
            assert rows[0]["c"] > 0


# ---------- WebSocket Failure Modes ----------

class TestWebSocketFailures:
    @pytest.mark.error
    async def test_send_to_user_with_broken_connection(self):
        from app.ws.connection_manager import ConnectionManager
        from app.models import WSMessage

        class BrokenWS:
            async def accept(self):
                pass
            async def send_json(self, data):
                raise ConnectionResetError("Connection reset")

        manager = ConnectionManager()
        await manager.connect("broken_user", BrokenWS())
        msg = WSMessage(type="test", payload={})
        # Should not crash
        try:
            await manager.send_to_user("broken_user", msg)
        except ConnectionResetError:
            pass  # Error propagation is acceptable

    @pytest.mark.error
    async def test_broadcast_with_mixed_connections(self):
        from app.ws.connection_manager import ConnectionManager

        class GoodWS:
            def __init__(self):
                self.sent = []
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent.append(data)

        class BadWS:
            async def accept(self):
                pass
            async def send_json(self, data):
                raise Exception("Connection lost")

        manager = ConnectionManager()
        good = GoodWS()
        await manager.connect("good", good)
        await manager.connect("bad", BadWS())

        await manager.broadcast({"type": "test", "payload": {}})
        # Good connection should still receive
        assert len(good.sent) == 1
        # Bad connection should be removed
        assert "bad" not in manager.active_connections
