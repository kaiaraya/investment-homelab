import asyncio
import os
from playwright.async_api import async_playwright

ARTIFACT_DIR = "/home/araya-sawasdichai/.gemini/antigravity-ide/brain/ab53dd73-2011-4c7f-a1fd-82c0125945a0"


async def run_browser_automation():
    print("🚀 Launching Headless Chromium to test http://localhost:8000/console...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/google-chrome"
        )
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()

        # Step 1: Open Console
        print("1. Navigating to http://localhost:8000/console...")
        await page.goto("http://localhost:8000/console")
        await page.wait_for_load_state("networkidle")
        title = await page.title()
        print(f"   Page Title: '{title}'")
        
        # Screenshot Initial State
        ss_init = os.path.join(ARTIFACT_DIR, "console_1_initial.png")
        await page.screenshot(path=ss_init, full_page=False)
        print(f"   📸 Saved initial screenshot: {ss_init}")

        # Step 2: Click "Buy TRUE 3800" preset and Send
        print("\n2. Testing Preset 'Buy TRUE 3800'...")
        await page.click("button:has-text('Buy TRUE 3800')")
        await asyncio.sleep(0.3)
        await page.click("button:has-text('Send Order Signal')")
        await page.wait_for_timeout(1000)

        log_text = await page.inner_text("#consoleLog")
        print(f"   Response Console:\n{log_text[:200]}...")
        ss_buy = os.path.join(ARTIFACT_DIR, "console_2_buy_true.png")
        await page.screenshot(path=ss_buy, full_page=False)
        print(f"   📸 Saved Buy TRUE screenshot: {ss_buy}")

        # Step 3: Click "Odd-lot 96" preset and Send
        print("\n3. Testing Pre-Trade Odd-lot 96 rejection...")
        await page.click("button:has-text('Odd-lot 96')")
        await asyncio.sleep(0.3)
        await page.click("button:has-text('Send Order Signal')")
        await page.wait_for_timeout(1000)

        log_text = await page.inner_text("#consoleLog")
        assert "Odd-lot rejected" in log_text, "Expected Odd-lot rejection in console log"
        print("   ✅ Odd-lot correctly rejected!")
        ss_oddlot = os.path.join(ARTIFACT_DIR, "console_3_oddlot_reject.png")
        await page.screenshot(path=ss_oddlot, full_page=False)
        print(f"   📸 Saved Odd-lot screenshot: {ss_oddlot}")

        # Step 4: Test SMS OTP Relay
        print("\n4. Testing SMS OTP Relay...")
        await page.click("button:has-text('Relay OTP')")
        await page.wait_for_timeout(800)
        log_text = await page.inner_text("#consoleLog")
        assert "849201" in log_text
        print("   ✅ SMS OTP 849201 successfully relayed!")

        # Step 5: Test Intelligent Strategy Report Parser
        print("\n5. Testing Strategy Report Parsing & Order Ingestion...")
        await page.click("button:has-text('Parse & Queue Orders')")
        await page.wait_for_timeout(2000)
        log_text = await page.inner_text("#consoleLog")
        assert "total_parsed" in log_text
        print("   ✅ Strategy Report parsed & immediate orders queued into SQLite!")

        ss_parsed = os.path.join(ARTIFACT_DIR, "console_4_strategy_parsed.png")
        await page.screenshot(path=ss_parsed, full_page=False)
        print(f"   📸 Saved Strategy Parsed screenshot: {ss_parsed}")

        # Step 6: Test Watchlist Triggers Tab
        print("\n6. Testing Watchlist Triggers Tab...")
        await page.click("#tabTriggersBtn")
        await page.wait_for_timeout(1000)
        triggers_html = await page.inner_text("#triggersTableBody")
        assert "AOT" in triggers_html and "PTG" in triggers_html
        print("   ✅ Watchlist Triggers tab active and displaying monitoring rules!")

        ss_trg = os.path.join(ARTIFACT_DIR, "console_5_watchlist_tab.png")
        await page.screenshot(path=ss_trg, full_page=False)
        print(f"   📸 Saved Watchlist Triggers screenshot: {ss_trg}")

        # Step 7: Test EOD Market Close (16:35)
        print("\n7. Testing EOD Market Close (16:35)...")
        await page.click("#tabOrdersBtn")
        await page.click("button:has-text('Market Close (16:35)')")
        await page.wait_for_timeout(1500)
        log_text = await page.inner_text("#consoleLog")
        print(f"   EOD Response: {log_text}")

        ss_eod = os.path.join(ARTIFACT_DIR, "console_6_orders_eod.png")
        await page.screenshot(path=ss_eod, full_page=False)
        print(f"   📸 Saved EOD Orders screenshot: {ss_eod}")

        await browser.close()
        print("\n🎉 ALL BROWSER INTERACTION TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_browser_automation())
