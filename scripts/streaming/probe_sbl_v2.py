# -*- coding: utf-8 -*-
"""Phase 1.5 probe v2 — margin account switch + SBL/Short/Cover + Change order.

Improvements over v1:
  * SAVES storage_state to data/streaming_session.json after login, and
    --resume reuses it (no OTP on rerun).
  * Correct account-dropdown selector (span.outline-none) — v1 used the
    Click2Win selector which does not exist on the live Streaming console.
  * After switching to margin 3024959, dumps SBL/Short/Cover + order-status actions.

Read-only (no submit/cancel/change). Save stages to data/probes/.
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
SESSION = "data/streaming_session.json"
STREAMING_URL = settings.STREAMING_URL
os.makedirs(OUT_DIR, exist_ok=True)
RESUME = "--resume" in sys.argv


def save(tag, data):
    p = os.path.join(OUT_DIR, f"streaming_sblv2_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[saved] {p}")


async def dump_accounts(page):
    return await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const acc = [];
      document.querySelectorAll('span.outline-none, span[tabindex], div.cursor-pointer, option, li').forEach(el => {
        const t = txt(el);
        if (/(302495|Equity|Derivatives|Margin|Cash|Credit|TFEX)/i.test(t) && t.length < 60)
          acc.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,80),
                    text: t, outer: el.outerHTML.slice(0,300)});
      });
      return {accounts: acc};
    }""")


async def dump_tabs(page):
    return await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const tabs = [];
      document.querySelectorAll('div, span, a, button, li, label').forEach(el => {
        const t = txt(el);
        if (/(sbl|short|cover|borrow|ยืม|ขายชอร์ต|change|modify|แก้|เปลี่ยน|order|status|สถานะ)/i.test(t) && t.length < 30)
          tabs.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,70), text: t});
      });
      return {url: location.href, tabs};
    }""")


async def login_full(pw):
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
            await el.click(timeout=8000); print(">>> คลิก Streaming SSO"); break
    else:
        await page.evaluate("popup('../../Put_SSO_Settrade.aspx?Page=streaming','',window.screen.width,window.screen.height)")
    await page.wait_for_timeout(10000)
    for pg in ctx.pages:
        if "settrade" in pg.url.lower() or "streamingpage" in pg.url.lower():
            page = pg; break
    return browser, ctx, page


async def main():
    pw = await async_playwright().start()
    if RESUME and os.path.exists(SESSION):
        args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
            args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
        browser = await pw.chromium.launch(**args)
        ctx = await browser.new_context(storage_state=SESSION, viewport={"width": 1440, "height": 960})
        page = await ctx.new_page()
        await page.goto(STREAMING_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(6000)
        print(">>> resume session ->", page.url)
    else:
        browser, ctx, page = await login_full(pw)
        # persist session so reruns skip OTP
        await ctx.storage_state(path=SESSION)
        print(">>> saved storage_state ->", SESSION)

    acc = await dump_accounts(page)
    save("accounts", acc)
    print("=== accounts (pre-switch) ===")
    for a in acc["accounts"]:
        print(json.dumps(a, ensure_ascii=False))

    # switch account -> margin 3024959
    for sel in ["span.outline-none:has-text('3024952')", "span.outline-none:has-text('Equity')",
                "div.cursor-pointer:has-text('3024952')"]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click(timeout=6000)
            print(">>> opened account dropdown via", sel)
            await page.wait_for_timeout(1500)
            break
    acc2 = await dump_accounts(page)
    save("accounts_dropdown", acc2)
    print("=== accounts (dropdown) ===")
    for a in acc2["accounts"]:
        print(json.dumps(a, ensure_ascii=False))
    for sel in ["li:has-text('3024959')", "span:has-text('3024959')", "div:has-text('3024959')",
                "text=3024959"]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click(timeout=6000)
            print(">>> switched to margin via", sel)
            await page.wait_for_timeout(4000)
            break
    acc3 = await dump_accounts(page)
    save("accounts_after", acc3)
    print("=== accounts (after switch) ===")
    for a in acc3["accounts"]:
        print(json.dumps(a, ensure_ascii=False))

    tabs = await dump_tabs(page)
    save("tabs", tabs)
    print("=== tabs (sbl/short/cover/change/order) ===")
    for t in tabs["tabs"]:
        print(json.dumps(t, ensure_ascii=False))

    # click SBL if present
    for t in tabs["tabs"]:
        if "sbl" in t["text"].lower() or "ยืม" in t["text"] or "borrow" in t["text"].lower():
            try:
                await page.click(f"text={t['text']}", timeout=6000)
                print(">>> คลิก SBL:", t["text"])
                await page.wait_for_timeout(4000)
                snap = await snapshot_dom(page, "SBL_TAB")
                save("sbl_tab", snap)
                print("=== SBL sideButtons:", json.dumps(snap["sideButtons"], ensure_ascii=False)[:900])
                print("=== SBL inputs:", json.dumps(snap["inputs"], ensure_ascii=False)[:900])
                print("=== SBL submit:", json.dumps(snap["submitButtons"], ensure_ascii=False)[:900])
                break
            except Exception as e:
                print(">>> SBL click:", type(e).__name__, str(e)[:120])

    shot = os.path.join(OUT_DIR, f"streaming_sblv2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    await page.screenshot(path=shot, full_page=True)
    print("shot:", shot)
    # keep session saved on exit too (in case of further nav)
    await ctx.storage_state(path=SESSION)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
