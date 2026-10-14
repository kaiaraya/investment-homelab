"""
Headed Session Refresher and Cookie Exporter for Krungsri Securities
===================================================================
1. Launches headed Chrome on DISPLAY=:0 with existing data/session_state.json
2. Opens Krungsri Member Portal (https://www.krungsrisecurities.com/th/main/default.aspx)
3. Waits for user to log in or refresh the page
4. Detects logged-in state or waits for user to press ENTER in terminal
5. Saves the fresh session cookies to data/session_state.json
6. Verifies Quick Trade SSO access
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DISPLAY", ":0")

SESSION_FILE = os.path.join(PROJECT_ROOT, "data", "session_state.json")

async def main():
    print("=" * 60)
    print("🔑 Krungsri Session Refresher (Headed)")
    print("=" * 60)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        executable_path="/usr/bin/google-chrome",
        args=["--no-sandbox", "--disable-popup-blocking", "--window-size=1400,950"]
    )
    
    storage_arg = {"storage_state": SESSION_FILE} if os.path.exists(SESSION_FILE) else {}
    context = await browser.new_context(
        **storage_arg,
        viewport={"width": 1380, "height": 900}
    )

    page = await context.new_page()
    print("🌐 Opening Krungsri Portal: https://www.krungsrisecurities.com/th/main/default.aspx ...")
    await page.goto("https://www.krungsrisecurities.com/th/main/default.aspx", wait_until="domcontentloaded")

    print("\n👉 กรุณาดูที่หน้าจอเบราว์เซอร์:")
    print("   กรุณากรอก Username / Password และเข้าสู่ระบบบนหน้าจอ Chrome ที่เปิดขึ้นมา")

    # Monitor for login indicators or wait up to 120 seconds
    logged_in = False
    for sec in range(120):
        try:
            # Check if login form is still present
            has_login_box = await page.evaluate("() => !!document.querySelector('#txtUsername, input[name*=\"Username\"], input[name*=\"user\" i]')")
            has_user_info = await page.evaluate("() => !!document.querySelector('#lblUser, #lblAccount, a[href*=\"Logout\" i], a[href*=\"logout\" i]') || document.body.innerText.includes('ออกจากระบบ')")
            
            if not has_login_box and has_user_info:
                logged_in = True
                print(f"🎉 ตรวจพบการเข้าสู่ระบบสำเร็จบนหน้าจอ! (วินาทีที่ {sec})")
                break
            elif sec % 10 == 0:
                print(f"⏳ กำลังรอคุณ Login บนหน้าจอ... ({sec}/120 วินาที)")
        except Exception:
            pass
        await asyncio.sleep(1)

    if logged_in:
        print("💾 กำลังบันทึก Session cookies ลง data/session_state.json...")
        await context.storage_state(path=SESSION_FILE)
        print("✅ บันทึก Session สำเร็จเรียบร้อย!")

        # Test Quick Trade SSO
        print("🌐 ทดสอบเปิด Quick Trade ผ่าน SSO...")
        qt_page = await context.new_page()
        await qt_page.goto("https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=place_order", wait_until="domcontentloaded")
        await qt_page.wait_for_timeout(3000)
        print(f"📍 Quick Trade Page URL: {qt_page.url[:80]}...")
        if "fastorder" in qt_page.url or "settrade" in qt_page.url:
            print("🚀 Quick Trade SSO ใช้งานได้สมบูรณ์แบบ!")
            # Re-save with Settrade cookies included
            await context.storage_state(path=SESSION_FILE)
            print("💾 อัปเดต data/session_state.json ครบทั้ง Krungsri และ Settrade เรียบร้อย")
            await qt_page.wait_for_timeout(5000)
    else:
        print("⚠️ หมดเวลารอ หรือยังไม่พบสถานะ Login")

    await browser.close()
    await pw.stop()

if __name__ == "__main__":
    asyncio.run(main())
