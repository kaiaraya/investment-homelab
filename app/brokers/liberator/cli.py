#!/usr/bin/env python3
"""
Standalone CLI & Test Harness for Liberator Securities Broker Plugin.
====================================================================
Dedicated interactive runner for Liberator Securities WebTrade automation,
session inspection, interactive co-piloting, and portfolio querying.

Usage:
    # 1. Inspect Liberator configuration and session status:
    .venv/bin/python -m app.brokers.liberator.cli status

    # 2. Run interactive login & co-pilot runner (Headed Chrome + KDE Connect OTP):
    .venv/bin/python -m app.brokers.liberator.cli login

    # 3. Query account summary and holdings:
    .venv/bin/python -m app.brokers.liberator.cli portfolio
"""

import sys
import os
import asyncio
import argparse
from pprint import pprint

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from app.brokers.liberator.plugin import liberator_plugin
from app.core.config import settings

# ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"


async def cmd_status(args):
    print("=" * 65)
    print(f"{C_BOLD}🛡️ Liberator Securities (WebTrade) Status{C_RESET}")
    print("=" * 65)
    health = await liberator_plugin.get_health()
    print(f"• Configured:    {'✅ YES' if health['is_configured'] else '❌ NO (Missing Credentials in .env)'}")
    print(f"• Username:      {settings.LIBERATOR_USERNAME or 'Not Set'}")
    print(f"• Login URL:     {getattr(settings, 'LIBERATOR_LOGIN_URL', 'https://webtrade.liberator.co.th/login')}")
    print(f"• Saved Session: {'✅ EXISTS (' + settings.LIBERATOR_SESSION_PATH + ')' if health['has_saved_session'] else '❌ None'}")
    print(f"• Active Tab:    {'✅ RUNNING' if health['tab_active'] else '❌ OFFLINE'}")
    print(f"• Health Status: {health['status']}")
    print(f"• Last Sync:     {health['last_heartbeat']}")
    print("=" * 65)


async def cmd_login(args):
    print("=" * 65)
    print(f"{C_BOLD}{C_MAGENTA}🚀 Launching Liberator Interactive Login Co-pilot...{C_RESET}")
    print("=" * 65)
    from scripts.liberator.watch_and_learn_liberator import LiberatorWatchAndLearn
    runner = LiberatorWatchAndLearn()
    await runner.run()


async def cmd_portfolio(args):
    print("=" * 65)
    print(f"{C_BOLD}📊 Fetching Liberator Account Summary & Portfolio...{C_RESET}")
    print("=" * 65)
    summary = await liberator_plugin.get_account_summary()
    print(f"• Account:        {C_BOLD}{summary.account_no}{C_RESET} ({summary.account_type})")
    print(f"• Line Available: ฿{summary.line_available:,.2f}")
    print(f"• Cash Balance:   ฿{summary.cash_balance:,.2f}")
    print(f"• Total Equity:   ฿{summary.total_equity:,.2f}")

    portfolio = await liberator_plugin.get_portfolio()
    print(f"• Holdings Count: {len(portfolio.positions)}")
    for pos in portfolio.positions:
        print(f"   - {pos.symbol:<6} Vol: {pos.volume:<6,d} Avg: ฿{pos.avg_cost:<6.2f} Mkt: ฿{pos.market_price:<6.2f} Val: ฿{pos.market_value:<9,.2f} PnL: ฿{pos.unrealized_pnl:+,.2f} ({pos.pct_unrealized_pnl:+.2f}%)")

    orders = await liberator_plugin.get_orders()
    if orders:
        print(f"\n• Orders ({len(orders)} orders):")
        for o in orders:
            print(f"   - #{o.get('order_no', 'N/A')} {o.get('time', '')} {o.get('symbol', ''):<5} {o.get('side', ''):<4} Vol: {o.get('volume', 0):,d} Matched: {o.get('matched', 0):,d} Status: {o.get('status', 'Unknown')}")
    print("=" * 65)


async def cmd_action_exit(args):
    print("=" * 65)
    print(f"{C_BOLD}🎯 [PILLAR 6] Liberator Tactical Action Exit{C_RESET}")
    print("=" * 65)
    symbol = args.symbol.upper()
    volume = args.volume
    price = args.price
    reason = args.reason or "Tactical Action Exit via CLI"

    print(f" • Target Symbol:  {C_BOLD}{symbol}{C_RESET}")
    print(f" • Requested Vol:  {f'{volume:,}' if volume else 'ALL AVAILABLE (100%)'}")
    print(f" • Target Price:   {f'฿{price:.2f}' if price else 'Market / Offer Price'}")
    print(f" • Exit Reason:    {reason}")
    print("-" * 65)

    res = await liberator_plugin.execute_action_exit(
        symbol=symbol,
        volume=volume,
        target_price=price,
        reason=reason
    )
    if res.get("success"):
        print(f"{C_GREEN}✅ Action Exit Submitted! Order #{res.get('broker_order_no')} (Status: {res.get('status')}){C_RESET}")
    else:
        print(f"{C_YELLOW}⚠️ Action Exit Notice / Status: {res.get('status', 'ERROR')}{C_RESET}")
        print(f"   Detail: {res.get('error') or res.get('message')}")
    print("=" * 65)


