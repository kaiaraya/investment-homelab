# -*- coding: utf-8 -*-
"""B.6 — LIVE order executor over the CDP gateway (``execute_order_via_cdp``).

This is the only module in the gateway allowed to move money. It fills the broker's
real order ticket in the *already-open* Chrome tab (the human-witnessed session owned by
``scripts/broker_cdp/session_daemon.py``), submits it, reads the exchange order number
**off the screen**, records it in ``orders`` and then triggers the manual-order sync so a
human's own orders and the bot's stay in one ledger.

Sequence (per the B.6 card)::

    kill-switch → normalise → validator (odd-lot / tick / value / strict short uptick G6)
    → SBL borrow check (SHORT) → PIN present → DRY_RUN guard → lock+tab (manager.get_tab)
    → account switch+verify (SHORT/COVER → margin) → fill symbol/side/vol/price → PIN
    → Anti-DW symbol/volume/price re-read → submit → confirm modal → read NEW order no
    → record ``orders`` → trigger ``sync_orders_from_cdp``

Guardrails that are load-bearing (do not weaken without a witness):

* **DRY_RUN_MODE** — ``settings.DRY_RUN_MODE`` (default ``True``) stops the flow *after*
  validation and *before* anything is typed into the ticket. The tab is opened read-only
  for a selector/account preflight and the result is ``status="DRY_RUN"`` with
  ``broker_order_no=None``. Nothing is submitted, no ``orders`` row is written.
  ``bypass_dry_run=True`` exists for the human-witnessed session only.
* **Anti-Mock** — an order number is only ever the NEW ledger row that matches
  symbol+side+volume+price and was not present before submit. If it can't be read the
  result is ``status="UNCONFIRMED"`` and the row is recorded with
  ``status="UNCONFIRMED"`` / ``broker_order_no=None``. We never invent an order number
  (contrast: ``streaming_driver._scrape_order_no`` falls back to ``STM-<ts>``).
* **Account assertion** — before submit the header account is re-read; a mismatch aborts
  (a SHORT placed on the Cash account, or a BUY on Margin by accident, is never sent).
* **Ledger readability** — the ledger snapshot is taken *before* submit; if it cannot be
  read the order is refused rather than submitted unverifiable.
* **G6 strict short uptick** — a SHORT requires ``last_trade_price``; without a quote the
  call is rejected (``E_NO_QUOTE``) instead of skipping the uptick rule.

Broker slugs: ``kss`` (Settrade Streaming via Krungsri SSO) and ``lib`` / ``liberator``
(Liberator WebTrade — BUY/SELL only, cash account; Short/Cover is unsupported there).
Selectors come from the probe contract
``docs/handoff/TASK-loop1-b0a-order-entry-contract.md``.

NOTE: ``manager.get_tab`` holds a non-reentrant per-``(broker, target)`` lock. Never call
another ``get_tab``/``scrape_*``/``sync_*`` helper *inside* the ``async with get_tab(...)``
block — this module reads the ledger through the passed ``page`` for exactly that reason
and only triggers ``sync_orders_from_cdp`` after the block exits.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import session as db_session
from app.db.models import Order, SBLBorrowLot, SessionLog
from app.services import pin_guard
from app.services.broker_cdp import sync_service
from app.services.broker_cdp.manager import get_tab
from app.services.validator import validator

logger = logging.getLogger("broker_cdp_order_executor")

# --------------------------------------------------------------------------- #
# Broker metadata — gateway slug -> CDP slug / DB broker / target tab / PIN key
# --------------------------------------------------------------------------- #
_BROKER_META: Dict[str, Dict[str, Any]] = {
    "kss": {
        "cdp": "kss",
        "broker": "KRUNGSRI",
        "target": "streaming",
        "pin_key": "KRUNGSRI_PIN",
        "sides": ("BUY", "SELL", "SHORT", "COVER"),
    },
    "lib": {
        "cdp": "liberator",
        "broker": "LIBERATOR",
        "target": "portfolio",
        "pin_key": "LIBERATOR_PIN",
        "sides": ("BUY", "SELL"),          # WebTrade footer ticket is cash buy/sell only
    },
    "liberator": {
        "cdp": "liberator",
        "broker": "LIBERATOR",
        "target": "portfolio",
        "pin_key": "LIBERATOR_PIN",
        "sides": ("BUY", "SELL"),
    },
}

#: Canonical side ⇄ ledger/radio letter. ``H``/``C`` match both the Streaming radios and
#: the QuickTrade side letters (probe-confirmed).
_SIDE_ALIASES: Dict[str, str] = {
    "B": "BUY", "BUY": "BUY", "LONG": "BUY",
    "S": "SELL", "SELL": "SELL",
    "H": "SHORT", "SHORT": "SHORT", "SS": "SHORT", "SHORTSELL": "SHORT",
    "C": "COVER", "COVER": "COVER",
}

#: Human-readable side letters for logging/audit (never sent to the DOM directly).
_SIDE_LETTER: Dict[str, str] = {"BUY": "B", "SELL": "S", "SHORT": "H", "COVER": "C"}

# --- Settrade Streaming (port 9333, target "streaming") --------------------- #
KSS_SIDE_RADIOS: Dict[str, Sequence[str]] = {
    "BUY": ("input#equity-place-order-buy-radio-button",
            "label[for='equity-place-order-buy-radio-button']", "#equity-place-order-buy-radio-button"),
    "SELL": ("input#equity-place-order-sell-radio-button",
             "label[for='equity-place-order-sell-radio-button']", "#equity-place-order-sell-radio-button"),
    "SHORT": ("input#equity-place-order-short-radio-button",
              "label[for='equity-place-order-short-radio-button']", "#equity-place-order-short-radio-button"),
    "COVER": ("input#equity-place-order-cover-radio-button",
              "label[for='equity-place-order-cover-radio-button']", "#equity-place-order-cover-radio-button"),
}
KSS_SYMBOL: Sequence[str] = ("input[placeholder='Symbol']",)
KSS_VOLUME: Sequence[str] = ("input[name='equity-place-order-vol']", "input[placeholder='Volume']")
KSS_PRICE: Sequence[str] = ("input[name='price-input']", "input[placeholder='Price']")
KSS_PIN: Sequence[str] = ("#pin", "input[placeholder='PIN']")
KSS_SUBMIT: Sequence[str] = ("button:has-text('Submit')", "button:has-text('Send')")
#: The real Streaming submit button is **labelled with the side name** (``Buy`` / ``Sell`` /
#: ``Short`` / ``Cover``) and carries ``bg-color-<side>-20`` — verified live 2026-10-21.
#: A fresh, side-less ticket still renders the literal "Submit", so keep both fallbacks:
#: matching only "Submit" made every live submit fail with ``E_SUBMIT_FAILED``.
KSS_SUBMIT_BY_SIDE: Dict[str, Sequence[str]] = {
    side: (f"button.bg-color-{side.lower()}-20",) + tuple(KSS_SUBMIT)
    for side in ("BUY", "SELL", "SHORT", "COVER")
}
KSS_CONFIRM: Sequence[str] = ("button:has-text('Confirm')", "button:has-text('ยืนยัน')",
                              "button:has-text('OK')")
#: The Order Confirmation modal (ReactModal, ``[role=dialog]``) repeats the side name on its
#: accept button ("Cover"/"Buy"/...) next to "Cancel" — live-verified 2026-10-21. Without the
#: side-labelled selector the modal is never accepted and the order silently stays unsent.
KSS_CONFIRM_BY_SIDE: Dict[str, Sequence[str]] = {
    side: (f"[role=dialog] button:has-text('{label}')",
           "[role=dialog] button:has-text('Confirm')",
           "[role=dialog] button:has-text('ยืนยัน')",
           "[role=dialog] button:has-text('OK')") + tuple(KSS_CONFIRM)
    for side, label in (("BUY", "Buy"), ("SELL", "Sell"), ("SHORT", "Short"), ("COVER", "Cover"))
}
#: Any visible modal currently blocking the ticket.
_DIALOG_JS = """() => !!document.querySelector('[role=dialog]')"""
KSS_ACCOUNT_TRIGGER: Sequence[str] = ("div.position-relative.cursor-pointer", "span.outline-none")

# --- Liberator WebTrade (port 9334, target "portfolio", footer ticket) ------ #
LIB_SIDE_TOGGLES: Dict[str, Sequence[str]] = {
    "BUY": ("button:has-text('Buy')", ":text('Buy')"),
    "SELL": ("button:has-text('Sell')", ":text('Sell')"),
}
LIB_SYMBOL: Sequence[str] = ("#SearchSymbolList-setBuySellFooter",)
LIB_VOLUME: Sequence[str] = ("#volume",)
LIB_PRICE: Sequence[str] = ("#price",)
LIB_PIN: Sequence[str] = ("#pin",)
LIB_SUBMIT: Sequence[str] = ("#buttonSubmit", "button:has-text('Submit')")
LIB_CONFIRM: Sequence[str] = ("button:has-text('Confirm')", "button:has-text('ยืนยัน')",
                              "#confirmDialogActiveButton")

#: ``span.outline-none`` showing "3024959 (Equity)" -> "3024959".
_ACTIVE_ACCOUNT_JS = """() => {
  const clean = s => (s == null ? '' : String(s).trim());
  for (const s of document.querySelectorAll('span.outline-none')) {
    const m = clean(s.innerText).match(/\\b(\\d{7})\\b/);
    if (m) return m[1];
  }
  return '';
}"""

#: SET continuous-session windows in Bangkok local time (advisory only — the broker is
#: the authority; a pre-open submit is reported as a warning, never silently dropped).
_MARKET_WINDOWS: Tuple[Tuple[int, int], ...] = ((9 * 60 + 55, 12 * 60 + 30), (14 * 60 + 25, 16 * 60 + 30))

#: Error codes (stable — the receipt card / CLI maps these to Thai messages).
E_BAD_BROKER = "E_BAD_BROKER"
E_BAD_SIDE = "E_BAD_SIDE"
E_UNSUPPORTED_SIDE = "E_UNSUPPORTED_SIDE"
E_BAD_ORDER = "E_BAD_ORDER"
E_KILL_SWITCH = "E_KILL_SWITCH"
E_VALIDATOR = "E_VALIDATOR"
E_NO_QUOTE = "E_NO_QUOTE"
E_NO_SBL = "E_NO_SBL"
E_NO_PIN = "E_NO_PIN"
E_BAD_PIN = "E_BAD_PIN"
E_NO_TAB = "E_NO_TAB"
E_TICKET_INCOMPLETE = "E_TICKET_INCOMPLETE"
E_WRONG_ACCOUNT = "E_WRONG_ACCOUNT"
E_LEDGER_UNREADABLE = "E_LEDGER_UNREADABLE"
E_ANTI_DW = "E_ANTI_DW"
E_SUBMIT_FAILED = "E_SUBMIT_FAILED"
E_CONFIRM_FAILED = "E_CONFIRM_FAILED"
E_ORDER_NO_UNREADABLE = "E_ORDER_NO_UNREADABLE"
#: The broker refused the trading PIN (wrong PIN or a suspended PIN). Recorded, counted by
#: ``app.services.pin_guard`` and never returned as a silent failure (2026-10-29 lockout).
E_PIN_REJECTED = "E_PIN_REJECTED"
E_PIN_SUSPENDED = "E_PIN_SUSPENDED"
#: The guard refuses to type a PIN at all — the broker is quarantined until a human resets.
E_PIN_GUARD = "E_PIN_GUARD"

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,20}$")


# --------------------------------------------------------------------------- #
# Pure helpers (unit-testable without a browser or a DB)
# --------------------------------------------------------------------------- #
def normalise_side(side: Any) -> Optional[str]:
    """``"h"``/``"Short-Sell"``/``"Cover(M)"`` -> canonical side; unknown -> ``None``."""
    raw = re.sub(r"\([^)]*\)", " ", str(side or ""))        # drop a "(M)" matched marker
    s = re.sub(r"[^A-Za-z]", "", raw).upper()
    return _SIDE_ALIASES.get(s)


def resolve_broker(broker: Any) -> Optional[Dict[str, Any]]:
    """Gateway slug -> broker metadata dict, or ``None`` for an unknown slug."""
    return _BROKER_META.get(str(broker or "").strip().lower())


def resolve_pin(broker: str, pin: Optional[str] = None) -> Optional[str]:
    """6-digit PIN from the caller or the broker's ``.env`` key; ``None`` if absent/invalid."""
    meta = resolve_broker(broker)
    if meta is None:
        return None
    raw = pin if pin is not None else getattr(settings, meta["pin_key"], "")
    p = str(raw or "").strip()
    return p if re.fullmatch(r"\d{6}", p) else None


