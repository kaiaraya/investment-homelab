#!/usr/bin/env python3
"""
Interactive Playwright Co-piloting Harness: Watch-and-Learn.
Designed for developer + AI collaborative web automation:
1. Opens visible Chrome on desktop (:0) with active session cookies.
2. Accepts real-time CLI commands for DOM inspection and action execution.
3. Buffers verified steps and exports standardized runbooks to learned_workflows/<name>.md.

Usage:
    .venv/bin/python scripts/watch_and_learn.py [--platform trademan|click2win] [--workflow <name>] [--devtools]
"""

import sys
import os
import re
import asyncio
import argparse
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.broker_factory import get_auth_driver, get_broker_driver
from app.browser.popup_manager import popup_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("WatchAndLearn")


class WatchAndLearnSession:
    def __init__(self, platform_name: str, workflow_name: str, devtools: bool = False):
        self.platform_name = platform_name.upper()
        if self.platform_name in ["TRADEMAN", "KRUNGSRI"]:
            settings.TRADING_PLATFORM = "TRADEMAN"
        else:
            settings.TRADING_PLATFORM = "CLICK2WIN"

        self.workflow_name = workflow_name
        self.devtools = devtools
        self.auth = get_auth_driver()
        self.broker = get_broker_driver()
        self.page = None
        self.recorded_steps: List[Dict[str, str]] = []

    async def initialize(self) -> bool:
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"

        settings.TRADING_PLATFORM = self.platform_name
        settings.PLAYWRIGHT_HEADLESS = False

        print("\n" + "=" * 75)
        print(f" 👁️  WATCH-AND-LEARN INTERACTIVE CO-PILOT HARNESS")
        print(f" • Platform: {self.platform_name}")
        print(f" • Workflow: {self.workflow_name}")
        print(f" • Mode: Headed Chrome (Display: {os.environ.get('DISPLAY', ':0')})")
        print("=" * 75 + "\n")

        print("[1/3] Connecting to browser and restoring session...")
        self.page = await self.auth.launch_browser(resume_state=True)
        is_valid = await self.auth.verify_saved_session()

        if is_valid:
            print(f"✅ Session restored! Logged in on {self.platform_name}.")
            print(f"• Current URL: {self.page.url}")
        else:
            print(f"ℹ️  No active session. Initiating automated login for {self.platform_name}...")
            if self.platform_name == "CLICK2WIN":
                success = await self.auth.login(
                    username=settings.CLICK2WIN_USERNAME,
                    password=settings.CLICK2WIN_PASSWORD,
                    pin=settings.CLICK2WIN_PIN
                )
                if not success:
                    print("❌ Click2Win login failed.")
                    return False
            else:
                login_task = asyncio.create_task(
                    self.auth.login(
                        username=settings.KRUNGSRI_USERNAME,
                        password=settings.KRUNGSRI_PASSWORD
                    )
                )
                from app.services.kdeconnect_service import kdeconnect_service
                announced = False
                while not login_task.done():
                    await asyncio.sleep(1.0)
                    if self.auth.status == "AWAITING_OTP":
                        if not announced:
                            print(f"\n🔑 2FA SMS OTP REQUIRED! Broker Ref Code: [{self.auth.current_ref or 'Pending'}]")
                            print("• Auto-capturing via KDE Connect D-Bus...")
                            announced = True
                        try:
                            polled = await kdeconnect_service.poll_active_notifications()
                            if polled:
                                print(f"📱 KDE Connect captured OTP: {polled.masked_otp}! Relaying...")
                        except Exception:
                            pass

                res = await login_task
                if not res.success:
                    print(f"❌ Krungsri login failed: {res.message}")
                    return False
                print(f"✅ Login successful! Active at: {self.auth.current_url}")

        print("\n[2/3] Checking popups and overlays...")
        await popup_manager.dismiss_popups(self.page)

        print("\n[3/3] Ready for interactive co-piloting!")
        self._print_help()
        return True

    def _print_help(self):
        print("""
Commands Cheat Sheet:
  nav <url|tab>                - Navigate to URL or SPA tab ('portfolio', 'sbl', etc.)
  query <selector>             - Inspect element text and HTML snippet
  query_all <selector>         - List all matching elements and their inner text
  click <selector>             - Click element (with auto-dismiss popups)
  type <selector> <text>       - Fill input field with text
  eval <javascript>            - Run arbitrary JS on page and print result
  pause                        - Open Playwright Inspector (pause execution)
  screenshot [name]            - Capture screenshot to data/screenshots/
  step <ACTION> <SEL> <VAL> <DESC> - Buffer a verified action step
  steps                        - View buffered steps table
  save                         - Save buffered steps to learned_workflows/<workflow>.md
  help                         - Show this help message
  exit / quit                  - Exit session cleanly
""")

    async def execute_command(self, raw_cmd: str) -> bool:
        cmd = raw_cmd.strip()
        if not cmd:
            return True

        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        try:
            if action in ["exit", "quit", "q"]:
                return False

            elif action == "help":
                self._print_help()

            elif action == "status":
                print(f"• URL: {self.page.url}")
                print(f"• Title: {await self.page.title()}")
                print(f"• Recorded Steps: {len(self.recorded_steps)}")

            elif action == "nav":
                target = args.strip()
                if "://" in target:
                    await self.page.goto(target, wait_until="domcontentloaded")
                elif hasattr(self.broker, "switch_tab"):
                    await self.broker.switch_tab(target)
                else:
                    await self.page.goto(f"https://trademan.in.th/{target}", wait_until="domcontentloaded")
                await self.page.wait_for_timeout(1000)
                await popup_manager.dismiss_popups(self.page)
                print(f"✅ Navigated to: {self.page.url}")

            elif action == "query":
                sel = args.strip()
                el = await self.page.query_selector(sel)
                if not el:
                    print(f"❌ Element not found for: '{sel}'")
                else:
                    txt = (await el.inner_text()).strip()
                    vis = await el.is_visible()
                    print(f"✅ Found! Visible: {vis} | Text: '{txt}'")
                    html = await self.page.evaluate("el => el.outerHTML.substring(0, 300)", el)
                    print(f"   HTML snippet: {html}")

            elif action == "query_all":
                sel = args.strip()
                els = await self.page.query_selector_all(sel)
                print(f"• Found {len(els)} elements matching '{sel}':")
                for i, el in enumerate(els[:15]):
                    txt = (await el.inner_text()).strip()
                    vis = await el.is_visible()
                    print(f"   [{i}] (vis={vis}) '{txt[:80]}'")

            elif action == "click":
                sel = args.strip()
                el = await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                if el:
                    await el.click()
                    await self.page.wait_for_timeout(800)
                    await popup_manager.dismiss_popups(self.page)
                    print(f"✅ Clicked '{sel}'")
                else:
                    print(f"❌ Could not click '{sel}'")

            elif action == "type":
                sub = args.split(maxsplit=1)
                if len(sub) < 2:
                    print("Usage: type <selector> <text>")
                else:
                    sel, txt = sub[0], sub[1]
                    await self.page.fill(sel, txt)
                    print(f"✅ Typed '{txt}' into '{sel}'")

            elif action == "eval":
                res = await self.page.evaluate(args)
                print(f"• Result: {res}")

            elif action == "pause":
                print("⏸️ Pausing execution for Playwright Inspector...")
                await self.page.pause()
                print("▶️ Resumed!")

            elif action == "screenshot":
                name = args.strip() or f"{self.workflow_name}_{int(datetime.now().timestamp())}"
                if not name.endswith(".png"):
                    name += ".png"
                path = os.path.join(PROJECT_ROOT, "data", "screenshots", name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                await self.page.screenshot(path=path)
                print(f"📸 Screenshot saved: {path}")

            elif action == "step":
                # Syntax: step <ACTION> <SEL> <VAL> <DESC>
                # Using comma or pipe separation if provided
                raw_step = args.strip()
                m = re.match(r'^(\S+)\s+(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$', raw_step)
                if m:
                    act_type, sel, val, desc = m.groups()
                else:
                    toks = raw_step.split(maxsplit=3)
                    act_type = toks[0] if len(toks) > 0 else "ACTION"
                    sel = toks[1] if len(toks) > 1 else "-"
                    val = toks[2] if len(toks) > 2 else "-"
                    desc = toks[3] if len(toks) > 3 else "-"

                step_data = {
                    "step": str(len(self.recorded_steps) + 1),
                    "action": act_type.upper(),
                    "selector": sel,
                    "value": val,
                    "description": desc
                }
                self.recorded_steps.append(step_data)
                print(f"📝 Recorded Step {step_data['step']}: {step_data['action']} on '{step_data['selector']}' ({step_data['description']})")

            elif action == "steps":
                if not self.recorded_steps:
                    print("ℹ️  No steps recorded yet. Use 'step <ACTION> <SEL> <VAL> <DESC>' to add.")
                else:
                    print("\nBuffered Workflow Steps:")
                    print("| Step | Action | Target Selector | Value / Args | Description |")
                    print("| :---: | :---: | :--- | :--- | :--- |")
                    for s in self.recorded_steps:
                        print(f"| {s['step']} | `{s['action']}` | `{s['selector']}` | `{s['value']}` | {s['description']} |")
                    print()

            elif action == "save":
                self.save_runbook()

            else:
                print(f"Unknown command: '{action}'. Type 'help' for options.")

        except Exception as e:
            print(f"⚠️ Error executing '{cmd}': {e}")

        return True

    def save_runbook(self):
        if not self.recorded_steps:
            print("⚠️ Cannot save empty workflow. Record at least one step first.")
            return

        runbook_dir = os.path.join(PROJECT_ROOT, "learned_workflows")
        os.makedirs(runbook_dir, exist_ok=True)
        fname = f"{self.workflow_name}.md" if not self.workflow_name.endswith(".md") else self.workflow_name
        fpath = os.path.join(runbook_dir, fname)

        lines = [
            f"# Learned Workflow: {self.workflow_name}",
            f"**Workflow Name:** `{self.workflow_name}`  ",
            f"**Platform:** `{self.platform_name}`  ",
            f"**Recorded At:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Status:** `VERIFIED`  ",
            "",
            "## Description",
            f"Verified human-in-the-loop co-piloted workflow for {self.workflow_name} on {self.platform_name}.",
            "",
            "## Execution Steps",
            "| Step | Action | Target Selector | Value / Arguments | Description |",
            "| :---: | :---: | :--- | :--- | :--- |"
        ]

        for s in self.recorded_steps:
            lines.append(f"| {s['step']} | `{s['action']}` | `{s['selector']}` | `{s['value']}` | {s['description']} |")

        lines.extend([
            "",
            "## Health Verification Rules",
            "- [x] All target selectors must be present and visible in DOM",
            "- [x] No unhandled error modal overlays",
            "",
            "---",
            "*Generated by Watch-and-Learn Interactive Co-piloting Protocol*"
        ])

        with open(fpath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"\n🎉 Successfully saved runbook to: {fpath} ({len(self.recorded_steps)} steps)")


async def main():
    parser = argparse.ArgumentParser(description="Watch-and-Learn Interactive Co-pilot")
    parser.add_argument("--platform", choices=["trademan", "click2win"], default="trademan")
    parser.add_argument("--workflow", default="trademan_account_switch_and_portfolio")
    parser.add_argument("--devtools", action="store_true", help="Launch with DevTools opened")
    parser.add_argument("--exec", type=str, default="", help="Single command to execute and exit")
    args = parser.parse_args()

    session = WatchAndLearnSession(
        platform_name=args.platform,
        workflow_name=args.workflow,
        devtools=args.devtools
    )

    ok = await session.initialize()
    if not ok:
        print("Initialization failed.")
        return

    if args.exec:
        await session.execute_command(args.exec)
        return

    # Interactive REPL
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, input, "watch-and-learn> ")
            cont = await session.execute_command(line)
            if not cont:
                break
        except (EOFError, KeyboardInterrupt):
            print("\nExiting watch-and-learn session...")
            break


if __name__ == "__main__":
    asyncio.run(main())
