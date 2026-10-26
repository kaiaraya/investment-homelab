#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract SBL Realtime inventory from ALL 4 tabs (SET50 / SET100 / NEW SEC / XD XR)."""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402

OUT = os.path.join(REPO, "data", "har", "sbl_4tabs.json")

EXTRACT = r"""() => {
    const clean = s => (s || '').replace(/\u00a0/g, ' ').trim();
    const rows = [];
    // Capture every table row's cells (handles SET50/100/NEW SEC inventory + XD/XR table)
    for (const tr of document.querySelectorAll('table tr')) {
        const cells = Array.from(tr.querySelectorAll('td,th')).map(td => clean(td.innerText));
        const joined = cells.join(' | ');
        if (joined && cells.length >= 2) rows.push(joined);
    }
    return rows;
}"""

TABS = [
    ("#MainCenter_lbSet50", "SET50"),
    ("#MainCenter_lbSet100", "SET100"),
    ("#MainCenter_lbNewSec", "NEWSEC"),
    ("#MainCenter_lbXD", "XDXR"),
]


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "sbl", "kss")
    await page.bring_to_front()
    await page.wait_for_timeout(1000)

    result = {}
    for sel, name in TABS:
        try:
            el = page.locator(sel)
            if await el.count():
                await el.first.click()
                await page.wait_for_timeout(3500)
        except Exception as ex:
            print(f"⚠️ click {name}: {ex}")
        result[name] = await page.evaluate(EXTRACT)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 saved {OUT}")
    for name, rows in result.items():
        print(f"\n=== {name} ({len(rows)} rows) ===")
        for r in rows[:8]:
            print("  " + r[:160])
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
