# -*- coding: utf-8 -*-
"""One-shot: dump the full Streaming login page (broker list + form) to a file.
Read-only. Saves immediately (no login wait) so we can read the broker list.
"""
import asyncio
import json
import os
from datetime import datetime

from playwright.async_api import async_playwright

from app.core.config import settings

OUT_DIR = "data/probes"
os.makedirs(OUT_DIR, exist_ok=True)


async def main():
    pw = await async_playwright().start()
    args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    page = await (await browser.new_context(viewport={"width": 1440, "height": 960})).new_page()

    await page.goto("https://streaming.settrade.com/realtime/streaming-login/login.jsp",
                    wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(2500)

    data = await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const links = [];
      document.querySelectorAll('a, button, [role=button], li, option, img[title], img[alt]').forEach(el => {
        const t = txt(el);
        const href = el.getAttribute && el.getAttribute('href') || '';
        if (t || href) links.push({tag: el.tagName, id: el.id||'', cls:(el.className||'').toString().slice(0,60),
                                   text: t.slice(0,60), href: href.slice(0,160)});
      });
      const selects = [];
      document.querySelectorAll('select').forEach(el => {
        const opts = Array.from(el.querySelectorAll('option')).map(o => o.innerText.trim());
        selects.push({id: el.id||'', name: el.name||'', options: opts});
      });
      return {url: location.href, title: document.title,
              bodyText: (document.body ? document.body.innerText : '').slice(0, 8000),
              links, selects,
              html: document.documentElement.outerHTML.slice(0, 20000)};
    }""")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(OUT_DIR, f"streaming_login_{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("URL:", data["url"])
    print("TITLE:", data["title"])
    print("=== bodyText (first 3000) ===")
    print(data["bodyText"][:3000])
    print("=== links/buttons (broker list etc) ===")
    for l in data["links"]:
        print(json.dumps(l, ensure_ascii=False))
    print("=== selects ===")
    print(json.dumps(data["selects"], ensure_ascii=False, indent=1))
    print("\nSaved:", out)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
