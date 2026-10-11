#!/usr/bin/env python3
"""
Live Read-Only Scraping Verification Script (Zero Risk).
Demonstrates and tests Live DOM Scraping directly on TradeMan:
1. 3.1.1 Scrape Portfolio Holdings (Symbol, Volume, Avg Cost, Market Price, Unrealized PnL)
2. 3.5.5 Scrape Account Summary (Excess Equity, Cash Balance)
3. 3.3.6 Scrape SBL Inventory for a sample stock (e.g. CPALL)
4. 3.4.1 Scrape Unmatched Orders from Order Status tab

NO BUY/SELL/SHORT/BORROW ORDERS ARE PLACED. ZERO FINANCIAL RISK.
"""

import os
import sys
import asyncio
import logging

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LiveScraperTest")


async def main():
    print("=" * 75)
    print(" 🔍 LIVE READ-ONLY SCRAPING TEST (ZERO FINANCIAL RISK)")
    print(" Target: Krungsri TradeMan (DOM Scraping Only)")
    print("=" * 75)

    # 1. Launch / Restore Browser Session
    print("\n[Step 1] Connecting to Browser Session...")
    try:
        page = await auth_driver.launch_browser(resume_state=True)
        is_restored = await auth_driver.verify_saved_session()
        
        if not is_restored:
            print("⚠️  No active TradeMan session found in data/session_state.json!")
            print("Please run `python scripts/run_phase2_login.py` first to log in and save cookies.")
            print("Alternatively, you can log in now if credentials are in .env.")
            
            username = os.getenv("KRUNGSRI_USERNAME", settings.KRUNGSRI_USERNAME).strip()
            password = os.getenv("KRUNGSRI_PASSWORD", settings.KRUNGSRI_PASSWORD).strip()
            if username and password:
                print("Attempting login...")
                res = await auth_driver.login(username, password)
                if res.get("status") != "AUTHENTICATED":
                    print(f"❌ Login failed: {res.get('message')}")
                    await auth_driver.close()
                    return
            else:
                await auth_driver.close()
                return

        print("✅ TradeMan Session is AUTHENTICATED and READY!")
        print(f"   Current URL: {auth_driver.current_url}")

        # 2. Test 3.1.1: Scrape Portfolio Holdings
        print("\n" + "-" * 75)
        print("📊 [Test 3.1.1] Scraping Real Portfolio Holdings (Read-Only DOM)...")
        print("-" * 75)
        holdings = await trademan_driver.scrape_portfolio()
        if holdings:
            print(f"🎉 Successfully scraped {len(holdings)} holdings from TradeMan:\n")
            print(f"{'Symbol':<10} {'Type':<8} {'Volume':>10} {'Avg Cost':>12} {'Price':>10} {'Unrealized PnL':>16} {'% PnL':>10}")
            print("-" * 80)
            for h in holdings:
                print(
                    f"{h.get('symbol', ''):<10} "
                    f"{h.get('position_type', ''):<8} "
                    f"{h.get('volume', 0):>10,d} "
                    f"฿{h.get('avg_cost', 0.0):>10.2f} "
                    f"฿{h.get('current_price', 0.0):>8.2f} "
                    f"฿{h.get('unrealized_pnl', 0.0):>14.2f} "
                    f"{h.get('pnl_pct', 0.0):>+9.2f}%"
                )
        else:
            print("ℹ️  Portfolio is currently empty or no stock rows detected in the table.")

        # 3. Test 3.5.5: Scrape Account Summary (EE & Cash)
        print("\n" + "-" * 75)
        print("💰 [Test 3.5.5] Scraping Account Balances (EE & Cash)...")
        print("-" * 75)
        acc_summary = await trademan_driver.scrape_account_summary()
        print(f"   Excess Equity (EE): ฿{acc_summary.get('excess_equity', 0):,.2f}")
        print(f"   Cash Balance:       ฿{acc_summary.get('cash_balance', 0):,.2f}")
        print(f"   Realized PnL:       ฿{acc_summary.get('realized_pnl', 0):,.2f}")

        # 4. Test 3.3.6: Scrape SBL Inventory for CPALL
        print("\n" + "-" * 75)
        print("📦 [Test 3.3.6] Scraping SBL Inventory for CPALL (Stock Query Only)...")
        print("-" * 75)
        sbl_info = await trademan_driver.scrape_sbl_inventory("CPALL")
        print(f"   Symbol:             {sbl_info.get('symbol')}")
        print(f"   Available to Borrow: {sbl_info.get('available_qty', 0):,} shares")
        print(f"   Status:             {sbl_info.get('status')}")

        # 5. Test 3.4.1: Scrape Unmatched Orders
        print("\n" + "-" * 75)
        print("📋 [Test 3.4.1] Scraping Unmatched Orders in Order Status...")
        print("-" * 75)
        unmatched = await trademan_driver.scrape_unmatched_orders()
        if unmatched:
            print(f"   Found {len(unmatched)} active/unmatched orders:")
            for o in unmatched:
                print(f"   • Order #{o.get('order_id')}: {o.get('side')} {o.get('symbol')} {o.get('volume')} @ {o.get('price')} [{o.get('status')}]")
        else:
            print("   No unmatched orders pending on the board.")

        print("\n" + "=" * 75)
        print(" ✅ ZERO-RISK LIVE SCRAPING VERIFICATION COMPLETE!")
        print("    All requested DOM scrapers evaluated directly on TradeMan.")
        print("=" * 75)

    except Exception as e:
        logger.error(f"Error during live scraping test: {e}", exc_info=True)
    finally:
        print("\nKeeping browser open for 15 seconds for visual inspection...")
        await asyncio.sleep(15)
        await auth_driver.close()
        print("Browser session closed cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
