#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""READ-ONLY: map Streaming UI state + find native Change row-action selectors."""
import asyncio
import json
import sys

REPO = "/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab"
sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402


async def main():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "streaming", "kss")
    print("PAGE:", page.url)

    info = await page.evaluate("""() => {
        const body = document.body ? document.body.innerText : '';
        // current account (span showing 3024xxx)
        const acctMatch = body.match(/3024\\d{3}/);
        // any element whose class contains phnjeo
        const phn = [...document.querySelectorAll('[class*="phnjeo"]')].map(e => ({
            tag: e.tagName, cls: (e.className||'').toString().slice(0,120),
            text: (e.textContent||'').trim().slice(0,50),
            html: e.outerHTML.slice(0,500)
        }));
        // any element with Change/แก้ไข text
        const chg = [...document.querySelectorAll('li,span,a,button,div')].filter(e =>
            /^(change|แก้ไข)$/i.test((e.textContent||'').trim())
        ).map(e => ({
            tag: e.tagName, cls: (e.className||'').toString().slice(0,120),
            text: (e.textContent||'').trim().slice(0,50),
            html: e.outerHTML.slice(0,400)
        }));
        return {
            acct: acctMatch ? acctMatch[0] : null,
            bodyHead: body.slice(0, 1200),
            phnjeo: phn.slice(0, 20),
            changeEls: chg.slice(0, 20)
        };
    }""")
    print("ACCOUNT:", info.get("acct"))
    print("=== BODY HEAD ===")
    print(info.get("bodyHead"))
    print("=== phnjeo elements ===")
    print(json.dumps(info.get("phnjeo"), ensure_ascii=False, indent=2))
    print("=== Change/แก้ไข elements ===")
    print(json.dumps(info.get("changeEls"), ensure_ascii=False, indent=2))

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
