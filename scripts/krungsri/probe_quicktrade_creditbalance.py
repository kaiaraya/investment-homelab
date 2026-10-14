"""
Quick Trade Order Ledger & Action Probe for Credit Balance (3024959)
===================================================================
1. Selects account 3024959 (Equity)
2. Reads the live open order table
3. Checks if selecting the order row reveals any 'Change' / 'Edit' capability
"""

import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DISPLAY", ":0")

from scripts.krungsri.probe_krungsri_products import (
    Probe,
    PRODUCT_START_URLS,
    SESSION_FILE,
    redact_url,
)


async def check_order_actions():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        executable_path="/usr/bin/google-chrome",
        args=["--no-sandbox", "--disable-popup-blocking", "--window-size=1400,950"]
    )
    context = await browser.new_context(
        storage_state=SESSION_FILE,
        viewport={"width": 1380, "height": 900}
    )
    probe = Probe("quicktrade_creditbalance")
    await context.route("**/*", probe.guard)
    
    page = await context.new_page()
    probe.attach(page)

    target_url = PRODUCT_START_URLS["quicktrade"]
    print(f"🌐 Navigating to {target_url} ...")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

    # Wait for fastorder page
    active_page = page
    for sec in range(20):
        for p in context.pages:
            if "fastorder" in p.url or ("settrade" in p.url and "sso" not in p.url and "oauth" not in p.url and "callback" not in p.url):
                active_page = p
                break
        if "sso" not in active_page.url and "oauth" not in active_page.url and "callback" not in active_page.url:
            break
        await asyncio.sleep(1)

    await active_page.wait_for_timeout(3000)
    print(f"📍 Active Page: {redact_url(active_page.url)}")

    # 1. Switch to 3024959 (Equity)
    print("🔄 Switching account to '3024959 (Equity)'...")
    await active_page.select_option("#accInv", "3024959 (Equity)")
    await active_page.wait_for_timeout(3000)

    # 2. Inspect the Equity Order Table
    order_data = await active_page.evaluate('''() => {
        // Look for order table body
        const bodies = Array.from(document.querySelectorAll('#orderBodyEq, [id*=\"orderBody\"], [id*=\"orderTable\"], table'));
        const targetBody = document.querySelector('#orderBodyEq') || bodies.find(b => b.rows && b.rows.length > 0 && b.innerText.includes('3024959'));
        
        const allTables = Array.from(document.querySelectorAll('table')).map(t => ({
            id: t.id,
            rows: Array.from(t.querySelectorAll('tr')).map(r => ({
                cells: Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim().replace(/\\s+/g, ' ')),
                checkboxes: Array.from(r.querySelectorAll('input[type=checkbox]')).map(cb => ({ id: cb.id, name: cb.name, value: cb.value })),
                buttons: Array.from(r.querySelectorAll('button, input[type=button], a')).map(b => b.innerText || b.value || b.title)
            }))
        })).filter(t => t.rows.length > 0 && t.rows.some(r => r.cells.length > 5));

        return {
            selected_acc: document.querySelector('#accInv')?.value,
            tables: allTables
        };
    }''')
    print("\n📊 Order Ledger Data for 3024959:")
    for t in order_data["tables"]:
        print(f"Table id={t['id']} (rows={len(t['rows'])}):")
        for r_idx, r in enumerate(t['rows']):
            print(f"   Row {r_idx}: {r['cells']} | Checkboxes: {r['checkboxes']} | Buttons: {r['buttons']}")

    # 3. Check what buttons are associated with the order list
    action_btns = await active_page.evaluate('''() => {
        const orderSection = document.querySelector('#orderHeadEq')?.closest('div, td, table')?.parentElement || document.body;
        const btns = Array.from(orderSection.querySelectorAll('input[type=button], button, a.btn, a[role=button]'));
        return btns.map(b => ({
            tag: b.tagName,
            text: (b.value || b.innerText || b.title || '').trim(),
            id: b.id,
            disabled: b.disabled,
            onclick: b.getAttribute('onclick')
        })).filter(x => x.text);
    }''')
    print(f"\n🔘 Order Action Buttons around table:")
    for b in action_btns:
        print(f"   • [{b['tag']}] '{b['text']}' (id={b['id']} disabled={b['disabled']} onclick={b['onclick']})")

    # 4. Check if clicking on the first order checkbox or row enables anything
    checkbox = await active_page.query_selector("#orderBodyEq input[type=checkbox], table input[type=checkbox]")
    if checkbox:
        print(f"\n👉 Checking order row checkbox...")
        await checkbox.check()
        await active_page.wait_for_timeout(1000)
        
        # Re-check action buttons state
        btns_after_check = await active_page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('input[type=button], button'));
            return btns.map(b => ({
                text: (b.value || b.innerText || '').trim(),
                id: b.id,
                disabled: b.disabled
            })).filter(x => ['cancel', 'change', 'detail', 'edit', 'ยกเลิก', 'แก้ไข'].some(k => x.text.toLowerCase().includes(k)));
        }''')
        print("🔘 Buttons state after checkbox selected:", btns_after_check)

    print("\n" + "="*80)
    print("👀 Browser is open headed for 15 seconds so you can see Quick Trade on screen...")
    print("="*80)
    await active_page.wait_for_timeout(15000)

    await browser.close()
    await pw.stop()

if __name__ == "__main__":
    asyncio.run(check_order_actions())
