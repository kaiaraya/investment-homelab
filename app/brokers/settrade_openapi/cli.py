#!/usr/bin/env python3
"""
Standalone CLI & Test Harness for Settrade Open API Broker Plugin.
==================================================================
Direct Machine-to-Machine (M2M) API inspection without opening browsers.

Usage:
    .venv/bin/python -m app.brokers.settrade_openapi.cli status
    .venv/bin/python -m app.brokers.settrade_openapi.cli quote CPALL
    .venv/bin/python -m app.brokers.settrade_openapi.cli account
    .venv/bin/python -m app.brokers.settrade_openapi.cli order --symbol CPALL --side BUY --vol 100 --price 58.50
"""

import sys
import os
import asyncio
import argparse
from pprint import pprint

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from app.brokers.settrade_openapi.plugin import settrade_openapi_plugin
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
    print(f"{C_BOLD}⚡ Settrade Open API (Direct M2M) Status{C_RESET}")
    print("=" * 65)
    health = await settrade_openapi_plugin.get_health()
    print(f"• Configured:    {'✅ YES' if health['is_configured'] else '❌ NO (Missing App ID/Secret)'}")
    print(f"• Broker ID:     {health.get('broker_id', 'SANDBOX')}")
    print(f"• App Code:      {health.get('app_code', 'SANDBOX')}")
    print(f"• App ID:        {settings.SETTRADE_APP_ID[:4]}***" if settings.SETTRADE_APP_ID else "• App ID:        None")
    print(f"• Status:        {health['status']}")
    print(f"• Last Sync:     {health['last_heartbeat']}")
    print("=" * 65)


async def cmd_quote(args):
    symbol = args.symbol.upper().strip()
    print(f"📡 Querying Real-time Quote for {C_BOLD}{symbol}{C_RESET} via Settrade Open API...")

    if not settrade_openapi_plugin.is_configured():
        print(f"{C_YELLOW}⚠️  SETTRADE_APP_ID not configured in .env. Returning simulated quote:{C_RESET}")
        base = 58.50 if symbol == "CPALL" else (12.80 if symbol == "TRUE" else 100.0)
        print(f"• {symbol}: Last=฿{base:.2f}, Bid=฿{base - 0.25:.2f}, Offer=฿{base + 0.25:.2f}")
        return

    try:
        from settrade_v2 import Investor
        investor = Investor(
            app_id=settings.SETTRADE_APP_ID,
            app_secret=settings.SETTRADE_APP_SECRET,
            broker_id=settings.SETTRADE_BROKER_ID or "SANDBOX",
            app_code=settings.SETTRADE_APP_CODE or "SANDBOX",
            is_auto_queue=False
        )
        market = investor.MarketData()
        q = market.get_quote_symbol(symbol=symbol)
        print(f"{C_GREEN}✅ Quote Received successfully!{C_RESET}")
        print(f"• Symbol:     {symbol}")
        print(f"• Last Price: ฿{q.get('last', q.get('close', '-'))}")
        print(f"• High / Low: ฿{q.get('high', '-')} / ฿{q.get('low', '-')}")
        print(f"• Volume:     {q.get('total_volume', '-'):,}" if isinstance(q.get('total_volume'), (int, float)) else f"• Volume:     {q.get('total_volume', '-')}")
    except Exception as e:
        print(f"{C_RED}❌ Quote fetch exception: {e}{C_RESET}")


async def cmd_account(args):
    print("=" * 65)
    print(f"{C_BOLD}📊 Settrade Open API Account Summary{C_RESET}")
    print("=" * 65)
    acc = await settrade_openapi_plugin.get_account_summary()
    print(f"• Account No:     {acc.account_no} ({acc.account_type})")
    print(f"• Line Available: ฿{acc.line_available:,.2f}")
    print(f"• Cash Balance:   ฿{acc.cash_balance:,.2f}")
    print(f"• Excess Equity:  ฿{acc.excess_equity:,.2f}")
    print("=" * 65)


async def cmd_order(args):
    symbol = args.symbol.upper().strip()
    side = args.side.upper().strip()
    vol = args.vol
    price = args.price

    print("=" * 65)
    print(f"{C_BOLD}⚡ SUBMITTING SETTRADE OPEN API ORDER{C_RESET}")
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
        pin=settings.SETTRADE_PIN or "000000"
    )
    res = await settrade_openapi_plugin.place_order(req)
    if res.success:
        print(f"{C_GREEN}✅ Order Dispatched! Order ID: {res.order_id}{C_RESET}")
        print(f" • Message: {res.message}")
    else:
        print(f"{C_RED}❌ Order Rejected: {res.message}{C_RESET}")


def main():
    parser = argparse.ArgumentParser(description="Settrade Open API Broker Plugin CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("status", help="Get Open API connection status")

    quote_p = subparsers.add_parser("quote", help="Get real-time quote for symbol")
    quote_p.add_argument("symbol", help="Stock symbol e.g. CPALL")

    subparsers.add_parser("account", help="Get account balance")

    order_p = subparsers.add_parser("order", help="Submit order via Direct API")
    order_p.add_argument("--symbol", required=True, help="Stock symbol")
    order_p.add_argument("--side", choices=["BUY", "SELL", "LONG", "SHORT"], default="BUY", help="Order side")
    order_p.add_argument("--vol", type=int, default=100, help="Order volume")
    order_p.add_argument("--price", type=float, required=True, help="Order price limit")

    args = parser.parse_args()

    if not args.command or args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "quote":
        asyncio.run(cmd_quote(args))
    elif args.command == "account":
        asyncio.run(cmd_account(args))
    elif args.command == "order":
        asyncio.run(cmd_order(args))


if __name__ == "__main__":
    main()
