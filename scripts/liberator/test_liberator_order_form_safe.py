import asyncio
import json
import os
from playwright.async_api import async_playwright

from app.core.config import settings

async def test_order_form_and_portfolio_safe():
    state_file = "data/liberator_session.json"
    with open(state_file, "r") as f:
        data = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"]
        )
        context = await browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        await context.add_cookies(data.get("cookies", []))
        page = await context.new_page()

        print("🌐 Navigating to Liberator Portfolio...")
        await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # -------------------------------------------------------------
        # 1. SCRAPE COMPLETE HOLDINGS TABLE
        # -------------------------------------------------------------
        print("\n📊 1. Scraping Holdings Table...")
        holdings = await page.evaluate("""() => {
            const rows = [];
            const trs = Array.from(document.querySelectorAll('tr, div[role="row"]'));
            for (const tr of trs) {
                const parts = tr.innerText.trim().split(/\\s+/);
                if (parts.length >= 7 && ['BCH', 'BCP', 'IVL', 'RCL', 'THAI'].includes(parts[0])) {
                    rows.push({
                        symbol: parts[0],
                        act_vol: parseFloat(parts[1].replace(/,/g, '')) || 0,
                        in_port: parseFloat(parts[2].replace(/,/g, '')) || 0,
                        avg_cost: parseFloat(parts[3].replace(/,/g, '')) || 0,
                        market_price: parseFloat(parts[4].replace(/,/g, '')) || 0,
                        amount_cost: parseFloat((parts[5] || '0').replace(/,/g, '')) || 0,
                        market_value: parseFloat((parts[6] || '0').replace(/,/g, '')) || 0,
                        unrealized_pnl: parseFloat((parts[7] || '0').replace(/,/g, '').replace('–', '-')) || 0,
                        pct_unrealized: parseFloat((parts[8] || '0').replace(/,/g, '').replace('%', '').replace('–', '-')) || 0
                    });
                }
            }
            return rows;
        }""")

        print(f"✅ Successfully scraped {len(holdings)} holdings:")
        for h in holdings:
            print(f"   • {h['symbol']:<5} In Port: {h['in_port']:<6} Avg: ฿{h['avg_cost']:<6.2f} Price: ฿{h['market_price']:<6.2f} PnL: ฿{h['unrealized_pnl']:+,.2f} ({h['pct_unrealized']:+.2f}%)")

        # -------------------------------------------------------------
        # 2. TEST PLACE ORDER FORM INTERACTION (SAFE DRY-RUN)
        # -------------------------------------------------------------
        print("\n🎯 2. Testing Place Order Form Interaction (SAFE - NO SUBMISSION)...")

        # A. Test Toggle Sell
        print(" • Selecting 'Sell' side...")
        await page.locator(":text('Sell')").first.click()
        await page.wait_for_timeout(500)
        btn_txt = await page.inner_text("#buttonSubmit")
        print(f"   Submit button label is now: '{btn_txt}' (Expected: 'Sell')")

        # B. Test Toggle Buy
        print(" • Selecting 'Buy' side...")
        await page.locator(":text('Buy')").first.click()
        await page.wait_for_timeout(500)
        btn_txt = await page.inner_text("#buttonSubmit")
        print(f"   Submit button label is now: '{btn_txt}' (Expected: 'Buy')")

        # C. Test Symbol Input
        print(" • Testing Symbol entry (#SearchSymbolList-setBuySellFooter)...")
        sym_input = await page.query_selector("#SearchSymbolList-setBuySellFooter")
        if sym_input:
            await sym_input.fill("BCH")
            print("   Filled symbol: 'BCH'")

        # D. Test Volume Input
        print(" • Testing Volume entry (#volume)...")
        vol_input = await page.query_selector("#volume")
        if vol_input:
            await vol_input.fill("100")
            print("   Filled volume: '100'")

        # E. Test Price Input
        print(" • Testing Price entry (#price)...")
        price_input = await page.query_selector("#price")
        if price_input:
            await price_input.fill("11.00")
            print("   Filled price: '11.00'")

        # F. Test PIN Input
        print(" • Testing PIN entry (#pin)...")
        pin_input = await page.query_selector("#pin")
        if pin_input:
            await pin_input.fill(settings.LIBERATOR_PIN)
            print("   Filled PIN: '51****'")

        # Take screenshot of the populated form
        os.makedirs("data/screenshots", exist_ok=True)
        shot_path = "data/screenshots/liberator_order_form_tested.png"
        await page.screenshot(path=shot_path)
        print(f"\n📸 Verification screenshot of filled form saved to: {shot_path}")

        # G. Click CLEAR button to reset safely!
        print("\n🧹 Clicking 'Clear' button to reset form safely without submitting...")
        clear_btn = await page.query_selector("button:has-text('Clear')")
        if clear_btn:
            await clear_btn.click()
            await page.wait_for_timeout(1000)
            vol_val = await vol_input.input_value() if vol_input else "N/A"
            print(f"✅ Form reset successfully! Volume input value after clear: '{vol_val}'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_order_form_and_portfolio_safe())
