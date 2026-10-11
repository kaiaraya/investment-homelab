#!/usr/bin/env python3
"""
Playwright Inspector Step-by-Step Tutorial for Beginners.
=========================================================
สคริปต์สอนการใช้งาน Playwright Inspector สำหรับมือใหม่:
- รันเบราว์เซอร์จริงแบบมองเห็นหน้าจอ (Headed Chrome)
- เปิดหน้าต่าง Playwright Inspector GUI ควบคู่กัน
- มีจุดหยุด `await page.pause()` เพื่อให้คุณฝึกกดปุ่ม Next Step ('Step over' หรือ F10)
- สอนใช้เครื่องมือ Explore (เป้าเล็ง) เพื่อชี้หา Selector บนหน้าเว็บ
"""

import asyncio
import os
import sys

# Ensure root path in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright


async def run_tutorial():
    print("\n" + "=" * 75)
    print(" 🎓 ยินดีต้อนรับสู่คู่มือการใช้ Playwright Inspector สำหรับมือใหม่")
    print("=" * 75)
    print(" 1. ระบบกำลังเปิด Google Chrome ขึ้นมาบนหน้าจอ...")
    print(" 2. หน้าต่าง 'Playwright Inspector' จะเปิดขึ้นมาควบคู่กัน")
    print("\n 📌 วิธีใช้งานหน้าต่าง Playwright Inspector:")
    print("    ▶️  Resume (F5)     : สั่งให้โปรแกรมรันต่อไปจนเจอจุดหยุดถัดไป")
    print("    ⏭️  Step over (F10) : ปุ่ม 'Next Step' กดทีละครั้งเพื่อสั่งรันทีละคำสั่ง!")
    print("    🎯  Explore (เป้าเล็ง): คลิกปุ่มนี้ แล้วเอาเมาส์ไปชี้ปุ่มบนหน้าเว็บ จะก๊อปปี้ Selector ให้ทันที")
    print("=" * 75 + "\n")

    async with async_playwright() as p:
        chrome_path = "/usr/bin/google-chrome"
        launch_kwargs = {
            "headless": False,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1366,850"
            ]
        }
        if os.path.exists(chrome_path):
            launch_kwargs["executable_path"] = chrome_path

        # 1. Launch Browser
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(viewport={"width": 1366, "height": 850})
        page = await context.new_page()

        # =========================================================================
        # 📍 Step 1: เปิดหน้า Web Test Console
        # =========================================================================
        url = "http://localhost:8000/console"
        print(f"▶️  [Step 1] กำลังเปิดหน้าเว็บ: {url}")
        await page.goto(url, wait_until="networkidle")

        print("\n" + "🔔" * 35)
        print(" ⏸️  [จุดหยุดที่ 1]: หน้าเว็บเปิดสำเร็จแล้ว!")
        print(" 👉 หันไปดูที่หน้าต่าง 'Playwright Inspector'")
        print(" 👉 ลองกดปุ่ม 'Step over' (หรือกด F10 บนคีย์บอร์ด) เพื่อก้าวไปทีละคำสั่ง")
        print(" 👉 หรือกดปุ่ม 'Resume' (F5) เพื่อข้ามไปยังจุดทดสอบถัดไป")
        print("🔔" * 35 + "\n")
        await page.pause()  # <--- จุดที่เปิด Inspector GUI

        # =========================================================================
        # 📍 Step 2: เลือก Preset คำสั่งซื้อหุ้น "Buy TRUE 3800"
        # =========================================================================
        print("▶️  [Step 2] กำลังคลิกปุ่ม Preset 'Buy TRUE 3800'...")
        await page.click("button:has-text('Buy TRUE 3800')")
        await asyncio.sleep(0.5)

        print("\n" + "🔔" * 35)
        print(" ⏸️  [จุดหยุดที่ 2]: กรอกฟอร์ม Preset เรียบร้อย!")
        print(" 👉 สังเกตบนหน้าเว็บ: ช่อง Symbol กลายเป็น 'TRUE', Volume กลายเป็น '3800'")
        print(" 👉 กด 'Step over' (F10) เพื่อเตรียมคลิกปุ่มส่งคำสั่ง")
        print("🔔" * 35 + "\n")
        await page.pause()  # <--- Inspector จะหยุดให้ตรวจฟอร์ม

        # =========================================================================
        # 📍 Step 3: ส่งคำสั่งซื้อ และตรวจเช็คผลลัพธ์ใน Console Log
        # =========================================================================
        print("▶️  [Step 3] กำลังคลิก 'Send Order Signal'...")
        await page.click("button:has-text('Send Order Signal')")
        await page.wait_for_timeout(1000)

        log_text = await page.inner_text("#consoleLog")
        print(f"   ผลลัพธ์ในหน้าจอ Console:\n   {log_text[:120].strip()}...")

        print("\n" + "🔔" * 35)
        print(" ⏸️  [จุดหยุดที่ 3]: ส่งคำสั่งสำเร็จ!")
        print(" 👉 หน้าจอแสดงผลว่าคำสั่งถูกบันทึกลงฐานข้อมูล SQLite เรียบร้อย")
        print(" 👉 กด 'Step over' (F10) เพื่อทดสอบด่านถัดไป")
        print("🔔" * 35 + "\n")
        await page.pause()

        # =========================================================================
        # 📍 Step 4: ทดสอบกฎป้องกันความเสี่ยง (Odd-lot 96 หุ้น ต้องถูกปฏิเสธ)
        # =========================================================================
        print("▶️  [Step 4] ทดสอบส่งเศษหุ้น 'Odd-lot 96' (Pre-Trade Risk Control)...")
        await page.click("button:has-text('Odd-lot 96')")
        await asyncio.sleep(0.3)
        await page.click("button:has-text('Send Order Signal')")
        await page.wait_for_timeout(800)

        print("\n" + "🔔" * 35)
        print(" ⏸️  [จุดหยุดที่ 4]: ระบบปฏิเสธเศษหุ้นสำเร็จ!")
        print(" 👉 สังเกตกล่องข้อความ Console: แสดง 'Odd-lot rejected'")
        print(" 👉 กด 'Step over' (F10) เพื่อไปดูแท็บตาราง")
        print("🔔" * 35 + "\n")
        await page.pause()

        # =========================================================================
        # 📍 Step 5: สลับแท็บไปดู Watchlist Triggers
        # =========================================================================
        print("▶️  [Step 5] คลิกสลับแท็บไปที่ 'Watchlist Triggers'...")
        await page.click("#tabTriggersBtn")
        await page.wait_for_timeout(600)

        print("\n" + "🔔" * 35)
        print(" ⏸️  [จุดหยุดที่ 5]: ฝึกใช้ปุ่ม Explore (เป้าเล็ง)!")
        print(" 👉 ในหน้าต่าง Playwright Inspector ให้คลิกปุ่มไอคอน 'Explore' (เป้าเล็ง)")
        print(" 👉 จากนั้นเลื่อนเมาส์ไปชี้แถวในตาราง Watchlist Triggers บนหน้าเว็บ")
        print(" 👉 สังเกตว่า Inspector จะแสดงโค้ด locator เช่น page.locator('...') ให้ทันที!")
        print(" 👉 เมื่อพอใจแล้ว กดปุ่ม Resume (F5) เพื่อสิ้นสุดการทดสอบ")
        print("🔔" * 35 + "\n")
        await page.pause()

        print("\n🎉 จบการฝึกอบรมเรียบร้อยแล้ว ปิดเบราว์เซอร์...")
        await browser.close()
        print("✅ การทดสอบเสร็จสมบูรณ์!")


if __name__ == "__main__":
    asyncio.run(run_tutorial())
