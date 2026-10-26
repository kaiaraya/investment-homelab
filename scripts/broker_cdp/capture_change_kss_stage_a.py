#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.4a STAGE A — Streaming: place passive BUY BCPG, click native Change,
dump the Change dialog HTML (DISCOVERY — does NOT confirm, does NOT cancel).
Leaves the order resting so Stage B can fill+confirm+capture."""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from app.browser.streaming_driver import StreamingDriver  # noqa: E402
from scripts.broker_cdp.har_capture import HarCapture  # noqa: E402

SYMBOL = "BCPG"
VOLUME = 100
SIDE = "BUY"
STATIC_DATA_URL = "https://apigwcld.settrade.com/api/marketdata/v4/029/static-data/{sym}?market=E"

SET_TICKS = [
    (0.01, 0.01), (2.0, 0.02), (5.0, 0.05), (10.0, 0.1),
    (25.0, 0.25), (100.0, 0.5), (200.0, 1.0), (400.0, 2.0),
]


def set_tick(price: float) -> float:
    tick = 0.01
    for lo, t in SET_TICKS:
        if price >= lo:
            tick = t
    return tick


async def main():
    drv = StreamingDriver()
    if not await drv.connect_cdp():
        print("❌ connect_cdp failed (daemon 9333 down?)")
        return
    page = drv.page_override
    print(f"📍 Streaming attached: {page.url}")

    cap = HarCapture()
    cap.attach(page)

    # 1. static data -> passive price
    cap.set_phase("streaming_quote")
    sd = await page.evaluate(
        f"""async () => {{ const r = await fetch('{STATIC_DATA_URL.format(sym=SYMBOL)}', {{credentials:'include'}}); return {{status:r.status, body:await r.text()}}; }}"""
    )
    if sd.get("status") != 200:
        print("❌ static-data fetch failed")
        await drv._cdp_pw.stop()
        return
    d = json.loads(sd["body"])
    bid = d.get("firstBid")
    ask = d.get("firstAsk")
    tick = set_tick(float(d.get("close") or 0))
    print(f"📊 BCPG: bid={bid} ask={ask} close={d.get('close')} tick={tick}")
    if bid is None:
        print("❌ no live bid")
        await drv._cdp_pw.stop()
        return
    passive = round(float(bid) - tick, 2)
    change_price = round(passive - tick, 2)
    print(f"🎯 place={passive} change-to={change_price}")

    # 2. place passive BUY
    cap.set_phase("streaming_place")
    res = await drv.execute_order(SYMBOL, SIDE, VOLUME, passive, bypass_dry_run=True)
    print(f"📝 place: {json.dumps(res, ensure_ascii=False, default=str)[:400]}")
    order_no = res.get("broker_order_no")
    if not res.get("success") or not order_no:
        print("❌ place failed")
        await drv._cdp_pw.stop()
        return
    await page.wait_for_timeout(2000)

    # 3. verify resting via DGW API (matched 0)
    cap.set_phase("streaming_verify")
    chk = await page.evaluate(
        """async () => { const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/orders', {credentials:'include'}); return await r.text(); }"""
    )
    try:
        orders = json.loads(chk)
        mine = [o for o in orders if str(o.get("orderNo")) == str(order_no)]
        if mine:
            m = mine[0]
            print(f"🔍 resting: matched={m.get('matched')} balance={m.get('balance')} status={m.get('showOrderStatus')}")
            if m.get("matched", 0) > 0:
                print("⚠️ ORDER MATCHED — aborting (do not change a matched order)")
                await drv._cdp_pw.stop()
                return
    except Exception as ex:
        print(f"⚠️ verify parse: {ex}")

    # 4. find row <ul> containing order_no, click native Change (li.css-phnjeo)
    cap.set_phase("streaming_change_click")
    click_res = await page.evaluate(
        """(orderNo) => {
            const lis = [...document.querySelectorAll('li')];
            const li = lis.find(e => (e.textContent||'').trim() === String(orderNo));
            if (!li) return {ok:false, reason:'order-number li not found'};
            const ul = li.closest('ul');
            if (!ul) return {ok:false, reason:'row ul not found'};
            const change = ul.querySelector('li.css-phnjeo, li[class*="phnjeo"]');
            if (!change) return {ok:false, reason:'change li not found in row', rowHtml: ul.outerHTML.slice(0,1500)};
            change.click();
            return {ok:true, changeText: change.textContent.trim(), rowHtml: ul.outerHTML.slice(0,1500)};
        }""",
        str(order_no),
    )
    print(f"🔧 change click: {json.dumps(click_res, ensure_ascii=False)[:600]}")
    if not click_res.get("ok"):
        await drv._cdp_pw.stop()
        return
    await page.wait_for_timeout(2000)

    # 5. dump the Change dialog HTML (discovery)
    cap.set_phase("streaming_change_dialog")
    dialog = await page.evaluate(
        """() => {
            const sels = ['[role="dialog"]', '[class*="modal"]', '[class*="dialog"]', '[class*="popup"]', '[class*="overlay"]', '[class*="Modal"]', '[class*="Dialog"]'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) return {sel: s, html: el.outerHTML};
            }
            // fallback: body tail (dialog often appended at end)
            return {sel: '(none)', html: document.body.innerHTML.slice(-6000)};
        }"""
    )
    out_path = os.path.join(REPO, "data", "har", "kss_change_dialog.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(dialog.get("html", ""))
    print(f"💾 dialog HTML ({dialog.get('sel')}) -> {out_path} ({len(dialog.get('html',''))} chars)")
    print("=== DIALOG (first 3500 chars) ===")
    print(dialog.get("html", "")[:3500])

    # NOTE: intentionally NOT confirming/cancelling — Stage B continues.
    print(f"⏸ STAGE A done. Order {order_no} resting @ {passive}; change-to={change_price}; dialog left open.")
    await drv._cdp_pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
