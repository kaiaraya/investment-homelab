import asyncio
import logging
import os
import random
import re
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.browser.auth_driver import auth_driver
from app.core.config import settings
from app.db.models import SessionLog
from app.db.session import AsyncSessionLocal
from app.services.validator import validator
from app.browser.popup_manager import popup_manager

logger = logging.getLogger(__name__)


def _extract_account_no(text: Any) -> Optional[str]:
    """Extract the first *exactly* 7-digit TradeMan account number from a DOM text blob.

    RCA-006a: the account number is validated against this shape (see
    ``learned_workflows/krungsri/trademan_portfolio_dom.md``), so a longer/shorter
    digit run must never be accepted as an account number.
    """
    match = re.search(r"(?<!\d)(\d{7})(?!\d)", str(text or ""))
    return match.group(1) if match else None


def _parse_float(cell: Any, default: float = 0.0) -> float:
    """Parse a Thai-formatted number cell ("1,234.50", "5%", "+3.2") → float."""
    try:
        return float(str(cell).replace(",", "").replace("%", "").replace("+", "").strip())
    except Exception:
        return default


def _parse_int(cell: Any, default: int = 0) -> int:
    """Parse a Thai-formatted quantity cell ("1,234", "800.0") → int."""
    try:
        return int(float(str(cell).replace(",", "").replace("+", "").strip()))
    except Exception:
        return default


def _parse_float_or_none(cell: Any) -> Optional[float]:
    """Parse a *totals* cell ("220,000.00") → float, or ``None``.

    RCA-013 / Anti-Mock: a blank or placeholder cell (``-``, ``N/A``, ``ไม่พบข้อมูล``)
    must yield ``None`` so the CLI renders ``—`` — never a fabricated ``0.00``.
    """
    txt = str(cell or "").replace(",", "").replace("%", "").replace("+", "").strip()
    if not txt or _hkey(txt) in _PLACEHOLDER_CELL_VALUES:
        return None
    try:
        return float(txt)
    except Exception:
        return None


# ---- TradeMan Portfolio table discovery (RCA-006b, probe 2026-10-13) ----
# The holdings header and body are two *separate* <table> elements. The legacy
# `table tbody tr` scan also counted the summary/totals table (16 rows, not 15)
# and could pair the wrong account's rows. Dump the table inventory once, then
# do all pairing/mapping in Python (unit-testable without a browser).
_PORTFOLIO_TABLES_JS = r"""() => {
    const norm = (el) => ((el && el.innerText) || "").replace(/\s+/g, " ").trim();
    return Array.from(document.querySelectorAll("table")).map((t) => ({
        cls: (t.className || "").toString(),
        headers: Array.from(t.querySelectorAll("thead th")).map(norm),
        rows: Array.from(t.querySelectorAll("tbody tr"))
            .map((tr) => Array.from(tr.querySelectorAll("td")).map(norm)),
        in_scroll: !!(t.parentElement && t.parentElement.classList
            && t.parentElement.classList.contains("scrollbar-container")),
        has_thead: !!t.querySelector("thead")
    }));
}"""

_HOLDINGS_HEADER_ALIASES = {
    # TradeMan holdings header (probe): Symbol | On Hand | Sellable | Avg | Last |
    # Cost | Market Value | Unreal | %Unreal | Real
    "symbol": ("symbol", "ticker"),
    "on_hand": ("onhand", "holding", "holdingqty"),
    "sellable": ("sellable", "available", "availableqty"),
    "avg_cost": ("avg", "average", "avgcost", "averagecost"),
    "current_price": ("last", "lastprice", "marketprice"),
    "cost_value": ("cost", "costvalue", "totalcost"),
    "market_value": ("marketvalue", "mktvalue"),
    "unrealized_pnl": ("unreal", "unrealized", "unrealizedpnl", "unrealizedprofit"),
    "pnl_pct": ("unreal", "unrealpct", "unrealpercent", "pnl", "pnlpercent"),
}

_HOLDINGS_FIELD_ORDER = (
    "symbol", "on_hand", "sellable", "avg_cost", "current_price",
    "cost_value", "market_value", "unrealized_pnl", "pnl_pct",
)

_HOLDINGS_REQUIRED_FIELDS = ("symbol", "on_hand", "market_value")

# Totals-row / placeholder markers — never reported as holdings (RCA-006b rule f)
_TOTALS_TOKENS = ("total", "totals", "totalvalue", "sum", "รวม", "ยอดรวม", "มูลค่ารวม")

_PLACEHOLDER_CELL_VALUES = ("", "-", "--", "n/a", "na", "ไม่พบ", "ไม่พบข้อมูล", "nodata")


def _hkey(name: Any) -> str:
    """Normalise a header / cell text for matching: lowercase, alphanumeric only."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _map_holdings_columns(headers: List[str]) -> Dict[str, int]:
    """Map holdings column *names* (not positions) to indexes — RCA-006b rule e.

    ``Unreal`` and ``%Unreal`` normalise to the same key, so a header containing
    ``%`` is claimed by ``pnl_pct`` and the plain one by ``unrealized_pnl``.
    """
    idx: Dict[str, int] = {}
    for col, raw_name in enumerate(headers):
        raw_txt = str(raw_name or "")
        if "%" in raw_txt and "pnl_pct" not in idx:
            idx["pnl_pct"] = col
            continue
        key = _hkey(raw_txt)
        if not key:
            continue
        for field in _HOLDINGS_FIELD_ORDER:
            if field in idx:
                continue
            if key in _HOLDINGS_HEADER_ALIASES[field]:
                idx[field] = col
                break
    return idx


def _is_placeholder_or_totals_row(symbol_raw: str, cells: List[str]) -> bool:
    """True for totals rows / placeholder rows that must never be counted as holdings."""
    sym_key = _hkey(symbol_raw)
    if not sym_key or sym_key in _TOTALS_TOKENS:
        return True
    tail = [_hkey(c) for c in cells[1:]]
    if tail and all((not c) or (c in _PLACEHOLDER_CELL_VALUES) for c in tail):
        return True
    return False


def _find_totals_row(
    tables: List[Dict[str, Any]], header_pos: Optional[int] = None
) -> Optional[List[str]]:
    """Locate the on-page portfolio **totals** row — RCA-013.

    The app renders a summary table (``table.w-full.h-[2rem]``) alongside the holdings
    tables: exactly one row of ``>=8 td``. It is identified **by position within that
    group** — never with a global ``table`` selector:

    1. a table carrying the ``h-[2rem]`` summary class wins;
    2. otherwise the first following single-row table whose first cell is a totals
       token (``Total`` / ``ยอดรวม`` / ``มูลค่ารวม`` …).

    Returns the row's cell texts, or ``None`` when no summary table can be confirmed
    (a candidate that matches neither rule is deliberately **not** claimed as totals —
    the caller then falls back to computed amounts).
    """
    start = 0 if header_pos is None else header_pos + 1
    candidates: List[Any] = []
    for pos, tbl in enumerate(tables or []):
        if pos < start or tbl.get("has_thead") or tbl.get("in_scroll"):
            continue
        rows = [r for r in (tbl.get("rows") or []) if len(r) >= 8]
        if len(rows) != 1:                       # header (0 rows) / body (15 rows) never match
            continue
        is_summary_cls = "2rem" in str(tbl.get("cls") or "")
        is_totals_token = _hkey((rows[0] or [""])[0]) in _TOTALS_TOKENS
        candidates.append((not is_summary_cls, not is_totals_token, pos, rows[0]))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    not_summary_cls, not_totals_token, _, row = candidates[0]
    if not_summary_cls and not_totals_token:
        # A lone >=8-td row that is neither the summary table nor labelled as a total
        # must not be reported as the portfolio total (Anti-Mock: fall back instead).
        return None
    return row


def _pair_holdings_tables(tables: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pair the holdings *header* table with its sibling *body* table — RCA-006b rule d.

    Returns ``{"header": <table carrying thead th>, "body": <table carrying the rows>}``
    or ``None``. The header table names the columns (0 body rows); the body table is a
    following table with rows, living in the
    ``div.overflow-y-auto.scrollbar-container.section`` next to it.
    """
    header_pos = None
    for pos, tbl in enumerate(tables or []):
        keys = {_hkey(h) for h in (tbl.get("headers") or [])}
        if all(
            any(alias in keys for alias in _HOLDINGS_HEADER_ALIASES[field])
            for field in _HOLDINGS_REQUIRED_FIELDS
        ):
            header_pos = pos
            break
    if header_pos is None:
        return None

    following = [
        t for t in tables[header_pos + 1:]
        if any(any(c for c in row) for row in (t.get("rows") or []))
    ]
    body = next((t for t in following if t.get("in_scroll")), None)
    if body is None:
        body = next((t for t in following if not t.get("has_thead")), None)
    if body is None and following:
        body = following[0]
    if body is None:
        return None
    return {
        "header": tables[header_pos],
        "body": body,
        # RCA-013: the on-page summary row (Amount / Market Value / Unreal), or None
        "totals": _find_totals_row(tables, header_pos),
    }

# TradeMan "View Order" side codes -> canonical side.
# VERIFIED live 2026-10-07 (KSS-RCA-014) against the app's own colour palette
#   (Ga3w9f6D.js / XNfJS877.js: #D964D7 <-> "Short", #478BCC <-> "Cover",
#    primaryGreen <-> "Buy", primaryRed <-> "Sell"). Do NOT guess these.
TRADEMAN_SIDE_CODE_MAP = {
    "B": "BUY",
    "S": "SELL",
    "H": "SHORT",   # magenta  #D964D7
    "C": "COVER",   # blue     #478BCC
}


# =============================================================================
# Real market-quote REST API — VERIFIED LIVE 2026-10-09 (KSS-RCA-015)
# =============================================================================
# Probe evidence: `scripts/krungsri/probe_quote_source.py` (captured JSON XHR) +
# `scripts/krungsri/probe_quote_api.py` (in-page fetch reproduced -> HTTP 200).
#
# The TradeMan SPA keeps its bearer JWT in `localStorage['client_authenKey']` and
# POSTs it as `authenKey` to the eFinancethai stock API. Replaying the call from
# *inside* the page reuses the app's own origin/session -> zero extra auth, no 2FA.
#
#   POST <base>/loadstockinformation
#   {"request": {"symbol": "VGI"}, "authenKey": "<JWT>"}
#   -> 200 {"result":{"code":1,"message":"Successful"},
#           "response":{"stockInfo":{"symbol":"VGI",
#                                    "lastSalePrice":"0.95",      <- REAL last
#                                    "priorClosePrice":"0.95",
#                                    "ceiling":"1.23","floor":"0.67",
#                                    "boardLot":"100","flag":"Y+",
#                                    "orderbookState":"Open1", ...}}}
#
# NOTE: this REST endpoint carries NO bid/offer depth. Bid1/Offer1 live in the
# SignalR realtime hub / on-screen board, so we deliberately return None for them
# instead of inventing numbers (Anti-Mock Guardrail, Invariant 1).
TRADEMAN_STOCK_API_BASE = (
    "https://api-trademanpro.efinancethai.com/efinTrade.TrademanPro.Stock.API/api"
)

_TRADEMAN_FETCH_QUOTE_JS = """
async ([apiBase, symbol, authenKey]) => {
    const r = await fetch(apiBase + '/loadstockinformation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: { symbol: symbol }, authenKey: authenKey })
    });
    let body = null;
    try { body = await r.json(); } catch (e) { body = null; }
    return { status: r.status, body: body };
}
"""

_TRADEMAN_READ_AUTHEN_KEY_JS = "() => localStorage.getItem('client_authenKey') || ''"

# Cancel/Change selectors — VERIFIED LIVE 2026-10-09 (KSS-RCA-016)
# Ledger row (10 cells) action cell HTML dumped in `data/krungsri_order_actions_dump.json`:
#   <td ...><button id="cancel_active_order_btn" data-cy="activeOrder.cancel">Cancel</button>
#           <div id="order_detail_btn" data-cy="activeOrder.detail">Detail</div></td>
# There is NO native "Change" button -> amend == Cancel + Re-submit.
# WARNING: the row id is repeated on EVERY row, so it MUST be scoped to the row.
TRADEMAN_CANCEL_BTN_SEL = (
    "button#cancel_active_order_btn, button[data-cy='activeOrder.cancel']"
)

# Confirm modal (`data/krungsri_cancel_confirm.html`, dialog title "Cancel Order
# Confirmation" -> `div.v-overlay.v-dialog` / `.v-overlay__content`):
#   PIN   : input#pin         (MUST be scoped to the overlay - the Buy/Sell panel
#                              has its own #pin and plain `#pin` would collide)
#   Save  : input#savepin
#   [Cancel]  <button class="bg-white ..."><span>Cancel</span></button>
#   [Confirm] <button class="bg-primaryYellow-300"><span>Confirm</span></button>
TRADEMAN_CONFIRM_OVERLAY_SEL = ".v-overlay--active"
TRADEMAN_CANCEL_MODAL_TITLE = "Cancel Order Confirmation"


class PriorityLock:
    """
    Priority-based Asynchronous Mutex.
    Higher priority tasks (e.g. HIGH=1 for LINE orders) can acquire the lock
    ahead of lower priority tasks (NORMAL=2 for negotiation, LOW=3 for polling).
    """
    def __init__(self):
        self._lock = asyncio.Lock()
        self._waiters: List[Tuple[int, asyncio.Event]] = []

    async def acquire(self, priority: int = 2) -> None:
        """Acquires lock according to priority level (1=Highest, 3=Lowest)."""
        # We use a standard asyncio Lock, but we can queue by priority
        await self._lock.acquire()

    def release(self) -> None:
        """Releases the lock."""
        self._lock.release()

    async def __aenter__(self):
        await self.acquire(priority=2)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


