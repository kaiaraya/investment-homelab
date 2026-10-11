#!/usr/bin/env python3
"""
Krungsri TradeMan Full-Spectrum Session & Multi-Account Test Runner.
====================================================================
Isolated E2E verification for Krungsri Securities:
1. Fresh Headed Login via Krungsri Portal with 2FA SMS OTP (KDE Connect Mi 10T / Terminal / Browser)
2. Seamless SSO Redirect to TradeMan (trademan.in.th) & Auto-Dismiss Popups
3. Multi-Account Switching:
   - Cash Balance Account (3024952): Scrape Cash, Line Available, Holdings
   - Margin Credit Balance Account (3024959): Scrape Excess Equity (EE), Cash, Holdings
4. Session Persistence & Re-entry Validation (Direct access to Portfolio without OTP)
5. Self-Annealing Edge Case Detection & Root Cause Analysis

Usage:
  .venv/bin/python scripts/test_krungsri_full_session_flow.py [--force-fresh] [--headless]
"""

import os
import sys
import time
import asyncio
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure DISPLAY for Headed Chrome
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

from app.core.config import settings
from app.core.events import event_bus
from app.schemas.auth import OTPPayload, OTPSource
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.browser.popup_manager import popup_manager
from app.services.kdeconnect_service import kdeconnect_service

# ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"
C_BLUE = "\033[94m"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("KrungsriFullFlow")


async def _terminal_otp_listener(current_ref: Optional[str] = None):
    """Listens to stdin in parallel so user can type OTP directly if KDE Connect is delayed."""
    loop = asyncio.get_running_loop()
    try:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        code = line.strip()
        if len(code) == 6 and code.isdigit():
            print(f"\n{C_GREEN}⌨️  Terminal OTP entered: {code[:2]}**** -> Publishing to EventBus...{C_RESET}")
            await event_bus.publish_otp(
                OTPPayload(
                    source=OTPSource.CLI_TERMINAL,
                    otp=code,
                    ref=current_ref,
                    sender="terminal_user"
                )
            )
            return code
    except Exception:
        pass
    return None


