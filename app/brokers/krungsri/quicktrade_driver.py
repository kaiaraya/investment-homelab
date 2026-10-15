"""
Krungsri Quick Trade driver (Pillar 6 - passive price negotiation)
==================================================================
Broker-isolated driver for the Krungsri Member SSO "Quick Trade" application
(``fastorder.jsp``) plus the Settrade Order-Detail page. This is the ONLY Quick
Trade code path; it never touches TradeMan or any other broker.

Capabilities:
1. Read a live 5-level Bid/Offer book + market info for a symbol
   (``#eqQuoteSymbol`` + ``#btnGetQuotes`` -> ``#instBidOfferEq`` / ``#instInfoEq``).
2. Read the open-order ledger (``#orderBodyEq``) to snapshot one order (``get_order``)
   or to list every working order of the MARGIN account (``list_open_orders``).
3. Amend an existing order in place via "Change Price& Volume" on the Settrade
   order-detail page (``app.settrade.com/order-status-detail/``): price only,
   the volume field is never touched.

Safety:
- Zero-OTP: reuses ``data/session_state.json`` (never logs in, never fires SMS).
- ``settings.DRY_RUN_MODE`` (default True): fill the price + PIN but do NOT click
  Submit. Anti-mock: results are reported exactly as observed.
- The page-level primitives (``_fetch_quote`` / ``_open_order_detail`` /
  ``_fill_amendment`` / ``_submit``) accept an injected ``page`` so they are unit
  testable with a mock DOM and no browser.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

from app.core.config import settings

logger = logging.getLogger("Krungsri.QuickTrade")

BROKER_ID = "029"
QUICKTRADE_SSO_URL = "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=place_order"
ORDER_DETAIL_URL_TMPL = (
    "https://app.settrade.com/order-status-detail/"
    "?brokerId=" + BROKER_ID + "&accountNo={account_no}&orderNo={order_no}&tradeDate={trade_date}"
)
BKK = timezone(timedelta(hours=7))

_JS_QUOTE = """
() => {
  const rows = Array.from(document.querySelectorAll('#instBidOfferEq tr')).map(tr =>
    Array.from(tr.querySelectorAll('td, th')).map(td => (td.innerText || '').trim()));
  const infoEl = document.querySelector('#instInfoEq');
  return {
    symbol: (document.querySelector('#eqQuoteSymbol') || {}).value || '',
    bid_offer_rows: rows,
    info_text: infoEl ? infoEl.innerText : ''
  };
}
"""

_JS_LEDGER = """
() => {
  const rows = Array.from(document.querySelectorAll('#orderBodyEq tr')).map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()));
  return {
    selected_account: (document.querySelector('#accInv') || {}).value || '',
    rows: rows
  };
}
"""

# Ledger header -> canonical field (runbook 2.1: Order no, Symbol, Date, Time, Side,
# Price, Volume, Matched, Balance, Cancelled, Status).
_LEDGER_COLUMNS = {
    "order": "order_no", "order no": "order_no", "order_no": "order_no",
    "orderno": "order_no", "เลขที่คำสั่ง": "order_no", "เลขที่": "order_no",
    "symbol": "symbol", "หลักทรัพย์": "symbol", "หุ้น": "symbol",
    "side": "side", "ประเภท": "side", "ซื้อ/ขาย": "side",
    "price": "price", "ราคา": "price",
    "volume": "volume", "ปริมาณ": "volume", "จำนวน": "volume",
    "matched": "matched", "จับคู่": "matched",
    "balance": "balance", "คงเหลือ": "balance",
    "cancelled": "cancelled", "ยกเลิก": "cancelled",
    "status": "status", "สถานะ": "status",
}
_SIDE_ALIASES = {
    "SHORT SELL": "SHORT", "OPEN SHORT": "OPEN_SHORT",
    "LONG SELL": "SELL", "BUY": "BUY", "SELL": "SELL",
    "SHORT": "SHORT", "OPEN_SHORT": "OPEN_SHORT",
    "LONG": "LONG", "COVER": "COVER",
}


class KrungsriQuickTradeDriver:
    """Production driver for Krungsri Quick Trade + Settrade order amendment."""

    def __init__(self, headless: bool = True):
        self._lock = asyncio.Lock()
        self.headless = headless

    # ------------------------------------------------------------------ #
    # pure parsers (no browser)                                          #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _num(value: Any) -> Optional[float]:
        if value is None:
            return None
        s = str(value).strip().replace(",", "")
        if not s or s in {"-", "--"}:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    @classmethod
    def _int(cls, value: Any) -> Optional[int]:
        f = cls._num(value)
        return int(f) if f is not None else None

    @staticmethod
    def _norm_header(cell: Any) -> str:
        return re.sub(r"\s+", " ", str(cell or "").strip().lower()).rstrip(".").rstrip(":").strip()

    @staticmethod
    def _as_order_no(cell: Any) -> Optional[str]:
        s = re.sub(r"[\s,]", "", str(cell or ""))
        return s if re.fullmatch(r"\d{5,}", s) else None

    @staticmethod
    def _norm_side(cell: Any) -> Optional[str]:
        raw = re.sub(r"\s+", " ", str(cell or "").strip().upper())
        if not raw:
            return None
        return _SIDE_ALIASES.get(raw, raw.replace(" ", "_"))

    @classmethod
    def parse_bid_offer(cls, rows: Optional[List[List[str]]]) -> Dict[str, Any]:
        """Parse ``#instBidOfferEq`` rows -> best bid/offer (row 1 = best)."""
        bids: List[Optional[float]] = []
        offers: List[Optional[float]] = []
        for r in rows or []:
            if not r or len(r) < 3:
                continue
            b, o = cls._num(r[1]), cls._num(r[2])
            if b is None and o is None:
                continue
            bids.append(b)
            offers.append(o)
        best_bid = next((b for b in bids if b is not None), None)
        best_offer = next((o for o in offers if o is not None), None)
        return {"best_bid": best_bid, "best_offer": best_offer, "bids": bids, "offers": offers}

    @classmethod
    def parse_market_info(cls, text: Optional[str]) -> Dict[str, Optional[float]]:
        """Extract the last traded price from ``#instInfoEq`` text (anti-mock: None if absent).

        Only an explicit ``Last`` label is trusted; the previous ``Close`` is never
        substituted for ``Last`` because that would corrupt the SET uptick check.
        """
        t = text or ""
        for label in (r"last(?:\s*price)?", "ล่าสุด"):
            m = re.search(label + r"\s*[:/=]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", t, re.IGNORECASE)
            if m:
                v = cls._num(m.group(1))
                if v is not None:
                    return {"last": v}
        return {"last": None}

    @classmethod
    def _header_map(cls, row: List[str]) -> Optional[Dict[str, int]]:
        mapping: Dict[str, int] = {}
        for idx, cell in enumerate(row or []):
            key = _LEDGER_COLUMNS.get(cls._norm_header(cell))
            if key and key not in mapping:
                mapping[key] = idx
        required = {"order_no", "symbol", "side", "price"}
        return mapping if required <= set(mapping) else None

    @classmethod
    def parse_order_ledger(cls, rows: Optional[List[List[str]]]) -> List[Dict[str, Any]]:
        """Parse ``#orderBodyEq`` rows -> list of order dicts (header-driven, positional fallback)."""
        cleaned = [r for r in (rows or []) if r]
        if not cleaned:
            return []
        header_map, header_idx = None, -1
        for i, r in enumerate(cleaned):
            m = cls._header_map(r)
            if m:
                header_map, header_idx = m, i
                break
        orders: List[Dict[str, Any]] = []
        if header_map:
            for r in cleaned[header_idx + 1:]:
                o = cls._row_from_map(r, header_map)
                if o and o.get("order_no"):
                    orders.append(o)
        else:
            for r in cleaned:
                o = cls._row_positional(r)
                if o and o.get("order_no"):
                    orders.append(o)
        return orders

    @classmethod
    def _row_from_map(cls, cells: List[str], m: Dict[str, int]) -> Optional[Dict[str, Any]]:
        def get(key: str) -> Optional[str]:
            idx = m.get(key)
            return cells[idx] if idx is not None and idx < len(cells) else None

        order_no = cls._as_order_no(get("order_no"))
        if not order_no:
            return None
        return {
            "order_no": order_no,
            "symbol": (get("symbol") or "").strip().upper() or None,
            "side": cls._norm_side(get("side")),
            "price": cls._num(get("price")),
            "volume": cls._int(get("volume")),
            "matched": cls._int(get("matched")),
            "balance": cls._int(get("balance")),
            "status": (get("status") or "").strip() or None,
        }

    @classmethod
    def _row_positional(cls, cells: List[str]) -> Optional[Dict[str, Any]]:
        """Positional fallback for the runbook layout [cb?] order,symbol,date,time,side,price,vol,matched,balance,cancelled,status."""
        if len(cells) >= 2 and cls._as_order_no(cells[1]) and not cls._as_order_no(cells[0]):
            off = 1
        elif cls._as_order_no(cells[0]):
            off = 0
        else:
            return None
        try:
            return {
                "order_no": cls._as_order_no(cells[off]),
                "symbol": (cells[off + 1] or "").strip().upper() or None,
                "side": cls._norm_side(cells[off + 4]),
                "price": cls._num(cells[off + 5]),
                "volume": cls._int(cells[off + 6]),
                "matched": cls._int(cells[off + 7]),
                "balance": cls._int(cells[off + 8]),
                "status": (cells[off + 10] or "").strip() or None,
            }
        except IndexError:
            return None

    @staticmethod
    def find_order(orders: List[Dict[str, Any]], order_no: str) -> Optional[Dict[str, Any]]:
        target = str(order_no or "").strip()
        for o in orders or []:
            if str(o.get("order_no") or "").strip() == target:
                return o
        return None

    @staticmethod
    def filter_open_orders(orders: Optional[List[Dict[str, Any]]],
                           account_no: Optional[str] = None) -> List[Dict[str, Any]]:
        """Keep only the orders that are still working (``balance > 0``, not cancelled/matched).

        ``account_no`` (when given) is copied onto every row so the caller can amend the
        order on the exact account it was read from. Pure - no browser.
        """
        out: List[Dict[str, Any]] = []
        for o in orders or []:
            try:
                balance = int(o.get("balance") or 0)
            except (TypeError, ValueError):
                continue
            status = str(o.get("status") or "").upper()
            if balance > 0 and "CANCEL" not in status and "MATCH" not in status.split():
                row = dict(o)
                if account_no:
                    row.setdefault("account_no", account_no)
                out.append(row)
        return out

    @staticmethod
    def _fmt_price(price: Any) -> str:
        return f"{float(price):.2f}"

    # ------------------------------------------------------------------ #
    # page primitives (injectable page -> unit-testable with a mock DOM)  #
    # ------------------------------------------------------------------ #
    async def _select_account(self, page, account_no: Optional[str]) -> None:
        if not account_no:
            return
        for label in (f"{account_no} (Equity)", f"{account_no} (Cash Balance)"):
            try:
                await page.select_option("#accInv", label=label)
                await page.wait_for_timeout(1500)
                return
            except Exception:
                continue
        try:
            await page.select_option("#accInv", value=account_no)
            await page.wait_for_timeout(1500)
        except Exception as exc:
            logger.warning(f"select account {account_no} failed: {exc}")

    async def _fetch_quote(self, page, symbol: str) -> Dict[str, Any]:
        """Fill ``#eqQuoteSymbol``, click Get Quotes and return the parsed quote dict."""
        symbol = (symbol or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        await page.fill("#eqQuoteSymbol", symbol)
        await page.click("#btnGetQuotes")
        await page.wait_for_timeout(1200)
        data = await page.evaluate(_JS_QUOTE)
        bo = self.parse_bid_offer(data.get("bid_offer_rows"))
        mi = self.parse_market_info(data.get("info_text"))
        return {
            "symbol": (data.get("symbol") or symbol).strip().upper(),
            "best_bid": bo["best_bid"],
            "best_offer": bo["best_offer"],
            "last": mi.get("last"),
            "bids": bo["bids"],
            "offers": bo["offers"],
        }

    async def _read_order_ledger(self, page) -> Dict[str, Any]:
        data = await page.evaluate(_JS_LEDGER)
        return {
            "selected_account": (data.get("selected_account") or "").strip(),
            "orders": self.parse_order_ledger(data.get("rows")),
        }

    async def _open_order_detail(self, context, order_no: str, account_no: str,
                                 trade_date: Optional[str] = None):
        """Open the Settrade order-detail page via its direct URL in a new tab."""
        trade_date = trade_date or datetime.now(BKK).strftime("%Y-%m-%d")
        url = ORDER_DETAIL_URL_TMPL.format(
            account_no=account_no, order_no=order_no, trade_date=trade_date)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        return page

    async def _fill_amendment(self, page, new_price: Any, pin: Optional[str]) -> str:
        """Open the Change Price& Volume modal and fill price + PIN (volume untouched)."""
        await page.click("button:has-text('Change Price& Volume')")
        await page.wait_for_timeout(1500)
        price_str = self._fmt_price(new_price)
        for sel in ("input[formcontrolname='price']", "input[name='price']"):
            try:
                await page.fill(sel, price_str)
                break
            except Exception:
                continue
        if pin:
            for sel in ("input[placeholder='PIN']", "input[type='password']", "input[name='pin']", "input[placeholder*='PIN']", "input[placeholder*='Pin']"):
                try:
                    await page.fill(sel, pin)
                    break
                except Exception:
                    continue
        return price_str

    async def _submit(self, page, dry_run: bool) -> bool:
        """Click Submit only when live; in dry-run the amendment stays staged."""
        if dry_run:
            return False
        await page.click("button:has-text('Submit')")
        await page.wait_for_timeout(3000)
        return True

    # ------------------------------------------------------------------ #
    # browser lifecycle + orchestration                                  #
    # ------------------------------------------------------------------ #
    def _session_file(self) -> str:
        path = settings.SESSION_STATE_PATH
        if not os.path.isabs(path):
            base = getattr(settings, "PROJECT_ROOT", None) or os.getcwd()
            path = os.path.join(base, path)
        return path

    async def _launch(self, playwright):
        launch_args: Dict[str, Any] = {
            "headless": self.headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,900"],
        }
        if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
            launch_args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
        browser = await playwright.chromium.launch(**launch_args)
        context = await browser.new_context(
            storage_state=self._session_file(),
            viewport={"width": 1280, "height": 900},
        )
        return browser, context

    async def get_quote(self, symbol: str, account_no: Optional[str] = None) -> Dict[str, Any]:
        """Scrape a live quote for ``symbol`` from Quick Trade."""
        async with self._lock:
            session_file = self._session_file()
            if not os.path.exists(session_file):
                return {"success": False, "error": f"Session file not found at {session_file}"}
            playwright = await async_playwright().start()
            browser, context = await self._launch(playwright)
            try:
                page = await context.new_page()
                await page.goto(QUICKTRADE_SSO_URL, wait_until="domcontentloaded", timeout=45000)
                for _ in range(20):
                    if "fastorder" in page.url:
                        break
                    await page.wait_for_timeout(1000)
                await self._select_account(page, account_no)
                quote = await self._fetch_quote(page, symbol)
                return {"success": True, **quote}
            except Exception as exc:
                logger.error(f"get_quote({symbol}) failed: {exc}")
                return {"success": False, "error": str(exc)}
            finally:
                await context.close()
                await browser.close()
                await playwright.stop()

    @staticmethod
    def candidate_accounts() -> List[str]:
        """Accounts to search when the caller did not pin one (margin first, then cash)."""
        seen: set = set()
        out: List[str] = []
        for acc in (settings.TRADEMAN_ACCOUNT_NO_MARGIN, settings.TRADEMAN_ACCOUNT_NO_CASH):
            a = str(acc or "").strip()
            if a and a not in seen:
                seen.add(a)
                out.append(a)
        return out

    async def get_order(self, order_no: str, account_no: Optional[str] = None) -> Dict[str, Any]:
        """Snapshot an open order from the ledger, searching the configured accounts."""
        candidates = [account_no] if account_no else self.candidate_accounts()
        async with self._lock:
            session_file = self._session_file()
            if not os.path.exists(session_file):
                return {"success": False, "error": f"Session file not found at {session_file}"}
            playwright = await async_playwright().start()
            browser, context = await self._launch(playwright)
            try:
                page = await context.new_page()
                await page.goto(QUICKTRADE_SSO_URL, wait_until="domcontentloaded", timeout=45000)
                for _ in range(20):
                    if "fastorder" in page.url:
                        break
                    await page.wait_for_timeout(1000)
                for acc in candidates:
                    await self._select_account(page, acc)
                    ledger = await self._read_order_ledger(page)
                    order = self.find_order(ledger["orders"], order_no)
                    if order:
                        return {"success": True, "account_no": acc, **order}
                return {"success": False,
                        "error": f"order {order_no} not found in accounts {candidates}"}
            except Exception as exc:
                logger.error(f"get_order({order_no}) failed: {exc}")
                return {"success": False, "error": str(exc)}
            finally:
                await context.close()
                await browser.close()
                await playwright.stop()

    async def list_open_orders(self, account_no: Optional[str] = None) -> Dict[str, Any]:
        """List the working orders (``balance > 0``) held in the Quick Trade ledger.

        Read-only: selects no price and submits nothing. Defaults to the MARGIN account
        (``settings.TRADEMAN_ACCOUNT_NO_MARGIN``), which is where this installation's
        order ledger lives (KSS-QT-RCA-001) and where the in-place amendment is allowed
        to act. Zero-OTP: reuses the saved session, never logs in.
        """
        account = str(account_no or getattr(settings, "TRADEMAN_ACCOUNT_NO_MARGIN", "") or "").strip()
        async with self._lock:
            session_file = self._session_file()
            if not os.path.exists(session_file):
                return {"success": False, "error": f"Session file not found at {session_file}"}
            playwright = await async_playwright().start()
            browser, context = await self._launch(playwright)
            try:
                page = await context.new_page()
                await page.goto(QUICKTRADE_SSO_URL, wait_until="domcontentloaded", timeout=45000)
                for _ in range(20):
                    if "fastorder" in page.url:
                        break
                    await page.wait_for_timeout(1000)
                await self._select_account(page, account)
                ledger = await self._read_order_ledger(page)
                return {
                    "success": True,
                    "account_no": account,
                    "selected_account": ledger["selected_account"] or account,
                    "orders": self.filter_open_orders(ledger["orders"], account),
                }
            except Exception as exc:
                logger.error(f"list_open_orders({account}) failed: {exc}")
                return {"success": False, "error": str(exc)}
            finally:
                await context.close()
                await browser.close()
                await playwright.stop()

    async def amend_price(self, order_no: str, new_price: Any, account_no: str,
                          trade_date: Optional[str] = None, pin: Optional[str] = None,
                          dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """Amend an existing order's price in place (volume preserved)."""
        dry_run = settings.DRY_RUN_MODE if dry_run is None else bool(dry_run)
        pin = settings.KRUNGSRI_PIN if pin is None else pin
        result: Dict[str, Any] = {
            "success": False, "order_no": order_no, "new_price": self._num(new_price),
            "dry_run": dry_run, "submitted": False,
        }
        if not account_no:
            result["error"] = "account_no is required for a Settrade order amendment"
            return result
        async with self._lock:
            session_file = self._session_file()
            if not os.path.exists(session_file):
                result["error"] = f"Session file not found at {session_file}"
                return result
            playwright = await async_playwright().start()
            browser, context = await self._launch(playwright)
            try:
                page = await self._open_order_detail(context, order_no, account_no, trade_date)
                result["price_field"] = await self._fill_amendment(page, new_price, pin)
                result["submitted"] = await self._submit(page, dry_run)
                result["success"] = True
                result["status"] = "SUBMITTED" if result["submitted"] else "STAGED_DRY_RUN"
                return result
            except Exception as exc:
                logger.error(f"amend_price({order_no}) failed: {exc}")
                result["error"] = str(exc)
                return result
            finally:
                await context.close()
                await browser.close()
                await playwright.stop()


quicktrade_driver = KrungsriQuickTradeDriver()
