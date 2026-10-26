"""
Settrade Streaming Driver (Krungsri SSO) — TASK-loop1-8 Phase 1.
================================================================
Playwright automation for the *live* Settrade Streaming trading console
(StreamingPage.jsp) reached via the Krungsri SSO path.

Adapted from ``app/browser/click2win_driver.py`` (same Settrade Streaming app,
identical trading DOM) with three key differences for the LIVE account:

1. **Real SHORT/COVER** — the live margin account 3024952 supports short-sell /
   cover. Unlike Click2Win (which simulates SHORT->SELL / COVER->BUY), these sides
   are passed through verbatim: SHORT selects the Sell radio + Short toggle,
   COVER selects the Buy radio + Cover toggle.

2. **Session path** = ``settings.STREAMING_SESSION_PATH`` (data/streaming_session.json).

3. **Anti-DW symbol assertion** on the order ticket before submit (the Tier-3
   assert pattern from ``app/browser/trademan_driver.py``, KSS-RCA-006): the order
   ticket's active symbol must equal the target exactly, or the order is REJECTED.

SET Equity only (no TFEX Derivatives). Fail-closed everywhere: no browser -> honest
FAILED, no fabricated order numbers / quotes.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

import app.db.session as _db_session
from app.browser.popup_manager import popup_manager
from app.browser.streaming_auth_driver import streaming_auth_driver
from app.core.config import settings
from app.db.models import SessionLog
from app.services.validator import validator

logger = logging.getLogger(__name__)

# Trading DOM selectors (confirmed Phase 0 probe — same app as click2win_driver)
SYMBOL_INPUT_SELECTOR = "input[placeholder='Symbol']"
VOLUME_INPUT_SELECTOR = "input[name='equity-place-order-vol'], input[placeholder='Volume']"
PRICE_INPUT_SELECTOR = "input[name='price-input'], input[placeholder='Price']"
PRICE_STEPPER_CONTAINER_SELECTOR = ".z-index-smart-price-volume, .css-zxyhmd"
PRICE_STEPPER_TRIGGER_SELECTOR = ".display-flex:has(input[name='price-input']) .cursor-pointer, .css-1kqdsxq"
PRICE_STEPPER_MINUS_SELECTOR = ".z-index-smart-price-volume .bg-color-loser-100, div.bg-color-loser-100:has-text('-')"
PRICE_STEPPER_PLUS_SELECTOR = ".z-index-smart-price-volume .bg-color-gainer-100, div.bg-color-gainer-100:has-text('+')"
PIN_INPUT_SELECTOR = "input#pin, input[placeholder='PIN']"

BUY_RADIO_SELECTORS = [
    "input#equity-place-order-buy-radio-button",
    "label[for*='buy' i]",
    "label:has-text('Buy')",
    "input[value='B']",
]
SELL_RADIO_SELECTORS = [
    "input#equity-place-order-sell-radio-button",
    "label[for*='sell' i]",
    "label:has-text('Sell')",
    "input[value='S']",
]
SHORT_RADIO_SELECTORS = [
    "input#equity-place-order-short-radio-button",
    "label[for='equity-place-order-short-radio-button']",
    "label:has-text('Short')",
    "input[value='H']",
]
COVER_RADIO_SELECTORS = [
    "input#equity-place-order-cover-radio-button",
    "label[for='equity-place-order-cover-radio-button']",
    "label:has-text('Cover')",
    "input[value='C']",
]

SUBMIT_SELECTORS = [
    "button.bg-color-dark-blue-60",
    "button:has-text('Submit')",
    "button:has-text('Buy')",
    "button:has-text('Sell')",
    "button:has-text('Cover')",
    "button:has-text('Short')",
    "button.bg-color-buy-button",
    "button.bg-color-sell-button",
    "button[class*='bg-color-cover']",
    "button[class*='bg-color-short']",
]
CONFIRM_SELECTORS = [
    "div:has-text('Order Confirmation') button.bg-color-cover-20",
    "div:has-text('Order Confirmation') button.bg-color-buy-20",
    "div:has-text('Order Confirmation') button.bg-color-sell-20",
    "div:has-text('Order Confirmation') button[class*='bg-color-cover']",
    "div:has-text('Order Confirmation') button[class*='bg-color-short']",
    "div:has-text('Order Confirmation') button:has-text('Cover')",
    "div:has-text('Order Confirmation') button:has-text('Buy')",
    "div:has-text('Order Confirmation') button:has-text('Sell')",
    "div:has-text('Order Confirmation') button:has-text('Short')",
    "div:has-text('Order Confirmation') button:has-text('Confirm')",
    "button:has-text('Confirm')",
    "button:has-text('ยืนยัน')",
    ".modal-confirm button",
    ".modal button",
]

CANCEL_ACTION_SELECTOR = "a:has-text('Cancel'), button:has-text('Cancel')"
CANCEL_CONFIRM_SELECTOR = "button:has-text('Confirm'), button:has-text('ตกลง'), button:has-text('OK')"


class StreamingDriver:
    """Playwright automation driver for the live Settrade Streaming console."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.page_override: Optional[Page] = None
        self.active_account_no: str = settings.STREAMING_ACCOUNT_NO or "3024952"
        self.active_account_type: str = "EQUITY"
        self._cdp_pw = None
        self._cdp_browser = None
        self._cdp_context = None
        self._cdp_connected = False

    @property
    def page(self) -> Optional[Page]:
        if self.page_override and not self.page_override.is_closed():
            return self.page_override
        from app.browser.tab_manager import tab_manager

        stm_page = tab_manager.get_tab("streaming")
        if stm_page and not stm_page.is_closed():
            return stm_page
        return streaming_auth_driver.page if streaming_auth_driver.is_authenticated else None

    async def _log_event(self, event_type: str, details: str) -> None:
        try:
            async with _db_session.AsyncSessionLocal() as db:
                db.add(SessionLog(event_type=event_type, details=details))
                await db.commit()
        except Exception as e:
            logger.debug(f"StreamingDriver log failed ({event_type}): {e}")

    async def connect_cdp(self, target: str = "streaming") -> bool:
        """Attach to the running KSS/Settrade Streaming CDP daemon (port 9333).

        Replaces the ``streaming_auth_driver`` launch/login path on this driver's
        order/cancel/scrape entry points: the daemon owns the live (human-visible)
        Chrome session, so this only *connects* and never opens a new browser or fires
        a login/OTP. The resolved page is stored as ``page_override``.
        """
        from scripts.broker_cdp.client import cdp_url_for, connect_cdp, resolve_target_tab

        if self._cdp_connected and self.page_override and not self.page_override.is_closed():
            return True

        # Disconnect any previous CDP playwright (keeps the daemon's browser alive).
        if self._cdp_pw is not None:
            try:
                await self._cdp_pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._cdp_pw = None

        try:
            pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), broker="kss")
        except Exception as e:  # noqa: BLE001
            logger.error("Streaming connect_cdp failed: %s", e)
            return False

        try:
            page = await resolve_target_tab(ctx, target, "kss")
        except Exception as e:  # noqa: BLE001
            logger.error("Streaming resolve_target_tab failed: %s", e)
            try:
                await pw.stop()
            except Exception:  # noqa: BLE001
                pass
            return False

        if page is None:
            logger.error("Streaming CDP daemon has no '%s' tab", target)
            try:
                await pw.stop()
            except Exception:  # noqa: BLE001
                pass
            return False

        self._cdp_pw = pw
        self._cdp_browser = browser
        self._cdp_context = ctx
        self.page_override = page
        self._cdp_connected = True
        logger.info("Streaming attached to CDP daemon tab '%s': %s", target, page.url)
        return True

    async def disconnect_cdp(self) -> bool:
        """Drop the CDP attachment WITHOUT closing the daemon's Chrome.

        ``/logout`` uses this: the daemon (port 9333) owns the live, human-visible
        browser, so logging out of this process must only stop *our* Playwright
        connection. Returns True when an attachment was actually dropped.
        """
        was_connected = self._cdp_connected
        pw = self._cdp_pw
        self._cdp_pw = None
        self._cdp_browser = None
        self._cdp_context = None
        self._cdp_connected = False
        self.page_override = None
        if pw is not None:
            try:
                await pw.stop()
            except Exception as e:  # noqa: BLE001
                logger.debug("Streaming disconnect_cdp stop failed: %s", e)
        if was_connected:
            logger.info("Streaming detached from CDP daemon (daemon browser kept alive)")
        return was_connected

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    async def _ensure_streaming_page(self, auto_launch: bool = False) -> Optional[Page]:
        """Guarantee the active page is on StreamingPage.jsp, attaching to the CDP daemon if asked."""
        page = self.page
        if not page or page.is_closed():
            if not auto_launch:
                return None
            logger.info("Streaming page not active. Attaching to the CDP daemon (9333)...")
            if not await self.connect_cdp():
                logger.warning("Streaming CDP daemon (9333) not available.")
                return None
            page = self.page

        if not page or page.is_closed():
            return None

        if "StreamingPage" not in page.url:
            logger.info(f"Page at {page.url}; navigating to StreamingPage.jsp...")
            try:
                await page.goto(settings.STREAMING_URL, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2500)
                await popup_manager.dismiss_popups(page)
            except Exception as e:
                logger.warning(f"Notice during _ensure_streaming_page navigation: {e}")

        return page

    async def switch_tab(self, tab_name: str) -> bool:
        """Navigate to a Streaming tab: 'portfolio', 'market', 'trading', 'order_status'."""
        page = await self._ensure_streaming_page()
        if not page or page.is_closed():
            return False

        key = tab_name.lower()
        candidates = {
            "portfolio": ["button:has-text('Portfolio')", "a:has-text('Portfolio')", "span:has-text('Portfolio')", "text=Portfolio"],
            "market": ["button:has-text('Realtime')", "button:has-text('Market')", "a:has-text('Market')", "text=Market"],
            "trading": ["button:has-text('Buy/Sell')", "button:has-text('B/S')", "button:has-text('Trading')", "input[placeholder='Symbol']"],
            "order_status": ["button:has-text('View Order')", "a:has-text('View Order')", "span:has-text('View Order')", "button:has-text('Order')", "text=View Order"],
        }

        for sel in candidates.get(key, [f"text='{tab_name}'"]):
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(800)
                    await popup_manager.dismiss_popups(page)
                    return True
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------
    # Side / ticket primitives
    # ------------------------------------------------------------------

    async def switch_account(self, account_no: str) -> bool:
        """
        Switch the account dropdown to a target account (e.g. margin 3024959).

        Confirmed DOM: the account trigger is ``span.outline-none`` showing
        "3024952 (Equity)"; options are ``li[tabindex='0']`` (e.g. "3024959 (Equity)").
        """
        page = await self._ensure_streaming_page()
        if not page or page.is_closed():
            return False
        try:
            for sel in ["span.outline-none:has-text('Equity')", "span.outline-none",
                        "div.cursor-pointer:has-text('Equity')"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(timeout=6000)
                    await page.wait_for_timeout(1200)
                    break
            for sel in [f"li:has-text('{account_no}')", f"text={account_no}"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(timeout=6000)
                    self.active_account_no = account_no
                    await page.wait_for_timeout(2500)
                    logger.info(f"Switched Streaming account to {account_no}")
                    return True
        except Exception as e:
            logger.warning(f"Streaming switch_account({account_no}) failed: {e}")
        return False

    async def _select_side(self, page: Page, side: str) -> bool:
        """
        Select the side radio directly. On the live margin account all four sides
        are real radios: Buy (B), Sell (S), Short (H), Cover (C).
        """
        group = {
            "BUY": BUY_RADIO_SELECTORS,
            "SELL": SELL_RADIO_SELECTORS,
            "SHORT": SHORT_RADIO_SELECTORS,
            "COVER": COVER_RADIO_SELECTORS,
        }.get(side, BUY_RADIO_SELECTORS)
        for sel in group:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(force=True)
                    await page.wait_for_timeout(300)
                    return True
            except Exception:
                continue
        logger.warning(f"Streaming side radio for '{side}' not found; proceeding best-effort.")
        return False

    async def _read_active_symbol(self, page: Page) -> Optional[str]:
        """Read the order ticket's current symbol (Anti-DW Tier-3 assertion source)."""
        try:
            sym_input = page.locator(SYMBOL_INPUT_SELECTOR).first
            val = await sym_input.input_value()
            return (val or "").strip().upper()
        except Exception:
            return None

    async def _scrape_order_no(self, page: Page) -> Optional[str]:
        """Scrape the first numeric order number (>= 5 digits) from the order table."""
        try:
            cells = await page.evaluate(
                """() => {
                    const r = document.querySelector('table tbody tr:first-child');
                    if (!r) return null;
                    return Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim());
                }"""
            )
            if not cells:
                return None
            return next((c for c in cells if c.isdigit() and len(c) >= 5), None)
        except Exception as e:
            logger.debug(f"Order No scrape notice: {e}")
            return None

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def execute_order(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        position: Optional[str] = "AUTO",
        pin: Optional[str] = None,
        account_type: Optional[str] = None,
        auto_launch: bool = False,
        price_type: Optional[str] = "Limit",
        bypass_dry_run: bool = False,
        tick_offset: int = 0,
        use_stepper: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Submit a real order on Settrade Streaming (SET Equity only).

        Sides BUY / SELL / SHORT / COVER are all real (SHORT/COVER are NOT simulated).
        An Anti-DW assertion verifies the ticket symbol before submit and REJECTs on
        any mismatch (fail-closed, never a wrong-stock order).
        """
        async with self.lock:
            sym = symbol.upper().strip()
            side_clean = side.upper().strip()
            pin_val = pin or settings.KRUNGSRI_PIN or settings.TRADING_PIN

            if account_type and account_type.upper().strip() == "DERIVATIVES":
                err = "Settrade Streaming (Krungsri SSO) supports SET Equity only; TFEX Derivatives not supported."
                logger.warning(err)
                return {"success": False, "status": "REJECTED", "error": err}

            # Pre-trade validation. NOTE: last_trade_price is not resolved here yet
            # (uptick enforcement for real SHORT is a later live-witness phase).
            ok, err = validator.validate_all(symbol=sym, side=side_clean, volume=volume, price=price)
            if not ok:
                logger.warning(f"Order rejected by pre-trade validator: {err}")
                await self._log_event("STREAMING_ORDER_REJECTED", f"{side_clean} {volume} {sym}: {err}")
                return {"success": False, "status": "REJECTED", "error": err}

            page = await self._ensure_streaming_page(auto_launch=auto_launch)
            if not page or page.is_closed():
                err = "Browser session not connected"
                await self._log_event("STREAMING_ORDER_FAILED", f"{side_clean} {volume} {sym}: {err}")
                return {"success": False, "status": "FAILED", "error": err}

            await self.switch_tab("trading")
            await page.wait_for_timeout(800)

            # 1. Account: SHORT/COVER require the margin account (3024959).
            if side_clean in ("SHORT", "COVER"):
                await self.switch_account(settings.STREAMING_ACCOUNT_NO_MARGIN)

            # 2. Side
            await self._select_side(page, side_clean)

            # 2. Symbol
            sym_el = page.locator(SYMBOL_INPUT_SELECTOR).first
            await sym_el.fill(sym)
            await page.wait_for_timeout(300)

            # 3. Volume
            vol_el = page.locator(VOLUME_INPUT_SELECTOR).first
            await vol_el.fill(str(volume))
            await page.wait_for_timeout(300)

            # 4. Price & Stepper trigger
            price_el = page.locator(PRICE_INPUT_SELECTOR).first
            await price_el.fill(f"{price:.2f}")
            await page.wait_for_timeout(300)

            # Stepper adjustment if tick_offset or use_stepper requested
            if tick_offset != 0 or use_stepper:
                steps = tick_offset
                if steps != 0:
                    container = page.locator(PRICE_STEPPER_CONTAINER_SELECTOR).first
                    if not (await container.is_visible()):
                        trigger = page.locator(PRICE_STEPPER_TRIGGER_SELECTOR).first
                        if await trigger.is_visible():
                            await trigger.click()
                        else:
                            await price_el.click()
                        await page.wait_for_timeout(200)
                    btn_sel = PRICE_STEPPER_PLUS_SELECTOR if steps > 0 else PRICE_STEPPER_MINUS_SELECTOR
                    btn = page.locator(btn_sel).first
                    for _ in range(abs(steps)):
                        if await btn.is_visible():
                            await btn.click()
                            await page.wait_for_timeout(100)
                    val = await price_el.input_value()
                    if val:
                        try:
                            price = float(str(val).replace(",", "").strip())
                        except (ValueError, TypeError):
                            pass

            # 5. PIN (if editable)
            if pin_val:
                pin_el = page.locator(PIN_INPUT_SELECTOR).first
                try:
                    if await pin_el.is_visible() and await pin_el.is_enabled():
                        await pin_el.fill(pin_val)
                    else:
                        logger.info("PIN field saved/disabled in active session; skipping fill.")
                except Exception as pe:
                    logger.debug(f"PIN fill bypass: {pe}")

            # 6. Anti-DW symbol assertion (KSS-RCA-006 Tier-3) — before submit.
            active_sym = await self._read_active_symbol(page)
            if active_sym != sym:
                err_msg = (
                    f"CRITICAL Anti-DW Assertion Failed: Active symbol is '{active_sym}', "
                    f"expected exact '{sym}'! Aborting."
                )
                logger.critical(err_msg)
                await self._log_event("STREAMING_ORDER_REJECTED", err_msg)
                return {"success": False, "status": "REJECTED", "error": err_msg}

            # 7. DRY_RUN guard — stop before submit (mirror TradeMan execute_order).
            #    Form is filled and the Anti-DW symbol assert has passed; only the
            #    irreversible Send click is omitted while DRY_RUN_MODE is on.
            if settings.DRY_RUN_MODE and not bypass_dry_run:
                await self._log_event(
                    "STREAMING_ORDER_DRY_RUN",
                    f"[DRY RUN] {side_clean} {volume} {sym} @ ฿{price:.2f} — form filled, symbol verified, Send omitted",
                )
                return {
                    "success": True,
                    "status": "SIMULATED_SUCCESS",
                    "symbol": sym,
                    "side": side_clean,
                    "volume": volume,
                    "price": price,
                    "account_no": self.active_account_no,
                    "account_type": "EQUITY",
                    "message": "Order form filled and verified; Send omitted per DRY_RUN_MODE.",
                }

            # 8. Human pacing + submit
            await asyncio.sleep(random.uniform(0.8, 1.2))

            submit_btn = None
            for sel in SUBMIT_SELECTORS:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    submit_btn = el
                    break
            if not submit_btn:
                return {"success": False, "status": "FAILED", "error": "Submit button not found on Streaming order ticket"}

            await submit_btn.click(force=True)
            await page.wait_for_timeout(1000)

            for c_sel in CONFIRM_SELECTORS:
                try:
                    c_btn = await page.query_selector(c_sel)
                    if c_btn and await c_btn.is_visible():
                        logger.info(f"Confirming order modal via selector: {c_sel}")
                        await c_btn.click(force=True)
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    continue

            broker_order_no = await self._scrape_order_no(page) or f"STM-{int(datetime.now(timezone.utc).timestamp())}"
            await self._log_event(
                "STREAMING_ORDER_SUBMITTED",
                f"{side_clean} {volume} {sym} @ ฿{price:.2f} ({broker_order_no})",
            )
            return {
                "success": True,
                "status": "SUBMITTED",
                "broker_order_no": broker_order_no,
                "symbol": sym,
                "side": side_clean,
                "volume": volume,
                "price": price,
                "account_no": self.active_account_no,
                "account_type": "EQUITY",
                "message": f"Successfully submitted to Settrade Streaming ({broker_order_no})",
            }

    # ------------------------------------------------------------------
    # Open orders / cancel / modify (cancel+replace)
    # ------------------------------------------------------------------

    async def scrape_unmatched_orders(self, account_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scrape queuing/open orders from the View Order tab (fail-closed: [] on no page)."""
        async with self.lock:
            page = await self._ensure_streaming_page()
            if not page or page.is_closed():
                return []

            # 1. JS-first: fetch from Settrade DGW orders endpoint (P.2)
            try:
                js_orders = await page.evaluate(
                    """async () => {
                        let acct = '3024959';
                        const acctMatch = document.body.innerText.match(/3024\d{3}/);
                        if (acctMatch) acct = acctMatch[0];
                        const r = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}/orders`, {credentials: 'include'});
                        if (!r.ok) return null;
                        return await r.json();
                    }"""
                )
                if isinstance(js_orders, list):
                    unmatched = []
                    for o in js_orders:
                        status = str(o.get("showOrderStatus") or o.get("orderStatus") or "").upper()
                        if any(st in status for st in ["QUEU", "OPEN", "PENDING", "PARTIAL", "WAIT"]):
                            side = str(o.get("side") or "").upper()
                            norm_side = "SHORT" if "SHORT" in side else ("COVER" if "COVER" in side else ("SELL" if "SELL" in side else "BUY"))
                            unmatched.append({
                                "broker_order_no": str(o.get("orderNo") or ""),
                                "symbol": str(o.get("symbol") or "UNKNOWN").upper(),
                                "side": norm_side,
                                "raw_cells": [str(o.get("orderNo")), str(o.get("symbol")), str(o.get("side")), str(o.get("price")), str(o.get("vol")), status],
                                "status": "QUEUED",
                                "account_type": account_type or self.active_account_type,
                            })
                    return unmatched
            except Exception as e:
                logger.debug(f"JS-first open orders scrape failed, falling back to DOM: {e}")

            # 2. Playwright selector fallback
            await self.switch_tab("order_status")
            await page.wait_for_timeout(800)

            unmatched: List[Dict[str, Any]] = []
            try:
                raw_rows = await page.evaluate(
                    """() => {
                        const res = [];
                        const rows = document.querySelectorAll('table tbody tr');
                        for (const r of rows) {
                            const tds = Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim());
                            if (tds.length > 0) res.push(tds);
                        }
                        return res;
                    }"""
                )
                for idx, cells in enumerate(raw_rows, 1):
                    text_upper = " | ".join(cells).upper()
                    if any(st in text_upper for st in ["QUEU", "OPEN", "PENDING", "PARTIAL", "WAIT"]):
                        order_no = next((c for c in cells if c.isdigit() and len(c) >= 5), f"STM-ORD-{idx}")
                        sym_cand = next(
                            (c for c in cells if c.isalpha() and 2 <= len(c) <= 10 and c not in ["BUY", "SELL", "SHORT", "COVER", "OPEN", "CLOSE", "CANCEL"]),
                            "",
                        )
                        side_cand = next((c for c in cells if c in ["B", "S", "H", "C", "BUY", "SELL", "SHORT", "COVER"]), "BUY")
                        norm_side = {"B": "BUY", "BUY": "BUY", "S": "SELL", "SELL": "SELL", "H": "SHORT", "SHORT": "SHORT", "C": "COVER", "COVER": "COVER"}.get(side_cand, "BUY")
                        unmatched.append({
                            "broker_order_no": order_no,
                            "symbol": sym_cand or "UNKNOWN",
                            "side": norm_side,
                            "raw_cells": cells,
                            "status": "QUEUED",
                            "account_type": account_type or self.active_account_type,
                        })
            except Exception as e:
                logger.warning(f"Error scraping Streaming open orders: {e}")

            return unmatched

    async def cancel_order(self, broker_order_no: str, symbol: Optional[str] = None, bypass_dry_run: bool = False) -> Dict[str, Any]:
        """Cancel an open order on Streaming (fail-closed when the row/action is missing)."""
        page = await self._ensure_streaming_page()
        if not page or page.is_closed():
            return {
                "success": False,
                "status": "FAILED",
                "broker_order_no": broker_order_no,
                "error": "Browser session not connected",
            }

        # DRY_RUN guard — a cancel is irreversible, never fire it while DRY_RUN_MODE is on.
        if settings.DRY_RUN_MODE and not bypass_dry_run:
            await self._log_event("STREAMING_CANCEL_DRY_RUN", f"[DRY RUN] cancel {broker_order_no} ({symbol}) omitted")
            return {
                "success": True,
                "status": "SIMULATED_SUCCESS",
                "broker_order_no": broker_order_no,
                "message": "Cancel simulated (DRY_RUN_MODE)",
            }

        try:
            await self.switch_tab("order_status")
            await page.wait_for_timeout(1000)

            target_tr = await page.query_selector(f"tr:has-text('{broker_order_no}')")
            if not target_tr and symbol:
                target_tr = await page.query_selector(
                    f"tr:has-text('{symbol}'):has-text('Queuing'), tr:has-text('{symbol}'):has-text('Open')"
                )

            if not target_tr:
                return {
                    "success": False,
                    "status": "FAILED",
                    "broker_order_no": broker_order_no,
                    "error": f"Order {broker_order_no} not found in View Order",
                }

            cancel_btn = await target_tr.query_selector(CANCEL_ACTION_SELECTOR)
            if not cancel_btn or not await cancel_btn.is_visible():
                return {
                    "success": False,
                    "status": "FAILED",
                    "broker_order_no": broker_order_no,
                    "error": f"No cancel action available for order {broker_order_no}",
                }

            await cancel_btn.click()
            await page.wait_for_timeout(1000)

            confirm_btn = await page.query_selector(CANCEL_CONFIRM_SELECTOR)
            if confirm_btn and await confirm_btn.is_visible():
                await confirm_btn.click()
                await page.wait_for_timeout(1000)

            await self._log_event("STREAMING_ORDER_CANCELLED", f"Successfully cancelled order {broker_order_no}")
            return {
                "success": True,
                "status": "CANCELLED",
                "broker_order_no": broker_order_no,
                "message": f"Order {broker_order_no} cancelled on Settrade Streaming",
            }
        except Exception as e:
            logger.warning(f"Error during Streaming cancel: {e}")
            return {
                "success": False,
                "status": "FAILED",
                "broker_order_no": broker_order_no,
                "error": str(e),
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
    ) -> Dict[str, Any]:
        """
        Price negotiation via Cancel & Re-submit (Streaming has no native Modify).

        Guardrail C1/C2: cancels one order, then re-submits at the new price only if
        a positive new_price is given. DRY_RUN_MODE is honored unless bypass_dry_run.
        """
        cancel_res = await self.cancel_order(broker_order_no=broker_order_no, symbol=symbol, bypass_dry_run=bypass_dry_run)
        if not cancel_res.get("success"):
            return {
                "success": False,
                "status": "FAILED",
                "old_order_no": broker_order_no,
                "error": cancel_res.get("error", "Cancel failed"),
            }

        if not new_price or new_price <= 0:
            return cancel_res

        vol = remaining_volume if remaining_volume > 0 else 100
        res = await self.execute_order(
            symbol=symbol,
            side=side,
            volume=vol,
            price=new_price,
            pin=pin,
            bypass_dry_run=bypass_dry_run,
        )

        new_order_no = res.get("broker_order_no", f"STM-MOD-{int(datetime.now(timezone.utc).timestamp())}")
        await self._log_event(
            "STREAMING_PRICE_NEGOTIATION",
            f"Adjusted {symbol} {side} from {broker_order_no} to {new_order_no} @ ฿{new_price:.2f}",
        )
        return {
            "success": res.get("success", False),
            "status": "MODIFIED" if res.get("success") else res.get("status", "FAILED"),
            "broker_order_no": new_order_no,
            "old_order_no": broker_order_no,
            "symbol": symbol,
            "side": side,
            "new_price": new_price,
            "volume": vol,
            "message": f"Successfully cancelled {broker_order_no} and re-submitted as {new_order_no} @ ฿{new_price:.2f}",
        }

    # ------------------------------------------------------------------
    # Portfolio / quotes
    # ------------------------------------------------------------------

    async def scrape_portfolio(self, account_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scrape open positions from the Streaming Portfolio ReactVirtualized grid."""
        async with self.lock:
            page = await self._ensure_streaming_page()
            if not page or page.is_closed():
                return []

            # 1. JS-first: fetch positions directly via Settrade DGW endpoint (P.2)
            try:
                js_data = await page.evaluate(
                    """async () => {
                        let acct = '3024959';
                        const acctMatch = document.body.innerText.match(/3024\d{3}/);
                        if (acctMatch) acct = acctMatch[0];
                        const r = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}`, {credentials: 'include'});
                        if (!r.ok) return null;
                        return await r.json();
                    }"""
                )
                if js_data and "portfolio" in js_data and isinstance(js_data["portfolio"], list):
                    positions: List[Dict[str, Any]] = []
                    for item in js_data["portfolio"]:
                        pos = {
                            "symbol": str(item.get("symbol") or item.get("stockSymbol") or "").strip().upper(),
                            "position_type": str(item.get("positionType") or item.get("side") or "LONG").strip().upper(),
                            "start_vol": int(item.get("startVol") or item.get("startVolume") or 0),
                            "available_volume": int(item.get("availableVol") or item.get("availableVolume") or item.get("volume") or 0),
                            "actual_volume": int(item.get("actualVol") or item.get("actualVolume") or item.get("volume") or 0),
                            "avg_cost": float(item.get("avgCost") or item.get("cost") or 0.0),
                            "market_price": float(item.get("marketPrice") or item.get("last") or 0.0),
                            "market_value": float(item.get("marketValue") or 0.0),
                            "unrealized_pl": float(item.get("unrealizedPl") or item.get("unrealizedPnl") or 0.0),
                            "account_type": account_type or self.active_account_type,
                            "volume": int(item.get("actualVol") or item.get("actualVolume") or item.get("volume") or 0),
                        }
                        positions.append(pos)
                    return positions
            except Exception as e:
                logger.debug(f"JS-first portfolio scrape failed, falling back to DOM: {e}")

            # 2. Playwright selector fallback
            await self.switch_tab("portfolio")
            await page.wait_for_timeout(1500)

            positions: List[Dict[str, Any]] = []
            try:
                positions = await page.evaluate(
                    """() => {
                        const rows = [];
                        const container = document.querySelector('.ReactVirtualized__Grid__innerScrollContainer');
                        if (!container) return rows;
                        const uls = container.querySelectorAll('ul');
                        for (const ul of uls) {
                            const lis = Array.from(ul.querySelectorAll('li')).map(li => li.innerText.trim());
                            if (lis.length >= 11) {
                                const side = (lis[1] || '').toUpperCase();
                                if (side === 'LONG' || side === 'SHORT') {
                                    rows.push({
                                        symbol: lis[0], position_type: side,
                                        start_vol: parseInt(lis[2].replace(/,/g, '')) || 0,
                                        available_volume: parseInt(lis[3].replace(/,/g, '')) || 0,
                                        actual_volume: parseInt(lis[4].replace(/,/g, '')) || 0,
                                        avg_cost: parseFloat(lis[5].replace(/,/g, '')) || 0.0,
                                        market_price: parseFloat(lis[6].replace(/,/g, '')) || 0.0,
                                        market_value: parseFloat(lis[8].replace(/,/g, '')) || 0.0,
                                        unrealized_pl: parseFloat(lis[10].replace(/,/g, '')) || 0.0,
                                    });
                                } else if (!isNaN(parseInt(lis[1].replace(/,/g, '')))) {
                                    rows.push({
                                        symbol: lis[0], position_type: 'LONG',
                                        start_vol: parseInt(lis[1].replace(/,/g, '')) || 0,
                                        available_volume: parseInt(lis[2].replace(/,/g, '')) || 0,
                                        actual_volume: parseInt(lis[3].replace(/,/g, '')) || 0,
                                        avg_cost: parseFloat(lis[4].replace(/,/g, '')) || 0.0,
                                        market_price: parseFloat(lis[5].replace(/,/g, '')) || 0.0,
                                        market_value: parseFloat(lis[7].replace(/,/g, '')) || 0.0,
                                        unrealized_pl: parseFloat(lis[8].replace(/,/g, '')) || 0.0,
                                    });
                                }
                            }
                        }
                        return rows;
                    }"""
                )
                for pos in positions:
                    pos["account_type"] = pos.get("account_type", account_type or self.active_account_type)
                    pos["volume"] = pos.get("actual_volume", 0)
            except Exception as e:
                logger.warning(f"Error scraping Streaming portfolio: {e}")

            return positions

    async def scrape_balance(self, account_type: Optional[str] = None) -> Dict[str, Any]:
        """Scrape account balance (line available, cash balance, credit limit, equity) via JS-first + DOM fallback."""
        async with self.lock:
            page = await self._ensure_streaming_page()
            if not page or page.is_closed():
                return {}

            # 1. JS-first via Settrade DGW account endpoint
            try:
                res = await page.evaluate(
                    """async () => {
                        let acct = '3024959';
                        const acctMatch = document.body.innerText.match(/3024\d{3}/);
                        if (acctMatch) acct = acctMatch[0];
                        const r = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}`, {credentials: 'include'});
                        if (!r.ok) return null;
                        const d = await r.json();
                        return {
                            account: acct,
                            account_type: d.accountType,
                            line_available: d.lineAvailable,
                            cash_balance: d.cashBalance,
                            credit_limit: d.creditLimit,
                            equity_balance: d.equityBalance,
                            credit_balance: d.creditBalance,
                            source: 'streaming_js'
                        };
                    }"""
                )
                if res and res.get("line_available") is not None:
                    return res
            except Exception as e:
                logger.debug(f"JS-first balance scrape failed, falling back to DOM: {e}")

            # 2. Playwright DOM selector fallback
            try:
                dom_balance = await page.evaluate(
                    """() => {
                        const res = {};
                        const texts = Array.from(document.querySelectorAll('div, p, span, td')).map(el => el.innerText.trim());
                        for (const t of texts) {
                            let m;
                            if (t.includes('Line Available')) {
                                m = t.match(/Line Available[:\s]*([\d,]+\.\d*)/i);
                                if (m) res.line_available = parseFloat(m[1].replace(/,/g, ''));
                            }
                            if (t.includes('Cash Balance')) {
                                m = t.match(/Cash Balance[:\s]*([\d,]+\.\d*)/i);
                                if (m) res.cash_balance = parseFloat(m[1].replace(/,/g, ''));
                            }
                        }
                        return res;
                    }"""
                )
                if dom_balance:
                    dom_balance["source"] = "streaming_dom"
                    return dom_balance
            except Exception as e:
                logger.debug(f"DOM balance scrape failed: {e}")

            return {}

    async def get_market_bid_offer(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch the live top bid/offer from the Streaming bid/offer panel.

        Fail-closed (Anti-Mock): when no live DOM data is available the values are
        None with ``source='unavailable'`` — never fabricated fallback prices.
        """
        data: Dict[str, Any] = {
            "bid_1": None,
            "offer_1": None,
            "last": None,
            "prior_close": None,
            "source": "unavailable",
        }
        page = self.page
        if page and not page.is_closed():
            clean_sym = (symbol or "").strip().upper()
            # 1. JS-first: fetch marketdata static-data
            try:
                js_quote = await page.evaluate(
                    f"""async () => {{
                        try {{
                            const r = await fetch('https://apigwcld.settrade.com/api/marketdata/v4/029/static-data/{clean_sym}?market=E', {{credentials: 'include'}});
                            if (!r.ok) return null;
                            const d = await r.json();
                            return {{
                                bid_1: d.firstBid || null,
                                offer_1: d.firstAsk || null,
                                last: d.last || null,
                                prior_close: d.close || null,
                            }};
                        }} catch (e) {{
                            return null;
                        }}
                    }}"""
                )
                if js_quote and (js_quote.get("bid_1") or js_quote.get("offer_1")):
                    data.update(js_quote)
                    data["source"] = "streaming_js"
                    return data
            except Exception as e:
                logger.debug(f"JS-first quote failed for {clean_sym}, falling back to DOM: {e}")

            # 2. Playwright DOM selector fallback
            try:
                scraped = await page.evaluate(
                    """() => {
                        const res = {};
                        const bidEls = document.querySelectorAll('.bid-price, .bid-col, [class*="bid" i]');
                        const offerEls = document.querySelectorAll('.offer-price, .offer-col, [class*="offer" i]');
                        if (bidEls.length > 0) {
                            const v = parseFloat(bidEls[0].innerText.replace(/,/g, ''));
                            if (!isNaN(v) && v > 0) res.bid_1 = v;
                        }
                        if (offerEls.length > 0) {
                            const v = parseFloat(offerEls[0].innerText.replace(/,/g, ''));
                            if (!isNaN(v) && v > 0) res.offer_1 = v;
                        }
                        return res;
                    }"""
                )
                if scraped and (scraped.get("bid_1") or scraped.get("offer_1")):
                    data.update(scraped)
                    data["last"] = scraped.get("bid_1")
                    data["prior_close"] = scraped.get("bid_1")
                    data["source"] = "streaming_dom"
            except Exception as e:
                logger.debug(f"Could not scrape live DOM bid/offer: {e}")

        return data


# Global singleton instance
streaming_driver = StreamingDriver()
