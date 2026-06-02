"""Tests for event clustering module."""
import pytest
from datetime import datetime, timezone, timedelta

from app.models import Entity, EventCluster


class TestEntityNames:
    def test_extracts_names_and_aliases(self):
        from app.analysis.event_cluster import _entity_names
        entities = [
            Entity(name="工商银行", type="company", aliases=["ICBC", "工行"]),
            Entity(name="银行业", type="industry"),
        ]
        names = _entity_names(entities)
        assert "工商银行" in names
        assert "icbc" in names
        assert "工行" in names
        assert "银行业" in names


class TestFindMatchingCluster:
    def test_finds_match_by_entity_overlap(self):
        from app.analysis.event_cluster import find_matching_cluster
        entities = [
            Entity(name="工商银行", type="company", aliases=[]),
            Entity(name="降息", type="policy", aliases=[]),
            Entity(name="银行业", type="industry", aliases=[]),
        ]
        existing = [EventCluster(
            cluster_id="ev_test1",
            title="降息影响银行业",
            entities=[Entity(name="降息", type="policy"), Entity(name="银行业", type="industry"), Entity(name="LPR", type="indicator")],
            news_ids=[1],
            sentiment_avg=-0.3,
            sentiment_distribution={"negative": 1},
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            significance=0.3,
        )]
        result = find_matching_cluster(entities, existing, datetime.now(timezone.utc))
        assert result is not None
        assert result.cluster_id == "ev_test1"

    def test_no_match_insufficient_overlap(self):
        from app.analysis.event_cluster import find_matching_cluster
        entities = [Entity(name="特斯拉", type="company", aliases=[])]
        existing = [EventCluster(
            cluster_id="ev_test2",
            title="银行降息",
            entities=[Entity(name="工商银行", type="company"), Entity(name="降息", type="policy")],
            news_ids=[1],
            sentiment_avg=0.0,
            sentiment_distribution={"neutral": 1},
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            significance=0.1,
        )]
        result = find_matching_cluster(entities, existing, datetime.now(timezone.utc))
        assert result is None

    def test_no_match_time_window_expired(self):
        from app.analysis.event_cluster import find_matching_cluster
        entities = [Entity(name="工商银行", type="company"), Entity(name="降息", type="policy")]
        old_time = datetime.now(timezone.utc) - timedelta(hours=50)
        existing = [EventCluster(
            cluster_id="ev_test3",
            title="旧事件",
            entities=[Entity(name="工商银行", type="company"), Entity(name="降息", type="policy")],
            news_ids=[1],
            sentiment_avg=0.0,
            sentiment_distribution={"neutral": 1},
            first_seen=old_time,
            last_seen=old_time,
            significance=0.1,
        )]
        result = find_matching_cluster(entities, existing, datetime.now(timezone.utc))
        assert result is None


class TestSignificance:
    def test_high_significance(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(8, -0.8)
        assert score >= 0.5

    def test_low_significance(self):
        from app.analysis.event_cluster import compute_significance
        score = compute_significance(1, 0.0)
        assert score < 0.3


class TestSentimentDistribution:
    def test_distribution(self):
        from app.analysis.event_cluster import compute_sentiment_distribution
        sentiments = [
            {"label": "positive"},
            {"label": "positive"},
            {"label": "negative"},
        ]
        dist = compute_sentiment_distribution(sentiments)
        assert dist["positive"] == 2
        assert dist["negative"] == 1
