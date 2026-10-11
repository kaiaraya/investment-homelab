#!/usr/bin/env python3
"""
Live Test Harness: Liberator WebTrade Login & 2FA SMS Interception
===================================================================
1. Launches visible Headed Chrome on DISPLAY=:0.
2. Navigates to https://webtrade.liberator.co.th/login.
3. Automatically enters credentials from .env.
4. Auto-intercepts 2FA SMS OTP from KDE Connect (Android Mi 10T).
5. Navigates to Portfolio dashboard and persists cookies to data/liberator_session.json.
6. Scrapes Cash Balance and Line Available.
"""

import sys
import os
import asyncio
import logging

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.brokers.liberator.driver import liberator_driver
from app.core.config import settings

# ANSI formatting
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def main():
    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_MAGENTA}🚀 [LIVE TEST] Liberator WebTrade Login & 2FA SMS Gateway{C_RESET}")
    print("=" * 75)
    print(f" • Username:      {C_BOLD}{settings.LIBERATOR_USERNAME or '7055938'}{C_RESET}")
    print(f" • Login URL:     https://webtrade.liberator.co.th/login")
    print(f" • Mode:          {C_GREEN}Headed Chrome on DISPLAY=:0{C_RESET}")
    print(f" • Hardware 2FA:  {C_CYAN}KDE Connect Auto-Interception (Xiaomi Mi 10T){C_RESET}")
    print("=" * 75 + "\n")

    try:
        # Force fresh login to test the entire login + 2FA OTP flow
        print(f"🔑 Initiating automated login...")
        result = await liberator_driver.login(force_fresh=True)

        print("\n" + "=" * 75)
        if result.success:
            print(f"{C_BOLD}{C_GREEN}🎉 LIBERATOR LOGIN SUCCESSFUL!{C_RESET}")
            print(f" • Status:        {result.status}")
            print(f" • Landing URL:   {liberator_driver.current_url}")
            print(f" • Saved Session: {liberator_driver.session_path}")

            # Scrape basic balances
            print(f"\n📊 Scraping account balances...")
            balances = await liberator_driver.scrape_portfolio()
            print(f" • Line Available: ฿{balances.get('line_available', 0.0):,.2f}")
            print(f" • Cash Balance:   ฿{balances.get('cash_balance', 0.0):,.2f}")
            print(f" • Total Equity:   ฿{balances.get('total_equity', 0.0):,.2f}")

            # Take diagnostic screenshot
            os.makedirs("data/screenshots", exist_ok=True)
            shot_file = "data/screenshots/liberator_login_success.png"
            if liberator_driver.page and not liberator_driver.page.is_closed():
                await liberator_driver.page.screenshot(path=shot_file)
                print(f"\n📸 Verification screenshot saved to: {shot_file}")
        else:
            print(f"{C_BOLD}{C_RED}❌ LIBERATOR LOGIN FAILED!{C_RESET}")
            print(f" • Error: {result.error_message}")
        print("=" * 75 + "\n")

    except Exception as e:
        print(f"\n{C_RED}❌ Unhandled Exception during login: {e}{C_RESET}")
    finally:
        # Keep open for 15 seconds for user to inspect, then close cleanly
        await asyncio.sleep(15)
        await liberator_driver.close()


if __name__ == "__main__":
    asyncio.run(main())
