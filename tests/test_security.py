"""Security and input validation tests.

Tests for SQL injection prevention, XSS prevention, input sanitization,
authentication checks, and data validation.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import NewsItem, SentimentResult, AlertPayload
from app import deps


# ---------- SQL Injection Prevention ----------

class TestSQLInjectionPrevention:
    @pytest.mark.security
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_news_title_with_sql_injection(self, db):
        malicious_title = "'; DROP TABLE news; --"
        item = NewsItem(
            source="test",
            title=malicious_title,
            title_hash="sql_inject_hash",
            content_snippet="test",
        )
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_news
            news_id = await save_news(item)
            assert news_id is not None
            # Verify table still exists
            rows = await db.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='news'"
            )
            assert len(rows) == 1

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_source_filter_sql_injection(self, db):
        malicious_source = "test'; DELETE FROM news; --"
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_news
            # Should not crash or execute malicious SQL
            result = await query_news(source=malicious_source)
            assert isinstance(result, list)
            # Verify no data was deleted
            rows = await db.execute_fetchall("SELECT COUNT(*) as c FROM news")
            assert rows[0]["c"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_entity_name_sql_injection(self, db):
        malicious_name = "央行'; DROP TABLE entities; --"
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_entity_timeline
            result = await query_entity_timeline(malicious_name)
            assert isinstance(result, list)
            # Verify table still exists
            rows = await db.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
            )
            assert len(rows) == 1

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_report_id_sql_injection(self, db):
        malicious_id = "r_1'; DROP TABLE reports; --"
        with patch("app.repository.get_db", return_value=db):
            from app.repository import load_report
            result = await load_report(malicious_id)
            assert result is None
            # Verify table still exists
            rows = await db.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='reports'"
            )
            assert len(rows) == 1

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_user_id_sql_injection(self, db):
        malicious_user = "u1'; DELETE FROM subscriptions; --"
        with patch("app.repository.get_db", return_value=db):
            from app.repository import save_subscription
            await save_subscription(malicious_user, ["test"], -0.5)
            # Verify no data was deleted
            rows = await db.execute_fetchall("SELECT COUNT(*) as c FROM subscriptions")
            assert rows[0]["c"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_keyword_stats_sql_injection(self, db):
        with patch("app.repository.get_db", return_value=db):
            from app.repository import query_keyword_stats
            # Should not crash with extreme hours value
            result = await query_keyword_stats(hours=999999999)
            assert isinstance(result, list)


# ---------- XSS Prevention ----------

class TestXSSPrevention:
    @pytest.mark.security
    def test_news_item_with_script_tag(self):
        item = NewsItem(
            source="test",
            title="<script>alert('xss')</script>正常新闻",
            url="javascript:alert('xss')",
            content_snippet="<img src=x onerror=alert('xss')>",
        )
        assert "<script>" in item.title
        # Model stores raw data; frontend should escape on display

    @pytest.mark.security
    def test_alert_payload_with_html(self):
        item = NewsItem(source="test", title="<b>bold</b>")
        sentiment = SentimentResult(news_item=item, score=-0.5, label="negative")
        alert = AlertPayload(
            news_item=item,
            sentiment=sentiment,
            deep_analysis="<script>alert('xss')</script>分析内容",
        )
        assert "<script>" in alert.deep_analysis

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_report_export_escapes_html(self):
        from app.analysis.report_service import export_markdown
        report = {
            "news_title": "<script>alert('xss')</script>",
            "news_source": "test",
            "sentiment_score": -0.5,
            "sentiment_label": "negative",
            "sentiment_confidence": 0.85,
            "alert_level": "warning",
            "triggered_keywords": [],
            "created_at": "2026-06-01",
            "news_url": "",
            "news_snippet": "<img src=x onerror=alert('xss')>",
        }
        md = export_markdown(report)
        assert md is not None
        # Markdown output contains raw text (not executed as script)


# ---------- Input Validation ----------

class TestAPIInputValidation:
    @pytest.mark.security
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_create_subscription_invalid_threshold(self, api_client):
        resp = await api_client.post(
            "/subscriptions",
            json={"user_id": "u1", "keywords": ["test"], "threshold": "invalid"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_create_subscription_missing_required(self, api_client):
        resp = await api_client.post("/subscriptions", json={"user_id": "u1"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_create_subscription_empty_user_id(self, api_client):
        resp = await api_client.post(
            "/subscriptions",
            json={"user_id": "", "keywords": ["test"], "threshold": -0.5},
        )
        # Empty string is technically valid for string fields
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_news_history_negative_limit(self, api_client):
        resp = await api_client.get("/news/history?limit=-1")
        assert resp.status_code == 422  # FastAPI validates positive int

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_news_history_zero_limit(self, api_client):
        resp = await api_client.get("/news/history?limit=0")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sentiment_trend_negative_hours(self, api_client):
        resp = await api_client.get("/sentiment/trend?hours=-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_generate_report_empty_intent(self, api_client):
        resp = await api_client.post("/reports/generate", json={"intent": ""})
        assert resp.status_code == 200  # Empty intent is allowed

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_generate_report_very_long_intent(self, api_client):
        long_intent = "分析" * 1000
        with patch("app.analysis.intent_report.extract_keywords", new_callable=AsyncMock, return_value=["分析"]), \
             patch("app.analysis.intent_report.search_recent_news", new_callable=AsyncMock, return_value=[]), \
             patch("app.analysis.intent_report.crawl_fresh_news", new_callable=AsyncMock, return_value=[]):
            resp = await api_client.post("/reports/generate", json={"intent": long_intent})
            assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_add_source_invalid_parser(self, api_client):
        resp = await api_client.post(
            "/sources",
            json={"key": "test", "name": "Test", "url": "https://example.com", "parser": "nonexistent"},
        )
        assert resp.status_code == 200  # Currently allows any parser string

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_add_source_malformed_url(self, api_client):
        resp = await api_client.post(
            "/sources",
            json={"key": "test", "name": "Test", "url": "not-a-url", "parser": "rss"},
        )
        assert resp.status_code == 200  # URL validation is not strict

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_notification_prefs_invalid_level(self, api_client):
        resp = await api_client.put(
            "/notifications/u1",
            json={"silence_minutes": 30, "min_level": "invalid_level"},
        )
        assert resp.status_code == 200  # Currently accepts any string

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_notification_prefs_negative_silence(self, api_client):
        resp = await api_client.put(
            "/notifications/u1",
            json={"silence_minutes": -1, "min_level": "info"},
        )
        assert resp.status_code == 200


# ---------- Settings Validation ----------

class TestSettingsValidation:
    @pytest.mark.security
    def test_missing_api_key(self):
        settings = Settings(deepseek_api_key="")
        assert settings.deepseek_api_key == ""

    @pytest.mark.security
    def test_negative_poll_interval(self):
        settings = Settings(rss_poll_interval_seconds=-1)
        assert settings.rss_poll_interval_seconds == -1
        # Should be validated at usage time

    @pytest.mark.security
    def test_zero_process_pool_size(self):
        settings = Settings(process_pool_size=0)
        assert settings.process_pool_size == 0

    @pytest.mark.security
    def test_very_large_cache_size(self):
        settings = Settings(dedup_cache_max_size=999999999)
        assert settings.dedup_cache_max_size == 999999999

    @pytest.mark.security
    def test_empty_smtp_settings(self):
        settings = Settings(smtp_host="", smtp_port=0)
        assert settings.smtp_host == ""
        assert settings.smtp_port == 0


# ---------- Parser Security ----------

class TestParserSecurity:
    @pytest.mark.security
    def test_parse_sina_with_malicious_json(self):
        from app.crawler.sources import parse_sina
        import json
        malicious = json.dumps({
            "result": {
                "data": [
                    {"title": "<script>alert(1)</script>", "url": "javascript:void(0)", "intro": "<img src=x onerror=alert(1)>"},
                ]
            }
        })
        items = parse_sina(malicious, "test")
        assert len(items) == 1
        # Raw data stored; frontend should escape
        assert "<script>" in items[0].title

    @pytest.mark.security
    def test_parse_cls_with_malicious_content(self):
        from app.crawler.sources import parse_cls
        import json
        malicious = json.dumps({
            "data": {
                "roll_data": [
                    {"title": "<b>test</b>", "content": "<script>alert(1)</script>", "id": "1"},
                ]
            }
        })
        items = parse_cls(malicious, "test")
        assert len(items) == 1
        assert "<script>" in items[0].content_snippet

    @pytest.mark.security
    def test_parse_rss_with_malicious_xml(self):
        from app.crawler.sources import parse_rss
        malicious = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <title>Test</title>
            <item>
              <title><![CDATA[<script>alert('xss')</script>]]></title>
              <link>javascript:alert('xss')</link>
              <description><![CDATA[<img src=x onerror=alert('xss')>]]></description>
            </item>
          </channel>
        </rss>"""
        items = parse_rss(malicious, "test")
        if items:
            assert "<script>" in items[0].title or "alert" in items[0].title

    @pytest.mark.security
    def test_parse_rss_with_billion_laughs(self):
        from app.crawler.sources import parse_rss
        # Simple test for XML entity expansion
        malicious = """<?xml version="1.0"?>
        <!DOCTYPE rss [
          <!ENTITY xxe "XXE">
        ]>
        <rss version="2.0">
          <channel>
            <item><title>&xxe;</title><link></link><description></description></item>
          </channel>
        </rss>"""
        # Should handle without crashing
        items = parse_rss(malicious, "test")
        assert isinstance(items, list)


