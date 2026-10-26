#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P.4a STAGE D — Streaming native in-place Change (full flow, capture XHR).

Full native flow: Change (inline editor) -> fill price -> Submit -> "Change
Order Confirmation" modal -> click "Change" -> XHR. Uses the resting order
11014863, captures the change XHR, verifies, then cancels.
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

ORDER_NO = "11014863"
NEW_PRICE = "6.70"
ACCT = "3024959"
ORDERS_URL = f"https://apigw.settrade.com/api/dgw/v3/029/accounts/{ACCT}/orders"


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

    # 0. dismiss any leftover modal
    try:
        modal = page.locator('.ReactModal__Content[role="dialog"]').first
        if await modal.count():
            await modal.locator("button", has_text="Cancel").first.click(timeout=5000)
            await page.wait_for_timeout(1000)
            print("🧹 dismissed leftover modal")
    except Exception as ex:
        print(f"⚠️ modal dismiss: {ex}")

    # 1. confirm order resting
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == ORDER_NO]
    if not mine:
        print(f"❌ order {ORDER_NO} not open")
        await browser.close()
        await pw.stop()
        return
    print(f"🔍 before: price={mine[0].get('price')} matched={mine[0].get('matched')} status={mine[0].get('showOrderStatus')}")

    # 2. click Change (expand inline editor)
    cap.set_phase("streaming_change_click")
    row = page.locator(f"ul:has(li:text-is('{ORDER_NO}'))").first
    await row.locator("li.css-phnjeo, li[class*='phnjeo']").first.click(timeout=10000)
    await page.wait_for_timeout(1500)
    print("🔧 clicked Change")

    # 3. fill new price
    cap.set_phase("streaming_change_fill")
    await row.locator('input[name="change-order-price-input"]').first.fill(NEW_PRICE)
    await page.wait_for_timeout(800)
    print(f"✏️ filled price = {await row.locator('input[name=\"change-order-price-input\"]').first.input_value()}")

    # 4. click inline Submit -> opens confirmation modal
    cap.set_phase("streaming_change_submit")
    await row.locator("button", has_text="Submit").first.click(timeout=10000)
    await page.wait_for_timeout(2000)
    print("🚀 clicked inline Submit")

    # 5. read the confirmation modal
    modal = page.locator('.ReactModal__Content[role="dialog"]').first
    try:
        mtext = (await modal.inner_text()).strip()
        print(f"📋 modal: {mtext[:300]}")
    except Exception as ex:
        print(f"⚠️ modal read: {ex}")

    # 6. click "Change" in the modal -> fires XHR
    cap.set_phase("streaming_change_confirm")
    await modal.locator("button", has_text="Change").first.click(timeout=10000)
    await page.wait_for_timeout(2500)
    print("✅ clicked modal Change")

    # 7. verify
    cap.set_phase("streaming_change_verify")
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == ORDER_NO]
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
        {"orderNo": ORDER_NO, "pin": pin},
    )
    print(f"🗑 cancel: {json.dumps(cancel, ensure_ascii=False)[:250]}")
    await page.wait_for_timeout(1500)
    orders = await read_orders(page)
    mine = [o for o in orders if str(o.get("orderNo")) == ORDER_NO]
    print(f"🔍 after cancel: status={mine[0].get('showOrderStatus') if mine else 'GONE'}")

    save("kss_change", cap, "KSS Streaming native Change (BCPG BUY 100)")
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
