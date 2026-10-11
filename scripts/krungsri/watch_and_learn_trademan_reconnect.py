#!/usr/bin/env python3
"""
TradeMan Session Reconnect & Full Auto-Healing Watch-and-Learn Studio
====================================================================
Interactive Human-in-the-Loop Playwright Co-pilot for TradeMan Session Reconnect:
1. Launches Headed Google Chrome on DISPLAY=:0 with active session cookies from data/session_state.json.
2. Navigates to TradeMan (https://trademan.in.th/Portfolio).
3. Detects any active connection timeout, reconnect modals, overlay dialogs, or disconnect banners.
4. Allows interactive user inspection, clicking via terminal or directly on screen.
5. Can simulate network drop (offline/online) to reproduce reconnect prompts reliably.
6. Records and saves verified selectors into learned_workflows/trademan_session_reconnect.md.
"""

import os
import sys
import time
import json
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from playwright.async_api import async_playwright, Page, BrowserContext, Browser

from app.core.config import settings

# ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("WatchAndLearn.TradeManReconnect")

ARTIFACT_DIR = "/home/araya-sawasdichai/.gemini/antigravity-ide/brain/d1755cee-0ec2-4505-9300-2a8d4fcb2a94"
RUNBOOK_PATH = os.path.join(PROJECT_ROOT, "learned_workflows", "trademan_session_reconnect.md")


async def highlight_element(page: Page, selector: str, color: str = "#00ffcc", delay_ms: int = 400):
    """Applies glowing visual co-pilot outline on target element."""
    try:
        await page.evaluate(f"""
            (sel) => {{
                const el = document.querySelector(sel);
                if (el) {{
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    el.style.outline = '3px solid {color}';
                    el.style.boxShadow = '0 0 16px {color}';
                    el.style.transition = 'all 0.3s ease';
                }}
            }}
        """, selector)
        if delay_ms > 0:
            await page.wait_for_timeout(delay_ms)
    except Exception:
        pass


async def capture_snapshot(page: Page, filename: str) -> str:
    """Captures verification screenshot into artifact directory."""
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    filepath = os.path.join(ARTIFACT_DIR, filename)
    await page.screenshot(path=filepath, full_page=False)
    print(f"   📸 Screenshot captured: {C_CYAN}{filepath}{C_RESET}")
    return filepath


async def scan_reconnect_modals(page: Page) -> List[Dict[str, Any]]:
    """
    Scans TradeMan DOM for active modal dialogs, reconnect buttons, snackbars, and overlays.
    """
    js_scanner = """
    () => {
        const items = [];
        const seen = new Set();

        // 1. Scan active overlays and dialogs
        document.querySelectorAll(".v-overlay--active, .v-dialog, [role='dialog'], .v-card, .v-snackbar, .v-alert, .modal").forEach((dialog, dIdx) => {
            const isVisible = dialog.offsetParent !== null || dialog.classList.contains('v-overlay--active');
            const dText = dialog.innerText.trim();
            
            // Check buttons inside dialog
            dialog.querySelectorAll("button, a, input[type='button'], span[role='button']").forEach(btn => {
                const bText = (btn.innerText || btn.getAttribute('value') || btn.getAttribute('title') || '').trim();
                let sel = '';
                if (btn.id) sel = `#${btn.id}`;
                else if (btn.className && typeof btn.className === 'string') {
                    const firstCls = btn.className.split(' ').filter(c => c && !c.includes(':'))[0];
                    if (firstCls) sel = `button.${firstCls}:has-text('${bText}')`;
                }
                if (!sel) sel = `button:has-text('${bText}')`;

                const key = sel + bText;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        type: 'MODAL_BUTTON',
                        label: bText || 'Button',
                        selector: sel,
                        parent_text: dText.substring(0, 80).replace(/\\n/g, ' '),
                        visible: isVisible
                    });
                }
            });
        });

        // 2. Scan any elements containing reconnect or connection keywords
        document.querySelectorAll("button, a, div, span, p").forEach(el => {
            const txt = (el.innerText || '').trim();
            const txtLower = txt.toLowerCase();
            const keywords = ['reconnect', 'เชื่อมต่อ', 'ตัดการเชื่อมต่อ', 'หมดอายุ', 'timeout', 'หลุด', 'session expired', 'ลองใหม่', 'retry'];
            const matches = keywords.some(k => txtLower.includes(k));
            
            if (matches && txt.length < 80 && el.children.length <= 1) {
                let sel = el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}:has-text('${txt}')`;
                if (!seen.has(sel)) {
                    seen.add(sel);
                    items.push({
                        type: 'KEYWORD_ELEMENT',
                        label: txt,
                        selector: sel,
                        parent_text: el.parentElement ? el.parentElement.innerText.substring(0, 60).replace(/\\n/g, ' ') : '',
                        visible: el.offsetParent !== null
                    });
                }
            }
        });

        return items;
    }
    """
    try:
        return await page.evaluate(js_scanner)
    except Exception as e:
        logger.warning(f"Error scanning reconnect modals: {e}")
        return []