def market_window_warning(now: Optional[datetime] = None) -> Optional[str]:
    """Advisory: is the current Bangkok time inside a SET continuous session?"""
    now_bkk = (now or datetime.now(timezone.utc)).astimezone()
    if now_bkk.weekday() in (5, 6):
        return f"ตลาดปิด (เสาร์-อาทิตย์) — ส่งได้เฉพาะจันทร์-ศุกร์ · เวลา {now_bkk:%H:%M} (+07)"
    minutes = now_bkk.hour * 60 + now_bkk.minute
    if any(start <= minutes <= end for start, end in _MARKET_WINDOWS):
        return None
    return (f"นอกเวลาเทรด continuous (09:55–12:30 / 14:25–16:30) — เวลา {now_bkk:%H:%M} (+07) · "
            f"คำสั่งอาจถูก reject/รอเปิดตลาด")


def format_price(price: float) -> str:
    """Ticket price text — 2 decimals (SET tick sizes never need more)."""
    return f"{float(price):.2f}"


def _bno_sort_key(bno: str) -> Tuple[int, int, str]:
    """Sort order numbers numerically when numeric, else keep them last (len, int, text)."""
    digits = bno if bno.isdigit() else ""
    return (1 if digits else 0, int(digits) if digits else 0, bno)


def match_new_order_no(
    orders: Sequence[Dict[str, Any]],
    *,
    symbol: str,
    side: str,
    volume: int,
    price: float,
    known: Sequence[str],
) -> Optional[str]:
    """Newest ledger row that matches this order and was NOT in the pre-submit snapshot.

    Anti-Mock: symbol+side+volume+price must all match exactly; an unreadable price or a
    zero volume never matches. Returns ``None`` when nothing proves the submit landed.
    """
    known_set = {str(b).strip() for b in known}
    side_c = normalise_side(side)
    candidates: List[str] = []
    for o in orders:
        bno = str(o.get("broker_order_no") or "").strip()
        if not bno or bno in known_set:
            continue
        if str(o.get("symbol") or "").strip().upper() != str(symbol).strip().upper():
            continue
        if sync_service.map_ledger_side(o.get("side")) != side_c:
            continue
        if int(o.get("volume") or 0) != int(volume):
            continue
        row_price = o.get("price")
        if row_price is None or abs(float(row_price) - float(price)) > 1e-6:
            continue
        candidates.append(bno)
    return max(candidates, key=_bno_sort_key) if candidates else None


