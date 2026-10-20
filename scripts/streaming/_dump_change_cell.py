# -*- coding: utf-8 -*-
"""Dump the exact Change/Detail/Cancel cells + order row structure (reuse session)."""
import asyncio
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _reuse import reuse_page  # noqa: E402


async def main():
    pw, browser, page = await reuse_page()
    data = await page.evaluate("""() => {
      const cells = [];
      document.querySelectorAll('li').forEach(el => {
        const t = (el.innerText || '').trim();
        if (/^(change|detail|cancel)$/i.test(t))
          cells.push({text: t, cls: (el.className||'').toString(),
                      onclick: (el.getAttribute('onclick')||''),
                      outer: el.outerHTML});
      });
      const row = document.querySelector('ul.bg-color-cover-100, ul[class*="cover"]');
      // also find the row ul that contains the order checkbox
      let rowUl = null;
      document.querySelectorAll('ul').forEach(ul => {
        if (ul.querySelector('input[id*="11006664"]')) rowUl = ul;
      });
      return {cells, rowUlOuter: rowUl ? rowUl.outerHTML : null};
    }""")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join("data/probes", f"streaming_change_cells_{stamp}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("=== Change/Detail/Cancel cells ===")
    for c in data["cells"]:
        print(json.dumps(c, ensure_ascii=False))
    print("\n=== row ul (order 11006664) ===")
    print((data["rowUlOuter"] or "")[:5000])
    print("\nSaved:", p)
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
