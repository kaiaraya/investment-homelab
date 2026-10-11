"""
Liberator Securities session health — browser-free JWT expiry inspection.
========================================================================
LIB-RCA-006 / LIB-RCA-007: single source of truth for deciding whether a saved
`data/liberator_session.json` storage state still carries a usable auth token.

Pure & synchronous (stdlib only, no Playwright) so it can be reused by:
  1. LiberatorDriver (before launching a headed browser)
  2. scripts/preflight_check.py (before any test / trading operation)

Anti-Mock Guardrail (Invariant 1): never report a stale/expired session as valid.
"""

import base64
import json
import os
import time
from typing import Any, Dict, Optional

DEFAULT_SAFETY_MARGIN_SECONDS = 60


def read_session_token_expiry(session_path: str) -> Optional[int]:
    """
    Returns the saved Liberator auth-token expiry as Unix seconds, or None when it
    cannot be determined (so the live DOM verification path is still exercised).

    Reads the `api-token` / `ws-token` JWT cookies first, then falls back to any
    non-session cookie `expires` field (Playwright writes session cookies as -1).
    """
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
    except Exception:
        return None

    jwt_exp: Optional[int] = None
    fallback_exp: Optional[int] = None

    for c in state_data.get("cookies", []):
        name = str(c.get("name", "")).lower()
        value = str(c.get("value", ""))
        if name in ("api-token", "ws-token"):
            if value.count(".") >= 2:
                try:
                    payload_b64 = value.split(".")[1]
                    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                    exp = claims.get("exp")
                    if isinstance(exp, (int, float)):
                        jwt_exp = int(exp)
                        break
                except Exception:
                    pass
            exp_attr = c.get("expires")
            if isinstance(exp_attr, (int, float)) and exp_attr > 0:
                fallback_exp = int(exp_attr)

    return jwt_exp if jwt_exp is not None else fallback_exp


def session_expired(
    session_path: str,
    safety_margin_seconds: int = DEFAULT_SAFETY_MARGIN_SECONDS,
) -> bool:
    """
    Returns True when the saved Liberator session token is already expired, or will
    expire within ``safety_margin_seconds``.

    Returns False when the expiry cannot be determined, so that the online DOM check
    in ``LiberatorDriver.verify_saved_session()`` still runs. This prevents treating
    a remembered-but-stale (~24h) JWT cookie as a valid session (LIB-RCA-006).
    """
    exp = read_session_token_expiry(session_path)
    if exp is None:
        return False
    return exp <= int(time.time()) + safety_margin_seconds


def session_health(
    session_path: str,
    safety_margin_seconds: int = DEFAULT_SAFETY_MARGIN_SECONDS,
) -> Dict[str, Any]:
    """
    Aggregated, render-friendly view of the saved session (used by preflight).

    Shape:
        {
            "exists": bool,                  # storage-state file present on disk
            "exp": int | None,               # token expiry (Unix s); None if undeterminable
            "expired": bool,                 # True ONLY when an expiry is known & passed (within margin)
            "remaining_seconds": int | None, # exp - now (can be negative); None if undeterminable
        }
    """
    exists = os.path.exists(session_path)
    exp = read_session_token_expiry(session_path) if exists else None
    if exp is None:
        return {
            "exists": exists,
            "exp": None,
            "expired": False,
            "remaining_seconds": None,
        }

    remaining = exp - int(time.time())
    return {
        "exists": True,
        "exp": exp,
        "expired": remaining <= safety_margin_seconds,
        "remaining_seconds": remaining,
    }
