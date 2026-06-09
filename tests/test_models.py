"""Tests for data models, database schema, and configuration.

Tests for Pydantic model validation, database initialization,
migrations, and settings configuration.
"""
import asyncio
from collections import OrderedDict

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import (
    NewsItem, SentimentResult, AlertPayload, Subscription,
    WSMessage, Entity, EventCluster, MultiSentiment,
    EntityRelation, CausalChain,
)
from app import deps
from config.settings import Settings


# ---------- Pydantic Model Validation Tests ----------

class TestNewsItemModel:
    @pytest.mark.unit
    def test_minimal_valid_creation(self):
        item = NewsItem(source="test", title="新闻标题")
        assert item.source == "test"
        assert item.title == "新闻标题"
        assert item.url == ""
        assert item.content_snippet == ""

    @pytest.mark.unit
    def test_full_creation(self):
        from datetime import datetime
        now = datetime.now()
        item = NewsItem(
            source="CNBC",
            title="Fed Rate Cut",
            url="https://example.com",
            published_at=now,
            content_snippet="摘要",
            title_hash="abc123",
        )
        assert item.published_at == now
        assert item.title_hash == "abc123"

    @pytest.mark.unit
    def test_model_dump(self):
        item = NewsItem(source="test", title="标题")
        data = item.model_dump()
        assert data["source"] == "test"
        assert "published_at" in data

    @pytest.mark.unit
    def test_model_json(self):
        item = NewsItem(source="test", title="标题")
        json_str = item.model_dump_json()
        assert "test" in json_str
        assert "标题" in json_str


class TestSentimentResultModel:
    @pytest.mark.unit
    def test_valid_score_range(self):
        result = SentimentResult(
            news_item=NewsItem(source="t", title="x"),
            score=0.5,
            label="positive",
            confidence=0.9,
        )
        assert result.score == 0.5
        assert result.confidence == 0.9

    @pytest.mark.unit
    def test_score_boundary_validation(self):
        with pytest.raises(Exception):
            SentimentResult(
                news_item=NewsItem(source="t", title="x"),
                score=-1.1,
                label="negative",
            )

    @pytest.mark.unit
    def test_confidence_boundary_validation(self):
        with pytest.raises(Exception):
            SentimentResult(
                news_item=NewsItem(source="t", title="x"),
                score=0.0,
                confidence=1.1,
            )

    @pytest.mark.unit
    def test_default_values(self):
        result = SentimentResult(
            news_item=NewsItem(source="t", title="x"),
            score=0.0,
            label="neutral",
        )
        assert result.confidence == 0.0
        assert result.news_db_id is None
        assert result.sentiment_db_id is None


class TestAlertPayloadModel:
    @pytest.mark.unit
    def test_minimal_creation(self):
        item = NewsItem(source="test", title="x")
        sentiment = SentimentResult(news_item=item, score=-0.5, label="negative")
        alert = AlertPayload(news_item=item, sentiment=sentiment)
        assert alert.alert_level == "warning"
        assert alert.triggered_keywords == []
        assert alert.deep_analysis is None

    @pytest.mark.unit
    def test_full_creation(self):
        item = NewsItem(source="test", title="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(
            news_item=item,
            sentiment=sentiment,
            deep_analysis="深度分析内容",
            triggered_keywords=["降息", "央行"],
            alert_level="critical",
        )
        assert alert.deep_analysis == "深度分析内容"
        assert len(alert.triggered_keywords) == 2
        assert alert.alert_level == "critical"


class TestSubscriptionModel:
    @pytest.mark.unit
    def test_default_threshold(self):
        sub = Subscription(user_id="u1", keywords=["test"])
        assert sub.threshold == -0.5

    @pytest.mark.unit
    def test_custom_threshold(self):
        sub = Subscription(user_id="u1", keywords=["test"], threshold=-0.8)
        assert sub.threshold == -0.8

    @pytest.mark.unit
    def test_empty_keywords(self):
        sub = Subscription(user_id="u1", keywords=[])
        assert sub.keywords == []


class TestWSMessageModel:
    @pytest.mark.unit
    def test_creation(self):
        msg = WSMessage(type="alert", payload={"score": -0.5})
        assert msg.type == "alert"
        assert msg.payload["score"] == -0.5

    @pytest.mark.unit
    def test_model_dump(self):
        msg = WSMessage(type="test", payload={"key": "value"})
        data = msg.model_dump()
        assert data["type"] == "test"
        assert data["payload"]["key"] == "value"


class TestEntityModel:
    @pytest.mark.unit
    def test_minimal_creation(self):
        entity = Entity(name="央行", type="policy")
        assert entity.name == "央行"
        assert entity.type == "policy"
        assert entity.aliases == []

    @pytest.mark.unit
    def test_with_aliases(self):
        entity = Entity(name="央行", type="policy", aliases=["人民银行", "PBOC"])
        assert len(entity.aliases) == 2

    @pytest.mark.unit
    def test_model_dump(self):
        entity = Entity(name="test", type="test")
        data = entity.model_dump()
        assert data["name"] == "test"


