#!/usr/bin/env python3
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab

async def probe():
    pw, browser, ctx = await connect_cdp(cdp_url_for('kss'), 'kss')
    page = await resolve_target_tab(ctx, 'streaming', 'kss')
    
    # 1. API check: open orders
    orders_api = await page.evaluate('''async () => {
        const r = await fetch('https://apigw.settrade.com/api/dgw/v3/029/accounts/3024959/orders', {credentials:'include'});
        return {status: r.status, body: await r.text()};
    }''')
    print('=== API Orders ===')
    print(orders_api)

    # 2. Check all elements matching order number 11007722
    elements = await page.evaluate('''() => {
        const els = [...document.querySelectorAll('*')].filter(e => {
            return e.children.length === 0 && e.textContent.includes('11007722');
        });
        return els.map(e => ({
            tag: e.tagName,
            className: e.className,
            text: e.textContent,
            parent_tag: e.parentElement ? e.parentElement.tagName : '',
            parent_class: e.parentElement ? e.parentElement.className : '',
            parent_html: e.parentElement ? e.parentElement.outerHTML.slice(0, 500) : ''
        }));
    }''')
    print('=== Elements matching 11007722 ===')
    print(json.dumps(elements, indent=2))

    await browser.close()
    await pw.stop()

if __name__ == '__main__':
    asyncio.run(probe())
