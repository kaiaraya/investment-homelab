#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read TU quote + open orders for margin acct 3024959 via the browser's own session."""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")
    await page.bring_to_front()

    quote_js = r"""async () => {
        const r = await fetch('https://apigwcld.settrade.com/api/marketdata/v4/029/static-data/TU?market=E', {credentials:'include'});
        return {status: r.status, body: await r.text()};
    }"""
    orders_js = r"""async () => {
        const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/orders', {credentials:'include'});
        return {status: r.status, body: await r.text()};
    }"""
    acct_js = r"""async () => {
        const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959', {credentials:'include'});
        return {status: r.status, body: await r.text()};
    }"""

    quote = await page.evaluate(quote_js)
    orders = await page.evaluate(orders_js)
    acct = await page.evaluate(acct_js)
    out = {"tu_quote": quote, "orders_3024959": orders, "acct_3024959": acct}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(os.path.join(REPO, "data", "har", "tu_state.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
