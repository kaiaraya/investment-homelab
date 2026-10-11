import asyncio
from typing import Any, Dict, List
from datetime import datetime, timezone


from app.schemas.auth import OTPPayload, OTPSource


class InternalEventBus:
    """
    Zero-Dependency In-Memory Event Bus & Queue.
    Acts as the high-speed bridge between the FastAPI Gateway (Phase 1)
    and Playwright Automation Workers (Phase 2 & Phase 3).
    """
    def __init__(self):
        self.order_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.otp_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.command_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.notification_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._history: List[Dict[str, Any]] = []
        self._latest_otp: Dict[str, Any] | None = None
        self._latest_otp_payload: OTPPayload | None = None

    async def publish_order(self, order_data: Dict[str, Any]) -> None:
        event = {
            "type": "ORDER_DISPATCH",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": order_data
        }
        await self.order_queue.put(event)
        self._record_history(event)

    async def publish_otp(self, otp_data: OTPPayload | Dict[str, Any]) -> OTPPayload:
        if isinstance(otp_data, OTPPayload):
            payload = otp_data
        else:
            payload = OTPPayload(**otp_data)

        event = {
            "type": "OTP_RELAY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload.model_dump(),
            "payload": payload
        }
        self._latest_otp = event
        self._latest_otp_payload = payload
        await self.otp_queue.put(event)
        self._record_history(event)
        return payload

    async def publish_command(self, command_data: Dict[str, Any]) -> None:
        event = {
            "type": "USER_COMMAND",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": command_data
        }
        await self.command_queue.put(event)
        self._record_history(event)

    async def publish_notification(self, notification_data: Dict[str, Any]) -> None:
        event = {
            "type": "NOTIFICATION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": notification_data
        }
        await self.notification_queue.put(event)
        self._record_history(event)

    def get_latest_otp(self) -> Dict[str, Any] | None:
        return self._latest_otp

    def get_latest_otp_payload(self) -> OTPPayload | None:
        return self._latest_otp_payload

    def _record_history(self, event: Dict[str, Any]) -> None:
        self._history.append(event)
        # Keep last 100 events in memory
        if len(self._history) > 100:
            self._history.pop(0)

    def get_queue_stats(self) -> Dict[str, Any]:
        return {
            "pending_orders": self.order_queue.qsize(),
            "pending_otps": self.otp_queue.qsize(),
            "pending_commands": self.command_queue.qsize(),
            "total_events_processed": len(self._history),
            "latest_events": self._history[-10:] if self._history else []
        }


# Global singleton instance
event_bus = InternalEventBus()
