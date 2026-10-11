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
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from playwright.async_api import async_playwright, Page, BrowserContext

from app.core.config import settings

logger = logging.getLogger("Krungsri.SBLRealtime")

CACHE_FILE = os.path.join(settings.PROJECT_ROOT if hasattr(settings, "PROJECT_ROOT") else os.getcwd(), "data", "krungsri_sbl_realtime.json")
SBL_START_URL = "https://www.krungsrisecurities.com/th/SBL/start.aspx"


class KrungsriSBLRealtimeDriver:
    """Production driver for Krungsri Member SSO SBL Real Time application."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cached_data: Optional[Dict[str, Any]] = None
        self._load_cache_from_disk()

    def _load_cache_from_disk(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._cached_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read SBL cache from {CACHE_FILE}: {e}")

    def _save_cache_to_disk(self, data: Dict[str, Any]):
        try:
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
        Validates whether a symbol is safe to short/borrow.
        Enforces HARD BLOCK on any symbol in the XD/XR list.
        """
        sym = symbol.strip().upper()
        cache = self.get_cached_data() or {}
        xd_list = cache.get("xd_xr_inventory", [])
        set50 = cache.get("set50_inventory", [])
        set100 = cache.get("set100_inventory", [])
        newsec = cache.get("newsec_inventory", [])

        # Check XD/XR match
        xd_match = next((x for x in xd_list if x.get("symbol") == sym), None)
        if xd_match:
            b_date = xd_match.get("book_date", "")
            x_type = xd_match.get("type", "XD")
            return {
                "symbol": sym,
                "is_blocked": True,
                "verdict": "HARD_BLOCKED_XD_XR",
                "badge": f"⛔ บล็อกคำสั่ง (ติด {x_type} วันที่ {b_date})",
                "reason": (
                    f"⛔ ห้ามเปิดสถานะขายชอร์ต (Short Sell) เด็ดขาด เนื่องจากหุ้น {sym} มีกำหนดขึ้นเครื่องหมาย {x_type} "
                    f"ในวันที่ {b_date} ซึ่งตามกฎเกณฑ์ SBL ผู้ยืมจะต้องจ่ายเงินชดเชยปันผลหรือสิทธิ์ 100% ให้แก่ผู้ให้ยืม"
                ),
                "corporate_action": xd_match,
                "available_qty": 0,
                "borrow_fee_pct": 3.5
            }

        # Check available quantity across inventory pools
        all_inv = set50 + set100 + newsec
        inv_item = next((i for i in all_inv if i.get("symbol") == sym), None)
        if inv_item:
            avail = inv_item.get("available_qty", 0)
            fee = inv_item.get("borrow_fee_pct", 3.5)
            im = inv_item.get("initial_margin_pct", 50.0)
            if avail > 0:
                return {
                    "symbol": sym,
                    "is_blocked": False,
                    "verdict": "BORROW_ALLOWED",
                    "badge": f"🟢 พร้อมยืม Short ({avail:,} หุ้น)",
                    "reason": f"มีคลังหุ้นพร้อมให้ยืม {avail:,} หุ้น ดอกเบี้ย {fee}% ปลอดภัยไม่มีเครื่องหมาย XD/XR",
                    "available_qty": avail,
                    "borrow_fee_pct": fee,
                    "initial_margin_pct": im
                }
            else:
                return {
                    "symbol": sym,
                    "is_blocked": True,
                    "verdict": "OUT_OF_STOCK",
                    "badge": "🔴 คลังหมด (Available = 0)",
                    "reason": f"ไม่มีสต็อกหุ้น {sym} ให้ยืมในคลัง Krungsri SBL ณ ขณะนี้",
                    "available_qty": 0,
                    "borrow_fee_pct": fee,
                    "initial_margin_pct": im
                }

        return {
            "symbol": sym,
            "is_blocked": False,
            "verdict": "UNVERIFIED_INVENTORY",
            "badge": "⚪ ไม่อยู่ในรายชื่อหลัก",
            "reason": f"หุ้น {sym} ไม่ได้อยู่ในหมวด SET50/SET100/NEWSEC แนะนำตรวจสอบผ่านหน้าต่างยืมหุ้นเดี่ยว",
            "available_qty": 0,
            "borrow_fee_pct": 3.5
        }


krungsri_sbl_driver = KrungsriSBLRealtimeDriver()
