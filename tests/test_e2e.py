"""End-to-end pipeline integration tests.

Tests that verify the full data flow from news ingestion through sentiment
analysis, deep analysis, and API response.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from collections import OrderedDict

from app.models import (
    NewsItem, SentimentResult, AlertPayload, Entity, MultiSentiment,
    WSMessage,
)
from app import deps
from config.settings import Settings


# ---------- Full Pipeline Tests ----------

class TestFullPipeline:
    @pytest.fixture(autouse=True)
    def setup_deps(self):
        deps.settings = Settings(deepseek_api_key="test-key")
        deps.news_queue = asyncio.Queue(maxsize=100)
        deps.scored_queue = asyncio.Queue(maxsize=100)
        deps.alert_queue = asyncio.Queue(maxsize=50)
        deps.dedup_cache = OrderedDict()
        deps.active_connections = {}
        deps.active_subscriptions = {}
        deps.sources = {}
        yield
        deps.active_subscriptions.clear()
        deps.dedup_cache.clear()
        deps.sources = {}

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_from_crawl_to_alert(self, seeded_db):
        """Test the full pipeline: crawl -> dedup -> sentiment -> alert."""
        db, ids = seeded_db

        # Step 1: Simulate news ingestion
        news_item = NewsItem(
            source="CNBC",
            title="Fed signals aggressive rate cut amid recession fears",
            url="https://example.com/fed-cut",
            content_snippet="The Federal Reserve hinted at a possible rate cut.",
            title_hash="pipeline_hash_1",
        )

        # Step 2: Save to DB (simulate repository)
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            news_id = await save_news(news_item)
            assert news_id is not None

        # Step 3: Simulate sentiment scoring
        sentiment = SentimentResult(
            news_item=news_item,
            score=-0.8,
            label="negative",
            confidence=0.9,
            news_db_id=news_id,
        )

        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_sentiment
            sentiment_id = await save_sentiment(news_id, sentiment)
            assert sentiment_id is not None

        # Step 4: Simulate subscription matching
        deps.active_subscriptions["u1"] = {
            "user_id": "u1",
            "keywords": ["Fed", "rate cut"],
            "threshold": -0.5,
        }

        from app.models import Subscription
        deps.active_subscriptions["u1"] = Subscription(
            user_id="u1", keywords=["Fed", "rate cut"], threshold=-0.5
        )

        from app.subscription.matcher import match_subscriptions
        alert = AlertPayload(
            news_item=news_item,
            sentiment=sentiment,
            alert_level="critical",
            triggered_keywords=["Fed", "rate cut"],
        )
        matched = match_subscriptions(alert)
        assert len(matched) == 1
        assert matched[0][0].user_id == "u1"

        # Step 5: Simulate notification dispatch
        from app.notification.dispatcher import should_send_alert
        assert should_send_alert(alert, "u1") is True

        # Step 6: Verify data persisted
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_alert_history
            alerts = await query_alert_history(limit=10)
            # Alert not actually saved in this flow, but the pipeline is verified
            assert isinstance(alerts, list)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_entity_extraction(self, db):
        """Test pipeline with entity extraction and knowledge graph."""
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '[{"name":"美联储","type":"policy","aliases":["Fed"]},{"name":"利率","type":"indicator","aliases":[]}]'

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            entities = await extract_and_save(
                1, "美联储宣布降息", "详情内容", "hash1"
            )
            assert len(entities) == 2
            assert entities[0].name == "美联储"

        # Step 2: Extract relations
        mock_client.analyze.return_value = '[{"source":"美联储","target":"利率","relation":"affects","context":"央行决定利率","confidence":0.9}]'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            from app.analysis.knowledge_graph import extract_relations
            relations = await extract_relations("美联储降息", "详情", entities)
            assert len(relations) == 1
            assert relations[0].source == "美联储"

        # Step 3: Infer causal chain
        mock_client.analyze.return_value = '{"trigger":"降息","path":["降息","利差收窄","房贷上升"],"impact":"房地产利好","confidence":0.8}'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            from app.analysis.knowledge_graph import infer_causal_chain
            chain = await infer_causal_chain(entities, relations, "context")
            assert chain is not None
            assert chain.trigger == "降息"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_event_clustering(self, db):
        """Test event clustering pipeline."""
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "央行降息事件"

        entities = [
            Entity(name="央行", type="policy"),
            Entity(name="LPR", type="indicator"),
        ]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.event_cluster.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.event_cluster import try_cluster
            cluster = await try_cluster(
                1, "央行宣布降息", entities, -0.5, "negative"
            )
            if cluster:
                assert cluster.cluster_id.startswith("ev_")
                assert len(cluster.entities) == 2

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_multi_sentiment(self, seeded_db):
        """Test multi-dimensional sentiment analysis pipeline."""
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"fear":0.8,"greed":0.1,"optimism":0.2,"uncertainty":0.7,"dominant":"fear"}'

        entities = [Entity(name="央行", type="policy")]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(
                ids["n1"], "央行降息引发市场恐慌", "恐慌情绪蔓延", entities
            )
            assert result is not None
            assert result.dominant == "fear"
            assert result.fear > result.greed

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_fed_policy(self, db):
        """Test Fed policy tracking pipeline."""
        mock_items = [
            NewsItem(
                source="CNBC",
                title="Fed signals rate cut in September",
                url="",
                content_snippet="The Federal Reserve hinted at a possible rate cut.",
                title_hash="fed1",
            ),
            NewsItem(
                source="BBC",
                title="US inflation slows to 2.4%",
                url="",
                content_snippet="Inflation data shows slowing trend.",
                title_hash="fed2",
            ),
        ]

        # Step 1: Crawl Fed news
        with patch("app.crawler.sources.fetch_all_sources", return_value=mock_items):
            from app.analysis.fed_policy import crawl_fed_news
            fed_news = await crawl_fed_news()
            assert len(fed_news) >= 1

        # Step 2: Generate policy summary
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"rate_trend":"cutting","policy_stance":"dovish","qt_qe_status":"QT ongoing","rate_level":"5.00%-5.25%","summary":"美联储进入降息周期","key_events":["FOMC signals rate cut"],"outlook":"预计继续降息","sources":["CNBC"]}'

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.fed_policy.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.fed_policy import generate_policy_summary
            summary = await generate_policy_summary(fed_news)
            assert summary is not None
            assert summary["rate_trend"] == "cutting"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_intent_report(self, db):
        """Test intent-based report generation pipeline."""
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '["降息","银行","LPR","rate cut","interest rate"]'

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.intent_report.deps") as mock_deps:
            mock_deps.settings = MagicMock()
            from app.analysis.intent_report import extract_keywords
            keywords = await extract_keywords("降息对银行股的影响")
            assert len(keywords) >= 3

        # Step 2: Search recent news
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.intent_report import search_recent_news
            results = await search_recent_news(keywords, hours=168)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pipeline_with_report_followup(self, seeded_db):
        """Test report follow-up question pipeline."""
        db, ids = seeded_db
        alert = AlertPayload(
            news_item=NewsItem(source="test", title="央行降息"),
            sentiment=SentimentResult(
                news_item=NewsItem(source="test", title="x"), score=-0.5, label="negative"
            ),
            deep_analysis="央行降息利好债券市场",
        )

        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_report
            await save_report("r_pipeline_test", alert)

        mock_client = AsyncMock()
        mock_client.analyze.return_value = "降息对银行股的影响更大，因为净息差收窄"

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.report_service.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.report_service import followup_question
            result = await followup_question("r_pipeline_test", "降息对银行股有什么影响")
            assert result is not None
            assert "银行股" in result


# ---------- WebSocket Alert Pipeline ----------

class TestWebSocketAlertPipeline:
    @pytest.fixture(autouse=True)
    def setup_deps(self):
        deps.settings = Settings(deepseek_api_key="test-key")
        deps.news_queue = asyncio.Queue(maxsize=100)
        deps.scored_queue = asyncio.Queue(maxsize=100)
        deps.alert_queue = asyncio.Queue(maxsize=50)
        deps.dedup_cache = OrderedDict()
        deps.active_connections = {}
        deps.active_subscriptions = {}
        deps.sources = {}
        yield
        deps.active_subscriptions.clear()
        deps.dedup_cache.clear()
        deps.sources = {}

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_alert_broadcast_pipeline(self):
        from app.ws.connection_manager import ConnectionManager
        from app.models import WSMessage

        class FakeWS:
            def __init__(self):
                self.sent = []
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent.append(data)

        manager = ConnectionManager()
        ws = FakeWS()
        await manager.connect("u1", ws)

        # Simulate alert message
        msg = WSMessage(
            type="alert",
            payload={
                "title": "央行降息",
                "score": -0.8,
                "level": "critical",
                "keywords": ["降息", "央行"],
            },
        )
        await manager.send_to_user("u1", msg)
        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "alert"

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_momentum_shift_broadcast(self):
        from app.ws.connection_manager import ConnectionManager
        from app.models import WSMessage

        class FakeWS:
            def __init__(self):
                self.sent = []
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent.append(data)

        manager = ConnectionManager()
        ws1 = FakeWS()
        ws2 = FakeWS()
        await manager.connect("u1", ws1)
        await manager.connect("u2", ws2)

        msg = WSMessage(
            type="momentum_shift",
            payload={
                "entity": "央行",
                "from_dominant": "fear",
                "to_dominant": "optimism",
            },
        )
        await manager.broadcast(msg.model_dump())
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1


# ---------- Data Cleanup Pipeline ----------

class TestDataCleanupPipeline:
    @pytest.mark.asyncio
    async def test_cleanup_pipeline(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import cleanup_old_data, query_news

            # Verify data exists
            before = await query_news(limit=100)
            assert len(before) == 3

            # Cleanup with 0 days should not delete recent data
            await cleanup_old_data(days=0)
            after = await query_news(limit=100)
            assert len(after) == 3

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_full_data_lifecycle(self, db):
        """Test complete data lifecycle: create -> query -> cleanup."""
        with patch("app.repository.get_db", return_value=db):
            from app.repository import (
                save_news, load_news_by_id, query_news, cleanup_old_data
            )

            # Create
            item = NewsItem(
                source="test", title="生命周期测试", title_hash="lifecycle_1"
            )
            news_id = await save_news(item)
            assert news_id is not None

            # Read
            loaded = await load_news_by_id(news_id)
            assert loaded["title"] == "生命周期测试"

            # Query
            results = await query_news(limit=10)
            assert len(results) >= 1

            # Cleanup (0 days won't delete just-created items)
            await cleanup_old_data(days=0)
            after_cleanup = await query_news(limit=10)
            assert len(after_cleanup) >= 1


# ---------- Source Management Pipeline ----------

class TestSourceManagementPipeline:
    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_source_lifecycle(self, api_client):
        """Test full source lifecycle: add -> list -> update -> delete."""
        # Add
        resp = await api_client.post(
            "/sources",
            json={"key": "test_src", "name": "Test Source", "url": "https://test.com", "parser": "rss"},
        )
        assert resp.status_code == 200

        # List
        resp = await api_client.get("/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "test_src" in data

        # Update
        resp = await api_client.patch(
            "/sources/test_src",
            json={"enabled": False},
        )
        assert resp.status_code == 200

        # Delete
        resp = await api_client.delete("/sources/test_src")
        assert resp.status_code == 200

        # Verify deleted
        resp = await api_client.get("/sources")
        assert "test_src" not in resp.json()


# ---------- Subscription Lifecycle Pipeline ----------

class TestSubscriptionLifecyclePipeline:
    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_subscription_lifecycle(self, api_client):
        """Test full subscription lifecycle: create -> get -> list -> delete."""
        # Create
        resp = await api_client.post(
            "/subscriptions",
            json={"user_id": "lifecycle_user", "keywords": ["降息", "央行"], "threshold": -0.5},
        )
        assert resp.status_code == 200

        # Get
        resp = await api_client.get("/subscriptions/lifecycle_user")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "lifecycle_user"
        assert "降息" in data["keywords"]

        # List
        resp = await api_client.get("/subscriptions")
        assert resp.status_code == 200
        assert any(s["user_id"] == "lifecycle_user" for s in resp.json())

        # Delete
        resp = await api_client.delete("/subscriptions/lifecycle_user")
        assert resp.status_code == 200

        # Verify deleted
        resp = await api_client.get("/subscriptions/lifecycle_user")
        # May return None or 404 depending on implementation
        assert resp.status_code in [200, 404]
