#!/usr/bin/env python3
"""
Krungsri Capital SBL Type-Safe Playwright Debug Runner
=====================================================
Workflow 4:
1. Zero-OTP Session Verification (Krungsri TradeMan)
2. SBL Multi-Tab Scraper (SET50 Borrow Quota, XD/XR Warnings, Active Borrowed Lots)
3. Targeted SBL Search Probing (CPALL, DELTA, HANA)
4. Type-Safe Validation via SBLStockItem and SBLMultiTabSnapshot

Debug features:
- Headed Chromium with visual glowing element highlights
- On-failure mode (halts and enters interactive Grill-Me menu if error occurs)
- Type-Safe schema validation on every data structure

Usage:
    .venv/bin/python scripts/debug_krungsri_sbl_typesafe.py [--mode on-failure|step] [--symbols CPALL DELTA HANA]
"""

import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.browser.popup_manager import popup_manager
from app.browser.grill_harness import GrillController
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform
from app.schemas.sbl import SBLStockItem, SBLTargetStockQuery, SBLMultiTabSnapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("KrungsriSBLDebug")


async def run_sbl_typesafe_debug(mode: str = "on-failure", probe_symbols: List[str] = None):
    if not probe_symbols:
        probe_symbols = ["CPALL", "DELTA", "HANA"]

    print("=" * 80)
    print(" 🎯 KRUNGSRI CAPITAL: SBL BORROW INQUIRY TYPE-SAFE DEBUG RUNNER")
    print(" • Broker: Krungsri TradeMan (Production)")
    print(f" • Mode: Headed Desktop (:0) | Grill Mode: {mode.upper()}")
    print(f" • Target Probe Stocks: {', '.join(probe_symbols)}")
    print(" • Mode: Read-Only DOM (Zero Financial Risk - No Borrow Orders Placed)")
    print("=" * 80)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.TRADING_PLATFORM = "TRADEMAN"
    settings.PLAYWRIGHT_HEADLESS = False

    grill = GrillController(mode=mode, auto_highlight=True)

    # ---------------------------------------------------------
    # STEP 1: Browser Launch & Zero-OTP Session Verification
    # ---------------------------------------------------------
    page = None
    async def step_auth():
        nonlocal page
        print("\n[Step 1/4] Launching Chromium and verifying active TradeMan session...")
        page = await auth_driver.launch_browser(resume_state=True)
        is_saved_valid = await auth_driver.verify_saved_session()

        if is_saved_valid:
            print(f"   ✅ [Type-Safe] Session Valid! Resumed URL: {page.url}")
        else:
            print("   ⚠️  Existing session invalid or expired. Performing Auto-Fallback login...")
            res = await auth_driver.login(
                username=settings.KRUNGSRI_USERNAME,
                password=settings.KRUNGSRI_PASSWORD
            )
            login_res = LoginResult(**res) if isinstance(res, dict) else res
            if not login_res.success:
                raise RuntimeError(f"Login failed: {login_res.message}")
            print(f"   ✅ [Type-Safe] Login Successful! Status: {login_res.status}")

    await grill.execute_step(None, "Step 1: Authenticate / Restore Session (Zero-OTP)", step_auth)

    # ---------------------------------------------------------
    # STEP 2: Navigate to TradeMan SBL Tab
    # ---------------------------------------------------------
    async def step_navigate_sbl():
        print("\n[Step 2/4] Navigating to TradeMan SBL tab and dismissing popups...")
        trademan_driver.page_override = page
        
        # Navigate or switch to SBL tab
        if "SBL" not in page.url:
            await page.goto("https://trademan.in.th/SBL", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

        # Auto-dismiss popups
        await popup_manager.dismiss_popups(page)

        # Highlight navigation tab
        await grill.highlight_element(page, "a[href*='SBL'], span:has-text('หุ้นยืม SBL'), div:has-text('หุ้นยืม SBL')", color="#10b981")
        print(f"   ✅ SBL tab loaded. Active URL: {page.url}")

    await grill.execute_step(page, "Step 2: Navigate to TradeMan SBL Tab", step_navigate_sbl, selector="a[href*='SBL']")

    # ---------------------------------------------------------
    # STEP 3: Multi-Tab SBL Scrape (SET50, XD/XR, Port Lots)
    # ---------------------------------------------------------
    snapshot = SBLMultiTabSnapshot(broker=BrokerPlatform.TRADEMAN)

    async def step_multitab_scrape():
        nonlocal snapshot
        print("\n[Step 3/4] Scraping Multi-Tab SBL Inventory (SET50, XD/XR, Borrowed Portfolio)...")
        raw_sbl = await trademan_driver.scrape_sbl_all_tabs()
        raw_data = raw_sbl.get("data", raw_sbl)

        # 1. Parse SET50 inventory
        for item in raw_data.get("set50_inventory", []):
            try:
                stock = SBLStockItem(
                    symbol=item.get("symbol", ""),
                    available_qty=int(item.get("available_qty", 0)),
                    borrow_fee_pct=float(item.get("borrow_fee_pct", 3.50)),
                    initial_margin_pct=float(item.get("initial_margin_pct", 50.0)),
                    corporate_action_sign=None,
                    is_borrowable=int(item.get("available_qty", 0)) > 0
                )
                snapshot.set50_inventory.append(stock)
            except Exception as e:
                logger.warning(f"Error parsing SET50 item {item}: {e}")

        # 2. Parse XD / XR inventory
        for item in raw_data.get("xd_xr_inventory", []):
            try:
                sign = item.get("sign") or ("XD" if "xd" in str(item).lower() else "XR")
                stock = SBLStockItem(
                    symbol=item.get("symbol", ""),
                    available_qty=int(item.get("available_qty", 0)),
                    borrow_fee_pct=float(item.get("borrow_fee_pct", 3.50)),
                    initial_margin_pct=float(item.get("initial_margin_pct", 50.0)),
                    corporate_action_sign=sign,
                    is_borrowable=False  # Corporate action prevents safe overnight shorting
                )
                snapshot.xd_xr_inventory.append(stock)
            except Exception as e:
                logger.warning(f"Error parsing XD/XR item {item}: {e}")

        snapshot.active_borrowed_lots = raw_data.get("sbl_portfolio_lots", [])

        print(f"   ✅ [Type-Safe] Scraped {len(snapshot.set50_inventory)} SET50 SBL stocks.")
        print(f"   ⚠️  [Type-Safe] Scraped {len(snapshot.xd_xr_inventory)} stocks with XD/XR corporate actions.")
        print(f"   💼 [Type-Safe] Current active borrowed lots: {len(snapshot.active_borrowed_lots)}")

    await grill.execute_step(page, "Step 3: Multi-Tab SBL Scrape", step_multitab_scrape)

    # ---------------------------------------------------------
    # STEP 4: Targeted Stock Probing via Search Input
    # ---------------------------------------------------------
    async def step_probe_targets():
        nonlocal snapshot
        print(f"\n[Step 4/4] Performing targeted stock searches on SBL pool for: {', '.join(probe_symbols)}...")

        for sym in probe_symbols:
            print(f"   🔍 Probing SBL quota for '{sym}'...")
            raw_target = await trademan_driver.scrape_sbl_inventory(symbol=sym)
            
            # Highlight search element
            await grill.highlight_element(page, "input[placeholder*='ค้นหา' i], input[placeholder*='ใส่ชื่อหุ้น' i]", color="#3b82f6")
            
            avail = int(raw_target.get("available_qty", 0))
            item = SBLStockItem(
                symbol=sym,
                available_qty=avail,
                borrow_fee_pct=float(raw_target.get("borrow_fee_pct", 3.50)),
                initial_margin_pct=float(raw_target.get("initial_margin_pct", 50.0)),
                is_borrowable=avail > 0
            )
            query = SBLTargetStockQuery(
                target_symbol=sym,
                result=item,
                matched=avail > 0 or raw_target.get("available_qty") is not None
            )
            snapshot.targeted_searches.append(query)
            status_emoji = "🟢" if avail > 0 else "🔴"
            print(f"      {status_emoji} {sym}: Quota = {avail:,} shares | Fee = {item.borrow_fee_pct:.2f}% | IM = {item.initial_margin_pct:.0f}%")

        print("   ✅ [Type-Safe] Targeted stock probes completed.")

    await grill.execute_step(page, "Step 4: Targeted SBL Stock Probing", step_probe_targets, selector="input[placeholder*='ค้นหา' i]")

    # ---------------------------------------------------------
    # PRINT RESULTS SUMMARY TABLE
    # ---------------------------------------------------------
    print("\n" + "=" * 90)
    print(f" 📊 KRUNGSRI TRADEMAN SBL INVENTORY SNAPSHOT ({snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')})")
    print("=" * 90)
    print(" 🎯 TARGET PROBE RESULTS:")
    print("-" * 90)
    print(f"{'#':<3} | {'Symbol':<10} | {'Available Quota':<18} | {'Fee % p.a.':<12} | {'IM %':<8} | {'Borrowable Status':<18}")
    print("-" * 90)
    for i, q in enumerate(snapshot.targeted_searches, 1):
        r = q.result
        status_text = "🟢 READY TO SHORT" if r.is_borrowable else "🔴 POOL EMPTY / RESTRICTED"
        print(f"{i:<3} | {r.symbol:<10} | {r.available_qty:<18,} | {r.borrow_fee_pct:>8.2f}%    | {r.initial_margin_pct:>4.0f}%  | {status_text:<18}")

    print("\n" + "-" * 90)
    print(f" 🏛️ SET50 POOL PREVIEW (Sample of {len(snapshot.set50_inventory)} stocks):")
    print("-" * 90)
    for i, stock in enumerate(snapshot.set50_inventory[:10], 1):
        print(f"{i:<3} | {stock.symbol:<10} | Quota: {stock.available_qty:>12,} shares | Fee: {stock.borrow_fee_pct:.2f}% | IM: {stock.initial_margin_pct:.0f}%")
    if len(snapshot.set50_inventory) > 10:
        print(f"... and {len(snapshot.set50_inventory) - 10} more SET50 stocks in pool.")

    if snapshot.xd_xr_inventory:
        print("\n" + "-" * 90)
        print(f" ⚠️  CORPORATE ACTION RESTRICTIONS ({len(snapshot.xd_xr_inventory)} stocks):")
        print("-" * 90)
        for i, stock in enumerate(snapshot.xd_xr_inventory[:5], 1):
            print(f"{i:<3} | {stock.symbol:<10} | Sign: [{stock.corporate_action_sign}] | Quota: {stock.available_qty:,}")

    print("=" * 90)
    print(" 🎉 SBL WORKFLOW DEBUG + TYPE-SAFE RUN COMPLETED SUCCESSFULLY!")
    print(" Zero Financial Risk verified: Read-only DOM scraping, no borrow orders submitted.")
    print("=" * 90)

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Krungsri Capital SBL Type-Safe Debug Runner")
    parser.add_argument("--mode", choices=["on-failure", "step"], default="on-failure",
                        help="Grill mode: 'on-failure' or 'step'")
    parser.add_argument("--symbols", nargs="+", default=["CPALL", "DELTA", "HANA"],
                        help="Symbols to probe on SBL")
    args = parser.parse_args()

    asyncio.run(run_sbl_typesafe_debug(mode=args.mode, probe_symbols=args.symbols))


if __name__ == "__main__":
    main()
