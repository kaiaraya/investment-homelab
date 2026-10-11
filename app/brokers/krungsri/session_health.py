"""
Krungsri Securities (TradeMan) session health — browser-free session-file inspection.
====================================================================================
KSS-RCA-011 / LIB-RCA-007: single source of truth for deciding whether the saved
`data/session_state.json` Playwright storage state is even worth reusing.

Why this module exists
----------------------
TradeMan's SSO cookies are *session cookies* (Playwright writes ``expires: -1``), so there
is **no offline JWT ``exp``** to decode like Liberator's ``api-token`` (LIB-RCA-006). The
only browser-free signal is the **storage-state file's age** plus its presence:

  * file missing            -> a fresh headed login + 2FA SMS OTP is REQUIRED
  * file present but stale  -> (older than a trading day) treat as EXPIRED, warn the user
  * file present and recent -> reuse is worth attempting (live DOM check at connect)

Pure & synchronous (stdlib only, no Playwright) so it can be reused by:
  1. app.mcp.pillars.pillar1_session.session_get_health  (MCP health payload)
  2. scripts/preflight_check.py                          (pre-flight reporting)
  3. app.browser.session_sentinel.SessionSentinel        (background transition watch)

Anti-Mock Guardrail (root_cause_and_escalation.md, Invariant 1): never report a
missing/expired session as "ready" — callers must surface ``needs_fresh_login``.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict

# TradeMan SSO sessions do not survive a full trading day. Anything older than this is
# treated as EXPIRED for reporting purposes (the live DOM check still decides reuse).
DEFAULT_MAX_AGE_HOURS = 12.0

# Verdict reasons (stable strings — tests + runbooks assert on them).
REASON_MISSING = "MISSING"
REASON_STALE = "STALE"
REASON_RECENT = "RECENT"


def session_file_info(
    path: str,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> Dict[str, Any]:
    """
    Aggregated, render-friendly view of the saved Krungsri storage state.

    Shape:
        {
            "exists": bool,             # storage-state file present on disk
            "mtime": float | None,      # file mtime (Unix s); None if missing
            "mtime_iso": str | None,    # human-readable local mtime
            "age_seconds": float | None,# now - mtime; None if missing
            "age_hours": float | None,  # age in hours; None if missing
            "cookie_count": int,        # best-effort cookie count (0 if unreadable)
            "needs_fresh_login": bool,  # True => fresh headed login + OTP REQUIRED
            "reason": str,              # MISSING | STALE | RECENT
        }
    """
    if not os.path.exists(path):
        return {
            "exists": False,
            "mtime": None,
            "mtime_iso": None,
            "age_seconds": None,
            "age_hours": None,
            "cookie_count": 0,
            "needs_fresh_login": True,
            "reason": REASON_MISSING,
        }

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None

    age_seconds = None if mtime is None else max(0.0, time.time() - mtime)
    age_hours = None if age_seconds is None else age_seconds / 3600.0
    mtime_iso = (
        None
        if mtime is None
        else datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    )

    cookie_count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookie_count = len(data.get("cookies", []) or [])
    except Exception:
        # Unreadable/corrupt state -> presence alone cannot be trusted.
        cookie_count = 0

    needs_fresh_login = age_hours is None or age_hours > max_age_hours

    return {
        "exists": True,
        "mtime": mtime,
        "mtime_iso": mtime_iso,
        "age_seconds": age_seconds,
        "age_hours": age_hours,
        "cookie_count": cookie_count,
        "needs_fresh_login": needs_fresh_login,
        "reason": REASON_STALE if needs_fresh_login else REASON_RECENT,
    }


def session_needs_fresh_login(
    path: str,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> bool:
    """Convenience predicate: True when a fresh headed login is required."""
    return bool(session_file_info(path, max_age_hours=max_age_hours)["needs_fresh_login"])
