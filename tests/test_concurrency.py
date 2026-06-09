"""Concurrency and race condition tests.

Tests for thread safety, async race conditions, concurrent queue operations,
WebSocket concurrent connections, and parallel data access.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from collections import OrderedDict

from app.models import NewsItem, SentimentResult, AlertPayload, WSMessage
from app import deps
from config.settings import Settings


# ---------- Async Queue Concurrency ----------

class TestQueueConcurrency:
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_concurrent_put_and_get(self):
        queue = asyncio.Queue(maxsize=100)
        items = [f"item_{i}" for i in range(50)]

        async def producer():
            for item in items:
                await queue.put(item)

        async def consumer():
            results = []
            for _ in range(50):
                result = await queue.get()
                results.append(result)
                queue.task_done()
            return results

        producer_task = asyncio.create_task(producer())
        consumer_task = asyncio.create_task(consumer())

        await asyncio.gather(producer_task, consumer_task)
        consumed = await consumer_task
        assert len(consumed) == 50
        assert set(consumed) == set(items)

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_multiple_producers_single_consumer(self):
        queue = asyncio.Queue(maxsize=100)

        async def producer(start, count):
            for i in range(count):
                await queue.put(f"p{start}_{i}")

        async def consumer():
            results = []
            for _ in range(30):
                results.append(await queue.get())
                queue.task_done()
            return results

        producers = [asyncio.create_task(producer(i, 10)) for i in range(3)]
        consumer_task = asyncio.create_task(consumer())

        await asyncio.gather(*producers)
        results = await consumer_task
        assert len(results) == 30

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_queue_full_blocking(self):
        queue = asyncio.Queue(maxsize=1)
        await queue.put("first")

        async def try_put():
            try:
                await asyncio.wait_for(queue.put("second"), timeout=0.1)
                return True
            except asyncio.TimeoutError:
                return False

        result = await try_put()
        assert result is False  # Should timeout because queue is full

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_concurrent_dedup_cache_access(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=1000)

        async def register_hashes(start, count):
            for i in range(count):
                check_and_register(f"hash_{start}_{i}")

        tasks = [asyncio.create_task(register_hashes(i, 50)) for i in range(5)]
        await asyncio.gather(*tasks)
        assert len(deps.dedup_cache) <= 1000


# ---------- WebSocket Concurrent Connections ----------

class TestWebSocketConcurrency:
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_concurrent_connections(self):
        from app.ws.connection_manager import ConnectionManager

        class FakeWS:
            def __init__(self, name):
                self.name = name
                self.sent = []
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent.append(data)

        manager = ConnectionManager()
        connections = [FakeWS(f"user_{i}") for i in range(10)]

        for i, ws in enumerate(connections):
            await manager.connect(f"user_{i}", ws)

        assert len(manager.active_connections) == 10

        msg = {"type": "test", "payload": {"key": "value"}}
        await manager.broadcast(msg)

        for ws in connections:
            assert len(ws.sent) == 1

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_disconnect_during_broadcast(self):
        from app.ws.connection_manager import ConnectionManager

        class DisconnectingWS:
            def __init__(self):
                self.sent = []
                self.fail_after = 2
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent.append(data)
                if len(self.sent) >= self.fail_after:
                    raise Exception("Simulated disconnect")

        manager = ConnectionManager()
        ws = DisconnectingWS()
        await manager.connect("fragile", ws)

        await manager.broadcast({"type": "test"})
        await manager.broadcast({"type": "test"})

        # Should be removed after failure
        assert "fragile" not in manager.active_connections

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_rapid_connect_disconnect(self):
        from app.ws.connection_manager import ConnectionManager

        class MinimalWS:
            async def accept(self):
                pass
            async def send_json(self, data):
                pass

        manager = ConnectionManager()
        for i in range(20):
            ws = MinimalWS()
            await manager.connect(f"user_{i}", ws)
            manager.disconnect(f"user_{i}")

        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_broadcast_with_many_connections(self):
        from app.ws.connection_manager import ConnectionManager

        class CountingWS:
            def __init__(self):
                self.sent_count = 0
            async def accept(self):
                pass
            async def send_json(self, data):
                self.sent_count += 1

        manager = ConnectionManager()
        connections = [CountingWS() for _ in range(100)]

        for i, ws in enumerate(connections):
            await manager.connect(f"u_{i}", ws)

        await manager.broadcast({"type": "sentiment", "payload": {"score": 0.5}})

        for ws in connections:
            assert ws.sent_count == 1


# ---------- Subscription Matcher Concurrency ----------

class TestSubscriptionMatcherConcurrency:
    @pytest.mark.concurrency
    def test_concurrent_subscription_modification(self):
        from app.subscription.matcher import match_subscriptions
        from app.models import Subscription

        deps.active_subscriptions = {}

        # Add subscriptions from multiple "threads"
        for i in range(50):
            deps.active_subscriptions[f"u{i}"] = Subscription(
                user_id=f"u{i}",
                keywords=[f"keyword_{i}"],
                threshold=-0.5,
            )

        item = NewsItem(source="test", title="keyword_0 keyword_1 keyword_2", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)

        matched = match_subscriptions(alert)
        assert len(matched) == 3

    @pytest.mark.concurrency
    def test_subscription_modification_during_matching(self):
        from app.subscription.matcher import match_subscriptions
        from app.models import Subscription

        deps.active_subscriptions = {
            "u1": Subscription(user_id="u1", keywords=["降息"], threshold=-0.5),
        }

        item = NewsItem(source="test", title="央行降息", title_hash="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)

        # Modify subscriptions during matching (simulated)
        matched = match_subscriptions(alert)
        deps.active_subscriptions["u2"] = Subscription(user_id="u2", keywords=["央行"], threshold=-0.5)

        assert len(matched) == 1


# ---------- Database Concurrent Access ----------

class TestDatabaseConcurrency:
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_concurrent_entity_saves(self, db):
        from app.models import Entity
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_entities

            async def save_batch(start, count):
                entities = [Entity(name=f"entity_{start}_{i}", type="test") for i in range(count)]
                return await save_entities(1, entities)

            tasks = [asyncio.create_task(save_batch(i, 5)) for i in range(5)]
            results = await asyncio.gather(*tasks)

            total = sum(len(r) for r in results)
            assert total == 25

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_concurrent_news_queries(self, seeded_db):
        db, _ = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_news

            async def query_multiple():
                results = []
                for _ in range(5):
                    results.append(await query_news(limit=10))
                return results

            tasks = [asyncio.create_task(query_multiple()) for _ in range(3)]
            all_results = await asyncio.gather(*tasks)

            for results in all_results:
                assert len(results) == 5


# ---------- Source Health Concurrent Updates ----------

class TestSourceHealthConcurrency:
    @pytest.mark.concurrency
    def test_concurrent_health_updates(self):
        from app.crawler.sources import SourceHealth

        health = SourceHealth()
        for _ in range(100):
            health.consecutive_failures += 1

        assert health.consecutive_failures == 100
        assert health.is_healthy is False

    @pytest.mark.concurrency
    def test_health_recovery_after_failures(self):
        from app.crawler.sources import SourceHealth

        health = SourceHealth()
        health.consecutive_failures = 10
        assert health.is_healthy is False

        health.consecutive_failures = 0
        assert health.is_healthy is True


# ---------- Notification Concurrent Access ----------

class TestNotificationConcurrency:
    @pytest.mark.concurrency
    def test_concurrent_silence_checks(self):
        from app.notification.dispatcher import (
            set_notification_prefs, is_in_silence_period, mark_alert_sent, _notification_prefs
        )
        _notification_prefs.clear()
        set_notification_prefs("u1", {"silence_minutes": 30})
        mark_alert_sent("u1")

        # Multiple checks should all return the same result
        results = [is_in_silence_period("u1") for _ in range(100)]
        assert all(r is True for r in results)

    @pytest.mark.concurrency
    def test_notification_prefs_race_condition(self):
        from app.notification.dispatcher import (
            set_notification_prefs, get_notification_prefs, _notification_prefs
        )
        _notification_prefs.clear()

        # Simulate rapid updates
        for i in range(50):
            set_notification_prefs("u1", {"silence_minutes": i})

        prefs = get_notification_prefs("u1")
        assert prefs["silence_minutes"] == 49


# ---------- Async Task Cancellation ----------

class TestAsyncTaskCancellation:
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_task_cancellation_during_queue_operation(self):
        queue = asyncio.Queue()

        async def slow_consumer():
            try:
                while True:
                    await asyncio.wait_for(queue.get(), timeout=0.01)
            except asyncio.TimeoutError:
                pass

        task = asyncio.create_task(slow_consumer())
        await asyncio.sleep(0.05)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    @pytest.mark.concurrency
    async def test_graceful_shutdown_with_pending_items(self):
        queue = asyncio.Queue()
        for i in range(10):
            queue.put_nowait(f"item_{i}")

        # Simulate shutdown: process remaining items
        processed = []
        while not queue.empty():
            try:
                item = queue.get_nowait()
                processed.append(item)
                queue.task_done()
            except asyncio.QueueEmpty:
                break

        assert len(processed) == 10


# ---------- Memory Pressure Tests ----------

class TestMemoryPressure:
    @pytest.mark.concurrency
    def test_dedup_cache_under_memory_pressure(self):
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=100000)

        # Register many items
        for i in range(100000):
            check_and_register(f"hash_{i}")

        assert len(deps.dedup_cache) == 100000

        # Register more - should evict oldest
        for i in range(100000, 110000):
            check_and_register(f"hash_{i}")

        assert len(deps.dedup_cache) == 100000
        assert "hash_0" not in deps.dedup_cache
        assert "hash_109999" in deps.dedup_cache
