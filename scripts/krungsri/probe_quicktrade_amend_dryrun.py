"""
Live Observable Test: Krungsri Quick Trade Amend Price DRY-RUN
==============================================================
Headed browser test on DISPLAY=:0:
1. Opens Quick Trade SSO session
2. Navigates to Settrade Order Detail for account 3024959 (order 11008198)
3. Clicks "Change Price& Volume"
4. Fills in new Price (29.50) and PIN (from settings)
5. Takes screenshot to data/screenshots/quicktrade_amend_dryrun.png
6. DOES NOT click Submit (dry-run guaranteed)
7. Waits 10 seconds for user to visually inspect on screen
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DISPLAY", ":0")

from app.core.config import settings

BKK = timezone(timedelta(hours=7))
SESSION_FILE = os.path.join(PROJECT_ROOT, "data", "session_state.json")
SCREENSHOT_PATH = os.path.join(PROJECT_ROOT, "data", "screenshots", "quicktrade_amend_dryrun.png")

ORDER_NO = "11008198"
ACCOUNT_NO = "3024959"
TARGET_PRICE = "29.50"


async def main():
    print("=" * 60)
    print("🚀 Starting Quick Trade Amend Price Headed DRY-RUN Test")
    print(f"📍 Account: {ACCOUNT_NO} | Order No: {ORDER_NO} | Target Price: {TARGET_PRICE}")
    print("=" * 60)

    if not os.path.exists(SESSION_FILE):
        print(f"❌ Session file not found at {SESSION_FILE}")
        return

    trade_date = datetime.now(BKK).strftime("%Y-%m-%d")
    detail_url = (
        f"https://app.settrade.com/order-status-detail/"
        f"?brokerId=029&accountNo={ACCOUNT_NO}&orderNo={ORDER_NO}&tradeDate={trade_date}"
    )

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        executable_path="/usr/bin/google-chrome",
        args=["--no-sandbox", "--disable-popup-blocking", "--window-size=1280,900"]
    )
    context = await browser.new_context(
        storage_state=SESSION_FILE,
        viewport={"width": 1280, "height": 900}
    )

    try:
        page = await context.new_page()
        
        # 1. Warm up session via SSO place_order
        print("🌐 Step 1: Navigating to Quick Trade SSO...")
        await page.goto("https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=place_order", wait_until="domcontentloaded", timeout=45000)
        for _ in range(20):
            if "fastorder" in page.url or ("settrade" in page.url and "sso" not in page.url and "oauth" not in page.url):
                break
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(3000)
        print(f"✅ Reached: {page.url[:80]}...")

        # 2. Open Order Detail directly
        print(f"🌐 Step 2: Opening Order Detail: {detail_url}")
        detail_page = await context.new_page()
        await detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=45000)
        await detail_page.wait_for_timeout(3000)

        # 3. Check for "Change Price& Volume" button
        print("🔍 Step 3: Looking for 'Change Price& Volume' button...")
        change_btn = detail_page.locator("button:has-text('Change Price& Volume')")
        btn_count = await change_btn.count()
        if btn_count == 0:
            print("⚠️ Button 'Change Price& Volume' not found. Checking all buttons on page:")
            btns = await detail_page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim())")
            print(f"   Available buttons: {btns}")
        else:
            print("🔘 Clicking 'Change Price& Volume'...")
            await change_btn.first.click()
            await detail_page.wait_for_timeout(2000)

            # 4. Fill Price and PIN using Angular formcontrolname
            print(f"✍️ Step 4: Staging Price = {TARGET_PRICE} and PIN...")
            price_sel = "input[formcontrolname='price'], input[name='price']"
            price_input = detail_page.locator(price_sel)
            if await price_input.count() > 0:
                await price_input.first.fill(TARGET_PRICE)
                print(f"   ✅ Successfully filled Price = {TARGET_PRICE} into {price_sel}")
            else:
                print("⚠️ Price input not found")

            pin_sel = "input[placeholder='PIN'], input[type='password'], input[name='pin']"
            pin_input = detail_page.locator(pin_sel)
            if await pin_input.count() > 0:
                pin_val = settings.KRUNGSRI_PIN or "123456"
                await pin_input.first.fill(pin_val)
                print(f"   ✅ Successfully filled PIN into {pin_sel}")
            else:
                print("⚠️ PIN input not found")

            # Verify on-screen filled values
            val_check = await detail_page.evaluate('''() => {
                const p = document.querySelector("input[formcontrolname='price']");
                const v = document.querySelector("input[formcontrolname='vol']");
                const pin = document.querySelector("input[type='password']");
                return {
                    price: p ? p.value : null,
                    vol: v ? v.value : null,
                    pin_filled: pin ? pin.value.length > 0 : false
                };
            }''')
            print(f"📊 Verified staged values on modal: Price={val_check['price']}, Vol={val_check['vol']}, PIN_filled={val_check['pin_filled']}")

            # 5. Capture Screenshot
            await detail_page.screenshot(path=SCREENSHOT_PATH)
            print(f"📸 Screenshot saved: {SCREENSHOT_PATH}")
            print("🛑 DRY-RUN GUARANTEE: Submit button will NOT be clicked.")

            # 5. Capture Screenshot
            await detail_page.screenshot(path=SCREENSHOT_PATH)
            print(f"📸 Screenshot saved: {SCREENSHOT_PATH}")
            print("🛑 DRY-RUN GUARANTEE: Submit button will NOT be clicked.")

        # 6. Keep display visible for inspection
        print("👀 Keeping browser open for 12 seconds so you can see it on screen...")
        await detail_page.wait_for_timeout(12000)

    finally:
        await context.close()
        await browser.close()
        await pw.stop()
        print("🏁 Test run finished.")


if __name__ == "__main__":
    asyncio.run(main())
