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
