#!/usr/bin/env python3
"""
Diagnostic & Step-1 Account Switcher for Click2Win
Tests and validates switching to Derivatives (CW32_D_7338419) and dumps the exact DOM structure.
"""

import os
import sys
import asyncio
import logging

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.click2win_auth_driver import click2win_auth_driver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def main():
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.PLAYWRIGHT_HEADLESS = False
    print("🚀 Launching browser...")
    page = await click2win_auth_driver.launch_browser(resume_state=True)

    streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
    print(f"🌐 Navigating to {streaming_url}...")
    try:
        await page.goto(streaming_url, wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        print(f"Nav notice: {e}")
    await page.wait_for_timeout(3000)

    # 1. Dismiss any existing modal
    print("\n🔍 Step 1: Checking for modal dialogs...")
    modal = await page.query_selector(".ReactModalPortal, div[role='dialog'], .modal")
    if modal and await modal.is_visible():
        print("   Found open modal portal!")
        ok_btn = await page.query_selector("button:has-text('OK'), button:has-text('ตกลง')")
        if ok_btn:
            print("   Clicking OK button on modal...")
            await ok_btn.click()
            await page.wait_for_timeout(1000)

    # 2. Check current account
    acc_box = page.locator("div.bg-color-account-info-group")
    acc_text = await acc_box.inner_text()
    print(f"\n📊 Step 2: Current Account Box Text:\n{acc_text}")

    # 3. Click account dropdown
    print("\n👉 Step 3: Clicking account dropdown...")
    trigger = page.locator("div.bg-color-account-info-group div.cursor-pointer, div.bg-color-account-info-group").first
    await trigger.click()
    await page.wait_for_timeout(800)

    # 4. Find all options using get_by_text or specific locator
    print("   Searching for CW32_D_ option...")
    deriv_option = page.locator("text=CW32_D_").first
    if await deriv_option.is_visible():
        print(f"   🎯 Found CW32_D_ element! Text: [{await deriv_option.inner_text()}]")
        await deriv_option.click()
        print("   ✅ Clicked CW32_D_ option!")
        await page.wait_for_timeout(2000)
    else:
        print("   ❌ CW32_D_ option not visible!")

    # 5. Check updated account
    updated_acc_text = await acc_box.inner_text()
    print(f"\n📊 Step 4: Updated Account Box Text:\n{updated_acc_text}")

    # 6. Inspect Place Order row!
    print("\n🔬 Step 5: Inspecting Place Order row DOM...")
    place_order_bar = page.locator("div:has-text('Place Order')").last
    if await place_order_bar.is_visible():
        print(f"   Place Order Bar Text:\n{await place_order_bar.inner_text()}")

    # Dump all inputs and buttons in the bottom bar
    print("\n📋 Form Controls in Place Order area:")
    inputs = await page.query_selector_all("input, button, label, select")
    for el in inputs:
        try:
            if await el.is_visible():
                tag = await el.evaluate("e => e.tagName")
                txt = (await el.inner_text()).strip()
                val = await el.get_attribute("value") or ""
                ph = await el.get_attribute("placeholder") or ""
                el_id = await el.get_attribute("id") or ""
                el_type = await el.get_attribute("type") or ""
                if any(k in f"{txt} {val} {ph} {el_id}".lower() for k in ["buy", "sell", "long", "short", "symbol", "vol", "price", "auto", "open", "close"]):
                    print(f"   [{tag}] id='{el_id}' type='{el_type}' text='{txt}' val='{val}' placeholder='{ph}'")
        except Exception:
            pass

    # Capture snapshot screenshot
    os.makedirs("data/screenshots", exist_ok=True)
    ss_path = "data/screenshots/c2w_derivatives_form_inspected.png"
    await page.screenshot(path=ss_path)
    print(f"\n📸 Screenshot saved: {ss_path}")

    await page.wait_for_timeout(3000)
    await click2win_auth_driver.close()
    print("✅ Diagnostic complete.")


if __name__ == "__main__":
    asyncio.run(main())
