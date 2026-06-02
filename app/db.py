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

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    news_id INTEGER REFERENCES news(id),
    sentiment_id INTEGER REFERENCES sentiment(id),
    alert_level TEXT NOT NULL DEFAULT 'warning',
    triggered_keywords TEXT DEFAULT '',
    deep_analysis TEXT DEFAULT NULL,
    referenced_news TEXT DEFAULT '[]',
    -- Redundant fields for independent queries
    news_title TEXT DEFAULT '',
    news_source TEXT DEFAULT '',
    news_url TEXT DEFAULT '',
    news_snippet TEXT DEFAULT '',
    sentiment_score REAL DEFAULT 0.0,
    sentiment_label TEXT DEFAULT '',
    sentiment_confidence REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_news_hash ON news(title_hash);
CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);
CREATE INDEX IF NOT EXISTS idx_news_created ON news(created_at);
CREATE INDEX IF NOT EXISTS idx_sentiment_score ON sentiment(score);
CREATE INDEX IF NOT EXISTS idx_sentiment_processed ON sentiment(processed_at);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(alert_level);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS news_entities (
    news_id INTEGER NOT NULL REFERENCES news(id),
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    PRIMARY KEY(news_id, entity_id)
);

CREATE TABLE IF NOT EXISTS event_clusters (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    entities_json TEXT DEFAULT '[]',
    news_ids_json TEXT DEFAULT '[]',
    sentiment_avg REAL DEFAULT 0.0,
    sentiment_distribution TEXT DEFAULT '{}',
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    significance REAL DEFAULT 0.0,
    alert_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS multi_sentiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL REFERENCES news(id),
    entity_name TEXT DEFAULT '',
    fear REAL DEFAULT 0.0,
    greed REAL DEFAULT 0.0,
    optimism REAL DEFAULT 0.0,
    uncertainty REAL DEFAULT 0.0,
    dominant TEXT DEFAULT 'neutral',
    momentum REAL DEFAULT 0.0,
    momentum_shift INTEGER DEFAULT 0,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    context TEXT DEFAULT '',
    confidence REAL DEFAULT 0.5,
    news_id INTEGER REFERENCES news(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_entity, target_entity, relation, news_id)
);

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_news_entities_news ON news_entities(news_id);
CREATE INDEX IF NOT EXISTS idx_news_entities_entity ON news_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_event_clusters_significance ON event_clusters(significance);
CREATE INDEX IF NOT EXISTS idx_multi_sentiment_entity ON multi_sentiment(entity_name);
CREATE INDEX IF NOT EXISTS idx_multi_sentiment_processed ON multi_sentiment(processed_at);
CREATE INDEX IF NOT EXISTS idx_relations_source ON entity_relations(source_entity);
CREATE INDEX IF NOT EXISTS idx_relations_target ON entity_relations(target_entity);
"""

# Module-level connection (set at startup, closed at shutdown)
_db: aiosqlite.Connection | None = None


async def init_db() -> aiosqlite.Connection:
    global _db
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _migrate(_db)
    await _db.commit()
    logger.info("Database initialized at %s", DB_PATH)
    return _db


async def _migrate(db: aiosqlite.Connection):
    """Add columns to existing tables if they're missing."""
    # reports: add redundant fields for independent queries
    cols = await _get_columns(db, "reports")
    if "news_title" not in cols:
        for col, col_type in [
            ("news_title", "TEXT DEFAULT ''"),
            ("news_source", "TEXT DEFAULT ''"),
            ("news_url", "TEXT DEFAULT ''"),
            ("news_snippet", "TEXT DEFAULT ''"),
            ("sentiment_score", "REAL DEFAULT 0.0"),
            ("sentiment_label", "TEXT DEFAULT ''"),
            ("sentiment_confidence", "REAL DEFAULT 0.0"),
        ]:
            await db.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_type}")
        logger.info("Migrated reports table: added redundant fields")
    if "referenced_news" not in cols:
        await db.execute("ALTER TABLE reports ADD COLUMN referenced_news TEXT DEFAULT '[]'")
        logger.info("Migrated reports table: added referenced_news column")


async def _get_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    rows = await db.execute_fetchall(f"PRAGMA table_info({table})")
    return {row[1] for row in rows}


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
