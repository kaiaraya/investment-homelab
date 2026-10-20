# -*- coding: utf-8 -*-
"""Phase 0 auto-login probe — selects KRUNGSRI broker, fills creds from .env,
clicks Login, then dumps whatever comes next (SSO redirect / OTP form / StreamingPage).

Read-only. Headed so the human can complete OTP if 2FA triggers.
Saves the post-login state IMMEDIATELY (before any OTP wait) so we keep the
SSO/OTP form structure even if the window is closed early.
"""
import asyncio
import json
import os
import sys
from datetime import datetime

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_streaming import snapshot_dom  # noqa: E402

from app.core.config import settings  # noqa: E402

OUT_DIR = "data/probes"
os.makedirs(OUT_DIR, exist_ok=True)
BASE = "https://streaming.settrade.com/realtime/streaming-login/login.jsp"


def save(tag, data):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join(OUT_DIR, f"streaming_autologin_{tag}_{stamp}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[saved] {p}")
    return p


async def main():
    pw = await async_playwright().start()
    args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx = await browser.new_context(viewport={"width": 1440, "height": 960})
    page = await ctx.new_page()

    await page.goto(BASE, wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(2000)

    pre = await snapshot_dom(page, "PRE_LOGIN")
    save("pre", pre)
    print("PRE URL:", pre["url"])

    # --- auto-login ---
    u, p = settings.KRUNGSRI_USERNAME, settings.KRUNGSRI_PASSWORD
    if not u or not p:
        print(">>> ไม่มี KRUNGSRI_USERNAME/PASSWORD ใน .env — หยุด (ให้ login มือ)")
        await browser.close()
        return

    try:
        # 1. select broker KRUNGSRI
        await page.click("ng-select input[role='combobox']", timeout=8000)
        await page.wait_for_timeout(800)
        await page.fill("ng-select input[role='combobox']", "KRUNGSRI")
        await page.wait_for_timeout(1000)
        await page.click(".ng-dropdown-panel .ng-option:has-text('KRUNGSRI')", timeout=8000)
        await page.wait_for_timeout(800)

        # 2. fill username / password (robust selectors)
        for sel in ["input[placeholder='Username']", "#usernameInput", "#txtLogin"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(u)
                print(f"filled username via {sel}")
                break
        for sel in ["input[placeholder='Password']", "#txtPassword"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(p)
                print(f"filled password via {sel}")
                break

        # 3. submit
        await page.click("#submitBtn", timeout=8000)
        print(">>> คลิก Login แล้ว — รอดู redirect/SSO/OTP ...")
        await page.wait_for_timeout(9000)
    except Exception as e:
        print(">>> auto-login error:", type(e).__name__, str(e)[:250])

    after = await snapshot_dom(page, "AFTER_LOGIN_CLICK")
    after["url"] = page.url
    save("after_click", after)
    print("POST-LOGIN URL:", page.url)
    print("bodyText head:", (after.get("bodyText") or "")[:800])

    # --- drive 2FA: Continue -> verify option -> SMS OTP -> wait for human OTP ---
    if "twofa" in page.url.lower() or "confirm-device" in page.url.lower():
        try:
            await page.click("button:has-text('Continue')", timeout=8000)
            await page.wait_for_timeout(4000)
            verify = await snapshot_dom(page, "TWOFA_VERIFY_OPTION")
            verify["url"] = page.url
            save("twofa_verify", verify)
            print("TWOFA URL:", page.url)
            print("verify bodyText head:", (verify.get("bodyText") or "")[:1200])
            # click the 'click here' fallback to reveal the SMS OTP option
            for sel in ["a:has-text('click here')", "text=click here",
                        "button:has-text('click here')", "a:has-text('คลิก')"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(timeout=8000)
                    print(f"clicked 'click here' via {sel}")
                    await page.wait_for_timeout(2500)
                    break
            # then click Get SMS OTP
            for sel in ["button:has-text('Get SMS OTP')", "button:has-text('SMS OTP')",
                        "button:has-text('OTP')"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(timeout=8000)
                    print(f"clicked SMS OTP via {sel}")
                    await page.wait_for_timeout(4000)
                    otp = await snapshot_dom(page, "TWOFA_OTP_FORM")
                    otp["url"] = page.url
                    save("twofa_otp", otp)
                    print("OTP URL:", page.url)
                    print("OTP inputs:", json.dumps(otp.get("loginInputs", []), ensure_ascii=False)[:800])
                    break
        except Exception as e:
            print(">>> 2FA drive error:", type(e).__name__, str(e)[:200])

    # --- wait for StreamingPage (human completes OTP if needed) ---
    waited = 0
    authed = False
    try:
        while waited < 180:
            if "streamingpage" in page.url.lower():
                authed = True
                break
            await page.wait_for_timeout(3000)
            waited += 3
            if waited % 30 == 0:
                print(f"   ... รอ StreamingPage ({waited}s) — URL: {page.url}")
    except Exception as e:
        print(f">>> browser ปิดระหว่างรอ ({type(e).__name__})")

    if authed:
        post = await snapshot_dom(page, "POST_LOGIN_STREAMINGPAGE")
        save("streamingpage", post)
        print("=== STREAMING PAGE URL:", post["url"])
        print("=== side buttons:", json.dumps(post["sideButtons"], ensure_ascii=False)[:1200])
        print("=== action buttons:", json.dumps(post["actionButtons"], ensure_ascii=False)[:1500])
        shot = os.path.join(OUT_DIR, f"streaming_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        await page.screenshot(path=shot, full_page=True)
        print("shot:", shot)
    else:
        print(">>> ยังไม่ถึง StreamingPage — ดู after_click JSON (SSO/OTP form) เอา")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
