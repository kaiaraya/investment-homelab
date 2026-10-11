import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.ai.memory import agent_memory
from app.services.line_service import line_service
from app.services.kdeconnect_service import kdeconnect_service

logger = logging.getLogger(__name__)


class KillSwitchService:
    """
    Emergency Kill Switch & Safety Guardian Service:
    Provides an instantaneous circuit breaker to freeze all autonomous trading,
    abort incoming orders, cancel active unmatched orders, and alert the user.
    """

    def __init__(self):
        self._is_active: bool = False
        self._activated_at: Optional[str] = None
        self._reason: Optional[str] = None
        self._triggered_by: Optional[str] = None

    def is_active(self) -> bool:
        """Returns True if the Emergency Kill Switch is currently triggered."""
        return self._is_active

    async def activate(self, reason: str = "Manual User Panic Trigger", triggered_by: str = "USER") -> Dict[str, Any]:
        """
        Activates the Emergency Kill Switch:
        1. Freezes autonomous agent trading.
        2. Automatically purges/cancels all open orders on broker.
        3. Sends broadcast alerts to LINE and KDE Connect.
        4. Logs the emergency event in SQLite audit memory.
        """
        self._is_active = True
        self._activated_at = datetime.now(timezone.utc).isoformat()
        self._reason = reason
        self._triggered_by = triggered_by

        agent_memory.set_working_key("system_kill_switch", True)

        logger.critical(f"🚨 EMERGENCY KILL SWITCH ACTIVATED! Triggered by [{triggered_by}]: {reason}")

        # 1. Emergency Order Cancellation
        cancelled_orders_result = {}
        try:
            from app.services.eod_service import eod_service
            cancelled_orders_result = await eod_service.cancel_all_pending_orders()
            logger.info("Emergency Kill Switch: Successfully requested cancellation of all open orders.")
        except Exception as exc:
            logger.error(f"Error cancelling orders during Kill Switch activation: {exc}")
            cancelled_orders_result = {"error": str(exc)}

        # 2. Broadcast High-Priority Push Alerts
        alert_text = (
            f"🚨 [EMERGENCY KILL SWITCH ACTIVATED]\n"
            f"Triggered By: {triggered_by}\n"
            f"Reason: {reason}\n"
            f"Time: {self._activated_at}\n"
            f"Action: All trading frozen. Open orders cancelled."
        )

        try:
            await line_service.send_text_message(alert_text)
        except Exception as line_err:
            logger.warning(f"Failed to dispatch Kill Switch LINE message: {line_err}")

        try:
            await kdeconnect_service.send_notification(
                title="🚨 KILL SWITCH ACTIVATED",
                body=f"Trading frozen: {reason}",
            )
        except Exception as kde_err:
            logger.warning(f"Failed to dispatch Kill Switch KDE Connect notification: {kde_err}")

        # 3. Persistent Memory Audit Log
        payload = {
            "status": "KILL_SWITCH_ACTIVE",
            "activated_at": self._activated_at,
            "triggered_by": triggered_by,
            "reason": reason,
            "cancelled_orders": cancelled_orders_result,
        }

        await agent_memory.log_decision(
            agent_name="KillSwitchService",
            action_type="KILL_SWITCH_ACTIVATED",
            thought=f"Emergency freeze initiated: {reason}",
            output_result=payload,
            is_success=True,
        )

        return payload

    async def reset(self, authorized_by: str = "USER") -> Dict[str, Any]:
        """
        Resets the Emergency Kill Switch and returns the system to ready state.
        """
        if not self._is_active:
            return {"status": "ALREADY_INACTIVE", "message": "Kill Switch is not active."}

        self._is_active = False
        reset_time = datetime.now(timezone.utc).isoformat()
        agent_memory.set_working_key("system_kill_switch", False)

        logger.info(f"Emergency Kill Switch RESET by [{authorized_by}] at {reset_time}.")

        reset_msg = (
            f"✅ [KILL SWITCH RESET]\n"
            f"Authorized By: {authorized_by}\n"
            f"Time: {reset_time}\n"
            f"Status: Normal trading operations restored."
        )

        try:
            await line_service.send_text_message(reset_msg)
        except Exception as line_err:
            logger.warning(f"Failed to dispatch Kill Switch reset message: {line_err}")

        payload = {
            "status": "KILL_SWITCH_RESET",
            "reset_at": reset_time,
            "authorized_by": authorized_by,
        }

        await agent_memory.log_decision(
            agent_name="KillSwitchService",
            action_type="KILL_SWITCH_RESET",
            thought=f"System normal operations restored by {authorized_by}",
            output_result=payload,
            is_success=True,
        )

        return payload

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state of the Kill Switch."""
        return {
            "is_active": self._is_active,
            "activated_at": self._activated_at,
            "reason": self._reason,
            "triggered_by": self._triggered_by,
        }


# Global singleton instance
kill_switch_service = KillSwitchService()
