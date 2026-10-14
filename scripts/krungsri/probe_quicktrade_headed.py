"""
Quick Trade Live Headed Probe (Read-only, Submit Guarded)
==========================================================
Launches Chrome headed on DISPLAY=:0 with saved session.
Inspects:
1. Account selector (Credit Balance / Cash Balance)
2. Order input form schema
3. Order Status / View Order list (find open orders)
4. Native Change Order button / modal inspection
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DISPLAY", ":0")

from scripts.krungsri.probe_krungsri_products import (
    Probe,
    PRODUCT_START_URLS,
    SESSION_FILE,
    redact_url,
    LANDMARKS_JS,
)

OUT_DIR = os.path.join(PROJECT_ROOT, "data", "probes", "krungsri")


async def probe_quicktrade():
    print("🚀 Launching Headed Chrome for Quick Trade Probe...")
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
    
    probe = Probe("quicktrade")
    await context.route("**/*", probe.guard)
    
    page = await context.new_page()
    probe.attach(page)
    context.on("page", lambda p: (probe.attach(p), print(f"🪟 New popup/tab: {redact_url(p.url)}")))

    target_url = PRODUCT_START_URLS["quicktrade"]
    print(f"🌐 Navigating to {target_url} ...")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
    
    active_page = page
    for sec in range(20):
        for p in context.pages:
            if "fastorder" in p.url or ("settrade" in p.url and "sso" not in p.url and "oauth" not in p.url and "callback" not in p.url):
                active_page = p
                break
        if "sso" not in active_page.url and "oauth" not in active_page.url and "callback" not in active_page.url:
            print(f"✅ Reached destination page after {sec}s!")
            break
        await asyncio.sleep(1)
        
    await active_page.wait_for_timeout(3000)

    print(f"📍 Active Page URL: {redact_url(active_page.url)}")
    print(f"📑 Page Title: {await active_page.title()}")
    
    print(f"🖼️ Total frames on active page: {len(active_page.frames)}")
    for f_idx, fr in enumerate(active_page.frames):
        print(f"   Frame #{f_idx}: {redact_url(fr.url)}")

    # 1. Inspect Account Selector
    accounts_info = await active_page.evaluate('''() => {
        const allFrames = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => {
            try { return f.contentDocument; } catch(e) { return null; }
        }).filter(Boolean)];
        for (const doc of allFrames) {
            const selects = Array.from(doc.querySelectorAll('select'));
            const accSelect = selects.find(s => s.name?.toLowerCase().includes('acc') || s.id?.toLowerCase().includes('acc')) || selects[0];
            if (accSelect) {
                return {
                    found: true,
                    id: accSelect.id,
                    name: accSelect.name,
                    current_value: accSelect.value,
                    options: Array.from(accSelect.options).map(o => ({ value: o.value, text: o.text.trim() }))
                };
            }
        }
        return { found: false };
    }''')
    print("\n🏦 [Account Selector Info]:", json.dumps(accounts_info, ensure_ascii=False, indent=2))

    # 2. Inspect Navigation / Tabs (Order, View Order, Portfolio, etc.)
    tabs_info = await active_page.evaluate('''() => {
        const allDocs = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => {
            try { return f.contentDocument; } catch(e) { return null; }
        }).filter(Boolean)];
        const links = [];
        for (const doc of allDocs) {
            links.push(...Array.from(doc.querySelectorAll('a, button, li, [role=tab], input[type=button]')));
        }
        return links.map(el => ({
            tag: el.tagName,
            text: (el.innerText || el.value || '').trim(),
            id: el.id,
            href: el.getAttribute('href'),
            onclick: el.getAttribute('onclick')
        })).filter(x => x.text && x.text.length < 30);
    }''')
    print(f"\n📑 Found {len(tabs_info)} clickable elements/tabs. Relevant tabs:")
    for t in tabs_info:
        if any(k in t['text'].lower() for k in ['order', 'view', 'status', 'port', 'change', 'cancel', 'deal', 'คำสั่ง']):
            print(f"   • [{t['tag']}] '{t['text']}' (id={t['id']} href={t['href']} onclick={t['onclick']})")

    # 3. Inspect Order Form Inputs
    inputs_info = await active_page.evaluate('''() => {
        const allDocs = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => {
            try { return f.contentDocument; } catch(e) { return null; }
        }).filter(Boolean)];
        const inps = [];
        for (const doc of allDocs) {
            inps.push(...Array.from(doc.querySelectorAll('input, select, textarea')));
        }
        return inps.filter(e => e.type !== 'hidden').map(e => ({
            id: e.id,
            name: e.name,
            type: e.type,
            placeholder: e.placeholder,
            value: e.value,
            disabled: e.disabled
        }));
    }''')
    print(f"\n📝 Form Inputs ({len(inputs_info)} visible inputs):")
    for inp in inputs_info:
        print(f"   • [{inp['type']}] name={inp['name']} id={inp['id']} val='{inp['value']}' placeholder='{inp['placeholder']}'")

    # 4. Check Order List / Status Table
    order_tables = await active_page.evaluate('''() => {
        const allDocs = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => {
            try { return f.contentDocument; } catch(e) { return null; }
        }).filter(Boolean)];
        const tables = [];
        for (const doc of allDocs) {
            tables.push(...Array.from(doc.querySelectorAll('table')));
        }
        return tables.map((t, idx) => {
            const rows = Array.from(t.querySelectorAll('tr'));
            const headerRow = rows[0];
            const headers = headerRow ? Array.from(headerRow.querySelectorAll('th, td')).map(c => c.innerText.trim().replace(/\\s+/g, ' ')) : [];
            const dataRows = rows.slice(1, 10).map(r => Array.from(r.querySelectorAll('td')).map(c => ({
                text: c.innerText.trim().replace(/\\s+/g, ' '),
                html: c.innerHTML.slice(0, 150)
            })));
            return {
                table_idx: idx,
                id: t.id,
                class: t.className,
                row_count: rows.length,
                headers: headers,
                sample_rows: dataRows
            };
        }).filter(t => t.headers.length > 3 || t.row_count > 1);
    }''')
    print(f"\n📊 Tables detected ({len(order_tables)} table(s)):")
    for ot in order_tables:
        print(f"   Table #{ot['table_idx']} id={ot['id']} rows={ot['row_count']}")
        print(f"   Headers: {ot['headers']}")
        if ot['sample_rows']:
            print(f"   First row cells: {[c['text'] for c in ot['sample_rows'][0]]}")

    # 5. Search specifically for "Change" or "Cancel" buttons or links in the page
    change_cancel_controls = await active_page.evaluate('''() => {
        const allDocs = [document, ...Array.from(document.querySelectorAll('iframe')).map(f => {
            try { return f.contentDocument; } catch(e) { return null; }
        }).filter(Boolean)];
        const els = [];
        for (const doc of allDocs) {
            els.push(...Array.from(doc.querySelectorAll('a, button, input[type=button], input[type=submit], img, span')));
        }
        return els.filter(e => {
            const txt = (e.innerText || e.value || e.title || e.alt || '').toLowerCase();
            return txt.includes('change') || txt.includes('cancel') || txt.includes('edit') || txt.includes('แก้ไข') || txt.includes('ยกเลิก');
        }).map(e => ({
            tag: e.tagName,
            text: (e.innerText || e.value || e.title || e.alt || '').trim(),
            id: e.id,
            class: e.className,
            onclick: e.getAttribute('onclick'),
            href: e.getAttribute('href')
        }));
    }''')
    print(f"\n🔍 [Change/Cancel Controls Found] ({len(change_cancel_controls)}):")
    for ctrl in change_cancel_controls:
        print(f"   • [{ctrl['tag']}] '{ctrl['text']}' id={ctrl['id']} onclick={ctrl['onclick']} href={ctrl['href']}")

    # Snapshot initial
    await probe.snapshot("quicktrade_initial_state")

    # If there is a tab called "View Order" or "Order Status", let's see if we should click it
    view_order_tab = await active_page.query_selector("text='View Order', text='Order Status', text='Status', a:has-text('View Order'), a:has-text('Status')")
    if view_order_tab and await view_order_tab.is_visible():
        print(f"\n👉 Clicking View Order / Status tab...")
        await view_order_tab.click()
        await active_page.wait_for_timeout(3000)
        await probe.snapshot("quicktrade_after_click_view_order")

    print("\n" + "="*80)
    print("👀 BROWSER IS OPEN HEADED ON DISPLAY=:0.")
    print("   Take a look at the window on your screen!")
    print("   Waiting 20 seconds for inspection...")
    print("="*80)
    await active_page.wait_for_timeout(20000)

    # Dump probe summary
    probe_path = probe.dump({
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "account_info": accounts_info,
        "change_cancel_controls": change_cancel_controls
    })
    print(f"\n✅ Probe summary saved to: {probe_path}")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(probe_quicktrade())