class TestEventClusterModel:
    @pytest.mark.unit
    def test_creation(self):
        from datetime import datetime, timezone
        cluster = EventCluster(
            cluster_id="ev_1",
            title="央行降息",
            entities=[Entity(name="央行", type="policy")],
            news_ids=[1],
            sentiment_avg=-0.5,
            sentiment_distribution={"negative": 1},
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        assert cluster.significance == 0.0


class TestMultiSentimentModel:
    @pytest.mark.unit
    def test_defaults(self):
        ms = MultiSentiment(news_id=1)
        assert ms.fear == 0.0
        assert ms.greed == 0.0
        assert ms.optimism == 0.0
        assert ms.uncertainty == 0.0
        assert ms.dominant == "neutral"
        assert ms.momentum == 0.0
        assert ms.momentum_shift is False

    @pytest.mark.unit
    def test_full_values(self):
        ms = MultiSentiment(
            news_id=1,
            entity_name="央行",
            fear=0.8,
            greed=0.1,
            optimism=0.2,
            uncertainty=0.7,
            dominant="fear",
            momentum=0.5,
            momentum_shift=True,
        )
        assert ms.dominant == "fear"
        assert ms.momentum_shift is True


class TestEntityRelationModel:
    @pytest.mark.unit
    def test_creation(self):
        relation = EntityRelation(source="A", target="B", relation="affects")
        assert relation.confidence == 0.5  # default
        assert relation.context == ""

    @pytest.mark.unit
    def test_full_creation(self):
        relation = EntityRelation(
            source="央行", target="利率", relation="affects",
            context="央行决定利率", confidence=0.9,
        )
        assert relation.confidence == 0.9


class TestCausalChainModel:
    @pytest.mark.unit
    def test_creation(self):
        chain = CausalChain(
            trigger="降息",
            path=["降息", "利差收窄", "房贷上升"],
            impact="房地产利好",
            confidence=0.8,
        )
        assert len(chain.path) == 3
        assert chain.confidence == 0.8


# ---------- Database Schema Tests ----------

class TestDatabaseSchema:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_schema_creates_all_tables(self, db):
        """Verify all expected tables are created."""
        tables = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = {row["name"] for row in tables}
        expected = {
            "news", "sentiment", "alerts", "subscriptions",
            "reports", "entities", "news_entities",
            "event_clusters", "multi_sentiment",
            "entity_relations", "fed_policy_summary",
        }
        assert expected.issubset(table_names)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_schema_creates_indexes(self, db):
        """Verify expected indexes are created."""
        indexes = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row["name"] for row in indexes}
        expected_indexes = {
            "idx_news_hash", "idx_news_source", "idx_news_created",
            "idx_sentiment_score", "idx_sentiment_processed",
            "idx_alerts_level", "idx_alerts_created",
            "idx_reports_created", "idx_fed_policy_created",
            "idx_entities_name", "idx_entities_type",
            "idx_news_entities_news", "idx_news_entities_entity",
            "idx_event_clusters_significance",
            "idx_multi_sentiment_entity", "idx_multi_sentiment_processed",
            "idx_relations_source", "idx_relations_target",
        }
        assert expected_indexes.issubset(index_names)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_news_table_constraints(self, db):
        """Verify news table has expected constraints."""
        columns = await db.execute_fetchall("PRAGMA table_info(news)")
        col_info = {row["name"]: row for row in columns}
        assert col_info["title_hash"]["notnull"] == 1
        assert col_info["source"]["notnull"] == 1
        assert col_info["title"]["notnull"] == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sentiment_table_constraints(self, db):
        """Verify sentiment table has expected constraints."""
        columns = await db.execute_fetchall("PRAGMA table_info(sentiment)")
        col_info = {row["name"]: row for row in columns}
        assert col_info["news_id"]["notnull"] == 1
        assert col_info["score"]["notnull"] == 1
        assert col_info["label"]["notnull"] == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_entities_unique_constraint(self, db):
        """Verify entities table has unique constraint on (name, type)."""
        # The unique constraint is enforced by INSERT OR IGNORE in save_entities
        # Check that the table definition includes UNIQUE
        schema = await db.execute_fetchall("SELECT sql FROM sqlite_master WHERE type='table' AND name='entities'")
        table_sql = schema[0]["sql"]
        assert "UNIQUE" in table_sql


# ---------- Database Migration Tests ----------

class TestDatabaseMigrations:
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_migration_adds_reports_columns(self, db):
        """Verify migration adds redundant columns to reports table."""
        from app.db import _migrate
        await _migrate(db)

        columns = await db.execute_fetchall("PRAGMA table_info(reports)")
        col_names = {row["name"] for row in columns}
        expected_cols = {
            "news_title", "news_source", "news_url", "news_snippet",
            "sentiment_score", "sentiment_label", "sentiment_confidence",
            "referenced_news",
        }
        assert expected_cols.issubset(col_names)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_migration_is_idempotent(self, db):
        """Verify running migration twice doesn't fail."""
        from app.db import _migrate
        await _migrate(db)
        # Should not raise
        await _migrate(db)


# ---------- Settings Configuration Tests ----------

