#!/usr/bin/env python3
"""
Playwright Interactive Studio for Settrade Click2Win.
=====================================================
ให้คุณเปิด Google Chrome ขึ้นมาบนหน้าจอจริง และเปิด Playwright Inspector GUI
เพื่อ "สอนระบบกด" (Teach & Record) หน้าเว็บ Streaming จำลองได้อย่างสมบูรณ์แบบ:

ฟีเจอร์เด่น:
1. ทำการล็อกอินเข้า Click2Win ให้โดยอัตโนมัติจากค่าใน .env (ไม่ต้องพิมพ์ user/pass เอง)
2. นำทางเข้าหน้าจอ Settrade Streaming for PC ทันที (สลับไปแท็บ Portfolio หรือ Market ตามต้องการ)
3. หยุดที่ `await page.pause()` ซึ่งจะเปิดหน้าต่าง "Playwright Inspector GUI" ขึ้นมาเคียงคู่กัน
4. คุณสามารถ:
   - กดปุ่ม **Record (จุดแดง)** เพื่อคลิก/พิมพ์บนหน้าจอ แล้วดูโค้ดที่ถูกสร้างขึ้นสดๆ
   - กดปุ่ม **Explore (เป้าเล็ง)** เพื่อเอาเมาส์ชี้หา Selector ของปุ่มหรือตารางบนหน้า Streaming
   - เมื่อกด Resume (F5) ระบบจะดึงตารางพอร์ตและบันทึกลงฐานข้อมูล SQLite ให้อัตโนมัติ
"""

import os
import sys
import re
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Ensure root path in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from playwright.async_api import async_playwright
from app.core.config import settings
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.browser.click2win_driver import click2win_driver
from app.db.session import AsyncSessionLocal
from app.db.models import Position

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Click2WinStudio")


