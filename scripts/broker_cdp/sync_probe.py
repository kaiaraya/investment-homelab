#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live read-only sync probe — B.3 verification.

Scrapes balance + holdings from the broker's live CDP tab and (unless ``--dry-run``)
writes them into ``broker_accounts`` + ``positions`` via ``sync_portfolio_from_cdp``.

Read-only with respect to the broker: it never submits an order, never switches account,
never clicks anything that mutates the broker ledger (it only switches the Streaming page
to its Portfolio tab, exactly like the existing read path).

Usage:
    .venv/bin/python scripts/broker_cdp/sync_probe.py kss [--dry-run]
    .venv/bin/python scripts/broker_cdp/sync_probe.py lib [--dry-run]
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
    parser = argparse.ArgumentParser(description="Live CDP portfolio sync probe (B.3)")
    parser.add_argument("broker", choices=["kss", "lib", "liberator"])
    parser.add_argument("--dry-run", action="store_true", help="scrape only, no DB write")
    args = parser.parse_args()

    from app.services.broker_cdp.sync_service import (
        scrape_portfolio_from_cdp,
        sync_portfolio_from_cdp,
    )

    if args.dry_run:
        snap = await scrape_portfolio_from_cdp(args.broker)
        print("=== DRY-RUN scrape (no DB write) ===")
        print(json.dumps({k: v for k, v in snap.items() if k != "holdings"},
                         ensure_ascii=False, indent=2, default=str))
        print(f"holdings: {len(snap.get('holdings', []))} row(s)")
        for h in snap.get("holdings", []):
            print("  ", json.dumps(h, ensure_ascii=False, default=str))
        return 0

    result = await sync_portfolio_from_cdp(args.broker)
    print("=== SYNC result (written to DB) ===")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
