"""
Diagnose which row-scoped locator strategy actually resolves the Liberator "Change"
control of a resting order.  READ-ONLY: nothing is clicked or submitted.

Why: probe_order_change_ui.py reported ``matches=0`` for
    tr(filter has_text=rb"\b11894\b") >> "td:last-child div.cursor-pointer" (filter ^Change$)
so we must find the strategy that works empirically instead of guessing.

Usage:
    .venv/bin/python scripts/liberator/diag_change_locator.py [order_no]
"""

import asyncio
import json
import re
import sys

from playwright.async_api import async_playwright

STATE_FILE = "data/liberator_session.json"
PORTFOLIO_URL = "https://webtrade.liberator.co.th/Portfolio"


async def main():
    order_no = sys.argv[1] if len(sys.argv) > 1 else "11894"

    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"],
        )
        context = await browser.new_context(no_viewport=True)
        await context.add_cookies(state.get("cookies", []))
        page = await context.new_page()
        await page.goto(PORTFOLIO_URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4500)
        print(f"URL: {page.url}")

        rows = page.locator("#OrderTableList tbody tr")
        print(f"\n[1] rows total                       : {await rows.count()}")

        by_str = rows.filter(has_text=order_no)
        print(f"[2] rows filter(has_text='{order_no}')  : {await by_str.count()}")

        by_re = rows.filter(has_text=re.compile(rf"\b{re.escape(order_no)}\b"))
        print(f"[3] rows filter(has_text=r'\\b{order_no}\\b'): {await by_re.count()}")

        r = (by_str.first if await by_str.count() else rows.first)
        print(f"[4] row textContent                  : {(await r.text_content())[:120]!r}")

        for sel in ["td", "td:last-child", "td:nth-last-of-type(1)", "> td", "div.cursor-pointer",
                    "td:last-child div.cursor-pointer", "td:last-child > div",
                    "td:last-child div", "td:nth-child(12)", "td:nth-child(11)"]:
            try:
                print(f"[5] row.locator({sel!r}).count() = {await r.locator(sel).count()}")
            except Exception as e:
                print(f"[5] row.locator({sel!r}) ERR {e}")

        try:
            print(f"[6] last-td div inner texts        : {await r.locator('td:last-child div.cursor-pointer').all_inner_texts()}")
        except Exception as e:
            print(f"[6] ERR {e}")

        print("\n[7] STRATEGY MATRIX (count must be >=1)")
        strategies = {
            "A td:last-child div.cursor-pointer | filter has_text 'Change' (str)":
                r.locator("td:last-child div.cursor-pointer").filter(has_text="Change"),
            "B td:last-child div.cursor-pointer | filter has_text ^Change$ (re)":
                r.locator("td:last-child div.cursor-pointer").filter(has_text=re.compile(r"^Change$")),
            "C td:last-child div.cursor-pointer | filter has_text ^\\s*Change\\s*$ (re)":
                r.locator("td:last-child div.cursor-pointer").filter(has_text=re.compile(r"^\s*Change\s*$")),
            "D div.cursor-pointer | filter has_text 'Change'":
                r.locator("div.cursor-pointer").filter(has_text="Change"),
            "E text-is selector":
                r.locator('div:text-is("Change")'),
            "F text= selector":
                r.locator("text=Change"),
            "G get_by_text exact":
                r.get_by_text("Change", exact=True),
            "H xpath normalize-space":
                r.locator("xpath=.//div[normalize-space(text())='Change']"),
            "I nth index":
                r.locator("td:last-child div.cursor-pointer").nth(0),
        }
        for name, loc in strategies.items():
            try:
                print(f"    {name:<62} -> count={await loc.count()}")
            except Exception as e:
                print(f"    {name:<62} -> ERR {type(e).__name__}: {str(e)[:90]}")

        print("\n[8] Pick first visible 'Change' among all strategies")
        for name, loc in strategies.items():
            try:
                n = await loc.count()
                if n:
                    first = loc.first
                    print(f"    VISIBLE via {name}: text={await first.text_content()!r} "
                          f"box={await first.bounding_box()}")
                    break
            except Exception as e:
                print(f"    {name} ERR {type(e).__name__}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
