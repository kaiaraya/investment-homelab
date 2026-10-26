#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.4a STAGE C — Streaming native in-place Change capture (Playwright-driven).

Places a fresh passive BUY via the DGW API (real orderNo), expands the row's
inline Change editor, fills the new price with Playwright fill() (proper React
event), clicks the row Submit, captures the XHR, verifies, then cancels.
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from app.core.config import settings  # noqa: E402
from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402
from scripts.broker_cdp.har_capture import HarCapture, save  # noqa: E402

SYMBOL = "BCPG"
VOLUME = 100
ACCT = "3024959"
STATIC_DATA_URL = "https://apigwcld.settrade.com/api/marketdata/v4/029/static-data/{sym}?market=E"
ORDERS_URL = f"https://apigw.settrade.com/api/dgw/v3/029/accounts/{ACCT}/orders"

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


async def read_orders(page):
    txt = await page.evaluate(
        f"""async () => {{ const r = await fetch('{ORDERS_URL}', {{credentials:'include'}}); return await r.text(); }}"""
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
    pin = settings.KRUNGSRI_PIN or settings.TRADING_PIN

    # 1. static data -> passive price
    sd = await page.evaluate(
        f"""async () => {{ const r = await fetch('{STATIC_DATA_URL.format(sym=SYMBOL)}', {{credentials:'include'}}); return {{status:r.status, body:await r.text()}}; }}"""
    )
    d = json.loads(sd["body"])
    bid = d.get("firstBid")
    tick = set_tick(float(d.get("close") or 0))
    passive = round(float(bid) - tick, 2)
    change_price = round(passive - tick, 2)
    print(f"📊 BCPG bid={bid} tick={tick} -> place={passive} change-to={change_price}")

    # 2. place via DGW API (real orderNo)
    cap.set_phase("streaming_place_api")
    place = await page.evaluate(
        """async ({price, pin}) => {
            const body = {side:'Buy', symbol:'BCPG', trusteeIdType:'Local', volume:100,
                          price, priceType:'Limit', validityType:'Day', bypassWarning:false,
                          pin, positionType:''};
            const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/orders', {
                method:'POST', credentials:'include',
                headers:{'content-type':'application/json'}, body: JSON.stringify(body)
            });
            return {status: r.status, body: await r.text()};
        }""",
        {"price": passive, "pin": pin},
    )
    print(f"📝 place: {json.dumps(place, ensure_ascii=False)[:400]}")
    order_no = None
    try:
        order_no = str(json.loads(place["body"]).get("orderNo"))
    except Exception:
        pass
    if not order_no:
        print("❌ place failed (no orderNo)")
        await browser.close()
        await pw.stop()
        return
    print(f"📝 real orderNo = {order_no}")
    await page.wait_for_timeout(1500)

    # 3. verify resting
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == order_no]
    if not mine:
        print("❌ order not found after place")
        await browser.close()
        await pw.stop()
        return
    print(f"🔍 resting: price={mine[0].get('price')} matched={mine[0].get('matched')}")

    # 4. click native Change (expand inline editor)
    cap.set_phase("streaming_change_click")
    row = page.locator(f"ul:has(li:text-is('{order_no}'))").first
    try:
        await row.locator("li.css-phnjeo, li[class*='phnjeo']").first.click()
        await page.wait_for_timeout(1500)
        print("🔧 clicked Change")
    except Exception as ex:
        print(f"❌ change click: {ex}")
        await browser.close()
        await pw.stop()
        return

    # 5. fill new price via Playwright (proper React events)
    cap.set_phase("streaming_change_fill")
    price_input = row.locator('input[name="change-order-price-input"]').first
    try:
        await price_input.fill(str(change_price))
        await page.wait_for_timeout(800)
        print(f"✏️ filled price = {await price_input.input_value()}")
    except Exception as ex:
        print(f"❌ price fill: {ex}")
        await browser.close()
        await pw.stop()
        return

    # 6. inspect Submit button state, then click
    submit = row.locator("button", has_text="Submit").first
    try:
        print(f"🚀 submit disabled? {await submit.is_disabled()} text='{(await submit.inner_text()).strip()}'")
    except Exception as ex:
        print(f"⚠️ submit inspect: {ex}")
    cap.set_phase("streaming_change_submit")
    await submit.click()
    await page.wait_for_timeout(2500)

    # 7. verify via API
    cap.set_phase("streaming_change_verify")
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == order_no]
    if mine:
        print(f"🔍 after: price={mine[0].get('price')} matched={mine[0].get('matched')} status={mine[0].get('showOrderStatus')}")
    else:
        print("⚠️ order gone after change")

    # 8. cancel (cleanup)
    cap.set_phase("streaming_cancel")
    cancel = await page.evaluate(
        """async ({orderNo, pin}) => {
            const body = {orders:[{sequenceNo:'0', orderNo, symbol:'BCPG', tradeDate:'2026-10-26'}], pin};
            const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/cancel', {
                method:'PATCH', credentials:'include',
                headers:{'content-type':'application/json'}, body: JSON.stringify(body)
            });
            return {status: r.status, body: await r.text()};
        }""",
        {"orderNo": order_no, "pin": pin},
    )
    print(f"🗑 cancel: {json.dumps(cancel, ensure_ascii=False)[:300]}")
    await page.wait_for_timeout(1500)
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == order_no]
    print(f"🔍 after cancel: status={mine[0].get('showOrderStatus') if mine else 'GONE'}")

    save("kss_change", cap, "KSS Streaming native Change (BCPG BUY 100)")
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
