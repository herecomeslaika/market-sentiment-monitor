from __future__ import annotations

import logging

from app import deps
from app.models import Subscription
from app import repository

logger = logging.getLogger(__name__)


async def add_subscription(user_id: str, keywords: list[str], threshold: float = -0.5) -> Subscription:
    sub = Subscription(user_id=user_id, keywords=keywords, threshold=threshold)
    deps.active_subscriptions[user_id] = sub
    await repository.save_subscription(user_id, keywords, threshold)
    logger.info("Subscription added: user=%s keywords=%s", user_id, keywords)
    return sub


async def remove_subscription(user_id: str) -> bool:
    if user_id in deps.active_subscriptions:
        del deps.active_subscriptions[user_id]
        await repository.delete_subscription(user_id)
        logger.info("Subscription removed: user=%s", user_id)
        return True
    return False


def get_subscription(user_id: str) -> Subscription | None:
    return deps.active_subscriptions.get(user_id)


def list_subscriptions() -> dict[str, Subscription]:
    return dict(deps.active_subscriptions)


async def load_subscriptions_from_db():
    rows = await repository.load_subscriptions()
    for user_id, data in rows.items():
        deps.active_subscriptions[user_id] = Subscription(
            user_id=user_id,
            keywords=data["keywords"],
            threshold=data["threshold"],
        )
    if rows:
        logger.info("Loaded %d subscriptions from DB", len(rows))
