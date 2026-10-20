# -*- coding: utf-8 -*-
"""Phase 0 probe — Krungsri SSO portal → find the Streaming SSO link.

Loads the saved Krungsri session (session_state.json), opens the member portal,
and dumps every SSO link (start_SSO.aspx?page=XX) + anything mentioning
Streaming/Settrade. This tells us the SSO code to reach Settrade Streaming the
same way TradeMan uses page=TM.
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
    args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx_kwargs = {"viewport": {"width": 1440, "height": 960}}
    if os.path.exists(settings.SESSION_STATE_PATH):
        ctx_kwargs["storage_state"] = settings.SESSION_STATE_PATH
    ctx = await browser.new_context(**ctx_kwargs)
    page = await ctx.new_page()

    await page.goto(settings.KRUNGSRI_LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)

    data = await page.evaluate("""() => {
      const txt = el => (el.innerText || el.value || '').trim();
      const ssos = [];
      document.querySelectorAll('a[href*="start_SSO"], a[href*="sso"], a[onclick*="SSO"], a[onclick*="popup"]').forEach(el => {
        ssos.push({text: txt(el), href: el.getAttribute('href')||'', onclick: el.getAttribute('onclick')||''});
      });
      const streamingLinks = [];
      document.querySelectorAll('a, button, img, div, span, li').forEach(el => {
        const t = txt(el);
        const href = el.getAttribute && el.getAttribute('href') || '';
        const src = el.getAttribute && el.getAttribute('src') || '';
        if (/(streaming|settrade|trademan|real.?time|realtime)/i.test(t + ' ' + href + ' ' + src))
          streamingLinks.push({tag: el.tagName, text: t.slice(0,40), href: href.slice(0,160),
                               src: src.slice(0,160), outer: (el.outerHTML||'').slice(0,300)});
      });
      return {url: location.href,
              bodyText: (document.body ? document.body.innerText : '').slice(0, 2500),
              ssos, streamingLinks};
    }""")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(OUT_DIR, f"krungsri_portal_{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("URL:", data["url"])
    print("=== bodyText (first 1500) ===")
    print(data["bodyText"][:1500])
    print("=== SSO links ===")
    print(json.dumps(data["ssos"], ensure_ascii=False, indent=1))
    print("=== streaming/settrade/trademan links ===")
    print(json.dumps(data["streamingLinks"], ensure_ascii=False, indent=1)[:3000])
    print("\nSaved:", out)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
