#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.4a STAGE A2 — click native Change on the resting BCPG order and dump the
dialog HTML (DISCOVERY only, no confirm / no cancel)."""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402

ORDER_NO = "11014738"


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")
    print(f"📍 attached: {page.url}")

    click_res = await page.evaluate(
        """(orderNo) => {
            const lis = [...document.querySelectorAll('li')];
            const li = lis.find(e => (e.textContent||'').trim() === String(orderNo));
            if (!li) return {ok:false, reason:'order-number li not found'};
            const ul = li.closest('ul');
            if (!ul) return {ok:false, reason:'row ul not found'};
            const change = ul.querySelector('li.css-phnjeo, li[class*="phnjeo"]');
            if (!change) return {ok:false, reason:'change li not found', rowHtml: ul.outerHTML.slice(0,2000)};
            change.click();
            return {ok:true, changeText: change.textContent.trim(), rowHtml: ul.outerHTML.slice(0,1200)};
        }""",
        ORDER_NO,
    )
    print(f"🔧 click: {json.dumps(click_res, ensure_ascii=False)[:700]}")
    if not click_res.get("ok"):
        await browser.close()
        await pw.stop()
        return
    await page.wait_for_timeout(2000)

    dialog = await page.evaluate(
        """() => {
            const sels = ['[role="dialog"]', '[class*="modal"]', '[class*="Modal"]', '[class*="dialog"]', '[class*="Dialog"]', '[class*="popup"]', '[class*="overlay"]'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) return {sel: s, html: el.outerHTML};
            }
            return {sel: '(none)', html: document.body.innerHTML.slice(-8000)};
        }"""
    )
    out_path = os.path.join(REPO, "data", "har", "kss_change_dialog.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(dialog.get("html", ""))
    print(f"💾 dialog ({dialog.get('sel')}) -> {out_path} ({len(dialog.get('html',''))} chars)")
    print("=== DIALOG (first 4500 chars) ===")
    print(dialog.get("html", "")[:4500])

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
