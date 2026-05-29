from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import deps
from app.models import Subscription, SubscriptionCommand
from app.ws.connection_manager import get_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])
manager = get_manager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    logger.info("WebSocket connected: %s", user_id)

    try:
        while True:
            data = await websocket.receive_json()
            try:
                cmd = SubscriptionCommand(**data)
                if cmd.action == "subscribe":
                    sub = Subscription(
                        user_id=user_id,
                        keywords=cmd.keywords,
                        threshold=cmd.threshold,
                    )
                    deps.active_subscriptions[user_id] = sub
                    logger.info("User %s subscribed: %s", user_id, cmd.keywords)
                    await websocket.send_json({"type": "subscribed", "keywords": cmd.keywords})
                elif cmd.action == "unsubscribe":
                    deps.active_subscriptions.pop(user_id, None)
                    logger.info("User %s unsubscribed", user_id)
                    await websocket.send_json({"type": "unsubscribed"})
            except Exception as e:
                logger.warning("Invalid command from %s: %s", user_id, e)
                await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        deps.active_subscriptions.pop(user_id, None)
        logger.info("WebSocket disconnected: %s", user_id)
