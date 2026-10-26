#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""READ-ONLY probe: dump Streaming order-status DOM to map the native Change
row action (reference row = existing order 11011357, do NOT click anything)."""
import asyncio
import json
import sys

REPO = "/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab"
sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")
    print("PAGE:", page.url)

    # switch to order_status tab (reuse driver's known selectors)
    for sel in ["button:has-text('View Order')", "a:has-text('View Order')", "span:has-text('View Order')", "text=View Order"]:
        el = page.locator(sel).first
        if await el.count():
            try:
                await el.click()
                await page.wait_for_timeout(2500)
                break
            except Exception as ex:
                print(f"  (click {sel} -> {type(ex).__name__}: {ex})")
    print("AFTER TAB CLICK:", page.url)

    # dump any row containing order no 11011357
    html = await page.evaluate("""() => {
        const out = {rows: [], changeCandidates: [], tables: []};
        document.querySelectorAll('table').forEach((t, ti) => {
            if (ti > 8) return;
            const txt = (t.innerText || '').slice(0, 300);
            if (/11011357|Change|แก้ไข|Queuing|Order No|คำสั่ง/.test(txt)) {
                out.tables.push({ti, txt});
            }
        });
        // find rows mentioning the order number
        document.querySelectorAll('tr').forEach(tr => {
            const t = tr.innerText || '';
            if (t.includes('11011357')) {
                out.rows.push(tr.outerHTML.slice(0, 4000));
                // collect clickable / underlined descendants (potential Change link)
                [...tr.querySelectorAll('li,span,a,button,div')].forEach(e => {
                    const st = getComputedStyle(e);
                    const u = st.textDecorationLine.includes('underline') || /change|แก้ไข/i.test(e.textContent||'');
                    if (u || /change|แก้ไข/i.test(e.textContent||'')) {
                        out.changeCandidates.push({
                            tag: e.tagName, cls: (e.className||'').toString().slice(0,100),
                            text: (e.textContent||'').trim().slice(0,60),
                            under: st.textDecorationLine,
                            html: e.outerHTML.slice(0,400)
                        });
                    }
                });
            }
        });
        return out;
    }""")
    print("=== TABLES ===")
    print(json.dumps(html.get("tables", []), ensure_ascii=False, indent=2)[:1500])
    print("=== ROWS ===")
    for r in html.get("rows", []):
        print(r[:4000])
        print("---")
    print("=== CHANGE CANDIDATES ===")
    print(json.dumps(html.get("changeCandidates", []), ensure_ascii=False, indent=2)[:3000])

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
