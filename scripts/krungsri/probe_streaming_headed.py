"""
Settrade Streaming Order Ledger & Native Change Probe
======================================================
1. Navigates to Streaming via Krungsri SSO
2. Switches account to 3024959 (Credit Balance)
3. Navigates to 'Order Status' / 'View Order'
4. Locates open order 11008198 (MTC)
5. Inspects Action buttons: Change / Cancel
6. If Change button is found, clicks it to reveal the edit modal and dumps editable fields
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


async def probe_streaming():
    print("🚀 Launching Headed Chrome for Streaming Probe...")
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
    probe = Probe("streaming")
    await context.route("**/*", probe.guard)
    
    page = await context.new_page()
    probe.attach(page)
    context.on("page", lambda p: (probe.attach(p), print(f"🪟 New popup/tab: {redact_url(p.url)}")))

    target_url = PRODUCT_START_URLS["streaming"]
    print(f"🌐 Navigating to {target_url} ...")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

    # Wait for StreamingPage.jsp
    active_page = page
    for sec in range(25):
        for p in context.pages:
            if "streaming" in p.url.lower() and "settrade" in p.url.lower() and "sso" not in p.url.lower() and "callback" not in p.url.lower():
                active_page = p
                break
        if "sso" not in active_page.url.lower() and "callback" not in active_page.url.lower():
            print(f"✅ Reached Streaming page after {sec}s!")
            break
        await asyncio.sleep(1)

    await active_page.wait_for_timeout(4000)
    print(f"📍 Active Streaming Page: {redact_url(active_page.url)}")
    print(f"📑 Page Title: {await active_page.title()}")

    # Inspect account selector in Streaming
    acc_info = await active_page.evaluate('''() => {
        const allDocs = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => {
            try { return f.contentDocument; } catch(e) { return null; }
        }).filter(Boolean)];
        for (const doc of allDocs) {
            const selects = Array.from(doc.querySelectorAll('select'));
            const acc = selects.find(s => s.id?.includes('Account') || s.name?.includes('Account') || s.className?.includes('account'));
            if (acc) {
                return {
                    id: acc.id,
                    name: acc.name,
                    val: acc.value,
                    options: Array.from(acc.options).map(o => ({ value: o.value, text: o.text.trim() }))
                };
            }
        }
        return null;
    }''')
    print("\n🏦 Streaming Account Selector:", json.dumps(acc_info, ensure_ascii=False, indent=2))

    # Switch to 3024959 if needed
    if acc_info:
        for opt in acc_info.get("options", []):
            if "3024959" in opt["value"] or "3024959" in opt["text"]:
                print(f"🔄 Switching Streaming account to {opt['value']}...")
                await active_page.evaluate(f'''(val) => {{
                    const el = document.getElementById("{acc_info['id']}") || document.querySelector("select[name='{acc_info['name']}']");
                    if (el) {{
                        el.value = val;
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}''', opt["value"])
                await active_page.wait_for_timeout(3000)
                break

    # Look for Order Status tab in Streaming
    print("\n🔍 Locating 'Order' / 'View Order' / 'Order Status' tab...")
    tab_clicked = await active_page.evaluate('''() => {
        const els = Array.from(document.querySelectorAll('a, button, div, span, li'));
        const orderTab = els.find(e => {
            const t = (e.innerText || '').trim();
            return t === 'Order Status' || t === 'View Order' || t === 'Orders' || t === 'Order';
        });
        if (orderTab) {
            orderTab.click();
            return (orderTab.innerText || '').trim();
        }
        return null;
    }''')
    print(f"👉 Tab click result: {tab_clicked}")
    await active_page.wait_for_timeout(3000)

    # Search for Order 11008198 or MTC in order rows
    order_scan = await active_page.evaluate('''() => {
        const rows = Array.from(document.querySelectorAll('tr, div.slick-row, div.grid-canvas div, div[role=row]'));
        const matchedRows = [];
        for (const r of rows) {
            const txt = r.innerText || '';
            if (txt.includes('MTC') || txt.includes('11008198')) {
                // Find all clickable controls inside this row
                const ctrls = Array.from(r.querySelectorAll('button, a, input, span[onclick], i, svg, [role=button]')).map(c => ({
                    tag: c.tagName,
                    text: (c.innerText || c.title || c.className || '').trim(),
                    title: c.title,
                    class: c.className,
                    onclick: c.getAttribute('onclick')
                }));
                matchedRows.push({
                    text: txt.replace(/\\s+/g, ' ').slice(0, 150),
                    controls: ctrls
                });
            }
        }
        return matchedRows;
    }''')
    print(f"\n📋 Order Match for MTC / 11008198 ({len(order_scan)} row(s) found):")
    for r in order_scan:
        print(f"   • Text: {r['text']}")
        print(f"     Controls: {r['controls']}")

    # Search for ANY 'Change' button or 'Cancel' button on the entire Streaming screen
    streaming_actions = await active_page.evaluate('''() => {
        const els = Array.from(document.querySelectorAll('button, a, input[type=button], span, div[role=button]'));
        return els.filter(e => {
            const t = (e.innerText || e.title || e.getAttribute('aria-label') || '').toLowerCase();
            return t === 'change' || t === 'cancel' || t.includes('change order') || t.includes('cancel order') || t === 'แก้ไข' || t === 'ยกเลิก';
        }).map(e => ({
            tag: e.tagName,
            text: (e.innerText || e.title || e.getAttribute('aria-label') || '').trim(),
            id: e.id,
            class: e.className
        }));
    }''')
    print(f"\n🔘 Streaming Action Buttons ({len(streaming_actions)}):")
    for b in streaming_actions:
        print(f"   • [{b['tag']}] '{b['text']}' id={b['id']} class={b['class']}")

    # If a Change control is visible, click it to see the modal
    change_btn = await active_page.query_selector("button:has-text('Change'), a:has-text('Change'), [title='Change'], [title='Change Order']")
    if change_btn and await change_btn.is_visible():
        print("\n👉 Found Change button! Clicking to inspect modal...")
        await change_btn.click()
        await active_page.wait_for_timeout(2000)
        
        # Dump modal inputs
        modal_inputs = await active_page.evaluate('''() => {
            const modals = Array.from(document.querySelectorAll('.modal, .dialog, .popup, [role=dialog], div[id*=\"dialog\"], div[id*=\"modal\"]'));
            const activeModal = modals.find(m => m.offsetWidth > 0 && m.offsetHeight > 0) || document.body;
            return {
                title: activeModal.querySelector('.modal-title, .dialog-title, h3, h4')?.innerText,
                inputs: Array.from(activeModal.querySelectorAll('input, select')).map(i => ({
                    id: i.id,
                    name: i.name,
                    type: i.type,
                    value: i.value,
                    disabled: i.disabled
                })),
                buttons: Array.from(activeModal.querySelectorAll('button, input[type=button]')).map(b => (b.innerText || b.value || '').trim())
            };
        }''')
        print("📝 Change Modal Details:", json.dumps(modal_inputs, ensure_ascii=False, indent=2))
        
        # Close modal safely (never submit!)
        close_btn = await active_page.query_selector("button:has-text('Cancel'), button:has-text('Close'), .close, [aria-label='Close']")
        if close_btn:
            await close_btn.click()

    print("\n" + "="*80)
    print("👀 Streaming is open headed for 20 seconds on DISPLAY=:0...")
    print("="*80)
    await active_page.wait_for_timeout(20000)

    await browser.close()
    await pw.stop()

if __name__ == "__main__":
    asyncio.run(probe_streaming())
