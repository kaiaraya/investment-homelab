#!/usr/bin/env python3
"""
Interactive Visible Headed Click2Win Live Browser Test Script.
Opens Google Chrome visibly on your desktop (:0), navigates to Click2Win,
enters credentials, verifies login, and checks Equity & Derivatives accounts.
"""

import sys
import os
import time
import asyncio
import logging
from dotenv import load_dotenv

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# Freshly load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.browser.click2win_driver import click2win_driver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Click2WinLiveTest")


async def main():
    print("=" * 75)
    print(" 🖥️  LIVE HEADED BROWSER TEST: SETTRADE CLICK2WIN")
    print("=" * 75)

    # 1. Ensure DISPLAY environment variable for Desktop window
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"
    print(f"• Desktop Display: {os.environ.get('DISPLAY')}")

    # Force visible headed Chrome
    settings.PLAYWRIGHT_HEADLESS = False

    # 2. Check credentials from .env
    username = os.getenv("CLICK2WIN_USERNAME", "").strip()
    password = os.getenv("CLICK2WIN_PASSWORD", "").strip()

    if not username or not password:
        print("\n⚠️  CLICK2WIN CREDENTIALS NOT FOUND IN .env!")
        print("กรุณากรอก Username และ Password ในไฟล์ `.env` ที่บรรทัด:")
        print("   CLICK2WIN_USERNAME=\"your_username\"")
        print("   CLICK2WIN_PASSWORD=\"your_password\"")
        print("\nหรือจะพิมพ์กรอกตอนนี้เลยก็ได้ (ระบบจะไม่บันทึกรหัสผ่านลง Log):")
        try:
            username = input("👉 Enter Click2Win Username / Email: ").strip()
            import getpass
            password = getpass.getpass("👉 Enter Click2Win Password: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

        if not username or not password:
            print("❌ Username and Password are required. Exiting.")
            sys.exit(1)

    print(f"\n🚀 กำลังเปิด Google Chrome บนหน้าจอของคุณ (Headed Mode)...")
    page = await click2win_auth_driver.launch_browser(resume_state=False)

    print(f"🌐 กำลังนำทางไปยัง {settings.CLICK2WIN_URL} ...")
    login_result = await click2win_auth_driver.login(username=username, password=password)

    if login_result.get("success"):
        print("\n✅ ล็อกอินเข้าสู่ Click2Win สำเร็จแล้ว!")
        print(f"• URL: {login_result.get('url')}")

        # Probe accounts
        print("\n🔍 กำลังตรวจสอบบัญชีหุ้น (Equity) และอนุพันธ์ (Derivatives)...")
        accounts_summary = await click2win_driver.scrape_accounts_summary()
        accounts = accounts_summary.get("accounts", [])
        print(f"📊 พบบัญชีทั้งหมด {len(accounts)} บัญชี:")
        for acc in accounts:
            print(f"   - [{acc.get('account_type')}] เลขที่: {acc.get('account_no')} | วงเงินซื้อ: ฿{acc.get('line_available', 0):,.2f} | เงินสด: ฿{acc.get('cash_balance', 0):,.2f}")

        print("\n" + "=" * 75)
        print(" 🎉 หน้าต่าง Google Chrome เปิดค้างอยู่บนหน้าจอของคุณแล้ว")
        print("    คุณสามารถมองเห็นหน้าเว็บ Click2Win ได้โดยตรงบน Desktop")
        print("=" * 75)
        
        # Take a verification screenshot
        snap_path = await click2win_auth_driver.take_diagnostic_snapshot("live_test_verified")
        if snap_path:
            print(f"📸 บันทึกภาพ Screenshot ยืนยันไว้ที่: {snap_path}")

        print("\n⏱️ กำลังเปิดหน้าต่างเบราว์เซอร์ค้างไว้ 60 วินาที เพื่อให้คุณตรวจสอบบนหน้าจอ...")
        for i in range(60, 0, -10):
            print(f"   (เปิดค้างอยู่อีก {i} วินาที)...")
            await asyncio.sleep(10)
    else:
        print(f"\n❌ การล็อกอินไม่สำเร็จ: {login_result.get('error', login_result.get('message'))}")
        print("หน้าต่าง Chrome จะเปิดค้างไว้ 10 วินาทีเพื่อให้คุณดูข้อความแจ้งเตือนบนหน้าจอ...")
        await asyncio.sleep(10)

    await click2win_auth_driver.close()
    print("👋 จบการทดสอบเบราว์เซอร์.")


if __name__ == "__main__":
    asyncio.run(main())
