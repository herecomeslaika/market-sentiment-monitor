from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime

from app.db import get_db

logger = logging.getLogger(__name__)


async def save_news(item) -> int | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO news (source, title, url, content_snippet, title_hash, published_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (item.source, item.title, item.url, item.content_snippet,
             item.title_hash, item.published_at.isoformat() if item.published_at else None),
        )
        await db.commit()
        if cursor.lastrowid and cursor.lastrowid > 0:
            return cursor.lastrowid
        # Row already exists, fetch its id
        row = await db.execute_fetchall(
            "SELECT id FROM news WHERE title_hash = ?", (item.title_hash,)
        )
        return row[0][0] if row else None
    except Exception as e:
        logger.error("save_news error: %s", e)
        return None


async def save_sentiment(news_id: int, result) -> int | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO sentiment (news_id, score, label, confidence, processed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (news_id, result.score, result.label, result.confidence,
             result.processed_at.isoformat() if result.processed_at else None),
        )
        await db.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error("save_sentiment error: %s", e)
        return None


async def save_alert(news_id: int, sentiment_id: int, alert) -> int | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO alerts (news_id, sentiment_id, alert_level, triggered_keywords, deep_analysis)
               VALUES (?, ?, ?, ?, ?)""",
            (news_id, sentiment_id, alert.alert_level,
             json.dumps(alert.triggered_keywords, ensure_ascii=False),
             alert.deep_analysis),
        )
        await db.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error("save_alert error: %s", e)
        return None


async def query_news(limit: int = 50, offset: int = 0, source: str | None = None):
    db = await get_db()
    if source:
        rows = await db.execute_fetchall(
            "SELECT * FROM news WHERE source = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (source, limit, offset),
        )
    else:
        rows = await db.execute_fetchall(
            "SELECT * FROM news ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    return [dict(row) for row in rows]


async def load_news_by_id(news_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM news WHERE id = ?", (news_id,))
    if not rows:
        return None
    return dict(rows[0])


async def query_sentiment_history(hours: int = 24):
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT s.score, s.label, s.confidence, s.processed_at, n.title, n.source
           FROM sentiment s JOIN news n ON s.news_id = n.id
           WHERE s.processed_at >= datetime('now', ?)
           ORDER BY s.processed_at DESC""",
        (f"-{hours} hours",),
    )
    return [dict(row) for row in rows]


async def query_alert_history(limit: int = 50, offset: int = 0, level: str | None = None):
    db = await get_db()
    if level:
        rows = await db.execute_fetchall(
            """SELECT a.*, n.title, n.source, n.url, s.score, s.label, s.confidence
               FROM alerts a
               JOIN news n ON a.news_id = n.id
               JOIN sentiment s ON a.sentiment_id = s.id
               WHERE a.alert_level = ?
               ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
            (level, limit, offset),
        )
    else:
        rows = await db.execute_fetchall(
            """SELECT a.*, n.title, n.source, n.url, s.score, s.label, s.confidence
               FROM alerts a
               JOIN news n ON a.news_id = n.id
               JOIN sentiment s ON a.sentiment_id = s.id
               ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )
    return [dict(row) for row in rows]


async def query_sentiment_trend(hours: int = 24, interval_minutes: int = 30):
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT
             strftime('%Y-%m-%d %H:%M', processed_at) as time_bucket,
             AVG(score) as avg_score,
             COUNT(*) as count,
             MIN(score) as min_score,
             MAX(score) as max_score
           FROM sentiment
           WHERE processed_at >= datetime('now', ?)
           GROUP BY time_bucket
           ORDER BY time_bucket""",
        (f"-{hours} hours",),
    )
    return [dict(row) for row in rows]


async def query_keyword_stats(hours: int = 24):
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT triggered_keywords, alert_level, COUNT(*) as count
           FROM alerts
           WHERE created_at >= datetime('now', ?)
           GROUP BY triggered_keywords, alert_level
           ORDER BY count DESC
           LIMIT 20""",
        (f"-{hours} hours",),
    )
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["triggered_keywords"] = json.loads(r["triggered_keywords"])
        except (json.JSONDecodeError, TypeError):
            pass
        results.append(r)
    return results


