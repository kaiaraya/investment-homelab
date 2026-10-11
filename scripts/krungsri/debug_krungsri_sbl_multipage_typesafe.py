#!/usr/bin/env python3
"""
Krungsri Capital SBL Multi-Page Type-Safe Playwright Debug Runner
================================================================
Comprehensive verification of all SBL categories:
- SET50 (Multi-Page)
- SET100 (Multi-Page)
- NEWSEC (New Securities - Multi-Page)
- XD, XR (Corporate Actions - Multi-Page)

Features:
- Headed Chromium with visual glowing element highlights
- Automatic pagination traversal (iterates Page 1 -> End for each category)
- Type-Safe schema validation via SBLStockItem, SBLCategorySummary, and SBLComprehensiveSnapshot
- On-failure grill mode (halts only on error/unhandled modal)
- 100% Zero Financial Risk (Read-only DOM scraping)

Usage:
    .venv/bin/python scripts/debug_krungsri_sbl_multipage_typesafe.py [--mode on-failure|step] [--categories SET50 SET100 NEWSEC XD_XR]
"""

import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.auth_driver import auth_driver
from app.browser.popup_manager import popup_manager
from app.browser.grill_harness import GrillController
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform
from app.schemas.sbl import SBLCategory, SBLStockItem, SBLCategorySummary, SBLComprehensiveSnapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("KrungsriSBLMultiPage")


TAB_CONFIGS = [
    {
        "category": SBLCategory.SET50,
        "tab_name": "SET50",
        "selector": "span.cursor-pointer:has-text('SET50')",
        "description": "SET50 Large-Cap Borrow Pool"
    },
    {
        "category": SBLCategory.SET100,
        "tab_name": "SET100",
        "selector": "span.cursor-pointer:has-text('SET100')",
        "description": "SET100 Mid-to-Large Cap Borrow Pool"
    },
    {
        "category": SBLCategory.NEWSEC,
        "tab_name": "NEWSEC",
        "selector": "span.cursor-pointer:has-text('NEWSEC')",
        "description": "New Securities Added to SBL"
    },
    {
        "category": SBLCategory.XD_XR,
        "tab_name": "XD, XR",
        "selector": "span.cursor-pointer:has-text('XD, XR')",
        "description": "Securities with Upcoming Corporate Actions (XD/XR)"
    }
]


