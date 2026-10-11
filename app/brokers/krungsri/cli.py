#!/usr/bin/env python3
"""
Krungsri TradeMan Standalone CLI Tester.
=========================================
Dedicated interactive runner for Krungsri Securities automated login,
2FA SMS OTP verification (KDE Connect + Terminal input + Direct Browser),
and TradeMan SSO session management.

Usage:
  # 1. Run interactive Headed login with visible Chrome and Terminal OTP prompt:
  .venv/bin/python -m app.brokers.krungsri.cli login

  # 2. Force fresh login (clear cookies and request new OTP):
  .venv/bin/python -m app.brokers.krungsri.cli login --force-fresh

  # 3. Check saved session status:
  .venv/bin/python -m app.brokers.krungsri.cli status

  # 4. Directly feed OTP into running session:
  .venv/bin/python -m app.brokers.krungsri.cli submit-otp 123456 --ref BIPE
"""

import os
import sys
import time
import asyncio
import logging
import argparse
from typing import Optional

from app.core.config import settings
from app.core.events import event_bus
from app.schemas.auth import OTPPayload, OTPSource, AuthStatus
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("KrungsriCLI")


async def _terminal_otp_listener(current_ref: Optional[str] = None):
    """Asynchronously listens to stdin so user can type OTP directly in the terminal."""
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


async def cmd_login(args):
    headed = not args.headless
    force_fresh = args.force_fresh

    if "DISPLAY" not in os.environ and headed:
        os.environ["DISPLAY"] = ":0"

    settings.PLAYWRIGHT_HEADLESS = not headed

    print("=" * 75)
    print(f"{C_BOLD}{C_MAGENTA} 🏢 KRUNGSRI TRADEMAN - STANDALONE INTERACTIVE TESTER{C_RESET}")
    print(f" • Mode:        {C_GREEN}{'Headed (Visible Chrome on DISPLAY=:0)' if headed else 'Headless'}{C_RESET}")
    print(f" • Force Fresh: {C_YELLOW}{force_fresh}{C_RESET}")
    print(f" • State File:  {settings.SESSION_STATE_PATH}")
    print("=" * 75)

    # 1. Check existing session if not force_fresh
    if not force_fresh:
        print(f"\n[1/5] Checking existing saved session state in {settings.SESSION_STATE_PATH}...")
        try:
            page = await auth_driver.launch_browser(resume_state=True)
            if await auth_driver.verify_saved_session():
                print(f"{C_GREEN}✅ Active session verified! Already authenticated on TradeMan.{C_RESET}")
                print(f" • Current URL: {page.url}")
                print(f" • Title:       '{await page.title()}'")
                await _show_account_summary()
                await _hold_browser_open(page, args.wait_seconds)
                return True
            else:
                print(f"{C_YELLOW}ℹ️  Saved session expired or not found. Proceeding with fresh login...{C_RESET}")
        except Exception as e:
            print(f"{C_YELLOW}⚠️  Session check note: {e}. Proceeding with login...{C_RESET}")

    # 2. Verify credentials
    username = settings.KRUNGSRI_USERNAME
    password = settings.KRUNGSRI_PASSWORD

    if not username or not password:
        print(f"{C_RED}❌ Error: KRUNGSRI_USERNAME and KRUNGSRI_PASSWORD not found in .env!{C_RESET}")
        return False

    print(f"\n[2/5] Initiating Krungsri Portal automated login for {C_BOLD}{username[:3]}***{C_RESET}...")

    # Start login task
    login_task = asyncio.create_task(
        auth_driver.login(
            username=username,
            password=password,
            timeout_otp=args.otp_timeout,
            force_fresh=force_fresh
        )
    )

    announced_ref = False
    otp_input_task = None

    # Monitoring loop during login
    while not login_task.done():
        await asyncio.sleep(0.5)

        if auth_driver.status == "AWAITING_OTP" and not announced_ref:
            ref_code = auth_driver.current_ref or "Pending"
            announced_ref = True
            print("\n" + "-" * 75)
            print(f"{C_BOLD}{C_YELLOW}🔑 2FA SMS OTP REQUIRED BY KRUNGSRI!{C_RESET}")
            print(f" • Broker Reference Code: {C_BOLD}{C_CYAN}[Ref: {ref_code}]{C_RESET}")
            print(f" • 📱 Auto-listening via KDE Connect (Mi 10T)...")
            print(f" • 💻 Directly type in browser Chrome window (Playwright detects DOM automatically)")
            print(f" • ⌨️  OR enter 6-digit OTP right here in this terminal:")
            print(f"{C_CYAN}Enter 6-digit OTP: {C_RESET}", end="", flush=True)

            # Spawn concurrent stdin listener
            otp_input_task = asyncio.create_task(_terminal_otp_listener(current_ref=ref_code))

    if otp_input_task and not otp_input_task.done():
        otp_input_task.cancel()

    try:
        login_res = await login_task
        if login_res.success:
            print("\n" + "=" * 75)
            print(f"{C_GREEN}{C_BOLD}🎉 KRUNGSRI TRADEMAN LOGIN SUCCESSFUL!{C_RESET}")
            print(f" • Active Tab URL: {auth_driver.current_url}")
            print(f" • Broker Ref:    {login_res.otp_ref or auth_driver.current_ref or 'N/A'}")
            print(f" • Session Saved: {settings.SESSION_STATE_PATH}")
            print("=" * 75)

            # Scrape and print account summary
            await _show_account_summary()

            # Keep browser open for inspection
            if auth_driver.page:
                await _hold_browser_open(auth_driver.page, args.wait_seconds)
            return True
        else:
            print(f"\n{C_RED}❌ Login failed: {login_res.message}{C_RESET}")
            return False

    except Exception as e:
        print(f"\n{C_RED}❌ Login Exception: {e}{C_RESET}")
        return False


