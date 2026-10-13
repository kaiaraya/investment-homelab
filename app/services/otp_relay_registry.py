"""
OTP Relay Registry — broker attribution + primary-DB pinning (LINE-RCA-010)
===========================================================================

Root cause this module fixes (2026-10-08, live evidence):

1. **Wrong database (fatal).** `webhook_line.py` depends on `get_db()`, which is
   *platform-aware* (`get_session_factory(None)` → `settings.TRADING_PLATFORM`).
   With `TRADING_PLATFORM=CLICK2WIN` the webhook wrote `LINE_OTP_RECEIVED` into
   `investment_homelab_click2win.db` while **every** driver polls the *primary*
   database (`AsyncSessionLocal`) → the row was invisible → `TIMEOUT (180s)` even
   though the operator typed the code. Proven by the orphan row in the sandbox DB
   (`id=26 LINE_OTP_RECEIVED … 922412 (Ref: N/A)`).
   The relay channel is broker-agnostic, so it is **pinned to the primary DB** here.

2. **No broker attribution.** The webhook ACK hard-coded "Krungsri Securities" and
   resolved `ref` only from `auth_driver.current_ref`, so a Liberator OTP was
   labelled Krungsri with `Ref: N/A`. Requests are now recorded as an
   `OTP_REQUESTED` marker carrying `broker=` / `ref=`; the reply echoes the broker
   that actually asked (**latest-request-wins**, operator decision 2026-10-08).

Zero-Contradiction: `auth_driver.OTP_SESSION_LOG_PATTERN` still parses the
`LINE_OTP_RECEIVED` details written here — the shape only gained a trailing
`(Broker: X)` tag. Rows without the tag (legacy / KDE) stay acceptable (lenient).

Broker Knowledge Isolation: this module only *labels* + *correlates*; it never
carries broker-specific DOM/session assumptions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select

from app.db.models import SessionLog
from app.services.redaction import redact_otp_details

logger = logging.getLogger(__name__)

# --- Event types (single source of truth for the relay channel) --------------
EVENT_OTP_REQUESTED = "OTP_REQUESTED"
EVENT_OTP_RECEIVED = "LINE_OTP_RECEIVED"

# A pending request is honoured for slightly longer than the 180s OTP wait, so a
# slow operator still gets honest attribution instead of a silent `Ref: N/A`.
DEFAULT_PENDING_TTL_SECONDS = 300

# Canonical broker labels (moved here from `line_service.push_otp_request` so the
# push and the ACK can never drift apart — Zero-Contradiction).
BROKER_LABELS = {
    "KRUNGSRI": "Krungsri TradeMan",
    "TRADEMAN": "Krungsri TradeMan",
    "LIBERATOR": "Liberator WebTrade",
    "CLICK2WIN": "Settrade Click2Win",
}

_REQUEST_BROKER_RE = re.compile(r"broker=([A-Za-z0-9_]+)")
_REQUEST_REF_RE = re.compile(r"\bref=(\S+)")
_OTP_BROKER_RE = re.compile(r"\(Broker:\s*([A-Za-z0-9_]+)\)")


# --------------------------------------------------------------------- pure ----

def broker_label(broker: Optional[str]) -> Optional[str]:
    """Human-facing label for a broker tag (`LIBERATOR` -> `Liberator WebTrade`)."""
    if not broker:
        return None
    tag = str(broker).strip()
    if not tag:
        return None
    return BROKER_LABELS.get(tag.upper(), tag)


def format_request_details(
    broker: Optional[str],
    ref: Optional[str],
    ttl_seconds: int = DEFAULT_PENDING_TTL_SECONDS,
) -> str:
    """Details string for an `OTP_REQUESTED` marker (latest-request-wins)."""
    return (
        f"OTP requested by broker={(broker or '').upper()} "
        f"ref={ref or 'N/A'} ttl={int(ttl_seconds)}s"
    )


def format_otp_details(
    otp: str,
    ref: Optional[str] = None,
    broker: Optional[str] = None,
) -> str:
    """
    Details string for a `LINE_OTP_RECEIVED` row.

    The shape stays compatible with ``auth_driver.OTP_SESSION_LOG_PATTERN`` (a
    tolerant ``Received...OTP...: NNNNNN`` regex) so the channel-gated DB waits keep
    working; the trailing ``(Broker: X)`` tag is what lets each driver ignore the
    other broker's OTP (LINE-RCA-010).
    """
    tag = f" (Broker: {broker.upper()})" if broker else ""
    return f"Received OTP 6-digits from LINE: {otp} (Ref: {ref or 'N/A'}){tag}"


def parse_request_broker(details: Optional[str]) -> Optional[str]:
    """Extract the broker tag from an `OTP_REQUESTED` marker (upper-cased)."""
    m = _REQUEST_BROKER_RE.search(details or "")
    return m.group(1).upper() if m else None


def parse_request_ref(details: Optional[str]) -> Optional[str]:
    """Extract the ref from an `OTP_REQUESTED` marker (`N/A` -> None)."""
    m = _REQUEST_REF_RE.search(details or "")
    if not m:
        return None
    val = m.group(1).strip()
    return None if val.upper() in ("N/A", "NONE", "-", "") else val


def parse_otp_broker(details: Optional[str]) -> Optional[str]:
    """
    Extract the `(Broker: X)` tag from a `LINE_OTP_RECEIVED` row.

    ``None`` means "untagged" (legacy row / KDE SMS) — callers must treat that as
    *acceptable* so historical rows keep working (lenient, never fail-closed here).
    """
    m = _OTP_BROKER_RE.search(details or "")
    return m.group(1).upper() if m else None


# Broker tags each driver accepts as "its own". Labels only — no DOM/session
# behaviour crosses brokers (Broker Knowledge Isolation).
BROKER_ALIASES: Dict[str, tuple] = {
    "KRUNGSRI": ("KRUNGSRI", "TRADEMAN"),
    "TRADEMAN": ("KRUNGSRI", "TRADEMAN"),
    "LIBERATOR": ("LIBERATOR",),
    "CLICK2WIN": ("CLICK2WIN",),
}


def broker_matches(expected: Optional[str], actual: Optional[str]) -> bool:
    """
    True when an OTP tagged `actual` may be consumed by the `expected` broker.

    * ``actual is None``  → untagged (legacy / KDE SMS) → **lenient accept**, so
      historical rows and the dormant KDE fallback keep working.
    * otherwise the tag must name the same broker (aliases allowed).
    """
    if not actual:
        return True
    exp = str(expected or "").upper()
    return str(actual).upper() in BROKER_ALIASES.get(exp, (exp,))


# ---------------------------------------------------------------- DB-backed ----

@dataclass
class PendingOtpRequest:
    """The most recent broker OTP request still inside its TTL window."""

    broker: str
    ref: Optional[str]
    label: str
    created_at: Optional[datetime] = None


def _primary_session():
    """Primary-DB session factory — imported lazily so test overrides apply."""
    from app.db.session import AsyncSessionLocal

    return AsyncSessionLocal()


async def record_request(
    broker: str,
    ref: Optional[str] = None,
    ttl_seconds: int = DEFAULT_PENDING_TTL_SECONDS,
) -> bool:
    """
    Persist an `OTP_REQUESTED` marker into the **primary** DB.

    Called by `line_service.push_otp_request()` immediately before the push, so the
    webhook can attribute the operator's reply to the broker that actually asked.
    Best-effort: a failure never aborts the login flow.
    """
    details = format_request_details(broker, ref, ttl_seconds)
    try:
        async with _primary_session() as db:
            db.add(SessionLog(event_type=EVENT_OTP_REQUESTED, details=details))
            await db.commit()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[OTP RELAY] Could not record request marker: {e}")
        return False
    logger.info(f"[OTP RELAY] pending request recorded -> {details}")
    return True


async def resolve_pending_request(
    ttl_seconds: int = DEFAULT_PENDING_TTL_SECONDS,
) -> Optional[PendingOtpRequest]:
    """
    Latest-request-wins: return the newest `OTP_REQUESTED` marker inside `ttl_seconds`.

    Returns ``None`` when there is no fresh marker (then callers fall back to
    `auth_driver.current_ref` for the legacy Krungsri-only path).
    """
    try:
        async with _primary_session() as db:
            stmt = (
                select(SessionLog)
                .where(SessionLog.event_type == EVENT_OTP_REQUESTED)
                .order_by(SessionLog.created_at.desc(), SessionLog.id.desc())
                .limit(1)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[OTP RELAY] Could not resolve pending request: {e}")
        return None

    if row is None or not row.details:
        return None

    broker = parse_request_broker(row.details)
    if not broker:
        return None

    created = row.created_at
    if created is not None:
        created_utc = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - created_utc).total_seconds()
        if age > ttl_seconds:
            logger.info(
                f"[OTP RELAY] Latest request (broker={broker}) is stale ({age:.0f}s > "
                f"{ttl_seconds}s) - not attributing this OTP."
            )
            return None

    return PendingOtpRequest(
        broker=broker,
        ref=parse_request_ref(row.details),
        label=broker_label(broker) or broker,
        created_at=created,
    )


async def record_otp_received(
    otp: str,
    ref: Optional[str] = None,
    broker: Optional[str] = None,
) -> bool:
    """
    Persist a `LINE_OTP_RECEIVED` row into the **primary** DB (LINE-RCA-010).

    This is the cross-process hand-off every driver polls — it MUST live in the same
    database the drivers read (`AsyncSessionLocal`), never the platform-aware
    `get_db()` session (that was the fatal bug).
    """
    details = format_otp_details(otp, ref, broker)
    try:
        async with _primary_session() as db:
            db.add(SessionLog(event_type=EVENT_OTP_RECEIVED, details=details))
            await db.commit()
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"[OTP RELAY] Could not persist LINE_OTP_RECEIVED row: {e}")
        return False
    logger.info(f"[OTP RELAY] LINE_OTP_RECEIVED persisted -> {redact_otp_details(details)}")
    return True

