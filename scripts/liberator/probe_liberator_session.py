import asyncio
import os
import json
from playwright.async_api import async_playwright

async def probe_liberator_session():
    state_file = "data/liberator_session.json"
    if not os.path.exists(state_file):
        print("❌ No data/liberator_session.json found!")
        return

    with open(state_file, "r") as f:
        data = json.load(f)

    cookies = data.get("cookies", [])
    print(f"📦 Loaded {len(cookies)} cookies from {state_file}")

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
        await context.add_cookies(cookies)
        page = await context.new_page()

        print("🌐 Navigating to https://webtrade.liberator.co.th/Portfolio...")
        try:
            await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            print(f"📍 Current URL: {page.url}")
            print(f"📄 Page Title: {await page.title()}")

            # Check if redirected to login
            if "login" in page.url.lower():
                print("⚠️ Session expired (redirected to login page).")
            else:
                print("🎉 Session is still VALID! Landed on:", page.url)

            # Take screenshot
            os.makedirs("data/screenshots", exist_ok=True)
            shot_path = "data/screenshots/liberator_session_probe.png"
            await page.screenshot(path=shot_path)
            print(f"📸 Screenshot saved to {shot_path}")

        except Exception as e:
            print(f"❌ Error during probe: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(probe_liberator_session())
