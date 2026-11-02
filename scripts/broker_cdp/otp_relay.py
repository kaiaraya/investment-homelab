"""
CDP OTP relay — reuse the ORIGINAL app-level LINE relay (แบบเดิม).

Do NOT re-implement the readiness gate or the cross-process OTP poll here:
those are single-source-of-truth in app/services/otp_relay_readiness.py,
app/services/line_service.py and app/services/otp_relay_registry.py.

The CDP login scripts call these two thin helpers instead of the card
t_203d1799 parallel otp_flow.py, so LINE relay stays NON-BLOCKING: the
headed browser + manual OTP is always the safety net.

STALE-OTP GUARD: `check_line_otp_once` only accepts rows with
``SessionLog.id > since_id``. The login loop captures the watermark right
before it asks LINE for a code and advances it after every fill, so a code
left over from an earlier login (or a test) can never be typed into a fresh
OTP form — the broker counts every wrong code as a failed attempt.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select

from app.db.models import SessionLog
from app.db.session import AsyncSessionLocal
from app.services.otp_relay_registry import broker_matches, parse_otp_broker
from app.services.redaction import redact_otp

logger = logging.getLogger(__name__)

# Same single-source-of-truth regex as app/browser/auth_driver.py (LINE-RCA-002).
OTP_SESSION_LOG_PATTERN = re.compile(r"Received[^:]*OTP[^:]*:\s*([0-9]{6})")


@dataclass(frozen=True)
class OtpMatch:
    """A LINE OTP row that belongs to this broker and postdates the watermark."""

    otp: str
    row_id: int


async def latest_otp_row_id() -> int:
    """Highest LINE_OTP_RECEIVED id — the watermark to pass as ``since_id``."""
    try:
        async with AsyncSessionLocal() as db:
            v = (
                await db.execute(
                    select(func.max(SessionLog.id)).where(
                        SessionLog.event_type == "LINE_OTP_RECEIVED"
                    )
                )
            ).scalar()
        return int(v or 0)
    except Exception as e:
        logger.warning(f"[CDP OTP] watermark read failed: {e}")
        return 0


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


async def check_line_otp_once(broker: str, since_id: int = 0) -> Optional[OtpMatch]:
    """One non-blocking poll of the PRIMARY DB for a FRESH OTP for this broker.

    Mirrors auth_driver._wait_for_otp_multi_channel (check 2): reads
    `LINE_OTP_RECEIVED` rows newer than ``since_id`` and applies broker
    attribution (LINE-RCA-010), so the CDP path and the app path can never
    disagree on whose OTP. Returns None when nothing fresh has arrived.
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(SessionLog)
                .where(
                    SessionLog.event_type == "LINE_OTP_RECEIVED",
                    SessionLog.id > int(since_id),
                )
                .order_by(SessionLog.id.desc())
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
            logger.info(
                f"[CDP OTP] Got fresh LINE OTP for {broker} "
                f"(row {row.id}): {redact_otp(otp)}"
            )
            return OtpMatch(otp=otp, row_id=int(row.id))
    return None
