"""
Operations Cockpit SSE Broadcaster.
===================================
A lightweight, dependency-free Server-Sent Events (SSE) fan-out used to push live
operations events (HITL order pending, action-exit executed/matched, etc.) to
/console and remote clients.

Relocated here from app/monitoring/market_stream.py when the Monitor & Alert feature
(and its `app/monitoring/` engine package) was removed. Only the SSE bus — shared
infrastructure consumed by orders.py and the action-exit services — is retained.
"""

import asyncio
import logging
from typing import Dict, Any, Set
from datetime import datetime, timezone

logger = logging.getLogger("SSEBroadcaster")


class SSEBroadcaster:
    """
    Manages active Server-Sent Events (SSE) subscribers from /console and remote clients.
    """
    def __init__(self):
        self._clients: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        """Subscribes a new SSE client queue."""
        q = asyncio.Queue(maxsize=100)
        self._clients.add(q)
        logger.info(f"SSEBroadcaster: New client subscribed (Active: {len(self._clients)})")
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribes an SSE client queue."""
        if q in self._clients:
            self._clients.remove(q)
            logger.info(f"SSEBroadcaster: Client disconnected (Active: {len(self._clients)})")

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcasts a typed SSE message to all connected clients."""
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        for q in list(self._clients):
            try:
                if not q.full():
                    await q.put(payload)
            except Exception:
                pass

    # Backwards-compatible alias: several services call sse_broadcaster.broadcast(...)
    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Alias of broadcast_event() (kept for existing callers)."""
        await self.broadcast_event(event_type, data)


# Global SSE Broadcaster singleton
sse_broadcaster = SSEBroadcaster()
