# -*- coding: utf-8 -*-
"""Resume (no OTP) headless dump — exact side radio inputs for Short/Cover/Normal
on the MARGIN account, plus the Change/action buttons in order status."""
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
    args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx = await browser.new_context(storage_state=SESSION, viewport={"width": 1440, "height": 960})
    page = await ctx.new_page()
    await page.goto(settings.STREAMING_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(5000)
    print("URL:", page.url)

    # switch to margin if on cash
    if "3024952" in (await page.inner_text("body"))[:2000] or True:
        try:
            await page.click("span.outline-none:has-text('Equity')", timeout=5000)
            await page.wait_for_timeout(1000)
            await page.click("li:has-text('3024959')", timeout=5000)
            await page.wait_for_timeout(3000)
            print(">>> switched to margin")
        except Exception as e:
            print(">>> switch note:", type(e).__name__, str(e)[:100])

    data = await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const radios = [];
      document.querySelectorAll('input[type=radio], input[type=checkbox]').forEach(el => {
        radios.push({id: el.id, name: el.name, value: el.value, type: el.type,
                     checked: el.checked, outer: el.outerHTML.slice(0,200)});
      });
      const shortCover = [];
      document.querySelectorAll('label, div, input').forEach(el => {
        const t = txt(el);
        if (/^(short|cover|normal)$/i.test(t))
          shortCover.push({tag: el.tagName, id: el.id||'', text: t,
                           for: el.getAttribute && el.getAttribute('for')||'',
                           outer: el.outerHTML.slice(0,300)});
      });
      const actionBtns = [];
      document.querySelectorAll('button, a, i, img, span, div').forEach(el => {
        const t = txt(el);
        const oc = (el.getAttribute && el.getAttribute('onclick'))||'';
        if (/(change|modify|แก้|เปลี่ยน|แก้ไข)/i.test(t + ' ' + oc) && t.length < 30)
          actionBtns.push({tag: el.tagName, id: el.id||'', cls: (el.className||'').toString().slice(0,70),
                           text: t, onclick: oc.slice(0,150), outer: el.outerHTML.slice(0,300)});
      });
      return {url: location.href, radios, shortCover, actionBtns,
              bodyText: (document.body ? document.body.innerText : '').slice(0, 1500)};
    }""")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join(OUT, f"streaming_side_radios_{stamp}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("=== radios ===")
    print(json.dumps(data["radios"], ensure_ascii=False, indent=1))
    print("=== short/cover/normal ===")
    print(json.dumps(data["shortCover"], ensure_ascii=False, indent=1))
    print("=== change/modify actions ===")
    print(json.dumps(data["actionBtns"], ensure_ascii=False, indent=1))
    print("\nSaved:", p)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
