#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only state probe for the P.0a card (no order placement).

1. Streaming (kss 9333): dump current account + open-order rows + any TU row.
2. SBL (kss 9333): dump PP + borrowable inventory (SET50/SET100/NEW SEC/XD) +
   active borrow contracts (borrowed quantities).
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab, inspect_sbl_application  # noqa: E402

OUT = os.path.join(REPO, "data", "har", "sbl_inventory.json")


async def streaming_state(ctx):
    page = await resolve_target_tab(ctx, "streaming", "kss")
    if not page:
        return {"error": "no streaming tab"}
    await page.bring_to_front()
    await page.wait_for_timeout(1500)
    js = r"""() => {
        const out = {account: null, orders: [], tu_hits: [], tu_mentions: []};
        const bodyText = document.body.innerText;
        const acctEls = [...document.querySelectorAll('span,div,p')].filter(e => /3024\d{3}/.test(e.innerText) && e.innerText.length < 60);
        out.account = acctEls.slice(0, 3).map(e => e.innerText.trim().slice(0, 60));
        for (const el of document.querySelectorAll('tr, [class*="order"], [class*="Order"]')) {
            const t = (el.innerText || '').trim();
            if (/TU|BCPG|3024/.test(t) && t.length < 300) out.tu_hits.push(t.slice(0, 300));
        }
        const tuText = bodyText.split(/\r?\n/).filter(l => /TU/.test(l));
        out.tu_mentions = tuText.slice(0, 20);
        return out;
    }"""
    return await page.evaluate(js)


async def sbl_state(ctx):
    page = await resolve_target_tab(ctx, "sbl", "kss")
    if not page:
        return {"error": "no sbl tab"}
    await page.bring_to_front()
    await page.wait_for_timeout(1000)
    return await inspect_sbl_application(page)


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    st = await streaming_state(ctx)
    sbl = await sbl_state(ctx)
    result = {"streaming": st, "sbl": sbl}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
