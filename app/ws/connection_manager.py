from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from app import deps
from app.models import AlertPayload, WSMessage

logger = logging.getLogger(__name__)

# Module-level singleton shared with ws/routes.py
_manager: ConnectionManager | None = None


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        deps.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)
        deps.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: WSMessage):
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message.model_dump())
            except Exception as e:
                logger.warning("Failed to send to %s: %s", user_id, e)
                self.disconnect(user_id)

    async def broadcast_alert(self, alert: AlertPayload, target_user_ids: list[str]):
        message = WSMessage(type="alert", payload=alert.model_dump())
        for uid in target_user_ids:
            await self.send_to_user(uid, message)


def get_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def alert_pusher():
    from app.subscription.matcher import match_subscriptions
    from app.notification.dispatcher import dispatch_notification

    mgr = get_manager()
    while True:
        try:
            alert: AlertPayload = await deps.alert_queue.get()
            matched = match_subscriptions(alert)
            target_users = [sub.user_id for sub, _ in matched]

            # WebSocket push
            if target_users:
                await mgr.broadcast_alert(alert, target_users)

            # External notification channels (email, DingTalk, Feishu)
            for uid in target_users:
                try:
                    await dispatch_notification(alert, uid)
                except Exception as e:
                    logger.warning("Notification dispatch failed for %s: %s", uid, e)

            if target_users:
                logger.info("Alert pushed to %d users", len(target_users))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("alert_pusher error: %s", e, exc_info=True)
            await asyncio.sleep(1)
