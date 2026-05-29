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

async def save_report(report_id: str, alert, news_id: int | None = None, sentiment_id: int | None = None):
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO reports (id, news_id, sentiment_id, alert_level, triggered_keywords, deep_analysis)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (report_id, news_id, sentiment_id, alert.alert_level,
         json.dumps(alert.triggered_keywords, ensure_ascii=False),
         alert.deep_analysis),
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
    return r