async def run_studio():
    session_file = settings.SESSION_STATE_PATH
    if not os.path.exists(session_file):
        print(f"{C_RED}❌ Error: {session_file} does not exist. Please run ./start_homelab.sh first.{C_RESET}")
        return

    print("\n" + "=" * 80)
    print(f"{C_BOLD}{C_MAGENTA}🎬 PLAYWRIGHT STUDIO & WATCH-AND-LEARN CO-PILOT: TRADEMAN RECONNECT{C_RESET}")
    print("=" * 80)
    print(" • Purpose: Inspect, Learn, and Master TradeMan Session Reconnect Flow")
    print(f" • Mode:    {C_GREEN}Headed Chrome (Visible on DISPLAY=:0){C_RESET}")
    print(f" • State:   {session_file}")
    print("=" * 80)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    playwright = await async_playwright().start()
    launch_kwargs = {
        "headless": False,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1600,960",
            "--start-maximized"
        ]
    }
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        launch_kwargs["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE

    print("\n[1/3] Launching Google Chrome and loading saved session state...")
    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        storage_state=session_file,
        viewport={"width": 1600, "height": 960}
    )

    page = await context.new_page()
    target_url = "https://trademan.in.th/Portfolio"
    print(f"[2/3] Navigating to TradeMan: {C_CYAN}{target_url}{C_RESET}")

    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"{C_YELLOW}⚠️ Page navigation notice: {e}{C_RESET}")

    # Capture initial view
    print("\n[3/3] Capturing initial screenshot...")
    await capture_snapshot(page, "trademan_reconnect_initial.png")

    recorded_steps = [
        {"action": "NAVIGATE", "target": target_url, "description": "Open TradeMan Portfolio"}
    ]

    is_offline = False

    while True:
        if page.is_closed():
            print("Browser window closed. Exiting studio.")
            break

        current_url = page.url
        current_title = await page.title()
        print("\n" + "=" * 80)
        print(f"{C_BOLD}📍 ACTIVE TAB:{C_RESET} {C_CYAN}{current_url}{C_RESET} | {C_YELLOW}'{current_title}'{C_RESET}")
        print("=" * 80)

        # Scan reconnect items
        items = await scan_reconnect_modals(page)
        if items:
            print(f"{C_BOLD}🚨 Detected {len(items)} Reconnect / Modal Elements:{C_RESET}")
            print(f"  {'#':<4} {'TYPE':<16} {'LABEL / BUTTON':<30} {'PARENT CONTEXT / TEXT':<40}")
            print("  " + "-" * 95)
            for idx, itm in enumerate(items, start=1):
                lbl = itm['label'][:28]
                ctx = itm['parent_text'][:38]
                vis = "🟢" if itm.get('visible') else "⚪"
                print(f"  {idx:<4} {itm['type']:<16} {vis} {C_GREEN}{lbl:<28}{C_RESET} {C_DIM}{ctx:<40}{C_RESET}")
            print("  " + "-" * 95)
        else:
            print("  ℹ️ No active Reconnect Modal detected right now. (Page is healthy or connected)")

        print(f"\n{C_BOLD}🎮 Interactive Co-Pilot Commands:{C_RESET}")
        if items:
            print(f"  • {C_CYAN}1 - {len(items)}{C_RESET}  : Type number to highlight & click that reconnect button")
        print(f"  • {C_CYAN}click <selector>{C_RESET} : Click specific CSS selector or text")
        print(f"  • {C_CYAN}offline{C_RESET}          : Toggle Network Offline/Online (trigger reconnect modal)")
        print(f"  • {C_CYAN}reload{C_RESET}           : Soft Reload TradeMan page (preserves session)")
        print(f"  • {C_CYAN}shot{C_RESET}             : Capture high-res screenshot")
        print(f"  • {C_CYAN}rescan{C_RESET}           : Re-scan current page elements")
        print(f"  • {C_CYAN}save{C_RESET}             : Save recorded workflow to {RUNBOOK_PATH}")
        print(f"  • {C_CYAN}q{C_RESET}                : Quit studio")
        print(f"  • {C_YELLOW}หรือคลิกที่หน้าจอ Chrome ได้โดยตรงเลยครับ ระบบจะตรวจจับหน้าใหม่อัตโนมัติ{C_RESET}")

        loop = asyncio.get_running_loop()
        try:
            print(f"\n{C_BOLD}Co-Pilot Input > {C_RESET}", end="", flush=True)
            user_input = await loop.run_in_executor(None, sys.stdin.readline)
            cmd = user_input.strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd:
            continue

        if cmd.lower() in ("q", "quit", "exit"):
            break

        if cmd.lower() == "shot":
            filename = f"trademan_step_{int(time.time())}.png"
            await capture_snapshot(page, filename)
            continue

        if cmd.lower() == "rescan":
            continue

        if cmd.lower() == "reload":
            print("Reloading TradeMan page...")
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            recorded_steps.append({
                "action": "SOFT_RELOAD",
                "target": "page.reload()",
                "description": "Soft reloaded TradeMan page to recover session"
            })
            await capture_snapshot(page, f"trademan_reloaded_{int(time.time())}.png")
            continue

        if cmd.lower() == "offline":
            is_offline = not is_offline
            if is_offline:
                print(f"{C_RED}⚡ Simulating NETWORK OFFLINE...{C_RESET}")
                await context.set_offline(True)
                print("Network is now OFFLINE. TradeMan should detect disconnect within 10-20s.")
            else:
                print(f"{C_GREEN}⚡ Simulating NETWORK ONLINE...{C_RESET}")
                await context.set_offline(False)
                print("Network is now ONLINE.")
            await page.wait_for_timeout(2000)
            continue

        if cmd.lower() == "save":
            _save_workflow(recorded_steps)
            continue

        if cmd.lower().startswith("click "):
            target_sel = cmd[6:].strip()
            print(f"Highlighting & clicking '{target_sel}'...")
            await highlight_element(page, target_sel, color="#ff007f")
            try:
                await page.click(target_sel, timeout=5000)
                await page.wait_for_timeout(2500)
                recorded_steps.append({
                    "action": "CLICK",
                    "target": target_sel,
                    "description": f"Clicked {target_sel} on TradeMan"
                })
                await capture_snapshot(page, f"trademan_clicked_{int(time.time())}.png")
            except Exception as e:
                print(f"{C_RED}Click failed: {e}{C_RESET}")
            continue

        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(items):
                target_item = items[idx]
                target_sel = target_item['selector']
                target_lbl = target_item['label']
                print(f"\n🎯 [CO-PILOT ACTION] Selecting #{cmd}: {C_GREEN}{target_lbl}{C_RESET} ({target_sel})")
                await highlight_element(page, target_sel, color="#00ffcc", delay_ms=600)
                try:
                    await page.click(target_sel, timeout=5000)
                    await page.wait_for_timeout(3000)
                    recorded_steps.append({
                        "action": "RECONNECT_CLICK",
                        "target": target_sel,
                        "label": target_lbl,
                        "description": f"Clicked Reconnect button '{target_lbl}' ({target_sel})"
                    })
                    await capture_snapshot(page, f"trademan_reconnected_{int(time.time())}.png")
                except Exception as e:
                    print(f"{C_RED}Click failed: {e}{C_RESET}")
            else:
                print(f"{C_RED}Invalid number. Enter 1 to {len(items)}.{C_RESET}")

    print("\nClosing browser...")
    _save_workflow(recorded_steps)
    await browser.close()
    await playwright.stop()
    print(f"\n{C_GREEN}✅ TradeMan Reconnect studio session completed.{C_RESET}\n")


