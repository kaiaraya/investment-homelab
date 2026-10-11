"""
Live E2E runner: amend a resting Liberator order IN PLACE via the native `Change` control
(ต่อราคา) — a thin wrapper around `LiberatorDriver.change_order()`.

SAFETY:
  * This DOES submit a real order amendment. The PIN is read from `settings.LIBERATOR_PIN`
    and is never printed or logged.
  * It aborts without firing any SMS OTP when the saved session is not authenticated.
  * `--dry-run` only reports the current row and never submits.

Usage:
    .venv/bin/python scripts/liberator/run_change_order_live.py 11894 11.70 --dry-run
    .venv/bin/python scripts/liberator/run_change_order_live.py 11894 11.70
    .venv/bin/python scripts/liberator/run_change_order_live.py 11894 11.70 --new-volume 2000

Exit code: 0 = PASS (amendment verified on the same order number), 1 = FAIL / aborted.
"""

import argparse
import asyncio
import json
import sys

from app.brokers.liberator.driver import liberator_driver


async def _read_order(order_no: str):
    data = await liberator_driver.scrape_portfolio(force_refresh=True)
    return next(
        (o for o in data.get("orders", []) if str(o.get("order_no")) == str(order_no)), None
    )


async def main() -> int:
    ap = argparse.ArgumentParser(description="Amend a Liberator order in place (live).")
    ap.add_argument("order_no", help="broker order number, e.g. 11894")
    ap.add_argument("new_price", type=float, help="new limit price")
    ap.add_argument("--new-volume", type=int, default=None, help="optional new volume (board lot)")
    ap.add_argument("--dry-run", action="store_true", help="report only; never submit")
    args = ap.parse_args()

    await liberator_driver.launch_browser(resume_state=True)
    print(f"URL   : {liberator_driver.current_url}")

    before = await _read_order(args.order_no)
    print(f"BEFORE: {json.dumps(before, ensure_ascii=False)}")
    if before is None:
        print(f"ABORT: order #{args.order_no} is not in the Liberator order table.")
        await liberator_driver.close()
        return 1

    if args.dry_run:
        print("DRY-RUN: no amendment submitted.")
        await liberator_driver.close()
        return 0

    res = await liberator_driver.change_order(
        args.order_no, args.new_price, new_volume=args.new_volume
    )
    print(f"RESULT: {json.dumps(res, ensure_ascii=False)}")

    after = await _read_order(args.order_no)
    print(f"AFTER : {json.dumps(after, ensure_ascii=False)}")
    await liberator_driver.close()
    return 0 if res.get("success") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
