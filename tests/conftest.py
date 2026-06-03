"""Shared test fixtures and configuration."""
import asyncio
from collections import OrderedDict

import aiosqlite
import pytest

from app import deps
from app.db import SCHEMA
from app.models import Subscription
from config.settings import Settings


@pytest.fixture(autouse=True)
def setup_deps():
    """Initialize deps with test settings and clean state for every test."""
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.news_queue = asyncio.Queue(maxsize=100)
    deps.scored_queue = asyncio.Queue(maxsize=100)
    deps.alert_queue = asyncio.Queue(maxsize=50)
    deps.dedup_cache = OrderedDict()
    deps.active_connections = {}
    deps.active_subscriptions = {}
    deps.sources = {}
    yield
    deps.active_subscriptions.clear()
    deps.dedup_cache.clear()
    deps.sources = {}


@pytest.fixture
async def db():
    """Provide an in-memory SQLite database with full schema."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
async def seeded_db(db):
    """Provide a DB with sample news, sentiment, and subscription data."""
    # Insert news
    await db.execute(
        "INSERT INTO news (source, title, title_hash, content_snippet) VALUES (?, ?, ?, ?)",
        ("新浪财经-A股", "央行宣布降息25个基点", "hash1", "人民银行宣布下调LPR利率"),
    )
    await db.execute(
        "INSERT INTO news (source, title, title_hash, content_snippet) VALUES (?, ?, ?, ?)",
        ("CNBC", "Fed signals rate cut in September", "hash2", "The Federal Reserve hinted at a possible rate cut."),
    )
    await db.execute(
        "INSERT INTO news (source, title, title_hash, content_snippet) VALUES (?, ?, ?, ?)",
        ("东方财富", "股市大涨突破3500点", "hash3", "A股市场今日大幅上涨"),
    )
    await db.commit()

    # Get inserted news IDs
    news_rows = await db.execute_fetchall("SELECT id FROM news ORDER BY id")
    n1, n2, n3 = [r["id"] for r in news_rows]

    # Insert sentiment
    await db.execute(
        "INSERT INTO sentiment (news_id, score, label, confidence) VALUES (?, ?, ?, ?)",
        (n1, -0.5, "negative", 0.85),
    )
    await db.execute(
        "INSERT INTO sentiment (news_id, score, label, confidence) VALUES (?, ?, ?, ?)",
        (n2, 0.7, "positive", 0.9),
    )
    await db.execute(
        "INSERT INTO sentiment (news_id, score, label, confidence) VALUES (?, ?, ?, ?)",
        (n3, 0.8, "positive", 0.75),
    )
    await db.commit()

    # Insert entities
    await db.execute(
        "INSERT INTO entities (name, type, aliases) VALUES (?, ?, ?)",
        ("央行", "policy", '["人民银行","PBOC"]'),
    )
    await db.execute(
        "INSERT INTO entities (name, type, aliases) VALUES (?, ?, ?)",
        ("LPR", "indicator", '["贷款市场报价利率"]'),
    )
    await db.execute(
        "INSERT INTO entities (name, type, aliases) VALUES (?, ?, ?)",
        ("美联储", "policy", '["Fed"]'),
    )
    await db.commit()

    entity_rows = await db.execute_fetchall("SELECT id FROM entities ORDER BY id")
    e1, e2, e3 = [r["id"] for r in entity_rows]

    # Link entities to news
    await db.execute("INSERT INTO news_entities (news_id, entity_id) VALUES (?, ?)", (n1, e1))
    await db.execute("INSERT INTO news_entities (news_id, entity_id) VALUES (?, ?)", (n1, e2))
    await db.execute("INSERT INTO news_entities (news_id, entity_id) VALUES (?, ?)", (n2, e3))
    await db.commit()

    # Insert multi_sentiment
    await db.execute(
        "INSERT INTO multi_sentiment (news_id, entity_name, fear, greed, optimism, uncertainty, dominant) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (n1, "央行", 0.7, 0.1, 0.1, 0.8, "fear"),
    )
    await db.execute(
        "INSERT INTO multi_sentiment (news_id, entity_name, fear, greed, optimism, uncertainty, dominant) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (n2, "美联储", 0.1, 0.6, 0.7, 0.3, "optimism"),
    )
    await db.commit()

    # Insert subscription
    await db.execute(
        "INSERT INTO subscriptions (user_id, keywords, threshold) VALUES (?, ?, ?)",
        ("test_user", '["降息","利率"]', -0.5),
    )
    await db.commit()

    yield db, {"n1": n1, "n2": n2, "n3": n3, "e1": e1, "e2": e2, "e3": e3}


@pytest.fixture
async def api_client():
    """Provide an httpx AsyncClient for testing API endpoints."""
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_rss():
    """Provide sample RSS XML for parser tests."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Fed signals rate cut in September</title>
      <link>https://example.com/fed-rate-cut</link>
      <description>The Federal Reserve hinted at a possible rate cut amid slowing inflation.</description>
      <pubDate>Mon, 02 Jun 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Nvidia stock hits all-time high</title>
      <link>https://example.com/nvidia-ath</link>
      <description>Nvidia shares surged after announcing new AI chip lineup.</description>
      <pubDate>Mon, 02 Jun 2026 13:00:00 GMT</pubDate>
    </item>
    <item>
      <title></title>
      <link>https://example.com/empty</link>
      <description>Should be skipped</description>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def sample_news_items():
    """Provide sample NewsItem objects for tests."""
    from app.models import NewsItem
    return [
        NewsItem(source="新浪财经-A股", title="央行宣布降息25个基点", url="", content_snippet="人民银行宣布下调LPR利率", title_hash="hash1"),
        NewsItem(source="CNBC", title="Fed signals rate cut in September", url="https://example.com", content_snippet="Rate cut hints", title_hash="hash2"),
        NewsItem(source="东方财富", title="股市大涨突破3500点", url="", content_snippet="A股大幅上涨", title_hash="hash3"),
    ]