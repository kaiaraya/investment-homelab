# -*- coding: utf-8 -*-
"""Phase 1.5 probe — Streaming margin account + SBL tab (Short/Cover) + Change order.

After Krungsri SSO -> StreamingPage:
  1. dump the account selector (find margin 3024959 + how to switch)
  2. list every tab/button (find SBL / Short / Cover entry point)
  3. click SBL tab, dump the Short/Cover order form
  4. open Order Status, dump row actions (look for native Change/Modify)

Read-only (no order submit / cancel / change). Saves each stage to data/probes/.
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


def save(tag, data):
    p = os.path.join(OUT_DIR, f"streaming_sbl_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[saved] {p}")


async def dump_tabs_buttons(page):
    return await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const tabs = [];
      document.querySelectorAll('div, span, a, button, li, label').forEach(el => {
        const t = txt(el);
        if (/(sbl|short|cover|buy|sell|change|modify|แก้|เปลี่ยน|order|คำสั่ง|status|สถานะ|borrow|ยืม)/i.test(t) && t.length < 30)
          tabs.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,70), text: t});
      });
      return {url: location.href, tabs};
    }""")


async def dump_accounts(page):
    return await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const acc = [];
      document.querySelectorAll('span[tabindex="0"], select, option, div').forEach(el => {
        const t = txt(el);
        if (/302495|Equity|Derivatives|Margin|Cash|Credit/i.test(t) && t.length < 60)
          acc.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,70), text: t});
      });
      return {accounts: acc};
    }""")


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
        try:
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
        except Exception as e:
            print(">>> login fill error:", type(e).__name__, str(e)[:150])

    # wait for member portal
    waited = 0
    while waited < 240:
        body = await page.inner_text("body")
        if any(k in body for k in ["ยินดีต้อนรับ", "creditbalance"]) or "member" in page.url.lower():
            break
        if waited % 20 == 0:
            print(f"   ... รอ login/OTP ({waited}s) — URL: {page.url}")
        await page.wait_for_timeout(4000)
        waited += 4

    # click Streaming SSO
    stream_clicked = False
    for sel in ["a:has-text('โปรแกรม Streaming')", "a:has-text('Streaming')"]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click(timeout=8000)
            print(">>> คลิก Streaming SSO:", sel)
            stream_clicked = True
            break
    if not stream_clicked:
        await page.evaluate("popup('../../Put_SSO_Settrade.aspx?Page=streaming','',window.screen.width,window.screen.height)")
        stream_clicked = True
    await page.wait_for_timeout(10000)

    # find the Streaming page (popup or same tab)
    for pg in ctx.pages:
        if "settrade" in pg.url.lower() or "streamingpage" in pg.url.lower():
            page = pg
            print(">>> Streaming page:", pg.url)
            break

    acc = await dump_accounts(page)
    save("accounts", acc)
    print("=== accounts ===")
    print(json.dumps(acc, ensure_ascii=False, indent=1)[:2000])

    # switch to margin if a selector is present (best-effort, read-only nav)
    try:
        await page.click("div.bg-color-account-info-group span[tabindex='0']", timeout=5000)
        await page.wait_for_timeout(1500)
        acc2 = await dump_accounts(page)
        save("accounts_open", acc2)
        print("=== accounts (dropdown open) ===")
        print(json.dumps(acc2, ensure_ascii=False, indent=1)[:2500])
        # try click margin option
        for sel in ["div:has-text('3024959')", "text=3024959", "span:has-text('3024959')"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=5000)
                print(">>> switched to margin via", sel)
                await page.wait_for_timeout(3000)
                break
    except Exception as e:
        print(">>> account dropdown:", type(e).__name__, str(e)[:120])

    tabs = await dump_tabs_buttons(page)
    save("tabs", tabs)
    print("=== tabs/buttons (sbl/short/cover/change/order) ===")
    for t in tabs["tabs"]:
        print(json.dumps(t, ensure_ascii=False))

    # click SBL tab if found
    for t in tabs["tabs"]:
        if "sbl" in t["text"].lower():
            try:
                await page.click(f"text={t['text']}", timeout=6000)
                print(">>> คลิก SBL:", t["text"])
                await page.wait_for_timeout(4000)
                snap = await snapshot_dom(page, "SBL_TAB")
                save("sbl_tab", snap)
                print("=== SBL side buttons:", json.dumps(snap["sideButtons"], ensure_ascii=False)[:800])
                print("=== SBL inputs:", json.dumps(snap["inputs"], ensure_ascii=False)[:800])
                print("=== SBL submit:", json.dumps(snap["submitButtons"], ensure_ascii=False)[:800])
                break
            except Exception as e:
                print(">>> SBL click:", type(e).__name__, str(e)[:120])

    shot = os.path.join(OUT_DIR, f"streaming_sbl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    await page.screenshot(path=shot, full_page=True)
    print("shot:", shot)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