async def cleanup_old_data(days: int = 30):
    db = await get_db()
    cutoff = f"-{days} days"
    await db.execute(
        "DELETE FROM alerts WHERE created_at < datetime('now', ?)", (cutoff,)
    )
    await db.execute(
        "DELETE FROM sentiment WHERE processed_at < datetime('now', ?)", (cutoff,)
    )
    await db.execute(
        "DELETE FROM news WHERE created_at < datetime('now', ?)", (cutoff,)
    )
    await db.commit()
    logger.info("Cleaned up data older than %d days", days)


# ---------- Subscription Persistence ----------

async def save_subscription(user_id: str, keywords: list[str], threshold: float):
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO subscriptions (user_id, keywords, threshold)
           VALUES (?, ?, ?)""",
        (user_id, json.dumps(keywords, ensure_ascii=False), threshold),
    )
    await db.commit()


async def delete_subscription(user_id: str):
    db = await get_db()
    await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    await db.commit()


async def load_subscriptions() -> dict:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT user_id, keywords, threshold FROM subscriptions")
    result = {}
    for row in rows:
        r = dict(row)
        try:
            r["keywords"] = json.loads(r["keywords"])
        except (json.JSONDecodeError, TypeError):
            r["keywords"] = []
        result[r["user_id"]] = r
    return result


# ---------- Report Persistence ----------

async def save_report(report_id: str, alert, news_id: int | None = None, sentiment_id: int | None = None, referenced_news: list[dict] | None = None):
    db = await get_db()
    ref_json = json.dumps(referenced_news or [], ensure_ascii=False)
    await db.execute(
        """INSERT OR REPLACE INTO reports
           (id, news_id, sentiment_id, alert_level, triggered_keywords, deep_analysis,
            news_title, news_source, news_url, news_snippet,
            sentiment_score, sentiment_label, sentiment_confidence, referenced_news)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (report_id, news_id, sentiment_id, alert.alert_level,
         json.dumps(alert.triggered_keywords, ensure_ascii=False),
         alert.deep_analysis,
         alert.news_item.title, alert.news_item.source,
         alert.news_item.url, alert.news_item.content_snippet,
         alert.sentiment.score, alert.sentiment.label, alert.sentiment.confidence,
         ref_json),
    )
    await db.commit()


