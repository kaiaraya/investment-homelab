#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.0a order-capture: COVER TU 3100 on Streaming (margin 3024959).

Capture-only (short stays open): place COVER passive -> native Change -> cancel,
recording every XHR/Fetch/PostBack to data/har/kss_order.har + endpoints json.

The native Change dialog selectors are not yet mapped (per the D1 gap), so this
pass drives Change best-effort: it dumps the order-row HTML + any dialog that
opens, fills the price if the inputs are found, and always proceeds to cancel.
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from app.browser.streaming_driver import StreamingDriver  # noqa: E402
from scripts.broker_cdp.har_capture import HarCapture, save  # noqa: E402

SYMBOL = "TU"
VOLUME = 3100
SIDE = "COVER"
STATIC_DATA_URL = "https://apigwcld.settrade.com/api/marketdata/v4/029/static-data/{sym}?market=E"

CHANGE_LINK_SELECTORS = [
    "li.css-phnjeo",
    "li[class*='phnjeo']",
    "span[style*='underline']",
    "a:has-text('Change')",
    "li:has-text('Change')",
    "button:has-text('Change')",
    "li:has-text('แก้ไข')",
    "button:has-text('แก้ไข')",
]


def tick_for(price: float, spread_list) -> float:
    tick = 0.01
    for tier in spread_list or []:
        if price >= float(tier.get("lowerLimit", 0)):
            tick = float(tier.get("tick", tick))
    return tick


async def read_static_data(page, sym):
    js = f"""async () => {{
        const r = await fetch('{STATIC_DATA_URL.format(sym=sym)}', {{credentials:'include'}});
        return {{status: r.status, body: await r.text()}};
    }}"""
    res = await page.evaluate(js)
    if res.get("status") != 200:
        return None
    return json.loads(res["body"])


async def find_order_row(page, order_no, symbol):
    """Locate the View Order row for this order; return (tr, row_html)."""
    await page.wait_for_timeout(1500)
    tr = await page.query_selector(f"tr:has-text('{order_no}')")
    if not tr:
        tr = await page.query_selector(f"tr:has-text('{symbol}'):has-text('Queuing')")
    if not tr:
        tr = await page.query_selector(f"tr:has-text('{symbol}'):has-text('Open')")
    if not tr:
        return None, ""
    html = await tr.evaluate("el => el.outerHTML")
    return tr, html


async def try_native_change(page, tr, new_price, pin):
    """Best-effort native in-place Change. Returns a dict describing what happened."""
    found = None
    for sel in CHANGE_LINK_SELECTORS:
        el = await tr.query_selector(sel)
        if el and await el.is_visible():
            found = el
            break
    if not found:
        # fall back: any underlined element in the row
        els = await tr.evaluate(
            """el => [...el.querySelectorAll('li,span,a,button')]
                .filter(e => getComputedStyle(e).textDecorationLine.includes('underline'))
                .map(e => e.outerHTML.slice(0, 200))"""
        )
        return {"ok": False, "reason": "no change link found", "row_underlined": els[:5]}

    await found.click()
    await page.wait_for_timeout(1500)

    # dump whatever dialog opened
    dialog_html = await page.evaluate(
        """() => {
            const d = document.querySelector('[role="dialog"], .modal, [class*="modal"], [class*="dialog"], [class*="popup"]');
            return d ? d.outerHTML.slice(0, 3000) : '(no dialog element found)';
        }"""
    )

    # try to fill a price input inside any dialog
    price_filled = False
    for psel in ["input[type='number']", "input[name*='price' i]", "input[placeholder*='price' i]", "input[placeholder*='ราคา' i]"]:
        el = await page.query_selector(psel)
        if el and await el.is_visible():
            try:
                await el.fill(f"{new_price:.2f}")
                price_filled = True
                break
            except Exception:
                continue
    if not price_filled:
        return {"ok": False, "reason": "change dialog price input not found", "dialog_html": dialog_html}

    # PIN (best-effort)
    pin_el = await page.query_selector("#pin, input[name*='pin' i], input[type='password']")
    if pin_el and await pin_el.is_visible() and pin:
        try:
            await pin_el.fill(pin)
        except Exception:
            pass

    # confirm
    confirmed = False
    for csel in ["button:has-text('Confirm')", "button:has-text('ยืนยัน')", "button:has-text('OK')", "button[type='submit']"]:
        el = await page.query_selector(csel)
        if el and await el.is_visible():
            await el.click()
            confirmed = True
            break
    await page.wait_for_timeout(1500)
    return {"ok": confirmed, "price_filled": True, "dialog_html": dialog_html[:1500]}


async def main():
    from app.core.config import settings

    drv = StreamingDriver()
    if not await drv.connect_cdp():
        print("❌ connect_cdp failed (daemon down?)")
        return
    page = drv.page_override
    print(f"📍 attached: {page.url}")

    cap = HarCapture()
    cap.attach(page)
    pin = settings.KRUNGSRI_PIN or settings.TRADING_PIN

    # 1. live quote -> passive price
    cap.set_phase("quote_read")
    sd = await read_static_data(page, SYMBOL)
    if not sd:
        print("❌ static-data fetch failed")
        await drv._cdp_pw.stop()
        return
    first_bid = sd.get("firstBid")
    first_ask = sd.get("firstAsk")
    tick = tick_for(float(sd.get("close") or 0), sd.get("spreadList"))
    print(f"📊 {SYMBOL}: firstBid={first_bid} firstAsk={first_ask} close={sd.get('close')} tick={tick}")
    if first_bid is None:
        print("❌ no live bid yet — market not open?")
        await drv._cdp_pw.stop()
        return
    passive = round(float(first_bid) - tick, 2)
    change_price = round(float(first_bid) - 2 * tick, 2)
    print(f"🎯 passive COVER = {passive}, change-to = {change_price}")

    # 2. place COVER
    cap.set_phase("streaming_cover_place")
    res = await drv.execute_order(SYMBOL, SIDE, VOLUME, passive, bypass_dry_run=True)
    order_no = res.get("broker_order_no")
    print(f"📝 place: {json.dumps(res, ensure_ascii=False, default=str)[:400]}")
    await page.wait_for_timeout(2000)

    # 3. verify + find row
    cap.set_phase("streaming_cover_verify")
    await drv.switch_tab("order_status")
    tr, row_html = await find_order_row(page, order_no, SYMBOL)
    print(f"🔍 order row found: {bool(tr)}")
    if row_html:
        print("ROW HTML:\n" + row_html[:2000])

    # 4. native Change (best-effort)
    cap.set_phase("streaming_cover_change")
    change_info = {"ok": False, "reason": "no row"}
    if tr:
        change_info = await try_native_change(page, tr, change_price, pin)
    print(f"🔧 native change: {json.dumps(change_info, ensure_ascii=False)[:800]}")

    # 5. cancel
    cap.set_phase("streaming_cover_cancel")
    cancel_res = await drv.cancel_order(order_no or "", SYMBOL, bypass_dry_run=True)
    print(f"🗑 cancel: {json.dumps(cancel_res, ensure_ascii=False, default=str)[:300]}")
    await page.wait_for_timeout(2000)

    # 6. verify cancelled
    cap.set_phase("streaming_cover_verify2")
    orders2 = await drv.scrape_unmatched_orders()
    still = [o for o in orders2 if str(o.get("broker_order_no")) == str(order_no)]
    print(f"🔍 after cancel: {len(orders2)} open, order_no still present: {len(still)}")

    save("kss_order", cap, "KSS Streaming COVER TU order capture")
    await drv._cdp_pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
