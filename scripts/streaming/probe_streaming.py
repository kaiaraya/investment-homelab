# -*- coding: utf-8 -*-
"""Phase 0 probe — Settrade Streaming (streaming.settrade.com) — read-only.

Opens a HEADED Chromium, dumps the login form, PAUSES for the human to log in
(Streaming uses Username + Password + optional 2FA SMS OTP / Streaming Token),
then dumps the post-login trading UI so we can decide reuse-vs-rewrite the driver.

Dumps (7 items, per TASK-loop1-8):
  1. URL / title / branding
  2. login form fields (pre-login)
  3. order ticket: symbol/price/volume inputs + side buttons + submit button
  4. unmatched-orders table rows + cancel + Modify/Change buttons
  5. bid/offer depth elements
  6. account selector + account number/type
  7. XHR endpoints (stock|quote|bid|offer|order|depth)

Never clicks Cancel / Submit / Modify. Saves JSON + screenshot under data/probes/.
"""
import asyncio
import json
import os
import re
from datetime import datetime

from playwright.async_api import async_playwright

from app.core.config import settings

OUT_DIR = "data/probes"
os.makedirs(OUT_DIR, exist_ok=True)
BASE_URL = "https://streaming.settrade.com"


async def snapshot_dom(page, label):
    """Collect the 7 probe items from the current page state."""
    data = await page.evaluate("""() => {
      const txt = (el) => (el.innerText || el.value || '').trim();
      const url = location.href;
      const title = document.title;

      // item 3: order ticket inputs + side buttons + submit
      const inputs = [];
      document.querySelectorAll('input, textarea').forEach(el => {
        const id = el.id || el.name || '';
        if (/(symbol|stock|instrument|price|volume|qty|lot|amount|cost|pin|password)/i.test(id + ' ' + (el.placeholder||'')))
          inputs.push({tag: el.tagName, id: el.id||'', name: el.name||'', type: el.type||'',
                       placeholder: (el.placeholder||'').slice(0,60), visible: el.offsetParent !== null});
      });
      const sideButtons = [];
      document.querySelectorAll('button, a, input[type=button], div[role=button], li, span').forEach(el => {
        const t = txt(el);
        if (/^(buy|sell|short|cover|ซื้อ|ขาย|ขายชอร์ต|cover)$/i.test(t) || /^(buy|sell|short|cover|ซื้อ|ขาย)$/i.test(el.id||''))
          sideButtons.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,60), text: t.slice(0,20)});
      });
      const submitButtons = [];
      document.querySelectorAll('button, a, input[type=button], input[type=submit]').forEach(el => {
        const t = txt(el);
        if (/(send|submit|place|order|confirm|ส่ง|ยืนยัน|ซื้อ|ขาย)/i.test(t + ' ' + (el.id||'')))
          submitButtons.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,80), text: t.slice(0,30)});
      });

      // item 4: table rows + cancel/modify/change buttons
      const rows = [];
      document.querySelectorAll('table tr').forEach(tr => {
        const cells = Array.from(tr.querySelectorAll('td, th')).map(td => txt(td));
        if (cells.length) rows.push(cells.slice(0, 20));
      });
      const actionButtons = [];
      document.querySelectorAll('button, a, input[type=button], i, span, div').forEach(el => {
        const t = txt(el);
        const oc = (el.getAttribute && el.getAttribute('onclick')) || '';
        if (/(cancel|modify|change|ยกเลิก|แก้ไข|เปลี่ยน|แก้)/i.test(t) || /(cancel|modify|change)/i.test(oc))
          actionButtons.push({tag: el.tagName, id: el.id||'', text: t.slice(0,30),
                              onclick: oc.slice(0,200), outer: el.outerHTML.slice(0,300)});
      });

      // item 5: bid/offer depth
      const bidOffer = [];
      document.querySelectorAll('div, span, td, table').forEach(el => {
        const t = txt(el);
        const c = (el.className||'').toString();
        if (/(bid|offer|best bid|best offer)/i.test(t + ' ' + c) && t.length < 60)
          bidOffer.push({tag: el.tagName, cls: c.slice(0,80), text: t.slice(0,60)});
      });

      // item 6: account selector / number
      const account = [];
      document.querySelectorAll('select, option, div, span').forEach(el => {
        const t = txt(el);
        if (/(account|บัญชี|port|portfolio|cash|margin|credit)/i.test(t) && t.length < 60)
          account.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,60), text: t.slice(0,60)});
      });

      // item 2: login form (pre-login only, but harmless to always collect)
      const loginInputs = [];
      document.querySelectorAll('input').forEach(el => {
        const id = (el.id||el.name||'').toLowerCase();
        if (/(user|pass|login|otp|pin|txtlogin|txtpassword|txtuser)/i.test(id + ' ' + (el.placeholder||'')))
          loginInputs.push({tag: el.tagName, id: el.id||'', name: el.name||'', type: el.type||'',
                            placeholder: (el.placeholder||'').slice(0,60)});
      });
      const loginButtons = [];
      document.querySelectorAll('button, a, input[type=button], input[type=submit]').forEach(el => {
        const t = txt(el);
        if (/(login|sign in|continue|submit|enter|เข้าสู่ระบบ|ล็อกอิน|login|otp)/i.test(t))
          loginButtons.push({tag: el.tagName, id: el.id||'', text: t.slice(0,40), outer: el.outerHTML.slice(0,200)});
      });

      return {url, title, inputs, sideButtons, submitButtons, rows: rows.slice(0, 60),
              actionButtons, bidOffer, account, loginInputs, loginButtons,
              bodyText: (document.body ? document.body.innerText.slice(0, 3000) : '')};
    }""")
    data["label"] = label
    data["ts"] = datetime.now().isoformat()
    return data


