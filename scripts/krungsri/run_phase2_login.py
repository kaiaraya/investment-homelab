#!/usr/bin/env python3
"""
Interactive Phase 2 Krungsri Login & 2FA OTP Relay Verification Script.
Runs Headed Chrome on the active desktop screen, submits credentials,
waits for SMS OTP (KDE Connect auto-capture or web console/manual CLI entry), and confirms TradeMan SSO.
"""

import sys
import os
import time
import asyncio
import logging
import threading
from dotenv import load_dotenv

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Reload .env freshly
load_dotenv(override=True)

from app.core.config import settings
from app.browser.auth_driver import KrungsriAuthDriver
from app.core.events import event_bus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Phase2Runner")


async def main():
    print("=" * 70)
    print(" 🚀 Phase 2: Krungsri Securities & TradeMan Playwright Driver")
    print("=" * 70)

    # 1. Verify Credentials
    username = os.getenv("KRUNGSRI_USERNAME", settings.KRUNGSRI_USERNAME).strip()
    password = os.getenv("KRUNGSRI_PASSWORD", settings.KRUNGSRI_PASSWORD).strip()

    if not username or not password:
        print("\n⚠️  KRUNGSRI CREDENTIALS NOT CONFIGURED IN .env!")
        print("Please edit `.env` and set:")
        print("   KRUNGSRI_USERNAME=your_username")
        print("   KRUNGSRI_PASSWORD=your_password")
        print("\nOr you can enter them now interactively (they will not be logged):")
        try:
            username = input("Enter Krungsri Username: ").strip()
            import getpass
            password = getpass.getpass("Enter Krungsri Password: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted by user.")
            sys.exit(0)

        if not username or not password:
            print("❌ Username and Password are required. Exiting.")
            sys.exit(1)

    print(f"\n[1/4] Starting Headed Chromium Browser (/usr/bin/google-chrome)...")
    print(f"      Display:  {os.environ.get('DISPLAY', ':0')}")
    print(f"      Headless: {settings.PLAYWRIGHT_HEADLESS}")
    print(f"      Target:   {settings.KRUNGSRI_LOGIN_URL}")

    driver = KrungsriAuthDriver()

    try:
        page = await driver.launch_browser(resume_state=True)
        print("      ✅ Browser window launched successfully on your screen.")

        # Check existing session
        print("\n[2/4] Checking for existing active session in data/session_state.json...")
        if await driver.verify_saved_session():
            print("      🎉 SUCCESS: Active session restored! TradeMan is already authenticated.")
            print(f"      Current URL: {page.url}")
            print("\nBrowser will remain open for 30 seconds for your inspection.")
            await asyncio.sleep(30)
            await driver.close()
            return

        print("      No active session found. Proceeding with live Krungsri login...")
        print(f"\n[3/4] Navigating to Krungsri Login & Submitting Credentials...")
        print(f"      Username: {username[:3]}*** (masked)")

        # Run login sequence in background task so we can monitor CLI
        login_task = asyncio.create_task(
            driver.login(
                username=username,
                password=password,
                timeout_otp=settings.OTP_TIMEOUT_SECONDS
            )
        )

        # Monitor status while waiting
        start_time = time.time()
        ref_announced = False
        loop = asyncio.get_running_loop()

        def stdin_worker():
            """Allow typing 6-digit OTP directly into terminal while waiting."""
            try:
                line = sys.stdin.readline().strip()
                if line and len(line) == 6 and line.isdigit():
                    print(f"\n⌨️  CLI input detected: {line}. Submitting OTP...")
                    asyncio.run_coroutine_threadsafe(
                        event_bus.publish_otp({"otp": line, "source": "cli_terminal", "ref": driver.current_ref}),
                        loop
                    )
            except Exception:
                pass

        while not login_task.done():
            await asyncio.sleep(1.0)
            elapsed = int(time.time() - start_time)

            if driver.status == "AWAITING_OTP":
                if not ref_announced:
                    ref_announced = True
                    print("\n" + "#" * 65)
                    print(f" 📲 2FA SMS OTP REQUIRED BY KRUNGSRI SECURITIES!")
                    print(f"    Reference Code (Ref): {driver.current_ref or 'N/A'}")
                    print(f"    Timeout: {settings.OTP_TIMEOUT_SECONDS} seconds")
                    print(f"    Multiple Ways to Submit OTP:")
                    print(f"      1. Web Console: http://100.88.217.33:8000/console")
                    print(f"      2. CLI Terminal: Type the 6 digits right here and press Enter")
                    print("#" * 65)
                    threading.Thread(target=stdin_worker, daemon=True).start()

                remaining = max(0, settings.OTP_TIMEOUT_SECONDS - elapsed)
                sys.stdout.write(f"\r⏳ Waiting for SMS OTP... [{remaining}s remaining]   ")
                sys.stdout.flush()

        result = await login_task
        print("\n\n" + "=" * 70)
        print(" 🎉 Phase 2 Login Verification: SUCCESSFUL!")
        print("=" * 70)
        print(f" Status:       {result.get('status')}")
        print(f" Final URL:    {result.get('url')}")
        print(f" Session File: {settings.SESSION_STATE_PATH} (Saved)")
        print(f" Message:      {result.get('message')}")
        print("\nThe TradeMan / Krungsri trading browser window is now LIVE and AUTHENTICATED.")
        print("Keeping browser open for 60 seconds so you can inspect the interface.")
        await asyncio.sleep(60)

    except Exception as e:
        print(f"\n❌ Error during Phase 2 login verification: {e}")
        snapshot = await driver.take_diagnostic_snapshot("phase2_cli_error")
        if snapshot:
            print(f"📸 Diagnostic screenshot captured: {snapshot.get('screenshot')}")
            print(f"📄 HTML dump captured: {snapshot.get('html')}")
    finally:
        print("\nClosing browser...")
        await driver.close()
        print("Finished.")


if __name__ == "__main__":
    asyncio.run(main())
