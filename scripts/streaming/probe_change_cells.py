# -*- coding: utf-8 -*-
"""Focused resume dump — exact outerHTML of the Change/Detail/Cancel cells."""
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
    await page.goto(settings.KRUNGSRI_LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(2500)
    for sel in ["a:has-text('โปรแกรม Streaming')", "a:has-text('Streaming')"]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            await el.click(timeout=8000)
            print(">>> คลิก Streaming SSO:", sel)
            break
    await page.wait_for_timeout(9000)
    for pg in ctx.pages:
        if "settrade" in pg.url.lower() or "streamingpage" in pg.url.lower():
            page = pg
            break
    print("URL:", page.url)
    if "Unauthorized" in page.url or "login" in page.url.lower():
        print("!! session expired again — need fresh OTP")
        await browser.close()
        return

    try:
        await page.click("span.outline-none:has-text('Equity')", timeout=5000)
        await page.wait_for_timeout(1000)
        await page.click("li:has-text('3024959')", timeout=5000)
        await page.wait_for_timeout(3000)
        print(">>> margin")
    except Exception as e:
        print(">>> switch note:", type(e).__name__, str(e)[:80])

    data = await page.evaluate("""() => {
      const cells = [];
      document.querySelectorAll('li').forEach(el => {
        const t = (el.innerText || '').trim();
        if (/^(change|detail|cancel)$/i.test(t))
          cells.push({text: t, cls: (el.className||'').toString(),
                      onclick: (el.getAttribute('onclick')||''),
                      data: JSON.stringify(Object.fromEntries([...el.attributes].filter(a=>a.name.startsWith('data-')).map(a=>[a.name,a.value]))),
                      outer: el.outerHTML});
      });
      // the row <ul> for order 11006664
      const row = document.querySelector('ul.bg-color-cover-100');
      return {cells, rowOuter: row ? row.outerHTML : null,
              bodyText: (document.body ? document.body.innerText : '').slice(0, 400)};
    }""")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join(OUT, f"streaming_change_cells_{stamp}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("=== Change/Detail/Cancel cells ===")
    for c in data["cells"]:
        print(json.dumps(c, ensure_ascii=False))
    print("\n=== row ul ===")
    print((data["rowOuter"] or "")[:4000])
    print("\nSaved:", p)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
