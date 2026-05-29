import asyncio
from collections import OrderedDict

import pytest

from app import deps
from app.models import Subscription
from config.settings import Settings


@pytest.fixture(autouse=True)
def setup_deps():
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.news_queue = asyncio.Queue(maxsize=100)
    deps.scored_queue = asyncio.Queue(maxsize=100)
    deps.alert_queue = asyncio.Queue(maxsize=50)
    deps.dedup_cache = OrderedDict()
    deps.active_connections = {}
    deps.active_subscriptions = {}
    yield
    deps.active_subscriptions.clear()
    deps.dedup_cache.clear()