async def cmd_negotiate(args):
    print("=" * 65)
    print(f"{C_BOLD}🎯 [PILLAR 6] Liberator Price Negotiation (ต่อราคา){C_RESET}")
    print("=" * 65)
    res = await liberator_plugin.negotiate_price(
        order_no=args.order_no,
        symbol=args.symbol,
        target_price=args.price
    )
    if res.get("success"):
        print(f"{C_GREEN}✅ Price Negotiation Processed:{C_RESET} {res.get('message')}")
        if res.get("action") == "AMENDED_IN_PLACE":
            print(f"   • Order (number retained): #{res.get('order_no')} {res.get('symbol')} {res.get('side')}")
            print(f"   • Price: ฿{float(res.get('old_price') or 0):.2f} -> ฿{float(res.get('new_price') or 0):.2f}")
        elif res.get("action") == "NONE":
            print(f"   • No amend needed: order #{res.get('order_no')} already at ฿{float(res.get('current_price') or 0):.2f}")
    else:
        print(f"{C_YELLOW}⚠️ Notice: {res.get('error') or res.get('message')}{C_RESET}")
    print("=" * 65)


async def cmd_change(args):
    """Amend a resting order IN PLACE via the broker's native Change control (ไม่เสียคิว)."""
    print("=" * 65)
    print(f"{C_BOLD}🎯 [PILLAR 6] Liberator Amend In Place (กด Change — order number เดิม){C_RESET}")
    print("=" * 65)
    print(f" • Order #:    {args.order_no}")
    print(f" • New Price:  ฿{args.price:.2f}")
    if args.volume:
        print(f" • New Volume: {args.volume:,}")
    print("-" * 65)

    res = await liberator_plugin.change_order(
        order_no=args.order_no,
        new_price=args.price,
        new_volume=args.volume
    )
    if res.get("success"):
        print(
            f"{C_GREEN}✅ Amended In Place!{C_RESET} Order #{res.get('order_no')} "
            f"@ ฿{float(res.get('new_price') or 0):.2f} (status: {res.get('status')})"
        )
        print(f"   • Order number retained (no cancel + re-place): #{res.get('order_no')}")
    else:
        print(f"{C_YELLOW}⚠️ Amend Notice / Status: {res.get('status', 'ERROR')}{C_RESET}")
        print(f"   Detail: {res.get('error') or res.get('message')}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Liberator Securities Standalone CLI Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. status
    p_status = subparsers.add_parser("status", help="Inspect Liberator configuration and health status")
    p_status.set_defaults(func=cmd_status)

    # 2. login
    p_login = subparsers.add_parser("login", help="Launch interactive login & watch-and-learn co-pilot in Headed Chrome")
    p_login.set_defaults(func=cmd_login)

    # 3. portfolio
    p_port = subparsers.add_parser("portfolio", help="Query account summary and holdings")
    p_port.set_defaults(func=cmd_portfolio)

    # 4. action-exit
    p_exit = subparsers.add_parser("action-exit", help="Trigger Tactical Action Exit (Sell) for a stock")
    p_exit.add_argument("--symbol", required=True, help="Stock ticker (e.g. BCP, BCH, IVL)")
    p_exit.add_argument("--volume", type=int, default=None, help="Volume to sell (defaults to 100% of holding)")
    p_exit.add_argument("--price", type=float, default=None, help="Target limit price")
    p_exit.add_argument("--reason", default="Manual CLI Trigger", help="Reason for exit")
    p_exit.set_defaults(func=cmd_action_exit)

    # 5. negotiate
    p_neg = subparsers.add_parser("negotiate", help="Trigger passive queue pegging (ต่อราคา) on open orders")
    p_neg.add_argument("--symbol", default=None, help="Filter by symbol")
    p_neg.add_argument("--order-no", default=None, help="Specific order number to negotiate")
    p_neg.add_argument("--price", type=float, default=None, help="New target pegged price")
    p_neg.set_defaults(func=cmd_negotiate)

    # 6. change — amend a resting order IN PLACE via the broker's native Change control
    p_chg = subparsers.add_parser("change", help="Amend a resting order IN PLACE (native Change control)")
    p_chg.add_argument("order_no", help="Broker order number (e.g. 11894)")
    p_chg.add_argument("price", type=float, help="New limit price")
    p_chg.add_argument("--volume", type=int, default=None, help="Optional new volume (board lot x100)")
    p_chg.set_defaults(func=cmd_change)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
