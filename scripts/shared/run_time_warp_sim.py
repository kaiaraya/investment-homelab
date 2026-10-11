#!/usr/bin/env python3
"""
Time Warp & Scenario Simulator CLI Runner.
Allows testing Phase 3 timed events (10:15, 11:00, 15:30, 16:35) in fast-forward mode:
- 5 Comprehensive Scenarios (Normal, TP/SL, Volatility/Rebound, Unmatched Negotiation, SBL Held Over EOD)
- Dual HITL Mode: Auto-Pilot (automated fast regression) vs Interactive (pauses for LINE/console)
- Accelerated Virtual Clock (10x, 60x, or instant fast-forward)

Usage:
  python scripts/run_time_warp_sim.py --scenario 1
  python scripts/run_time_warp_sim.py --scenario all
  python scripts/run_time_warp_sim.py --scenario 4 --hitl auto
"""

import sys
import os
import asyncio
import argparse
import logging

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.virtual_clock import virtual_clock
from app.services.scenario_matrix import scenario_matrix
from app.db.init_db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TimeWarpCLI")


async def run_single_scenario(scenario_num: int, hitl_mode: str):
    print("\n" + "=" * 75)
    print(f" 🚀 EXECUTING SCENARIO {scenario_num} (HITL Mode: {hitl_mode.upper()})")
    print("=" * 75)

    if scenario_num == 1:
        res = await scenario_matrix.run_scenario_1_normal(hitl_mode)
    elif scenario_num == 2:
        res = await scenario_matrix.run_scenario_2_tpsl_triggers(hitl_mode)
    elif scenario_num == 3:
        res = await scenario_matrix.run_scenario_3_volatility_rebound(hitl_mode)
    elif scenario_num == 4:
        res = await scenario_matrix.run_scenario_4_unmatched_negotiation_failed(hitl_mode)
    elif scenario_num == 5:
        res = await scenario_matrix.run_scenario_5_sbl_held_carrying_fee(hitl_mode)
    else:
        print(f"❌ Invalid scenario number: {scenario_num}")
        return

    print("\n📊 SCENARIO RESULT:")
    print(f"  • Name:             {res.get('name')}")
    print(f"  • Status:           {res.get('status')}")
    for k, v in res.items():
        if k not in ["scenario", "name", "status", "eod_report"]:
            print(f"  • {k.replace('_', ' ').title():<20}: {v}")

    print("\n📑 EOD REPORT GENERATED AT 16:35:")
    report = res.get("eod_report", "").strip()
    if report:
        for line in report.splitlines():
            print(f"    {line}")
    else:
        print("    (Report generated in database)")
    print("=" * 75)


async def main():
    parser = argparse.ArgumentParser(description="Phase 3 Time Warp & Scenario Simulator")
    parser.add_argument(
        "--scenario",
        type=str,
        default="all",
        help="Scenario to run: 1, 2, 3, 4, 5, or 'all'"
    )
    parser.add_argument(
        "--hitl",
        type=str,
        default="auto",
        choices=["auto", "interactive"],
        help="HITL Mode: 'auto' (fast auto-pilot) or 'interactive' (pauses virtual clock)"
    )
    args = parser.parse_args()

    print("=" * 75)
    print(" ⏱️  INVESTMENT HOMELAB: TIME WARP & SCENARIO SIMULATOR")
    print(" Fast-Forward Full Trading Day (09:30 -> 10:15 -> 11:00 -> 15:30 -> 16:35)")
    print("=" * 75)

    # Initialize DB
    await init_db()

    if args.scenario.lower() == "all":
        print("\nRunning ALL 5 comprehensive scenarios sequentially...")
        for s in [1, 2, 3, 4, 5]:
            await run_single_scenario(s, args.hitl)
            await asyncio.sleep(0.5)
        print("\n🎉 ALL 5 SCENARIOS COMPLETED SUCCESSFULLY IN TIME-WARP MODE!")
    else:
        try:
            s_num = int(args.scenario)
            await run_single_scenario(s_num, args.hitl)
        except ValueError:
            print(f"Invalid scenario argument: {args.scenario}")
            sys.exit(1)

    # Reset clock to real time when done
    virtual_clock.set_real_time_mode()
    print("\nVirtual clock restored to REAL_TIME mode.")


if __name__ == "__main__":
    asyncio.run(main())
