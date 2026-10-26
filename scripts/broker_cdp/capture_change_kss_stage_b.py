#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.4a STAGE B — Streaming native in-place Change capture.

The Change editor is an INLINE row expansion (not a modal): clicking
`li.css-phnjeo` reveals `input[name="change-order-price-input"]` /
`change-order-volume-input` + inline Submit/Cancel in the row. Fills the new
(more-passive) price, submits, captures the XHR, verifies via DGW API, then
cancels the order (cleanup).
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402
from scripts.broker_cdp.har_capture import HarCapture, save  # noqa: E402

ORDER_NO = "11014738"
NEW_PRICE = "6.70"


async def read_orders(page):
    txt = await page.evaluate(
        """async () => { const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/orders', {credentials:'include'}); return await r.text(); }"""
    )
    try:
        return json.loads(txt)
    except Exception:
        return []


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")
    print(f"📍 attached: {page.url}")

    cap = HarCapture()
    cap.attach(page)

    # 0. confirm the order is still resting (matched 0) before touching it
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == ORDER_NO]
    if not mine:
        print(f"❌ order {ORDER_NO} no longer open — aborting")
        await browser.close()
        await pw.stop()
        return
    print(f"🔍 before: price={mine[0].get('price')} matched={mine[0].get('matched')} status={mine[0].get('showOrderStatus')}")

    # 1. ensure the row's Change editor is expanded
    state = await page.evaluate(
        """(orderNo) => {
            const lis = [...document.querySelectorAll('li')];
            const li = lis.find(e => (e.textContent||'').trim() === String(orderNo));
            if (!li) return {ok:false, reason:'row li not found'};
            const ul = li.closest('ul');
            const priceEl = ul.querySelector('input[name="change-order-price-input"]');
            if (!priceEl || priceEl.offsetParent === null) {
                const ch = ul.querySelector('li.css-phnjeo, li[class*="phnjeo"]');
                if (!ch) return {ok:false, reason:'change li not found'};
                ch.click();
                return {ok:true, clicked:true};
            }
            return {ok:true, clicked:false};
        }""",
        ORDER_NO,
    )
    print(f"🔧 ensure expanded: {json.dumps(state, ensure_ascii=False)}")
    if not state.get("ok"):
        await browser.close()
        await pw.stop()
        return
    await page.wait_for_timeout(1500)

    # 2. fill new price
    cap.set_phase("streaming_change_fill")
    fill = await page.evaluate(
        """({orderNo, price}) => {
            const lis = [...document.querySelectorAll('li')];
            const li = lis.find(e => (e.textContent||'').trim() === String(orderNo));
            const ul = li.closest('ul');
            const pe = ul.querySelector('input[name="change-order-price-input"]');
            if (!pe) return {ok:false, reason:'price input not found'};
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(pe, price);
            pe.dispatchEvent(new Event('input', {bubbles:true}));
            pe.dispatchEvent(new Event('change', {bubbles:true}));
            return {ok:true, value: pe.value};
        }""",
        {"orderNo": ORDER_NO, "price": NEW_PRICE},
    )
    print(f"✏️ fill price: {json.dumps(fill, ensure_ascii=False)}")
    if not fill.get("ok"):
        await browser.close()
        await pw.stop()
        return
    await page.wait_for_timeout(500)

    # 3. click the row's inline Submit
    cap.set_phase("streaming_change_submit")
    submit = await page.evaluate(
        """(orderNo) => {
            const lis = [...document.querySelectorAll('li')];
            const li = lis.find(e => (e.textContent||'').trim() === String(orderNo));
            const ul = li.closest('ul');
            const btns = [...ul.querySelectorAll('button')];
            const s = btns.find(b => (b.textContent||'').trim().toLowerCase() === 'submit');
            if (!s) return {ok:false, reason:'submit button not found', buttons: btns.map(b=>(b.textContent||'').trim())};
            s.click();
            return {ok:true};
        }""",
        ORDER_NO,
    )
    print(f"🚀 submit: {json.dumps(submit, ensure_ascii=False)}")
    await page.wait_for_timeout(2500)

    # 4. verify via DGW API
    cap.set_phase("streaming_change_verify")
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == ORDER_NO]
    if mine:
        print(f"🔍 after: price={mine[0].get('price')} matched={mine[0].get('matched')} status={mine[0].get('showOrderStatus')}")
    else:
        print("⚠️ order not in list after change")

    # 5. cancel the order via DGW PATCH /cancel (cleanup — endpoint already mapped)
    from app.core.config import settings

    pin = settings.KRUNGSRI_PIN or settings.TRADING_PIN
    cap.set_phase("streaming_cancel")
    cancel = await page.evaluate(
        """async ({orderNo, pin}) => {
            const body = {orders:[{sequenceNo:'0', orderNo, symbol:'BCPG', tradeDate:'2026-10-26'}], pin};
            const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/cancel', {
                method: 'PATCH', credentials: 'include',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify(body)
            });
            return {status: r.status, body: await r.text()};
        }""",
        {"orderNo": ORDER_NO, "pin": pin},
    )
    print(f"🗑 cancel API: {json.dumps(cancel, ensure_ascii=False)[:500]}")
    await page.wait_for_timeout(2000)

    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == ORDER_NO]
    status = mine[0].get("showOrderStatus") if mine else "GONE"
    print(f"🔍 after cancel: order {ORDER_NO} status={status}")

    save("kss_change", cap, "KSS Streaming native Change (BCPG BUY 100)")
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
