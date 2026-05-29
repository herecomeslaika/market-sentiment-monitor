from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

from fastapi import WebSocket

from app.models import Subscription

if TYPE_CHECKING:
    from config.settings import Settings
    from app.crawler.sources import SourceConfig, default_sources

# Configuration (set at startup)
settings: Settings | None = None

# In-memory queues
news_queue: asyncio.Queue | None = None
scored_queue: asyncio.Queue | None = None
alert_queue: asyncio.Queue | None = None

# Dedup cache: title_hash -> timestamp
dedup_cache: OrderedDict[str, float] = OrderedDict()

# Process pool for FinBERT
finbert_pool: ProcessPoolExecutor | None = None

# WebSocket connections: user_id -> WebSocket
active_connections: dict[str, WebSocket] = {}

# Subscriptions: user_id -> Subscription
active_subscriptions: dict[str, Subscription] = {}

# News sources: source_key -> SourceConfig
sources: dict[str, SourceConfig] = {}

# Background tasks (tracked for graceful shutdown)
background_tasks: list[asyncio.Task] = []
