import asyncio
import os
from playwright.async_api import async_playwright

from app.core.config import settings

async def inspect_liberator_post_login():
    if not settings.LIBERATOR_USERNAME or not settings.LIBERATOR_PASSWORD:
        raise SystemExit("Set LIBERATOR_USERNAME and LIBERATOR_PASSWORD in .env")
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
        page = await context.new_page()

        print("Navigating to https://webtrade.liberator.co.th/login...")
        await page.goto("https://webtrade.liberator.co.th/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Fill Username
        u = await page.query_selector("input[placeholder*='Username' i]")
        if u:
            await u.fill(settings.LIBERATOR_USERNAME)
            print("Filled username")

        # Fill Password
        p_el = await page.query_selector("input[placeholder*='Password' i]")
        if p_el:
            await p_el.fill(settings.LIBERATOR_PASSWORD)
            print("Filled password")

        # Click Confirm button
        btn = await page.query_selector("button:has-text('ยืนยัน')")
        if btn:
            await btn.click()
            print("Clicked ยืนยัน")

        # Wait 4 seconds and capture state
        await page.wait_for_timeout(4000)
        print("URL after 4s:", page.url)
        print("Title:", await page.title())

        # Screenshot
        os.makedirs("data/screenshots", exist_ok=True)
        shot = "data/screenshots/liberator_after_login_click.png"
        await page.screenshot(path=shot)
        print("Saved screenshot to", shot)

        # Check DOM text
        body = await page.inner_text("body")
        print("Body text snippet:\n", body[:500])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_liberator_post_login())
