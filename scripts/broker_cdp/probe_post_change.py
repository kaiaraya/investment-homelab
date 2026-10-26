#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""POST-CLICK probe: click native Change on order 11014738, then dump every
visible input + button + PIN field + the order-ticket state, to map the real
Change flow (modal vs in-ticket)."""
import asyncio
import json
import sys

REPO = "/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab"
sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402

ORDER_NO = "11014738"


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")

    # click Change
    click = await page.evaluate(
        """(orderNo) => {
            const lis = [...document.querySelectorAll('li')];
            const li = lis.find(e => (e.textContent||'').trim() === String(orderNo));
            if (!li) return {ok:false, reason:'li not found'};
            const ul = li.closest('ul');
            const ch = ul.querySelector('li.css-phnjeo, li[class*="phnjeo"]');
            if (!ch) return {ok:false, reason:'change li not found'};
            ch.click();
            return {ok:true};
        }""",
        ORDER_NO,
    )
    print("click:", json.dumps(click))
    await page.wait_for_timeout(2500)

    state = await page.evaluate(
        """() => {
            const inputs = [...document.querySelectorAll('input')].filter(e =>
                e.offsetParent !== null).map(e => ({
                    type: e.type, name: e.name||'', id: e.id||'',
                    placeholder: e.placeholder||'', value: e.value||'',
                    cls: (e.className||'').toString().slice(0,60)
                }));
            const buttons = [...document.querySelectorAll('button')].filter(e =>
                e.offsetParent !== null).map(e => ({
                    text: (e.textContent||'').trim().slice(0,40),
                    cls: (e.className||'').toString().slice(0,60),
                    disabled: e.disabled
                })).filter(b => b.text);
            // any element mentioning change/confirm/PIN/แก้ไข/ยืนยัน
            const hints = [...document.querySelectorAll('li,span,a,button,div')].filter(e => {
                const t = (e.textContent||'').trim();
                return /change|confirm|แก้ไข|ยืนยัน|ยกเลิก|cancel|pin/i.test(t) && t.length < 60;
            }).map(e => ({tag:e.tagName, cls:(e.className||'').toString().slice(0,60), text:(e.textContent||'').trim().slice(0,50)})).slice(0, 40);
            return {inputs, buttons, hints};
        }"""
    )
    print("=== VISIBLE INPUTS ===")
    print(json.dumps(state.get("inputs"), ensure_ascii=False, indent=1))
    print("=== VISIBLE BUTTONS ===")
    print(json.dumps(state.get("buttons"), ensure_ascii=False, indent=1))
    print("=== HINTS (change/confirm/pin/cancel) ===")
    print(json.dumps(state.get("hints"), ensure_ascii=False, indent=1))

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
