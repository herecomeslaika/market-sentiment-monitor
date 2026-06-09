"""Tests for subscription manager (with DB persistence)."""
import asyncio
import os
import tempfile

import pytest

from app import deps
from app.models import Subscription


@pytest.fixture(autouse=True)
async def setup_db():
    import app.db as db_mod
    old_path = db_mod.DB_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        db_mod.DB_PATH = type(old_path)(tmpdir) / "test.db"
        try:
            from app.db import init_db, close_db
            await init_db()
            deps.active_subscriptions = {}
            yield
        finally:
            await close_db()
            db_mod.DB_PATH = old_path


class TestSubscriptionManager:
    @pytest.mark.integration
    async def test_add_subscription(self):
        from app.subscription.manager import add_subscription
        sub = await add_subscription("u1", ["美联储"], -0.5)
        assert sub.user_id == "u1"
        assert "美联储" in sub.keywords
        assert "u1" in deps.active_subscriptions

    @pytest.mark.integration
    async def test_remove_subscription(self):
        from app.subscription.manager import add_subscription, remove_subscription
        await add_subscription("u1", ["比特币"], -0.3)
        removed = await remove_subscription("u1")
        assert removed is True
        assert "u1" not in deps.active_subscriptions

    @pytest.mark.integration
    async def test_remove_nonexistent(self):
        from app.subscription.manager import remove_subscription
        removed = await remove_subscription("nobody")
        assert removed is False

    @pytest.mark.integration
    async def test_persist_and_load(self):
        from app.subscription.manager import add_subscription, load_subscriptions_from_db
        await add_subscription("u1", ["降息"], -0.6)
        # Clear in-memory
        deps.active_subscriptions = {}
        assert "u1" not in deps.active_subscriptions
        # Reload from DB
        await load_subscriptions_from_db()
        assert "u1" in deps.active_subscriptions
        assert "降息" in deps.active_subscriptions["u1"].keywords

    @pytest.mark.integration
    async def test_list_subscriptions(self):
        from app.subscription.manager import add_subscription, list_subscriptions
        await add_subscription("u1", ["A"], -0.5)
        await add_subscription("u2", ["B"], -0.3)
        all_subs = list_subscriptions()
        assert len(all_subs) == 2
