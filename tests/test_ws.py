"""Tests for WebSocket connection manager."""
import pytest

from app.ws.connection_manager import ConnectionManager, get_manager


class FakeWS:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)


class TestConnectionManager:
    def test_get_manager_singleton(self):
        m1 = get_manager()
        m2 = get_manager()
        assert m1 is m2

    async def test_connect_and_disconnect(self):
        manager = ConnectionManager()
        ws = FakeWS()
        await manager.connect("user1", ws)
        assert "user1" in manager.active_connections

        manager.disconnect("user1")
        assert "user1" not in manager.active_connections

    async def test_send_to_user(self):
        manager = ConnectionManager()
        ws = FakeWS()
        await manager.connect("user1", ws)
        from app.models import WSMessage
        msg = WSMessage(type="test", payload={"key": "value"})
        await manager.send_to_user("user1", msg)
        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "test"

    async def test_send_to_nonexistent_user(self):
        manager = ConnectionManager()
        from app.models import WSMessage
        msg = WSMessage(type="test", payload={})
        await manager.send_to_user("nobody", msg)

    async def test_broadcast(self):
        manager = ConnectionManager()
        ws1 = FakeWS()
        ws2 = FakeWS()
        await manager.connect("u1", ws1)
        await manager.connect("u2", ws2)

        await manager.broadcast({"type": "sentiment", "payload": {"score": 0.5}})
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1

    async def test_broadcast_removes_disconnected(self):
        manager = ConnectionManager()

        class BadWS:
            async def accept(self):
                pass
            async def send_json(self, data):
                raise Exception("Connection lost")

        await manager.connect("bad_user", BadWS())
        await manager.broadcast({"type": "test"})
        assert "bad_user" not in manager.active_connections