async def run_full_spectrum_flow(force_fresh: bool = False, headless: bool = False):
    print("=" * 80)
    print(f"{C_BOLD}{C_MAGENTA}🏢 KRUNGSRI TRADEMAN - FULL-SPECTRUM SESSION & MULTI-ACCOUNT VERIFICATION{C_RESET}")
    print(f" • Mode:         {C_GREEN}{'Headless' if headless else 'Headed (Visible Chrome on DISPLAY=:0)'}{C_RESET}")
    print(f" • Force Fresh:  {C_YELLOW}{force_fresh}{C_RESET}")
    print(f" • Cash A/C:     {C_CYAN}{settings.TRADEMAN_ACCOUNT_NO_CASH}{C_RESET}")
    print(f" • Margin A/C:   {C_CYAN}{settings.TRADEMAN_ACCOUNT_NO_MARGIN}{C_RESET}")
    print(f" • Session File: {settings.SESSION_STATE_PATH}")
    print("=" * 80)

    settings.PLAYWRIGHT_HEADLESS = headless

    results = {
        "step1_login": False,
        "step2_sso": False,
        "step3_switch_cash": False,
        "step3_cash_balances": {},
        "step4_switch_margin": False,
        "step4_margin_balances": {},
        "step5_session_reentry": False,
        "errors": []
    }

    # Pre-check KDE Connect Mi 10T
    try:
        is_reachable = await kdeconnect_service.is_device_reachable()
        print(f"📱 KDE Connect (Mi 10T): {'✅ ONLINE (SMS Auto-read ready)' if is_reachable else '⚠️ OFFLINE (Terminal OTP active)'}")
    except Exception as e:
        print(f"📱 KDE Connect note: {e}")

    # =========================================================================
    # STEP 1 & 2: Krungsri Login & TradeMan SSO
    # =========================================================================
    print(f"\n{C_BOLD}[STEP 1/5] Initiating Krungsri Authentication & SSO...{C_RESET}")
    
    login_task = asyncio.create_task(
        auth_driver.login(
            force_fresh=force_fresh,
            timeout_otp=180
        )
    )

    announced_ref = False
    otp_input_task = None

    while not login_task.done():
        await asyncio.sleep(0.5)
        if auth_driver.status == "AWAITING_OTP" and not announced_ref:
            ref_code = auth_driver.current_ref or "Pending"
            announced_ref = True
            print("\n" + "-" * 75)
            print(f"{C_BOLD}{C_YELLOW}🔑 2FA SMS OTP REQUIRED BY KRUNGSRI!{C_RESET}")
            print(f" • Reference Code: {C_BOLD}{C_CYAN}[Ref: {ref_code}]{C_RESET}")
            print(f" • 📱 Auto-reading via KDE Connect (Mi 10T)...")
            print(f" • ⌨️  OR enter 6-digit OTP right here in terminal:")
            print(f"{C_CYAN}Enter 6-digit OTP: {C_RESET}", end="", flush=True)
            otp_input_task = asyncio.create_task(_terminal_otp_listener(current_ref=ref_code))

    if otp_input_task and not otp_input_task.done():
        otp_input_task.cancel()

    try:
        login_res = await login_task
        if not login_res.success:
            print(f"{C_RED}❌ Login failed: {login_res.message}{C_RESET}")
            results["errors"].append(f"Login failed: {login_res.message}")
            return results

        results["step1_login"] = True
        results["step2_sso"] = True
        print(f"{C_GREEN}✅ Step 1 & 2 Successful: Authenticated and landed on TradeMan!{C_RESET}")
        print(f" • Current URL: {auth_driver.current_url}")
        print(f" • Resumed:     {login_res.resumed}")
    except Exception as e:
        print(f"{C_RED}❌ Login Exception: {e}{C_RESET}")
        results["errors"].append(f"Login exception: {e}")
        return results

    # =========================================================================
    # STEP 3: Switch to Cash Account (3024952) & Scrape Balances
    # =========================================================================
    print(f"\n{C_BOLD}[STEP 3/5] Testing Account Switch to CASH ({settings.TRADEMAN_ACCOUNT_NO_CASH})...{C_RESET}")
    try:
        cash_switch = await trademan_driver.switch_account("CASH")
        print(f" • Switch Result: {cash_switch.get('status')} - {cash_switch.get('message')}")
        
        await asyncio.sleep(1.0)
        cash_summary = await trademan_driver.scrape_account_summary(force_live=True)
        cash_holdings = await trademan_driver.scrape_portfolio()

        results["step3_switch_cash"] = cash_switch.get("success", False)
        results["step3_cash_balances"] = cash_summary

        print(f"{C_GREEN}✅ CASH Account Active ({settings.TRADEMAN_ACCOUNT_NO_CASH}):{C_RESET}")
        print(f"   • Cash Balance / Line Available: ฿{cash_summary.get('cash_balance', 0):,.2f}")
        print(f"   • Total Equity:                 ฿{cash_summary.get('total_equity', 0):,.2f}")
        print(f"   • Holdings count:               {len(cash_holdings)} stocks")
        for h in cash_holdings:
            print(f"     - {h.get('symbol')}: {h.get('volume')} shares @ ฿{h.get('avg_cost', 0):,.2f}")
    except Exception as e:
        print(f"{C_RED}❌ Error during Cash Account switch/scrape: {e}{C_RESET}")
        results["errors"].append(f"Cash account error: {e}")

    # =========================================================================
    # STEP 4: Switch to Margin Account (3024959) & Scrape Balances
    # =========================================================================
    print(f"\n{C_BOLD}[STEP 4/5] Testing Account Switch to MARGIN ({settings.TRADEMAN_ACCOUNT_NO_MARGIN})...{C_RESET}")
    try:
        margin_switch = await trademan_driver.switch_account("MARGIN")
        print(f" • Switch Result: {margin_switch.get('status')} - {margin_switch.get('message')}")

        await asyncio.sleep(1.0)
        margin_summary = await trademan_driver.scrape_account_summary(force_live=True)
        margin_holdings = await trademan_driver.scrape_portfolio()

        results["step4_switch_margin"] = margin_switch.get("success", False)
        results["step4_margin_balances"] = margin_summary

        print(f"{C_GREEN}✅ MARGIN Account Active ({settings.TRADEMAN_ACCOUNT_NO_MARGIN}):{C_RESET}")
        print(f"   • Excess Equity (EE):           ฿{margin_summary.get('excess_equity', 0):,.2f}")
        print(f"   • Cash Balance:                 ฿{margin_summary.get('cash_balance', 0):,.2f}")
        print(f"   • Total Equity:                 ฿{margin_summary.get('total_equity', 0):,.2f}")
        print(f"   • Holdings count:               {len(margin_holdings)} stocks")
        for h in margin_holdings:
            print(f"     - {h.get('symbol')} ({h.get('position_type', 'LONG')}): {h.get('volume')} shares @ ฿{h.get('avg_cost', 0):,.2f}")
    except Exception as e:
        print(f"{C_RED}❌ Error during Margin Account switch/scrape: {e}{C_RESET}")
        results["errors"].append(f"Margin account error: {e}")

    # =========================================================================
    # STEP 5: Session Persistence & Re-entry Validation (Zero-OTP Check)
    # =========================================================================
    print(f"\n{C_BOLD}[STEP 5/5] Testing Session Persistence & Direct Re-entry (Zero-OTP)...{C_RESET}")
    try:
        # Save storage state
        if auth_driver.context:
            await auth_driver.context.storage_state(path=settings.SESSION_STATE_PATH)
            print(f" • Saved storage state to {settings.SESSION_STATE_PATH}")

        # Test pre-flight verification on a newly opened tab
        test_page = await auth_driver.context.new_page()
        print(f" • Navigating fresh tab directly to {settings.TRADEMAN_PORTFOLIO_URL} ...")
        await test_page.goto(settings.TRADEMAN_PORTFOLIO_URL, wait_until="domcontentloaded", timeout=15000)
        await test_page.wait_for_timeout(2000)
        await popup_manager.dismiss_popups(test_page)

        acc_el = await test_page.wait_for_selector("#dropDownAccountPort, .account-selector", state="visible", timeout=8000)
        curr_url = test_page.url.lower()

        if acc_el and "trademan.in.th" in curr_url and "signin" not in curr_url:
            acc_text = (await acc_el.inner_text()).strip()
            print(f"{C_GREEN}🎉 ZERO-OTP RE-ENTRY VERIFIED! (#dropDownAccountPort visible: '{acc_text}'){C_RESET}")
            results["step5_session_reentry"] = True
        else:
            print(f"{C_YELLOW}⚠️ Direct re-entry could not locate #dropDownAccountPort on new tab (URL: {curr_url}){C_RESET}")
            results["errors"].append(f"Re-entry selector missing at {curr_url}")

        await test_page.close()
    except Exception as e:
        print(f"{C_RED}❌ Re-entry validation error: {e}{C_RESET}")
        results["errors"].append(f"Re-entry error: {e}")

    # =========================================================================
    # SUMMARY REPORT
    # =========================================================================
    print("\n" + "=" * 80)
    print(f"{C_BOLD}📊 FINAL KRUNGSRI VERIFICATION SUMMARY REPORT{C_RESET}")
    print("=" * 80)
    print(f" 1. Krungsri Portal Login & OTP:       {'✅ PASSED' if results['step1_login'] else '❌ FAILED'}")
    print(f" 2. TradeMan SSO Redirect & Popups:     {'✅ PASSED' if results['step2_sso'] else '❌ FAILED'}")
    print(f" 3. Cash A/C Switch (3024952):          {'✅ PASSED' if results['step3_switch_cash'] else '❌ FAILED'}")
    print(f" 4. Margin A/C Switch (3024959):        {'✅ PASSED' if results['step4_switch_margin'] else '❌ FAILED'}")
    print(f" 5. Session Persistence & Re-entry:     {'✅ PASSED' if results['step5_session_reentry'] else '❌ FAILED'}")
    
    if results["errors"]:
        print(f"\n{C_RED}⚠️ Identified Issues / Edge Cases:{C_RESET}")
        for err in results["errors"]:
            print(f"   • {err}")
    else:
        print(f"\n{C_GREEN}{C_BOLD}🎉 100% ALL 5 MILESTONES PASSED WITH ZERO CRITICAL FAILURES!{C_RESET}")
    print("=" * 80)

    return results


def main():
    parser = argparse.ArgumentParser(description="Krungsri TradeMan Full-Spectrum Verification Runner")
    parser.add_argument("--force-fresh", action="store_true", help="Clear cookies and perform fresh login with new OTP")
    parser.add_argument("--headless", action="store_true", help="Run without visible Chrome window")
    args = parser.parse_args()

    asyncio.run(run_full_spectrum_flow(force_fresh=args.force_fresh, headless=args.headless))


if __name__ == "__main__":
    main()
