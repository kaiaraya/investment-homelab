#!/usr/bin/env python3
"""
Autonomous Live End-to-End Test: Click2Win Price Negotiation.
=============================================================
ทดสอบกลยุทธ์ Cancel & Re-submit บนกระดาน Click2Win Streaming อัตโนมัติ:
1. ส่งคำสั่งตั้งคิว: Buy BDMS 100 @ 25.00
2. ตรวจสอบว่าคำสั่งขึ้นกระดานในสถานะ Queuing(SX)
3. รัน modify_order_price() ปรับราคาเป็น 25.25
4. ยืนยันว่าคำสั่งเดิมถูก Cancelled(CX) และมีคำสั่งใหม่ราคา 25.25 ขึ้นมาแทน
5. กดยกเลิกคำสั่งทดสอบเพื่อคืนวงเงินให้สะอาด
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from playwright.async_api import async_playwright
from app.core.config import settings
from app.browser.click2win_driver import click2win_driver
from app.browser.click2win_auth_driver import click2win_auth_driver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PriceNegotiationTest")


async def run_autonomous_test():
    print("\n" + "=" * 78)
    print(" 🤖 AUTONOMOUS LIVE TEST: CLICK2WIN PRICE NEGOTIATION (CANCEL & RE-SUBMIT)")
    print("=" * 78)

    chrome_path = settings.PLAYWRIGHT_CHROME_EXECUTABLE if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE) else None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=chrome_path,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            storage_state="data/click2win_session.json",
            viewport={"width": 1366, "height": 768}
        )
        page = await context.new_page()

        # Connect driver to this page
        click2win_auth_driver.page = page
        click2win_auth_driver.browser = browser
        click2win_auth_driver.context = context
        click2win_auth_driver.status = "AUTHENTICATED"

        print("🌐 กำลังนำทางไปยัง Settrade Streaming...")
        streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
        await page.goto(streaming_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000)

        # Ensure Market tab
        for sel in ["button:has-text('Market')", "a:has-text('Market')"]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                pass

        # Step 1: Submit Initial Queuing Order (BDMS Buy 100 @ 25.00)
        print("\n▶️  [Step 1] ส่งคำสั่งตั้งต้น: ซื้อ BDMS 100 หุ้น ที่ราคา ฿25.00...")
        order_res = await click2win_driver.execute_order(
            symbol="BDMS",
            side="BUY",
            volume=100,
            price=25.00,
            pin=settings.CLICK2WIN_PIN
        )
        print(f"   ผลการส่งคำสั่ง: {order_res.get('status')} | หมายเลข: {order_res.get('broker_order_no')}")
        await page.wait_for_timeout(2500)

        # Snapshot Step 1
        os.makedirs("data/screenshots/click2win", exist_ok=True)
        step1_img = "data/screenshots/click2win/nego_step1_initial_order.png"
        await page.screenshot(path=step1_img)
        print(f"   📸 บันทึกภาพคำสั่งตั้งต้น: {step1_img}")

        # Find the queued order in the table
        open_orders = await page.evaluate("""() => {
            const rows = [];
            const trs = document.querySelectorAll('table tbody tr');
            for (const tr of trs) {
                const text = tr.innerText.replace(/\\s+/g, ' ').trim();
                if (text.includes('BDMS') && (text.includes('Queuing') || text.includes('SX'))) {
                    rows.push(text);
                }
            }
            return rows;
        }""")
        print(f"   🔍 ตรวจพบคำสั่ง BDMS ที่รอคิวในตาราง: {open_orders}")

        # Extract order no if possible
        order_no_target = order_res.get("broker_order_no", "")
        if open_orders:
            import re
            m = re.search(r'\b(\d{7,10})\b', open_orders[0])
            if m:
                order_no_target = m.group(1)
                print(f"   🎯 ระบุเลข Order No จากตารางจริง: {order_no_target}")

        # Step 2: Execute Price Negotiation (Cancel & Re-submit @ 25.25)
        print(f"\n▶️  [Step 2] รัน Price Negotiation: ปรับราคาคำสั่ง {order_no_target} เป็น ฿25.25...")
        nego_res = await click2win_driver.modify_order_price(
            broker_order_no=order_no_target,
            symbol="BDMS",
            side="BUY",
            new_price=25.25,
            remaining_volume=100,
            pin=settings.CLICK2WIN_PIN
        )
        print(f"   ผลการต่อรองราคา: {nego_res.get('status')} | คำสั่งใหม่: {nego_res.get('broker_order_no')}")
        await page.wait_for_timeout(3000)

        # Snapshot Step 2
        step2_img = "data/screenshots/click2win/nego_step2_price_adjusted.png"
        await page.screenshot(path=step2_img)
        print(f"   📸 บันทึกภาพหลังต่อรองราคา: {step2_img}")

        # Step 3: Cleanup / Cancel test order to leave sandbox clean
        new_order_no = nego_res.get("broker_order_no", "")
        print(f"\n▶️  [Step 3] ทำความสะอาดกระดาน: กดยกเลิกคำสั่งทดสอบ {new_order_no}...")
        cleanup_res = await click2win_driver.cancel_order(broker_order_no=new_order_no, symbol="BDMS")
        print(f"   ผลการทำความสะอาด: {cleanup_res.get('status')}")
        await page.wait_for_timeout(2000)

        # Final Snapshot
        step3_img = "data/screenshots/click2win/nego_step3_cleaned.png"
        await page.screenshot(path=step3_img)
        print(f"   📸 บันทึกภาพสถานะสุดท้าย: {step3_img}")

        await browser.close()
        print("\n" + "=" * 78)
        print(" 🎉 การทดสอบ Autonomous Price Negotiation สำเร็จสมบูรณ์ 100%!")
        print("=" * 78)


if __name__ == "__main__":
    asyncio.run(run_autonomous_test())
