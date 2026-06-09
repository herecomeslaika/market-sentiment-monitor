"""Tests for the API routes."""
import pytest
from unittest.mock import AsyncMock, patch

from app.models import NewsItem, SentimentResult, AlertPayload


class TestHealthEndpoint:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_health_returns_ok(self, api_client):
        resp = await api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        for key in ["news_queue_size", "scored_queue_size", "alert_queue_size", "active_connections", "active_subscriptions", "dedup_cache_size"]:
            assert key in data


class TestStatusEndpoint:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_status_returns_info(self, api_client):
        resp = await api_client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        for key in ["settings", "queues", "connections", "subscriptions", "sources", "source_health"]:
            assert key in data


class TestSubscriptionEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_create_and_get_subscription(self, api_client):
        resp = await api_client.post("/subscriptions", json={"user_id": "u1", "keywords": ["降息"], "threshold": -0.5})
        assert resp.status_code == 200
        resp = await api_client.get("/subscriptions/u1")
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "u1"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_list_subscriptions(self, api_client):
        await api_client.post("/subscriptions", json={"user_id": "u1", "keywords": ["A"], "threshold": -0.5})
        resp = await api_client.get("/subscriptions")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_delete_subscription(self, api_client):
        await api_client.post("/subscriptions", json={"user_id": "u1", "keywords": ["A"], "threshold": -0.5})
        resp = await api_client.delete("/subscriptions/u1")
        assert resp.status_code == 200


class TestSourceEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_list_sources_empty(self, api_client):
        resp = await api_client.get("/sources")
        assert resp.status_code == 200
        assert resp.json() == {}

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_add_source(self, api_client):
        resp = await api_client.post("/sources", json={"key": "test_src", "name": "Test", "url": "https://example.com", "parser": "sina"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_delete_nonexistent_source(self, api_client):
        resp = await api_client.delete("/sources/nonexistent")
        assert resp.status_code == 404


class TestReportEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_list_reports(self, api_client):
        resp = await api_client.get("/reports")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_get_nonexistent_report(self, api_client):
        resp = await api_client.get("/reports/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_followup_nonexistent_report(self, api_client):
        resp = await api_client.post("/reports/nonexistent/followup", json={"question": "test"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_export_markdown_nonexistent(self, api_client):
        resp = await api_client.get("/reports/nonexistent/markdown")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_compare_nonexistent(self, api_client):
        resp = await api_client.post("/reports/nonexistent/compare")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_generate_report_missing_body(self, api_client):
        resp = await api_client.post("/reports/generate")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_generate_report_no_news(self, api_client):
        with patch("app.analysis.intent_report.extract_keywords", new_callable=AsyncMock, return_value=["不存在的关键词"]), \
             patch("app.analysis.intent_report.search_recent_news", new_callable=AsyncMock, return_value=[]), \
             patch("app.analysis.intent_report.crawl_fresh_news", new_callable=AsyncMock, return_value=[]):
            resp = await api_client.post("/reports/generate", json={"intent": "不存在的主题", "hours": 24})
            assert resp.status_code == 200
            assert "error" in resp.json()

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_generate_report_success(self, api_client):
        mock_news = [{"title": "央行降息", "source": "test", "url": "", "content_snippet": "降息了", "score": -0.5, "label": "negative", "confidence": 0.9}]
        with patch("app.analysis.intent_report.extract_keywords", new_callable=AsyncMock, return_value=["降息"]), \
             patch("app.analysis.intent_report.search_recent_news", new_callable=AsyncMock, return_value=mock_news), \
             patch("app.analysis.intent_report.generate_analysis", new_callable=AsyncMock, return_value="测试研报"), \
             patch("app.repository.save_report", new_callable=AsyncMock):
            resp = await api_client.post("/reports/generate", json={"intent": "降息对银行股的影响", "hours": 24})
            assert resp.status_code == 200
            data = resp.json()
            assert data["report_id"].startswith("r_")
            assert data["deep_analysis"] == "测试研报"


class TestSentimentEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_sentiment_trend(self, api_client):
        resp = await api_client.get("/sentiment/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert "trend" in data
        assert "momentum_shifts" in data

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_sentiment_history(self, api_client):
        resp = await api_client.get("/sentiment/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestEntityAndEventEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_list_entities(self, api_client):
        resp = await api_client.get("/entities")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_list_events(self, api_client):
        resp = await api_client.get("/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_multi_sentiment_history(self, api_client):
        resp = await api_client.get("/sentiment/multi")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_knowledge_relations(self, api_client):
        resp = await api_client.get("/knowledge/relations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestNotificationEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_get_notification_prefs(self, api_client):
        resp = await api_client.get("/notifications/u1")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_set_notification_prefs(self, api_client):
        resp = await api_client.put("/notifications/u1", json={"silence_minutes": 30, "min_level": "warning"})
        assert resp.status_code == 200


class TestFedPolicyEndpoints:
    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_fed_policy_no_data(self, api_client):
        with patch("app.analysis.fed_policy.get_fed_policy", return_value={"rate_trend": "no data", "summary": "no data", "policy_stance": "", "qt_qe_status": "", "key_events": [], "outlook": "", "sources": [], "news_count": 0}):
            resp = await api_client.get("/fed-policy")
            assert resp.status_code == 200
            data = resp.json()
            assert "rate_trend" in data

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_fed_policy_refresh(self, api_client):
        mock_result = {
            "rate_trend": "cutting", "policy_stance": "dovish", "qt_qe_status": "QT ongoing",
            "summary": "美联储进入降息周期", "key_events": ["FOMC signals rate cut"],
            "outlook": "预计继续降息", "sources": ["CNBC"], "news_count": 5,
        }
        with patch("app.analysis.fed_policy.get_fed_policy", return_value=mock_result):
            resp = await api_client.get("/fed-policy?refresh=true")
            assert resp.status_code == 200
            data = resp.json()
            assert data["rate_trend"] == "cutting"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_fed_policy_news(self, api_client):
        with patch("app.analysis.fed_policy.search_fed_news", return_value=[]):
            resp = await api_client.get("/fed-policy/news")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)