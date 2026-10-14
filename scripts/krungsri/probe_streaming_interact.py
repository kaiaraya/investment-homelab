"""
Streaming Headed Interactive Probe for Credit Balance
======================================================
1. Clicks account switch to 3024959 (Equity) via JS click or selector
2. Inspects Order Status / Portfolio in Streaming
3. Locates MTC order 11008198
4. Checks for Change / Cancel buttons
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

async def probe_streaming_live():
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
    probe = Probe("streaming_live")
    await context.route("**/*", probe.guard)
    
    page = await context.new_page()
    probe.attach(page)

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
            break
        await asyncio.sleep(1)

    await active_page.wait_for_timeout(4000)
    print(f"📍 Active Page: {redact_url(active_page.url)}")

    # 1. Switch account to 3024959 (Equity) via direct DOM event
    print("🔄 Switching Streaming account to 3024959 (Equity)...")
    switch_res = await active_page.evaluate('''() => {
        const lis = Array.from(document.querySelectorAll('li'));
        const target = lis.find(l => (l.innerText || '').includes('3024959 (Equity)'));
        if (target) {
            // Trigger mousedown, mouseup, click
            target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
            target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
            target.click();
            return { success: true, text: target.innerText };
        }
        // Try clicking dropdown trigger first
        const trigger = document.querySelector('div:has(> svg)');
        if (trigger) trigger.click();
        return { success: false, lis_count: lis.length };
    }''')
    print("Switch attempt 1:", switch_res)
    await active_page.wait_for_timeout(2000)

    # If not switched, try clicking the dropdown container first
    curr_acc = await active_page.evaluate('''() => {
        const el = Array.from(document.querySelectorAll('*')).find(e => (e.innerText || '').includes('3024959 (Equity)') && e.innerText.length < 50);
        return el ? el.innerText : null;
    }''')
    if not curr_acc:
        print("Clicking dropdown arrow...")
        arrow = await active_page.query_selector("div:has-text('3024952') svg, span:has-text('3024952')")
        if arrow:
            await arrow.click()
            await active_page.wait_for_timeout(1000)
            await active_page.click("li:has-text('3024959')")
            await active_page.wait_for_timeout(2000)

    # Check body text now
    body_text = await active_page.inner_text("body")
    print(f"Current Account in View: {'3024959' if '3024959' in body_text else '3024952'}")

    # 2. In Settrade Streaming, let's navigate to "Portfolio" or look for bottom bar
    print("\n👉 Clicking 'Portfolio' tab in Streaming...")
    port_tab = await active_page.query_selector("div:has-text('Portfolio'), button:has-text('Portfolio'), a:has-text('Portfolio')")
    if port_tab and await port_tab.is_visible():
        await port_tab.click()
        await active_page.wait_for_timeout(3000)

    # Check for order 11008198 or MTC
    body_text_port = await active_page.inner_text("body")
    print("MTC in Portfolio/Order:", "MTC" in body_text_port)
    print("11008198 in Portfolio/Order:", "11008198" in body_text_port)

    # 3. Search for Change or Cancel buttons in Streaming DOM
    buttons_list = await active_page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type=button], [role=button]'));
        return btns.map(b => ({
            tag: b.tagName,
            text: (b.innerText || b.value || b.title || '').trim(),
            id: b.id,
            cls: b.className
        })).filter(b => {
            const t = b.text.toLowerCase();
            return t.includes('change') || t.includes('cancel') || t.includes('buy') || t.includes('sell') || t.includes('order');
        });
    }''')
    print(f"\n🔘 Relevant Action Buttons found ({len(buttons_list)}):")
    for b in buttons_list[:25]:
        print(f"   • [{b['tag']}] '{b['text']}' cls={b['cls']}")

    print("\n" + "="*80)
    print("👀 Streaming is open headed for 20 seconds on DISPLAY=:0...")
    print("="*80)
    await active_page.wait_for_timeout(20000)

    await browser.close()
    await pw.stop()

if __name__ == "__main__":
    asyncio.run(probe_streaming_live())
