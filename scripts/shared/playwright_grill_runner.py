#!/usr/bin/env python3
"""
Playwright Grill-Me Interactive Test & Inspection Console.
=========================================================
Gives you a real-time, human-in-the-loop (HITL) feedback loop during Playwright testing:
- Runs headed Chromium with live element highlighting.
- Pauses before actions (in --mode step) or catches mistakes (in --mode on-failure).
- Lets you launch Playwright Inspector GUI (page.pause()) anytime with [p].
- Lets you test/probe CSS/XPath selectors live with visual highlighting on screen with [i].
- Lets you evaluate JavaScript in the browser console with [e].
- Lets you update selectors and retry without re-running the entire test with [u] or [r].

Usage:
  # 1. Interactive testing of local Homelab Web Console (default):
  .venv/bin/python scripts/playwright_grill_runner.py --target console --mode step

  # 2. Test in on-failure mode (only halts and grills when something fails or times out):
  .venv/bin/python scripts/playwright_grill_runner.py --target console --mode on-failure

  # 3. Interactive live scraper test on TradeMan (zero-risk read only):
  .venv/bin/python scripts/playwright_grill_runner.py --target trademan --mode step

  # 4. Interactive playground on custom URL:
  .venv/bin/python scripts/playwright_grill_runner.py --target inspect --url http://localhost:8000/console
"""

import argparse
import asyncio
import os
import sys

# Ensure root path in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.async_api import async_playwright
from app.browser.grill_harness import GrillController
from app.core.config import settings


async def run_console_scenario(page, grill: GrillController):
    """Scenario testing the Homelab Local Web Console."""
    url = "http://localhost:8000/console"

    # Step 1: Navigate to Console
    async def action_goto():
        await page.goto(url, wait_until="networkidle", timeout=10000)
    await grill.execute_step(page, f"Navigate to {url}", action_goto)

    # Step 2: Test Preset 'Buy TRUE 3800'
    selector_preset = "button:has-text('Buy TRUE 3800')"
    async def action_click_preset(sel=selector_preset):
        await page.click(sel, timeout=5000)
    await grill.execute_step(page, "Click Preset 'Buy TRUE 3800'", action_click_preset, selector=selector_preset)

    # Step 3: Click 'Send Order Signal'
    selector_send = "button:has-text('Send Order Signal')"
    async def action_send_signal(sel=selector_send):
        await page.click(sel, timeout=5000)
        await page.wait_for_timeout(1000)
    await grill.execute_step(page, "Click 'Send Order Signal'", action_send_signal, selector=selector_send)

    # Step 4: Verify Order Result in Console Log
    selector_log = "#consoleLog"
    async def action_verify_log(sel=selector_log):
        log_text = await page.inner_text(sel)
        if "TRUE" not in log_text and "success" not in log_text.lower():
            raise AssertionError(f"Expected order result in console log, got:\n{log_text[:300]}")
        print(f"   Console Log Output Snippet:\n   {log_text[:150]}...")
    await grill.execute_step(page, "Verify Order Log in Console", action_verify_log, selector=selector_log)

    # Step 5: Test Odd-Lot Rejection Preset
    selector_oddlot = "button:has-text('Odd-lot 96')"
    async def action_click_oddlot(sel=selector_oddlot):
        await page.click(sel, timeout=5000)
        await page.click("button:has-text('Send Order Signal')", timeout=5000)
        await page.wait_for_timeout(1000)
        log_text = await page.inner_text("#consoleLog")
        if "rejected" not in log_text.lower() and "odd-lot" not in log_text.lower():
            raise AssertionError(f"Expected Odd-lot rejection message in log, got:\n{log_text[:300]}")
    await grill.execute_step(page, "Test Odd-lot 96 Rejection Guardrail", action_click_oddlot, selector=selector_oddlot)

    # Step 6: Test Watchlist Triggers Tab Switch
    selector_tab_trg = "#tabTriggersBtn"
    async def action_switch_tab(sel=selector_tab_trg):
        await page.click(sel, timeout=5000)
        await page.wait_for_timeout(600)
    await grill.execute_step(page, "Switch to Watchlist Triggers Tab", action_switch_tab, selector=selector_tab_trg)

    # Step 7: Inspect Triggers Table
    selector_trg_body = "#triggersTableBody"
    async def action_check_triggers(sel=selector_trg_body):
        content = await page.inner_text(sel)
        print(f"   Triggers Table Row Preview: {content[:100].strip()}...")
    await grill.execute_step(page, "Inspect Watchlist Triggers Content", action_check_triggers, selector=selector_trg_body)


async def run_trademan_scenario(page, grill: GrillController):
    """Scenario testing Krungsri TradeMan Live Session & Read-Only Scraping."""
    from app.browser.auth_driver import auth_driver
    from app.browser.trademan_driver import trademan_driver

    # Step 1: Check Session State
    async def action_verify_session():
        auth_driver.page = page
        auth_driver.browser = page.context.browser
        auth_driver.context = page.context
        valid = await auth_driver.verify_saved_session()
        if not valid:
            print("   ⚠️  No authenticated session active. Navigating to Krungsri Login...")
            await page.goto(settings.KRUNGSRI_LOGIN_URL, wait_until="networkidle")
            raise RuntimeError("TradeMan is not logged in. Please log in or restore session.")
    await grill.execute_step(page, "Verify Active TradeMan Session", action_verify_session)

    # Step 2: Switch to Portfolio Tab
    async def action_switch_port():
        await trademan_driver.switch_tab("Portfolio")
    await grill.execute_step(page, "Switch to Portfolio Tab", action_switch_port)

    # Step 3: Scrape Holdings
    async def action_scrape_holdings():
        holdings = await trademan_driver.scrape_portfolio()
        print(f"   📊 Scraped {len(holdings)} holdings from TradeMan.")
    await grill.execute_step(page, "Scrape Portfolio Holdings", action_scrape_holdings)


