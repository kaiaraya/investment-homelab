#!/usr/bin/env python3
"""
Standalone CLI & Test Harness for Click2Win Broker Plugin.
==========================================================
Run independently to diagnose and test Click2Win Sandbox:

Usage:
    .venv/bin/python -m app.brokers.click2win.cli status
    .venv/bin/python -m app.brokers.click2win.cli test-auth
    .venv/bin/python -m app.brokers.click2win.cli test-portfolio
    .venv/bin/python -m app.brokers.click2win.cli order --symbol CPALL --side BUY --vol 100 --price 58.50
    .venv/bin/python -m app.brokers.click2win.cli switch-account DERIVATIVES
"""

import sys
import os
import asyncio
import argparse
from pprint import pprint

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from app.brokers.click2win.plugin import click2win_plugin
from app.brokers.base import OrderRequest
from app.core.config import settings

# ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"


async def cmd_status(args):
    print("=" * 65)
    print(f"{C_BOLD}🎮 Click2Win Sandbox Status{C_RESET}")
    print("=" * 65)
    health = await click2win_plugin.get_health()
    pprint(health)
    print("=" * 65)


async def cmd_test_auth(args):
    print("🔐 Authenticating with Settrade Click2Win Sandbox (force_fresh=True)...")
    success = await click2win_plugin.authenticate(force_fresh=True)
    if success:
        print(f"{C_GREEN}✅ Click2Win Sandbox Authentication Successful!{C_RESET}")
    else:
        print(f"{C_RED}❌ Click2Win Sandbox Authentication Failed! Check credentials.{C_RESET}")


async def cmd_test_portfolio(args):
    print("📊 Fetching Click2Win Account Summary & Positions...")
    summary = await click2win_plugin.get_account_summary()
    print(f"• Account:        {C_BOLD}{summary.account_no}{C_RESET} ({summary.account_type})")
    print(f"• Line Available: ฿{summary.line_available:,.2f}")
    print(f"• Cash Balance:   ฿{summary.cash_balance:,.2f}")
    port = await click2win_plugin.get_portfolio()
    print(f"• Holdings Count: {len(port.positions)}")
    for pos in port.positions:
        print(f"   • {pos.symbol:<8}: {pos.volume:,} shares (Avg: {pos.avg_cost:.2f}, Mkt: {pos.market_price:.2f}, PnL: {pos.unrealized_pnl:+,.2f})")


async def cmd_order(args):
    symbol = args.symbol.upper().strip()
    side = args.side.upper().strip()
    vol = args.vol
    price = args.price
    pin = args.pin or settings.CLICK2WIN_PIN or "000000"

    print("=" * 65)
    print(f"{C_BOLD}⚡ SUBMITTING CLICK2WIN SANDBOX ORDER{C_RESET}")
    print(f" • Symbol: {C_CYAN}{symbol}{C_RESET}")
    print(f" • Side:   {C_GREEN if side in ['BUY', 'LONG'] else C_RED}{side}{C_RESET}")
    print(f" • Volume: {vol:,}")
    print(f" • Price:  ฿{price:.2f}")
    print("=" * 65)

    req = OrderRequest(
        symbol=symbol,
        side=side,
        volume=vol,
        price=price,
        pin=pin
    )
    res = await click2win_plugin.place_order(req)
    if res.success:
        print(f"{C_GREEN}✅ Order Submitted Successfully!{C_RESET}")
        print(f" • Order ID: {res.order_id}")
        print(f" • Message:  {res.message}")
    else:
        print(f"{C_RED}❌ Order Failed / Rejected: {res.message}{C_RESET}")


async def cmd_switch_account(args):
    target = args.type.upper().strip()
    print(f"🔄 Switching Click2Win active tab to {target}...")
    ok = await click2win_plugin.switch_account_type(target)
    if ok:
        print(f"{C_GREEN}✅ Switched to {target} successfully.{C_RESET}")
    else:
        print(f"{C_RED}❌ Failed to switch account to {target}.{C_RESET}")


def main():
    parser = argparse.ArgumentParser(description="Click2Win Broker Plugin CLI Tester")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("status", help="Get Click2Win plugin status")
    subparsers.add_parser("test-auth", help="Test login and authentication")
    subparsers.add_parser("test-portfolio", help="Fetch portfolio and accounts")

    order_p = subparsers.add_parser("order", help="Submit order on Sandbox")
    order_p.add_argument("--symbol", required=True, help="Stock / TFEX Symbol (e.g. CPALL, S50Z24)")
    order_p.add_argument("--side", choices=["BUY", "SELL", "LONG", "SHORT"], default="BUY", help="Order side")
    order_p.add_argument("--vol", type=int, default=100, help="Order volume (e.g. 100)")
    order_p.add_argument("--price", type=float, required=True, help="Order price limit (e.g. 58.50)")
    order_p.add_argument("--pin", default=None, help="Trading PIN (defaults to .env)")

    switch_p = subparsers.add_parser("switch-account", help="Switch between EQUITY and DERIVATIVES")
    switch_p.add_argument("type", choices=["EQUITY", "DERIVATIVES"], help="Target account type")

    args = parser.parse_args()

    if not args.command or args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "test-auth":
        asyncio.run(cmd_test_auth(args))
    elif args.command == "test-portfolio":
        asyncio.run(cmd_test_portfolio(args))
    elif args.command == "order":
        asyncio.run(cmd_order(args))
    elif args.command == "switch-account":
        asyncio.run(cmd_switch_account(args))


if __name__ == "__main__":
    main()
