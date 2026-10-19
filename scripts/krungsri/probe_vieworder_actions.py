# -*- coding: utf-8 -*-
"""STEP 0a probe — TradeMan View Order actions + quote/depth DOM (read-only).

Opens a HEADED Chromium with the saved session, dumps:
  * every View Order row (text) and its action-cell HTML
  * every element whose onclick/text mentions cancel/modify
  * bid/offer-ish elements on the Buy/Sell panel (depth source check)
  * XHR endpoints that look like stock/quote/bid/order

Never clicks Cancel / Submit. Saves HTML + screenshot under data/probes/.
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


async def main():
    pw = await async_playwright().start()
    args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx = await browser.new_context(
        storage_state=settings.SESSION_STATE_PATH,
        viewport={"width": 1400, "height": 950},
    )
    page = await ctx.new_page()

    net = []
    page.on("response", lambda r: net.append(r.url) if re.search(
        r"stock|quote|bid|offer|order", r.url, re.I) else None)

    await page.goto("https://trademan.in.th/Portfolio", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(6000)
    print("URL:", page.url)

    # View Order tab (deterministic id from the driver)
    try:
        await page.click("div#order_btn", timeout=8000)
        await page.wait_for_timeout(3500)
    except Exception as e:
        print("order_btn click failed:", type(e).__name__, str(e)[:120])

    dump = await page.evaluate("""() => {
      const rows = [];
      document.querySelectorAll('table tr').forEach(tr => {
        const cells = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText||'').trim());
        if (!cells.length) return;
        const last = tr.querySelector('td:last-child');
        rows.push({cells, actionHTML: last ? last.innerHTML.slice(0, 1200) : ''});
      });
      const clicky = [];
      document.querySelectorAll('button, a, input[type=button], i, span, div').forEach(el => {
        const t = (el.innerText||el.value||'').trim();
        const oc = el.getAttribute && (el.getAttribute('onclick')||'');
        if (/cancel|ยกเลิก|modify|change|แก้ไข/i.test(t) || /cancel|modify|change/i.test(oc)) {
          clicky.push({tag: el.tagName, text: t.slice(0,40), onclick: oc.slice(0,200),
                       outer: el.outerHTML.slice(0,500)});
        }
      });
      return {rows, clicky};
    }""")

    # Buy/Sell panel — look for a bid/offer depth area
    quotes = await page.evaluate("""() => {
      const hits = [];
      document.querySelectorAll('*').forEach(el => {
        const t = (el.innerText||'').trim();
        if (t && t.length < 400 && /(bid|offer|ราคาเสนอซื้อ|ราคาเสนอขาย)/i.test(t) && el.children.length <= 3) {
          hits.push({tag: el.tagName, cls: el.className, text: t.slice(0,240)});
        }
      });
      return hits.slice(0, 25);
    }""")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = f"{OUT_DIR}/trademan_vieworder_{ts}.html"
    shot_path = f"{OUT_DIR}/trademan_vieworder_{ts}.png"
    open(html_path, "w", encoding="utf-8").write(await page.content())
    await page.screenshot(path=shot_path, full_page=True)

    print("ROWS:", json.dumps(dump["rows"], ensure_ascii=False)[:2500])
    print("CLICKY:", json.dumps(dump["clicky"][:15], ensure_ascii=False)[:2500])
    print("QUOTE_HITS:", json.dumps(quotes, ensure_ascii=False)[:1500])
    print("XHR:", json.dumps(sorted(set(net))[:25], ensure_ascii=False))
    print("SAVED:", html_path, shot_path)

    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
