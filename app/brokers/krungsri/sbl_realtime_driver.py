"""
Krungsri SBL Real Time Driver
=============================
Autonomous driver for Krungsri Securities SBL Real Time Portal (/sblweb/MainSBL.aspx).
Replaces the legacy TradeMan SBL scraping mechanism with the real Member SSO portal.

Capabilities:
1. Full On-Demand Scraping:
   - SET50, SET100, NEW SEC borrowable inventories (Volume, Fee %, Initial Margin %)
   - XD/XR Corporate Actions Calendar (Symbol, Book Date, Type e.g. XD/XR/XM)
   - Real-time Purchasing Power (PP)
   - Active Borrow Transactions Table
2. Risk Supervision & Hard Blocker:
   - Hard blocks any short selling or borrowing on symbols registered in XD/XR list
     to prevent 100% dividend compensation liabilities.
3. Thread-safe Caching in `data/krungsri_sbl_realtime.json`.
"""

import os
import re
import json
import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from playwright.async_api import async_playwright, Page, BrowserContext

from app.core.config import settings

logger = logging.getLogger("Krungsri.SBLRealtime")

CACHE_FILE = os.path.join(settings.PROJECT_ROOT if hasattr(settings, "PROJECT_ROOT") else os.getcwd(), "data", "krungsri_sbl_realtime.json")
SBL_START_URL = "https://www.krungsrisecurities.com/th/SBL/start.aspx"

# ─── SBL cache staleness (fail-closed policy) ─────────────────────────────────
# Default freshness window = 24 hours ("1 trading day" in the conservative sense:
# anything older than yesterday's snapshot must not be trusted to permit a borrow).
# A long weekend therefore makes a Friday snapshot stale on Monday — that is
# intentional; the operator runs `/sbl sync` before borrowing.
# Override, in priority order: settings.SBL_CACHE_STALENESS_HOURS (attribute, for
# tests/integration), then env SBL_CACHE_STALENESS_HOURS, then 24h.
DEFAULT_STALENESS_HOURS = 24.0

# Cache keys that may carry the snapshot timestamp (legacy files first).
_CACHE_TIMESTAMP_KEYS = ("timestamp", "scraped_at", "cached_at")


def _staleness_seconds() -> float:
    """Freshness window in seconds (see DEFAULT_STALENESS_HOURS for the policy)."""
    raw = getattr(settings, "SBL_CACHE_STALENESS_HOURS", None)
    if raw is None:
        raw = os.getenv("SBL_CACHE_STALENESS_HOURS")
    try:
        hours = float(raw) if raw is not None else DEFAULT_STALENESS_HOURS
    except (TypeError, ValueError):
        hours = DEFAULT_STALENESS_HOURS
    if hours <= 0:
        hours = DEFAULT_STALENESS_HOURS
    return hours * 3600.0


def _cache_timestamp_of(data: Dict[str, Any]) -> Optional[Any]:
    for key in _CACHE_TIMESTAMP_KEYS:
        if data.get(key):
            return data.get(key)
    return None


