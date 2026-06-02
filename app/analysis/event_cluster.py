"""Cluster news into events based on entity overlap and time window."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import deps
from app.models import Entity, EventCluster

logger = logging.getLogger(__name__)

# Minimum shared entities to merge into same cluster
MIN_SHARED_ENTITIES = 2
# Max time span within a cluster
MAX_CLUSTER_HOURS = 48


def _entity_names(entities: list[Entity]) -> set[str]:
    names = set()
    for e in entities:
        names.add(e.name.lower())
        for a in e.aliases:
            names.add(a.lower())
    return names


def find_matching_cluster(
    entities: list[Entity],
    existing_clusters: list[EventCluster],
    news_time: datetime,
) -> EventCluster | None:
    """Find an existing cluster that shares enough entities with the new news."""
    new_names = _entity_names(entities)
    if len(new_names) < 1:
        return None

    for cluster in existing_clusters:
        shared = new_names & _entity_names(cluster.entities)
        if len(shared) >= MIN_SHARED_ENTITIES:
            # Check time window
            if abs((news_time - cluster.last_seen).total_seconds()) <= MAX_CLUSTER_HOURS * 3600:
                return cluster
    return None


async def generate_cluster_title(news_titles: list[str], entities: list[Entity]) -> str:
    """Use LLM to generate a concise title for an event cluster."""
    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    titles_text = "\n".join(f"- {t}" for t in news_titles[:8])
    entity_names = ", ".join(e.name for e in entities[:5])

    prompt = (
        f"以下是关于同一事件的几条新闻标题，涉及的实体包括：{entity_names}\n"
        f"新闻标题：\n{titles_text}\n\n"
        "请用一句话（不超过20字）概括这个事件的核心主题。只返回概括，不要其他内容。"
    )

    try:
        result = await asyncio.wait_for(
            client.analyze("你是一个新闻编辑，擅长提炼事件主题。", prompt),
            timeout=10,
        )
        return result.strip().strip('"').strip()[:50]
    except Exception as e:
        logger.warning("Cluster title generation failed: %s", e)
        # Fallback: use first entity name
        return f"{entities[0].name}相关事件" if entities else "未命名事件"


def compute_significance(news_count: int, sentiment_avg: float) -> float:
    """Compute cluster significance score (0-1)."""
    # More news and stronger sentiment = more significant
    count_score = min(news_count / 10.0, 1.0) * 0.5
    sentiment_score = min(abs(sentiment_avg), 1.0) * 0.5
    return round(count_score + sentiment_score, 2)


def compute_sentiment_distribution(sentiments: list[dict]) -> dict:
    """Compute distribution of sentiment labels."""
    dist: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
    for s in sentiments:
        label = s.get("label", "neutral")
        if label in dist:
            dist[label] += 1
        else:
            dist["neutral"] += 1
    return dist


async def try_cluster(
    news_id: int,
    title: str,
    entities: list[Entity],
    sentiment_score: float,
    sentiment_label: str,
    news_time: datetime | None = None,
) -> EventCluster | None:
    """Try to add news to an existing cluster or create a new one.

    Returns the cluster if a new one was created (not if merged into existing).
    """
    if not entities or not news_id:
        return None

    news_time = news_time or datetime.now(timezone.utc)

    from app.repository import load_recent_clusters, save_event_cluster, update_cluster_add_news

    existing = await load_recent_clusters(hours=MAX_CLUSTER_HOURS)
    matched = find_matching_cluster(entities, existing, news_time)

    if matched:
        # Merge into existing cluster
        await update_cluster_add_news(
            matched.cluster_id,
            news_id,
            sentiment_score,
            sentiment_label,
            news_time,
        )
        # Update in-memory cluster
        if news_id not in matched.news_ids:
            matched.news_ids.append(news_id)
        matched.last_seen = news_time
        # Recalculate avg
        scores = [matched.sentiment_avg * (len(matched.news_ids) - 1), sentiment_score]
        matched.sentiment_avg = sum(scores) / len(matched.news_ids)
        matched.significance = compute_significance(len(matched.news_ids), matched.sentiment_avg)
        logger.info("Merged news %d into cluster %s", news_id, matched.cluster_id)
        return None

    # Create new cluster
    cluster_id = f"ev_{uuid4().hex[:12]}"
    cluster = EventCluster(
        cluster_id=cluster_id,
        title=title[:50],
        entities=entities,
        news_ids=[news_id],
        sentiment_avg=sentiment_score,
        sentiment_distribution={sentiment_label: 1},
        first_seen=news_time,
        last_seen=news_time,
        significance=compute_significance(1, sentiment_score),
    )

    # Generate a better title asynchronously
    try:
        cluster_title = await generate_cluster_title([title], entities)
        cluster.title = cluster_title
    except Exception:
        pass

    await save_event_cluster(cluster)
    logger.info("Created new cluster %s: %s", cluster_id, cluster.title)
    return cluster