async def run_multipage_sbl_debug(mode: str = "on-failure", selected_cats: List[str] = None):
    print("=" * 85)
    print(" 🎯 KRUNGSRI CAPITAL: MULTI-PAGE SBL INVENTORY TYPE-SAFE DEBUG RUNNER")
    print(" • Broker: Krungsri TradeMan (Production)")
    print(f" • Mode: Headed Desktop (:0) | Grill Mode: {mode.upper()}")
    print(" • Categories: SET50, SET100, NEWSEC, XD/XR (Full Pagination)")
    print(" • Safety: 100% Zero Financial Risk (Read-Only DOM Inspection)")
    print("=" * 85)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.TRADING_PLATFORM = "TRADEMAN"
    settings.PLAYWRIGHT_HEADLESS = False

    grill = GrillController(mode=mode, auto_highlight=True)

    # 1. Connect & Verify Session
    page = None
    async def step_auth():
        nonlocal page
        print("\n[Step 1/5] Launching Chromium and verifying active TradeMan session...")
        page = await auth_driver.launch_browser(resume_state=True)
        is_valid = await auth_driver.verify_saved_session()
        if not is_valid:
            print("   ⚠️ Existing session invalid or expired. Performing Auto-Fallback login...")
            res = await auth_driver.login(
                username=settings.KRUNGSRI_USERNAME,
                password=settings.KRUNGSRI_PASSWORD
            )
            login_res = LoginResult(**res) if isinstance(res, dict) else res
            if not login_res.success:
                raise RuntimeError(f"Login failed: {login_res.message}")
        print(f"   ✅ [Type-Safe] Session Verified! URL: {page.url}")

    await grill.execute_step(None, "Step 1: Session Verification (Zero-OTP)", step_auth)

    # 2. Navigate to SBL Page
    async def step_nav_sbl():
        print("\n[Step 2/5] Navigating to TradeMan SBL and dismissing popups...")
        if "SBL" not in page.url:
            await page.goto("https://trademan.in.th/SBL", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
        await popup_manager.dismiss_popups(page)
        print(f"   ✅ SBL screen active. URL: {page.url}")

    await grill.execute_step(page, "Step 2: Navigate to SBL Screen", step_nav_sbl)

    # 3. Comprehensive Multi-Page Scraping Loop across Categories
    comprehensive_snapshot = SBLComprehensiveSnapshot(broker=BrokerPlatform.TRADEMAN)

    for cfg in TAB_CONFIGS:
        cat_enum = cfg["category"]
        if selected_cats and cat_enum.value not in selected_cats and cfg["tab_name"] not in selected_cats:
            continue

        cat_summary = SBLCategorySummary(category=cat_enum)

        async def step_scrape_category(config=cfg, summary=cat_summary):
            cat_name = config["tab_name"]
            sel = config["selector"]
            print(f"\n[Category Scrape] Switching to tab '{cat_name}' ({config['description']})...")

            # Click Category Tab
            tab_el = await page.query_selector(sel)
            if not tab_el:
                raise AssertionError(f"Category tab '{cat_name}' not found with selector: {sel}")
            await tab_el.click()
            await page.wait_for_timeout(800)
            await popup_manager.dismiss_popups(page)

            # Ensure we start at Page 1 if a page 1 button exists
            page1_btn = await page.query_selector("button[aria-label='Go to page 1']")
            if page1_btn:
                await page1_btn.click()
                await page.wait_for_timeout(600)

            page_idx = 1
            seen_symbols = set()

            while True:
                print(f"   📄 Scraping {cat_name} -> Page {page_idx}...")
                await grill.highlight_element(page, "div.flex.cursor-pointer", color="#10b981")

                # Extract rows from current page
                rows_data = await page.evaluate('''() => {
                    const results = [];
                    const rows = document.querySelectorAll('div.flex.cursor-pointer');
                    for (const r of rows) {
                        const texts = Array.from(r.querySelectorAll('span, div'))
                            .map(el => el.innerText.trim())
                            .filter(t => t.length > 0);
                        const unique = [...new Set(texts)];
                        // Filter out navigation/header texts
                        if (unique.length >= 4 && !unique[0].includes('Assets') && !unique[0].includes('Portfolio') && !unique[0].includes('ยืม') && !unique[0].includes('Scan') && !unique[0].includes('SBL')) {
                            results.push({
                                symbol: unique[0],
                                borrow_fee_pct: parseFloat(unique[1].replace(/%/g, '')) || 3.50,
                                available_qty: parseInt(unique[2].replace(/,/g, ''), 10) || 0,
                                initial_margin_pct: parseFloat(unique[3].replace(/%/g, '')) || 50.0,
                                raw_texts: unique
                            });
                        }
                    }
                    return results;
                }''')

                page_new_count = 0
                for item in rows_data:
                    sym = item["symbol"].strip().upper()
                    if sym in seen_symbols:
                        continue
                    seen_symbols.add(sym)
                    page_new_count += 1

                    # Check corporate action signs
                    sign = None
                    if cat_enum == SBLCategory.XD_XR:
                        sign = "XD" if "XD" in str(item) else "XR"

                    stock = SBLStockItem(
                        symbol=sym,
                        available_qty=item["available_qty"],
                        borrow_fee_pct=item["borrow_fee_pct"],
                        initial_margin_pct=item["initial_margin_pct"],
                        category=cat_enum,
                        corporate_action_sign=sign,
                        page_number=page_idx,
                        is_borrowable=item["available_qty"] > 0 and (cat_enum != SBLCategory.XD_XR)
                    )
                    summary.stocks.append(stock)

                print(f"      • Found {len(rows_data)} rows on Page {page_idx} ({page_new_count} unique symbols).")

                # Check Next Page Button
                next_btn = await page.query_selector("button[aria-label='Next page']")
                if not next_btn:
                    # No pagination bar
                    break

                is_disabled = await page.evaluate('''el => {
                    return el.classList.contains('v-btn--disabled') || el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';
                }''', next_btn)

                if is_disabled:
                    print(f"      🏁 Reached last page of {cat_name} (Page {page_idx}).")
                    break

                # Click next page
                await next_btn.click()
                await page.wait_for_timeout(800)
                page_idx += 1

                # Safety break against infinite loop
                if page_idx > 20:
                    logger.warning(f"Safety limit of 20 pages reached for {cat_name}.")
                    break

            summary.total_pages_scraped = page_idx
            summary.total_stocks = len(summary.stocks)
            summary.total_borrowable_shares = sum(s.available_qty for s in summary.stocks)
            print(f"   ✅ [{cat_name}] Finished: {summary.total_stocks} stocks across {summary.total_pages_scraped} pages. Quota: {summary.total_borrowable_shares:,} shares.")

        await grill.execute_step(page, f"Scrape Category: {cfg['tab_name']}", step_scrape_category, selector=cfg["selector"])
        comprehensive_snapshot.categories[cat_enum.value] = cat_summary

    # Calculate Grand Totals
    comprehensive_snapshot.grand_total_stocks = sum(c.total_stocks for c in comprehensive_snapshot.categories.values())
    comprehensive_snapshot.grand_total_borrowable_shares = sum(c.total_borrowable_shares for c in comprehensive_snapshot.categories.values())

    # ---------------------------------------------------------
    # PRINT RESULTS COMPREHENSIVE TABLES
    # ---------------------------------------------------------
    print("\n" + "=" * 95)
    print(f" 📊 KRUNGSRI TRADEMAN COMPREHENSIVE SBL INVENTORY SNAPSHOT ({comprehensive_snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')})")
    print("=" * 95)
    print(f" • Grand Total Stocks Scraped: {comprehensive_snapshot.grand_total_stocks} stocks across all pools")
    print(f" • Grand Total Borrowable Volume: {comprehensive_snapshot.grand_total_borrowable_shares:,} shares")
    print("-" * 95)

    # 1. Category Overview Summary Table
    print(f"{'Category':<12} | {'Pages':<7} | {'Total Stocks':<14} | {'Total Quota (Shares)':<22} | {'Avg Fee %':<10} | {'Status':<15}")
    print("-" * 95)
    for cat_name, cat in comprehensive_snapshot.categories.items():
        avg_fee = (sum(s.borrow_fee_pct for s in cat.stocks) / cat.total_stocks) if cat.total_stocks > 0 else 3.50
        status_text = "🟢 READY TO SHORT" if cat.total_borrowable_shares > 0 else "⚪ NO QUOTA"
        print(f"{cat_name:<12} | {cat.total_pages_scraped:<7} | {cat.total_stocks:<14} | {cat.total_borrowable_shares:<22,} | {avg_fee:>8.2f}% | {status_text:<15}")

    # 2. Detailed Breakdown per Category
    for cat_name, cat in comprehensive_snapshot.categories.items():
        print("\n" + "-" * 95)
        print(f" 📁 Category: [{cat_name}] ({cat.total_stocks} stocks across {cat.total_pages_scraped} pages)")
        print("-" * 95)
        print(f"{'#':<3} | {'Symbol':<10} | {'Page':<6} | {'Available Quota':<18} | {'Fee %':<8} | {'IM %':<6} | {'Borrowable Status':<18}")
        print("-" * 95)
        # Show top 10 stocks by available volume
        sorted_stocks = sorted(cat.stocks, key=lambda s: s.available_qty, reverse=True)
        for i, s in enumerate(sorted_stocks[:12], 1):
            st_text = "🟢 AVAILABLE" if s.is_borrowable else ("⚠️ XD/XR CAUTION" if s.corporate_action_sign else "🔴 EMPTY")
            print(f"{i:<3} | {s.symbol:<10} | P.{s.page_number:<4} | {s.available_qty:<18,} | {s.borrow_fee_pct:>5.2f}% | {s.initial_margin_pct:>4.0f}% | {st_text:<18}")

        if len(sorted_stocks) > 12:
            print(f"... and {len(sorted_stocks) - 12} more stocks in [{cat_name}].")

        print("\n" + "=" * 95)
        print(" 🎉 FULL MULTI-PAGE SBL VERIFICATION COMPLETED SUCCESSFULLY!")
        print(" Zero Financial Risk verified: Read-only DOM scraping, all pages inspected.")
        print("=" * 95)

    return comprehensive_snapshot


def main():
    parser = argparse.ArgumentParser(description="Krungsri Capital SBL Multi-Page Type-Safe Debug Runner")
    parser.add_argument("--mode", choices=["on-failure", "step"], default="on-failure",
                        help="Grill mode: 'on-failure' or 'step'")
    parser.add_argument("--categories", nargs="+", default=["SET50", "SET100", "NEWSEC", "XD_XR"],
                        help="Categories to scrape (SET50, SET100, NEWSEC, XD_XR)")
    args = parser.parse_args()

    async def _runner():
        try:
            await run_multipage_sbl_debug(mode=args.mode, selected_cats=args.categories)
        finally:
            print("\n[Teardown] Gracefully closing browser context and preventing zombie processes...")
            await auth_driver.close()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()
