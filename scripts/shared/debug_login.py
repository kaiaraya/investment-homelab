#!/usr/bin/env python3
"""
Unified Playwright Debug Harness - Workflow 1: Login & Session Verification.
Supports both:
1. Settrade Click2Win (Sandbox - No OTP required)
2. Krungsri TradeMan (Live Production - 2FA SMS OTP required)

Usage:
    .venv/bin/python scripts/debug_login.py [--platform click2win|trademan] [--headless]
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
logger = logging.getLogger("DebugLogin")


async def run_debug_login(platform_name: str, headed: bool = True, wait_seconds: int = 0):
    print("=" * 75)
    print(f" 🚀 PLAYWRIGHT DEBUG: WORKFLOW 1 - LOGIN & SESSION VERIFICATION")
    print(f" • Target Platform: {platform_name.upper()}")
    print(f" • Mode: {'Headed (Visible Desktop :0)' if headed else 'Headless'}")
    print("=" * 75)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.TRADING_PLATFORM = platform_name.upper()
    settings.PLAYWRIGHT_HEADLESS = not headed

    auth = get_auth_driver()
    broker = get_broker_driver()

    print(f"\n[1/4] Checking existing saved session state...")
    page = await auth.launch_browser(resume_state=True)
    is_saved_valid = await auth.verify_saved_session()

    if is_saved_valid:
        print(f"✅ Active session restored from cookies! Already authenticated on {platform_name.upper()}.")
        print(f"• Current URL: {page.url}")
        print(f"• Page Title: '{await page.title()}'")
    else:
        print(f"ℹ️  No valid session found. Proceeding with fresh automated login...")
        if platform_name.upper() == "CLICK2WIN":
            username = settings.CLICK2WIN_USERNAME
            password = settings.CLICK2WIN_PASSWORD
            pin = settings.CLICK2WIN_PIN

            if not username or not password:
                print("❌ Error: CLICK2WIN_USERNAME and CLICK2WIN_PASSWORD not found in .env!")
                return False

            print(f"• Logging in as {username}...")
            success = await auth.login(username=username, password=password, pin=pin)
            if success:
                print("✅ Click2Win Login Successful!")
            else:
                print("❌ Click2Win Login Failed. Check credentials or screenshot in data/screenshots/")
                return False
        else:
            username = settings.KRUNGSRI_USERNAME
            password = settings.KRUNGSRI_PASSWORD

            if not username or not password:
                print("❌ Error: KRUNGSRI_USERNAME and KRUNGSRI_PASSWORD not found in .env!")
                return False

            print(f"• Initiating Krungsri TradeMan automated login for {username[:3]}***...")
            login_task = asyncio.create_task(
                auth.login(username=username, password=password)
            )

            from app.services.kdeconnect_service import kdeconnect_service
            announced_ref = False
            while not login_task.done():
                await asyncio.sleep(1.0)
                if auth.status == "AWAITING_OTP":
                    if not announced_ref:
                        print(f"\n🔑 2FA SMS OTP REQUIRED! Broker Ref Code: [{auth.current_ref or 'Pending'}]")
                        print("• 📱 Auto-listening via KDE Connect (Mi 10T)...")
                        print("• 💻 Manual Fallback: Submit via Web Console (/console) or API")
                        announced_ref = True

                    # Poll KDE Connect notifications if reachable
                    try:
                        polled = await kdeconnect_service.poll_active_notifications()
                        if polled:
                            print(f"📱 KDE Connect auto-captured OTP: {polled.masked_otp}! Relaying to broker...")
                    except Exception:
                        pass

            try:
                login_res = await login_task
                if login_res.success:
                    print(f"✅ Krungsri TradeMan Login Successful! Active URL: {auth.current_url}")
                else:
                    print(f"❌ Krungsri Login Failed: {login_res.message}")
                    return False
            except Exception as e:
                print(f"❌ Login Exception: {e}")
                return False

    print("\n[2/4] Dismissing popups and checking active UI...")
    await popup_manager.dismiss_popups(page)

    print("\n[3/4] Inspecting account balances and excess equity...")
    try:
        acc = await broker.scrape_account_summary(force_live=True)
        print("• Account Summary:")
        for k, v in acc.items():
            if isinstance(v, (int, float)):
                print(f"   - {k}: ฿{v:,.2f}")
            else:
                print(f"   - {k}: {v}")
    except Exception as e:
        print(f"⚠️ Notice while reading account summary: {e}")

    screenshot_dir = os.path.join(PROJECT_ROOT, "data", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    screenshot_path = os.path.join(screenshot_dir, f"{platform_name.lower()}_live.png")
    try:
        await page.screenshot(path=screenshot_path)
        print(f"📸 Live screenshot saved: {screenshot_path}")
        
        # Also copy to artifact directory if available
        artifact_dir = "/home/araya-sawasdichai/.gemini/antigravity-ide/brain/de871b89-ba14-4439-adad-2982685d6828"
        if os.path.exists(artifact_dir):
            import shutil
            shutil.copy2(screenshot_path, os.path.join(artifact_dir, f"{platform_name.lower()}_live.png"))
    except Exception as e:
        print(f"⚠️ Screenshot capture warning: {e}")

    print("\n[4/4] Verification Complete! Chrome browser is ACTIVE and VISIBLE.")
    print("You can inspect the screen or interact with it.")
    
    if wait_seconds > 0:
        print(f"Keeping browser open for {wait_seconds} seconds...")
        await asyncio.sleep(wait_seconds)
    else:
        print("Press Enter to finish this debug session (Browser will remain open if cookies saved)...")
        try:
            await asyncio.to_thread(input)
        except (KeyboardInterrupt, EOFError):
            pass

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Playwright Login & Session")
    parser.add_argument(
        "--platform",
        choices=["click2win", "trademan"],
        default=getattr(settings, "TRADING_PLATFORM", "CLICK2WIN").lower(),
        help="Trading platform (click2win or trademan)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless instead of visible window"
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="Seconds to keep browser open (0 for interactive Enter)"
    )
    args = parser.parse_args()

    asyncio.run(run_debug_login(
        platform_name=args.platform,
        headed=not args.headless,
        wait_seconds=args.wait_seconds
    ))