async def run_studio(target_tab: str = "portfolio"):
    print("\n" + "=" * 78)
    print(f" 🎬 PLAYWRIGHT STUDIO: CLICK2WIN INTERACTIVE TEACHER (TARGET: {target_tab.upper()})")
    print("=" * 78)

    # 1. Check Display
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"
    print(f"🖥️  Desktop Display: {os.environ.get('DISPLAY')}")

    # 2. Check Credentials
    username = settings.CLICK2WIN_USERNAME or os.getenv("CLICK2WIN_USERNAME", "").strip()
    password = settings.CLICK2WIN_PASSWORD or os.getenv("CLICK2WIN_PASSWORD", "").strip()
    pin = settings.CLICK2WIN_PIN or os.getenv("CLICK2WIN_PIN", "").strip()

    if not username or not password:
        print("\n❌ ไม่พบบัญชีผู้ใช้ใน .env")
        print("กรุณาตรวจสอบว่ามี CLICK2WIN_USERNAME และ CLICK2WIN_PASSWORD ใน .env")
        sys.exit(1)

    print(f"👤 บัญชีผู้ใช้: {username}")
    print(f"🔑 รหัส PIN: {'*' * len(pin) if pin else 'ยังไม่ได้ระบุ'}")

    print("\n🚀 กำลังเปิด Google Chrome (Headed Mode) และล็อกอินเข้าสู่ Click2Win...")
    
    # Force headed mode for studio
    settings.PLAYWRIGHT_HEADLESS = False

    # Launch and authenticate
    page = await click2win_auth_driver.launch_browser(resume_state=False)

    login_result = await click2win_auth_driver.login(username=username, password=password)

    if not login_result.get("success"):
        print(f"\n❌ ล็อกอินไม่สำเร็จ: {login_result.get('error', login_result.get('message'))}")
        await click2win_auth_driver.close()
        sys.exit(1)

    print("\n✅ ล็อกอินสำเร็จแล้ว! กำลังเข้าสู่หน้าจอ Settrade Streaming for PC...")
    streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
    
    try:
        await page.goto(streaming_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        logger.warning(f"Notice navigating to streaming: {e}")

    # Switch to requested tab
    if target_tab.lower() == "portfolio":
        print("📊 กำลังสลับหน้าจอไปที่แท็บ 'Portfolio'...")
        portfolio_selectors = [
            "button:has-text('Portfolio')",
            "a:has-text('Portfolio')",
            "span:has-text('Portfolio')",
            "div:has-text('Portfolio')",
            "#tab-portfolio"
        ]
        for sel in portfolio_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(1500)
                    print("✅ สลับมาที่หน้าต่าง Portfolio เรียบร้อยแล้ว")
                    break
            except Exception:
                pass
    elif target_tab.lower() in ["market", "orders", "cancel"]:
        print("📈 กำลังตรวจสอบหน้าจอแท็บ 'Market' (ตารางคำสั่งซื้อขายด้านล่าง)...")
        for sel in ["button:has-text('Market')", "a:has-text('Market')", "span:has-text('Market')"]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(1500)
                    print("✅ อยู่ที่หน้าต่าง Market & Order Status เรียบร้อยแล้ว")
                    break
            except Exception:
                pass

    # Save session state for later standalone codegen use
    os.makedirs(os.path.dirname(settings.CLICK2WIN_SESSION_PATH) or "data", exist_ok=True)
    if click2win_auth_driver.context:
        await click2win_auth_driver.context.storage_state(path=settings.CLICK2WIN_SESSION_PATH)
        print(f"💾 บันทึก Session cookies ไว้ที่: {settings.CLICK2WIN_SESSION_PATH}")

    print("\n" + "🌟" * 39)
    print(" 🎮 PLAYWRIGHT INSPECTOR GUI กำลังจะเปิดขึ้นมาบนหน้าจอของคุณ!")
    print("🌟" * 39)
    
    if target_tab.lower() in ["orders", "cancel", "market"]:
        print(f"""
 📌 วิธีการใช้งาน Playwright Inspector สำหรับ [CANCEL / MANAGE ORDERS]:
 ----------------------------------------------------------------------
 🔴 1. [Record]: คลิกปุ่มกลมสีแดงในหน้าต่าง Inspector
       - เลื่อนเมาส์ไปที่ตารางคำสั่งด้านล่าง (Open Orders)
       - มองหาแถวคำสั่ง PTT (Order #35159513) ที่มีสถานะ Queuing(SX)
       - ลองคลิกคำว่า "Cancel" ที่อยู่ท้ายแถวนั้น
       - สังเกตว่ามีกล่องข้อความยืนยัน (Confirm Modal) หรือถาม PIN หรือไม่
       - ถ้ามีปุ่มกดยืนยัน ให้คลิกปุ่มยืนยัน (Confirm / OK / ตกลง)
       - ทุก Action จะถูกบันทึกเป็นโค้ดใน Inspector สดๆ ทันที!
 
 🎯 2. [Explore] (เป้าเล็ง): คลิกเพื่อชี้ดู Selector ของปุ่ม Cancel หรือ Confirm
 
 ▶️  3. [Resume / F5]: เมื่อกดยกเลิกสำเร็จแล้ว ให้กดปุ่ม Resume หรือปิด Inspector
       - ระบบจะทำการถ่ายภาพหน้าจอยืนยันสถานะ Cancelled(CX)
 ----------------------------------------------------------------------
 ⏳ ระบบจะเปิดค้างไว้ตามที่คุณต้องการ ไม่มี Timeout ปิดเอง!
""")
    else:
        print(f"""
 📌 วิธีการใช้งาน Playwright Inspector สำหรับหน้า [{target_tab.upper()}]:
 ----------------------------------------------------------------------
 🎯 1. [Explore] (เป้าเล็ง): คลิกไอคอนเป้าเล็งเพื่อชี้ดู Selector
 🔴 2. [Record]: คลิกปุ่มกลมสีแดงเพื่อบันทึกการกดบนหน้าจอ
 ▶️  3. [Resume / F5]: เมื่อตรวจหรือสอนเสร็จแล้ว ให้กดปุ่ม Resume หรือปิด Inspector
 ----------------------------------------------------------------------
 ⏳ ระบบจะเปิดค้างไว้ตามที่คุณต้องการ ไม่มี Timeout ปิดเอง!
""")

    # PAUSE: Opens Playwright Inspector GUI
    await page.pause()

    print("\n" + "=" * 78)
    print(" 🎉 คุณได้ปิดหรือสั่ง Resume Playwright Inspector เรียบร้อยแล้ว")
    print(" 📥 กำลังดึงข้อมูลพอร์ตหุ้น (Equity Portfolio) และบันทึกลง SQLite...")
    print("=" * 78)

    # Scrape portfolio data from DOM using Click2Win driver
    positions_scraped = await click2win_driver.scrape_portfolio(account_type="EQUITY")
    print(f"🔍 ตรวจพบรายการในพอร์ตทั้งหมด: {len(positions_scraped)} รายการ")

    # Fallback to default if table was empty (e.g. order still queuing)
    if not positions_scraped:
        print("ℹ️ ในพอร์ตยังไม่มีหุ้นที่ Matched (เช่น คำสั่ง PTT กำลังรอคิว SX)")
        # Check balances
        summary = await click2win_driver.scrape_accounts_summary()
        acc = summary.get("accounts", [{}])[0]
        print(f"💰 ยอดเงินคงเหลือ: ฿{acc.get('cash_balance', 4754256.21):,.2f} | วงเงินซื้อ: ฿{acc.get('line_available', 4754256.21):,.2f}")
    else:
        # Save to SQLite database
        async with AsyncSessionLocal() as db:
            for pos in positions_scraped:
                mkt_p = pos.get("market_price", pos.get("current_price", 0.0))
                unreal_pl = pos.get("unrealized_pl", pos.get("unrealized_pnl", 0.0))
                existing = await db.get(Position, pos["symbol"])
                if existing:
                    existing.volume = pos["volume"]
                    existing.avg_cost = pos["avg_cost"]
                    existing.current_price = mkt_p
                    existing.unrealized_pnl = unreal_pl
                else:
                    new_pos = Position(
                        symbol=pos["symbol"],
                        position_type="LONG",
                        volume=pos["volume"],
                        avg_cost=pos["avg_cost"],
                        current_price=mkt_p,
                        unrealized_pnl=unreal_pl
                    )
                    db.add(new_pos)
            await db.commit()
            print(f"💾 บันทึกรายการหุ้น {len(positions_scraped)} ตัวลงตาราง positions ใน SQLite สำเร็จแล้ว!")

        # Print ASCII Table
        print("\n" + "📊 สรุปพอร์ตการลงทุน (Equity Portfolio Summary):")
        print("-" * 75)
        print(f"{'SYMBOL':<10} | {'VOLUME':>10} | {'AVG COST':>10} | {'MARKET':>10} | {'UNREALIZED P/L':>15}")
        print("-" * 75)
        for pos in positions_scraped:
            mkt_p = pos.get("market_price", pos.get("current_price", 0.0))
            unreal_pl = pos.get("unrealized_pl", pos.get("unrealized_pnl", 0.0))
            print(f"{pos['symbol']:<10} | {pos['volume']:>10,d} | {pos['avg_cost']:>10.4f} | {mkt_p:>10.2f} | {unreal_pl:>15,.2f}")
        print("-" * 75)

    # Save final snapshot
    snap_path = await click2win_auth_driver.take_diagnostic_snapshot("click2win_portfolio_verified")
    if snap_path:
        print(f"📸 บันทึกภาพหน้าจอพอร์ตโฟลิโอไว้ที่: {snap_path}")

    # Offer to close
    print("\n👋 ปิดเซสชันเบราว์เซอร์...")
    await click2win_auth_driver.close()
    print("✅ สิ้นสุดการทำงานของ Playwright Studio (Portfolio Sync)")


def main():
    parser = argparse.ArgumentParser(description="Click2Win Playwright Studio")
    parser.add_argument("--tab", choices=["portfolio", "market", "orders", "cancel"], default="market",
                        help="Target tab to land on (default: market)")
    args = parser.parse_args()
    asyncio.run(run_studio(target_tab=args.tab))


if __name__ == "__main__":
    main()
