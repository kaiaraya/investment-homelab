# -*- coding: utf-8 -*-
"""Keepalive — login Krungsri SSO -> Streaming ONCE, keep the browser OPEN and
connectable over CDP so other scripts reuse the session (no OTP).

Launches Chrome MANUALLY with --remote-debugging-port (Playwright's own
launch_persistent_context does NOT expose a working CDP TCP server), then
connect_over_cdp drives the login. The Chrome process stays alive as long as
this script runs.

  PYTHONPATH=. .venv/bin/python scripts/streaming/streaming_keepalive.py

Other scripts:
  from _reuse import reuse_page
  pw, browser, page = await reuse_page()
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.config import settings  # noqa: E402

PROFILE_DIR = os.path.abspath("data/streaming_profile")
CDP_PORT = 9333
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"


def launch_chrome():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    chrome = settings.PLAYWRIGHT_CHROME_EXECUTABLE or "/usr/bin/google-chrome"
    proc = subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1440,960",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=open("data/streaming_chrome.log", "w"),
    )
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2) as r:
                json.load(r)
                return proc
        except Exception:
            time.sleep(1)
    raise RuntimeError("Chrome CDP server did not come up on port 9222")


async def main():
    proc = launch_chrome()
    print(">>> Chrome launched with CDP on", CDP_URL)

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(CDP_URL)
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    u, p = settings.KRUNGSRI_USERNAME, settings.KRUNGSRI_PASSWORD
    await page.goto(settings.KRUNGSRI_LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)
    body = await page.inner_text("body")
    if not any(k in body for k in ["ยินดีต้อนรับ", "creditbalance"]) and "member" not in page.url.lower():
        for sel in ["#login_username", "input[name*='user' i]"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(u); break
        for sel in ["#login_password", "input[name*='pass' i]"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(p); break
        await page.click("#login", timeout=8000)
        print(">>> กด Login (Krungsri) แล้ว — รอ OTP ...")

    waited = 0
    while waited < 300:
        body = await page.inner_text("body")
        if any(k in body for k in ["ยินดีต้อนรับ", "creditbalance"]) or "member" in page.url.lower():
            break
        if waited % 20 == 0:
            print(f"   ... รอ login/OTP ({waited}s) — URL: {page.url}")
        await page.wait_for_timeout(4000)
        waited += 4

    for sel in ["a:has-text('โปรแกรม Streaming')", "a:has-text('Streaming')"]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click(timeout=8000)
            print(">>> คลิก Streaming SSO:", sel)
            break
    else:
        await page.evaluate("popup('../../Put_SSO_Settrade.aspx?Page=streaming','',window.screen.width,window.screen.height)")
    await page.wait_for_timeout(10000)
    for pg in ctx.pages:
        if "settrade" in pg.url.lower() or "streamingpage" in pg.url.lower():
            page = pg
            break
    print(">>> Streaming URL:", page.url)

    try:
        await page.click("span.outline-none:has-text('Equity')", timeout=5000)
        await page.wait_for_timeout(1000)
        await page.click("li:has-text('3024959')", timeout=5000)
        await page.wait_for_timeout(3000)
        print(">>> switched to margin 3024959")
    except Exception as e:
        print(">>> switch note:", type(e).__name__, str(e)[:100])

    print(f"\n=== SESSION READY — keep this running. CDP: {CDP_URL} ===")
    print("   other scripts: from _reuse import reuse_page; pw, browser, page = await reuse_page()")
    await asyncio.Event().wait()  # never close; Chrome subprocess stays alive


if __name__ == "__main__":
    asyncio.run(main())
