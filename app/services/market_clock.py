"""Single source of truth for the negotiation (ต่อราคา) time window.

The SET negotiation window differs from the plain trading-hours window: price
negotiation is only legal between 09:55–12:30 and 14:25–16:30 (+07, Mon–Fri),
i.e. it excludes the ATO/ATC auctions at the open/close. Every caller that needs
to gate a ``/nego``-style action must ask this module, never re-derive the clock.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

_BKK = ZoneInfo("Asia/Bangkok")

#: (start, end) for the two negotiation sessions, in Bangkok local time.
_NEGO_SESSIONS = (
    (time(9, 55), time(12, 30)),
    (time(14, 25), time(16, 30)),
)


def _now_bkk(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(_BKK)
    if now.tzinfo is None:
        # A naive datetime is treated as already-Bangkok (tests pass local wall time).
        return now.replace(tzinfo=_BKK)
    return now.astimezone(_BKK)


def is_nego_window(now: Optional[datetime] = None) -> bool:
    """True when ``now`` falls inside a negotiation session (Mon–Fri, +07)."""
    bkk = _now_bkk(now)
    if bkk.weekday() >= 5:  # Saturday / Sunday
        return False
    t = bkk.time()
    return any(start <= t < end for start, end in _NEGO_SESSIONS)


def next_open_window(now: Optional[datetime] = None) -> str:
    """Human-readable Thai string naming the next negotiation window.

    Used by the "ตลาดปิด" card so the user knows when to come back without the
    caller having to compute it.
    """
    bkk = _now_bkk(now)
    t = bkk.time()

    def _next_weekday(d: datetime) -> datetime:
        nxt = d + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        return nxt

    for start, end in _NEGO_SESSIONS:
        if t < start:
            return f"เปิดอีกครั้ง {start.strftime('%H:%M')}"
    # Past the last session (or in the lunch gap) -> next weekday's first session.
    return f"พรุ่งนี้ {_NEGO_SESSIONS[0][0].strftime('%H:%M')}"


__all__ = ["is_nego_window", "next_open_window"]
