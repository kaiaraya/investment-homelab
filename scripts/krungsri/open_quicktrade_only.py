"""
Launcher script to open Krungsri Quick Trade in headed Chrome.
Stays open until the user closes the window.
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
    if not os.path.exists(SESSION_FILE):
        print(f"Error: {SESSION_FILE} not found.")
        return 1

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        executable_path="/usr/bin/google-chrome",
        args=["--no-sandbox", "--disable-popup-blocking", "--window-size=1560,980"]
    )
    context = await browser.new_context(
        storage_state=SESSION_FILE,
        viewport={"width": 1500, "height": 920}
    )

    page = await context.new_page()
    await page.goto(
        "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=place_order",
        wait_until="domcontentloaded",
        timeout=45000
    )

    print("Quick Trade is open on screen! It will stay open until you close the browser.")
    while True:
        alive = [p for p in context.pages if not p.is_closed()]
        if not alive:
            break
        await asyncio.sleep(2)

    await browser.close()
    await pw.stop()
    return 0

if __name__ == "__main__":
    asyncio.run(main())