async def run_click2win_scenario(page, grill: GrillController):
    """Scenario testing Settrade Click2Win & Streaming trading interface."""
    from app.browser.click2win_auth_driver import click2win_auth_driver
    from app.browser.click2win_driver import click2win_driver

    click2win_auth_driver.page = page
    click2win_auth_driver.browser = page.context.browser
    click2win_auth_driver.context = page.context

    # Step 1: Login to Click2Win
    async def action_login():
        res = await click2win_auth_driver.login()
        if not res.get("success"):
            raise RuntimeError(f"Click2Win login failed: {res.get('error', res.get('message'))}")
    await grill.execute_step(page, "Log into Click2Win Sandbox", action_login)

    # Step 2: Navigate to Streaming Page
    streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
    async def action_streaming():
        await page.goto(streaming_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2500)
    await grill.execute_step(page, "Open Settrade Streaming Trading Screen", action_streaming)

    # Step 3: Scrape Accounts & Balances
    async def action_scrape():
        summary = await click2win_driver.scrape_accounts_summary()
        accounts = summary.get("accounts", [])
        print(f"   📊 Discovered {len(accounts)} accounts on Click2Win:")
        for acc in accounts:
            print(f"      - [{acc.get('account_type')}] {acc.get('account_no')} | Line: ฿{acc.get('line_available', 0):,.2f}")
    await grill.execute_step(page, "Verify Accounts & Streaming Balance", action_scrape)


async def run_custom_inspect(page, grill: GrillController, url: str):
    """Opens a custom URL and keeps the interactive Grill-Me menu open."""
    async def action_goto():
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    await grill.execute_step(page, f"Open target URL: {url}", action_goto)

    print("\n" + "*" * 70)
    print(" 🎮 INTERACTIVE INSPECTION PLAYGROUND ACTIVE")
    print(" You can test selectors, run Playwright Inspector, or eval JS.")
    print("*" * 70)
    while True:
        choice = await grill.grill_menu(page, f"Live Inspection on {url}")
        if choice in ("abort", "skip"):
            break


async def main():
    parser = argparse.ArgumentParser(description="Playwright Grill-Me Interactive Test Console")
    parser.add_argument("--target", choices=["console", "trademan", "click2win", "inspect"], default="console",
                        help="Target test suite (console, trademan, click2win, inspect)")
    parser.add_argument("--mode", choices=["step", "on-failure"], default="step",
                        help="'step': pause at every action. 'on-failure': pause only on mistake/error")
    parser.add_argument("--url", default="http://localhost:8000/console",
                        help="Target URL for custom inspection")
    parser.add_argument("--headless", action="store_true", default=False,
                        help="Run in headless mode (default: False / Headed)")
    parser.add_argument("--devtools", action="store_true", default=False,
                        help="Auto-open Chrome DevTools on start")
    args = parser.parse_args()

    print("=" * 75)
    print(" 🕵️‍♂️  PLAYWRIGHT GRILL-ME INTERACTIVE TESTING HARNESS")
    print(f" Target:   {args.target.upper()}")
    print(f" Mode:     {args.mode.upper()} (Human-in-the-Loop Feedback Loop)")
    print(f" Headless: {args.headless}")
    print(f" DevTools: {args.devtools}")
    print("=" * 75)

    grill = GrillController(mode=args.mode)

    async with async_playwright() as p:
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1366,850",
            "--disable-blink-features=AutomationControlled"
        ]
        if args.devtools:
            launch_args.append("--auto-open-devtools-for-tabs")

        chrome_path = "/usr/bin/google-chrome"
        launch_kwargs = {
            "headless": args.headless,
            "args": launch_args
        }
        if os.path.exists(chrome_path):
            launch_kwargs["executable_path"] = chrome_path

        browser = await p.chromium.launch(**launch_kwargs)

        context_kwargs = {
            "viewport": {"width": 1366, "height": 850},
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }
        if os.path.exists(settings.SESSION_STATE_PATH) and args.target == "trademan":
            context_kwargs["storage_state"] = settings.SESSION_STATE_PATH

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        # Listen to console logs and page errors
        page.on("console", lambda msg: print(f"   [Browser Console {msg.type.upper()}]: {msg.text[:100]}"))
        page.on("pageerror", lambda err: print(f"   [Browser PageError]: {err}"))

        try:
            if args.target == "console":
                await run_console_scenario(page, grill)
            elif args.target == "trademan":
                await run_trademan_scenario(page, grill)
            elif args.target == "click2win":
                await run_click2win_scenario(page, grill)
            elif args.target == "inspect":
                await run_custom_inspect(page, grill, args.url)

            print("\n🎉 Scenario completed! Press Enter to close browser or [p] for Inspector.")
            choice = await asyncio.get_event_loop().run_in_executor(None, lambda: input("👉 Option: ").strip().lower())
            if choice == "p":
                await page.pause()

        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        finally:
            await browser.close()
            print("Browser closed.")


if __name__ == "__main__":
    asyncio.run(main())
