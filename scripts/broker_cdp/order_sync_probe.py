#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live read-only order-ledger sync probe — B.7 verification.

Scrapes the broker's order ledger from the live CDP tab and diffs it against the
local ``orders`` table; ledger rows whose ``broker_order_no`` isn't already known
are recorded with ``source='manual_sync'`` (a trade the human placed manually on
the frontend).

Read-only with respect to the broker: it never submits, cancels, or clicks anything
that mutates the ledger — it only reads the already-rendered order panel/grid.

Usage:
    .venv/bin/python scripts/broker_cdp/order_sync_probe.py kss [--dry-run]
    .venv/bin/python scripts/broker_cdp/order_sync_probe.py lib [--dry-run]
"""
import argparse
import asyncio
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Live CDP order-ledger sync probe (B.7)")
    parser.add_argument("broker", choices=["kss", "lib", "liberator"])
    parser.add_argument("--dry-run", action="store_true", help="scrape only, no DB write")
    args = parser.parse_args()

    from app.services.broker_cdp.sync_service import (
        scrape_orders_from_cdp,
        sync_orders_from_cdp,
    )

    if args.dry_run:
        snap = await scrape_orders_from_cdp(args.broker)
        print("=== DRY-RUN order-ledger scrape (no DB write) ===")
        print(json.dumps({k: v for k, v in snap.items() if k != "orders"},
                         ensure_ascii=False, indent=2, default=str))
        print(f"orders: {len(snap.get('orders', []))} row(s)")
        for o in snap.get("orders", []):
            print("  ", json.dumps(o, ensure_ascii=False, default=str))
        return 0

    result = await sync_orders_from_cdp(args.broker)
    print("=== ORDER SYNC result (manual orders written to DB) ===")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
