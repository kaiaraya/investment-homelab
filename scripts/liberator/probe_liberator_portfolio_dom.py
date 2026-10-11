import asyncio
import json
import os
from playwright.async_api import async_playwright

async def probe_portfolio_and_order_form():
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

        print("🌐 Navigating to https://webtrade.liberator.co.th/Portfolio...")
        await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # 1. Probing Balances
        print("\n--- 1. ACCOUNT BALANCES ---")
        line_el = await page.query_selector("*:has-text('Line Available')")
        print("Line Available element visible:", await line_el.is_visible() if line_el else False)

        # Evaluate JavaScript to extract balances cleanly
        balances = await page.evaluate("""() => {
            const text = document.body.innerText;
            const res = {};
            const mLine = text.match(/Line Available:\\s*([\\d,]+\\.?\\d*)/i);
            const mCash = text.match(/Cash Balance:\\s*([\\d,]+\\.?\\d*)/i);
            const mLimit = text.match(/Credit Limit:\\s*([\\d,]+\\.?\\d*)/i);
            if (mLine) res.line_available = mLine[1];
            if (mCash) res.cash_balance = mCash[1];
            if (mLimit) res.credit_limit = mLimit[1];
            return res;
        }""")
        print("Extracted Balances:", balances)

        # 2. Probing Holdings Table
        print("\n--- 2. PORTFOLIO HOLDINGS TABLE ---")
        rows = await page.evaluate("""() => {
            // Find all table rows or grid rows in the Portfolio area
            const results = [];
            const trs = Array.from(document.querySelectorAll('tr, div[role="row"]'));
            for (const tr of trs) {
                const text = tr.innerText.trim();
                const parts = text.split(/\\s+/);
                // Check if row has stock symbols like BCH, BCP, IVL, RCL, THAI
                if (['BCH', 'BCP', 'IVL', 'RCL', 'THAI'].includes(parts[0])) {
                    results.push({
                        raw: text,
                        symbol: parts[0],
                        parts: parts
                    });
                }
            }
            return results;
        }""")
        print(f"Found {len(rows)} matching stock rows in DOM:")
        for r in rows:
            print("  Row:", r)

        # 3. Probing Place Order Form Selectors
        print("\n--- 3. PLACE ORDER FORM SELECTORS ---")
        order_form_info = await page.evaluate("""() => {
            const info = {};
            // Radio buttons
            const radios = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
            info.radios = radios.map(r => ({
                id: r.id,
                name: r.name,
                value: r.value,
                checked: r.checked,
                parent_text: r.parentElement ? r.parentElement.innerText.trim() : ''
            }));

            // Inputs
            const inputs = Array.from(document.querySelectorAll('input'));
            info.inputs = inputs.map(i => ({
                id: i.id,
                name: i.name,
                placeholder: i.placeholder,
                type: i.type,
                value: i.value,
                className: i.className
            }));

            // Buttons
            const buttons = Array.from(document.querySelectorAll('button'));
            info.buttons = buttons.map(b => ({
                id: b.id,
                text: b.innerText.trim(),
                className: b.className
            })).filter(b => b.text && b.text.length < 20);

            return info;
        }""")

        print(f"Detected {len(order_form_info['inputs'])} inputs on page.")
        for inp in order_form_info['inputs']:
            if inp['placeholder'] or 'pin' in inp['className'].lower() or 'vol' in inp['placeholder'].lower():
                print("  Input:", inp)

        print("\nDetected relevant buttons:")
        for btn in order_form_info['buttons']:
            if any(k in btn['text'].lower() for k in ['buy', 'sell', 'clear', 'submit', 'refresh', 'pin']):
                print("  Button:", btn)

        # Screenshot of the active inspected state
        os.makedirs("data/screenshots", exist_ok=True)
        await page.screenshot(path="data/screenshots/liberator_portfolio_inspected.png")
        print("\n📸 Saved inspected screenshot to data/screenshots/liberator_portfolio_inspected.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(probe_portfolio_and_order_form())