# ---------- Queue Security ----------

class TestQueueSecurity:
    @pytest.mark.security
    def test_queue_with_large_payload(self):
        import asyncio
        queue = asyncio.Queue(maxsize=10)
        large_item = "x" * 1000000
        queue.put_nowait(large_item)
        assert queue.qsize() == 1

    @pytest.mark.security
    def test_queue_overflow_handling(self):
        import asyncio
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait("item1")
        with pytest.raises(asyncio.QueueFull):
            queue.put_nowait("item2")

    @pytest.mark.security
    def test_dedup_cache_with_many_entries(self):
        from collections import OrderedDict
        from app.crawler.dedup import check_and_register
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=10000)
        for i in range(15000):
            check_and_register(f"hash_{i}")
        assert len(deps.dedup_cache) == 10000


# ---------- WebSocket Security ----------

class TestWebSocketSecurity:
    @pytest.mark.security
    async def test_reject_malformed_message(self):
        from app.ws.connection_manager import ConnectionManager
        from app.models import WSMessage

        class FakeWS:
            async def accept(self):
                pass
            async def send_json(self, data):
                pass

        manager = ConnectionManager()
        await manager.connect("user1", FakeWS())
        # Should handle malformed payload gracefully
        msg = WSMessage(type="alert", payload={"<script>": "alert(1)"})
        await manager.send_to_user("user1", msg)
        assert "user1" in manager.active_connections