async def _show_account_summary():
    """Scrapes and prints Cash Balance and Credit Balance accounts."""
    print(f"\n[4/5] Inspecting TradeMan portfolio & account balances...")
    try:
        acc = await trademan_driver.scrape_account_summary(force_live=True)
        print(f"{C_BOLD}📊 Scraped TradeMan Accounts Summary:{C_RESET}")
        for k, v in acc.items():
            if isinstance(v, (int, float)):
                print(f"   • {k:<25}: ฿{v:,.2f}")
            else:
                print(f"   • {k:<25}: {v}")
    except Exception as e:
        print(f"   ⚠️ Notice: {e}")


async def _hold_browser_open(page, wait_seconds: int = 0):
    """Keeps Chrome window open so user can inspect it or test interactions."""
    print("\n[5/5] Chrome browser is ACTIVE on your desktop screen.")
    if wait_seconds > 0:
        print(f"Keeping browser open for {wait_seconds} seconds...")
        await asyncio.sleep(wait_seconds)
    else:
        print(f"{C_CYAN}👉 Press Enter in this terminal to close the test runner (Session state will be preserved):{C_RESET}")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, sys.stdin.readline)
        except (KeyboardInterrupt, EOFError):
            pass


async def cmd_status(args):
    print("=" * 65)
    print(f"{C_BOLD}🏢 Krungsri TradeMan Session Status{C_RESET}")
    print("=" * 65)
    exists = os.path.exists(settings.SESSION_STATE_PATH)
    print(f"Session State File: {settings.SESSION_STATE_PATH} ({'EXISTS' if exists else 'NOT FOUND'})")
    print(f"Driver Status:      {auth_driver.status}")
    print(f"Authenticated:      {auth_driver.is_authenticated}")
    print(f"Current URL:        {auth_driver.current_url or 'None'}")
    print(f"Last Heartbeat:     {auth_driver.last_heartbeat or 'Never'}")

    # Test reachability of Android phone via KDE Connect
    try:
        reachable = await kdeconnect_service.is_device_reachable()
        routes = await kdeconnect_service.get_network_routes()
        print(f"KDE Connect Mi 10T: {'✅ ONLINE' if reachable else '❌ OFFLINE'} (Route: {routes.get('route_label', '-')})")
    except Exception:
        pass
    print("=" * 65)


async def cmd_submit_otp(args):
    code = args.otp.strip()
    ref = args.ref
    print(f"Sending OTP {code} (Ref: {ref or 'None'}) to EventBus...")
    await event_bus.publish_otp(
        OTPPayload(
            source=OTPSource.CLI_TERMINAL,
            otp=code,
            ref=ref,
            sender="cli_submit"
        )
    )
    print(f"{C_GREEN}✅ OTP {code[:2]}**** dispatched successfully!{C_RESET}")


def main():
    parser = argparse.ArgumentParser(description="Krungsri TradeMan Standalone CLI Tester")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # login command
    login_p = subparsers.add_parser("login", help="Run interactive Krungsri login with visible Chrome")
    login_p.add_argument("--headless", action="store_true", help="Run in background headless mode")
    login_p.add_argument("--force-fresh", action="store_true", help="Bypass saved cookies and force fresh login")
    login_p.add_argument("--otp-timeout", type=int, default=180, help="OTP timeout in seconds (default: 180)")
    login_p.add_argument("--wait-seconds", type=int, default=0, help="Keep browser open for N seconds (0 for Enter prompt)")

    # status command
    subparsers.add_parser("status", help="Check session and KDE Connect status")

    # submit-otp command
    otp_p = subparsers.add_parser("submit-otp", help="Directly submit OTP into running session")
    otp_p.add_argument("otp", help="6-digit SMS OTP code")
    otp_p.add_argument("--ref", default=None, help="Reference code")

    # full-test command
    full_p = subparsers.add_parser("full-test", help="Run full-spectrum session, OTP, and multi-account verification")
    full_p.add_argument("--headless", action="store_true", help="Run without visible Chrome window")
    full_p.add_argument("--force-fresh", action="store_true", help="Force fresh login with new OTP")

    args = parser.parse_args()

    if not args.command or args.command == "login":
        if not args.command:
            args.command = "login"
            args.headless = False
            args.force_fresh = False
            args.otp_timeout = 180
            args.wait_seconds = 0
        asyncio.run(cmd_login(args))
    elif args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "submit-otp":
        asyncio.run(cmd_submit_otp(args))
    elif args.command == "full-test":
        from scripts.krungsri.test_krungsri_full_session_flow import run_full_spectrum_flow
        asyncio.run(run_full_spectrum_flow(force_fresh=args.force_fresh, headless=args.headless))


if __name__ == "__main__":
    main()
