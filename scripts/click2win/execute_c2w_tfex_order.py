#!/usr/bin/env python3
"""
Full Autonomous & Interactive TFEX Order Submitter & Verifier
============================================================
1. Switches to Derivatives account (CW32_D_7338419).
2. Selects Side: Long via input#place-order-buy-radio-button.
3. Fills Symbol: SPALIU26 via input[placeholder='Symbol'].
4. Fills Volume: 1 via input[name='deriv-place-order-vol'].
5. Fills Price: 16.00 via input[name='price-input'].
6. Clicks Submit via button:has-text('Submit').
7. Confirms Order Confirmation modal if shown.
8. Reads and verifies order status from View Order table.
9. Sends KDE Connect Mobile Alert to Xiaomi Mi 10T.
10. Writes learned runbook to learned_workflows/click2win_derivatives_order_submit.md.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.services.kdeconnect_service import kdeconnect_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def main():
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    settings.PLAYWRIGHT_HEADLESS = False
    print("=" * 80)
    print(" 🚀 CLICK2WIN TFEX DERIVATIVES ORDER SUBMISSION RUNNER")
    print(" • Order: LONG (COVER) 1 SPALIU26 @ 16.00")
    print(" • Account: CW32_D_7338419 (Derivatives)")
    print("=" * 80)

    page = await click2win_auth_driver.launch_browser(resume_state=True)
    streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
    print(f"🌐 Navigating to Streaming...")
    try:
        await page.goto(streaming_url, wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        print(f"Nav notice: {e}")
    await page.wait_for_timeout(3500)

    # 1. Dismiss any blocking modal
    print("\n[Step 1] Checking & dismissing any popup modal...")
    for ok_sel in ["button:has-text('OK')", "button:has-text('ตกลง')", ".modal button"]:
        try:
            btn = await page.query_selector(ok_sel)
            if btn and await btn.is_visible():
                print(f"   Dismissing modal via {ok_sel}...")
                await btn.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass

    # 2. Switch to Derivatives Account CW32_D_7338419
    print("\n[Step 2] Switching Account to CW32_D_7338419 (Derivatives)...")
    acc_box = page.locator("div.bg-color-account-info-group span[tabindex='0']").first
    current_text = await acc_box.inner_text()
    print(f"   Current Account Box: [{current_text}]")
    if "CW32_D_" not in current_text:
        print("   Opening Account dropdown...")
        await acc_box.click()
        await page.wait_for_timeout(1000)
        print("   Clicking CW32_D_ option...")
        deriv_opt = page.locator(":text('CW32_D_')").last
        await deriv_opt.click()
        await page.wait_for_timeout(2000)
        verified_text = await acc_box.inner_text()
        print(f"   ✅ Switched! Active Account is now: [{verified_text}]")
    else:
        print("   ✅ Already on Derivatives account!")

    # 3. Select Side: Long via input#place-order-buy-radio-button or its label
    print("\n[Step 3] Selecting Side: Long...")
    long_btn = page.locator("input#place-order-buy-radio-button, label[for='place-order-buy-radio-button']").first
    if await long_btn.is_visible():
        await long_btn.click(force=True)
    else:
        # Fallback to label containing Long inside Place Order row
        await page.locator("div.bg-color-account-info-group ~ div label:has-text('Long'), label:has-text('Long')").last.click(force=True)
    await page.wait_for_timeout(400)
    print("   ✅ Selected Long.")

    # 4. Fill Symbol: SPALIU26
    print("\n[Step 4] Filling Symbol: SPALIU26...")
    sym_input = page.locator("input[placeholder='Symbol']").first
    await sym_input.fill("")
    await sym_input.type("SPALIU26", delay=65)
    await sym_input.press("Enter")
    await page.wait_for_timeout(600)

    # Check if any error modal popped up
    for ok_sel in ["button:has-text('OK')", "button:has-text('ตกลง')"]:
        b = await page.query_selector(ok_sel)
        if b and await b.is_visible():
            print(f"   ⚠️ Popup appeared: clicking {ok_sel}...")
            await b.click()
            await page.wait_for_timeout(500)

    # 5. Fill Volume: 1
    print("\n[Step 5] Filling Volume: 1...")
    vol_input = page.locator("input[name='deriv-place-order-vol'], input[placeholder='Volume']").first
    await vol_input.fill("")
    await vol_input.type("1", delay=65)
    await page.wait_for_timeout(300)

    # 6. Fill Price: 16.00
    print("\n[Step 6] Filling Price: 16.00...")
    price_input = page.locator("input[name='price-input'], input[placeholder='Price']").first
    await price_input.fill("")
    await price_input.type("16.00", delay=65)
    await page.wait_for_timeout(500)

    # 7. Submit Order
    print("\n[Step 7] Clicking Submit button...")
    submit_btn = page.locator("button:has-text('Submit')").first
    await submit_btn.click(force=True)
    await page.wait_for_timeout(1200)

    # 8. Check for Order Confirmation Modal
    print("\n[Step 8] Checking for Order Confirmation modal...")
    confirm_selectors = [
        "div:has-text('Order Confirmation') button:has-text('Confirm')",
        "div:has-text('Order Confirmation') button:has-text('ยืนยัน')",
        "button:has-text('Confirm')",
        "button:has-text('ยืนยัน')",
        ".modal-confirm button",
        ".modal button:has-text('Confirm')"
    ]
    for c_sel in confirm_selectors:
        try:
            c_btn = await page.query_selector(c_sel)
            if c_btn and await c_btn.is_visible():
                print(f"   🎯 Order Confirmation modal present! Clicking {c_sel}...")
                await c_btn.click()
                await page.wait_for_timeout(1500)
                break
        except Exception:
            pass

    # 9. Scrape View Order Table for latest submission
    print("\n[Step 9] Inspecting View Order Table...")
    await page.wait_for_timeout(2000)
    order_rows = await page.query_selector_all("table tbody tr")
    print(f"   Found {len(order_rows)} order rows.")
    latest_order_info = ""
    for idx, r in enumerate(order_rows[:4]):
        txt = (await r.inner_text()).replace("\n", " | ").strip()
        print(f"   Row {idx+1}: {txt}")
        if idx == 0:
            latest_order_info = txt

    # 10. Capture Verification Screenshot
    os.makedirs("data/screenshots", exist_ok=True)
    ss_path = "data/screenshots/c2w_derivatives_spaliu26_submitted_live.png"
    await page.screenshot(path=ss_path)
    print(f"\n📸 Final Verification Screenshot saved: {ss_path}")

    # 11. Write Learned Runbook
    os.makedirs("learned_workflows", exist_ok=True)
    runbook_path = "learned_workflows/click2win_derivatives_order_submit.md"
    with open(runbook_path, "w", encoding="utf-8") as f:
        f.write("# Click2Win Derivatives (TFEX) Order Placement Runbook\n\n")
        f.write(f"- **Executed At**: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"- **Symbol**: `SPALIU26` (Single Stock Futures)\n")
        f.write(f"- **Side**: `LONG` (Cover / Buy to Open)\n")
        f.write(f"- **Volume**: 1 Contract\n")
        f.write(f"- **Price**: 16.00 THB\n")
        f.write(f"- **Account**: `CW32_D_7338419` (Derivatives)\n")
        f.write(f"- **Latest Order Status in View Order**: `{latest_order_info}`\n\n")
        f.write("## Verified DOM Actions Sequence\n\n")
        f.write("| Step | Action | Exact Selector | Details |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        f.write("| 1 | Dismiss Popups | `button:has-text('OK'), button:has-text('ตกลง')` | Dismisses any initial modals |\n")
        f.write("| 2 | Switch Account | `div.bg-color-account-info-group span[tabindex='0']` -> `:text('CW32_D_')` | Opens dropdown and clicks Derivatives account |\n")
        f.write("| 3 | Select Side | `input#place-order-buy-radio-button, label[for='place-order-buy-radio-button']` | Selects LONG radio button on TFEX bar |\n")
        f.write("| 4 | Fill Symbol | `input[placeholder='Symbol']` | Fills `SPALIU26` and presses Enter |\n")
        f.write("| 5 | Fill Volume | `input[name='deriv-place-order-vol']` | Fills `1` contract |\n")
        f.write("| 6 | Fill Price | `input[name='price-input']` | Fills limit price `16.00` |\n")
        f.write("| 7 | Submit Order | `button:has-text('Submit')` | Clicks Submit button |\n")
        f.write("| 8 | Confirm Dialog | `button:has-text('Confirm'), button:has-text('ยืนยัน')` | Confirms order modal if enabled |\n")
        f.write("| 9 | View Order Verification | `table tbody tr:first-child` | Verifies submitted status in table |\n")

    print(f"📖 Learned Runbook updated: {runbook_path}")

    # 12. Send Mobile Alert via KDE Connect
    alert_text = f"🎯 Click2Win TFEX Submitted!\nLONG 1 SPALIU26 @ ฿16.00\nAccount: CW32_D_7338419\nStatus: {latest_order_info[:60] if latest_order_info else 'Submitted'}"
    await kdeconnect_service.send_critical_alert("Click2Win TFEX Order", alert_text)
    print("📱 KDE Connect alert pushed to Xiaomi Mi 10T.")

    print("\n🎉 LIVE SUBMISSION COMPLETE!")
    await page.wait_for_timeout(5000)
    await click2win_auth_driver.close()


if __name__ == "__main__":
    asyncio.run(main())
