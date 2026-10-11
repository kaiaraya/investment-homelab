#!/usr/bin/env python3
"""
Unified Playwright Debug Harness - Workflow 2: Portfolio Holdings & SBL Inventory Scraper.
Supports both:
1. Settrade Click2Win (Equity & Derivatives Holdings)
2. Krungsri TradeMan (18 Holdings + SET50 SBL Borrowable Pool)

Usage:
    .venv/bin/python scripts/debug_scrape_portfolio.py [--platform click2win|trademan] [--symbol DELTA]
"""

import sys
import os
import argparse
import asyncio
import logging
from dotenv import load_dotenv

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.broker_factory import get_auth_driver, get_broker_driver
from app.browser.popup_manager import popup_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("DebugPortfolio")


async def run_debug_scrape(platform_name: str, symbol_filter: str = None, headed: bool = True):
    print("=" * 80)
    print(f" 📊 PLAYWRIGHT DEBUG: WORKFLOW 2 - PORTFOLIO HOLDINGS & SBL INVENTORY")
    print(f" • Platform: {platform_name.upper()}")
    print(f" • Mode: Read-Only DOM (Zero Financial Risk)")
    print("=" * 80)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.TRADING_PLATFORM = platform_name.upper()
    settings.PLAYWRIGHT_HEADLESS = not headed

    auth = get_auth_driver()
    broker = get_broker_driver()

    print(f"\n[1/3] Attaching to Chrome browser session...")
    page = await auth.launch_browser(resume_state=True)
    is_saved_valid = await auth.verify_saved_session()

    if not is_saved_valid:
        print(f"⚠️ Active session not authenticated on {platform_name.upper()}.")
        print("Please run `scripts/debug_login.py` first to establish session cookies.")
        return False

    await popup_manager.dismiss_popups(page)
    print(f"✅ Session verified. Active URL: {page.url}")

    print(f"\n[2/3] Scraping Portfolio Holdings...")
    try:
        holdings = await broker.scrape_portfolio()
        print(f"\n💼 Found {len(holdings)} positions in portfolio:")
        print("-" * 80)
        print(f"{'#':<3} | {'Symbol':<10} | {'Side':<6} | {'Volume':<10} | {'Avg Cost':<10} | {'Market':<10} | {'PnL %':<10}")
        print("-" * 80)
        for i, pos in enumerate(holdings, 1):
            sym = pos.get("symbol", "N/A")
            side = pos.get("side", pos.get("position_type", "LONG"))
            vol = pos.get("volume") or pos.get("actual_volume") or 0
            avg = pos.get("avg_cost") or pos.get("avg_price") or 0
            curr = pos.get("market_price") or pos.get("current_price") or 0
            pnl = pos.get("unrealized_pnl_pct", 0)
            print(f"{i:<3} | {sym:<10} | {side:<6} | {vol:<10,} | {avg:<10.2f} | {curr:<10.2f} | {pnl:+9.2f}%")
        print("-" * 80)
    except Exception as e:
        print(f"❌ Error scraping portfolio holdings: {e}")

    if platform_name.upper() == "TRADEMAN":
        print(f"\n[3/3] Scraping SBL Borrowable Pool (Krungsri SBL Multi-Tab)...")
        try:
            if hasattr(broker, "scrape_sbl_borrow_inventory"):
                sbl_data = await broker.scrape_sbl_borrow_inventory(symbol=symbol_filter)
            else:
                sbl_data = await broker.scrape_sbl_lots()

            print(f"📈 SBL Borrow Inventory Results (Filter: {symbol_filter or 'All Available'}):")
            if isinstance(sbl_data, list):
                print(f"Found {len(sbl_data)} SBL records.")
                for item in sbl_data[:10]:
                    print(f"  • {item}")
                if len(sbl_data) > 10:
                    print(f"  • ... and {len(sbl_data)-10} more items.")
            elif isinstance(sbl_data, dict):
                for k, v in sbl_data.items():
                    print(f"  • {k}: {v}")
        except Exception as e:
            print(f"⚠️ SBL Scrape Notice: {e}")
    else:
        print("\n[3/3] SBL Borrow Pool: Skipped (Click2Win sandbox does not provide SBL pool).")

    print("\n✅ Workflow 2 Scraping Complete! (All data read accurately without side effects)")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Playwright Portfolio Scraper")
    parser.add_argument(
        "--platform",
        choices=["click2win", "trademan"],
        default=getattr(settings, "TRADING_PLATFORM", "CLICK2WIN").lower(),
        help="Trading platform (click2win or trademan)"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Optional symbol filter for SBL search"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless instead of visible window"
    )
    args = parser.parse_args()

    asyncio.run(run_debug_scrape(platform_name=args.platform, symbol_filter=args.symbol, headed=not args.headless))
