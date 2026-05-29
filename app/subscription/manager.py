from __future__ import annotations

from app import deps
from app.models import Subscription


def add_subscription(sub: Subscription) -> None:
    deps.active_subscriptions[sub.user_id] = sub


def remove_subscription(user_id: str) -> None:
    deps.active_subscriptions.pop(user_id, None)


def get_subscription(user_id: str) -> Subscription | None:
    return deps.active_subscriptions.get(user_id)


def list_subscriptions() -> list[Subscription]:
    return list(deps.active_subscriptions.values())