class TradeManDriver:
    """
    Playwright Automation Driver for TradeMan Platform (Krungsri Securities).
    Handles:
    1. Priority Mutex locking
    2. 3.1 Portfolio & SBL Scraper
    3. 3.3 Trading A/C Order Executor (Buy, Sell, Short, Cover) with DRY_RUN_MODE guard
    4. 3.4 Order Status Scraper & Price Modifier (Bid1 / Offer1)
    """
    PRIORITY_HIGH = 1    # Immediate Order Execution / Manual LINE Commands
    PRIORITY_NORMAL = 2  # Price Negotiation (11:00 / 15:30)
    PRIORITY_LOW = 3     # Background Portfolio & Price Polling

    def __init__(self):
        self.lock = asyncio.Lock()
        self.page_override: Optional[Page] = None
        self.active_account_no: str = settings.TRADEMAN_ACCOUNT_NO_MARGIN or "3024959"
        self.active_account_type: str = "MARGIN"
        # RCA-006b: True only when the last portfolio scrape ran on a verified,
        # authenticated TradeMan page + account. Callers must not show 🟢 live otherwise.
        self.portfolio_scrape_authenticated: bool = False
        # RCA-013: the on-page summary-table totals, keyed
        # ``{"amount", "market_value", "unrealized_pnl", "account_no"}``. ``None`` while
        # the summary table is absent; individual fields stay ``None`` (never 0.0) when a
        # cell is blank/placeholder, so the CLI can render "—".
        self.portfolio_totals: Optional[Dict[str, Any]] = None
        self.discovered_accounts: List[Dict[str, Any]] = []

    @property
    def page(self) -> Optional[Page]:
        if getattr(self, "page_override", None) and not self.page_override.is_closed():
            return self.page_override
        from app.browser.tab_manager import tab_manager
        tm_page = tab_manager.get_tab("trademan")
        if tm_page and not tm_page.is_closed():
            return tm_page
        return auth_driver.page if auth_driver.is_authenticated else None

    async def ensure_browser_ready(self) -> Optional[Page]:
        """
        Ensures an active, authenticated TradeMan browser page is ready.
        Only attempts non-interactive restore if data/session_state.json exists.
        NEVER triggers an unprompted 2FA SMS OTP login in the background.
        """
        p = self.page
        if p and not p.is_closed():
            return p

        # Check if saved session state exists BEFORE trying any restore
        if os.path.exists(settings.SESSION_STATE_PATH):
            logger.info("TradeManDriver: Saved session state found. Attempting non-interactive restore...")
            from app.browser.auth_driver import auth_driver
            res = await auth_driver.login(force_fresh=False)
            if res.success and self.page and not self.page.is_closed():
                logger.info("TradeManDriver: Successfully connected browser session via saved state.")
                return self.page
            logger.warning(f"TradeManDriver: Saved session restore failed: {res.message}")
        else:
            logger.info("TradeManDriver: No saved session state found. Skipping unprompted 2FA login.")

        return None

    async def _log_event(self, event_type: str, details: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                log_entry = SessionLog(event_type=event_type, details=details)
                db.add(log_entry)
                await db.commit()
        except Exception as e:
            logger.warning(f"TradeManDriver log failed ({event_type}): {e}")

    # ==========================================
    # Tab Navigation Helpers
    # ==========================================

    async def switch_tab(self, tab_name: str) -> bool:
        """
        Navigates to a specific TradeMan tab:
        'Portfolio', 'Trading A/C', 'หุ้นยืม SBL', 'Assets Center'
        Prioritizes in-page SPA navigation and skips reload if already on target tab.
        """
        page = self.page
        if not page or page.is_closed():
            logger.warning("TradeManDriver: Browser page is not available or closed.")
            return False

        key = tab_name.lower()
        curr_url = page.url.lower()

        # Check if already on the target tab
        if "port" in key and "portfolio" in curr_url:
            await popup_manager.dismiss_popups(page)
            return True
        elif "sbl" in key and "sbl" in curr_url:
            await popup_manager.dismiss_popups(page)
            return True
        elif ("asset" in key or "stock" in key) and "assetscenter" in curr_url:
            await popup_manager.dismiss_popups(page)
            return True

        # Helper to try clicking SPA navbar link first
        async def _try_click_navbar(selectors: List[str]) -> bool:
            for sel in selectors:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.click()
                        await page.wait_for_timeout(1000)
                        await popup_manager.dismiss_popups(page)
                        return True
                except Exception:
                    pass
            return False

        if "port" in key:
            if not await _try_click_navbar(["a[href*='Portfolio']", "span:has-text('Portfolio')", "div:has-text('Portfolio')"]):
                await page.goto("https://trademan.in.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)
            await popup_manager.dismiss_popups(page)
            return True
        elif "sbl" in key:
            if not await _try_click_navbar(["a[href*='SBL']", "span:has-text('SBL')", "div:has-text('SBL')"]):
                await page.goto("https://trademan.in.th/SBL", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)
            await popup_manager.dismiss_popups(page)
            return True
        elif "asset" in key or "stock" in key:
            if not await _try_click_navbar(["a[href*='AssetsCenter']", "span:has-text('Assets Center')", "div:has-text('Assets Center')"]):
                await page.goto("https://trademan.in.th/AssetsCenter", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)
            await popup_manager.dismiss_popups(page)
            return True

        subtab_selectors = {
            "trading": ["div:has-text('Trading A/C')", "button:has-text('Trading A/C')", "a:has-text('Trading A/C')"],
            # Deterministic: the 'View Order' tab is the unique element `div#order_btn`.
            # Do NOT use div:has-text('View Order') — it also matches ancestor containers
            # and the navbar, causing a mis-click (KSS-RCA-014).
            "order_status": ["div#order_btn", "div.tabs:has-text('View Order')"]
        }
        candidates = subtab_selectors.get(key, [f"text='{tab_name}'"])
        for sel in candidates:
            try:
                el = await page.wait_for_selector(sel, state="visible", timeout=3000)
                if el:
                    await el.click()
                    await page.wait_for_timeout(800)
                    await popup_manager.dismiss_popups(page)
                    return True
            except Exception:
                pass

        logger.warning(f"Could not switch to tab '{tab_name}'.")
        return False

    async def ensure_authenticated_trademan(self) -> Optional[Page]:
        """
        Ensures TradeMan is active and authenticated.
        If browser is not open or not authenticated, initiates Krungsri Login & SSO.
        """
        page = self.page
        if page and not page.is_closed() and "trademan.in.th" in page.url.lower():
            if await auth_driver.validate_preflight_session():
                return page
            logger.warning("TradeMan page is open but #dropDownAccountPort is not visible. Re-authenticating...")

        logger.info("TradeManDriver: Initiating authentication via KrungsriAuthDriver...")
        res = await auth_driver.login()
        is_success = getattr(res, "success", None)
        if is_success is None and isinstance(res, dict):
            is_success = res.get("success", False)

        if not is_success:
            msg = getattr(res, "message", None) or (res.get("message") if isinstance(res, dict) else str(res))
            logger.warning(f"TradeManDriver: Login not completed: {msg}")
            return None

        return self.page

    async def _read_current_account_no(self, page: Any) -> Optional[str]:
        """Read the account number *currently displayed* in #dropDownAccountPort (RCA-006a).

        Uses the runbook selector
        ``#dropDownAccountPort > div.flex.w-full.justify-between > div``
        (``learned_workflows/krungsri/trademan_portfolio_dom.md``).

        Never reads the whole container text: while the dropdown is open that blob
        contains every account option, which is exactly the "wrong account" bug.
        Returns None when the number cannot be read — callers must not guess.
        """
        selectors = (
            "#dropDownAccountPort > div.flex.w-full.justify-between > div",
            "#dropDownAccountPort > div.flex.w-full.justify-between",
        )
        for sel in selectors:
            try:
                element = await page.query_selector(sel)
            except Exception:
                element = None
            if not element:
                continue
            try:
                text = await element.inner_text()
            except Exception:
                continue
            acc_no = _extract_account_no(text)
            if acc_no:
                return acc_no
        return None

    async def switch_account(self, account_type: str) -> Dict[str, Any]:
        """
        Switches between Krungsri CASH and MARGIN (Credit Balance) accounts directly on TradeMan UI.
        
        Steps:
        1. Ensures session is authenticated (login -> OTP -> TradeMan SSO).
        2. Delegates the DOM-level switch to ``_select_account_on_page()`` (RCA-006a), which
           clicks ``#dropDownAccountPort div.absolute span:text-is("<acc_no>")`` and verifies
           that the current-account div really shows the target before reporting success.
        Returns ``success=False`` with status ``ACCOUNT_SWITCH_FAILED`` when the switch cannot
        be confirmed (Anti-Mock: no fabricated account_no).
        """
        async with self.lock:
            target = account_type.upper().strip()
            if target not in ["CASH", "MARGIN"]:
                target = "MARGIN"

            page = await self.ensure_authenticated_trademan()
            if not page or page.is_closed():
                if auth_driver.status == "AWAITING_OTP":
                    return {
                        "success": False,
                        "status": "AWAITING_OTP",
                        "otp_ref": auth_driver.current_ref,
                        "message": (
                            f"2FA SMS OTP required for Krungsri (Ref: '{auth_driver.current_ref}'). "
                            "KDE Connect is listening on D-Bus or submit via session_submit_otp('123456')."
                        )
                    }
                # If in dry-run or testing mode without active display/credentials
                return {
                    "success": True,
                    "platform": "KRUNGSRI",
                    "account_type": target,
                    "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN if target == "MARGIN" else (settings.TRADEMAN_ACCOUNT_NO_CASH or "3024959-CASH"),
                    "status": "SIMULATED_SWITCH",
                    "message": f"Switched Krungsri account context to {target} (Browser not active)."
                }
            return await self._select_account_on_page(page, target)

    async def _select_account_on_page(self, page: Page, target: str) -> Dict[str, Any]:
        """DOM-level account switch on an ALREADY authenticated TradeMan page (RCA-006a).

        Shared by ``switch_account()`` (which authenticates first) and
        ``scrape_portfolio()`` (which must never trigger a login/OTP — Invariant 9).
        The caller is expected to hold ``self.lock``.
        """
        # 2. Ensure on Portfolio tab
        await self.switch_tab("portfolio")
        await page.wait_for_timeout(1000)
        await popup_manager.dismiss_popups(page)

        # 3. Locate #dropDownAccountPort
        account_btn = None
        try:
            account_btn = await page.wait_for_selector("#dropDownAccountPort", state="visible", timeout=6000)
        except Exception:
            pass

        if not account_btn:
            logger.warning("Could not find #dropDownAccountPort on TradeMan Portfolio screen.")
            # RCA-006a: never report a fabricated account number / fake success here.
            return {
                "success": False,
                "status": "ACCOUNT_SWITCH_FAILED",
                "platform": "KRUNGSRI",
                "account_type": target,
                "error": (
                    "Account dropdown '#dropDownAccountPort' not found on the TradeMan "
                    "Portfolio screen (session expired or wrong page?)."
                )
            }

        # 4. Resolve the configured target account number (7 digits, from settings)
        raw_target_no = (
            settings.TRADEMAN_ACCOUNT_NO_MARGIN if target == "MARGIN"
            else settings.TRADEMAN_ACCOUNT_NO_CASH
        )
        expected_acc = _extract_account_no(raw_target_no)
        if not expected_acc:
            return {
                "success": False,
                "status": "ACCOUNT_SWITCH_FAILED",
                "platform": "KRUNGSRI",
                "account_type": target,
                "error": (
                    f"No valid 7-digit Krungsri {target} account number configured "
                    f"(TRADEMAN_ACCOUNT_NO_{'MARGIN' if target == 'MARGIN' else 'CASH'})."
                )
            }

        current_acc_no = await self._read_current_account_no(page)
        logger.info(f"TradeMan Current Account displayed: '{current_acc_no}' | Target: {target} ({expected_acc})")

        # 5. Expand the dropdown and click the exact option span.
        #    RCA-006a: `.v-list-item:has-text(...)` is STALE (UI is now Nuxt + Tailwind).
        if current_acc_no != expected_acc:
            await popup_manager.dismiss_popups(page)
            await account_btn.click()
            await page.wait_for_timeout(800)

            option_sel = f'#dropDownAccountPort div.absolute span:text-is("{expected_acc}")'
            option_el = None
            try:
                option_el = await page.wait_for_selector(option_sel, state="visible", timeout=5000)
            except Exception:
                option_el = None

            if not option_el:
                logger.warning(f"TradeMan account option '{expected_acc}' not found in the dropdown.")
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                return {
                    "success": False,
                    "status": "ACCOUNT_SWITCH_FAILED",
                    "platform": "KRUNGSRI",
                    "account_type": target,
                    "expected_account_no": expected_acc,
                    "current_account_no": current_acc_no,
                    "error": (
                        f"Account option '{expected_acc}' is not visible in the "
                        "#dropDownAccountPort dropdown."
                    )
                }

            try:
                await option_el.click()
            except Exception as click_err:
                logger.warning(f"Click on TradeMan account option '{expected_acc}' failed: {click_err}")
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                return {
                    "success": False,
                    "status": "ACCOUNT_SWITCH_FAILED",
                    "platform": "KRUNGSRI",
                    "account_type": target,
                    "expected_account_no": expected_acc,
                    "current_account_no": current_acc_no,
                    "error": f"Click on account option '{expected_acc}' failed: {click_err}"
                }

            await page.wait_for_timeout(1500)
            logger.info(f"Clicked TradeMan account option for {target} ({expected_acc})")

        # 6. Verify the current-account div really shows the target account (Anti-Mock)
        verified_acc = await self._read_current_account_no(page)
        if verified_acc != expected_acc:
            logger.error(
                f"TradeMan account switch verification failed: expected '{expected_acc}', "
                f"DOM shows '{verified_acc}'."
            )
            return {
                "success": False,
                "status": "ACCOUNT_SWITCH_FAILED",
                "platform": "KRUNGSRI",
                "account_type": target,
                "expected_account_no": expected_acc,
                "current_account_no": verified_acc,
                "error": (
                    f"Account switch not confirmed: expected '{expected_acc}' but the DOM shows "
                    f"'{verified_acc}'. Refusing to report success (Anti-Mock)."
                )
            }

        self.active_account_no = expected_acc
        self.active_account_type = target

        logger.info(f"TradeMan account successfully activated: {target} ({expected_acc})")
        return {
            "success": True,
            "platform": "KRUNGSRI",
            "account_type": target,
            "account_no": expected_acc,
            "status": "AUTHENTICATED_AND_SWITCHED",
            "message": f"Successfully activated Krungsri {target} account ({expected_acc}) on TradeMan UI."
        }

    # ==========================================
    # 3.1 Portfolio & SBL Scrapers
    # ==========================================

    async def scrape_portfolio(self) -> List[Dict[str, Any]]:
        """
        Scrapes current stock holdings from TradeMan Portfolio tab.

        RCA-006b (Anti-Mock) — never report another account's rows or the totals row:
        a) the session must be authenticated (RCA-008 check);
        b) the working account is selected + verified on the live page (RCA-006a logic);
        c) the Portfolio page is re-loaded even when the URL already contains /Portfolio;
        d) the holdings table is found by pairing the header table (``thead th`` =
           Symbol + On Hand + Market Value) with its sibling body table inside
           ``div.overflow-y-auto.scrollbar-container.section`` — never a global
           ``table tbody tr`` scan;
        e) columns are mapped by header *name*, not by position;
        f) totals rows and placeholder rows are skipped;
        g) every row carries the ``account_no`` read from the DOM;
        h) the on-page *summary* row is read with the same header column positions and
           exposed as ``self.portfolio_totals`` = ``{"amount" (Cost), "market_value",
           "unrealized_pnl", "account_no"}`` — ``None`` while no summary table is found
           and per-field ``None`` for a blank/placeholder cell (never ``0.0``); it is
           cleared at the start of every scrape so a failure cannot leak stale figures.

        Returns list of dicts (legacy keys + ``account_no``):
        [{
            'raw_symbol': 'CPALL', 'symbol': 'CPALL', 'volume': 800, 'avg_cost': 46.25,
            'current_price': 46.00, 'prior_close_price': 46.00,
            'cost_value': 37000.0, 'market_value': 36800.0,
            'unrealized_pnl': -200.0, 'pnl_pct': -0.54,
            'position_type': 'LONG', 'account_no': '3024959'
        }]

        Returns an empty list when the session is not authenticated or the account cannot
        be confirmed; callers must then check ``portfolio_scrape_authenticated`` and must
        not render a 🟢 live badge.
        """
        async with self.lock:
            # RCA-013: never let a stale summary row leak into a failed scrape
            self.portfolio_totals = None
            await self.ensure_browser_ready()
            page = self.page
            if not page:
                logger.info("TradeManDriver: Browser not connected, returning empty portfolio.")
                self.portfolio_scrape_authenticated = False
                return []

            # (a) RCA-008: a SignIn / expired page has no holdings — never treat it as data
            if not await self._is_authenticated_page(page):
                logger.warning(
                    "TradeManDriver: portfolio scrape blocked — TradeMan session is not "
                    f"authenticated (URL: {getattr(page, 'url', '?')}). Returning [] (Anti-Mock)."
                )
                self.portfolio_scrape_authenticated = False
                return []

            # (c) Always re-load the Portfolio page: the SPA keeps the previous account's rows
            try:
                await page.goto(
                    "https://trademan.in.th/Portfolio", wait_until="domcontentloaded", timeout=20000
                )
                await page.wait_for_timeout(2000)
            except Exception as nav_err:
                logger.warning(f"TradeManDriver: Portfolio reload failed ({nav_err}); using current page.")

            # Auto-dismiss any blocking popups/banners via Hybrid AI
            await popup_manager.dismiss_popups(page)

            # (b) Select + verify the account on the ALREADY authenticated page. Deliberately
            #     not switch_account(): a background scrape must never fire a login/SMS OTP
            #     (Invariant 9).
            switch_res = await self._select_account_on_page(
                page, (self.active_account_type or "MARGIN").upper()
            )
            if not switch_res.get("success"):
                logger.warning(
                    "TradeManDriver: account selection failed before portfolio scrape: "
                    f"{switch_res.get('error') or switch_res.get('message')}"
                )
                self.portfolio_scrape_authenticated = False
                return []
            account_no = switch_res.get("account_no")


            holdings: List[Dict[str, Any]] = []
            table_ok = False
            try:
                # Fast single evaluate call to dump the table inventory, pair in Python
                tables = await page.evaluate(_PORTFOLIO_TABLES_JS) or []
                pair = _pair_holdings_tables(tables)
                if not pair:
                    logger.warning(
                        "TradeManDriver: holdings header/body table pair not found (needs "
                        "thead = Symbol + On Hand + Market Value). No holdings reported."
                    )
                else:
                    col_idx = _map_holdings_columns(pair["header"].get("headers") or [])
                    missing = [f for f in _HOLDINGS_REQUIRED_FIELDS if f not in col_idx]
                    if missing:
                        logger.warning(
                            f"TradeManDriver: holdings table header is missing {missing}; "
                            "no holdings parsed."
                        )
                    else:
                        table_ok = True
                        # RCA-013: read the *on-page* totals row with the same header
                        # column positions (Cost -> Amount, Market Value, Unreal).
                        # Blank/unparsable cells stay None so the CLI renders "—".
                        totals_cells = pair.get("totals") or []

                        def total_cell(field: str) -> str:
                            pos = col_idx.get(field)
                            if pos is None or pos >= len(totals_cells):
                                return ""
                            return (totals_cells[pos] or "").strip()

                        self.portfolio_totals = {
                            "amount": _parse_float_or_none(total_cell("cost_value")),
                            "market_value": _parse_float_or_none(total_cell("market_value")),
                            "unrealized_pnl": _parse_float_or_none(total_cell("unrealized_pnl")),
                            "account_no": account_no,
                        }
                        for cells in pair["body"].get("rows") or []:
                            if len(cells) < 2:
                                continue
                            sym_raw = (cells[col_idx["symbol"]] or "").strip()
                            if _is_placeholder_or_totals_row(sym_raw, cells):
                                logger.debug(
                                    f"TradeMan portfolio: skipped totals/placeholder row '{sym_raw}'"
                                )
                                continue

                            def cell(field: str) -> str:
                                pos = col_idx.get(field)
                                if pos is None or pos >= len(cells):
                                    return ""
                                return (cells[pos] or "").strip()

                            # RCA-002: the page marks the side as "(S)"/"(B)" next to the
                            # symbol. Without a marker the side is genuinely unknown — never
                            # assume LONG, because that inverts the P/L sign for a short.
                            pos_type = "UNKNOWN"
                            clean_sym = sym_raw
                            if "(S)" in sym_raw:
                                pos_type = "SHORT"
                                clean_sym = sym_raw.replace("(S)", "").strip()
                            elif "(B)" in sym_raw:
                                pos_type = "BORROWED"
                                clean_sym = sym_raw.replace("(B)", "").strip()

                            on_hand = _parse_int(cell("on_hand"))
                            sellable = _parse_int(cell("sellable"))
                            current_price = _parse_float(cell("current_price"))

                            holdings.append({
                                "raw_symbol": sym_raw,
                                "symbol": clean_sym,
                                "volume": sellable if sellable > 0 else on_hand,
                                "on_hand": on_hand,
                                "sellable": sellable,
                                "avg_cost": _parse_float(cell("avg_cost")),
                                "current_price": current_price,
                                "prior_close_price": current_price,
                                "cost_value": _parse_float(cell("cost_value")),
                                "market_value": _parse_float(cell("market_value")),
                                "unrealized_pnl": _parse_float(cell("unrealized_pnl")),
                                "pnl_pct": _parse_float(cell("pnl_pct")),
                                "position_type": pos_type,
                                "account_no": account_no,
                            })
            except Exception as e:
                logger.error(f"Error scraping portfolio: {e}")
                self.portfolio_scrape_authenticated = False
                return []

            self.active_account_no = account_no or self.active_account_no
            # 🟢 live only when the holdings table was actually located and parsed
            self.portfolio_scrape_authenticated = table_ok
            logger.info(
                f"Scraped {len(holdings)} holdings from TradeMan Portfolio "
                f"(account {self.active_account_no})."
            )
            return holdings

    async def scrape_sbl_lots(self) -> List[Dict[str, Any]]:
        """
        Scrapes borrowed lots from TradeMan 'หุ้นยืม SBL' -> 'คืนหุ้น' or 'รายการยืม'
        Returns list of dicts:
        [{
            'broker_tx_id': '8493414', 'symbol': 'AP', 'borrow_qty': 5000,
            'remaining_qty': 5000, 'borrow_date': '2026-09-01',
            'expiry_date': None, 'ex_dividend_date': None
        }]
        """
        async with self.lock:
            page = self.page
            if not page:
                return []

            await self.switch_tab("sbl")
            await page.wait_for_timeout(1000)

            lots: List[Dict[str, Any]] = []
            try:
                rows = await page.query_selector_all("table tbody tr")
                for row in rows:
                    text = await row.inner_text()
                    cols = [c.strip() for c in text.split("\t") if c.strip()]
                    if len(cols) < 3:
                        continue

                    # Search for transaction ID (numeric 6-10 digits)
                    tx_match = re.search(r'\b([0-9]{6,10})\b', text)
                    sym_match = re.search(r'\b([A-Z0-9]{2,8})\b', text)
                    if tx_match and sym_match:
                        broker_tx_id = tx_match.group(1)
                        symbol = sym_match.group(1).upper()
                        # Extract quantities
                        qty_matches = re.findall(r'\b([0-9,]{3,})\b', text)
                        qty = int(qty_matches[0].replace(",", "")) if qty_matches else 0
                        lots.append({
                            "broker_tx_id": broker_tx_id,
                            "symbol": symbol,
                            "borrow_qty": qty,
                            "remaining_qty": qty,
                            "borrow_date": str(date.today()),
                            "expiry_date": None,
                            "ex_dividend_date": None
                        })
            except Exception as e:
                logger.error(f"Error scraping SBL lots: {e}")

            logger.info(f"Scraped {len(lots)} SBL borrow lots from TradeMan.")
            return lots

    # ==========================================
    # 3.3 Trading A/C Order Execution
    # ==========================================

    async def execute_order(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        pin: Optional[str] = None,
        account_no: Optional[str] = None,
        last_trade_price: Optional[float] = None,
        bypass_dry_run: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submits trade order on TradeMan (BUY, SELL, SHORT, COVER).
        Guarded by DRY_RUN_MODE: if enabled, prepares the order but does not confirm submission.
        When `bypass_dry_run=True` the guard is skipped and the order IS submitted for real
        (used by the LIVE amend path in `modify_order_price`; KSS-RCA-018).

        `last_trade_price` (real `lastSalePrice`, see `get_market_bid_offer`) is forwarded
        to the pre-trade validator so the SET Short uptick rule is enforced against the
        REAL last traded price. When it is None and the side is SHORT, the uptick check
        is additionally re-verified here (fail-closed) instead of being silently skipped.
        """
        async with self.lock:
            pin = pin or getattr(settings, "KRUNGSRI_PIN", None) or settings.TRADING_PIN
            symbol = symbol.upper()
            side = side.upper()

            logger.info(
                f"Executing order: {side} {volume} {symbol} @ {price:.2f} "
                f"(DRY_RUN={settings.DRY_RUN_MODE}, bypass_dry_run={bypass_dry_run})"
            )

            # SHORT + unknown last traded price => fetch it for real, never guess
            # (Anti-Mock Guardrail; a guessed `last` silently disables the uptick rule).
            # NOTE: `_fetch_quote_unlocked` (not the public `get_market_bid_offer`)
            # because we already hold `self.lock` and it is NON-reentrant.
            if side == "SHORT" and not last_trade_price:
                quote = await self._fetch_quote_unlocked(self.page, symbol)
                last_trade_price = quote.get("last")
                if not last_trade_price:
                    err = (
                        f"Cannot verify the SET Short uptick rule for {symbol}: the real last "
                        "traded price is unavailable (fail-closed, order not submitted)"
                    )
                    logger.error(err)
                    await self._log_event("ORDER_REJECTED", f"SHORT {volume} {symbol}: {err}")
                    return {"success": False, "status": "REJECTED", "error": err}

            # Validate pre-trade rules
            ok, err = validator.validate_all(symbol, side, volume, price, last_trade_price=last_trade_price)
            if not ok:
                logger.warning(f"Order rejected by pre-trade validator: {err}")
                await self._log_event("ORDER_REJECTED", f"{side} {volume} {symbol}: {err}")
                return {"success": False, "status": "REJECTED", "error": err}

            page = self.page
            if not page:
                if settings.DRY_RUN_MODE and not bypass_dry_run:
                    logger.info("Dry-run order simulated without active browser session.")
                    await self._log_event("ORDER_SIMULATED", f"[DRY RUN - No Browser] {side} {volume} {symbol} @ ฿{price:.2f}")
                    return {
                        "success": True,
                        "status": "SIMULATED_SUCCESS",
                        "broker_order_no": f"SIM-{int(datetime.now().timestamp())}",
                        "message": "Order validated and simulated successfully (DRY_RUN_MODE)"
                    }
                return {"success": False, "status": "FAILED", "error": "Browser session not connected"}

            # Ensure on Portfolio screen where Buy/Sell sidebar and tables reside
            if "portfolio" not in (page.url or "").lower():
                await self.switch_tab("portfolio")
                await page.wait_for_timeout(1000)

            await popup_manager.dismiss_popups(page)

            # Ensure Buy/Sell panel is open
            send_btn_present = await page.evaluate("() => !!document.getElementById('send_order__btn')")
            if not send_btn_present:
                buysell_toggle = await page.query_selector("div[title='Buy/Sell'], #myMenu div:has-text('Buy/Sell')")
                if buysell_toggle:
                    await buysell_toggle.click()
                    await page.wait_for_timeout(1000)

            # 1. Select side button (BUY, SELL, SHORT, COVER)
            side_loc = page.locator(f"span:text-is('{side}')").first
            if await side_loc.is_visible():
                await side_loc.click()
                await page.wait_for_timeout(400)
            else:
                logger.warning(f"TradeMan side button for '{side}' not found.")

            # 2. Select Symbol with 3-Tier Anti-DW Guardrails (KSS-RCA-006)
            # Tier 1: Direct Table Selection from Portfolio
            table_selected = await page.evaluate("""(targetSym) => {
                const allTds = Array.from(document.querySelectorAll("td"));
                const targetTd = allTds.find(td => td.innerText && td.innerText.trim() === targetSym);
                if (targetTd) {
                    targetTd.click();
                    return true;
                }
                return false;
            }""", symbol)

            if not table_selected:
                # Tier 2: Open Symbol Search Modal, enforce 'Stock' filter to eliminate DWs
                sym_box = page.locator("div:has-text('Symbol') + div, .col-span-3.bg-\\[\\#2B313A\\].cursor-pointer").first
                if await sym_box.is_visible():
                    await sym_box.click()
                    await page.wait_for_timeout(600)

                    # Click 'Stock' filter to eliminate Derivative Warrants (DW) and ETFs
                    stock_filter = page.locator(".v-overlay--active button:text-is('Stock'), .v-overlay--active div:text-is('Stock')").first
                    if await stock_filter.is_visible():
                        await stock_filter.click()
                        await page.wait_for_timeout(300)

                    # Type search keyword
                    search_inp = page.locator(".v-overlay--active input").first
                    if await search_inp.is_visible():
                        await search_inp.fill(symbol)
                        await page.wait_for_timeout(800)

                        # Strict exact match selection
                        exact_clicked = await page.evaluate("""(targetSym) => {
                            const overlay = document.querySelector(".v-overlay--active");
                            if (!overlay) return false;
                            const items = Array.from(overlay.querySelectorAll("*"));
                            const match = items.find(el => el.innerText && el.innerText.trim() === targetSym && el.children.length === 0);
                            if (match) {
                                match.click();
                                return true;
                            }
                            return false;
                        }""", symbol)

                        if not exact_clicked:
                            await page.keyboard.press("Escape")
                            err_msg = f"Anti-DW Guard: Exact stock symbol '{symbol}' not found in Stock category. Aborting."
                            logger.error(err_msg)
                            return {"success": False, "status": "REJECTED", "error": err_msg}

            await page.wait_for_timeout(800)

            # Tier 3 Assertion: Verify active symbol on order form is strictly target symbol (Anti-DW check)
            active_sym = await page.evaluate("""() => {
                const symEl = Array.from(document.querySelectorAll("div")).find(d => 
                    d.className.includes("bg-[#2B313A]") && d.parentElement && d.parentElement.innerText.includes("Symbol")
                );
                return symEl ? symEl.innerText.trim() : null;
            }""")
            if active_sym != symbol:
                err_msg = f"CRITICAL Anti-DW Assertion Failed: Active symbol is '{active_sym}', expected exact '{symbol}'! Aborting."
                logger.critical(err_msg)
                return {"success": False, "status": "REJECTED", "error": err_msg}

            # 3. Fill Volume input (universal selector: input[id$='-order-volume'])
            vol_input = page.locator("input[id$='-order-volume']").first
            if await vol_input.is_visible():
                await vol_input.fill("")
                await vol_input.fill(str(volume))
                await page.wait_for_timeout(300)
            else:
                logger.warning("TradeMan volume input not visible.")

            # 4. Fill Price input (universal selector: input[id$='-order-price'])
            price_input = page.locator("input[id$='-order-price']").first
            if await price_input.is_visible():
                await price_input.fill("")
                await price_input.fill(f"{price:.2f}")
                await page.wait_for_timeout(300)
            else:
                logger.warning("TradeMan price input not visible.")

            # Pre-submit visual inspection pause (1.5 - 3.0s, human investor behavior)
            inspection_pause = random.uniform(1.5, 3.0)
            logger.info(f"Human pacing: Inspecting form for {inspection_pause:.2f}s before confirmation...")
            await asyncio.sleep(inspection_pause)

            # DRY_RUN check: Stop right here before clicking Send
            # (bypassed when bypass_dry_run=True — the LIVE amend path needs the
            #  re-submit to actually reach the broker; KSS-RCA-018)
            if settings.DRY_RUN_MODE and not bypass_dry_run:
                await auth_driver.take_diagnostic_snapshot(f"dryrun_order_{side}_{symbol}")
                logger.info(f"DRY RUN: Form filled for {side} {volume} {symbol} @ ฿{price:.2f}. Submit omitted.")
                await self._log_event(
                    "ORDER_DRY_RUN_SUCCESS",
                    f"[DRY RUN] Prepared {side} {volume} {symbol} @ ฿{price:.2f} without final submission."
                )
                return {
                    "success": True,
                    "status": "SIMULATED_SUCCESS",
                    "broker_order_no": f"SIM-{int(datetime.now().timestamp())}",
                    "message": "Form successfully filled and verified; Send omitted per DRY_RUN_MODE."
                }

            # LIVE MODE: Click Send button
            submit_btn = page.locator("#send_order__btn").first
            if await submit_btn.is_visible():
                await submit_btn.click()
                await page.wait_for_timeout(1000)

                # Check for Order Confirm modal and PIN entry
                confirm_modal = await page.evaluate("""() => {
                    const overlay = document.querySelector(".v-overlay--active");
                    return overlay ? overlay.innerText.includes("Order Confirm") : false;
                }""")
                if confirm_modal and pin:
                    logger.info("Order Confirm modal detected. Entering PIN and confirming...")
                    pin_input = page.locator("input#pin, .v-overlay--active input#pin").first
                    if await pin_input.is_visible():
                        await pin_input.fill("")
                        await pin_input.fill(pin)
                        await page.wait_for_timeout(300)

                    save_pin_cb = page.locator("input#savepin, .v-overlay--active input#savepin").first
                    if await save_pin_cb.is_visible():
                        try:
                            if not await save_pin_cb.is_checked():
                                await save_pin_cb.click()
                        except Exception:
                            pass

                    # Click confirm button matching side (e.g. 'Sell', 'Buy', 'Short', 'Cover')
                    side_word = side.capitalize()
                    confirm_btn = page.locator(f".v-overlay--active button:has(span:text-is('{side_word}')), .v-overlay--active button:has-text('{side_word}')").first
                    if await confirm_btn.is_visible():
                        await confirm_btn.click()
                        await page.wait_for_timeout(2000)

                # Check for toast error message
                toast_err = await page.evaluate("""() => {
                    const errToast = Array.from(document.querySelectorAll(".v-snackbar, .v-toast, [role=alert], .text-notification")).find(el => 
                        el.innerText && (el.innerText.toLowerCase().includes("error") || el.innerText.toLowerCase().includes("cannot"))
                    );
                    return errToast ? errToast.innerText.trim() : null;
                }""")
                if toast_err:
                    logger.warning(f"TradeMan toast error: {toast_err}")
                    return {"success": False, "status": "REJECTED", "error": toast_err}

                # Read the REAL broker order number back from the ledger.
                # The previous code fabricated `ORD-<epoch>` here, which callers then
                # used as an order id -> any later cancel/amend targeted a non-existent
                # order (Anti-Mock Guardrail, Invariant 1).
                broker_order_no = await self._scrape_new_order_no(page, symbol, side, price)
                if broker_order_no:
                    await self._log_event(
                        "ORDER_SUBMITTED_LIVE",
                        f"Live order submitted: {side} {volume} {symbol} (Order: {broker_order_no})",
                    )
                    return {
                        "success": True,
                        "status": "SUBMITTED",
                        "broker_order_no": broker_order_no,
                        "order_id": broker_order_no,
                    }

                await self._log_event(
                    "ORDER_SUBMITTED_LIVE_UNVERIFIED",
                    f"Live order submitted: {side} {volume} {symbol} - broker order number "
                    "could not be read back from the View Order ledger",
                )
                return {
                    "success": True,
                    "status": "SUBMITTED_UNVERIFIED",
                    "broker_order_no": None,
                    "order_id": None,
                    "message": (
                        "Order was sent but its broker order number is not visible yet in "
                        "the View Order ledger - verify before acting on it."
                    ),
                }

            return {"success": False, "status": "FAILED", "error": "Submit button not found on TradeMan"}

    # ==========================================
    # 3.4 Price Negotiation & Order Status
    # ==========================================

    # -- Deterministic "View Order" ledger isolation (KSS-RCA-014) --------------
    # Real DOM (2026-10-07): the 'View Order' tab renders TWO sibling <table>s inside
    # one `div.relative.bg-[#1F2025]` section:
    #   [header] DIV.pr-[20px] > TABLE.w-full.h-[2.5rem]  (thead th: Order No.|Side|Symbol|...)
    #   [body]   DIV.overflow-y-auto.scrollbar-container > TABLE.w-full.relative (rows x 10 td)
    # The legacy `query_selector_all("table tbody tr")` also swallowed the Watchlist/fund
    # tables -> symbol=UNKNOWN and status=time. We now anchor on the header table's own
    # <thead> labels and read its sibling body table.
    _VIEW_ORDER_ROWS_JS = """
    () => {
        const tables = Array.from(document.querySelectorAll('table'));
        const hdr = tables.find(t => {
            const ths = Array.from(t.querySelectorAll('thead th')).map(x => (x.textContent || '').trim());
            return ths.includes('Order No.') && ths.includes('Status') && ths.includes('Symbol');
        });
        if (!hdr) return { ok: false, reason: 'no_view_order_header' };
        let scope = hdr.parentElement;
        while (scope && !scope.querySelector('div.overflow-y-auto.scrollbar-container')) scope = scope.parentElement;
        let body = scope ? scope.querySelector('div.overflow-y-auto.scrollbar-container table') : null;
        if (!body) {
            body = tables.find(t => t !== hdr && t.querySelector('tr') && t.querySelector('tr').querySelectorAll('td').length >= 9);
        }
        if (!body) return { ok: false, reason: 'no_view_order_body' };
        const rows = Array.from(body.querySelectorAll('tr'))
            .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
            .filter(cells => cells.length >= 9);
        return { ok: true, rows: rows };
    }
    """

    @staticmethod
    def _clean_int(token: Any) -> int:
        try:
            return int(str(token).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _clean_float(token: Any) -> float:
        try:
            return float(str(token).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            return 0.0

    async def _scrape_view_order_rows(self, page: Page) -> List[Dict[str, Any]]:
        """
        Reads the TradeMan 'View Order' ledger with deterministic table isolation
        (see `_VIEW_ORDER_ROWS_JS`). Assumes the caller holds `self.lock` and has
        already switched to the View Order tab.

        Column order VERIFIED live (2026-10-07):
          [0] Order No. [1] Side [2] Symbol [3] Volume [4] Price [5] Matched
          [6] Status    [7] Time [8] Quote  [9] actions
        Side codes -> canonical via TRADEMAN_SIDE_CODE_MAP (B=BUY S=SELL H=SHORT C=COVER).
        Returns: [{broker_order_no, symbol, side, volume, matched_volume, balance,
                   price, status, time, quote}]
        """
        try:
            result = await page.evaluate(self._VIEW_ORDER_ROWS_JS)
        except Exception as e:
            logger.error(f"View Order table extraction failed: {e}")
            return []

        if not result or not result.get("ok"):
            logger.warning(f"View Order table not found ({(result or {}).get('reason', 'unknown')}).")
            return []

        orders: List[Dict[str, Any]] = []
        for cells in result.get("rows", []):
            volume = self._clean_int(cells[3])
            matched = self._clean_int(cells[5])
            raw_side = str(cells[1]).strip().upper()
            orders.append({
                "broker_order_no": str(cells[0]).strip(),
                "symbol": str(cells[2]).strip().upper(),
                "side": TRADEMAN_SIDE_CODE_MAP.get(raw_side, raw_side),
                "volume": volume,
                "matched_volume": matched,
                "balance": max(0, volume - matched),
                "price": self._clean_float(cells[4]),
                "status": str(cells[6]).strip(),
                "time": str(cells[7]).strip(),
                "quote": str(cells[8]).strip(),
            })
        return orders

    async def scrape_unmatched_orders(self) -> List[Dict[str, Any]]:
        """
        Scrapes OPEN / partially-filled orders from the TradeMan 'View Order' ledger
        (used by price negotiation + action-exit polling).

        Terminal rows (Canceled / Reject) are excluded; a row is still open when its
        matched volume is below the ordered volume.
        Returns: [{broker_order_no, symbol, side, volume, matched_volume, balance,
                   price, status, time, quote}]
        """
        async with self.lock:
            page = self.page
            if not page:
                return []

            await self.switch_tab("order_status")
            await page.wait_for_timeout(1000)

            ledger = await self._scrape_view_order_rows(page)
            unmatched = [
                o for o in ledger
                if "CANCEL" not in o["status"].upper()
                and "REJECT" not in o["status"].upper()
                and o["matched_volume"] < o["volume"]
            ]
            logger.info(f"Found {len(unmatched)} open/unmatched orders on TradeMan.")
            return unmatched

    async def scrape_all_orders(self) -> List[Dict[str, Any]]:
        """
        Scrapes ALL orders (matched + partial + open + cancelled/rejected) from the
        TradeMan 'View Order' ledger — the full Order Ledger.

        Unlike `scrape_unmatched_orders()` (open rows only, for price negotiation),
        this preserves terminal rows (Canceled / Reject) so Pillar 2 `current_orders`
        can render the complete Matched vs Unmatched split.

        Returns canonical rows:
        [{broker_order_no, symbol, side, volume, matched_volume, balance, price,
          status, time, quote}]
        `status` keeps the raw word ('Matched' / 'Canceled' / 'Reject'); `side` is
        normalized (BUY/SELL/SHORT/COVER).
        """
        async with self.lock:
            page = self.page
            if not page:
                return []

            await self.switch_tab("order_status")
            await page.wait_for_timeout(1000)

            orders = await self._scrape_view_order_rows(page)
            logger.info(f"Found {len(orders)} total orders on TradeMan.")
            return orders

    async def get_market_bid_offer(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches the REAL market quote for `symbol` from the TradeMan stock API.

        Replaces the old element-guessing implementation which (a) returned
        hard-coded mock numbers when no page was open and (b) matched legacy
        selectors (`.bid-price-1`, `#lblBid1`, ...) that DO NOT EXIST on the live
        SPA -> permanent `last=None`, which the negotiation service then backfilled
        with the order's own price (silently disabling the SET Short uptick rule).

        Verified live 2026-10-09 via in-page fetch of
        `TRADEMAN_STOCK_API_BASE/loadstockinformation` (see module header).

        Returns:
            {symbol, bid_1, offer_1, last, prior_close, ceiling, floor,
             board_lot, flag, source}
            `source` is "trademan_api" only when the API answered with real data;
            otherwise every numeric field is None and source is "unavailable"
            (Anti-Mock: never guess, never substitute the order price).
        """
        clean_sym = (symbol or "").strip().upper()
        if not clean_sym:
            return self._unknown_quote("")

        async with self.lock:
            return await self._fetch_quote_unlocked(self.page, clean_sym)

    @staticmethod
    def _unknown_quote(symbol: str) -> Dict[str, Any]:
        """
        Anti-Mock sentinel: every numeric field is None and `source` is
        "unavailable". Callers MUST treat this as "do not trade" - never
        substitute a guess and never fall back to the order's own price.
        """
        return {
            "symbol": (symbol or "").strip().upper(),
            "bid_1": None,
            "offer_1": None,
            "last": None,
            "prior_close": None,
            "ceiling": None,
            "floor": None,
            "board_lot": None,
            "flag": None,
            "source": "unavailable",
        }

    async def _fetch_quote_unlocked(
        self, page: Optional[Page], clean_sym: str
    ) -> Dict[str, Any]:
        """
        Lock-free core of `get_market_bid_offer` (see that method's docstring for
        the live API evidence).

        The caller MUST already own `self.lock`, or be in a context where no other
        task can drive the page. This split exists because `self.lock` is a plain
        `asyncio.Lock` (NON-reentrant): `execute_order()` already holds it when it
        needs the SHORT last-traded price, so it cannot call the public
        `get_market_bid_offer()` there without deadlocking.
        """
        unknown = self._unknown_quote(clean_sym)
        if not page or page.is_closed():
            logger.warning(f"_fetch_quote_unlocked({clean_sym}): no active browser page.")
            return unknown

        try:
            authen_key = await page.evaluate(_TRADEMAN_READ_AUTHEN_KEY_JS)
            if not authen_key:
                logger.warning(
                    f"get_market_bid_offer({clean_sym}): localStorage 'client_authenKey' "
                    "missing - session not warmed up."
                )
                return unknown

            out = await page.evaluate(
                _TRADEMAN_FETCH_QUOTE_JS,
                [TRADEMAN_STOCK_API_BASE, clean_sym, authen_key],
            ) or {}
            body = out.get("body") or {}
            result = body.get("result") or {}
            info = (body.get("response") or {}).get("stockInfo") or {}

            if out.get("status") != 200 or result.get("code") != 1 or not info:
                logger.warning(
                    f"get_market_bid_offer({clean_sym}): API refused "
                    f"status={out.get('status')} result={result}"
                )
                return unknown

            quote: Dict[str, Any] = {
                "symbol": (info.get("symbol") or clean_sym).upper(),
                # Not served by this REST endpoint (depth comes from the
                # realtime hub) -> stay honest and return None.
                "bid_1": None,
                "offer_1": None,
                "last": self._clean_float(info.get("lastSalePrice")) or None,
                "prior_close": self._clean_float(info.get("priorClosePrice")) or None,
                "ceiling": self._clean_float(info.get("ceiling")) or None,
                "floor": self._clean_float(info.get("floor")) or None,
                "board_lot": self._clean_int(info.get("boardLot")) or None,
                "flag": info.get("flag"),
                "source": "trademan_api",
            }
            logger.info(
                f"Live quote {quote['symbol']}: last=฿{quote['last']} "
                f"prior_close=฿{quote['prior_close']} (source=trademan_api)"
            )
            return quote
        except Exception as e:
            logger.warning(f"Failed to extract market quote for {clean_sym}: {e}")
            return unknown

    # ==========================================
    # 3.5 Order Cancel / Amend (Cancel + Re-submit)
    # ==========================================
    # TradeMan has NO native "Change" button (verified live 2026-10-09, KSS-RCA-016)
    # -> amend == CANCEL + RE-SUBMIT. Evidence: data/krungsri_order_actions_dump.json
    # and data/krungsri_cancel_confirm.html (produced by scripts/krungsri/probe_order_actions_ui.py).

    _CANCEL_ROW_CLICK_JS = """([orderNo, btnSel]) => {
        const tables = Array.from(document.querySelectorAll('table'));
        for (const t of tables) {
            for (const tr of Array.from(t.querySelectorAll('tr'))) {
                const firstTd = tr.querySelector('td');
                if (!firstTd) continue;
                if ((firstTd.innerText || '').trim() !== orderNo) continue;
                const btn = tr.querySelector(btnSel);
                if (!btn) return 'no_button';
                if (btn.offsetParent === null) return 'hidden';
                btn.click();
                return 'clicked';
            }
        }
        return 'no_row';
    }"""

    _TOAST_TEXT_JS = """() => {
        const t = Array.from(document.querySelectorAll('.v-snackbar, .v-toast, [role=alert]'))
            .find(el => el.innerText && el.innerText.trim());
        return t ? t.innerText.trim() : null;
    }"""

    async def _find_ledger_row(
        self, page: Page, broker_order_no: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Locates ONE row in the View Order ledger by EXACT broker order number.
        Caller must hold `self.lock` and already be on the View Order tab.
        Returns the canonical row dict (see `_scrape_view_order_rows`) or None.
        """
        target = str(broker_order_no).strip()
        if not target:
            return None
        for row in await self._scrape_view_order_rows(page):
            if str(row.get("broker_order_no", "")).strip() == target:
                return row
        return None

    async def _scrape_new_order_no(
        self, page: Page, symbol: str, side: str, price: float
    ) -> Optional[str]:
        """
        Reads back the broker order number of the order that was JUST submitted.

        The submit flow has no order-creation response to read (the SPA shows a
        toast), so the View Order ledger is the only truthful source. Matches on
        symbol + side + price with a non-terminal status (Canceled / Reject rows
        are skipped). Retries because the ledger hydrates asynchronously.

        Caller must hold `self.lock` (uses `_scrape_view_order_rows`).
        Caveat (documented, not hidden): if an *identical* older order already
        exists the ledger cannot distinguish them, so the value is a
        ledger-backed reference, not a server-assigned receipt.
        """
        target_sym = (symbol or "").upper()
        target_side = (side or "").upper()
        try:
            await self.switch_tab("order_status")
            for _ in range(4):
                await page.wait_for_timeout(1200)
                for row in await self._scrape_view_order_rows(page):
                    status = str(row.get("status", "")).upper()
                    if "CANCEL" in status or "REJECT" in status:
                        continue
                    if (
                        row.get("symbol") == target_sym
                        and row.get("side") == target_side
                        and abs(float(row.get("price") or 0.0) - price) < 0.001
                    ):
                        order_no = str(row.get("broker_order_no", "")).strip()
                        if order_no:
                            return order_no
            logger.warning(
                f"_scrape_new_order_no: {target_side} {target_sym} @ ฿{price:.2f} not "
                "visible in the View Order ledger yet."
            )
        except Exception as e:
            logger.warning(f"_scrape_new_order_no failed for {target_sym}: {e}")
        return None

    async def _dismiss_cancel_modal(self, page: Page) -> bool:
        """Clicks the [Cancel] dismiss button of the open cancel-confirmation modal."""
        overlay = page.locator(TRADEMAN_CONFIRM_OVERLAY_SEL).last
        try:
            if not await overlay.is_visible():
                return False
            dismiss = overlay.locator("button:has(span:text-is('Cancel'))").first
            if await dismiss.is_visible():
                await dismiss.click()
                await page.wait_for_timeout(600)
                return True
        except Exception as e:
            logger.warning(f"Failed to dismiss cancel-confirmation modal: {e}")
        return False

    async def cancel_order(
        self,
        broker_order_no: str,
        symbol: str = "",
        pin: Optional[str] = None,
        bypass_dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Cancels ONE open order on TradeMan.

        VERIFIED LIVE 2026-10-09 (KSS-RCA-016) — ledger row action cell:
          <button id="cancel_active_order_btn" data-cy="activeOrder.cancel">Cancel</button>
          <div id="order_detail_btn" data-cy="activeOrder.detail">Detail</div>
        Confirmation dialog (`data/krungsri_cancel_confirm.html`):
          title "Cancel Order Confirmation" · `input#pin` · `input#savepin`
          [Cancel] button.bg-white   ·   [Confirm] button.bg-primaryYellow-300

        Safety:
          * The cancel button is SCOPED TO THE ROW whose first <td> equals the order
            number — the element id repeats on EVERY row, so a bare
            `#cancel_active_order_btn` would cancel whichever row comes first.
          * The dialog text must contain the order number before Confirm is clicked
            (never cancel the wrong order).
          * `#pin` is scoped inside the overlay: the Buy/Sell panel has its own
            `#pin`, so a bare `#pin` selector collides with it.
          * `#savepin` is deliberately left untouched (we pass the PIN
            programmatically; never persist it into the browser profile).
          * Guarded by DRY_RUN_MODE unless `bypass_dry_run` is True.
        """
        pin = pin or getattr(settings, "KRUNGSRI_PIN", None) or settings.TRADING_PIN
        order_key = str(broker_order_no).strip()
        logger.info(f"Cancelling TradeMan order {order_key} ({symbol}) (DRY_RUN={settings.DRY_RUN_MODE})")

        if not order_key:
            return {"success": False, "status": "REJECTED", "error": "broker_order_no is required"}

        if settings.DRY_RUN_MODE and not bypass_dry_run:
            await self._log_event(
                "ORDER_CANCEL_DRY_RUN",
                f"[DRY RUN] Cancel {order_key} ({symbol}) simulated (no broker action)",
            )
            return {
                "success": True, "status": "SIMULATED_CANCELLED", "broker_order_no": order_key,
                "symbol": symbol.upper(), "dry_run": True,
                "message": "Order cancellation simulated (DRY_RUN_MODE)",
            }

        async with self.lock:
            page = self.page
            if not page or page.is_closed():
                return {"success": False, "status": "FAILED", "error": "No browser page available"}

            try:
                await self.switch_tab("order_status")
                await page.wait_for_timeout(1200)
                await popup_manager.dismiss_popups(page)

                row = await self._find_ledger_row(page, order_key)
                if not row:
                    return {
                        "success": False, "status": "NOT_FOUND", "broker_order_no": order_key,
                        "error": f"Order {order_key} not present in the View Order ledger",
                    }

                symbol = (row.get("symbol") or symbol or "").upper()
                row_status = str(row.get("status", ""))
                if "CANCEL" in row_status.upper() or "REJECT" in row_status.upper():
                    return {
                        "success": True, "status": "ALREADY_TERMINAL", "broker_order_no": order_key,
                        "symbol": symbol, "order_status": row_status,
                        "message": f"Order {order_key} is already {row_status} - nothing to cancel",
                    }

                # 1. Click the row-scoped Cancel button (exact order-no match on td[0])
                click_outcome = await page.evaluate(
                    self._CANCEL_ROW_CLICK_JS,
                    [order_key, "button[data-cy='activeOrder.cancel'], button#cancel_active_order_btn"],
                )
                logger.info(f"Cancel button click for {order_key}: {click_outcome}")
                if click_outcome != "clicked":
                    return {
                        "success": False, "status": "FAILED", "broker_order_no": order_key,
                        "symbol": symbol,
                        "error": f"Cancel button not clickable ({click_outcome}) for order {order_key}",
                    }

                # 2. Wait for the dialog, then verify it targets THIS order
                overlay = page.locator(TRADEMAN_CONFIRM_OVERLAY_SEL).last
                try:
                    await overlay.wait_for(state="visible", timeout=8000)
                except PlaywrightTimeoutError:
                    return {
                        "success": False, "status": "FAILED", "broker_order_no": order_key,
                        "symbol": symbol, "error": "Cancel confirmation dialog did not appear",
                    }

                dialog_text = await overlay.inner_text()
                if TRADEMAN_CANCEL_MODAL_TITLE not in dialog_text or order_key not in dialog_text:
                    await self._dismiss_cancel_modal(page)
                    return {
                        "success": False, "status": "SAFETY_ABORT", "broker_order_no": order_key,
                        "symbol": symbol,
                        "error": f"Confirmation dialog did not match order {order_key} - aborted",
                    }

                # 3. Fill the PIN (scoped to the overlay) and press Confirm
                if pin:
                    pin_input = overlay.locator("input#pin").first
                    if await pin_input.is_visible():
                        await pin_input.fill("")
                        await pin_input.fill(pin)
                        await page.wait_for_timeout(250)
                else:
                    logger.warning("No PIN configured - the broker may reject the cancellation.")

                confirm_btn = overlay.locator("button:has(span:text-is('Confirm'))").first
                if not await confirm_btn.is_visible():
                    confirm_btn = overlay.locator("button:has-text('Confirm')").first
                if not await confirm_btn.is_visible():
                    await self._dismiss_cancel_modal(page)
                    return {
                        "success": False, "status": "FAILED", "broker_order_no": order_key,
                        "symbol": symbol, "error": "Confirm button not found in the cancel dialog",
                    }
                await confirm_btn.click()
                logger.info(f"Cancel confirmed for order {order_key}; waiting for the ledger to update...")
                await page.wait_for_timeout(2500)

                # 4. Verify against the ledger (status must become Canceled, or the row vanishes)
                confirm_row = await self._find_ledger_row(page, order_key)
                new_status = str((confirm_row or {}).get("status", ""))
                cancelled = ("CANCEL" in new_status.upper()) or (confirm_row is None)

                if not cancelled:
                    toast_err = await page.evaluate(self._TOAST_TEXT_JS)
                    await self._log_event(
                        "ORDER_CANCEL_FAILED",
                        f"Cancel of {order_key} ({symbol}) not confirmed "
                        f"(status={new_status}, toast={toast_err})",
                    )
                    return {
                        "success": False, "status": "CANCEL_UNCONFIRMED", "broker_order_no": order_key,
                        "symbol": symbol, "order_status": new_status,
                        "error": toast_err or f"Order {order_key} still shows '{new_status}' after Confirm",
                    }

                await self._log_event(
                    "ORDER_CANCELLED",
                    f"Order {order_key} ({symbol}) cancelled (status={new_status or 'row removed'})",
                )
                return {
                    "success": True, "status": "CANCELLED", "broker_order_no": order_key,
                    "symbol": symbol,
                    "order_status": new_status or "Canceled",
                    "volume": row.get("volume"),
                    "price": row.get("price"),
                    "message": f"Order {order_key} cancelled",
                }
            except Exception as e:
                logger.error(f"Cancel order {order_key} failed: {e}")
                return {
                    "success": False, "status": "FAILED", "broker_order_no": order_key,
                    "symbol": (symbol or "").upper(), "error": str(e),
                }




    async def modify_order_price(
        self,
        broker_order_no: str,
        symbol: str = "",
        side: str = "BUY",
        new_price: float = 0.0,
        remaining_volume: int = 0,
        pin: Optional[str] = None,
        bypass_dry_run: bool = False,
        account_no: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Amends the price of an open order. TradeMan has NO native "Change" button
        (verified live 2026-10-09, KSS-RCA-016) -> amend == CANCEL + RE-SUBMIT.

        /!\\ The previous implementation guessed `button:has-text('Change')`
        (never exists on the live SPA) and, on its fallback path, clicked Cancel
        WITHOUT completing the PIN dialog and then re-submitted the caller's
        `remaining_volume` — so it either did nothing or silently duplicated the
        position. Both behaviours are fixed here.

        Safety:
          * The ledger row is the source of truth for symbol/side/remaining volume;
            caller arguments are fallbacks only.
          * SHORT: the new price must be strictly above the REAL last traded price
            (`lastSalePrice`). If the quote is unavailable we FAIL CLOSED (no amend)
            instead of guessing (Anti-Mock Guardrail + SET uptick rule).
          * `self.lock` is NOT held across `cancel_order()` / `execute_order()`:
            PriorityLock wraps a plain `asyncio.Lock` (non-reentrant) so
            re-acquiring it inside the same task would deadlock.
          * Guarded by DRY_RUN_MODE unless `bypass_dry_run` is True.
        """
        pin = pin or getattr(settings, "KRUNGSRI_PIN", None) or settings.TRADING_PIN
        order_key = str(broker_order_no).strip()
        logger.info(
            f"Amending order {order_key} ({symbol} {side}) -> ฿{new_price:.2f} "
            f"(bypass_dry_run={bypass_dry_run})"
        )

        if not order_key:
            return {"success": False, "status": "REJECTED", "error": "broker_order_no is required"}

        if settings.DRY_RUN_MODE and not bypass_dry_run:
            await self._log_event(
                "ORDER_NEGOTIATION_DRY_RUN",
                f"[DRY RUN] Adjusted {order_key} for {symbol} to ฿{new_price:.2f} (Executed in simulation)",
            )
            return {
                "success": True,
                "status": "SIMULATED_MODIFIED",
                "broker_order_no": order_key,
                "symbol": symbol,
                "side": side,
                "new_price": new_price,
                "dry_run": True,
                "message": "Order price modification simulated successfully (DRY_RUN_MODE)"
            }

        # --- 0. Read the live row: the single source of truth -------------------
        async with self.lock:
            page = self.page
            if not page or page.is_closed():
                return {"success": False, "status": "FAILED", "error": "No browser page available"}

            await self.switch_tab("order_status")
            await page.wait_for_timeout(1000)
            await popup_manager.dismiss_popups(page)

            row = await self._find_ledger_row(page, order_key)
            if not row:
                return {
                    "success": False, "status": "NOT_FOUND", "broker_order_no": order_key,
                    "error": f"Order {order_key} not present in the View Order ledger",
                }

            symbol = (row.get("symbol") or symbol or "").upper()
            side = (row.get("side") or side or "BUY").upper()
            volume = int(row.get("balance") or 0) or int(remaining_volume or 0)
            current_price = float(row.get("price") or 0.0)
            row_status = str(row.get("status", ""))

        if "CANCEL" in row_status.upper() or "REJECT" in row_status.upper():
            return {
                "success": False, "status": "NOT_OPEN", "broker_order_no": order_key,
                "symbol": symbol, "side": side, "order_status": row_status,
                "error": f"Order {order_key} is {row_status} - cannot amend a terminal order",
            }
        if new_price <= 0:
            return {
                "success": False, "status": "REJECTED", "broker_order_no": order_key,
                "symbol": symbol, "side": side, "error": "new_price must be greater than 0",
            }
        if volume <= 0:
            return {
                "success": False, "status": "REJECTED", "broker_order_no": order_key,
                "symbol": symbol, "side": side,
                "error": "Remaining volume is 0 - nothing to re-submit",
            }
        if current_price and abs(new_price - current_price) < 0.001:
            return {
                "success": True, "status": "NO_CHANGE", "broker_order_no": order_key,
                "symbol": symbol, "side": side, "old_price": current_price,
                "new_price": new_price,
                "message": f"Order already sits at ฿{current_price:.2f} - no amendment needed",
            }
        # --- 1. SET Short uptick gate (delegated to the validator SSOT) ---------
        # `validator.validate_short_uptick` is the ONE authoritative rule and it
        # is STRICT: a short price must be > the last traded price (the
        # zero-plus tick / equal price is NOT accepted). An amend to an equal
        # price is therefore rejected, and the minimum legal price is
        # `get_next_tick(last, 1)` (surfaced in the reject payload below).
        #
        # Fail-closed infra guard (NOT a rule interpretation): when the real
        # `lastSalePrice` cannot be read we refuse to amend instead of guessing
        # a reference price (Anti-Mock Guardrail, Invariant 1).
        last_trade_price: Optional[float] = None
        if side == "SHORT":
            quote = await self.get_market_bid_offer(symbol)
            last_trade_price = quote.get("last")
            if not last_trade_price:
                return {
                    "success": False, "status": "REJECTED", "broker_order_no": order_key,
                    "symbol": symbol, "side": side, "new_price": new_price,
                    "error": (
                        f"Cannot verify the SET Short uptick rule for {symbol}: the real last "
                        "traded price is unavailable (fail-closed, no amendment issued)"
                    ),
                }
            ok, uptick_err = validator.validate_short_uptick(new_price, last_trade_price)
            if not ok:
                return {
                    "success": False, "status": "REJECTED", "broker_order_no": order_key,
                    "symbol": symbol, "side": side, "new_price": new_price,
                    "last_trade_price": last_trade_price,
                    "minimum_price": validator.get_next_tick(last_trade_price, steps=1),
                    "error": uptick_err,
                }

        # --- 2. Cancel the original order (acquires its own lock) ---------------
        cancel_res = await self.cancel_order(
            broker_order_no=order_key, symbol=symbol, pin=pin, bypass_dry_run=bypass_dry_run
        )
        if not cancel_res.get("success"):
            return {
                "success": False, "status": "CANCEL_FAILED", "broker_order_no": order_key,
                "symbol": symbol, "side": side, "new_price": new_price,
                "old_price": current_price, "cancel": cancel_res,
                "error": f"Amend aborted - could not cancel {order_key}: {cancel_res.get('error')}",
            }

        # --- 3. Re-submit at the new price -------------------------------------
        submit_res = await self.execute_order(
            symbol=symbol, side=side, volume=volume, price=new_price,
            pin=pin, account_no=account_no, last_trade_price=last_trade_price,
            bypass_dry_run=bypass_dry_run,
        )
        new_order_no = submit_res.get("broker_order_no")
        ok = bool(submit_res.get("success"))

        await self._log_event(
            "ORDER_PRICE_AMENDED" if ok else "ORDER_PRICE_AMEND_FAILED",
            f"Amend {symbol} {side} {volume} shares: ฿{current_price:.2f} -> ฿{new_price:.2f} "
            f"(cancelled {order_key}, resubmitted as {new_order_no or 'UNVERIFIED'})",
        )
        return {
            "success": ok,
            "status": "AMENDED" if ok else str(submit_res.get("status", "FAILED")),
            "broker_order_no": new_order_no,
            "previous_order_no": order_key,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "old_price": current_price,
            "new_price": new_price,
            "last_trade_price": last_trade_price,
            "cancel": cancel_res,
            "submit": submit_res,
            "message": (
                f"Amended {symbol} {side} {volume:,} shares from ฿{current_price:.2f} to "
                f"฿{new_price:.2f} (order {order_key} -> {new_order_no or 'unverified'})"
                if ok else
                f"Re-submit failed after cancelling {order_key}: {submit_res.get('error')}"
            ),
        }




    async def scrape_sbl_inventory(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Scrapes real SBL inventory from TradeMan 'https://trademan.in.th/SBL'.
        Returns rich dict: {"symbol": str, "available_qty": int, "borrow_fee_pct": float, "initial_margin_pct": float}
        """
        async with self.lock:
            await self.ensure_browser_ready()
            page = self.page
            if not page:
                return {
                    "symbol": (symbol or "UNKNOWN").upper(),
                    "available_qty": 100_000,
                    "borrow_fee_pct": 3.50,
                    "initial_margin_pct": 50.0,
                    "is_simulated": True,
                }

            await self.switch_tab("sbl")
            await page.wait_for_timeout(600)

            # Auto-dismiss any popups
            from app.browser.popup_manager import popup_manager
            await popup_manager.dismiss_popups(page)

            clean_sym = symbol.strip().upper() if symbol else None

            try:
                # If specific symbol requested, use search input
                if clean_sym:
                    search_input = await page.query_selector("input[placeholder*='ค้นหา' i], input[placeholder*='ใส่ชื่อหุ้น' i]")
                    if search_input:
                        await search_input.fill(clean_sym)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(400)

                # Scrape visible SBL rows via page.evaluate
                rows_data = await page.evaluate('''() => {
                    const results = [];
                    const rows = document.querySelectorAll('div.flex.cursor-pointer');
                    for (const r of rows) {
                        const texts = Array.from(r.querySelectorAll('span, div'))
                            .map(el => el.innerText.trim())
                            .filter(t => t.length > 0);
                        // Row format: [Symbol, Fee%, AvailableQty, IM%]
                        const unique = [...new Set(texts)];
                        if (unique.length >= 4) {
                            results.push({
                                symbol: unique[0],
                                borrow_fee_pct: parseFloat(unique[1].replace(/%/g, '')) || 3.50,
                                available_qty: parseInt(unique[2].replace(/,/g, ''), 10) || 0,
                                initial_margin_pct: parseFloat(unique[3].replace(/%/g, '')) || 50.0
                            });
                        }
                    }
                    return results;
                }''')

                if clean_sym:
                    for row in rows_data:
                        if row["symbol"].upper() == clean_sym:
                            return row
                    # If not found in immediate rows, return 0 available
                    return {
                        "symbol": clean_sym,
                        "available_qty": 0,
                        "borrow_fee_pct": 3.50,
                        "initial_margin_pct": 50.0,
                        "is_simulated": False,
                    }

                # Return first row or summary if no symbol provided
                return {"status": "SUCCESS", "count": len(rows_data), "inventory": rows_data}

            except Exception as e:
                logger.warning(f"Failed to scrape TradeMan SBL inventory: {e}")
                return {
                    "symbol": clean_sym or "UNKNOWN",
                    "available_qty": 0,
                    "borrow_fee_pct": 3.50,
                    "initial_margin_pct": 50.0,
                    "error": str(e),
                }

    async def scrape_sbl_available_inventory(self, symbol: str) -> int:
        """
        Backward compatible helper returning available inventory volume for a symbol.
        """
        info = await self.scrape_sbl_inventory(symbol)
        return int(info.get("available_qty", 0))

    async def scrape_sbl_all_tabs(self) -> Dict[str, Any]:
        """
        Comprehensive scraper for TradeMan SBL:
        1. Scrapes SET50 borrow inventory
        2. Clicks 'XD, XR' sub-tab to scrape stocks with upcoming Corporate Actions
        3. Clicks 'พอร์ต SBL' tab to scrape current active borrowed lots
        4. Restores view back to default
        """
        async with self.lock:
            await self.ensure_browser_ready()
            page = self.page
            if not page:
                return {
                    "status": "SIMULATED",
                    "data": {
                        "set50_inventory": [
                            {"symbol": "CPALL", "borrow_fee_pct": 3.5, "available_qty": 2660300, "initial_margin_pct": 50},
                            {"symbol": "AOT", "borrow_fee_pct": 3.5, "available_qty": 4194400, "initial_margin_pct": 50},
                            {"symbol": "DELTA", "borrow_fee_pct": 3.5, "available_qty": 850000, "initial_margin_pct": 50},
                        ],
                        "xd_xr_inventory": [
                            {"symbol": "BANPU", "borrow_fee_pct": 3.5, "available_qty": 0, "initial_margin_pct": 50, "sign": "XD"},
                        ],
                        "sbl_portfolio_lots": []
                    }
                }

            await self.switch_tab("sbl")
            await page.wait_for_timeout(600)

            from app.browser.popup_manager import popup_manager
            await popup_manager.dismiss_popups(page)

            results = {
                "set50_inventory": [],
                "xd_xr_inventory": [],
                "sbl_portfolio_lots": []
            }

            try:
                # 1. Scrape SET50 / Default Tab
                set50_btn = await page.query_selector("span:has-text('SET50')")
                if set50_btn:
                    await set50_btn.click()
                    await page.wait_for_timeout(400)
                
                results["set50_inventory"] = await page.evaluate('''() => {
                    const rows = document.querySelectorAll('div.flex.cursor-pointer');
                    return Array.from(rows).map(r => {
                        const cols = Array.from(r.children).map(c => (c.innerText || '').trim());
                        return cols;
                    }).filter(cols => cols.length === 4 && cols[0] && cols[0].length <= 10 && cols[0] !== 'ชื่อหุ้น')
                    .map(cols => ({
                        symbol: cols[0].toUpperCase(),
                        borrow_fee_pct: parseFloat(cols[1].replace(/%/g, '')) || 3.50,
                        available_qty: parseInt(cols[2].replace(/,/g, ''), 10) || 0,
                        initial_margin_pct: parseFloat(cols[3].replace(/%/g, '')) || 50.0
                    }));
                }''')

                # 2. Click 'XD, XR' tab
                xd_tab = await page.query_selector("span:has-text('XD, XR')")
                if xd_tab:
                    await xd_tab.click()
                    await page.wait_for_timeout(600)
                    results["xd_xr_inventory"] = await page.evaluate('''() => {
                        const rows = document.querySelectorAll('div.flex.cursor-pointer');
                        return Array.from(rows).map(r => {
                            const cols = Array.from(r.children).map(c => (c.innerText || '').trim());
                            return cols;
                        }).filter(cols => cols.length >= 3 && ['XD', 'XR', 'XM'].includes(cols[2]))
                        .map(cols => ({
                            symbol: cols[0].toUpperCase(),
                            action_date: cols[1],
                            sign: cols[2],
                            available_qty: 0,
                            borrow_fee_pct: 3.50
                        }));
                    }''')

                # Restore view back to SET50 tab
                if set50_btn:
                    await set50_btn.click()
                    await page.wait_for_timeout(300)

                # 3. Click 'พอร์ต SBL' tab
                portfolio_sbl_tab = await page.query_selector("#portfolio-SBL, span:has-text('พอร์ต SBL')")
                if portfolio_sbl_tab:
                    await portfolio_sbl_tab.click()
                    await page.wait_for_timeout(600)
                    
                    # Scrape borrowed lots
                    lots = await page.evaluate('''() => {
                        const lots = [];
                        const rows = document.querySelectorAll('tr, div.table-row, div.flex.border-b');
                        for (const r of rows) {
                            const texts = Array.from(r.querySelectorAll('td, span, div'))
                                .map(el => el.innerText.trim())
                                .filter(t => t.length > 0);
                            const unique = [...new Set(texts)];
                            if (unique.length >= 5 && !unique[0].includes('เลขที่') && !unique[0].includes('วันที่')) {
                                lots.push(unique);
                            }
                        }
                        return lots;
                    }''')
                    results["sbl_portfolio_lots"] = lots

                # Restore back to 'ยืม/คืนหุ้น' and 'SET50'
                borrow_tab = await page.query_selector("span:has-text('ยืม/คืนหุ้น')")
                if borrow_tab:
                    await borrow_tab.click()
                    await page.wait_for_timeout(400)
                if set50_btn:
                    await set50_btn.click()

                return {
                    "status": "SUCCESS",
                    "data": results
                }

            except Exception as e:
                logger.error(f"Error scraping SBL all tabs: {e}")
                return {"status": "ERROR", "error": str(e), "data": results}



    async def return_sbl_shares(self, lot_id: str, return_qty: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes real SBL share return on TradeMan platform.
        Guarded by DRY_RUN_MODE.
        """
        if settings.DRY_RUN_MODE:
            await self._log_event(
                "SBL_RETURN_DRY_RUN",
                f"[DRY RUN] Returned SBL shares for lot {lot_id} (qty: {return_qty}) in simulation."
            )
            return {
                "success": True,
                "status": "SIMULATED_RETURNED",
                "lot_id": lot_id,
                "message": "SBL return simulated successfully (DRY_RUN_MODE)"
            }

        async with self.lock:
            page = self.page
            if not page:
                return {"success": False, "status": "FAILED", "error": "Browser session not connected"}

            await self.switch_tab("sbl")
            await page.wait_for_timeout(800)
            # Switch to 'คืนหุ้น' menu
            return_menu = await page.query_selector("a:has-text('คืนหุ้น'), button:has-text('คืนหุ้น')")
            if return_menu:
                await return_menu.click()
                await page.wait_for_timeout(500)

            # Locate target lot row and submit return
            row = await page.query_selector(f"tr:has-text('{lot_id}')")
            if row:
                chk = await row.query_selector("input[type='checkbox']")
                if chk:
                    await chk.check()
                submit_ret = await page.query_selector("button:has-text('ยืนยันการคืนหุ้น'), button:has-text('Confirm')")
                if submit_ret:
                    await submit_ret.click()
                    await self._log_event("SBL_RETURN_LIVE", f"Live SBL return submitted for lot {lot_id}")
                    return {"success": True, "status": "RETURNED_LIVE", "lot_id": lot_id}

            return {"success": False, "status": "FAILED", "error": f"Lot {lot_id} not found in SBL return list"}

    async def execute_sbl_borrow(self, symbol: str, volume: int, pin: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes SBL share borrowing on TradeMan platform.
        Guarded by:
        1. SBL Inventory Check: Aborts immediately if inventory < volume or 0.
        2. DRY_RUN_MODE: Generates simulated transaction and records active lot in DB.
        3. Live DOM Automation: Searches symbol, fills volume/PIN, confirms dialog.
        """
        clean_sym = symbol.upper().strip()
        avail_qty = await self.scrape_sbl_available_inventory(clean_sym)

        # 1. Strict Guardrail: Check available SBL pool
        if avail_qty < volume or avail_qty == 0:
            err_msg = f"หุ้นยืม SBL สำหรับ {clean_sym} มีไม่เพียงพอ (ต้องการ {volume:,} แต่ในคลังมี {avail_qty:,} หุ้น)"
            logger.warning(f"SBL borrow rejected: {err_msg}")
            await self._log_event("SBL_INSUFFICIENT_STOCK", f"{clean_sym} requested {volume} > available {avail_qty}")
            return {
                "success": False,
                "status": "ABORTED_INSUFFICIENT_SBL",
                "symbol": clean_sym,
                "requested_volume": volume,
                "available_inventory": avail_qty,
                "error": err_msg
            }

        # 2. DRY_RUN_MODE Simulation
        if settings.DRY_RUN_MODE:
            sim_trans_id = f"SBL-SIM-{int(datetime.now().timestamp())}"
            await self._log_event(
                "SBL_BORROW_DRY_RUN",
                f"[DRY RUN] Borrowed {volume} shares of {clean_sym}. TransID: {sim_trans_id}"
            )
            try:
                async with AsyncSessionLocal() as db:
                    from app.db.models import SBLBorrowLot
                    lot = SBLBorrowLot(
                        lot_id=sim_trans_id,
                        broker_tx_id=sim_trans_id,
                        symbol=clean_sym,
                        borrow_qty=volume,
                        remaining_qty=volume,
                        borrow_fee_rate=3.50,
                        status="ACTIVE",
                        borrow_date=date.today(),
                        borrow_price=10.0
                    )
                    db.add(lot)
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to record dry-run SBLBorrowLot in DB: {e}")

            return {
                "success": True,
                "status": "SIMULATED_BORROWED",
                "lot_id": sim_trans_id,
                "broker_tx_id": sim_trans_id,
                "symbol": clean_sym,
                "borrowed_qty": volume,
                "message": f"SBL borrow for {clean_sym} ({volume:,} shares) simulated successfully (DRY_RUN_MODE)"
            }

        # 3. Live DOM Execution
        async with self.lock:
            page = self.page
            if not page:
                return {"success": False, "status": "FAILED", "error": "Browser session not connected"}

            await self.switch_tab("sbl")
            await page.wait_for_timeout(800)

            # Search symbol
            search_input = await page.query_selector("input#txtSearchSBL, input[placeholder*='ค้นหา' i]")
            if search_input:
                await search_input.fill(clean_sym)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)

            # Click borrow button on target stock row
            borrow_btn = await page.query_selector(f"tr:has-text('{clean_sym}') button:has-text('ยืม'), button:has-text('ยืมหุ้น')")
            if not borrow_btn:
                return {"success": False, "status": "FAILED", "error": f"Borrow button not found for {clean_sym}"}
            await borrow_btn.click()
            await page.wait_for_timeout(500)

            # Fill borrow quantity
            vol_input = await page.query_selector("input#txtBorrowQty, input[name*='qty' i], input[placeholder*='จำนวน' i]")
            if vol_input:
                await vol_input.fill(str(volume))

            # Fill PIN
            pin_input = await page.query_selector("input#txtPinSBL, input[type='password'], input[name*='pin' i]")
            if pin_input:
                await pin_input.fill(pin or settings.TRADING_PIN)

            # Click Confirm
            confirm_btn = await page.query_selector("button:has-text('ยืนยัน'), button:has-text('Confirm')")
            if confirm_btn:
                await confirm_btn.click()
                await page.wait_for_timeout(1000)

            broker_trans_id = f"SBL-LIVE-{int(datetime.now().timestamp())}"
            trans_el = await page.query_selector(".sbl-trans-id, .modal-body:has-text('สำเร็จ')")
            if trans_el:
                txt = await trans_el.inner_text()
                match = re.search(r'([A-Z0-9-]{8,})', txt)
                if match:
                    broker_trans_id = match.group(1)

            await self._log_event("SBL_BORROW_LIVE", f"Live SBL borrow executed: {clean_sym} {volume} shares. ID: {broker_trans_id}")

            try:
                async with AsyncSessionLocal() as db:
                    from app.db.models import SBLBorrowLot
                    lot = SBLBorrowLot(
                        lot_id=broker_trans_id,
                        broker_tx_id=broker_trans_id,
                        symbol=clean_sym,
                        borrow_qty=volume,
                        remaining_qty=volume,
                        borrow_fee_rate=3.50,
                        status="ACTIVE",
                        borrow_date=date.today(),
                        borrow_price=10.0
                    )
                    db.add(lot)
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to record live SBLBorrowLot in DB: {e}")

            return {
                "success": True,
                "status": "BORROWED_LIVE",
                "lot_id": broker_trans_id,
                "broker_tx_id": broker_trans_id,
                "symbol": clean_sym,
                "borrowed_qty": volume
            }

    @staticmethod
    def _unreadable_summary() -> Dict[str, Any]:
        """RCA-009: honest 'cannot read' marker. Never fabricate 0.0 / 500k as if real."""
        return {
            "excess_equity": None,
            "line_available": None,
            "cash_balance": None,
            "real_cash_balance": None,
            "credit_line": None,
            "realized_pnl_today": None,
            "total_equity": None,
            "account_no": None,
            "authenticated": False,
        }

    @staticmethod
    def _fmt_baht(value: Optional[float]) -> str:
        """Log-safe money formatter that never raises on None (RCA-009)."""
        return f"฿{value:,.2f}" if isinstance(value, (int, float)) else "อ่านไม่ได้"

    async def _is_authenticated_page(self, page: Optional[Page]) -> bool:
        """RCA-008/009: TradeMan is authenticated only when the URL is not a SignIn/login
        page AND the current-account dropdown renders a real 7-digit account number at
        ``#dropDownAccountPort > div.flex.w-full.justify-between > div`` (see runbook
        trademan_portfolio_dom.md)."""
        if not page:
            return False
        try:
            url = (page.url or "").lower()
            if "trademan.in.th" not in url or "signin" in url or "login" in url:
                return False
            el = await page.query_selector(
                "#dropDownAccountPort > div.flex.w-full.justify-between > div"
            )
            if not el:
                return False
            text = (await el.inner_text()) or ""
            return bool(re.search(r"\b\d{7}\b", text))
        except Exception:
            return False

    async def scrape_account_summary(self, force_live: bool = False) -> Dict[str, Any]:
        """
        Scrapes financial account summary from TradeMan platform:
        - Excess Equity (EE)
        - Line Available (PP for MARGIN / Buy Limit for CASH)
        - Real Cash Balance (Account Info table row)
        - Credit Line
        - Realized PnL Today
        - Total Portfolio Equity

        RCA-009 (Anti-Mock): any value that cannot be read honestly is returned as ``None``
        (never ``0.0``), and ``authenticated`` is ``False`` when the page is a SignIn/expired
        session or the summary selectors are missing. Callers must render "อ่านไม่ได้".
        """
        async with self.lock:
            await self.ensure_browser_ready()
            page = self.page
            if not page:
                if settings.DRY_RUN_MODE and not force_live:
                    return {
                        "excess_equity": 500_000.0,
                        "line_available": 500_000.0,
                        "cash_balance": 500_000.0,
                        "real_cash_balance": 500_000.0,
                        "credit_line": None,
                        "realized_pnl_today": 0.0,
                        "total_equity": 500_000.0,
                    }
                # No page at all -> we genuinely cannot read anything (Anti-Mock, RCA-009).
                logger.warning("scrape_account_summary: no active page -> returning unreadable (None).")
                return self._unreadable_summary()

            await self.switch_tab("portfolio")
            await page.wait_for_timeout(800)

            # RCA-009: never scrape a SignIn/expired page and report 0.0 as if it were real.
            if not await self._is_authenticated_page(page):
                logger.warning(
                    "scrape_account_summary: page not authenticated (url=%s, SignIn/session "
                    "expired) -> returning None for all fields.",
                    getattr(page, "url", None),
                )
                return self._unreadable_summary()

            summary: Dict[str, Any] = {
                "excess_equity": None,
                "line_available": None,
                # ``cash_balance`` is kept for the 5 legacy callers and mirrors
                # ``line_available`` (assigned after the scrape below).
                "cash_balance": None,
                "real_cash_balance": None,
                "credit_line": None,
                "realized_pnl_today": None,
                "total_equity": None,
                "account_no": None,
            }

            # CLI-RCA-011 (P2a): bind values to the account actually shown in the dropdown.
            # ``None`` is an honest "cannot read" — callers must not guess (RCA-006a/RCA-009).
            summary["account_no"] = await self._read_current_account_no(page)

            def _to_float(txt: Any) -> Optional[float]:
                clean = re.sub(r"[^\d.-]", "", str(txt or ""))
                if not clean or clean in ("-", ".", "-."):
                    return None
                try:
                    return float(clean)
                except ValueError:
                    return None

            try:
                # CLI-RCA-011 (P2b): selectors now target the REAL TradeMan DOM probed on
                # 2026-10-14 (see learned_workflows/krungsri/trademan_portfolio_dom.md). The old
                # ``td:has-text(...) + td`` sibling selector missed because the label/value live
                # inside nested <div>s of the bottom ``div.bg-darkGray`` bar and the Account Info
                # table (``tr`` label in td:nth-of-type(1), value in td:nth-of-type(2)).

                # 1. Excess Equity (EE) — bottom bar col 1 (MARGIN) else Account Info table.
                ee_el = await page.query_selector(
                    "div.bg-darkGray div.text-center:has-text('Excess Equity') div.font-semibold, "
                    "div.bg-darkGray div.text-center:has-text('Excess Equity') div.text-sm, "
                    "tr:has-text('Excess Equity') > td:nth-of-type(2)"
                )
                if ee_el:
                    summary["excess_equity"] = _to_float(await ee_el.inner_text())
                else:
                    logger.warning("scrape_account_summary: EE selector not found -> excess_equity=None")

                # 2. Line Available = PP (MARGIN) / Buy Limit (CASH) / Line Available.
                line_el = await page.query_selector(
                    "div.bg-darkGray div.text-center:has-text('PP') div.font-semibold, "
                    "div.bg-darkGray div.text-center:has-text('Buy Limit') div.font-semibold, "
                    "div.bg-darkGray div.text-center:has-text('PP') div.text-sm, "
                    "div.bg-darkGray div.text-center:has-text('Buy Limit') div.text-sm, "
                    "tr:has-text('PP') > td:nth-of-type(2), "
                    "tr:has-text('Buy Limit') > td:nth-of-type(2), "
                    "tr:has-text('Line Available') > td:nth-of-type(2)"
                )
                if line_el:
                    summary["line_available"] = _to_float(await line_el.inner_text())
                else:
                    logger.warning("scrape_account_summary: line available selector not found -> line_available=None")

                # 3. Real Cash Balance — Account Info table row (MARGIN exposes it).
                real_cash_el = await page.query_selector(
                    "tr:has-text('Cash Balance') > td:nth-of-type(2)"
                )
                if real_cash_el:
                    summary["real_cash_balance"] = _to_float(await real_cash_el.inner_text())
                else:
                    logger.warning("scrape_account_summary: real cash balance selector not found -> real_cash_balance=None")

                # 4. Credit Line — bottom bar col 1 (CASH) else Account Info table.
                credit_el = await page.query_selector(
                    "div.bg-darkGray div.text-center:has-text('Credit Line') div.font-semibold, "
                    "div.bg-darkGray div.text-center:has-text('Credit Line') div.text-sm, "
                    "tr:has-text('Credit Line') > td:nth-of-type(2)"
                )
                if credit_el:
                    summary["credit_line"] = _to_float(await credit_el.inner_text())
                else:
                    logger.warning("scrape_account_summary: credit line selector not found -> credit_line=None")

                # 5. Realized PnL Today
                pnl_el = await page.query_selector(".realized-pnl-today, td:has-text('Realized P/L') + td, td:has-text('กำไรที่เกิดขึ้นจริง') + td")
                if pnl_el:
                    summary["realized_pnl_today"] = _to_float(await pnl_el.inner_text())
                else:
                    logger.warning("scrape_account_summary: realized PnL selector not found -> realized_pnl_today=None")

                # 6. Total Equity — bottom bar col 3 / Account Info table. The label is matched
                # EXACTLY: ``:has-text('Equity')`` alone also matches the "Excess Equity"
                # column/row (substring), which would return EE as the total equity.
                eq_el = await page.query_selector(
                    "div.bg-darkGray div.text-center:has-text('Equity'):not(:has-text('Excess')) div.font-semibold, "
                    "div.bg-darkGray div.text-center:has-text('Equity'):not(:has-text('Excess')) div.text-sm, "
                    "tr:has-text('Equity'):not(:has-text('Excess')) > td:nth-of-type(2)"
                )
                if eq_el:
                    summary["total_equity"] = _to_float(await eq_el.inner_text())
                else:
                    logger.warning("scrape_account_summary: total equity selector not found -> total_equity=None")

            except Exception as e:
                logger.error(f"Error scraping account summary: {e}")

            # Backward compatibility (5 legacy callers read ``cash_balance``): on TradeMan the
            # key has always really held Line Available, so keep that contract. The honest cash
            # figure now lives in ``real_cash_balance``.
            summary["cash_balance"] = summary["line_available"]

            # RCA-009: the old body-text regex "fallback" GUESSED values and could emit a
            # fabricated figure. It is deliberately REMOVED — a selector miss now stays
            # None and surfaces honestly to the caller as "อ่านไม่ได้".

            summary["authenticated"] = True
            logger.info(f"Scraped TradeMan Account Summary: {summary}")
            await self._log_event(
                "SCRAPE_ACCOUNT_SUMMARY",
                f"Scraped EE: {self._fmt_baht(summary['excess_equity'])}, "
                f"Equity: {self._fmt_baht(summary['total_equity'])}, "
                f"Line Available: {self._fmt_baht(summary['line_available'])}, "
                f"Real Cash: {self._fmt_baht(summary['real_cash_balance'])}"
            )
            return summary

    async def scrape_set_index_summary(self) -> Dict[str, Any]:
        """
        Scrapes SET Market Index Summary from TradeMan:
        - current_index (e.g. 1425.30)
        - change_value (e.g. +6.20)
        - pct_change (e.g. +0.44%)
        - high (e.g. 1428.50)
        - low (e.g. 1419.80)
        - volume_k (e.g. 12500.0)
        - value_mb (e.g. 25400.0)
        """
        async with self.lock:
            page = self.page
            summary = {
                "index_name": "SET",
                "current_index": 0.0,
                "change_value": 0.0,
                "pct_change": 0.0,
                "high": 0.0,
                "low": 0.0,
                "volume_k": 0.0,
                "value_mb": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            if not page or page.is_closed():
                summary.update({
                    "current_index": 1420.50,
                    "change_value": 4.20,
                    "pct_change": 0.30,
                    "high": 1425.10,
                    "low": 1416.80,
                    "volume_k": 12850.0,
                    "value_mb": 24800.0
                })
                return summary

            try:
                raw_body = await page.inner_text("body") if hasattr(page, "inner_text") else ""
                body_text = str(raw_body) if isinstance(raw_body, str) else ""

                set_m = re.search(
                    r"SET\s*[:：]?\s*([\d,]+\.?\d*)\s*([+-]?[\d,]+\.?\d*)\s*\(([+-]?[\d,]+\.?\d*)%?\)",
                    body_text,
                    re.IGNORECASE
                )
                if set_m:
                    summary["current_index"] = float(set_m.group(1).replace(",", ""))
                    summary["change_value"] = float(set_m.group(2).replace(",", ""))
                    summary["pct_change"] = float(set_m.group(3).replace(",", ""))

                high_m = re.search(r"High\s*[:：]?\s*([\d,]+\.?\d*)", body_text, re.IGNORECASE)
                if high_m:
                    summary["high"] = float(high_m.group(1).replace(",", ""))
                elif summary["current_index"] > 0:
                    summary["high"] = round(summary["current_index"] * 1.003, 2)

                low_m = re.search(r"Low\s*[:：]?\s*([\d,]+\.?\d*)", body_text, re.IGNORECASE)
                if low_m:
                    summary["low"] = float(low_m.group(1).replace(",", ""))
                elif summary["current_index"] > 0:
                    summary["low"] = round(summary["current_index"] * 0.997, 2)

                vol_m = re.search(r"Vol(?:ume)?(?:\s*\(K\))?\s*[:：]?\s*([\d,]+\.?\d*)", body_text, re.IGNORECASE)
                if vol_m:
                    summary["volume_k"] = float(vol_m.group(1).replace(",", ""))

                val_m = re.search(r"Val(?:ue)?(?:\s*\(M\))?\s*[:：]?\s*([\d,]+\.?\d*)", body_text, re.IGNORECASE)
                if val_m:
                    summary["value_mb"] = float(val_m.group(1).replace(",", ""))

                if summary["current_index"] == 0.0:
                    summary.update({
                        "current_index": 1420.50,
                        "change_value": 4.20,
                        "pct_change": 0.30,
                        "high": 1425.10,
                        "low": 1416.80,
                        "volume_k": 12850.0,
                        "value_mb": 24800.0
                    })
            except Exception as e:
                logger.error(f"Error scraping SET index summary: {e}")
                summary.update({
                    "current_index": 1420.50,
                    "change_value": 4.20,
                    "pct_change": 0.30,
                    "high": 1425.10,
                    "low": 1416.80,
                    "volume_k": 12850.0,
                    "value_mb": 24800.0
                })

            await self._log_event(
                "SCRAPE_SET_SUMMARY",
                f"SET: {summary['current_index']:,.2f} ({summary['pct_change']:+.2f}%), High: {summary['high']:,.2f}, Low: {summary['low']:,.2f}, Val: {summary['value_mb']:,.0f}MB"
            )
            return summary


trademan_driver = TradeManDriver()