def _parse_cache_timestamp(raw: Any) -> Optional[datetime]:
    """Best-effort parse of a cache timestamp; None when absent/unparseable."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        if value <= 0:
            return None
        if value > 1e11:  # milliseconds since epoch
            value /= 1000.0
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        # Legacy writers stamped naive UTC (datetime.utcnow()); assume UTC.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class KrungsriSBLRealtimeDriver:
    """Production driver for Krungsri Member SSO SBL Real Time application."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cached_data: Optional[Dict[str, Any]] = None
        # True when the snapshot came from disk without any usable timestamp —
        # such a cache is treated as stale (fail-closed) rather than trusted.
        self._cache_stamp_missing = False
        self._load_cache_from_disk()

    def _load_cache_from_disk(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._cached_data = data
                    self._cache_stamp_missing = _parse_cache_timestamp(_cache_timestamp_of(data)) is None
                    if self._cache_stamp_missing:
                        logger.warning(
                            f"SBL cache {CACHE_FILE} has no usable timestamp — treating it as stale (fail-closed)"
                        )
                else:
                    self._cached_data = None
                    self._cache_stamp_missing = False
            except Exception as e:
                logger.warning(f"Failed to read SBL cache from {CACHE_FILE}: {e}")

    def _save_cache_to_disk(self, data: Dict[str, Any]):
        try:
            # Every persisted snapshot must carry a timestamp, otherwise the next
            # process cannot tell fresh data from a stale file (and must block).
            if isinstance(data, dict) and _parse_cache_timestamp(_cache_timestamp_of(data)) is None:
                data["timestamp"] = datetime.now(timezone.utc).isoformat()
            self._cache_stamp_missing = False
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._cached_data = data
        except Exception as e:
            logger.error(f"Failed to persist SBL cache: {e}")

    def get_cached_data(self) -> Optional[Dict[str, Any]]:
        if not self._cached_data:
            self._load_cache_from_disk()
        return self._cached_data

    def cache_status(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Classifies the SBL snapshot: ``CACHE_MISS`` | ``CACHE_STALE`` | ``CACHE_FRESH``.

        Also returns ``age_seconds``, the raw ``timestamp``, the active
        ``staleness_seconds`` window and a Thai operator ``message`` — the read
        path (`/sbl`, `/sbl pool <sym>`) renders that message instead of raising
        when there is nothing trustworthy to show.

        A snapshot written by this process (`_save_cache_to_disk`, which always
        stamps it) is trusted; a snapshot loaded from disk without a timestamp is
        stale; a disk snapshot older than the window is stale.
        """
        window = _staleness_seconds()
        status: Dict[str, Any] = {
            "state": "CACHE_MISS",
            "timestamp": None,
            "age_seconds": None,
            "staleness_seconds": window,
            "message": "ยังไม่มีข้อมูลคลังหุ้นยืม SBL — พิมพ์ /sbl sync ก่อน",
        }
        data = self.get_cached_data()
        if not isinstance(data, dict) or not data:
            return status

        raw_ts = _cache_timestamp_of(data)
        ts = _parse_cache_timestamp(raw_ts)
        if raw_ts is not None:
            status["timestamp"] = raw_ts

        if ts is None:
            if self._cache_stamp_missing:
                status.update(
                    state="CACHE_STALE",
                    message="ข้อมูลคลัง SBL ไม่มี timestamp จึงตรวจความสดไม่ได้ — พิมพ์ /sbl sync ก่อน",
                )
                return status
            status.update(state="CACHE_FRESH", message="ข้อมูลคลัง SBL สด (เขียนในโปรเซสนี้)")
            return status

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age = max(0.0, (current - ts).total_seconds())
        status["age_seconds"] = round(age, 1)
        if age > window:
            status.update(
                state="CACHE_STALE",
                message=(
                    f"ข้อมูลคลัง SBL เก่าเกิน {window / 3600:.0f} ชม. "
                    f"(อายุ {age / 3600:.1f} ชม.) — พิมพ์ /sbl sync ก่อน"
                ),
            )
            return status
        status.update(state="CACHE_FRESH", message="ข้อมูลคลัง SBL สด")
        return status

    def invalidate_cache(self):
        """Invalidates in-memory cache to force reload on next query."""
        self._cached_data = None

    async def scrape_full_pool(self, headless: bool = True) -> Dict[str, Any]:
        """
        Executes an on-demand full scan of Krungsri SBL Real Time.
        Scrapes SET50, SET100, NEW SEC, XD/XR, Purchasing Power, and Active Transactions.
        """
        async with self._lock:
            session_file = settings.SESSION_STATE_PATH
            if not os.path.exists(session_file):
                return {
                    "success": False,
                    "error": f"Session file not found at {session_file}. Run ./start_homelab.sh first."
                }

            playwright = await async_playwright().start()
            launch_args = {
                "headless": headless,
                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,900"]
            }
            if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
                launch_args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE

            browser = await playwright.chromium.launch(**launch_args)
            context = await browser.new_context(
                storage_state=session_file,
                viewport={"width": 1280, "height": 900}
            )
            page = await context.new_page()

            try:
                logger.info(f"Navigating to Krungsri SBL: {SBL_START_URL}")
                await page.goto(SBL_START_URL, wait_until="networkidle", timeout=30000)

                # 1. Purchasing Power & Account Info
                body_text = await page.inner_text("body")
                pp_match = re.search(r"PP\s*=\s*([0-9,.]+)", body_text)
                purchasing_power = float(pp_match.group(1).replace(",", "")) if pp_match else 0.0

                cus_code = ""
                cus_name = ""
                try:
                    cus_code_el = await page.query_selector("#ctl00_MainCenter_txSearchCode, #ctl00_MainCenter_txtCusCode")
                    if cus_code_el:
                        cus_code = (await cus_code_el.input_value()).strip()
                    cus_name_el = await page.query_selector("#ctl00_MainCenter_lbCusName")
                    if cus_name_el:
                        cus_name = (await cus_name_el.input_value()).strip()
                except Exception:
                    pass

                # 2. Extract SET 50 (Default active tab)
                logger.info("Extracting SET50 inventory...")
                set50_inventory = await self._extract_inventory_table(page)

                # 3. Switch to SET 100
                logger.info("Extracting SET100 inventory...")
                await page.click("#MainCenter_lbSet100")
                await page.wait_for_timeout(1800)
                set100_inventory = await self._extract_inventory_table(page)

                # 4. Switch to NEW SEC
                logger.info("Extracting NEW SEC inventory...")
                await page.click("#MainCenter_lbNewSec")
                await page.wait_for_timeout(1800)
                newsec_inventory = await self._extract_inventory_table(page)

                # 5. Switch to XD, XR (CRITICAL RISK TAB)
                logger.info("Extracting XD/XR Corporate Actions Calendar...")
                await page.click("#MainCenter_lbXD")
                await page.wait_for_timeout(1800)
                xd_xr_calendar = await self._extract_xd_xr_table(page)

                # 6. Extract Active Borrow Transactions
                active_transactions = await self._extract_transactions_table(page)

                result_data = {
                    "success": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "KRUNGSRI_SSO_SBL_REALTIME",
                    "url": page.url,
                    "account_no": cus_code or getattr(settings, "TRADEMAN_ACCOUNT_NO_MARGIN", "302495"),
                    "account_name": cus_name or "คุณอารยะ สวัสดิชัย",
                    "purchasing_power": purchasing_power,
                    "counts": {
                        "set50": len(set50_inventory),
                        "set100": len(set100_inventory),
                        "newsec": len(newsec_inventory),
                        "xd_xr_risks": len(xd_xr_calendar),
                        "active_borrows": len(active_transactions)
                    },
                    "set50_inventory": set50_inventory,
                    "set100_inventory": set100_inventory,
                    "newsec_inventory": newsec_inventory,
                    "xd_xr_inventory": xd_xr_calendar,
                    "active_borrow_transactions": active_transactions
                }

                self._save_cache_to_disk(result_data)
                logger.info(f"✅ SBL Realtime sync complete: PP={purchasing_power:,.2f} | SET50={len(set50_inventory)} | XD/XR Risks={len(xd_xr_calendar)}")
                return result_data

            except Exception as e:
                logger.error(f"Error during SBL Realtime scraping: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "cached_data": self._cached_data
                }
            finally:
                await browser.close()
                await playwright.stop()

    async def _extract_inventory_table(self, page: Page) -> List[Dict[str, Any]]:
        """Parses the 4-column inventory sub-tables into structured items."""
        js_extract = """
        () => {
            const items = [];
            const seen = new Set();
            // In MainSBL.aspx, tables contain rows with Symbol, Fee, Volume, IM
            const tables = document.querySelectorAll('table');
            tables.forEach(table => {
                const rows = table.querySelectorAll('tr');
                rows.forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim());
                    // Check if 4 cells: [Symbol, Fee, Volume, IM]
                    if (cells.length >= 4) {
                        const sym = cells[0].toUpperCase();
                        const feeStr = cells[1];
                        const volStr = cells[2].replace(/,/g, '');
                        const imStr = cells[3];
                        
                        // Validate symbol format (alphanumeric 2-10 chars, not header)
                        if (/^[A-Z0-9]{2,10}$/.test(sym) && !['SYMBOL', 'FEE', 'VOLUME', 'IM', 'SET50', 'SET100'].includes(sym)) {
                            if (!seen.has(sym)) {
                                seen.add(sym);
                                const fee = parseFloat(feeStr) || 3.5;
                                const vol = parseInt(volStr, 10) || 0;
                                const im = parseFloat(imStr) || 50.0;
                                items.push({
                                    symbol: sym,
                                    borrow_fee_pct: fee,
                                    available_qty: vol,
                                    initial_margin_pct: im
                                });
                            }
                        }
                    }
                });
            });
            return items;
        }
        """
        try:
            return await page.evaluate(js_extract)
        except Exception as e:
            logger.warning(f"Failed to evaluate inventory table: {e}")
            return []

    async def _extract_xd_xr_table(self, page: Page) -> List[Dict[str, Any]]:
        """Parses the XD/XR corporate actions calendar table."""
        js_extract = """
        () => {
            const items = [];
            const seen = new Set();
            const validCorporateActions = ['XD', 'XR', 'XM', 'XW', 'XB', 'XI', 'XA', 'XE'];
            const tables = document.querySelectorAll('table');
            tables.forEach(table => {
                // Ignore transactions table at bottom
                if (table.closest('#ctl00_MainCenter_rgTrans_ctl00') || table.id.includes('rgTrans')) return;
                const rows = table.querySelectorAll('tr');
                rows.forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim());
                    // XD/XR format: [Symbol, Book Date, Type]
                    if (cells.length >= 3) {
                        const sym = cells[0].toUpperCase();
                        const dateStr = cells[1];
                        const typeStr = cells[2].toUpperCase();
                        
                        if (/^[A-Z0-9]{2,10}$/.test(sym) && !['SYMBOL', 'BOOK DATE', 'TYPE'].includes(sym) && validCorporateActions.includes(typeStr)) {
                            if (!seen.has(sym)) {
                                seen.add(sym);
                                items.push({
                                    symbol: sym,
                                    book_date: dateStr,
                                    type: typeStr,
                                    sign: typeStr
                                });
                            }
                        }
                    }
                });
            });
            return items;
        }
        """
        try:
            return await page.evaluate(js_extract)
        except Exception as e:
            logger.warning(f"Failed to evaluate XD/XR table: {e}")
            return []

    async def _extract_transactions_table(self, page: Page) -> List[Dict[str, Any]]:
        """Parses active borrowing contracts from the transactions table."""
        js_extract = """
        () => {
            const items = [];
            const headerTable = document.querySelector('#ctl00_MainCenter_rgTrans_ctl00_Header');
            const dataTable = document.querySelector('#ctl00_MainCenter_rgTrans_ctl00');
            if (!dataTable) return items;
            
            const rows = dataTable.querySelectorAll('tbody tr');
            rows.forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('td')).map(c => c.innerText.trim());
                // Ref.No, Tran Date, Time, Symbol, Type, Quantity, Borrowing Price, Borrowing Value, Fee Rate, Close Date
                if (cells.length >= 9) {
                    const refNo = cells[0];
                    if (refNo && refNo !== 'No records to display.') {
                        items.push({
                            ref_no: refNo,
                            tran_date: cells[1],
                            time: cells[2],
                            symbol: cells[3].toUpperCase(),
                            type: cells[4],
                            quantity: parseInt(cells[5].replace(/,/g, ''), 10) || 0,
                            borrow_price: parseFloat(cells[6].replace(/,/g, '')) || 0.0,
                            borrow_value: parseFloat(cells[7].replace(/,/g, '')) || 0.0,
                            fee_rate: parseFloat(cells[8]) || 3.5,
                            close_date: cells[9] || ''
                        });
                    }
                }
            });
            return items;
        }
        """
        try:
            return await page.evaluate(js_extract)
        except Exception as e:
            logger.warning(f"Failed to extract transactions table: {e}")
            return []

    def check_symbol_risk(self, symbol: str) -> Dict[str, Any]:
        """
        Validates whether a symbol is safe to short/borrow. **Fail-closed.**

        Decision order
        --------------
        1. ``HARD_BLOCKED_XD_XR`` — symbol is on the XD/XR corporate-action
           calendar. Checked first (and on any age of snapshot) because a
           registered ex-dividend/ex-rights marker does not stop being true when
           the pool list ages; it is the 100% dividend-compensation trap.
        2. ``CACHE_MISS`` — there is no SBL snapshot at all (no cache file /
           empty cache). ``is_blocked: True``.
        3. ``CACHE_STALE`` — the snapshot is older than the freshness window
           (``DEFAULT_STALENESS_HOURS`` = **24h / one trading day**; see
           ``_staleness_seconds`` for overrides) or was loaded from disk without
           any usable timestamp. ``is_blocked: True``. Consequence: a Friday
           snapshot is stale on Monday — run ``/sbl sync`` before borrowing.
        4. Fresh snapshot, symbol in a pool with ``available_qty > 0`` (and no
           XD/XR marker, checked in step 1) → ``BORROW_ALLOWED``. This is the
           **only** path to ``is_blocked: False`` for a borrow.
        5. Fresh snapshot, symbol in a pool with ``available_qty == 0`` →
           ``OUT_OF_STOCK`` (blocked).
        6. Fresh snapshot, symbol absent from every pool → ``NOT_IN_POOL``
           (blocked). *Deliberate change* from the old ``UNVERIFIED_INVENTORY``
           ``is_blocked: False``: a fresh, complete snapshot that does not list
           the symbol is evidence there is no borrowable inventory to lend, so
           waving the borrow through was a fail-open hole. The operator can
           still borrow after a manual check on the broker portal; this function
           simply refuses to *vouch* for it. The old verdict name is preserved
           in ``legacy_verdict`` for log/UI continuity.

        The read path is unaffected: ``cache_status()`` carries a Thai operator
        message ("ยังไม่มีข้อมูล … /sbl sync") so `/sbl` and `/sbl pool <sym>`
        render a hint instead of raising.
        """
        sym = symbol.strip().upper()
        cache = self.get_cached_data() or {}
        status = self.cache_status()
        xd_list = cache.get("xd_xr_inventory", []) or []
        set50 = cache.get("set50_inventory", []) or []
        set100 = cache.get("set100_inventory", []) or []
        newsec = cache.get("newsec_inventory", []) or []

        def _result(blocked: bool, verdict: str, badge: str, reason: str, **extra) -> Dict[str, Any]:
            out = {
                "symbol": sym,
                "is_blocked": blocked,
                "verdict": verdict,
                "badge": badge,
                "reason": reason,
                "available_qty": 0,
                "borrow_fee_pct": 3.5,
                "cache_state": status.get("state"),
                "cache_age_seconds": status.get("age_seconds"),
            }
            out.update(extra)
            return out

        # 1. XD/XR hard block — independent of snapshot age.
        xd_match = next((x for x in xd_list if isinstance(x, dict) and (x.get("symbol") or "").strip().upper() == sym), None)
        if xd_match:
            b_date = xd_match.get("book_date", "")
            x_type = xd_match.get("type", "XD")
            return _result(
                True,
                "HARD_BLOCKED_XD_XR",
                f"⛔ บล็อกคำสั่ง (ติด {x_type} วันที่ {b_date})",
                (
                    f"⛔ ห้ามเปิดสถานะขายชอร์ต (Short Sell) เด็ดขาด เนื่องจากหุ้น {sym} มีกำหนดขึ้นเครื่องหมาย {x_type} "
                    f"ในวันที่ {b_date} ซึ่งตามกฎเกณฑ์ SBL ผู้ยืมจะต้องจ่ายเงินชดเชยปันผลหรือสิทธิ์ 100% ให้แก่ผู้ให้ยืม"
                ),
                corporate_action=xd_match,
            )

        # 2./3. No trustworthy snapshot → fail closed.
        if status.get("state") != "CACHE_FRESH":
            verdict = "CACHE_MISS" if status.get("state") == "CACHE_MISS" else "CACHE_STALE"
            return _result(
                True,
                verdict,
                "⚪ ไม่มีข้อมูลคลัง SBL ที่เชื่อถือได้",
                (
                    f"⚠️ ยังไม่มีข้อมูลคลังหุ้นยืม SBL ที่สดพอจะยืนยันได้ว่าหุ้น {sym} ให้ยืมได้ "
                    f"({status.get('message')}) — ระบบบล็อกไว้ก่อนเพื่อความปลอดภัย (fail-closed)"
                ),
                cache_message=status.get("message"),
                operator_hint="พิมพ์ /sbl sync เพื่อรีเฟรชคลัง SBL แล้วลองใหม่",
            )

        # 4./5./6. Fresh snapshot: look the symbol up across every pool.
        all_inv = set50 + set100 + newsec
        inv_item = next(
            (i for i in all_inv if isinstance(i, dict) and (i.get("symbol") or "").strip().upper() == sym),
            None,
        )
        if inv_item:
            avail = inv_item.get("available_qty", 0) or 0
            fee = inv_item.get("borrow_fee_pct", 3.5)
            im = inv_item.get("initial_margin_pct", 50.0)
            if avail > 0:
                return _result(
                    False,
                    "BORROW_ALLOWED",
                    f"🟢 พร้อมยืม Short ({avail:,} หุ้น)",
                    f"มีคลังหุ้นพร้อมให้ยืม {avail:,} หุ้น ดอกเบี้ย {fee}% ปลอดภัยไม่มีเครื่องหมาย XD/XR",
                    available_qty=avail,
                    borrow_fee_pct=fee,
                    initial_margin_pct=im,
                )
            return _result(
                True,
                "OUT_OF_STOCK",
                "🔴 คลังหมด (Available = 0)",
                f"ไม่มีสต็อกหุ้น {sym} ให้ยืมในคลัง Krungsri SBL ณ ขณะนี้",
                borrow_fee_pct=fee,
                initial_margin_pct=im,
            )

        return _result(
            True,
            "NOT_IN_POOL",
            "⚪ ไม่อยู่ในคลังยืม (บล็อกไว้ก่อน)",
            (
                f"หุ้น {sym} ไม่ได้อยู่ในหมวด SET50/SET100/NEWSEC ของคลัง SBL ที่ดึงมาล่าสุด "
                f"จึงยังยืนยันไม่ได้ว่ามีหุ้นให้ยืม — ระบบบล็อกไว้ก่อน (fail-closed) "
                f"หากต้องการยืมจริงให้ตรวจหน้าต่างยืมหุ้นเดี่ยวของ Krungsri ก่อน"
            ),
            legacy_verdict="UNVERIFIED_INVENTORY",
            operator_hint="พิมพ์ /sbl sync เพื่อรีเฟรชคลัง SBL หรือตรวจสอบที่หน้าต่างยืมหุ้นเดี่ยว",
        )

    async def scrape_sbl_available_inventory(self, symbol: str) -> int:
        """
        Returns borrowable volume for a symbol from SBL Real Time cache or scrape.

        Read-safe: never raises, returns 0 when the snapshot is missing/stale and
        a refresh cannot be performed (the caller renders "ยังไม่มีข้อมูล").
        """
        sym = symbol.strip().upper()
        risk = self.check_symbol_risk(sym)

        # No snapshot at all → one best-effort refresh (only when a saved session
        # exists), then re-evaluate. Deliberately NOT triggered for a merely stale
        # snapshot: repeatedly poking the SBL portal from a read-only command
        # (`/sbl pool`) decays the SSO session — the operator refreshes explicitly
        # with `/sbl sync` instead. Never raises.
        if risk.get("verdict") == "CACHE_MISS":
            try:
                if os.path.exists(settings.SESSION_STATE_PATH):
                    res = await self.scrape_full_pool(headless=True)
                    if res.get("success"):
                        risk = self.check_symbol_risk(sym)
            except Exception as e:
                logger.warning(f"Live SBL inventory refresh failed: {e}")

        if risk.get("is_blocked"):
            if risk.get("verdict") == "CACHE_STALE":
                logger.warning(
                    f"SBL pool query for {sym} answered 0 — snapshot stale, operator must run /sbl sync"
                )
            return 0
        return risk.get("available_qty", 0) or 0

    async def scrape_sbl_lots(self) -> List[Dict[str, Any]]:
        """Returns active borrow transactions from SBL Real Time."""
        cache = self.get_cached_data()
        if not cache or not cache.get("active_borrow_transactions"):
            res = await self.scrape_full_pool(headless=True)
            cache = res if res.get("success") else cache
        txs = (cache or {}).get("active_borrow_transactions", [])
        lots = []
        for tx in txs:
            lots.append({
                "broker_tx_id": tx.get("ref_no"),
                "symbol": tx.get("symbol"),
                "borrow_qty": tx.get("quantity", 0),
                "remaining_qty": tx.get("quantity", 0),
                "borrow_price": tx.get("borrow_price", 0.0),
                "borrow_fee_rate": tx.get("fee_rate", 3.5),
                "borrow_date": tx.get("tran_date", ""),
            })
        return lots

    async def execute_sbl_borrow(self, symbol: str, volume: int) -> Dict[str, Any]:
        """
        Executes a borrow order via SBL Real Time (/sblweb/MainSBL.aspx).
        Respects DRY_RUN_MODE and enforces XD/XR hard block.
        """
        sym = symbol.strip().upper()
        risk = self.check_symbol_risk(sym)
        if risk.get("is_blocked") and risk.get("verdict") == "HARD_BLOCKED_XD_XR":
            return {
                "success": False,
                "status": "BLOCKED_BY_XD_XR",
                "error": risk.get("reason"),
            }
        # Fail-closed (2.11b): never start a borrow flow on a snapshot we cannot
        # trust — an empty/stale pool cache used to wave the borrow through.
        if risk.get("verdict") in ("CACHE_MISS", "CACHE_STALE"):
            return {
                "success": False,
                "status": "BLOCKED_BY_STALE_CACHE",
                "error": risk.get("reason") or "ข้อมูลคลัง SBL ยังไม่สด — พิมพ์ /sbl sync ก่อนยืมหุ้น",
            }

        # 1. Try JS-first via active CDP session
        try:
            from scripts.broker_cdp.js_runner import run_snippet
            cdp_res = await run_snippet(
                broker="kss",
                snippet_name="sbl_borrow",
                target_kind="sbl",
                arg={
                    "symbol": sym,
                    "volume": volume,
                    "dry_run": bool(settings.DRY_RUN_MODE),
                },
                timeout_s=30.0,
            )
            if cdp_res.get("success") and cdp_res.get("data"):
                data = cdp_res["data"]
                if data.get("success"):
                    return {
                        "success": True,
                        "status": data.get("status", "SBL_BORROW_SUBMITTED"),
                        "symbol": sym,
                        "volume": volume,
                        "dry_run": data.get("dry_run", bool(settings.DRY_RUN_MODE)),
                        "purchasing_power": data.get("purchasing_power"),
                        "source": "sbl_borrow_js",
                    }
                elif data.get("status") == "BLOCKED_BY_XD_XR":
                    return {
                        "success": False,
                        "status": "BLOCKED_BY_XD_XR",
                        "error": data.get("error"),
                        "source": "sbl_borrow_js",
                    }
        except Exception as e:
            logger.warning(f"SBL borrow JS execution failed, falling back: {e}")

        if settings.DRY_RUN_MODE:
            logger.info(f"[DRY-RUN] SBL Realtime borrow: {sym} {volume:,} shares")
            return {
                "success": True,
                "status": "SBL_BORROW_DRY_RUN",
                "symbol": sym,
                "volume": volume,
                "transaction_id": f"SBL-RT-{sym}-{int(time.time())}",
                "account_no": getattr(settings, "TRADEMAN_ACCOUNT_NO_MARGIN", "3024959"),
                "fee_rate": risk.get("borrow_fee_pct", 3.50),
            }

        # Fail-closed: live SBL borrow via Web DOM is not implemented yet.
        # Fabricating a SUBMITTED success on a live path would violate the
        # "no fabricated live success" guardrail and risk capital.
        return {
            "success": False,
            "status": "LIVE_SBL_NOT_IMPLEMENTED",
            "error": "Live SBL via Web DOM is disabled/not implemented — fail-closed to protect capital",
        }

    async def return_sbl_shares(self, lot_id: str, return_qty: int, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Submits SBL share return request via SBL Real Time.
        Respects DRY_RUN_MODE.
        """
        # 1. Try JS-first via active CDP session
        try:
            from scripts.broker_cdp.js_runner import run_snippet
            cdp_res = await run_snippet(
                broker="kss",
                snippet_name="sbl_return",
                target_kind="sbl",
                arg={
                    "ref_no": lot_id,
                    "symbol": symbol or "",
                    "volume": return_qty,
                    "dry_run": bool(settings.DRY_RUN_MODE),
                },
                timeout_s=30.0,
            )
            if cdp_res.get("success") and cdp_res.get("data"):
                data = cdp_res["data"]
                if data.get("success"):
                    return {
                        "success": True,
                        "status": data.get("status", "SBL_RETURN_SUBMITTED"),
                        "lot_id": lot_id,
                        "symbol": symbol or data.get("symbol"),
                        "return_qty": return_qty,
                        "dry_run": data.get("dry_run", bool(settings.DRY_RUN_MODE)),
                        "source": "sbl_return_js",
                    }
        except Exception as e:
            logger.warning(f"SBL return JS execution failed, falling back: {e}")

        if settings.DRY_RUN_MODE:
            logger.info(f"[DRY-RUN] SBL Realtime return: {symbol or lot_id} {return_qty:,} shares (lot={lot_id})")
            return {
                "success": True,
                "status": "SBL_RETURN_DRY_RUN",
                "symbol": symbol,
                "return_qty": return_qty,
                "lot_id": lot_id,
            }

        # Fail-closed: live SBL return via Web DOM is not implemented yet.
        return {
            "success": False,
            "status": "LIVE_SBL_NOT_IMPLEMENTED",
            "error": "Live SBL via Web DOM is disabled/not implemented — fail-closed to protect capital",
        }


krungsri_sbl_driver = KrungsriSBLRealtimeDriver()

