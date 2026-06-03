"""Tests for event clustering module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.models import Entity, EventCluster


class TestFindMatchingCluster:
    @pytest.mark.asyncio
    async def test_matching_by_entity_overlap(self):
        from app.analysis.event_cluster import find_matching_cluster
        existing = EventCluster(
            cluster_id="ev_1", title="央行降息", entities=[
                Entity(name="央行", type="policy"),
                Entity(name="LPR", type="indicator"),
            ], news_ids=[1], sentiment_avg=-0.5,
            sentiment_distribution={"negative": 1},
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc),
        )
        new_entities = [Entity(name="央行", type="policy"), Entity(name="LPR", type="indicator")]
        result = find_matching_cluster(new_entities, [existing], datetime.now(timezone.utc))
        assert result is not None
        assert result.cluster_id == "ev_1"

    @pytest.mark.asyncio
    async def test_no_match_different_entities(self):
        from app.analysis.event_cluster import find_matching_cluster
        existing = EventCluster(
            cluster_id="ev_1", title="央行降息", entities=[
                Entity(name="央行", type="policy"),
                Entity(name="LPR", type="indicator"),
            ], news_ids=[1], sentiment_avg=-0.5,
            sentiment_distribution={"negative": 1},
            first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc),
        )
        new_entities = [Entity(name="苹果", type="company"), Entity(name="AI", type="industry")]
        result = find_matching_cluster(new_entities, [existing], datetime.now(timezone.utc))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_match_empty_entities(self):
        from app.analysis.event_cluster import find_matching_cluster
        result = find_matching_cluster([], [], datetime.now(timezone.utc))
        assert result is None


class TestComputeSignificance:
    def test_high_count_high_sentiment(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(10, -0.8)
        assert score > 0.7

    def test_low_count_low_sentiment(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(1, 0.1)
        assert score < 0.3

    def test_bounded_between_0_and_1(self):
        from app.analysis.event_cluster import compute_significance
        for count in [0, 1, 5, 100]:
            for avg in [-1.0, -0.5, 0.0, 0.5, 1.0]:
                score = compute_significance(count, avg)
                assert 0 <= score <= 1


class TestTryCluster:
    @pytest.mark.asyncio
    async def test_cluster_without_entities_returns_none(self, seeded_db):
        db, ids = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.event_cluster import try_cluster
            result = await try_cluster(ids["n1"], "测试标题", [], 0.5, "positive")
            assert result is None

    @pytest.mark.asyncio
    async def test_cluster_creates_new(self, db):
        entities = [Entity(name="英伟达", type="company"), Entity(name="AI芯片", type="industry")]
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "英伟达AI芯片事件"

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.event_cluster.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.event_cluster import try_cluster
            result = await try_cluster(1, "英伟达发布新AI芯片", entities, 0.7, "positive")
            if result:
                assert result.cluster_id.startswith("ev_")
                assert len(result.entities) == 2
