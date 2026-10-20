# -*- coding: utf-8 -*-
"""Reuse the keepalive browser session (no OTP). Connect via CDP to the browser
that `streaming_keepalive.py` left open."""
import asyncio

from playwright.async_api import async_playwright

CDP_URL = "http://127.0.0.1:9333"


async def reuse_page():
    """Return (pw, browser, page) where page is the StreamingPage (or first tab)."""
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(CDP_URL)
    ctx = browser.contexts[0]
    page = None
    for p in ctx.pages:
        if "streamingpage" in p.url.lower():
            page = p
            break
    if page is None:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    return pw, browser, page


if __name__ == "__main__":
    async def _t():
        pw, browser, page = await reuse_page()
        print("page:", page.url)
        body = await page.inner_text("body")
        print("has BCPG order:", "11006664" in body)
        await browser.close()
        await pw.stop()
    asyncio.run(_t())
