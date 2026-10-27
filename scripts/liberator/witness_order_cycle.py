#!/usr/bin/env python3
"""Liberator direct-API order cycle witness: place → change → cancel (anti-mock re-read).

Runs the JS-first place/change/cancel snippets against the live CDP daemon (9334),
attaching to the already-authenticated headed browser (no re-login, no OTP).

Default (no --live): pre-place preview only (fee calc) — nothing submitted.
--live: full place → change → cancel cycle with anti-mock verification at each step.
        Requires settings.DRY_RUN_MODE=False and a human watching the screen.

Anti-mock: snapshots open orderNos BEFORE the cycle; after each step the order is
re-read from /va/order and matched by orderNo (never by naive symbol/price match),
so a same-price order already on the board (e.g. the morning's #15602) can't be
confused with the fresh witness order.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/liberator/witness_order_cycle.py --symbol BCPG --volume 100
  PYTHONPATH=. .venv/bin/python scripts/liberator/witness_order_cycle.py --live --symbol BCPG --volume 100
"""
import argparse
import asyncio
import json
import sys

from app.core.config import settings
from scripts.broker_cdp.js_runner import adjust_price_by_ticks, get_quote_js, run_snippet


async def read_orders() -> dict:
    res = await run_snippet("liberator", snippet_name="liberator_read", timeout_s=60)
    return res.get("data") or {}


def find_new_order(list_, before_nos: set, symbol: str, side_code: str, price: float):
    """Return the order dict that is NOT in the before-snapshot and matches the placed order."""
    hits = [
        o for o in list_
        if String(o.get("orderNo")) not in before_nos
        and (o.get("symbol") or o.get("stockSymbol")) == symbol
        and o.get("side") == side_code
        and o.get("status") == "PENDING"
        and parse_float(o.get("price")) == price
    ]
    return hits[-1] if hits else None


def parse_float(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def String(v):
    return "" if v is None else str(v)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BCPG")
    ap.add_argument("--side", default="Buy", choices=["Buy", "Sell"])
    ap.add_argument("--volume", type=int, default=100)
    ap.add_argument("--price", type=float, default=None, help="override limit price (else passive bid-2 ticks)")
    ap.add_argument("--live", action="store_true", help="real place→change→cancel (human must be watching)")
    args = ap.parse_args()

    symbol = args.symbol.strip().upper()
    volume = args.volume
    pin = settings.LIBERATOR_PIN
    account = settings.LIBERATOR_ACCOUNT_NO

    if not pin:
        print("ERROR: LIBERATOR_PIN not set in .env")
        sys.exit(2)
    if volume <= 0 or volume % 100 != 0:
        print("ERROR: volume must be a positive multiple of 100")
        sys.exit(2)
    if args.live and settings.DRY_RUN_MODE:
        print("ERROR: --live requires DRY_RUN_MODE=false in .env (currently true)")
        sys.exit(2)

    q = await get_quote_js("liberator", symbol)
    if not q.get("success"):
        print("QUOTE FAILED:", json.dumps(q, ensure_ascii=False))
        sys.exit(2)
    bid = q.get("bid_1") or q.get("last")
    offer = q.get("offer_1") or q.get("last")
    print(f"QUOTE {symbol}: bid={bid} offer={offer} last={q.get('last')} (source={q.get('source')})")

    if args.price is None:
        # bid-2 ticks: passively queued AND distinct from any order already at bid-1 (e.g. #15602)
        price = adjust_price_by_ticks(float(bid), steps=-2) if bid else None
    else:
        price = args.price
    if not price or price <= 0:
        print("ERROR: cannot compute passive price")
        sys.exit(2)
    change_price = adjust_price_by_ticks(float(price), steps=-1)

    print(f"PLAN: {args.side} {symbol} {volume} @ {price}  (change → {change_price})")
    print(f"accountNo={account}  DRY_RUN_MODE={settings.DRY_RUN_MODE}")

    # --- before snapshot (anti-mock baseline) ---
    before = await read_orders()
    before_nos = set(before.get("orderNos") or [])
    print(f"\nBEFORE: {len(before_nos)} open order(s): {sorted(before_nos)}")

    place_arg = {
        "symbol": symbol, "side": args.side, "volume": volume,
        "price": price, "pin": pin, "accountNo": account,
        "dryRun": not args.live,
    }
    place_res = await run_snippet("liberator", snippet_name="liberator_place", arg=place_arg, timeout_s=60)
    print("\n=== PLACE ===")
    print(json.dumps(place_res, ensure_ascii=False, indent=2, default=str))

    if not args.live:
        print("\nDRY-RUN complete: pre-place preview only, nothing submitted.")
        return

    data = place_res.get("data") or {}
    if not data.get("ok"):
        print("\nFAIL-CLOSED: place rejected by broker — aborting.")
        sys.exit(1)

    side_code = "B" if args.side == "Buy" else "S"
    new_order = find_new_order(data.get("list", []), before_nos, symbol, side_code, price)

    # one retry: the immediate re-read can miss the order on a slow board
    if new_order is None:
        await asyncio.sleep(2.0)
        recheck = await read_orders()
        new_order = find_new_order(recheck.get("list", []), before_nos, symbol, side_code, price)

    if new_order is None:
        print("\nFAIL-CLOSED: placed order not confirmed on board (no new PENDING order) — nothing to change/cancel.")
        sys.exit(1)

    order_no = String(new_order.get("orderNo"))
    print(f"\nPLACED (anti-mock): orderNo={order_no} price={new_order.get('price')} status={new_order.get('status')}")

    # --- change ---
    chg_arg = {"orderNo": order_no, "price": change_price, "volume": volume, "pin": pin}
    chg_res = await run_snippet("liberator", snippet_name="liberator_change", arg=chg_arg, timeout_s=60)
    print("\n=== CHANGE ===")
    print(json.dumps(chg_res, ensure_ascii=False, indent=2, default=str))
    chg_data = chg_res.get("data") or {}
    if not chg_data.get("ok") or not chg_data.get("verified"):
        print("\nFAIL-CLOSED: change not verified — leaving order OPEN for manual review.")
        sys.exit(1)
    print(f"\nCHANGED: orderNo={order_no} → {chg_data.get('changedPrice')} verified={chg_data.get('verified')}")

    # --- cancel ---
    can_arg = {"orderNo": order_no, "pin": pin}
    can_res = await run_snippet("liberator", snippet_name="liberator_cancel", arg=can_arg, timeout_s=60)
    print("\n=== CANCEL ===")
    print(json.dumps(can_res, ensure_ascii=False, indent=2, default=str))
    can_data = can_res.get("data") or {}
    if not can_data.get("ok") or not can_data.get("verified"):
        print("\nFAIL-CLOSED: cancel not verified — check the order on screen.")
        sys.exit(1)
    print(f"\nCANCELED: orderNo={order_no} cancelled={can_data.get('cancelled')} balance={can_data.get('balance')} verified={can_data.get('verified')}")
    print("\n✅ FULL CYCLE PASSED: place → change → cancel, anti-mock verified at each step.")


if __name__ == "__main__":
    asyncio.run(main())