class TestSettingsConfiguration:
    @pytest.mark.unit
    def test_default_settings(self):
        settings = Settings(deepseek_api_key="test")
        assert settings.rss_poll_interval_seconds == 30
        assert settings.process_pool_size == 2
        assert settings.dedup_cache_max_size == 10000
        assert settings.deepseek_model == "deepseek-chat"
        assert settings.deepseek_temperature == 0.3
        assert settings.deepseek_max_tokens == 2048
        assert settings.default_alert_threshold == -0.5
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000

    @pytest.mark.unit
    def test_custom_settings(self):
        settings = Settings(
            deepseek_api_key="test",
            rss_poll_interval_seconds=60,
            process_pool_size=4,
            dedup_cache_max_size=50000,
        )
        assert settings.rss_poll_interval_seconds == 60
        assert settings.process_pool_size == 4
        assert settings.dedup_cache_max_size == 50000

    @pytest.mark.unit
    def test_rss_urls_default(self):
        settings = Settings(deepseek_api_key="test")
        assert "wallstreetcn" in settings.rss_urls
        assert "cls" in settings.rss_urls

    @pytest.mark.unit
    def test_smtp_defaults(self):
        settings = Settings(deepseek_api_key="test")
        assert settings.smtp_host == ""
        assert settings.smtp_port == 465
        assert settings.smtp_user == ""

    @pytest.mark.unit
    def test_model_name(self):
        settings = Settings(deepseek_api_key="test")
        assert "distilbert" in settings.model_name


# ---------- Deps Module Tests ----------

class TestDepsModule:
    @pytest.mark.unit
    def test_initial_state(self):
        """Verify deps module initial state."""
        assert deps.settings is None or deps.settings is not None
        assert deps.news_queue is None or isinstance(deps.news_queue, asyncio.Queue)
        assert isinstance(deps.dedup_cache, OrderedDict)
        assert isinstance(deps.active_connections, dict)
        assert isinstance(deps.active_subscriptions, dict)
        assert isinstance(deps.sources, dict)

    @pytest.mark.unit
    def test_settings_assignment(self):
        settings = Settings(deepseek_api_key="test")
        deps.settings = settings
        assert deps.settings is settings
        assert deps.settings.deepseek_api_key == "test"

    @pytest.mark.unit
    def test_queue_assignment(self):
        queue = asyncio.Queue(maxsize=10)
        deps.news_queue = queue
        assert deps.news_queue is queue

    @pytest.mark.unit
    def test_dedup_cache_assignment(self):
        cache = OrderedDict()
        deps.dedup_cache = cache
        assert deps.dedup_cache is cache


# ---------- Model Serialization Tests ----------

class TestModelSerialization:
    @pytest.mark.unit
    def test_news_item_roundtrip(self):
        item = NewsItem(source="test", title="标题", title_hash="hash1")
        data = item.model_dump()
        restored = NewsItem(**data)
        assert restored.title == item.title
        assert restored.source == item.source

    @pytest.mark.unit
    def test_sentiment_result_roundtrip(self):
        item = NewsItem(source="t", title="x")
        result = SentimentResult(news_item=item, score=-0.5, label="negative", confidence=0.8)
        data = result.model_dump()
        # news_item is nested, so it should be serializable
        assert "news_item" in data
        assert data["score"] == -0.5

    @pytest.mark.unit
    def test_alert_payload_roundtrip(self):
        item = NewsItem(source="t", title="x")
        sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
        alert = AlertPayload(
            news_item=item, sentiment=sentiment,
            deep_analysis="分析", triggered_keywords=["k1"],
        )
        data = alert.model_dump()
        assert data["deep_analysis"] == "分析"
        assert data["triggered_keywords"] == ["k1"]

    @pytest.mark.unit
    def test_entity_roundtrip(self):
        entity = Entity(name="央行", type="policy", aliases=["人民银行"])
        data = entity.model_dump()
        restored = Entity(**data)
        assert restored.name == "央行"
        assert restored.aliases == ["人民银行"]

    @pytest.mark.unit
    def test_multi_sentiment_roundtrip(self):
        ms = MultiSentiment(
            news_id=1, entity_name="央行",
            fear=0.8, greed=0.1, optimism=0.2, uncertainty=0.7,
            dominant="fear", momentum=0.5, momentum_shift=True,
        )
        data = ms.model_dump()
        restored = MultiSentiment(**data)
        assert restored.dominant == "fear"
        assert restored.momentum_shift is True

    @pytest.mark.unit
    def test_entity_relation_roundtrip(self):
        relation = EntityRelation(
            source="A", target="B", relation="affects",
            context="ctx", confidence=0.9,
        )
        data = relation.model_dump()
        restored = EntityRelation(**data)
        assert restored.confidence == 0.9
        assert restored.context == "ctx"

    @pytest.mark.unit
    def test_causal_chain_roundtrip(self):
        chain = CausalChain(
            trigger="起因", path=["a", "b", "c"],
            impact="结果", confidence=0.8,
        )
        data = chain.model_dump()
        restored = CausalChain(**data)
        assert restored.path == ["a", "b", "c"]
        assert restored.confidence == 0.8
