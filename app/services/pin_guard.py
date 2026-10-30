# -*- coding: utf-8 -*-
"""PIN-attempt guard — the single place that knows whether we may type a trading PIN.

Why this module exists (2026-10-29 lockout, account 3024959)
------------------------------------------------------------
Every broker submit (place / cancel+replace / amend) carries the 6-digit trading PIN, and
the broker locks the account after a handful of wrong entries. Before this module the
gateway had **no** counter and no audit:

* a PIN the broker refused produced no ``orders`` row and no ``session_logs`` event
  (``execute_order_via_cdp`` returned before ``_record_order``), so nobody could answer
  "when did we type the wrong PIN";
* ``streaming_driver.execute_order`` reported ``STREAMING_ORDER_SUBMITTED`` with a
  synthetic ``STM-<epoch>`` number even when the page showed a PIN error — a false
  success that let the automation keep burning attempts;
* a JS ``alert()`` from the Settrade app was auto-dismissed by Playwright and never read.

Contract
--------
* ``classify_pin_error(text)`` — pure: does this broker message mean "wrong/suspended PIN"?
* ``check(broker)`` — may we submit *now*? (fail-closed, never raises)
* ``record_failure(broker, message)`` — count it, quarantine the broker, persist
* ``record_success(broker)`` — a proven order proves the PIN; clear the quarantine
* ``reset(broker, reason, actor)`` — human-only unlock after the PIN was fixed at the broker

State lives in ``settings.PIN_GUARD_STATE_PATH`` (``data/pin_guard.json``) so it survives
a gateway restart, and never contains the PIN itself — only an error snippet and
timestamps.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

E_PIN_REJECTED = "E_PIN_REJECTED"
E_PIN_SUSPENDED = "E_PIN_SUSPENDED"
E_PIN_GUARD = "E_PIN_GUARD"

#: Broker messages that mean the PIN itself was refused. English + Thai, because the
#: Settrade app answers in English while the Krungsri SSO/QuickTrade surface answers in Thai.
_SUSPENDED_RE = re.compile(
    r"(pin\s*(?:is|was)?\s*(?:suspend|lock|block)"
    r"|suspend\w*\s*(?:pin|user|account)"
    r"|pin\s*ถ(?:ู|ุ)ก(?:ระงับ|ล็อก|ล๊อค)"
    r"|บัญชีถ(?:ู|ุ)ก(?:ระงับ|ล็อก|ล๊อค)"
    r"|exceed\w*\s*(?:the\s*)?(?:maximum|limit|number)"
    r"|too\s*many\s*(?:attempt|time)"
    r"|เกินจำนวนครั้ง)",
    re.IGNORECASE,
)
_REJECTED_RE = re.compile(
    r"(invalid\s*pin|incorrect\s*pin|wrong\s*pin|pin\s*(?:is\s*)?(?:invalid|incorrect|wrong)"
    r"|รหัส\s*pin\s*ไม่ถูกต้อง|รหัสผ่าน\s*ไม่ถูกต้อง|pin\s*ผิด"
    r"|不正确)",
    re.IGNORECASE,
)

_HISTORY_MAX = 50
_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def classify_pin_error(text: Any) -> Optional[str]:
    """``E_PIN_SUSPENDED`` / ``E_PIN_REJECTED`` for a broker message, else ``None``.

    Suspension wins over rejection: "exceeded maximum pin attempts, pin suspended"
    matches both patterns and must be treated as the harder stop.
    """
    s = str(text or "").strip()
    if not s:
        return None
    if _SUSPENDED_RE.search(s):
        return E_PIN_SUSPENDED
    if _REJECTED_RE.search(s):
        return E_PIN_REJECTED
    return None


def is_pin_error(text: Any) -> bool:
    """True when ``text`` is a wrong/suspended PIN message."""
    return classify_pin_error(text) is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _broker_key(broker: Any) -> str:
    return str(broker or "UNKNOWN").strip().upper() or "UNKNOWN"


def _state_path() -> Path:
    raw = str(getattr(settings, "PIN_GUARD_STATE_PATH", "") or "data/pin_guard.json")
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _max_failures() -> int:
    try:
        return max(1, int(getattr(settings, "PIN_GUARD_MAX_FAILURES", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _lock_minutes() -> int:
    try:
        return max(0, int(getattr(settings, "PIN_GUARD_LOCK_MINUTES", 240) or 0))
    except (TypeError, ValueError):
        return 240


def _enabled() -> bool:
    return bool(getattr(settings, "PIN_GUARD_ENABLED", True))


def _empty_state() -> Dict[str, Any]:
    return {"version": 1, "brokers": {}}


def _load() -> Dict[str, Any]:
    p = _state_path()
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("brokers"), dict):
            return data
    except FileNotFoundError:
        return _empty_state()
    except Exception as exc:                                  # corrupted file
        logger.warning("pin_guard: state unreadable (%s: %s) — starting empty", type(exc).__name__, exc)
    return _empty_state()


def _save(state: Dict[str, Any]) -> None:
    p = _state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as exc:
        logger.warning("pin_guard: state write failed (%s: %s)", type(exc).__name__, exc)


def _entry(state: Dict[str, Any], broker: str) -> Dict[str, Any]:
    brokers = state.setdefault("brokers", {})
    ent = brokers.get(broker)
    if not isinstance(ent, dict):
        ent = {"failures": 0, "attempts": 0, "locked_until": None,
               "last_error": None, "history": []}
        brokers[broker] = ent
    ent.setdefault("failures", 0)
    ent.setdefault("attempts", 0)
    ent.setdefault("history", [])
    return ent


def _locked_until(ent: Dict[str, Any]) -> Optional[datetime]:
    raw = ent.get("locked_until")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def check(broker: Any) -> Dict[str, Any]:
    """May we submit a PIN-carrying request to ``broker`` right now?

    Returns ``{"allowed": bool, "reason": str|None, ...}``. Never raises: a guard that
    crashes must refuse (fail-closed), not open the gate.
    """
    key = _broker_key(broker)
    if not _enabled():
        return {"allowed": True, "reason": None, "enabled": False, "broker": key}
    try:
        with _LOCK:
            state = _load()
            ent = _entry(state, key)
            failures = int(ent.get("failures") or 0)
            until = _locked_until(ent)
            now = _now()
            if until and until > now:
                mins = max(1, int((until - now).total_seconds() // 60) + 1)
                return {
                    "allowed": False, "enabled": True, "broker": key,
                    "error_code": E_PIN_GUARD,
                    "failures": failures, "locked_until": until.isoformat(),
                    "last_error": ent.get("last_error"),
                    "reason": (
                        f"PIN guard: โบรกปฏิเสธ PIN {failures} ครั้ง — ระงับการส่งคำสั่ง {key} "
                        f"อีก {mins} นาที (ถึง {until:%Y-%m-%d %H:%M} UTC). "
                        f"ห้ามลองซ้ำเอง ต้องแก้ PIN กับโบรกแล้วสั่งปลดล็อก guard ก่อน "
                        f"(scripts/pin_guard.py reset {key.lower()})"
                    ),
                }
            if failures >= _max_failures():
                return {
                    "allowed": False, "enabled": True, "broker": key,
                    "error_code": E_PIN_GUARD,
                    "failures": failures,
                    "last_error": ent.get("last_error"),
                    "reason": (
                        f"PIN guard: มี PIN ที่ถูกปฏิเสธค้างอยู่ {failures} ครั้ง ({key}) — "
                        f"ต้องปลดล็อกด้วยมือหลังยืนยัน PIN กับโบรก "
                        f"(scripts/pin_guard.py reset {key.lower()})"
                    ),
                }
            return {"allowed": True, "enabled": True, "broker": key,
                    "failures": failures, "reason": None}
    except Exception as exc:                                  # never open the gate on error
        logger.warning("pin_guard.check failed (%s: %s) — refusing submit", type(exc).__name__, exc)
        return {"allowed": False, "enabled": True, "broker": key, "error_code": E_PIN_GUARD,
                "reason": f"PIN guard ทำงานผิดพลาด ({type(exc).__name__}: {exc}) — "
                          f"fail-closed ไม่ส่งคำสั่ง"}


def record_failure(broker: Any, message: Any = None, *, code: Optional[str] = None) -> Dict[str, Any]:
    """Count one broker PIN rejection and quarantine the broker."""
    key = _broker_key(broker)
    msg = str(message or "").strip()[:400]
    if not _enabled():
        return {"allowed": True, "broker": key, "enabled": False, "failures": 0}
    try:
        with _LOCK:
            state = _load()
            ent = _entry(state, key)
            ent["failures"] = int(ent.get("failures") or 0) + 1
            ent["attempts"] = int(ent.get("attempts") or 0) + 1
            ent["last_error"] = msg or None
            ent["last_failure_at"] = _now().isoformat()
            minutes = _lock_minutes()
            ent["locked_until"] = (_now() + timedelta(minutes=minutes)).isoformat() if minutes else None
            hist: List[Dict[str, Any]] = ent.setdefault("history", [])
            hist.append({"at": ent["last_failure_at"], "code": code or classify_pin_error(msg),
                         "error": msg})
            del hist[:-_HISTORY_MAX]
            _save(state)
            logger.error("pin_guard: PIN rejected for %s (failures=%s) — %s",
                         key, ent["failures"], msg[:160])
            return {"allowed": False, "broker": key, "enabled": True,
                    "failures": ent["failures"], "locked_until": ent.get("locked_until"),
                    "error_code": code or classify_pin_error(msg) or E_PIN_REJECTED,
                    "last_error": ent["last_error"]}
    except Exception as exc:
        logger.warning("pin_guard.record_failure failed (%s: %s)", type(exc).__name__, exc)
        return {"allowed": False, "broker": key, "enabled": True, "failures": 1,
                "error_code": E_PIN_GUARD, "last_error": msg or None}


def record_success(broker: Any) -> Dict[str, Any]:
    """A broker-accepted order proves the PIN — clear failures and the quarantine."""
    key = _broker_key(broker)
    try:
        with _LOCK:
            state = _load()
            ent = _entry(state, key)
            ent["failures"] = 0
            ent["locked_until"] = None
            ent["last_success_at"] = _now().isoformat()
            ent["attempts"] = int(ent.get("attempts") or 0) + 1
            _save(state)
        return {"allowed": True, "broker": key, "failures": 0}
    except Exception as exc:
        logger.warning("pin_guard.record_success failed (%s: %s)", type(exc).__name__, exc)
        return {"allowed": True, "broker": key, "failures": 0}


def reset(broker: Any, *, reason: str = "", actor: str = "human") -> Dict[str, Any]:
    """Human-only unlock after the PIN was confirmed/reset at the broker.

    Never call this from an automation path — it exists to hand the decision back to a
    person once the broker-side cause is fixed.
    """
    key = _broker_key(broker)
    with _LOCK:
        state = _load()
        ent = _entry(state, key)
        prev = {"failures": ent.get("failures"), "locked_until": ent.get("locked_until")}
        ent["failures"] = 0
        ent["locked_until"] = None
        hist: List[Dict[str, Any]] = ent.setdefault("history", [])
        hist.append({"at": _now().isoformat(), "code": "RESET", "error": reason or None,
                     "actor": actor, "previous": prev})
        del hist[:-_HISTORY_MAX]
        _save(state)
    logger.warning("pin_guard: reset %s by %s (%s)", key, actor, reason or "no reason given")
    return {"broker": key, "failures": 0, "locked_until": None, "previous": prev}


def status(broker: Any = None) -> Dict[str, Any]:
    """Read-only view for /status, MCP and CLI diagnostics."""
    with _LOCK:
        state = _load()
    brokers = state.get("brokers") or {}
    if broker:
        key = _broker_key(broker)
        return {"enabled": _enabled(), "max_failures": _max_failures(),
                "lock_minutes": _lock_minutes(), "broker": key,
                "state": brokers.get(key) or {}}
    return {"enabled": _enabled(), "max_failures": _max_failures(),
            "lock_minutes": _lock_minutes(), "brokers": brokers}
