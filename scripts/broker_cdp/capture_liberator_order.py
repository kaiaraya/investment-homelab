#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.4a — Liberator place/change/cancel HAR capture (BUY BCPG 100, passive).

Drives the live human-visible Liberator WebTrade session via the CDP daemon
(9334) and records every XHR for place -> change -> cancel. Passive BUY one
tick below Best Bid so it stays queued (never matches), then cancelled.
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from app.brokers.liberator.driver import LiberatorDriver  # noqa: E402
from scripts.broker_cdp.har_capture import HarCapture, save  # noqa: E402

SYMBOL = "BCPG"
VOLUME = 100
SIDE = "BUY"

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
    drv = LiberatorDriver()
    if not await drv.connect_cdp():
        print("❌ connect_cdp failed (daemon 9334 down?)")
        return
    page = drv.page
    print(f"📍 Liberator attached: {page.url}")

    cap = HarCapture()
    cap.attach(page)

    # 1. quote -> passive price (1 tick below bid, never matches)
    cap.set_phase("liberator_quote")
    q = await drv.get_market_bid_offer(SYMBOL)
    print(f"📊 quote: {json.dumps(q, ensure_ascii=False)}")
    bid = q.get("bid_1")
    offer = q.get("offer_1")
    if not q.get("success") or bid is None:
        print("❌ no live bid — aborting (fail-closed)")
        await drv.close()
        return
    tick = set_tick(float(bid))
    passive = round(float(bid) - tick, 2)
    change_price = round(passive - tick, 2)
    print(f"🎯 bid={bid} offer={offer} tick={tick} -> place={passive} change={change_price}")

    # 2. place passive BUY
    cap.set_phase("liberator_place")
    place = await drv.execute_order(SYMBOL, SIDE, VOLUME, passive, bypass_dry_run=True)
    print(f"📝 place: {json.dumps(place, ensure_ascii=False, default=str)[:500]}")
    order_no = place.get("broker_order_no")
    if not place.get("success") or not order_no:
        print("❌ place failed — aborting")
        await drv.close()
        return
    await page.wait_for_timeout(1500)

    # 3. change in place (more passive)
    cap.set_phase("liberator_change")
    change = await drv.change_order(str(order_no), change_price, bypass_dry_run=True)
    print(f"🔧 change: {json.dumps(change, ensure_ascii=False, default=str)[:500]}")
    await page.wait_for_timeout(1500)

    # 4. cancel
    cap.set_phase("liberator_cancel")
    cancel = await drv.cancel_order(str(order_no), bypass_dry_run=True)
    print(f"🗑 cancel: {json.dumps(cancel, ensure_ascii=False, default=str)[:500]}")
    await page.wait_for_timeout(1500)

    save("liberator_order", cap, "Liberator place/change/cancel (BCPG BUY 100)")
    await drv.close()


if __name__ == "__main__":
    asyncio.run(main())
