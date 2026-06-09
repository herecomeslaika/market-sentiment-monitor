"""Performance and load tests.

Tests for large dataset handling, memory usage, response times,
and stress conditions.
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from collections import OrderedDict

from app.models import NewsItem, SentimentResult, Entity
from app import deps
from config.settings import Settings


# ---------- Large Dataset Tests ----------

class TestLargeDatasetHandling:
    @pytest.mark.performance
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_query_news_with_large_offset(self, db):
        """Test querying with offset beyond data range."""
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_news
            start = time.time()
            result = await query_news(limit=10, offset=999999)
            elapsed = time.time() - start
            assert result == []
            assert elapsed < 1.0  # Should be fast even with large offset

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_save_many_news_items(self, db):
        """Test saving many news items sequentially."""
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            start = time.time()
            for i in range(100):
                item = NewsItem(
                    source="test",
                    title=f"新闻{i}",
                    title_hash=f"hash_{i}",
                )
                await save_news(item)
            elapsed = time.time() - start
            assert elapsed < 5.0  # Should complete within 5 seconds

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_batch_entity_saves(self, db):
        """Test saving many entities."""
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_entities
            entities = [Entity(name=f"entity_{i}", type="test") for i in range(100)]
            start = time.time()
            ids = await save_entities(1, entities)
            elapsed = time.time() - start
            assert len(ids) == 100
            assert elapsed < 3.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_sentiment_trend_with_empty_db(self, db):
        """Test sentiment trend query on empty database."""
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_sentiment_trend
            start = time.time()
            result = await query_sentiment_trend(hours=24)
            elapsed = time.time() - start
            assert "trend" in result
            assert "momentum_shifts" in result
            assert elapsed < 1.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_hot_entities_with_few_records(self, seeded_db):
        """Test hot entities query with limited data."""
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_hot_entities
            start = time.time()
            result = await query_hot_entities(limit=100)
            elapsed = time.time() - start
            assert len(result) >= 3
            assert elapsed < 1.0


# ---------- Memory Usage Tests ----------

class TestMemoryUsage:
    @pytest.mark.performance
    def test_dedup_cache_memory_efficiency(self):
        """Test dedup cache doesn't grow unbounded."""
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=10000)

        for i in range(20000):
            check_and_register(f"hash_{i}")

        assert len(deps.dedup_cache) == 10000

    @pytest.mark.performance
    def test_large_title_hash_computation(self):
        """Test hash computation with very long titles."""
        from app.crawler.sources import compute_title_hash
        title = "a" * 100000
        start = time.time()
        h = compute_title_hash(title)
        elapsed = time.time() - start
        assert isinstance(h, str)
        assert elapsed < 0.1  # Should be fast

    @pytest.mark.performance
    def test_large_html_clean(self):
        """Test HTML cleaning with large input."""
        from app.crawler.sources import _clean_html
        html = "<p>" + "content " * 10000 + "</p>"
        start = time.time()
        result = _clean_html(html)
        elapsed = time.time() - start
        assert len(result) <= 500  # Truncated
        assert elapsed < 1.0


# ---------- Response Time Tests ----------

class TestResponseTime:
    @pytest.mark.performance
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_health_endpoint_response_time(self, api_client):
        """Test health endpoint responds quickly."""
        start = time.time()
        resp = await api_client.get("/health")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 0.5

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_sources_list_response_time(self, api_client):
        """Test sources list responds quickly."""
        start = time.time()
        resp = await api_client.get("/sources")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 0.5

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_subscriptions_list_response_time(self, api_client):
        """Test subscriptions list responds quickly."""
        start = time.time()
        resp = await api_client.get("/subscriptions")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 0.5

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_entities_list_response_time(self, api_client):
        """Test entities list responds quickly."""
        start = time.time()
        resp = await api_client.get("/entities")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 1.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_sentiment_trend_response_time(self, api_client):
        """Test sentiment trend responds quickly."""
        start = time.time()
        resp = await api_client.get("/sentiment/trend")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 1.0


# ---------- Stress Tests ----------

class TestStressConditions:
    @pytest.mark.performance
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_api_requests(self, api_client):
        """Test handling multiple concurrent API requests."""
        async def make_request():
            resp = await api_client.get("/health")
            return resp.status_code

        start = time.time()
        tasks = [asyncio.create_task(make_request()) for _ in range(50)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        assert all(r == 200 for r in results)
        assert elapsed < 5.0  # 50 requests in under 5 seconds

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_rapid_subscription_operations(self, api_client):
        """Test rapid create/delete subscription operations."""
        async def create_and_delete(i):
            await api_client.post(
                "/subscriptions",
                json={"user_id": f"stress_{i}", "keywords": ["test"], "threshold": -0.5},
            )
            await api_client.delete(f"/subscriptions/stress_{i}")

        start = time.time()
        tasks = [asyncio.create_task(create_and_delete(i)) for i in range(20)]
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        assert elapsed < 10.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_queue_under_load(self):
        """Test queue performance under load."""
        queue = asyncio.Queue(maxsize=1000)

        async def producer(count):
            for i in range(count):
                await queue.put(f"item_{i}")

        async def consumer(count):
            for _ in range(count):
                await queue.get()
                queue.task_done()

        start = time.time()
        p_task = asyncio.create_task(producer(500))
        c_task = asyncio.create_task(consumer(500))
        await asyncio.gather(p_task, c_task)
        elapsed = time.time() - start

        assert queue.empty()
        assert elapsed < 5.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_dedup_cache_under_load(self):
        """Test dedup cache performance under load."""
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=100000)

        start = time.time()
        for i in range(10000):
            check_and_register(f"hash_{i}")
        elapsed = time.time() - start

        assert len(deps.dedup_cache) == 10000
        assert elapsed < 2.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_broadcast_to_many_connections(self):
        """Test WebSocket broadcast with many connections."""
        from app.ws.connection_manager import ConnectionManager

        class FastWS:
            def __init__(self):
                self.sent = []
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent.append(data)

        manager = ConnectionManager()
        connections = [FastWS() for _ in range(100)]

        start = time.time()
        for i, ws in enumerate(connections):
            await manager.connect(f"u_{i}", ws)

        await manager.broadcast({"type": "test", "payload": {}})
        elapsed = time.time() - start

        for ws in connections:
            assert len(ws.sent) == 1
        assert elapsed < 1.0


