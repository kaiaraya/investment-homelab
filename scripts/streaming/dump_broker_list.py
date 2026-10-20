# -*- coding: utf-8 -*-
"""One-shot: open the broker ng-select dropdown and dump every broker option.
Read-only, headless — no login needed. Saves broker list to data/probes/.
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
    ctx = await browser.new_context(viewport={"width": 1440, "height": 960})
    page = await ctx.new_page()

    await page.goto("https://streaming.settrade.com/realtime/streaming-login/login.jsp",
                    wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(2000)

    # Open the broker ng-select dropdown
    try:
        await page.click("ng-select input[role='combobox']", timeout=8000)
        await page.wait_for_timeout(1500)
    except Exception as e:
        print("open dropdown failed:", type(e).__name__, str(e)[:120])

    options = await page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('.ng-dropdown-panel .ng-option, .ng-dropdown-panel .ng-option-label, ng-dropdown-panel div[role=option]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t) out.push({text: t, id: el.getAttribute && (el.getAttribute('id')||''),
                         cls: (el.className||'').toString().slice(0,80)});
      });
      // also grab any visible text in the dropdown panel
      const panel = document.querySelector('.ng-dropdown-panel');
      return {options: out, panelText: panel ? panel.innerText.slice(0, 4000) : ''};
    }""")

    print("=== broker options ===")
    print(json.dumps(options, ensure_ascii=False, indent=1))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(OUT_DIR, f"streaming_broker_list_{stamp}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(options, f, ensure_ascii=False, indent=2)
    print("\nSaved:", out)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
