# -*- coding: utf-8 -*-
"""Dump links on the current member-portal page to find the Streaming SSO link."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _reuse import reuse_page  # noqa: E402


async def main():
    pw, browser, page = await reuse_page()
    print("page:", page.url)
    links = await page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('a, area').forEach(el => {
        const t = (el.innerText || '').trim();
        const h = (el.href || el.getAttribute('href') || '');
        if (/streaming|settrade|ซื้อขาย|โปรแกรม|trade/i.test(t + ' ' + h) && (t.length < 40))
          out.push({text: t, href: h.slice(0, 160), onclick: (el.getAttribute('onclick')||'').slice(0,120)});
      });
      return out;
    }""")
    for l in links:
        print(l)
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