def _result_fail(code: str, message: str, *, status: str = "REJECTED",
                 broker: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    """Pre-submit refusal (``status="REJECTED"``) or post-submit ambiguity."""
    payload: Dict[str, Any] = {
        "success": False,
        "status": status,
        "error_code": code,
        "error": message,
        "submitted": False,
        "broker_order_no": None,
        "order_id": None,
    }
    if broker:
        payload["broker"] = broker
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------- #
# Broker message capture — a JS alert() proves what the app said; the ledger cannot
# --------------------------------------------------------------------------- #
class _DialogCapture:
    """Collect JS ``alert``/``confirm`` texts raised on a page while we act on it.

    Playwright auto-dismisses an unhandled dialog, which is exactly how
    "Your pin is suspended" vanished without a trace on 2026-10-29. Attaching a handler
    both records the text and stops a later ``evaluate`` from hanging on the blocked page.
    """

    def __init__(self) -> None:
        self.messages: List[str] = []
        self.attached = False

    def _handler(self, dialog: Any) -> None:      # pragma: no cover - live browser only
        try:
            self.messages.append(str(getattr(dialog, "message", "") or ""))
        except Exception:
            pass
        try:
            asyncio.get_event_loop().create_task(dialog.dismiss())
        except Exception as exc:
            logger.debug("dialog dismiss failed: %s: %s", type(exc).__name__, exc)

    @property
    def text(self) -> str:
        return " | ".join(m for m in self.messages if m)

    @property
    def pin_error(self) -> Optional[str]:
        """The first captured message that means "wrong/suspended PIN", if any."""
        for msg in self.messages:
            if pin_guard.is_pin_error(msg):
                return msg
        return None


def _install_dialog_capture(page: Any) -> _DialogCapture:
    cap = _DialogCapture()
    try:
        page.on("dialog", cap._handler)
        cap.attached = True
    except Exception as exc:
        logger.debug("dialog capture unavailable (%s: %s)", type(exc).__name__, exc)
    return cap


def _detach_dialog_capture(page: Any, cap: Optional[_DialogCapture]) -> None:
    if cap is None or not cap.attached:
        return
    for meth in ("remove_listener", "off"):
        fn = getattr(page, meth, None)
        if callable(fn):
            try:
                fn("dialog", cap._handler)
                return
            except Exception:
                continue


async def _log_session_event(db: AsyncSession, event_type: str, details: str) -> None:
    """Best-effort ``session_logs`` row — a logging failure never eats the order result."""
    try:
        db.add(SessionLog(event_type=str(event_type)[:64], details=str(details)[:1000]))
        await db.commit()
    except Exception as exc:
        logger.warning("session_logs insert failed (%s): %s", event_type, exc)


# --------------------------------------------------------------------------- #
# DOM helpers (thin — every broker-specific selector lives in an ``async def``)
# --------------------------------------------------------------------------- #
async def _first_visible(page: Any, selectors: Sequence[str]) -> Tuple[Any, Optional[str]]:
    """First visible element from ``selectors`` (element, selector) or ``(None, None)``."""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
        except Exception:
            continue
        if el is None:
            continue
        try:
            visible = await el.is_visible()
        except Exception:
            visible = True
        if visible:
            return el, sel
    return None, None


async def _read_value(page: Any, selectors: Sequence[str]) -> Optional[str]:
    """Current text of the first visible matching input (``None`` if unreadable)."""
    el, _sel = await _first_visible(page, selectors)
    if el is None:
        return None
    try:
        return (await el.input_value()) or ""
    except Exception:
        return None


async def _fill(page: Any, selectors: Sequence[str], text: str) -> Tuple[bool, Optional[str]]:
    """Fill the first visible input; ``(False, selector)`` when the field is missing."""
    el, sel = await _first_visible(page, selectors)
    if el is None:
        return False, None
    try:
        await el.click()
    except Exception:
        pass
    try:
        await el.fill(text)
    except Exception as exc:  # pragma: no cover - Playwright-level failure
        logger.warning("fill(%r) failed: %s", text, exc)
        return False, sel
    try:
        await page.wait_for_timeout(150)
    except Exception:
        pass
    return True, sel


async def _click_first(page: Any, selectors: Sequence[str]) -> bool:
    el, _sel = await _first_visible(page, selectors)
    if el is None:
        return False
    try:
        await el.click()
    except Exception:
        try:
            await el.click(force=True)
        except Exception:
            return False
    return True


async def _dialog_open(page: Any) -> bool:
    """True when a modal (``[role=dialog]`` — e.g. Order Confirmation) is on screen."""
    try:
        return bool(await page.evaluate(_DIALOG_JS))
    except Exception:
        return False


async def _confirm_modal(page: Any, side: str, attempts: int = 5, delay_ms: int = 600) -> Optional[bool]:
    """Accept the Order Confirmation modal that follows Submit.

    ``True`` — the accept button was clicked. ``None`` — no modal ever appeared (nothing to
    confirm). ``False`` — a modal is on screen but its accept button could not be found, so
    the caller must NOT assume the order was sent (live failure mode, 2026-10-21).
    """
    for attempt in range(max(1, attempts)):
        if await _click_first(page, KSS_CONFIRM_BY_SIDE[side]):
            return True
        if not await _dialog_open(page):
            if attempt == 0:
                # give the app a beat to raise the modal before calling it "no modal"
                try:
                    await page.wait_for_timeout(delay_ms)
                except Exception:
                    await asyncio.sleep(delay_ms / 1000.0)
                continue
            return None
        try:
            await page.wait_for_timeout(delay_ms)
        except Exception:
            await asyncio.sleep(delay_ms / 1000.0)
    return False


async def _active_kss_account(page: Any) -> Optional[str]:
    """7-digit account shown in the Streaming header, or ``None`` when unreadable."""
    try:
        raw = await page.evaluate(_ACTIVE_ACCOUNT_JS)
    except Exception:
        return None
    m = re.search(r"\b(\d{7})\b", str(raw or ""))
    return m.group(1) if m else None


async def _kss_switch_account(page: Any, account_no: str) -> bool:
    """Switch the header account dropdown to ``account_no`` and verify the header moved."""
    current = await _active_kss_account(page)
    if current == account_no:
        return True
    if not await _click_first(page, KSS_ACCOUNT_TRIGGER):
        return False
    try:
        await page.wait_for_timeout(500)
    except Exception:
        pass
    if not await _click_first(page, (f"li:has-text('{account_no}')", f"text={account_no}")):
        return False
    try:
        await page.wait_for_timeout(1500)
    except Exception:
        pass
    return await _active_kss_account(page) == account_no


async def _ledger_snapshot(page: Any, cdp: str) -> Tuple[bool, set, str]:
    """Read the order ledger *before* submit → (readable, {order_no}, note)."""
    try:
        raw = await page.evaluate(
            sync_service._KSS_ORDER_LEDGER_JS if cdp == "kss" else sync_service._LIBERATOR_ORDER_LEDGER_JS
        )
    except Exception as exc:
        return False, set(), f"ledger evaluate failed: {type(exc).__name__}: {exc}"
    if not isinstance(raw, dict):
        return False, set(), "ledger evaluate returned no payload"
    try:
        rows = raw.get("rows") or []
        orders = (sync_service._parse_kss_order_rows(rows) if cdp == "kss"
                  else sync_service._parse_liberator_order_rows(rows))
    except Exception as exc:
        return False, set(), f"ledger parse failed: {type(exc).__name__}: {exc}"
    return True, {str(o.get("broker_order_no") or "").strip() for o in orders if o.get("broker_order_no")}, \
        f"{len(orders)} ledger rows before submit"


async def _read_new_order_no(
    page: Any, cdp: str, *, symbol: str, side: str, volume: int, price: float,
    known: Any, attempts: int = 4, delay_ms: int = 1200,
) -> Optional[str]:
    """Poll the ledger after submit for the NEW row matching this order (Anti-Mock)."""
    for i in range(max(1, attempts)):
        try:
            raw = await page.evaluate(
                sync_service._KSS_ORDER_LEDGER_JS if cdp == "kss" else sync_service._LIBERATOR_ORDER_LEDGER_JS
            ) or {}
            rows = raw.get("rows") or []
            orders = (sync_service._parse_kss_order_rows(rows) if cdp == "kss"
                      else sync_service._parse_liberator_order_rows(rows))
            bno = match_new_order_no(orders, symbol=symbol, side=side, volume=volume,
                                     price=price, known=known)
            if bno:
                return bno
        except Exception as exc:
            logger.warning("order-no read attempt %s failed: %s", i + 1, exc)
        if i + 1 < attempts:
            try:
                await page.wait_for_timeout(delay_ms)
            except Exception:
                await asyncio.sleep(delay_ms / 1000.0)
    return None


# --------------------------------------------------------------------------- #
# Per-broker ticket flows
# --------------------------------------------------------------------------- #
async def _kss_preflight(page: Any, side: str) -> Dict[str, Any]:
    """Read-only selector/account check for DRY_RUN — never types into the ticket."""
    missing: List[str] = []
    for label, sel in (
        ("side_radio", KSS_SIDE_RADIOS[side]),
        ("symbol", KSS_SYMBOL),
        ("volume", KSS_VOLUME),
        ("price", KSS_PRICE),
        ("pin", KSS_PIN),
        ("submit", KSS_SUBMIT_BY_SIDE[side]),
    ):
        el, _sel = await _first_visible(page, sel)
        if el is None:
            missing.append(label)
    return {"ok": not missing, "missing": missing, "account_no": await _active_kss_account(page),
            "target": "kss/streaming"}


async def _lib_preflight(
    page: Any,
    side: str,
    *,
    symbol: Optional[str] = None,
    volume: Optional[int] = None,
    price: Optional[float] = None,
    pin: Optional[str] = None,
    account_no: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only preflight for Liberator in DRY_RUN — tries JS pre-place preview first, falls back to DOM."""
    # 0. PIN safety: a preflight hits the same API as a real place, so never call it with a
    #    guessed PIN (the previous default "123456" was a live wrong-PIN attempt) and never
    #    call it while the broker is quarantined.
    if not pin_guard.check("LIBERATOR").get("allowed", True):
        return {"ok": None, "mode": "skipped",
                "note": "PIN guard ปิดอยู่ — ข้าม preflight (ไม่ยิง API ที่ต้องใช้ PIN)"}
    pin_str = str(pin or getattr(settings, "LIBERATOR_PIN", "") or "").strip()
    if not pin_str:
        return {"ok": None, "mode": "skipped",
                "note": "ไม่มี PIN ตั้งค่าไว้ — ข้าม JS preflight เพราะห้ามยิง PIN ปลอม"}
    # 1. JS direct-API preflight (witness-proven contract)
    try:
        from scripts.broker_cdp.js_runner import run_snippet
        acc_8 = str(account_no or getattr(settings, "LIBERATOR_ACCOUNT_NO", "") or "70559382").strip()
        if len(acc_8) == 7:
            acc_8 += "2"
        arg = {
            "symbol": (symbol or "BCPG").strip().upper(),
            "side": "Buy" if normalise_side(side) in ("BUY", "B") else "Sell",
            "volume": int(volume or 100),
            "price": float(price or 1.0),
            "pin": pin_str,
            "dryRun": True,
            "accountNo": acc_8,
        }
        js_res = await run_snippet("liberator", snippet_name="liberator_place", target_kind="portfolio", arg=arg, timeout_s=15.0)
        if js_res.get("success"):
            data = js_res.get("data") or {}
            if data.get("ok"):
                return {
                    "ok": True,
                    "mode": "js_snippet",
                    "preview": data.get("preview"),
                    "account_no": acc_8,
                    "target": "liberator/portfolio",
                }
            elif data.get("step") == "pre-place":
                return {
                    "ok": False,
                    "mode": "js_snippet",
                    "error": f"pre-place rejected: {data.get('errMsg')} (code {data.get('errorCode')})",
                    "target": "liberator/portfolio",
                }
    except Exception as exc:
        logger.debug("Liberator JS preflight attempt failed: %s", exc)

    # 2. Fallback: DOM preflight
    missing: List[str] = []
    side_k = normalise_side(side) or ""
    for label, sel in (
        ("side_toggle", LIB_SIDE_TOGGLES.get(side_k, ()) if side_k else ()),
        ("symbol", LIB_SYMBOL),
        ("volume", LIB_VOLUME),
        ("price", LIB_PRICE),
        ("pin", LIB_PIN),
        ("submit", LIB_SUBMIT),
    ):
        if not sel:
            continue
        el, _sel = await _first_visible(page, sel)
        if el is None:
            missing.append(label)
    return {"ok": not missing, "missing": missing, "target": "liberator/portfolio", "mode": "dom_fallback"}


async def _kss_execute_dom(
    page: Any, *, side: str, symbol: str, volume: int, price: float, pin: str,
    expected_account: str, known: set,
) -> Dict[str, Any]:
    """Fill + submit the Streaming ticket via DOM. Caller owns the page/lock and the DB write."""
    # 1. Account — SHORT/COVER must be on the margin account.
    account = await _active_kss_account(page)
    if account != expected_account:
        if not await _kss_switch_account(page, expected_account):
            return _result_fail(
                E_WRONG_ACCOUNT,
                f"สลับบัญชี Streaming เป็น {expected_account} ไม่สำเร็จ (header = {account or 'อ่านไม่ได้'}) — "
                f"ไม่ส่งคำสั่ง",
                account_no=account, expected_account=expected_account,
            )
        account = expected_account

    # 2. Side radio (before symbol: changing side re-renders the ticket).
    if not await _click_first(page, KSS_SIDE_RADIOS[side]):
        return _result_fail(E_TICKET_INCOMPLETE, f"ไม่พบ side radio {side} ({_SIDE_LETTER[side]})",
                            account_no=account)
    try:
        await page.wait_for_timeout(300)
    except Exception:
        pass

    # 3. Symbol / volume / price.
    ok, _ = await _fill(page, KSS_SYMBOL, symbol)
    if not ok:
        return _result_fail(E_TICKET_INCOMPLETE, "ไม่พบช่อง Symbol บน order ticket", account_no=account)
    try:
        await page.wait_for_timeout(300)
    except Exception:
        pass
    ok, _ = await _fill(page, KSS_VOLUME, str(int(volume)))
    if not ok:
        return _result_fail(E_TICKET_INCOMPLETE, "ไม่พบช่อง Volume บน order ticket", account_no=account)
    ok, _ = await _fill(page, KSS_PRICE, format_price(price))
    if not ok:
        return _result_fail(E_TICKET_INCOMPLETE, "ไม่พบช่อง Price บน order ticket", account_no=account)

    # 4. Anti-DW: read the ticket back before anything irreversible.
    got_sym = (await _read_value(page, KSS_SYMBOL) or "").strip().upper()
    got_vol = (await _read_value(page, KSS_VOLUME) or "").strip().replace(",", "")
    got_px = (await _read_value(page, KSS_PRICE) or "").strip().replace(",", "")
    problems = []
    if got_sym != symbol:
        problems.append(f"symbol {got_sym!r} != {symbol!r}")
    if got_vol not in (str(int(volume)), f"{int(volume)}.00"):
        problems.append(f"volume {got_vol!r} != {volume!r}")
    if got_px != format_price(price) and got_px != str(float(price)):
        problems.append(f"price {got_px!r} != {format_price(price)!r}")
    if problems:
        return _result_fail(E_ANTI_DW, "ticket read-back ไม่ตรง: " + "; ".join(problems),
                            account_no=account, ticket={"symbol": got_sym, "volume": got_vol, "price": got_px})

    # 5. PIN.
    ok, sel = await _fill(page, KSS_PIN, pin)
    if not ok and sel is None:
        return _result_fail(E_TICKET_INCOMPLETE, "ไม่พบช่อง PIN (#pin)", account_no=account)

    # 6. Submit → optional confirm modal.
    #    The button is labelled with the side name once a side is picked, so the generic
    #    "Submit" selector alone is not enough (live-verified 2026-10-21).
    if not await _click_first(page, KSS_SUBMIT_BY_SIDE[side]):
        return _result_fail(E_SUBMIT_FAILED, "ไม่พบปุ่ม Submit บน order ticket", account_no=account)
    try:
        await page.wait_for_timeout(1200)
    except Exception:
        pass
    confirmed = await _confirm_modal(page, side)
    if confirmed is False:
        # The modal is up but we could not accept it → the order was NOT sent. Leave the
        # ticket/dialog for the human and refuse loudly instead of reading a phantom number.
        return _result_fail(
            E_CONFIRM_FAILED,
            "มีหน้า Order Confirmation ค้างอยู่แต่กดยืนยันไม่ได้ — คำสั่งยังไม่ถูกส่ง "
            "(ตรวจหน้าจอแล้วกดยืนยันเอง หรือยกเลิก)",
            account_no=account, submitted=False,
        )
    if confirmed:
        try:
            await page.wait_for_timeout(1500)
        except Exception:
            pass
    else:
        logger.info("KSS: no confirm modal appeared — continuing to ledger read")

    # 7. Read the NEW order number from the ledger grid (never fabricated).
    bno = await _read_new_order_no(page, "kss", symbol=symbol, side=side, volume=volume,
                                   price=price, known=known)
    return {
        "success": bno is not None,
        "status": "SUBMITTED" if bno else "UNCONFIRMED",
        "submitted": True,
        "broker_order_no": bno,
        "confirm_modal": bool(confirmed),
        "account_no": account,
        "error_code": None if bno else E_ORDER_NO_UNREADABLE,
        "error": None if bno else (
            "ส่งคำสั่งแล้วแต่ยังอ่านเลขออเดอร์จาก ledger ไม่ได้ใน 4 ครั้ง — "
            "ต้องตรวจหน้า View Order ด้วยตา (ห้ามถือว่าสำเร็จ)"),
    }


def _normalize_lib_api_orders(raw_list: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize raw API order objects from /va/order to match_new_order_no format."""
    norm = []
    for o in raw_list:
        if not isinstance(o, dict):
            continue
        side_val = str(o.get("side") or o.get("sideShow") or "").upper()
        norm.append({
            "broker_order_no": str(o.get("orderNo") or "").strip(),
            "symbol": str(o.get("symbol") or o.get("symbolDisplay") or o.get("stockSymbol") or "").strip().upper(),
            "side": "BUY" if side_val in ("B", "BUY") else "SELL",
            "volume": int(o.get("volume") or 0),
            "price": float(o.get("price") or 0.0),
            "status": str(o.get("status") or o.get("statusShow") or ""),
        })
    return norm


def _normalize_kss_api_orders(raw_list: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize raw DGW API order objects from /accounts/{acct}/orders to match_new_order_no format."""
    norm = []
    for o in raw_list:
        if not isinstance(o, dict):
            continue
        side_val = str(o.get("side") or "").upper()
        norm_side = "BUY"
        if "COVER" in side_val:
            norm_side = "COVER"
        elif "SHORT" in side_val:
            norm_side = "SHORT"
        elif side_val in ("SELL", "S"):
            norm_side = "SELL"
        else:
            norm_side = "BUY"
        order_no = str(o.get("orderNo") or o.get("orderNoSeos") or "").strip()
        norm.append({
            "broker_order_no": order_no,
            "symbol": str(o.get("symbol") or "").strip().upper(),
            "side": norm_side,
            "volume": int(o.get("vol") or o.get("volume") or 0),
            "price": float(o.get("price") or 0.0),
            "status": str(o.get("showOrderStatus") or o.get("status") or ""),
        })
    return norm


async def _kss_execute_js(
    page: Any,
    *,
    side: str,
    symbol: str,
    volume: int,
    price: float,
    pin: str,
    known: set,
    account_no: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Streaming order via direct-API JS snippet (POST /orders -> re-read orders anti-mock)."""
    acct = str(account_no or getattr(settings, "STREAMING_ACCOUNT_NO_MARGIN", "") or "3024959").strip()
    arg = {
        "symbol": symbol.strip().upper(),
        "side": side,
        "volume": int(volume),
        "price": float(price),
        "pin": str(pin),
        "dryRun": False,
        "acct": acct,
    }

    try:
        from scripts.broker_cdp.js_runner import run_snippet
        js_res = await run_snippet(
            broker="kss",
            snippet_name="streaming_place",
            target_kind="streaming",
            arg=arg,
            timeout_s=60.0,
        )
    except Exception as exc:
        return {"success": False, "submitted": False, "fallback_ok": True, "status": "JS_RUNNER_ERROR", "error": str(exc)}

    if not js_res.get("success"):
        return {
            "success": False,
            "submitted": False,
            "fallback_ok": True,
            "status": "CDP_SNIPPET_FAILED",
            "error": js_res.get("error", "run_snippet failed"),
        }

    data = js_res.get("data") or {}
    if not isinstance(data, dict):
        return {
            "success": False,
            "submitted": False,
            "fallback_ok": True,
            "status": "INVALID_SNIPPET_DATA",
            "error": f"Snippet returned non-dict: {data!r}",
        }

    if not data.get("ok"):
        step = data.get("step")
        err_msg = data.get("errMsg") or data.get("error") or f"error in step {step}"
        # If step is auth/validate, nothing was sent to broker -> fallback safe.
        # If step is place/verify, payload was sent -> fallback NOT safe.
        fb_ok = step in ("auth", "validate")
        return {
            "success": False,
            "submitted": step in ("place", "verify"),
            "fallback_ok": fb_ok,
            "status": f"REJECTED_{step.upper()}" if step else "REJECTED",
            "error_code": f"E_KSS_{step.upper()}" if step else "E_KSS_REJECTED",
            "error": f"Streaming JS direct-API {step} failed: {err_msg}",
        }

    # Anti-Mock: verify new order number from re-read list
    order_list = data.get("list") or []
    norm_orders = _normalize_kss_api_orders(order_list)
    known_seq = list(known)
    bno = match_new_order_no(
        norm_orders, symbol=symbol, side=side, volume=volume, price=price, known=known_seq,
    )
    if not bno and data.get("orderNo"):
        cand = str(data.get("orderNo")).strip()
        if cand and cand not in known:
            bno = cand

    return {
        "success": bno is not None,
        "status": "SUBMITTED" if bno else "UNCONFIRMED",
        "submitted": True,
        "fallback_ok": False,
        "broker_order_no": bno,
        "account_no": acct,
        "source": "streaming_js",
        "error_code": None if bno else E_ORDER_NO_UNREADABLE,
        "error": None if bno else (
            "ส่งคำสั่งผ่าน JS direct-API แล้วแต่ยังอ่าน Order # จากตาราง orders ไม่ได้ — "
            "ต้องตรวจหน้า View Order ด้วยตา (ห้ามถือว่าสำเร็จ)"
        ),
    }


async def _kss_execute(
    page: Any, *, side: str, symbol: str, volume: int, price: float, pin: str,
    expected_account: str, known: set,
) -> Dict[str, Any]:
    """Execute Streaming order: JS direct-API primary, DOM ticket automation fallback (gated on fallback_ok)."""
    # 1. Primary: JS direct-API path
    js_res = await _kss_execute_js(
        page, side=side, symbol=symbol, volume=volume, price=price, pin=pin,
        known=known, account_no=expected_account,
    )
    if js_res.get("submitted") or js_res.get("success"):
        return js_res

    if not js_res.get("fallback_ok", False):
        return js_res

    # 2. Fallback: DOM ticket automation (only safe when nothing reached broker)
    logger.warning(
        "Streaming JS path not submitted (%s: %s) — falling back to DOM ticket",
        js_res.get("status"), js_res.get("error"),
    )
    return await _kss_execute_dom(
        page, side=side, symbol=symbol, volume=volume, price=price, pin=pin,
        expected_account=expected_account, known=known,
    )


async def _lib_execute_js(
    page: Any,
    *,
    side: str,
    symbol: str,
    volume: int,
    price: float,
    pin: str,
    known: set,
    account_no: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Liberator order via direct-API JS snippet (pre-place -> place -> re-read anti-mock)."""
    acc_8 = str(account_no or getattr(settings, "LIBERATOR_ACCOUNT_NO", "") or "70559382").strip()
    if len(acc_8) == 7:
        acc_8 += "2"
    side_name = "Buy" if normalise_side(side) in ("BUY", "B") else "Sell"

    arg = {
        "symbol": symbol.strip().upper(),
        "side": side_name,
        "volume": int(volume),
        "price": float(price),
        "pin": str(pin),
        "dryRun": False,
        "accountNo": acc_8,
    }

    try:
        from scripts.broker_cdp.js_runner import run_snippet
        res = await run_snippet(
            broker="liberator",
            snippet_name="liberator_place",
            target_kind="portfolio",
            arg=arg,
            timeout_s=60.0,
        )
    except Exception as exc:
        return {"success": False, "submitted": False, "status": "JS_RUNNER_ERROR", "error": str(exc)}

    if not res.get("success"):
        return {
            "success": False,
            "submitted": False,
            "status": "CDP_SNIPPET_FAILED",
            "error": res.get("error", "run_snippet failed"),
        }

    data = res.get("data") or {}
    if not isinstance(data, dict):
        return {
            "success": False,
            "submitted": False,
            "status": "INVALID_SNIPPET_DATA",
            "error": f"Snippet returned non-dict: {data!r}",
        }

    if not data.get("ok"):
        step = data.get("step")
        err_msg = data.get("errMsg") or data.get("error") or f"error in step {step}"
        return {
            "success": False,
            "submitted": False,
            "status": f"REJECTED_{step.upper()}" if step else "REJECTED",
            "error_code": f"E_LIB_{step.upper()}" if step else "E_LIB_REJECTED",
            "error": f"Liberator JS direct-API {step} failed: {err_msg}",
        }

    # Step place succeeded -> The order WAS submitted to the exchange!
    # Anti-Mock: verify new order number from re-read list
    order_list = data.get("list") or []
    norm_orders = _normalize_lib_api_orders(order_list)
    known_seq = list(known)
    bno = match_new_order_no(
        norm_orders, symbol=symbol, side=side, volume=volume, price=price, known=known_seq,
    )

    # If immediate re-read missed it on a slow board, retry reading once
    if not bno:
        try:
            await asyncio.sleep(2.0)
            recheck_res = await run_snippet(
                broker="liberator",
                snippet_name="liberator_read",
                target_kind="portfolio",
                timeout_s=30.0,
            )
            if recheck_res.get("success"):
                recheck_data = recheck_res.get("data") or {}
                norm_recheck = _normalize_lib_api_orders(recheck_data.get("list") or [])
                bno = match_new_order_no(
                    norm_recheck, symbol=symbol, side=side, volume=volume, price=price, known=known_seq,
                )
        except Exception as exc:
            logger.warning("Liberator re-read retry failed: %s", exc)

    return {
        "success": bno is not None,
        "status": "SUBMITTED" if bno else "UNCONFIRMED",
        "submitted": True,
        "broker_order_no": bno,
        "account_no": getattr(settings, "LIBERATOR_ACCOUNT_NO", acc_8),
        "source": "liberator_js",
        "error_code": None if bno else E_ORDER_NO_UNREADABLE,
        "error": None if bno else (
            "ส่งคำสั่งผ่าน JS direct-API แล้วแต่ยังอ่าน Order # จากตาราง orders ไม่ได้ — "
            "ต้องตรวจหน้า Portfolio ด้วยตา (ห้ามถือว่าสำเร็จ)"
        ),
    }


async def _lib_execute_dom(
    page: Any, *, side: str, symbol: str, volume: int, price: float, pin: str, known: set,
) -> Dict[str, Any]:
    """Fill + submit the WebTrade footer ticket (BUY/SELL only) via DOM."""
    if not await _click_first(page, LIB_SIDE_TOGGLES[side]):
        return _result_fail(E_TICKET_INCOMPLETE, f"ไม่พบ side toggle {side} บน footer ticket")
    try:
        await page.wait_for_timeout(300)
    except Exception:
        pass

    ok, _ = await _fill(page, LIB_SYMBOL, symbol)
    if not ok:
        return _result_fail(E_TICKET_INCOMPLETE, "ไม่พบช่อง Symbol บน footer ticket")
    try:
        await page.wait_for_timeout(400)
    except Exception:
        pass
    for sel, text, label in ((LIB_VOLUME, str(int(volume)), "Volume"),
                             (LIB_PRICE, format_price(price), "Price")):
        ok, _ = await _fill(page, sel, text)
        if not ok:
            return _result_fail(E_TICKET_INCOMPLETE, f"ไม่พบช่อง {label} บน footer ticket")

    got_sym = (await _read_value(page, LIB_SYMBOL) or "").strip().upper()
    got_vol = (await _read_value(page, LIB_VOLUME) or "").strip().replace(",", "")
    got_px = (await _read_value(page, LIB_PRICE) or "").strip().replace(",", "")
    problems = []
    if got_sym != symbol:
        problems.append(f"symbol {got_sym!r} != {symbol!r}")
    if got_vol not in (str(int(volume)), f"{int(volume)}.00"):
        problems.append(f"volume {got_vol!r} != {volume!r}")
    if got_px != format_price(price) and got_px != str(float(price)):
        problems.append(f"price {got_px!r} != {format_price(price)!r}")
    if problems:
        return _result_fail(E_ANTI_DW, "ticket read-back ไม่ตรง: " + "; ".join(problems))

    ok, sel = await _fill(page, LIB_PIN, pin)
    if not ok and sel is None:
        return _result_fail(E_TICKET_INCOMPLETE, "ไม่พบช่อง PIN (#pin) บน footer ticket")

    if not await _click_first(page, LIB_SUBMIT):
        return _result_fail(E_SUBMIT_FAILED, "ไม่พบปุ่ม Submit (#buttonSubmit)")
    try:
        await page.wait_for_timeout(1200)
    except Exception:
        pass
    confirmed = await _click_first(page, LIB_CONFIRM)
    if confirmed:
        try:
            await page.wait_for_timeout(1500)
        except Exception:
            pass

    bno = await _read_new_order_no(page, "lib", symbol=symbol, side=side, volume=volume,
                                   price=price, known=known)
    return {
        "success": bno is not None,
        "status": "SUBMITTED" if bno else "UNCONFIRMED",
        "submitted": True,
        "broker_order_no": bno,
        "confirm_modal": bool(confirmed),
        "account_no": getattr(settings, "LIBERATOR_ACCOUNT_NO", None),
        "error_code": None if bno else E_ORDER_NO_UNREADABLE,
        "error": None if bno else (
            "ส่งคำสั่งแล้วแต่ยังอ่าน Order # จากตาราง orders ไม่ได้ใน 4 ครั้ง — "
            "ต้องตรวจหน้า Portfolio ด้วยตา (ห้ามถือว่าสำเร็จ)"),
    }


async def _lib_execute(
    page: Any, *, side: str, symbol: str, volume: int, price: float, pin: str, known: set,
    account_no: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Liberator order: JS direct-API primary, DOM ticket automation fallback."""
    # 1. Primary: JS direct-API path
    js_res = await _lib_execute_js(
        page, side=side, symbol=symbol, volume=volume, price=price, pin=pin,
        known=known, account_no=account_no,
    )
    if js_res.get("submitted") or js_res.get("success"):
        return js_res

    # 2. Fallback: Playwright/DOM ticket automation
    logger.warning(
        "Liberator JS path not submitted (%s: %s) — falling back to DOM ticket",
        js_res.get("status"), js_res.get("error"),
    )
    return await _lib_execute_dom(
        page, side=side, symbol=symbol, volume=volume, price=price, pin=pin, known=known,
    )


async def execute_liberator_change_js(
    order_no: str,
    new_price: float,
    volume: int,
    pin: Optional[str] = None,
) -> Dict[str, Any]:
    """Amend a resting Liberator order in-place via PUT /va/order (anti-mock re-read)."""
    order_pin = pin or getattr(settings, "LIBERATOR_PIN", "")
    if not order_pin:
        return {"success": False, "error": "Valid Liberator PIN required."}
    from scripts.broker_cdp.js_runner import run_snippet
    arg = {"orderNo": str(order_no), "price": float(new_price), "volume": int(volume), "pin": str(order_pin)}
    res = await run_snippet("liberator", snippet_name="liberator_change", target_kind="portfolio", arg=arg, timeout_s=60.0)
    if not res.get("success"):
        return {"success": False, "error": res.get("error", "liberator_change snippet failed")}
    data = res.get("data") or {}
    return {
        "success": bool(data.get("ok") and data.get("verified")),
        "order_no": str(order_no),
        "changed_price": data.get("changedPrice"),
        "verified": bool(data.get("verified")),
        "error": data.get("errMsg") or data.get("error") if not data.get("ok") else None,
    }


async def execute_liberator_cancel_js(
    order_no: str,
    pin: Optional[str] = None,
) -> Dict[str, Any]:
    """Cancel a resting Liberator order via POST /va/order/cancelled (anti-mock re-read)."""
    order_pin = pin or getattr(settings, "LIBERATOR_PIN", "")
    if not order_pin:
        return {"success": False, "error": "Valid Liberator PIN required."}
    from scripts.broker_cdp.js_runner import run_snippet
    arg = {"orderNo": str(order_no), "pin": str(order_pin)}
    res = await run_snippet("liberator", snippet_name="liberator_cancel", target_kind="portfolio", arg=arg, timeout_s=60.0)
    if not res.get("success"):
        return {"success": False, "error": res.get("error", "liberator_cancel snippet failed")}
    data = res.get("data") or {}
    return {
        "success": bool(data.get("ok") and data.get("verified")),
        "order_no": str(order_no),
        "cancelled": data.get("cancelled"),
        "balance": data.get("balance"),
        "verified": bool(data.get("verified")),
        "error": data.get("errMsg") or data.get("error") if not data.get("ok") else None,
    }


async def execute_streaming_change_js(
    order_no: str,
    new_price: float,
    volume: int,
    pin: Optional[str] = None,
    trade_date: Optional[str] = None,
    acct: Optional[str] = None,
) -> Dict[str, Any]:
    """Amend a resting Streaming order in-place via PATCH .../orders/{orderNo}/change (anti-mock re-read)."""
    order_pin = pin or getattr(settings, "KRUNGSRI_PIN", "")
    if not order_pin:
        return {"success": False, "error": "Valid Krungsri/Streaming PIN required."}
    from scripts.broker_cdp.js_runner import run_snippet
    arg = {
        "orderNo": str(order_no),
        "price": float(new_price),
        "volume": int(volume),
        "pin": str(order_pin),
    }
    if trade_date:
        arg["tradeDate"] = str(trade_date)
    if acct:
        arg["acct"] = str(acct)
    res = await run_snippet("kss", snippet_name="streaming_change", target_kind="streaming", arg=arg, timeout_s=60.0)
    if not res.get("success"):
        return {"success": False, "error": res.get("error", "streaming_change snippet failed")}
    data = res.get("data") or {}
    return {
        "success": bool(data.get("ok") and data.get("verified")),
        "order_no": str(order_no),
        "changed_price": data.get("changedPrice"),
        "changed_volume": data.get("changedVolume"),
        "verified": bool(data.get("verified")),
        "error": data.get("errMsg") or data.get("error") if not data.get("ok") else None,
    }


async def execute_streaming_cancel_js(
    order_no: str,
    pin: Optional[str] = None,
    symbol: Optional[str] = None,
    trade_date: Optional[str] = None,
    acct: Optional[str] = None,
) -> Dict[str, Any]:
    """Cancel a resting Streaming order via PATCH .../accounts/{acct}/cancel (anti-mock re-read)."""
    order_pin = pin or getattr(settings, "KRUNGSRI_PIN", "")
    if not order_pin:
        return {"success": False, "error": "Valid Krungsri/Streaming PIN required."}
    from scripts.broker_cdp.js_runner import run_snippet
    arg = {"orderNo": str(order_no), "pin": str(order_pin)}
    if symbol:
        arg["symbol"] = str(symbol).strip().upper()
    if trade_date:
        arg["tradeDate"] = str(trade_date)
    if acct:
        arg["acct"] = str(acct)
    res = await run_snippet("kss", snippet_name="streaming_cancel", target_kind="streaming", arg=arg, timeout_s=60.0)
    if not res.get("success"):
        return {"success": False, "error": res.get("error", "streaming_cancel snippet failed")}
    data = res.get("data") or {}
    return {
        "success": bool(data.get("ok") and data.get("verified")),
        "order_no": str(order_no),
        "cancelled": bool(data.get("cancelled")),
        "status": data.get("status"),
        "verified": bool(data.get("verified")),
        "error": data.get("errMsg") or data.get("error") if not data.get("ok") else None,
    }


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
async def check_short_borrow(db: AsyncSession, symbol: str, volume: int) -> Tuple[bool, Optional[str]]:
    """SHORT guard: an ACTIVE ``sbl_borrow_lots`` row must cover ``volume`` shares."""
    res = await db.execute(select(SBLBorrowLot).where(
        SBLBorrowLot.symbol == symbol, SBLBorrowLot.status == "ACTIVE",
        SBLBorrowLot.remaining_qty >= int(volume)))
    if res.scalars().first() is None:
        return False, (f"ไม่มีหุ้นยืม SBL คงเหลือของ {symbol} (≥ {int(volume):,} หุ้น) — "
                       f"ยืม/คืน manual ใน Loop 1 ก่อน แล้วค่อยสั่ง short")
    return True, None


async def _record_order(
    db: AsyncSession,
    *,
    broker: str,
    symbol: str,
    side: str,
    volume: int,
    price: float,
    account_no: Optional[str],
    broker_order_no: Optional[str],
    status: str,
    error_message: Optional[str] = None,
) -> Optional[str]:
    """Insert the ``orders`` row for this execution (idempotent on ``broker_order_no``)."""
    if broker_order_no:
        existing = (await db.execute(
            select(Order.order_id).where(Order.broker_order_no == broker_order_no))).scalars().first()
        if existing:
            return existing
    order_id = (f"CDP-{broker}-{broker_order_no}" if broker_order_no
                else f"CDP-{broker}-{status}-{int(time.time() * 1000)}")
    db.add(Order(
        order_id=order_id,
        broker_order_no=broker_order_no,
        symbol=symbol,
        side=side,
        volume=int(volume),
        price=float(price),
        status=status,
        source="bot_cdp",
        account_no=account_no,
        broker=broker,
        error_message=error_message,
    ))
    await db.commit()
    return order_id


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
async def execute_order_via_cdp(
    broker: str,
    side: str,
    symbol: str,
    volume: int,
    price: float,
    *,
    pin: Optional[str] = None,
    account_no: Optional[str] = None,
    last_trade_price: Optional[float] = None,
    dry_run: Optional[bool] = None,
    bypass_dry_run: bool = False,
    record: bool = True,
) -> Dict[str, Any]:
    """Place ONE real order on the human-witnessed broker tab and record it.

    ``broker`` — ``kss`` | ``lib`` / ``liberator``. ``side`` — BUY/SELL/SHORT/COVER (or
    B/S/H/C). ``last_trade_price`` — required for SHORT (G6 strict uptick); pass the price
    the human sees on the quote board. ``dry_run`` — defaults to ``settings.DRY_RUN_MODE``.

    Returns a dict with ``success`` / ``status`` / ``broker_order_no`` / ``order_id`` and,
    for refusals, a stable ``error_code``. ``status`` values: ``DRY_RUN`` (validated, no
    ticket interaction), ``REJECTED`` (nothing sent), ``SUBMITTED`` (order number read off
    the ledger), ``UNCONFIRMED`` (sent, order number NOT provable — check by eye),
    ``RECORD_FAILED`` (sent, ledger read, DB write failed).
    """
    meta = resolve_broker(broker)
    if meta is None:
        return _result_fail(E_BAD_BROKER, f"ไม่รู้จัก broker {broker!r} (ใช้ kss | lib)")

    db_broker = meta["broker"]
    side_c = normalise_side(side)
    if side_c is None:
        return _result_fail(E_BAD_SIDE, f"side {side!r} ไม่ถูกต้อง (BUY/SELL/SHORT/COVER)",
                            broker=db_broker)
    if side_c not in meta["sides"]:
        return _result_fail(
            E_UNSUPPORTED_SIDE,
            f"{db_broker} รองรับเฉพาะ {', '.join(meta['sides'])} — {side_c} ต้องใช้บัญชี margin ที่ KSS",
            broker=db_broker,
        )

    sym = str(symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        return _result_fail(E_BAD_ORDER, f"symbol {symbol!r} ไม่ถูกต้อง", broker=db_broker)
    try:
        vol = int(volume)
        px = float(price)
    except (TypeError, ValueError):
        return _result_fail(E_BAD_ORDER, f"volume/price ไม่ใช่ตัวเลข ({volume!r}/{price!r})",
                            broker=db_broker)
    if vol <= 0 or px <= 0:
        return _result_fail(E_BAD_ORDER, f"volume/price ต้องมากกว่า 0 ({vol}/{px})", broker=db_broker)

    # G1 — money movement.
    from app.services.kill_switch_service import kill_switch_service
    if kill_switch_service.is_active():
        return _result_fail(E_KILL_SWITCH, "KILL-SWITCH ACTIVE — ระงับการส่งคำสั่งทั้งหมด",
                            broker=db_broker)

    # G0 — PIN guard: refuse before any PIN can be typed into the ticket. Checked before
    # the validator on purpose: a refused call must not consume the idempotency slot and
    # block the legitimate re-send after the guard is reset.
    guard = pin_guard.check(db_broker)
    if not guard.get("allowed", True):
        logger.error("PIN guard refused %s %s %s: %s", db_broker, side_c, sym, guard.get("reason"))
        return _result_fail(E_PIN_GUARD, guard.get("reason") or "PIN guard ปิดการส่งคำสั่ง",
                            broker=db_broker, symbol=sym, side=side_c, pin_guard=guard)

    dry = bool(settings.DRY_RUN_MODE) if dry_run is None else bool(dry_run)

    # G6 — a SHORT without a quote cannot prove the strict uptick rule: refuse, never skip.
    if side_c == "SHORT" and last_trade_price is None:
        return _result_fail(
            E_NO_QUOTE,
            "short ต้องมี last_trade_price เพื่อเช็ค strict uptick (G6) — อ่านราคาล่าสุดจากหน้าจอแล้วส่งมาด้วย",
            broker=db_broker, symbol=sym, side=side_c,
        )

    # Validator SSOT: odd-lot / tick / value ceiling / strict short uptick / idempotency.
    # A dry run must not poison the idempotency window for the real submit that follows.
    ok, err = validator.validate_all(
        symbol=sym, side=side_c, volume=vol, price=px,
        last_trade_price=last_trade_price, record_idempotency=not dry,
    )
    if not ok:
        return _result_fail(E_VALIDATOR, f"ไม่ผ่าน validator — {err}", broker=db_broker,
                            symbol=sym, side=side_c, volume=vol, price=px)

    warnings: List[str] = []
    warn = market_window_warning()
    if warn:
        warnings.append(warn)

    expected_account = str(account_no or "").strip() or None
    if expected_account is None and meta["cdp"] == "kss":
        margin = str(getattr(settings, "STREAMING_ACCOUNT_NO_MARGIN", "") or "").strip()
        cash = str(getattr(settings, "STREAMING_ACCOUNT_NO_CASH", "") or "").strip()
        expected_account = margin if side_c in ("SHORT", "COVER") else (
            str(getattr(settings, "STREAMING_ACCOUNT_NO", "") or "").strip() or margin or cash)
    if expected_account is None and meta["cdp"] == "liberator":
        expected_account = str(getattr(settings, "LIBERATOR_ACCOUNT_NO", "") or "").strip() or None

    session: AsyncSession = db_session.AsyncSessionLocal()
    try:
        # SHORT needs borrowed shares (SBL traded manually in Loop 1 — warn/refuse, never assume).
        if side_c == "SHORT":
            borrow_ok, borrow_msg = await check_short_borrow(session, sym, vol)
            if not borrow_ok:
                return _result_fail(E_NO_SBL, borrow_msg or "ไม่มีหุ้นยืม SBL",
                                    broker=db_broker, symbol=sym, side=side_c, volume=vol)

        pin_val = resolve_pin(broker, pin)
        if pin_val is None and not dry:
            key = meta["pin_key"]
            return _result_fail(
                E_NO_PIN if not str(getattr(settings, key, "") or "").strip() else E_BAD_PIN,
                f"ไม่มี PIN 6 หลัก ({key}) ใน .env — ใส่ก่อนยิงออเดอร์จริง",
                broker=db_broker, symbol=sym, side=side_c,
            )

        # ---- DRY_RUN guard: after validate, before anything is typed or submitted. ----
        if dry and not bypass_dry_run:
            preflight: Dict[str, Any] = {"ok": None, "note": "ไม่ได้เปิดแท็บ (dry run)"}
            try:
                async with get_tab(meta["cdp"], meta["target"]) as page:
                    preflight = (await _kss_preflight(page, side_c) if meta["cdp"] == "kss"
                                 else await _lib_preflight(
                                     page, side_c, symbol=sym, volume=vol, price=px,
                                     pin=pin_val, account_no=expected_account,
                                 ))
            except Exception as exc:
                preflight = {"ok": False,
                             "error": f"{type(exc).__name__}: {exc}",
                             "note": "ต่อ CDP tab ไม่ได้ — dry run ยังผ่านเพราะไม่ได้ส่งคำสั่ง"}
            return {
                "success": True,
                "status": "DRY_RUN",
                "submitted": False,
                "broker_order_no": None,
                "order_id": None,
                "broker": db_broker,
                "side": side_c,
                "symbol": sym,
                "volume": vol,
                "price": px,
                "account_no": expected_account,
                "pin_configured": pin_val is not None,
                "last_trade_price": last_trade_price,
                "preflight": preflight,
                "warnings": warnings,
                "message": "ผ่าน validator/guardrail แล้ว — DRY_RUN_MODE ปิดการส่ง (ไม่มีการกรอกตั๋ว/กด submit)",
            }

        # ---- LIVE path ----------------------------------------------------------
        if pin_val is None:  # bypass_dry_run with a dry run requested and no PIN configured
            return _result_fail(E_NO_PIN, f"ไม่มี PIN 6 หลัก ({meta['pin_key']}) — ไม่สามารถส่งได้",
                                broker=db_broker, symbol=sym, side=side_c)
        # ---- PIN guard already cleared above (G0): nothing here can type a PIN ----
        result: Dict[str, Any]
        dialog_cap: Optional[_DialogCapture] = None
        try:
            async with get_tab(meta["cdp"], meta["target"]) as page:
                readable, known, note = await _ledger_snapshot(page, meta["cdp"])
                if not readable:
                    return _result_fail(
                        E_LEDGER_UNREADABLE,
                        f"อ่าน order ledger ก่อนส่งไม่ได้ ({note}) — ไม่ส่งคำสั่งที่ตรวจยืนยันไม่ได้",
                        broker=db_broker, symbol=sym, side=side_c,
                    )
                logger.info("%s ledger snapshot: %s", db_broker, note)
                dialog_cap = _install_dialog_capture(page)
                try:
                    if meta["cdp"] == "kss":
                        result = await _kss_execute(
                            page, side=side_c, symbol=sym, volume=vol, price=px, pin=pin_val,
                            expected_account=expected_account or "", known=known,
                        )
                    else:
                        result = await _lib_execute(
                            page, side=side_c, symbol=sym, volume=vol, price=px, pin=pin_val,
                            known=known, account_no=expected_account,
                        )
                finally:
                    _detach_dialog_capture(page, dialog_cap)
        except Exception as exc:
            logger.exception("execute_order_via_cdp(%s) failed inside the tab", db_broker)
            return _result_fail("E_EXECUTION", f"{type(exc).__name__}: {exc}",
                                status="FAILED", broker=db_broker, symbol=sym, side=side_c)

        # ---- PIN rejection: the broker's own words outrank every guess ---------------
        # The message can come from a JS alert the app raised (DOM ticket) or from the
        # direct-API snippet's error payload (POST /orders refused). Either way it is a
        # real PIN attempt: count it, quarantine the broker, and keep the evidence.
        pin_msg = (dialog_cap.pin_error if dialog_cap else None) or (
            result.get("error") if pin_guard.is_pin_error(result.get("error") or "") else None)
        if pin_msg:
            code = pin_guard.classify_pin_error(pin_msg) or E_PIN_REJECTED
            guard_state = pin_guard.record_failure(db_broker, pin_msg, code=code)
            logger.error("PIN REJECTED by %s for %s %s: %s", db_broker, side_c, sym, pin_msg)
            result = _result_fail(
                code,
                f"โบรกปฏิเสธ PIN — {pin_msg} (ห้ามลองซ้ำเอง: PIN guard ปิดการส่งแล้ว)",
                status="REJECTED", broker=db_broker, symbol=sym, side=side_c,
                submitted=True, account_no=result.get("account_no"),
                pin_guard=guard_state, dialog_text=(dialog_cap.text if dialog_cap else None),
            )
        elif result.get("status") == "SUBMITTED":
            # A real order proves the PIN was accepted — clear any earlier quarantine.
            pin_guard.record_success(db_broker)

        result.update({
            "broker": db_broker, "side": side_c, "symbol": sym,
            "volume": vol, "price": px,
            "account_no": result.get("account_no") if result.get("account_no") is not None else expected_account,
            "last_trade_price": last_trade_price,
            "warnings": warnings,
        })
        if result.get("status") not in ("SUBMITTED", "UNCONFIRMED"):
            # A refused *submit* is still an attempt and must leave a row behind — the
            # 2026-10-29 lockout was invisible precisely because this branch returned
            # silently. Pre-submit refusals (nothing typed, nothing sent) stay unlogged.
            if record and result.get("submitted"):
                try:
                    result["order_id"] = await _record_order(
                        session, broker=db_broker, symbol=sym, side=side_c, volume=vol, price=px,
                        account_no=result.get("account_no"),
                        broker_order_no=result.get("broker_order_no"),
                        status="REJECTED",
                        error_message=(str(result.get("error") or "")[:500] or None),
                    )
                except Exception as exc:
                    logger.exception("orders row insert failed for refused %s", sym)
                    result["order_audit_error"] = f"{type(exc).__name__}: {exc}"
                await _log_session_event(
                    session, "CDP_ORDER_REJECTED",
                    f"{db_broker} {side_c} {vol} {sym} @ {px:.2f} "
                    f"{result.get('error_code') or 'E_UNKNOWN'} — {str(result.get('error') or '')[:300]}",
                )
            return result

        # ---- Record + sync (outside the tab lock: sync takes the same lock) ------
        order_id: Optional[str] = None
        if record:
            try:
                order_id = await _record_order(
                    session, broker=db_broker, symbol=sym, side=side_c, volume=vol, price=px,
                    account_no=result.get("account_no"),
                    broker_order_no=result.get("broker_order_no"),
                    status="SUBMITTED" if result["status"] == "SUBMITTED" else "UNCONFIRMED",
                    error_message=None if result["status"] == "SUBMITTED" else result.get("error"),
                )
            except Exception as exc:
                logger.exception("orders row insert failed for %s", sym)
                result.update({"status": "RECORD_FAILED", "success": False,
                               "error_code": "E_RECORD", "order_id": None,
                               "error": f"ส่งแล้วแต่บันทึก orders ไม่สำเร็จ: {type(exc).__name__}: {exc}"})
                return result
        result["order_id"] = order_id

        try:
            result["sync"] = await sync_service.sync_orders_from_cdp(broker)
        except Exception as exc:
            logger.warning("post-submit order sync skipped: %s: %s", type(exc).__name__, exc)
            result["sync"] = {"error": f"{type(exc).__name__}: {exc}"}

        result.setdefault("message", (
            f"ส่งคำสั่งสำเร็จ — เลขออเดอร์ {result.get('broker_order_no')}" if result["success"]
            else "ส่งแล้วแต่ยืนยันเลขออเดอร์ไม่ได้ — ตรวจหน้าจอด้วยตา"))
        logger.warning("LIVE ORDER %s %s %s %s @ %s -> %s (%s)", db_broker, side_c, vol, sym, px,
                       result.get("broker_order_no"), result.get("status"))
        return result
    finally:
        try:
            await session.close()
        except Exception:
            pass


async def execute_confirmed_order(draft: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    """Adapter for the B.5 confirm postback payload → :func:`execute_order_via_cdp`.

    ``handlers.handle_postback`` returns ``{"status": "TRADE_DRAFT_CONFIRMED", "order":
    {cmd, symbol, volume, price, broker, account, account_no}}``; this maps ``cmd`` to the
    executor's ``side``. Wiring this into the webhook is a separate witnessed change —
    nothing calls it automatically yet.
    """
    order = (draft or {}).get("order") or draft or {}
    return await execute_order_via_cdp(
        broker=order.get("broker"),
        side=order.get("cmd"),
        symbol=order.get("symbol"),
        volume=order.get("volume"),
        price=order.get("price"),
        account_no=order.get("account_no"),
        **kwargs,
    )


async def change_order_native(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Forward native amend to streaming_driver.change_order_native."""
    from app.browser.streaming_driver import streaming_driver
    return await streaming_driver.change_order_native(*args, **kwargs)


__all__ = [
    "execute_order_via_cdp",
    "execute_confirmed_order",
    "change_order_native",
    "match_new_order_no",
    "normalise_side",
    "resolve_broker",
    "resolve_pin",
    "market_window_warning",
    "format_price",
    "check_short_borrow",
]