async def main():
    pw = await async_playwright().start()
    args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx = await browser.new_context(viewport={"width": 1440, "height": 960})
    page = await ctx.new_page()

    net = []
    page.on("response", lambda r: net.append(r.url) if re.search(
        r"stock|quote|bid|offer|order|depth|market|instrument", r.url, re.I) else None)

    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- Stage 1: login form (before login) ---
    pre = await snapshot_dom(page, "PRE_LOGIN")
    pre["network"] = net[-40:]
    print("=== PRE-LOGIN URL:", pre["url"])
    print("=== login inputs:", json.dumps(pre["loginInputs"], ensure_ascii=False, indent=1)[:1500])
    print("=== login buttons:", json.dumps(pre["loginButtons"], ensure_ascii=False, indent=1)[:1500])

    # --- Stage 2: wait for the human to log in (poll for a post-login marker) ---
    print("\n>>> กรุณา login ใน browser ที่เปิดอยู่ (Username + Password + 2FA OTP ถ้าถาม)")
    print(">>> เมื่อเข้า Streaming ได้แล้ว สคริปต์จะจับอัตโนมัติแล้วดัมป์ต่อ ...")
    auth_markers = [
        "#account-select",
        "div.bg-color-account-info-group",
        "a:has-text('ออกจากระบบ')",
        "a:has-text('Logout')",
        "button:has-text('Market')",
    ]
    waited = 0
    authed = False
    try:
        while waited < 300:
            # Primary signal: landed on the Streaming trading page (not login.jsp / SSO)
            if "streamingpage" in page.url.lower():
                authed = True
                break
            for sel in auth_markers:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        authed = True
                        break
                except Exception:
                    pass
            if authed:
                break
            await page.wait_for_timeout(3000)
            waited += 3
            if waited % 30 == 0:
                print(f"   ... รอ login ({waited}s) — URL: {page.url}")
    except Exception as e:
        print(f"\n>>> Browser ถูกปิดระหว่างรอ login ({type(e).__name__}) — ไม่สามารถดัมป์ต่อได้")
        return

    if not authed:
        print(">>> ไม่พบ marker หลัง login ภายใน 300s — ดัมป์สถานะปัจจุบันไปก่อน")
    else:
        print(f">>> ตรวจพบ post-login ({waited}s) — ดัมป์ต่อ")

    await page.wait_for_timeout(3000)

    # --- Stage 3: post-login dump ---
    post = await snapshot_dom(page, "POST_LOGIN")
    post["network"] = net[-60:]
    print("=== POST-LOGIN URL:", post["url"])
    print("=== order inputs:", json.dumps(post["inputs"], ensure_ascii=False, indent=1)[:2000])
    print("=== side buttons:", json.dumps(post["sideButtons"], ensure_ascii=False, indent=1)[:1500])
    print("=== submit buttons:", json.dumps(post["submitButtons"], ensure_ascii=False, indent=1)[:1500])
    print("=== action buttons (cancel/modify/change):", json.dumps(post["actionButtons"], ensure_ascii=False, indent=1)[:2500])
    print("=== bid/offer:", json.dumps(post["bidOffer"], ensure_ascii=False, indent=1)[:1500])
    print("=== account:", json.dumps(post["account"], ensure_ascii=False, indent=1)[:1500])
    print("=== rows:", json.dumps(post["rows"], ensure_ascii=False, indent=1)[:2000])

    out = {stamp: {"pre": pre, "post": post}}
    out_path = os.path.join(OUT_DIR, f"streaming_probe_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    shot = os.path.join(OUT_DIR, f"streaming_probe_{stamp}.png")
    await page.screenshot(path=shot, full_page=True)

    print(f"\nSaved: {out_path}")
    print(f"Shot : {shot}")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
