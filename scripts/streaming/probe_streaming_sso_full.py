# -*- coding: utf-8 -*-
"""Phase 0 definitive probe — Krungsri SSO → Settrade Streaming (end-to-end).

1. Open headed Chromium (fresh).
2. Krungsri portal login: auto-fill #login_username / #login_password, submit.
3. Wait for OTP (human types the SMS code in the window), then the member portal.
4. Dump every SSO link (start_SSO.aspx?page=XX) to find the Streaming code.
5. Click the Streaming SSO link (not page=TM) -> land on streaming.settrade.com.
6. Full trading-UI snapshot (order ticket / unmatched / Modify / bid-offer).

Read-only (no orders). Saves each stage to data/probes/.
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
    p = os.path.join(OUT_DIR, f"sso_streaming_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[saved] {p}")
    return p


async def dump_ssos(page):
    return await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const ssos = [];
      document.querySelectorAll('a').forEach(el => {
        const href = el.getAttribute('href')||'';
        const oc = el.getAttribute('onclick')||'';
        if (/start_SSO|start_sso|sso|popup\(/i.test(href + oc))
          ssos.push({text: txt(el), href, onclick: oc});
      });
      const stream = [];
      document.querySelectorAll('a, button, img, div, span, li').forEach(el => {
        const t = txt(el);
        const href = el.getAttribute && el.getAttribute('href')||'';
        if (/(streaming|settrade)/i.test(t + ' ' + href) && t.length < 40)
          stream.push({tag: el.tagName, text: t, href: href.slice(0,160)});
      });
      return {url: location.href, ssos, stream,
              bodyText: (document.body ? document.body.innerText : '').slice(0, 2000)};
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

    # --- login (auto-fill if we're on the login form) ---
    body = await page.inner_text("body")
    already_in = any(k in body for k in ["ยินดีต้อนรับ", "ออกจากระบบ", "creditbalance"]) or "member" in page.url.lower()
    if not already_in:
        try:
            for sel in ["#login_username", "input[name*='user' i]", "input[placeholder*='ชื่อผู้ใช้']"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.fill(u); print(f"filled user via {sel}"); break
            for sel in ["#login_password", "input[name*='pass' i]", "input[placeholder*='รหัสผ่าน']"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.fill(p); print(f"filled pass via {sel}"); break
            await page.click("#login", timeout=8000)
            print(">>> กด Login (Krungsri) แล้ว — รอ OTP ...")
        except Exception as e:
            print(">>> krungsri login fill error:", type(e).__name__, str(e)[:200])

    # --- wait for OTP then member portal (human types OTP) ---
    waited = 0
    while waited < 240:
        body = await page.inner_text("body")
        if any(k in body for k in ["ยินดีต้อนรับ", "creditbalance", "เริ่มต้นใช้งาน"]) or "member" in page.url.lower():
            break
        if waited % 20 == 0:
            print(f"   ... รอ login/OTP ({waited}s) — URL: {page.url}")
            otp_inputs = await page.evaluate("""() => Array.from(document.querySelectorAll('input')).filter(i =>
                /otp|pin|รหัส|ref/i.test((i.id||i.name||i.placeholder||''))).map(i =>
                ({id:i.id, name:i.name, placeholder:i.placeholder, type:i.type}))""")
            if otp_inputs:
                print("   >>> เจอช่อง OTP — พิมพ์ OTP ในหน้าต่างแล้วกด submit:", json.dumps(otp_inputs, ensure_ascii=False))
        await page.wait_for_timeout(4000)
        waited += 4

    portal = await dump_ssos(page)
    save("portal", portal)
    print("PORTAL URL:", portal["url"])
    print("=== SSO links ===")
    print(json.dumps(portal["ssos"], ensure_ascii=False, indent=1))
    print("=== streaming links ===")
    print(json.dumps(portal["stream"], ensure_ascii=False, indent=1))

    # --- click the Streaming SSO link (not page=TM) ---
    stream_clicked = False
    for s in portal["ssos"]:
        if "TM" not in s["href"] and "tm" not in s["href"]:
            try:
                if s["onclick"]:
                    await page.evaluate(s["onclick"])
                elif s["href"]:
                    await page.goto(s["href"], wait_until="domcontentloaded", timeout=30000)
                print(">>> คลิก Streaming SSO:", s)
                stream_clicked = True
                await page.wait_for_timeout(8000)
                break
            except Exception as e:
                print(">>> SSO click error:", type(e).__name__, str(e)[:150])

    # follow to streaming.settrade.com if a popup/tab opened
    if not stream_clicked:
        for pg in ctx.pages:
            if "settrade" in pg.url.lower() or "streaming" in pg.url.lower():
                page = pg
                stream_clicked = True
                print(">>> พบ tab Streaming:", pg.url)
                break

    if stream_clicked:
        await page.wait_for_timeout(5000)
        snap = await snapshot_dom(page, "STREAMING_TRADING")
        snap["url"] = page.url
        save("trading", snap)
        print("=== TRADING URL:", snap["url"])
        print("=== side buttons:", json.dumps(snap["sideButtons"], ensure_ascii=False)[:1200])
        print("=== submit buttons:", json.dumps(snap["submitButtons"], ensure_ascii=False)[:1200])
        print("=== action (cancel/modify/change):", json.dumps(snap["actionButtons"], ensure_ascii=False)[:2000])
        print("=== bid/offer:", json.dumps(snap["bidOffer"], ensure_ascii=False)[:1200])
        print("=== account:", json.dumps(snap["account"], ensure_ascii=False)[:1200])
        shot = os.path.join(OUT_DIR, f"streaming_trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        await page.screenshot(path=shot, full_page=True)
        print("shot:", shot)
    else:
        print(">>> ไม่เจอ Streaming SSO link — ดู portal JSON เอา")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
