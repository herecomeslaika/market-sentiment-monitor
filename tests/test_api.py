"""Tests for the API routes."""
import asyncio
from collections import OrderedDict

import pytest
from httpx import AsyncClient, ASGITransport

from app import deps
from app.models import Subscription
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
    deps.sources = {}
    yield
    deps.active_subscriptions.clear()
    deps.dedup_cache.clear()
    deps.sources = {}


@pytest.fixture
async def client():
    from app.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "news_queue_size" in data
        assert "scored_queue_size" in data
        assert "alert_queue_size" in data
        assert "active_connections" in data
        assert "active_subscriptions" in data
        assert "dedup_cache_size" in data


class TestStatusEndpoint:
    async def test_status_returns_info(self, client):
        resp = await client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "settings" in data
        assert "queues" in data
        assert "connections" in data
        assert "subscriptions" in data
        assert "sources" in data
        assert "source_health" in data


class TestSubscriptionEndpoints:
    async def test_create_subscription(self, client):
        resp = await client.post("/subscriptions", json={
            "user_id": "u1", "keywords": ["美联储", "降息"], "threshold": -0.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "u1"
        assert "美联储" in data["keywords"]

    async def test_list_subscriptions(self, client):
        await client.post("/subscriptions", json={
            "user_id": "u1", "keywords": ["A"], "threshold": -0.5,
        })
        resp = await client.get("/subscriptions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_get_subscription(self, client):
        await client.post("/subscriptions", json={
            "user_id": "u1", "keywords": ["B"], "threshold": -0.3,
        })
        resp = await client.get("/subscriptions/u1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "u1"

    async def test_delete_subscription(self, client):
        await client.post("/subscriptions", json={
            "user_id": "u1", "keywords": ["C"], "threshold": -0.5,
        })
        resp = await client.delete("/subscriptions/u1")
        assert resp.status_code == 200
        assert "u1" not in deps.active_subscriptions


class TestSourceEndpoints:
    async def test_list_sources_empty(self, client):
        resp = await client.get("/sources")
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_add_source(self, client):
        resp = await client.post("/sources", json={
            "key": "test_src", "name": "Test Source", "url": "https://example.com", "parser": "sina",
        })
        assert resp.status_code == 200
        assert "test_src" in deps.sources

    async def test_update_source(self, client):
        deps.sources["test_src"] = type("SC", (), {"name": "Test", "url": "https://x.com", "parser": "sina", "enabled": True})()
        resp = await client.patch("/sources/test_src", json={"enabled": False})
        assert resp.status_code == 200
        assert deps.sources["test_src"].enabled is False

    async def test_update_nonexistent_source(self, client):
        resp = await client.patch("/sources/nonexistent", json={"enabled": False})
        assert resp.status_code == 404

    async def test_delete_source(self, client):
        deps.sources["test_src"] = type("SC", (), {"name": "Test", "url": "https://x.com", "parser": "sina", "enabled": True})()
        resp = await client.delete("/sources/test_src")
        assert resp.status_code == 200
        assert "test_src" not in deps.sources

    async def test_delete_nonexistent_source(self, client):
        resp = await client.delete("/sources/nonexistent")
        assert resp.status_code == 404


class TestReportEndpoints:
    async def test_get_nonexistent_report(self, client):
        resp = await client.get("/reports/nonexistent")
        assert resp.status_code == 404

    async def test_followup_nonexistent_report(self, client):
        resp = await client.post("/reports/nonexistent/followup", json={"question": "test"})
        assert resp.status_code == 404

    async def test_export_markdown_nonexistent(self, client):
        resp = await client.get("/reports/nonexistent/markdown")
        assert resp.status_code == 404

    async def test_compare_nonexistent(self, client):
        resp = await client.post("/reports/nonexistent/compare")
        assert resp.status_code == 404

    async def test_list_reports(self, client):
        resp = await client.get("/reports")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_generate_report_missing_body(self, client):
        resp = await client.post("/reports/generate")
        assert resp.status_code == 422

    async def test_generate_report_no_news(self, client):
        from unittest.mock import AsyncMock, patch
        with patch("app.analysis.intent_report.extract_keywords", new_callable=AsyncMock, return_value=["不存在的关键词"]), \
             patch("app.analysis.intent_report.search_recent_news", new_callable=AsyncMock, return_value=[]), \
             patch("app.analysis.intent_report.crawl_fresh_news", new_callable=AsyncMock, return_value=[]):
            resp = await client.post("/reports/generate", json={"intent": "不存在的主题", "hours": 24})
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data

    async def test_generate_report_success(self, client):
        from unittest.mock import AsyncMock, patch
        mock_news = [{"title": "央行降息", "source": "test", "url": "", "content_snippet": "降息了", "score": -0.5, "label": "negative", "confidence": 0.9}]
        with patch("app.analysis.intent_report.extract_keywords", new_callable=AsyncMock, return_value=["降息"]), \
             patch("app.analysis.intent_report.search_recent_news", new_callable=AsyncMock, return_value=mock_news), \
             patch("app.analysis.intent_report.generate_analysis", new_callable=AsyncMock, return_value="这是一份测试研报"), \
             patch("app.repository.save_report", new_callable=AsyncMock):
            resp = await client.post("/reports/generate", json={"intent": "降息对银行股的影响", "hours": 24})
            assert resp.status_code == 200
            data = resp.json()
            assert data["report_id"].startswith("r_")
            assert data["news_count"] == 1
            assert data["deep_analysis"] == "这是一份测试研报"
