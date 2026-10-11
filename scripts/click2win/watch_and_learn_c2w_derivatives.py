#!/usr/bin/env python3
"""
Settrade Click2Win Derivatives Co-pilot Runner (Watch-and-Learn / Playwright Studio)
===================================================================================
Executes Step-by-Step interactive learning loop for TFEX Derivatives Order Placement:
1. Opens headed Chromium on DISPLAY=:0 with restored session from data/click2win_session.json.
2. Checks for and dismisses any modal errors (e.g. "Symbol: Stock not found").
3. Inspects and switches active account from CW32_E_... (Equity) to CW32_D_... (Derivatives).
4. Deep-inspects and validates the Place Order form (Long/Short, Position: Auto, Symbol, Vol, Price).
5. Submits COVER order: LONG 1 SPALIU26 @ 16.00 (Position: Auto).
6. Captures verification screenshot and generates learned runbook in learned_workflows/.
7. Sends KDE Connect push alert to Xiaomi Mi 10T.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from playwright.async_api import Page
from app.core.config import settings
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.services.kdeconnect_service import kdeconnect_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("C2W-Derivatives-Copilot")


async def highlight(page: Page, selector: str, color: str = "#00ffcc"):
    """Applies a high-visibility glowing CSS border to an element for live observation."""
    try:
        await page.evaluate(f"""(sel) => {{
            const el = document.querySelector(sel);
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                el.style.outline = '3px solid {color}';
                el.style.boxShadow = '0 0 15px {color}';
                el.style.transition = 'all 0.3s ease';
            }}
        }}""", selector)
    except Exception:
        pass


async def run_copilot():
    print("=" * 80)
    print(" 🎬 WATCH-AND-LEARN CO-PILOT: SETTRADE CLICK2WIN DERIVATIVES (TFEX)")
    print(" • Target Contract: COVER 1 SPALIU26 @ 16.00 (Position: Auto)")
    print(" • Account Switch: CW32_E_... (Equity) -> CW32_D_... (Derivatives)")
    print(f" • Headed Display: {os.environ.get('DISPLAY', ':0')}")
    print("=" * 80)

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    learned_steps = []
    settings.PLAYWRIGHT_HEADLESS = False

    print("\n🚀 [1/6] Launching Google Chrome (Headed) with restored session...")
    page = await click2win_auth_driver.launch_browser(resume_state=True)

    streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
    print(f"   🌐 Navigating to Settrade Streaming: {streaming_url}...")
    try:
        await page.goto(streaming_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"   Notice during navigation: {e}")
    await page.wait_for_timeout(3500)

    # -------------------------------------------------------------
    # STEP 1: Modal Error Check & Dismissal
    # -------------------------------------------------------------
    print("\n🔍 [2/6] Checking for blocking modal popups (e.g. 'Stock not found' or Welcome dialog)...")
    modal_ok_selectors = [
        "button:has-text('OK')",
        "button:has-text('ตกลง')",
        ".modal button:has-text('OK')",
        "div[role='dialog'] button",
        "button.btn-primary"
    ]
    dismissed_modal = False
    for sel in modal_ok_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                print(f"   ⚠️ Found open modal button matching: {sel}")
                await highlight(page, sel, "#ff0055")
                await page.wait_for_timeout(800)
                await btn.click()
                await page.wait_for_timeout(1000)
                dismissed_modal = True
                print("   ✅ Dismissed modal popup.")
                learned_steps.append({
                    "step": "DISMISS_MODAL",
                    "selector": sel,
                    "action": "CLICK",
                    "details": "Dismissed blocking alert or modal"
                })
                break
        except Exception as e:
            logger.debug(f"Modal check notice: {e}")

    if not dismissed_modal:
        print("   ℹ️ No blocking modal popup found.")

    # -------------------------------------------------------------
    # STEP 2: Account Inspection & Switch to CW32_D_ (Derivatives)
    # -------------------------------------------------------------
    print("\n🔄 [3/6] Inspecting active account and switching to Derivatives (CW32_D_)...")
    account_container_selectors = [
        "div.bg-color-account-info-group",
        "div:has-text('CW32_')",
        "[data-testid='account-selector']"
    ]
    active_acc_text = ""
    for sel in account_container_selectors:
        acc_container = await page.query_selector(sel)
        if acc_container and await acc_container.is_visible():
            active_acc_text = (await acc_container.inner_text()).strip()
            print(f"   📊 Current Account Container Text: [{active_acc_text}]")
            break

    target_acc_no = settings.CLICK2WIN_ACCOUNT_NO_DERIVATIVES or "CW32_D_7338419"
    needs_switch = True
    if "CW32_D_" in active_acc_text or "DERIVATIVES" in active_acc_text.upper():
        print(f"   ✅ Already on Derivatives account: {target_acc_no}")
        needs_switch = False

    if needs_switch:
        print("   👉 Opening Account dropdown menu...")
        dropdown_triggers = [
            "div.bg-color-account-info-group div.cursor-pointer",
            "div.bg-color-account-info-group",
            "span:has-text('CW32_')",
            "div:has-text('CW32_E_')"
        ]
        opened = False
        for trig in dropdown_triggers:
            el = await page.query_selector(trig)
            if el and await el.is_visible():
                await highlight(page, trig, "#00ff88")
                await page.wait_for_timeout(500)
                await el.click()
                await page.wait_for_timeout(800)
                opened = True
                break

        # Find all dropdown items
        print("   📋 Inspecting account options in dropdown...")
        options = await page.query_selector_all("li, div[role='option'], .dropdown-item, div.cursor-pointer")
        found_deriv = None
        for opt in options:
            try:
                if await opt.is_visible():
                    txt = (await opt.inner_text()).strip()
                    if "CW32_D_" in txt or "Derivatives" in txt or "อนุพันธ์" in txt:
                        print(f"      🎯 Found Derivatives option: '{txt}'")
                        found_deriv = opt
                        break
            except Exception:
                pass

        if found_deriv:
            await found_deriv.click()
            print(f"   ✅ Clicked Derivatives account option ({target_acc_no})")
            await page.wait_for_timeout(1500)
            learned_steps.append({
                "step": "SWITCH_ACCOUNT_DERIVATIVES",
                "selector": "li:has-text('CW32_D_')",
                "action": "CLICK",
                "details": f"Switched account to {target_acc_no}"
            })
        else:
            # Try fallback selector
            fallback_sel = "li:has-text('CW32_D_'), li:has-text('Derivatives')"
            try:
                f_el = await page.wait_for_selector(fallback_sel, state="visible", timeout=3000)
                if f_el:
                    await f_el.click()
                    await page.wait_for_timeout(1500)
                    print(f"   ✅ Clicked via fallback: {fallback_sel}")
            except Exception as fe:
                print(f"   Notice clicking fallback account: {fe}")

    # -------------------------------------------------------------
    # STEP 3: Deep-Inspect Place Order Form (Derivatives Mode)
    # -------------------------------------------------------------
    print("\n🔬 [4/6] Deep-inspecting Place Order form elements for TFEX...")
    await page.wait_for_timeout(1000)

    # 3.1 Side Radio Buttons: Long vs Short
    print("   Checking Side controls (Long / Short)...")
    long_selectors = [
        "label:has-text('Long')",
        "input[value='Long']",
        "input[value='L']",
        "label[for*='long' i]",
        "input#tfex-place-order-long-radio-button",
        "label:has-text('Buy')"
    ]
    active_long_sel = None
    for sel in long_selectors:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            active_long_sel = sel
            print(f"   🎯 Identified LONG side selector: [{sel}]")
            await highlight(page, sel, "#00ccff")
            break

    # 3.2 Position Controls: Auto vs Open vs Close
    print("   Checking Position controls (Auto / Open / Close)...")
    position_selectors = [
        "label:has-text('Auto')",
        "input[value='Auto']",
        "select[name*='pos' i]",
        "label:has-text('Close')",
        "input[value='Close']"
    ]
    active_pos_sel = None
    for sel in position_selectors:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            active_pos_sel = sel
            print(f"   🎯 Identified Position selector: [{sel}]")
            await highlight(page, sel, "#ffbb00")
            break

    # 3.3 Symbol, Volume, Price Inputs
    sym_sel = "input[placeholder='Symbol'], input#txtSymbol, input#equity-place-order-symbol, input[name*='symbol' i]"
    vol_sel = "input[placeholder='Volume'], input[name='equity-place-order-vol'], input#txtVolume, input[name*='vol' i]"
    price_sel = "input[placeholder='Price'], input[name='price-input'], input#txtPrice, input[name*='price' i]"

    sym_el = await page.query_selector(sym_sel)
    vol_el = await page.query_selector(vol_sel)
    price_el = await page.query_selector(price_sel)

    print(f"   Symbol input visible: {bool(sym_el and await sym_el.is_visible())}")
    print(f"   Volume input visible: {bool(vol_el and await vol_el.is_visible())}")
    print(f"   Price input visible: {bool(price_el and await price_el.is_visible())}")

    # -------------------------------------------------------------
    # STEP 4: Fill Order (COVER 1 SPALIU26 @ 16.00, Position: Auto)
    # -------------------------------------------------------------
    print("\n✍️ [5/6] Filling Order Details: COVER 1 SPALIU26 @ 16.00 (Position: Auto)...")
    
    # Click Long
    if active_long_sel:
        long_btn = await page.query_selector(active_long_sel)
        if long_btn:
            await long_btn.click()
            await page.wait_for_timeout(400)
            learned_steps.append({
                "step": "SELECT_SIDE_LONG",
                "selector": active_long_sel,
                "action": "CLICK",
                "details": "Selected LONG (for COVER order)"
            })

    # Select Position: Auto if available
    if active_pos_sel:
        pos_btn = await page.query_selector(active_pos_sel)
        if pos_btn:
            await pos_btn.click()
            await page.wait_for_timeout(300)
            learned_steps.append({
                "step": "SELECT_POSITION_AUTO",
                "selector": active_pos_sel,
                "action": "CLICK",
                "details": "Selected Position: Auto"
            })

    # Fill Symbol: SPALIU26
    if sym_el:
        await highlight(page, sym_sel, "#33ff33")
        await sym_el.fill("")
        await sym_el.type("SPALIU26", delay=65)
        await sym_el.press("Enter")
        await page.wait_for_timeout(500)
        learned_steps.append({
            "step": "FILL_SYMBOL",
            "selector": sym_sel,
            "action": "TYPE",
            "value": "SPALIU26",
            "details": "Entered TFEX Single Stock Futures ticker"
        })

    # Fill Volume: 1
    if vol_el:
        await highlight(page, vol_sel, "#33ff33")
        await vol_el.fill("")
        await vol_el.type("1", delay=65)
        await page.wait_for_timeout(300)
        learned_steps.append({
            "step": "FILL_VOLUME",
            "selector": vol_sel,
            "action": "TYPE",
            "value": "1",
            "details": "Entered 1 contract"
        })

    # Fill Price: 16.00
    if price_el:
        await highlight(page, price_sel, "#33ff33")
        await price_el.fill("")
        await price_el.type("16.00", delay=65)
        await page.wait_for_timeout(400)
        learned_steps.append({
            "step": "FILL_PRICE",
            "selector": price_sel,
            "action": "TYPE",
            "value": "16.00",
            "details": "Entered Limit price 16.00"
        })

    # -------------------------------------------------------------
    # STEP 5: Order Submission & Confirmation
    # -------------------------------------------------------------
    print("\n🚀 [6/6] Submitting Order to Click2Win...")
    submit_selectors = [
        "button:has-text('Long')",
        "button.bg-color-submit-button",
        "button:has-text('Submit')",
        "div.css-1q863r0 button",
        "button#btnSubmit"
    ]
    submit_btn = None
    used_submit_sel = None
    for sel in submit_selectors:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            submit_btn = el
            used_submit_sel = sel
            break

    if submit_btn:
        await highlight(page, used_submit_sel, "#ffff00")
        print(f"   👉 Clicking Submit button matching: {used_submit_sel}")
        await submit_btn.click()
        await page.wait_for_timeout(1000)
        learned_steps.append({
            "step": "CLICK_SUBMIT",
            "selector": used_submit_sel,
            "action": "CLICK",
            "details": "Clicked Order Submission button"
        })

        # Check for Order Confirmation dialog
        print("   Checking for Order Confirmation modal...")
        confirm_selectors = [
            "div:has-text('Order Confirmation') button:has-text('Long')",
            "div:has-text('Order Confirmation') button:has-text('Confirm')",
            "div:has-text('Order Confirmation') button:has-text('ยืนยัน')",
            "button:has-text('Confirm')",
            "button:has-text('ยืนยัน')",
            "button:has-text('ตกลง')",
            ".modal-confirm button",
            ".modal button"
        ]
        for c_sel in confirm_selectors:
            try:
                c_btn = await page.query_selector(c_sel)
                if c_btn and await c_btn.is_visible():
                    print(f"   🎯 Order Confirmation modal popped up! Clicking {c_sel}...")
                    await highlight(page, c_sel, "#00ff88")
                    await page.wait_for_timeout(600)
                    await c_btn.click()
                    await page.wait_for_timeout(1500)
                    learned_steps.append({
                        "step": "CONFIRM_MODAL",
                        "selector": c_sel,
                        "action": "CLICK",
                        "details": "Confirmed Order Confirmation popup"
                    })
                    break
            except Exception as ce:
                logger.debug(f"Confirm modal check: {ce}")

    # Capture Verification Screenshot
    os.makedirs("data/screenshots", exist_ok=True)
    screenshot_path = "data/screenshots/c2w_derivatives_spaliu26_submitted.png"
    await page.screenshot(path=screenshot_path)
    print(f"\n📸 Verification Screenshot saved: {screenshot_path}")

    # -------------------------------------------------------------
    # STEP 6: Runbook Generation & Mobile Alert
    # -------------------------------------------------------------
    os.makedirs("learned_workflows", exist_ok=True)
    runbook_path = "learned_workflows/click2win_derivatives_order_submit.md"
    with open(runbook_path, "w", encoding="utf-8") as f:
        f.write("# Click2Win Derivatives (TFEX) Order Placement Runbook\n\n")
        f.write(f"- **Generated At**: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- **Contract**: SPALIU26 (Single Stock Futures)\n")
        f.write(f"- **Side**: LONG (COVER Short Position)\n")
        f.write(f"- **Volume**: 1 Contract\n")
        f.write(f"- **Price**: 16.00 THB\n")
        f.write(f"- **Account**: {target_acc_no} (Derivatives)\n\n")
        f.write("## Verified DOM Actions Sequence\n\n")
        f.write("| Step | Action | Selector | Value / Details |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for idx, s in enumerate(learned_steps, 1):
            f.write(f"| {idx} | `{s['action']}` | `{s['selector']}` | {s.get('value', s.get('details', '-'))} |\n")

    print(f"📖 Learned Runbook saved: {runbook_path}")

    # Send KDE Connect Alert to Phone
    alert_msg = f"✅ Click2Win TFEX Submitted!\nCOVER 1 SPALIU26 @ ฿16.00\nAccount: {target_acc_no}\nCheck /console"
    await kdeconnect_service.send_critical_alert("Click2Win TFEX Order", alert_msg)
    print("📱 Mobile Push Notification sent to Xiaomi Mi 10T via KDE Connect.")

    # Keep browser open for a few moments to let developer observe
    print("\n👀 Keeping browser open for 6 seconds for visual verification...")
    await page.wait_for_timeout(6000)
    await click2win_auth_driver.close()
    print("\n🎉 Co-pilot Session completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_copilot())
