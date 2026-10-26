#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""READ-ONLY: locate the order-number text node, walk to its row container,
dump the container HTML + every clickable/action descendant (to map the
native Change link). Does NOT click anything."""
import asyncio
import json
import sys

REPO = "/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab"
sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")

    res = await page.evaluate("""() => {
        const out = {found: [], containers: []};
        // find the leaf element whose exact text is the order number
        const all = [...document.querySelectorAll('*')];
        const leaf = all.find(e => e.children.length === 0 && (e.textContent||'').trim() === '11011357');
        if (!leaf) {
            out.note = 'exact-text leaf not found; searching substring';
            for (const e of all) {
                if (e.children.length === 0 && (e.textContent||'').includes('11011357')) {
                    out.found.push({tag: e.tagName, cls: (e.className||'').toString(), text: (e.textContent||'').trim()});
                }
            }
            return out;
        }
        // walk up 6 levels, dump each
        let cur = leaf;
        for (let i = 0; i < 6 && cur; i++) {
            out.containers.push({
                level: i, tag: cur.tagName,
                cls: (cur.className||'').toString().slice(0,150),
                id: cur.id || '',
                html: cur.outerHTML.slice(0, 3500)
            });
            cur = cur.parentElement;
        }
        // within the 3rd ancestor (row container), list clickable/action descendants
        cur = leaf;
        for (let i = 0; i < 3 && cur; i++) cur = cur.parentElement;
        if (cur) {
            out.rowActions = [...cur.querySelectorAll('li,span,a,button,div,i,svg')].filter(e => {
                const t = (e.textContent||'').trim();
                const c = (e.className||'').toString();
                return /change|cancel|แก้ไข|ยกเลิก/i.test(t) || /phnjeo|action|menu|dropdown|underline/i.test(c);
            }).map(e => ({
                tag: e.tagName, cls: (e.className||'').toString().slice(0,120),
                text: (e.textContent||'').trim().slice(0,40),
                under: getComputedStyle(e).textDecorationLine,
                html: e.outerHTML.slice(0,500)
            }));
            out.rowHtml = cur.outerHTML.slice(0, 6000);
        }
        return out;
    }""")
    print(json.dumps(res, ensure_ascii=False, indent=2)[:6000])

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
