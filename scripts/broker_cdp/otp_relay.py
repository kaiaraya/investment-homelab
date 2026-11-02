"""
CDP OTP relay — reuse the ORIGINAL app-level LINE relay (แบบเดิม).

Do NOT re-implement the readiness gate or the cross-process OTP poll here:
those are single-source-of-truth in app/services/otp_relay_readiness.py,
app/services/line_service.py and app/services/otp_relay_registry.py.

The CDP login scripts call these two thin helpers instead of the card
t_203d1799 parallel otp_flow.py, so LINE relay stays NON-BLOCKING: the
headed browser + manual OTP is always the safety net.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import select

from app.db.models import SessionLog
from app.db.session import AsyncSessionLocal
from app.services.otp_relay_registry import broker_matches, parse_otp_broker
from app.services.redaction import redact_otp

logger = logging.getLogger(__name__)

# Same single-source-of-truth regex as app/browser/auth_driver.py (LINE-RCA-002).
OTP_SESSION_LOG_PATTERN = re.compile(r"Received[^:]*OTP[^:]*:\s*([0-9]{6})")


async def request_line_otp(
    broker: str,
    ref: Optional[str] = None,
    timeout_seconds: int = 180,
) -> bool:
    """Best-effort: ask the operator for the OTP over LINE (original mechanism).

    Reuses otp_relay_readiness.check() + line_service.push_otp_request().
    NEVER raises, NEVER blocks login on failure — returns False so the caller
    simply keeps waiting for the manual (headed-browser) OTP.
    """
    try:
        from app.services.otp_relay_readiness import otp_relay_readiness

        readiness = await otp_relay_readiness.check()
        if not readiness.ready:
            logger.info(
                f"[CDP OTP] LINE relay not ready ({readiness.reason}); "
                "falling back to manual browser OTP."
            )
            return False
        from app.services.line_service import line_service

        pushed = await line_service.push_otp_request(
            ref=ref, broker=broker, timeout_seconds=timeout_seconds
        )
        return bool(pushed)
    except Exception as e:  # never fatal
        logger.warning(f"[CDP OTP] Could not push OTP request: {e}")
        return False


async def check_line_otp_once(broker: str) -> Optional[str]:
    """One non-blocking poll of the PRIMARY DB for this broker's LINE OTP.

    Mirrors auth_driver._wait_for_otp_multi_channel (check 2): reads
    `LINE_OTP_RECEIVED` rows and applies broker attribution (LINE-RCA-010),
    so the CDP path and the app path can never disagree on whose OTP.
    Returns the 6-digit OTP string, or None when absent/error.
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(SessionLog)
                .where(SessionLog.event_type == "LINE_OTP_RECEIVED")
                .order_by(SessionLog.created_at.desc(), SessionLog.id.desc())
                .limit(10)
            )
            rows = (await db.execute(stmt)).scalars().all()
    except Exception as e:
        logger.warning(f"[CDP OTP] DB poll failed: {e}")
        return None

    for row in rows:
        m = OTP_SESSION_LOG_PATTERN.search(row.details or "")
        if not m:
            continue
        otp = m.group(1)
        if broker_matches(broker, parse_otp_broker(row.details)):
            logger.info(f"[CDP OTP] Got LINE OTP for {broker}: {redact_otp(otp)}")
            return otp
    return None
