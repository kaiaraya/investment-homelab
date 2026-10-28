#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-market broker read-only snapshot CLI (SNAP.1).

Captures authoritative pre-market snapshot directly from broker REST endpoints
(KSS and Liberator) via CDP session daemons without touching internal DB.

Usage:
  .venv/bin/python scripts/pre_market_snapshot.py --all --dry-run
  .venv/bin/python scripts/pre_market_snapshot.py --all
  .venv/bin/python scripts/pre_market_snapshot.py --broker kss
  .venv/bin/python scripts/pre_market_snapshot.py --broker lib

Exit codes:
  0 = PASS / Snapshot captured
  1 = FAIL_CLOSED (broker down, auth error, or reconcile failure)
  2 = Usage error
"""
import argparse
import asyncio
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.services.broker_snapshot import broker_snapshot_service


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pre-market broker read-only snapshot CLI (SNAP.1)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Snapshot all brokers (KSS and Liberator)",
    )
    parser.add_argument(
        "--broker",
        choices=["kss", "lib", "liberator"],
        help="Snapshot specific broker",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform read and reconcile without writing to disk",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=os.path.join(REPO_ROOT, "data", "snapshots"),
        help="Directory to store snapshot JSON files (default: data/snapshots)",
    )
    return parser.parse_args()


async def main_async(args):
    if not args.all and not args.broker:
        print("Error: Must specify --all or --broker [kss|lib]", file=sys.stderr)
        return 2

    brokers = ["kss", "lib"] if args.all else [args.broker]

    print(f"[SNAP.1] Fetching snapshot for brokers: {brokers} (dry_run={args.dry_run})...")
    ok, snapshot, saved_path = await broker_snapshot_service.create_snapshot(
        brokers=brokers,
        dry_run=args.dry_run,
        snapshot_dir=args.snapshot_dir,
    )

    # Print clean JSON
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))

    if not ok:
        print(f"\n[FAIL_CLOSED] Snapshot failed! Status: {snapshot.get('status')}", file=sys.stderr)
        for err in snapshot.get("errors", []):
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"\n[SUCCESS] Snapshot verified & reconciled. Status: {snapshot.get('status')}")
    if saved_path:
        print(f"Saved snapshot: {saved_path}")
    elif args.dry_run:
        print("[DRY-RUN] No file written (dry-run mode).")

    return 0


def main():
    args = parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
