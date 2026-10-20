# -*- coding: utf-8 -*-
"""Finish session setup: navigate directly to the Streaming SSO endpoint
(no menu-hover needed), then switch to margin. Browser stays open after."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _reuse import reuse_page  # noqa: E402

SSO_URL = "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming"


async def main():
    pw, browser, page = await reuse_page()
    print("start page:", page.url)

    if "streamingpage" not in page.url.lower():
        # open SSO in a NEW tab (popup-like) so the member portal stays put
        ctx = browser.contexts[0]
        page2 = await ctx.new_page()
        await page2.goto(SSO_URL, wait_until="domcontentloaded", timeout=45000)
        print(">>> SSO nav ->", page2.url)
        # wait for the Streaming page to appear (SSO may chain redirects / new tabs)
        for _ in range(30):
            await page2.wait_for_timeout(2000)
            for pg in ctx.pages:
                if "streamingpage" in pg.url.lower() or "settrade" in pg.url.lower():
                    page = pg
                    break
            if "streamingpage" in page.url.lower():
                break
    print("streaming page:", page.url)

    # switch to margin
    try:
        await page.click("span.outline-none:has-text('Equity')", timeout=5000)
        await page.wait_for_timeout(1000)
        await page.click("li:has-text('3024959')", timeout=5000)
        await page.wait_for_timeout(3000)
        print(">>> switched to margin 3024959")
    except Exception as e:
        print(">>> switch note:", type(e).__name__, str(e)[:100])

    body = await page.inner_text("body")
    print("account 3024959:", "3024959" in body)
    print("BCPG order present:", "11006664" in body)
    print("Change button present:", "Change" in body)
    print("\n=== SESSION READY (browser stays open on :9333) ===")
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