# ---------- Parser Performance Tests ----------

class TestParserPerformance:
    @pytest.mark.performance
    def test_parse_sina_performance(self):
        """Test Sina parser with large input."""
        import json
        from app.crawler.sources import parse_sina

        data = json.dumps({
            "result": {
                "data": [
                    {"title": f"新闻{i}", "url": f"https://example.com/{i}", "intro": f"摘要{i}"}
                    for i in range(100)
                ]
            }
        })

        start = time.time()
        items = parse_sina(data, "test")
        elapsed = time.time() - start

        assert len(items) == 100
        assert elapsed < 1.0

    @pytest.mark.performance
    def test_parse_rss_performance(self):
        """Test RSS parser with large feed."""
        from app.crawler.sources import parse_rss

        items_xml = "".join(
            f"""<item>
                <title>News {i}</title>
                <link>https://example.com/{i}</link>
                <description>Description {i}</description>
                <pubDate>Mon, 02 Jun 2026 14:{i:02d}:00 GMT</pubDate>
            </item>"""
            for i in range(100)
        )
        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel><title>Test</title>{items_xml}</channel>
        </rss>"""

        start = time.time()
        items = parse_rss(rss, "test")
        elapsed = time.time() - start

        assert len(items) == 100
        assert elapsed < 2.0


# ---------- Database Query Performance ----------

class TestDatabaseQueryPerformance:
    @pytest.mark.performance
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_entity_timeline_performance(self, seeded_db):
        """Test entity timeline query performance."""
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_entity_timeline
            start = time.time()
            result = await query_entity_timeline("央行", hours=168)
            elapsed = time.time() - start
            assert isinstance(result, list)
            assert elapsed < 1.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_keyword_stats_performance(self, seeded_db):
        """Test keyword stats query performance."""
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_keyword_stats
            start = time.time()
            result = await query_keyword_stats(hours=24)
            elapsed = time.time() - start
            assert isinstance(result, list)
            assert elapsed < 1.0

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_multi_sentiment_history_performance(self, seeded_db):
        """Test multi-sentiment history query performance."""
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_multi_sentiment_history
            start = time.time()
            result = await query_multi_sentiment_history(hours=24, limit=50)
            elapsed = time.time() - start
            assert isinstance(result, list)
            assert elapsed < 1.0


# ---------- Knowledge Graph Performance ----------

class TestKnowledgeGraphPerformance:
    @pytest.mark.performance
    def test_parse_relations_performance(self):
        """Test relation parsing with many relations."""
        from app.analysis.knowledge_graph import _parse_relations

        relations = [
            {"source": f"A{i}", "target": f"B{i}", "relation": "affects", "context": "", "confidence": 0.5}
            for i in range(100)
        ]
        import json
        text = json.dumps(relations)

        start = time.time()
        result = _parse_relations(text)
        elapsed = time.time() - start

        assert len(result) == 100
        assert elapsed < 1.0

    @pytest.mark.performance
    def test_parse_causal_chain_performance(self):
        """Test causal chain parsing with long path."""
        from app.analysis.knowledge_graph import _parse_causal_chain

        path = [f"步骤{i}" for i in range(50)]
        text = f'{{"trigger": "起因", "path": {path}, "impact": "结果", "confidence": 0.5}}'

        start = time.time()
        result = _parse_causal_chain(text)
        elapsed = time.time() - start

        assert result is not None
        assert len(result.path) == 50
        assert elapsed < 0.5


# ---------- Event Cluster Performance ----------

class TestEventClusterPerformance:
    @pytest.mark.performance
    def test_compute_significance_performance(self):
        """Test significance computation performance."""
        from app.analysis.event_cluster import compute_significance

        start = time.time()
        for _ in range(10000):
            compute_significance(5, -0.5)
        elapsed = time.time() - start

        assert elapsed < 1.0

    @pytest.mark.performance
    def test_find_matching_cluster_performance(self):
        """Test cluster matching with many clusters."""
        from app.analysis.event_cluster import find_matching_cluster
        from app.models import Entity, EventCluster
        from datetime import datetime, timezone

        entities = [Entity(name=f"entity_{i}", type="test") for i in range(20)]
        clusters = [
            EventCluster(
                cluster_id=f"ev_{i}",
                title=f"事件{i}",
                entities=entities[:10],
                news_ids=[i],
                sentiment_avg=-0.5,
                sentiment_distribution={"negative": 1},
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            for i in range(100)
        ]

        new_entities = [Entity(name="entity_0", type="test"), Entity(name="entity_1", type="test")]

        start = time.time()
        result = find_matching_cluster(new_entities, clusters, datetime.now(timezone.utc))
        elapsed = time.time() - start

        # Should find a match quickly
        assert elapsed < 2.0
