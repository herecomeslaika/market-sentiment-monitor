from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path("data/sentiment.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT DEFAULT '',
    content_snippet TEXT DEFAULT '',
    title_hash TEXT NOT NULL UNIQUE,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sentiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL REFERENCES news(id),
    score REAL NOT NULL,
    label TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL REFERENCES news(id),
    sentiment_id INTEGER NOT NULL REFERENCES sentiment(id),
    alert_level TEXT NOT NULL DEFAULT 'warning',
    triggered_keywords TEXT DEFAULT '',
    deep_analysis TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id TEXT NOT NULL,
    keywords TEXT NOT NULL,
    threshold REAL NOT NULL DEFAULT -0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id)
);

CREATE INDEX IF NOT EXISTS idx_news_hash ON news(title_hash);
CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);
CREATE INDEX IF NOT EXISTS idx_news_created ON news(created_at);
CREATE INDEX IF NOT EXISTS idx_sentiment_score ON sentiment(score);
CREATE INDEX IF NOT EXISTS idx_sentiment_processed ON sentiment(processed_at);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(alert_level);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
"""

# Module-level connection (set at startup, closed at shutdown)
_db: aiosqlite.Connection | None = None


async def init_db() -> aiosqlite.Connection:
    global _db
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()
    logger.info("Database initialized at %s", DB_PATH)
    return _db


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        await init_db()
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
        logger.info("Database connection closed")
