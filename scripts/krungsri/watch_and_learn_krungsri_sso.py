#!/usr/bin/env python3
"""
Krungsri SSO Portal & SBL Program Watch-and-Learn Co-Pilot Studio
================================================================
Collaborative Interactive Session following the Watch-and-Learn & Playwright Studio Protocol:
1. Launches Headed Google Chrome on DISPLAY=:0 with active session cookies from data/session_state.json.
2. Navigates directly to Krungsri Securities member portal (https://www.krungsrisecurities.com/th/main/default.aspx).
3. Automatically scans and catalogs all available programs, SSO launchers (start_SSO.aspx?page=...), and menus.
4. Allows interactive user selection from Terminal or direct user clicks in the browser.
5. Captures high-res visual verification snapshots into artifact directory.
6. Records and saves verified navigation paths into learned_workflows/krungsri_sso_sbl.md.
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
logger = logging.getLogger("WatchAndLearn.KrungsriSSO")

ARTIFACT_DIR = "/home/araya-sawasdichai/.gemini/antigravity-ide/brain/d1755cee-0ec2-4505-9300-2a8d4fcb2a94"
RUNBOOK_PATH = os.path.join(PROJECT_ROOT, "learned_workflows", "krungsri_sso_sbl.md")


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


async def scan_portal_programs(page: Page) -> List[Dict[str, Any]]:
    """
    Scans the Krungsri Securities member portal DOM for all available programs,
    SSO buttons, application launchers, and top/side navigation menus.
    """
    js_scanner = """
    () => {
        const items = [];
        const seen = new Set();

        // 1. Scan links with start_SSO or sso in href
        document.querySelectorAll("a[href*='start_SSO'], a[href*='sso' i], a[href*='SSO']").forEach(a => {
            const href = a.getAttribute('href') || '';
            const text = (a.innerText || a.getAttribute('title') || '').trim();
            const img = a.querySelector('img');
            const imgAlt = img ? (img.getAttribute('alt') || img.getAttribute('title') || '') : '';
            const label = text || imgAlt || href;
            
            // Build unique CSS selector
            let selector = '';
            if (a.id) selector = `#${a.id}`;
            else if (a.getAttribute('href')) selector = `a[href='${href}']`;
            else selector = `a:has-text('${label}')`;

            const key = href || selector;
            if (!seen.has(key)) {
                seen.add(key);
                items.push({
                    type: 'SSO_LINK',
                    label: label,
                    href: href,
                    selector: selector,
                    id: a.id || '',
                    target: a.getAttribute('target') || ''
                });
            }
        });

        // 2. Scan right sidebar program icons
        document.querySelectorAll("div[id*='icon'], div[id*='menu'], table[id*='icon'], td[id*='icon']").forEach(div => {
            const a = div.querySelector('a') || div;
            const img = div.querySelector('img');
            const title = div.getAttribute('title') || (img ? img.getAttribute('alt') || img.getAttribute('title') : '') || div.innerText.trim();
            if (title && (title.length < 50)) {
                const selector = div.id ? `#${div.id}` : (img && img.id ? `#${img.id}` : '');
                if (selector && !seen.has(selector)) {
                    seen.add(selector);
                    items.push({
                        type: 'SIDEBAR_ICON',
                        label: title,
                        href: a.getAttribute ? (a.getAttribute('href') || '') : '',
                        selector: selector,
                        id: div.id || (img ? img.id : ''),
                        target: a.getAttribute ? (a.getAttribute('target') || '') : ''
                    });
                }
            }
        });

        // 3. Scan top navigation bar items
        document.querySelectorAll("ul[class*='menu'] > li > a, div[class*='navbar'] a, nav a").forEach(a => {
            const text = a.innerText.trim();
            const href = a.getAttribute('href') || '';
            if (text && text.length > 1 && text.length < 40 && !text.includes('\\n')) {
                const selector = a.id ? `#${a.id}` : `a:has-text('${text}')`;
                if (!seen.has(selector)) {
                    seen.add(selector);
                    items.push({
                        type: 'NAV_MENU',
                        label: text,
                        href: href,
                        selector: selector,
                        id: a.id || '',
                        target: a.getAttribute('target') || ''
                    });
                }
            }
        });

        // 4. Scan any buttons or images with SBL, Stock, or Trade
        document.querySelectorAll("a, button, input[type='button'], img").forEach(el => {
            const alt = el.getAttribute('alt') || el.getAttribute('title') || el.getAttribute('value') || el.innerText || '';
            const altLower = alt.toLowerCase();
            if (altLower.includes('sbl') || altLower.includes('borrow') || altLower.includes('ยืม') || altLower.includes('trademan') || altLower.includes('streaming')) {
                let selector = el.id ? `#${el.id}` : '';
                if (!selector && el.tagName === 'A' && el.getAttribute('href')) selector = `a[href='${el.getAttribute('href')}']`;
                if (!selector) selector = `${el.tagName.toLowerCase()}:has-text('${alt.trim()}')`;
                if (selector && !seen.has(selector)) {
                    seen.add(selector);
                    items.push({
                        type: 'KEYWORD_MATCH',
                        label: alt.trim(),
                        href: el.getAttribute ? (el.getAttribute('href') || '') : '',
                        selector: selector,
                        id: el.id || '',
                        target: el.getAttribute ? (el.getAttribute('target') || '') : ''
                    });
                }
            }
        });

        return items;
    }
    """
    try:
        items = await page.evaluate(js_scanner)
        return items
    except Exception as e:
        logger.warning(f"Error scanning DOM: {e}")
        return []


async def run_studio():
    session_file = settings.SESSION_STATE_PATH
    if not os.path.exists(session_file):
        print(f"{C_RED}❌ Error: {session_file} does not exist. Please run ./start_homelab.sh first.{C_RESET}")
        return

    print("\n" + "=" * 80)
    print(f"{C_BOLD}{C_MAGENTA}🎬 PLAYWRIGHT STUDIO & WATCH-AND-LEARN CO-PILOT: KRUNGSRI SSO PORTAL{C_RESET}")
    print("=" * 80)
    print(" • Purpose: Discover and learn the real SBL program from Krungsri Member Portal")
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
            "--window-size=1560,960",
            "--start-maximized"
        ]
    }
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        launch_kwargs["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE

    print("\n[1/4] Launching Google Chrome and loading saved session state...")
    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        storage_state=session_file,
        viewport={"width": 1560, "height": 960}
    )

    portal_url = getattr(settings, "KRUNGSRI_LOGIN_URL", "https://www.krungsrisecurities.com/th/main/default.aspx")
    print(f"[2/4] Navigating directly to Krungsri Portal: {C_CYAN}{portal_url}{C_RESET}")
    page = await context.new_page()

    # Track newly opened popup tabs
    pages_list = [page]
    def on_page_opened(p):
        print(f"\n{C_GREEN}🌐 New Browser Tab / Popup Opened!{C_RESET} -> {p.url}")
        pages_list.append(p)
    context.on("page", on_page_opened)

    try:
        await page.goto(portal_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"{C_YELLOW}⚠️ Page navigation warning: {e}{C_RESET}")

    # Dismiss any announcement popup
    try:
        ack_btn = await page.query_selector("text='รับทราบ', button:has-text('รับทราบ'), a:has-text('รับทราบ'), input[value*='รับทราบ']")
        if ack_btn and await ack_btn.is_visible():
            print("   📢 Dismissing announcement modal ('รับทราบ')...")
            await ack_btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    # Capture initial portal overview
    print("\n[3/4] Capturing portal overview screenshot...")
    await capture_snapshot(page, "krungsri_sso_portal_overview.png")

    # Catalog recorded workflow steps
    recorded_steps = [
        {"action": "NAVIGATE", "target": portal_url, "description": "Open Krungsri Member Portal"}
    ]

    # Interactive Co-Pilot Loop
    current_page = page
    while True:
        # Check active pages
        active_pages = [p for p in context.pages if not p.is_closed()]
        if not active_pages:
            print("All browser windows closed. Exiting studio.")
            break
        current_page = active_pages[-1]

        current_url = current_page.url
        current_title = await current_page.title()
        print("\n" + "=" * 80)
        print(f"{C_BOLD}📍 ACTIVE TAB:{C_RESET} {C_CYAN}{current_url}{C_RESET} | {C_YELLOW}'{current_title}'{C_RESET}")
        print("=" * 80)

        # Scan programs and links
        programs = await scan_portal_programs(current_page)
        if programs:
            print(f"{C_BOLD}📋 Detected {len(programs)} Program Launchers & Menu Items on this page:{C_RESET}")
            print(f"  {'#':<4} {'TYPE':<15} {'LABEL / NAME':<35} {'SELECTOR / HREF':<40}")
            print("  " + "-" * 95)
            for idx, item in enumerate(programs, start=1):
                lbl = item['label'][:33]
                desc = (item['selector'] or item['href'])[:38]
                print(f"  {idx:<4} {item['type']:<15} {C_GREEN}{lbl:<35}{C_RESET} {C_DIM}{desc:<40}{C_RESET}")
            print("  " + "-" * 95)
        else:
            print("  ℹ️ No standard SSO launcher items detected via regex. You can click directly in the browser.")

        print(f"\n{C_BOLD}🎮 Interactive Co-Pilot Commands:{C_RESET}")
        print(f"  • {C_CYAN}1 - {len(programs)}{C_RESET}  : Type number to highlight & click that program")
        print(f"  • {C_CYAN}click <selector>{C_RESET} : Click specific CSS selector or text")
        print(f"  • {C_CYAN}rescan{C_RESET}            : Re-scan current page elements")
        print(f"  • {C_CYAN}shot{C_RESET}              : Capture high-res screenshot of active tab")
        print(f"  • {C_CYAN}save{C_RESET}              : Save recorded workflow to {RUNBOOK_PATH}")
        print(f"  • {C_CYAN}q{C_RESET}                 : Quit studio")
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
            filename = f"sso_step_{int(time.time())}.png"
            await capture_snapshot(current_page, filename)
            continue

        if cmd.lower() == "rescan":
            continue

        if cmd.lower() == "save":
            _save_workflow(recorded_steps)
            continue

        if cmd.lower().startswith("click "):
            target_sel = cmd[6:].strip()
            print(f"Highlighting & clicking '{target_sel}'...")
            await highlight_element(current_page, target_sel, color="#ff007f")
            try:
                await current_page.click(target_sel, timeout=5000)
                await current_page.wait_for_timeout(2000)
                recorded_steps.append({
                    "action": "CLICK",
                    "target": target_sel,
                    "description": f"Clicked {target_sel} on {current_url}"
                })
            except Exception as e:
                print(f"{C_RED}Click failed: {e}{C_RESET}")
            continue

        # Check if user entered a number
        if cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(programs):
                target_item = programs[idx]
                target_sel = target_item['selector']
                target_lbl = target_item['label']
                print(f"\n🎯 [CO-PILOT ACTION] Selecting #{cmd}: {C_GREEN}{target_lbl}{C_RESET} ({target_sel})")
                await highlight_element(current_page, target_sel, color="#00ffcc", delay_ms=800)

                try:
                    # Expect potential popup
                    try:
                        async with current_page.expect_popup(timeout=5000) as popup_info:
                            await current_page.click(target_sel)
                        new_tab = await popup_info.value
                        print(f"🎉 New popup tab opened: {C_GREEN}{new_tab.url}{C_RESET}")
                        current_page = new_tab
                    except Exception:
                        await current_page.click(target_sel)
                        await current_page.wait_for_timeout(2500)

                    # Snapshot the result
                    snap_name = f"program_{cmd}_{int(time.time())}.png"
                    await capture_snapshot(current_page, snap_name)

                    recorded_steps.append({
                        "action": "LAUNCH_PROGRAM",
                        "target": target_sel,
                        "label": target_lbl,
                        "url_after": current_page.url,
                        "description": f"Launched program '{target_lbl}' via {target_sel}"
                    })
                except Exception as e:
                    print(f"{C_RED}Failed to click #{cmd}: {e}{C_RESET}")
            else:
                print(f"{C_RED}Invalid number. Please enter 1 to {len(programs)}.{C_RESET}")

    print("\n[4/4] Closing browser context...")
    _save_workflow(recorded_steps)
    await browser.close()
    await playwright.stop()
    print(f"\n{C_GREEN}✅ Studio session completed.{C_RESET}\n")


def _save_workflow(steps: List[Dict[str, Any]]):
    """Saves recorded workflow steps to learned_workflows/krungsri_sso_sbl.md."""
    os.makedirs(os.path.dirname(RUNBOOK_PATH), exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Krungsri SSO SBL Program Navigation Runbook",
        "",
        f"- **Generated At**: {now_str}",
        "- **Platform**: Krungsri Securities Member SSO Portal",
        "- **Authentication**: Pre-authenticated session state (`data/session_state.json`)",
        "- **Methodology**: Watch-and-Learn Interactive Co-pilot Protocol",
        "",
        "## Verified Navigation Steps",
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
        "## Code Usage Example",
        "```python",
        "# To execute this verified workflow autonomously in production:",
        "from app.browser.auth_driver import auth_driver",
        "",
        "# 1. Launch browser with saved session",
        "page = await auth_driver.launch_browser(resume_state=True)",
        "# 2. Navigate to portal",
        f"await page.goto('{settings.KRUNGSRI_LOGIN_URL}')",
        "```",
        ""
    ])

    with open(RUNBOOK_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n{C_GREEN}💾 Saved {len(steps)} steps to {RUNBOOK_PATH}{C_RESET}")


if __name__ == "__main__":
    asyncio.run(run_studio())
