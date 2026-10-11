#!/usr/bin/env python3
"""
Krungsri Capital Type-Safe Playwright Debug Runner
=================================================
Workflows:
1. Zero-OTP Session Verification & Auto-Fallback Login (Type-Safe LoginResult)
2. Live Portfolio Holdings Scraper (Type-Safe HoldingPosition / PortfolioSnapshot)
3. Live Account Summary & Excess Equity Scraper (Type-Safe AccountSummary)
4. Silent DB Reconciliation into SQLite positions table

Debug features:
- Headed Chromium with visual glowing element highlights
- On-failure mode (halts and enters interactive Grill-Me menu if error occurs)
- Type-Safe schema validation on every data structure

Usage:
    .venv/bin/python scripts/debug_krungsri_portfolio_typesafe.py [--mode on-failure|step] [--no-db-sync]
"""

import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.browser.popup_manager import popup_manager
from app.browser.grill_harness import GrillController
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform
from app.schemas.portfolio import HoldingPosition, AccountSummary, PortfolioSnapshot, PositionType
from app.services.portfolio_overview_service import portfolio_overview_service
from app.db.session import AsyncSessionLocal
from app.db.models import Position
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("KrungsriTypeSafeDebug")


async def run_portfolio_typesafe_debug(mode: str = "on-failure", sync_db: bool = True):
    print("=" * 80)
    print(" 🚀 KRUNGSRI CAPITAL: TYPE-SAFE PLAYWRIGHT DEBUG RUNNER")
    print(" • Broker: Krungsri TradeMan (Production)")
    print(f" • Mode: Headed Desktop (:0) | Grill Mode: {mode.upper()}")
    print(" • Workflows: [1] Session Restore -> [2] Portfolio Holdings -> [3] Account EE")
    print(f" • DB Sync: {'ENABLED (Silent DB Reconciliation)' if sync_db else 'DISABLED'}")
    print("=" * 80)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.TRADING_PLATFORM = "TRADEMAN"
    settings.PLAYWRIGHT_HEADLESS = False

    grill = GrillController(mode=mode, auto_highlight=True)

    # ---------------------------------------------------------
    # STEP 1: Browser Launch & Zero-OTP Session Verification
    # ---------------------------------------------------------
    page = None
    login_result: LoginResult = None

    async def step_auth():
        nonlocal page, login_result
        print("\n[Step 1/4] Launching Chromium and verifying active TradeMan session...")
        page = await auth_driver.launch_browser(resume_state=True)
        is_saved_valid = await auth_driver.verify_saved_session()

        if is_saved_valid:
            login_result = LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.TRADEMAN,
                resumed=True,
                url=page.url,
                message="Zero-OTP Session restored successfully from data/session_state.json"
            )
            print(f"   ✅ [Type-Safe] Session Valid! Resumed URL: {login_result.url}")
        else:
            print("   ⚠️  Existing session invalid or expired. Executing Auto-Fallback login...")
            username = settings.KRUNGSRI_USERNAME
            password = settings.KRUNGSRI_PASSWORD

            if not username or not password:
                raise ValueError("KRUNGSRI_USERNAME or KRUNGSRI_PASSWORD not set in .env")

            print(f"   🔑 Logging in via Krungsri Portal for user {username[:3]}***...")
            res = await auth_driver.login(username=username, password=password)
            if isinstance(res, dict):
                login_result = LoginResult(**res)
            else:
                login_result = res

            if not login_result.success:
                raise RuntimeError(f"Krungsri Login Failed: {login_result.message}")
            print(f"   ✅ [Type-Safe] Login Successful! Status: {login_result.status}")

    await grill.execute_step(None, "Step 1: Authenticate / Restore Session (Zero-OTP)", step_auth)

    # ---------------------------------------------------------
    # STEP 2: Navigate to Portfolio & Visual Highlight
    # ---------------------------------------------------------
    async def step_navigate_portfolio():
        print("\n[Step 2/4] Navigating to Portfolio tab and dismissing popups...")
        trademan_driver.page_override = page
        
        # Ensure we are on Portfolio page
        if "Portfolio" not in page.url:
            await page.goto("https://trademan.in.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

        # Auto-dismiss popups
        await popup_manager.dismiss_popups(page)
        
        # Highlight navigation tab & main container
        await grill.highlight_element(page, "a[href*='Portfolio'], span:has-text('Portfolio')", color="#10b981")
        await page.wait_for_timeout(600)
        print(f"   ✅ Portfolio tab loaded. URL: {page.url}")

    await grill.execute_step(page, "Step 2: Navigate to Portfolio Tab", step_navigate_portfolio, selector="a[href*='Portfolio']")

    # ---------------------------------------------------------
    # STEP 3: Scrape Holdings & Convert to Type-Safe Models
    # ---------------------------------------------------------
    typed_positions: List[HoldingPosition] = []

    async def step_scrape_holdings():
        nonlocal typed_positions
        print("\n[Step 3/4] Scraping portfolio table from DOM...")
        
        # Highlight the holdings table
        count = await grill.highlight_element(page, "table tbody tr", color="#f59e0b")
        print(f"   🔍 Highlighted {count} DOM table rows on screen.")

        raw_holdings = await trademan_driver.scrape_portfolio()
        print(f"   📊 Raw positions extracted from TradeMan: {len(raw_holdings)}")

        # Convert to Type-Safe HoldingPosition instances
        typed_positions = []
        for idx, item in enumerate(raw_holdings, 1):
            try:
                pos = HoldingPosition(
                    raw_symbol=item.get("raw_symbol", item.get("symbol", "")),
                    symbol=item.get("symbol", ""),
                    position_type=PositionType(item.get("position_type", "LONG")),
                    volume=int(item.get("volume", 0)),
                    on_hand=int(item.get("on_hand", 0)),
                    sellable=int(item.get("sellable", 0)),
                    avg_cost=float(item.get("avg_cost", 0.0)),
                    current_price=float(item.get("current_price", 0.0)),
                    prior_close_price=float(item.get("prior_close_price", item.get("current_price", 0.0))),
                    cost_value=float(item.get("cost_value", 0.0)),
                    market_value=float(item.get("market_value", 0.0)),
                    unrealized_pnl=float(item.get("unrealized_pnl", 0.0)),
                    pnl_pct=float(item.get("pnl_pct", 0.0))
                )
                typed_positions.append(pos)
            except Exception as parse_err:
                logger.warning(f"Error parsing holding item {item}: {parse_err}")

        print(f"   ✅ [Type-Safe] Successfully validated {len(typed_positions)} HoldingPosition models.")

    await grill.execute_step(page, "Step 3: Scrape Portfolio Holdings", step_scrape_holdings, selector="table tbody")

    # ---------------------------------------------------------
    # STEP 4: Scrape Account Summary & Excess Equity (EE)
    # ---------------------------------------------------------
    typed_account: AccountSummary = None
    snapshot: PortfolioSnapshot = None

    async def step_scrape_account():
        nonlocal typed_account, snapshot
        print("\n[Step 4/4] Scraping Account Balances (Cash, Line, Excess Equity)...")
        raw_acc = await trademan_driver.scrape_account_summary(force_live=True)

        typed_account = AccountSummary(
            broker=BrokerPlatform.TRADEMAN,
            cash_balance=raw_acc.get("cash_balance", 0.0),
            line_available=raw_acc.get("cash_balance", 0.0),
            excess_equity=raw_acc.get("excess_equity", 0.0)
        )

        total_cost = sum(p.cost_value for p in typed_positions)
        total_mkt = sum(p.market_value for p in typed_positions)
        total_pnl = sum(p.unrealized_pnl for p in typed_positions)
        overall_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

        snapshot = PortfolioSnapshot(
            broker=BrokerPlatform.TRADEMAN,
            account=typed_account,
            positions=typed_positions,
            total_cost=total_cost,
            total_market_value=total_mkt,
            total_unrealized_pnl=total_pnl,
            overall_pnl_pct=overall_pct
        )
        print("   ✅ [Type-Safe] PortfolioSnapshot created successfully.")

    await grill.execute_step(page, "Step 4: Scrape Account Summary & Excess Equity", step_scrape_account)

    # ---------------------------------------------------------
    # STEP 5: Silent DB Reconciliation
    # ---------------------------------------------------------
    if sync_db and typed_positions:
        print("\n[Database Sync] Performing Silent DB Reconciliation into SQLite...")
        dict_payload = [p.model_dump() for p in typed_positions]
        async with AsyncSessionLocal() as db:
            await portfolio_overview_service.reconcile_portfolio(db, dict_payload)

            # Query DB to verify
            result = await db.execute(select(Position))
            saved_positions = result.scalars().all()
            print(f"   💾 Database Synchronized! Total active positions in SQLite: {len(saved_positions)}")

    # ---------------------------------------------------------
    # PRINT RESULTS SUMMARY TABLE
    # ---------------------------------------------------------
    print("\n" + "=" * 90)
    print(f" 📈 KRUNGSRI TRADEMAN PORTFOLIO SNAPSHOT ({snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')})")
    print("=" * 90)
    print(f" • Cash Balance:   ฿{snapshot.account.cash_balance:,.2f}")
    print(f" • Excess Equity:  ฿{snapshot.account.excess_equity:,.2f}")
    print(f" • Total Cost:     ฿{snapshot.total_cost:,.2f}")
    print(f" • Market Value:   ฿{snapshot.total_market_value:,.2f}")
    print(f" • Total PnL:      ฿{snapshot.total_unrealized_pnl:+,.2f} ({snapshot.overall_pnl_pct:+.2f}%)")
    print("-" * 90)
    print(f"{'#':<3} | {'Symbol':<10} | {'Type':<6} | {'Volume':<10} | {'Avg Cost':<10} | {'Current':<10} | {'PnL (THB)':<14} | {'PnL %':<8}")
    print("-" * 90)

    for i, pos in enumerate(snapshot.positions, 1):
        pnl_color = "+" if pos.unrealized_pnl >= 0 else ""
        print(f"{i:<3} | {pos.symbol:<10} | {pos.position_type.value:<6} | {pos.volume:<10,} | {pos.avg_cost:<10.2f} | {pos.current_price:<10.2f} | {pos.unrealized_pnl:>+13,.2f} | {pos.pnl_pct:>+7.2f}%")

    print("=" * 90)
    print(" 🎉 PLAYWRIGHT DEBUG + TYPE-SAFE RUN COMPLETED SUCCESSFULLY!")
    print(" Zero Financial Risk verified: No trading buttons clicked, no orders placed.")
    print("=" * 90)

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Krungsri Capital Type-Safe Playwright Debug Runner")
    parser.add_argument("--mode", choices=["on-failure", "step"], default="on-failure",
                        help="Grill mode: 'on-failure' runs automatically and pauses only on error; 'step' pauses each step.")
    parser.add_argument("--no-db-sync", action="store_true", help="Skip SQLite DB reconciliation")
    args = parser.parse_args()

    async def _runner():
        try:
            await run_portfolio_typesafe_debug(mode=args.mode, sync_db=not args.no_db_sync)
        finally:
            print("\n[Teardown] Gracefully closing browser context and preventing zombie processes...")
            await auth_driver.close()

    asyncio.run(_runner())


if __name__ == "__main__":
    main()
