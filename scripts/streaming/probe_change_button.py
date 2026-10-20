# -*- coding: utf-8 -*-
"""Headed full-login probe — capture the COVER BCPG order + the native Change button.

Krungsri SSO (creds + OTP) -> Streaming -> switch margin -> dump order-status rows
and every Change/Modify/Cancel action. Read-only (no submit/cancel/change).
"""
import asyncio
import json
import os
import sys
from datetime import datetime

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.config import settings  # noqa: E402

OUT = "data/probes"
SESSION = "data/streaming_session.json"
os.makedirs(OUT, exist_ok=True)


async def main():
    pw = await async_playwright().start()
    args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx = await browser.new_context(viewport={"width": 1440, "height": 960})
    page = await ctx.new_page()

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
    while waited < 240:
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
    print("Streaming URL:", page.url)
    await ctx.storage_state(path=SESSION)
    print(">>> saved session")

    # switch to margin
    try:
        await page.click("span.outline-none:has-text('Equity')", timeout=5000)
        await page.wait_for_timeout(1000)
        await page.click("li:has-text('3024959')", timeout=5000)
        await page.wait_for_timeout(3000)
        print(">>> switched to margin 3024959")
    except Exception as e:
        print(">>> switch note:", type(e).__name__, str(e)[:120])

    data = await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const rows = [];
      document.querySelectorAll('tr, div').forEach(el => {
        const t = txt(el);
        if (/\\bBCPG\\b/i.test(t) && /\\d{6,}/.test(t))
          rows.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,60),
                     text: t.slice(0, 220), outer: el.outerHTML.slice(0, 700)});
      });
      const actions = [];
      document.querySelectorAll('button, a, span, div, i, img, td').forEach(el => {
        const t = txt(el);
        const oc = (el.getAttribute && el.getAttribute('onclick'))||'';
        if (/(change|modify|แก้|เปลี่ยน|แก้ไข|cancel|ยกเลิก)/i.test(t + ' ' + oc) && t.length < 25)
          actions.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,70),
                        text: t, onclick: oc.slice(0,200), outer: el.outerHTML.slice(0,300)});
      });
      return {url: location.href, rowCount: rows.length, rows, actions,
              bodyText: (document.body ? document.body.innerText : '').slice(0, 2500)};
    }""")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join(OUT, f"streaming_change_btn_{stamp}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("=== order rows (BCPG) ===", data["rowCount"])
    for r in data["rows"][:10]:
        print(json.dumps(r, ensure_ascii=False))
    print("=== change/modify/cancel actions ===")
    for a in data["actions"]:
        print(json.dumps(a, ensure_ascii=False))
    print("\n=== bodyText (order area) ===")
    print(data["bodyText"])
    print("\nSaved:", p)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