async def load_report(report_id: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM reports WHERE id = ?", (report_id,))
    if not rows:
        return None
    r = dict(rows[0])
    try:
        r["triggered_keywords"] = json.loads(r["triggered_keywords"])
    except (json.JSONDecodeError, TypeError):
        r["triggered_keywords"] = []
    try:
        r["referenced_news"] = json.loads(r.get("referenced_news", "[]"))
    except (json.JSONDecodeError, TypeError):
        r["referenced_news"] = []
    return r


async def query_reports(limit: int = 20, offset: int = 0, level: str | None = None):
    db = await get_db()
    if level:
        rows = await db.execute_fetchall(
            """SELECT id, alert_level, triggered_keywords, deep_analysis, created_at,
                      news_title, news_source, news_url, news_snippet,
                      sentiment_score, sentiment_label, sentiment_confidence, referenced_news
               FROM reports WHERE alert_level = ?
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (level, limit, offset),
        )
    else:
        rows = await db.execute_fetchall(
            """SELECT id, alert_level, triggered_keywords, deep_analysis, created_at,
                      news_title, news_source, news_url, news_snippet,
                      sentiment_score, sentiment_label, sentiment_confidence, referenced_news
               FROM reports
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["triggered_keywords"] = json.loads(r["triggered_keywords"])
        except (json.JSONDecodeError, TypeError):
            r["triggered_keywords"] = []
        results.append(r)
    return results


# ---------- Entity Persistence ----------

async def save_entities(news_id: int, entities) -> list[int]:
    db = await get_db()
    entity_ids = []
    for entity in entities:
        aliases_json = json.dumps(entity.aliases, ensure_ascii=False)
        # Upsert entity
        await db.execute(
            """INSERT OR IGNORE INTO entities (name, type, aliases) VALUES (?, ?, ?)""",
            (entity.name, entity.type, aliases_json),
        )
        row = await db.execute_fetchall(
            "SELECT id FROM entities WHERE name = ? AND type = ?",
            (entity.name, entity.type),
        )
        if row:
            eid = row[0][0]
            # Update aliases if entity already existed
            await db.execute(
                "UPDATE entities SET aliases = ? WHERE id = ?",
                (aliases_json, eid),
            )
            # Link news to entity
            await db.execute(
                "INSERT OR IGNORE INTO news_entities (news_id, entity_id) VALUES (?, ?)",
                (news_id, eid),
            )
            entity_ids.append(eid)
    await db.commit()
    return entity_ids


async def load_entities_for_news(news_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT e.id, e.name, e.type, e.aliases
           FROM entities e
           JOIN news_entities ne ON ne.entity_id = e.id
           WHERE ne.news_id = ?""",
        (news_id,),
    )
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["aliases"] = json.loads(r["aliases"])
        except (json.JSONDecodeError, TypeError):
            r["aliases"] = []
        results.append(r)
    return results


async def load_entities_for_news_items(news_ids: list[int]) -> list[dict]:
    """Load all distinct entities associated with multiple news items."""
    if not news_ids:
        return []
    db = await get_db()
    placeholders = ",".join("?" * len(news_ids))
    rows = await db.execute_fetchall(
        f"""SELECT DISTINCT e.id, e.name, e.type, e.aliases
            FROM entities e
            JOIN news_entities ne ON ne.entity_id = e.id
            WHERE ne.news_id IN ({placeholders})""",
        news_ids,
    )
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["aliases"] = json.loads(r["aliases"])
        except (json.JSONDecodeError, TypeError):
            r["aliases"] = []
        results.append(r)
    return results


async def query_hot_entities(limit: int = 20) -> list[dict]:
    """Get most frequently referenced entities."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT e.id, e.name, e.type, e.aliases, COUNT(ne.news_id) as news_count
           FROM entities e
           JOIN news_entities ne ON ne.entity_id = e.id
           GROUP BY e.id
           ORDER BY news_count DESC
           LIMIT ?""",
        (limit,),
    )
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["aliases"] = json.loads(r["aliases"])
        except (json.JSONDecodeError, TypeError):
            r["aliases"] = []
        results.append(r)
    return results


async def query_entity_timeline(entity_name: str, hours: int = 168) -> list[dict]:
    """Get sentiment timeline for a specific entity."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT n.id, n.title, n.source, n.created_at, s.score, s.label, s.confidence
           FROM news n
           JOIN news_entities ne ON ne.news_id = n.id
           JOIN entities e ON e.id = ne.entity_id
           LEFT JOIN sentiment s ON s.news_id = n.id
           WHERE (e.name = ? OR e.aliases LIKE ?)
           AND n.created_at >= datetime('now', ?)
           ORDER BY n.created_at DESC""",
        (entity_name, f'%"{entity_name}"%', f"-{hours} hours"),
    )
    return [dict(row) for row in rows]


# ---------- Event Cluster Persistence ----------

async def save_event_cluster(cluster) -> None:
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO event_clusters
           (id, title, entities_json, news_ids_json, sentiment_avg,
            sentiment_distribution, first_seen, last_seen, significance, alert_sent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (cluster.cluster_id, cluster.title,
         json.dumps([{"name": e.name, "type": e.type} for e in cluster.entities], ensure_ascii=False),
         json.dumps(cluster.news_ids),
         cluster.sentiment_avg,
         json.dumps(cluster.sentiment_distribution, ensure_ascii=False),
         cluster.first_seen.isoformat() if cluster.first_seen else None,
         cluster.last_seen.isoformat() if cluster.last_seen else None,
         cluster.significance),
    )
    await db.commit()


async def load_recent_clusters(hours: int = 48) -> list:
    """Load recent event clusters."""
    from app.models import Entity, EventCluster
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT * FROM event_clusters
           WHERE last_seen >= datetime('now', ?)
           ORDER BY significance DESC""",
        (f"-{hours} hours",),
    )
    results = []
    for row in rows:
        r = dict(row)
        try:
            entities_data = json.loads(r.get("entities_json", "[]"))
            r["entities"] = [Entity(**e) for e in entities_data]
        except (json.JSONDecodeError, TypeError):
            r["entities"] = []
        try:
            r["news_ids"] = json.loads(r.get("news_ids_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["news_ids"] = []
        try:
            r["sentiment_distribution"] = json.loads(r.get("sentiment_distribution", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["sentiment_distribution"] = {}
        results.append(EventCluster(
            cluster_id=r["id"],
            title=r.get("title", ""),
            entities=r["entities"],
            news_ids=r["news_ids"],
            sentiment_avg=r.get("sentiment_avg", 0.0),
            sentiment_distribution=r["sentiment_distribution"],
            first_seen=r.get("first_seen", ""),
            last_seen=r.get("last_seen", ""),
            significance=r.get("significance", 0.0),
        ))
    return results


async def update_cluster_add_news(cluster_id: str, news_id: int, sentiment_score: float, sentiment_label: str, news_time) -> None:
    """Add a news item to an existing cluster."""
    db = await get_db()
    row = await db.execute_fetchall("SELECT news_ids_json, sentiment_distribution FROM event_clusters WHERE id = ?", (cluster_id,))
    if not row:
        return
    r = dict(row[0])
    try:
        news_ids = json.loads(r.get("news_ids_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        news_ids = []
    try:
        dist = json.loads(r.get("sentiment_distribution", "{}"))
    except (json.JSONDecodeError, TypeError):
        dist = {}

    if news_id not in news_ids:
        news_ids.append(news_id)
    dist[sentiment_label] = dist.get(sentiment_label, 0) + 1

    # Recalculate average
    count = len(news_ids)
    old_avg_row = await db.execute_fetchall("SELECT sentiment_avg FROM event_clusters WHERE id = ?", (cluster_id,))
    old_avg = dict(old_avg_row[0])["sentiment_avg"] if old_avg_row else 0.0
    new_avg = (old_avg * (count - 1) + sentiment_score) / count if count > 0 else sentiment_score

    significance = min(count / 10.0, 1.0) * 0.5 + min(abs(new_avg), 1.0) * 0.5

    await db.execute(
        """UPDATE event_clusters
           SET news_ids_json = ?, sentiment_avg = ?, sentiment_distribution = ?,
               last_seen = ?, significance = ?
           WHERE id = ?""",
        (json.dumps(news_ids), new_avg, json.dumps(dist, ensure_ascii=False),
         news_time.isoformat() if news_time else None, round(significance, 2), cluster_id),
    )
    await db.commit()


async def query_event_clusters(limit: int = 20, offset: int = 0) -> list[dict]:
    """Query event clusters for API."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT id, title, entities_json, news_ids_json, sentiment_avg,
                  sentiment_distribution, first_seen, last_seen, significance, alert_sent
           FROM event_clusters
           ORDER BY significance DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["entities"] = json.loads(r.get("entities_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["entities"] = []
        try:
            r["news_ids"] = json.loads(r.get("news_ids_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["news_ids"] = []
        try:
            r["sentiment_distribution"] = json.loads(r.get("sentiment_distribution", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["sentiment_distribution"] = {}
        results.append(r)
    return results


# ---------- Multi-Sentiment Persistence ----------

async def save_multi_sentiment(ms) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO multi_sentiment
           (news_id, entity_name, fear, greed, optimism, uncertainty, dominant, momentum, momentum_shift)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ms.news_id, ms.entity_name, ms.fear, ms.greed, ms.optimism,
         ms.uncertainty, ms.dominant, ms.momentum, 1 if ms.momentum_shift else 0),
    )
    await db.commit()


async def load_last_multi_sentiment(entity_name: str) -> dict | None:
    """Load the most recent multi-sentiment for an entity."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT fear, greed, optimism, uncertainty, dominant
           FROM multi_sentiment
           WHERE entity_name = ?
           ORDER BY processed_at DESC LIMIT 1""",
        (entity_name,),
    )
    if not rows:
        return None
    return dict(rows[0])


async def query_multi_sentiment_history(hours: int = 24, limit: int = 50) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT ms.*, n.title, n.source
           FROM multi_sentiment ms
           JOIN news n ON n.id = ms.news_id
           WHERE ms.processed_at >= datetime('now', ?)
           ORDER BY ms.processed_at DESC LIMIT ?""",
        (f"-{hours} hours", limit),
    )
    return [dict(row) for row in rows]


async def query_momentum_shifts(hours: int = 24, limit: int = 20) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT ms.*, n.title, n.source
           FROM multi_sentiment ms
           JOIN news n ON n.id = ms.news_id
           WHERE ms.momentum_shift = 1
           AND ms.processed_at >= datetime('now', ?)
           ORDER BY ms.processed_at DESC LIMIT ?""",
        (f"-{hours} hours", limit),
    )
    return [dict(row) for row in rows]


async def query_entity_multi_sentiment(entity_name: str, hours: int = 168) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT ms.*, n.title
           FROM multi_sentiment ms
           JOIN news n ON n.id = ms.news_id
           WHERE ms.entity_name = ?
           AND ms.processed_at >= datetime('now', ?)
           ORDER BY ms.processed_at DESC""",
        (entity_name, f"-{hours} hours"),
    )
    return [dict(row) for row in rows]


# ---------- Entity Relation Persistence ----------

async def save_relations(relations: list, news_id: int) -> None:
    db = await get_db()
    for r in relations:
        await db.execute(
            """INSERT OR IGNORE INTO entity_relations
               (source_entity, target_entity, relation, context, confidence, news_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (r.source, r.target, r.relation, r.context, r.confidence, news_id),
        )
    await db.commit()


async def load_relations_for_context(entity_names: list[str], limit: int = 20) -> list[dict]:
    """Load relations involving any of the given entities."""
    if not entity_names:
        return []
    db = await get_db()
    placeholders = ",".join("?" * len(entity_names))
    rows = await db.execute_fetchall(
        f"""SELECT DISTINCT source_entity, target_entity, relation, context, confidence
            FROM entity_relations
            WHERE source_entity IN ({placeholders}) OR target_entity IN ({placeholders})
            ORDER BY confidence DESC LIMIT ?""",
        entity_names + entity_names + [limit],
    )
    return [dict(row) for row in rows]


async def query_entity_relations(entity_name: str | None = None, limit: int = 50) -> list[dict]:
    db = await get_db()
    if entity_name:
        rows = await db.execute_fetchall(
            """SELECT source_entity, target_entity, relation, context, confidence, news_id, created_at
               FROM entity_relations
               WHERE source_entity = ? OR target_entity = ?
               ORDER BY confidence DESC LIMIT ?""",
            (entity_name, entity_name, limit),
        )
    else:
        rows = await db.execute_fetchall(
            """SELECT source_entity, target_entity, relation, context, confidence, news_id, created_at
               FROM entity_relations
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
    return [dict(row) for row in rows]
