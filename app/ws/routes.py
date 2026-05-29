from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import deps
from app.models import Subscription, SubscriptionCommand
from app.subscription import manager as sub_manager
from app.ws.connection_manager import get_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])
ws_manager = get_manager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await ws_manager.connect(user_id, websocket)
    logger.info("WebSocket connected: %s", user_id)

    try:
        while True:
            data = await websocket.receive_json()
            try:
                cmd = SubscriptionCommand(**data)
                if cmd.action == "subscribe":
                    await sub_manager.add_subscription(user_id, cmd.keywords, cmd.threshold)
                    logger.info("User %s subscribed: %s", user_id, cmd.keywords)
                    await websocket.send_json({"type": "subscribed", "keywords": cmd.keywords})
                elif cmd.action == "unsubscribe":
                    await sub_manager.remove_subscription(user_id)
                    logger.info("User %s unsubscribed", user_id)
                    await websocket.send_json({"type": "unsubscribed"})
            except Exception as e:
                logger.warning("Invalid command from %s: %s", user_id, e)
                await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)
        logger.info("WebSocket disconnected: %s", user_id)
