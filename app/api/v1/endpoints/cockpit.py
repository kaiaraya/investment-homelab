"""
Operations Cockpit Live-Event Stream (SSE).
===========================================
Serves the shared, relocated SSE bus (`app.core.sse_broadcaster`) to the Operations
Cockpit (/console) and remote clients.

This endpoint replaces the former `GET /api/v1/monitoring/stream`, which was deleted
together with the Monitor & Alert feature (and its `app/monitoring/` engine package).
The event *producers* are unchanged and remain live:
  - app/api/v1/endpoints/orders.py           -> "hitl_order_pending"
  - app/services/action_exit_dispatcher.py   -> "action_exit_executed" / "action_exit_matched"
  - app/services/action_exit_service.py      -> action-exit lifecycle events
"""

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.core.sse_broadcaster import sse_broadcaster

logger = logging.getLogger("CockpitStream")

router = APIRouter()

# Keep-alive cadence: emit an SSE comment so proxies/browsers do not drop an idle stream.
_KEEPALIVE_SECONDS = 15.0


@router.get("/stream", summary="Operations Cockpit Server-Sent Events stream")
async def cockpit_stream(request: Request) -> EventSourceResponse:
    """
    Streams live operations events (HITL order pending, action-exit executed/matched)
    to the Operations Cockpit and remote clients.
    """

    async def event_generator():
        queue = sse_broadcaster.subscribe()
        try:
            yield {"event": "connected", "data": json.dumps({"status": "COCKPIT_STREAM_READY"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message: Dict[str, Any] = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield {"comment": "keep-alive"}
                    continue
                yield {
                    "event": message.get("type", "message"),
                    "data": json.dumps(message.get("data", {}), ensure_ascii=False),
                }
        finally:
            sse_broadcaster.unsubscribe(queue)

    return EventSourceResponse(event_generator())