def _save_workflow(steps: List[Dict[str, Any]]):
    """Saves recorded workflow to learned_workflows/trademan_session_reconnect.md."""
    os.makedirs(os.path.dirname(RUNBOOK_PATH), exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# TradeMan Session Reconnect & Auto-Healing Runbook",
        "",
        f"- **Generated At**: {now_str}",
        "- **Platform**: Krungsri TradeMan (`https://trademan.in.th/Portfolio`)",
        "- **Protocol**: Watch-and-Learn Interactive Co-pilot Protocol (`/watch-and-learn`, `/playwright-studio`)",
        "- **Strategy**: 4-Tier Full Auto-Healing (Modal Reconnect -> Soft Reload -> LINE/KDE Alert)",
        "",
        "## Verified Recovery Steps",
        "",
        "| Step | Action | Target / Selector | Description |",
        "| :--- | :--- | :--- | :--- |"
    ]
    for idx, s in enumerate(steps, start=1):
        act = s.get('action', '-')
        tgt = s.get('target', '-')
        desc = s.get('description', s.get('label', '-'))
        lines.append(f"| {idx} | `{act}` | `{tgt}` | {desc} |")

    lines.extend([
        "",
        "## Multi-Tier Auto-Healing Implementation",
        "```python",
        "# Production Auto-Healing Strategy for SessionSentinel:",
        "async def heal_trademan_session(page):",
        "    # Tier 1: Check for active Reconnect modal",
        "    reconnect_btn = await page.query_selector(\"button:has-text('Reconnect'), button:has-text('เชื่อมต่อใหม่')\")",
        "    if reconnect_btn and await reconnect_btn.is_visible():",
        "        await reconnect_btn.click()",
        "        await page.wait_for_timeout(3000)",
        "        return True",
        "    ",
        "    # Tier 2: Soft Reload",
        "    await page.reload(wait_until='domcontentloaded')",
        "    await page.wait_for_timeout(3000)",
        "    return True",
        "```",
        ""
    ])

    with open(RUNBOOK_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n{C_GREEN}💾 Saved {len(steps)} steps to {RUNBOOK_PATH}{C_RESET}")


if __name__ == "__main__":
    asyncio.run(run_studio())
