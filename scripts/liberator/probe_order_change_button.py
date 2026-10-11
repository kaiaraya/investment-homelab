"""
Probe the LIVE Liberator order table to locate the per-row "Change" (amend) control.
====================================================================================
READ-ONLY diagnostic: loads the saved session cookies, navigates to /Portfolio and
DUMPS DOM ONLY. It NEVER clicks Buy / Sell / Change / Cancel and never submits an order.

Goal (TASK 2026-10-09): find the selector of the native "Change" (แก้ไข) button that
amends a resting order IN-PLACE (same order number), so ``negotiate_price`` can stop
doing cancel + replace.

Usage:
    .venv/bin/python scripts/liberator/probe_order_change_button.py
"""

import asyncio
import json
import os

from playwright.async_api import async_playwright

STATE_FILE = "data/liberator_session.json"
PORTFOLIO_URL = "https://webtrade.liberator.co.th/Portfolio"
SHOT = "data/screenshots/liberator_order_table_probe.png"


async def main():
    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"],
        )
        context = await browser.new_context(
            no_viewport=True,
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        await context.add_cookies(state.get("cookies", []))
        page = await context.new_page()

        print(f"Navigating to {PORTFOLIO_URL} ...")
        await page.goto(PORTFOLIO_URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3500)
        print(f"   URL   : {page.url}")
        print(f"   Title : {await page.title()}")

        if "login" in page.url.lower():
            print("SESSION NOT AUTHENTICATED (redirected to /login). Aborting.")
            await browser.close()
            return

        # 1. Enumerate every table on the page (id / class / header / row count)
        tables = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('table').forEach((t, i) => {
                const head = t.querySelector('thead');
                out.push({
                    index: i,
                    id: t.id || null,
                    className: (typeof t.className === 'string' ? t.className : null),
                    header: head ? head.innerText.replace(/\\s+/g, ' ').trim() : null,
                    rowCount: t.querySelectorAll('tbody tr').length,
                });
            });
            return out;
        }""")
        print("\n--- TABLES ON /Portfolio ---")
        for t in tables:
            print(f"  [{t['index']}] id={t['id']!r} rows={t['rowCount']} hdr={t['header']!r}")

        # 2. Locate the orders table and dump every control inside each row
        order_info = await page.evaluate("""() => {
            let table = document.querySelector('#OrderTableList');
            let source = 'id';
            if (!table) {
                source = 'header-match';
                for (const t of document.querySelectorAll('table')) {
                    const h = t.querySelector('thead');
                    const txt = h ? h.innerText.toLowerCase() : '';
                    if (txt.includes('order #') && txt.includes('side')) { table = t; break; }
                }
            }
            if (!table) return { found: false };

            const headers = Array.from(table.querySelectorAll('thead th'))
                .map(th => th.innerText.replace(/\\s+/g, ' ').trim());
            const rows = [];
            table.querySelectorAll('tbody tr').forEach((tr, ri) => {
                const controls = [];
                const selectors = 'button, a, [role="button"], svg, i, img, input, ' +
                                  'span[class*="icon"], span[class*="btn"], div[role="button"]';
                tr.querySelectorAll(selectors).forEach(c => {
                    const cls = (typeof c.className === 'string')
                        ? c.className : (c.getAttribute('class') || '');
                    controls.push({
                        tag: c.tagName.toLowerCase(),
                        id: c.id || null,
                        className: cls || null,
                        text: (c.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40),
                        title: c.getAttribute('title'),
                        aria: c.getAttribute('aria-label'),
                        href: c.getAttribute('href'),
                        onclick: c.getAttribute('onclick'),
                    });
                });
                rows.push({
                    rowIndex: ri,
                    id: tr.id || null,
                    className: (typeof tr.className === 'string' ? tr.className : null),
                    text: tr.innerText.replace(/\\s+/g, ' ').trim().slice(0, 200),
                    html: tr.outerHTML.replace(/\\s+/g, ' ').slice(0, 1500),
                    controls,
                });
            });
            return {
                found: true, source, id: table.id || null,
                className: (typeof table.className === 'string' ? table.className : null),
                headers, rowCount: rows.length, rows,
            };
        }""")

        print("\n--- ORDER TABLE ---")
        if not order_info.get("found"):
            print("  NO orders table found on /Portfolio.")
        else:
            print(f"  matched-by={order_info['source']} id={order_info['id']!r} "
                  f"rows={order_info['rowCount']}")
            print(f"  headers={order_info['headers']}")
            for r in order_info["rows"]:
                print(f"\n  ROW {r['rowIndex']}  id={r['id']!r} class={r['className']!r}")
                print(f"    text     : {r['text']}")
                print(f"    html     : {r['html']}")
                for c in r["controls"]:
                    print(f"    control  : <{c['tag']}> id={c['id']} class={c['className']} "
                          f"text={c['text']!r} title={c['title']!r} aria={c['aria']!r} "
                          f"href={c['href']!r} onclick={c['onclick']!r}")

        # 2b. Dump the FULL order-grid HTML. Many SPAs keep a JS <template> row that
        #     already contains the per-row action buttons (Change/Cancel) even when no
        #     orders are rendered -> lets us learn the selector without a live order.
        grid_html = await page.evaluate("""() => {
            const t = document.querySelector('#OrderTableList');
            if (!t) return null;
            const container = t.closest('div') || t.parentElement;
            return {
                table: t.outerHTML.replace(/\\s+/g, ' '),
                container: container ? container.outerHTML.replace(/\\s+/g, ' ') : null,
                templates: Array.from(document.querySelectorAll('template'))
                    .map(x => x.innerHTML.replace(/\\s+/g, ' ')),
            };
        }""")
        print("\n--- FULL #OrderTableList HTML ---")
        if grid_html:
            print(grid_html.get("table"))
            print("\n--- PARENT CONTAINER HTML (truncated 6000) ---")
            print((grid_html.get("container") or "")[:6000])
            tpls = grid_html.get("templates", [])
            print(f"\n--- <template> ELEMENTS: {len(tpls)} ---")
            for i, tpl in enumerate(tpls):
                print(f"  [template {i}] {tpl[:1500]}")
        else:
            print("  (#OrderTableList not found)")

        # 2c. Document-wide hunt for any Change/amend/Cancel markup (even outside rows).
        action_nodes = await page.evaluate("""() => {
            const hits = [];
            const rx = /change|amend|cancel|ยกเลิก|แก้ไข/i;
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0 || ['BUTTON', 'A', 'SVG', 'I'].includes(el.tagName)) {
                    const t = (el.innerText || '').trim();
                    const c = (typeof el.className === 'string' ? el.className : '');
                    const oc = el.getAttribute('onclick') || '';
                    if (rx.test(t) || rx.test(c) || rx.test(oc) || rx.test(el.id || '')) {
                        hits.push({ tag: el.tagName.toLowerCase(), id: el.id || null,
                                    className: c.slice(0, 100), text: t.slice(0, 40),
                                    outer: el.outerHTML.replace(/\\s+/g, ' ').slice(0, 260) });
                    }
                }
            });
            return hits.slice(0, 50);
        }""")
        print("\n--- DOCUMENT-WIDE Change/Cancel HINTS ---")
        if not action_nodes:
            print("  (none)")
        for h in action_nodes:
            print(f"  <{h['tag']}> id={h['id']} class={h['className']!r} text={h['text']!r}")
            print(f"      {h['outer']}")

        # 2d. If the grid is empty, relax the "Hide inactive order" filter so any prior
        #     row renders -> reveals the per-row action-button markup.
        if order_info.get("found") and order_info.get("rowCount", 0) == 0:
            cb_state = await page.evaluate("""() => {
                const cb = Array.from(document.querySelectorAll('#OrderTableList input[type=checkbox]'))
                    .find(c => c.closest('th'));
                return cb ? cb.checked : null;
            }""")
            print(f"\n--- 'Hide inactive order' checked = {cb_state} ---")
            if cb_state:
                await page.evaluate("""() => {
                    const cb = Array.from(document.querySelectorAll('#OrderTableList input[type=checkbox]'))
                        .find(c => c.closest('th'));
                    if (cb) cb.click();
                }""")
                await page.wait_for_timeout(3000)
                print(f"    URL after toggle: {page.url}")
                after = await page.evaluate("""() => {
                    const t = document.querySelector('#OrderTableList');
                    const out = [];
                    t.querySelectorAll('tbody tr').forEach(tr => out.push(
                        tr.outerHTML.replace(/\\s+/g, ' ').slice(0, 1600)));
                    return out;
                }""")
                print(f"--- After toggle: {len(after)} row(s) ---")
                for i, h in enumerate(after):
                    print(f"  [row {i}] {h}")

        # 3. Page-level Change / แก้ไข controls (in case it lives outside the row)
        change_btns = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('button, a, [role="button"]').forEach(el => {
                const t = (el.innerText || '').trim();
                const cls = (typeof el.className === 'string' ? el.className : '');
                if (/change|amend|แก้ไข|แก้|edit/i.test(t) ||
                    /change|amend|edit/i.test(el.id || '') ||
                    /change|amend|edit/i.test(cls)) {
                    out.push({ tag: el.tagName.toLowerCase(), id: el.id || null,
                               className: cls || null, text: t.slice(0, 40) });
                }
            });
            return out;
        }""")
        print("\n--- PAGE-LEVEL Change / แก้ไข CONTROLS ---")
        if not change_btns:
            print("  (none found)")
        for b in change_btns:
            print(f"  <{b['tag']}> id={b['id']} class={b['className']} text={b['text']!r}")

        os.makedirs("data/screenshots", exist_ok=True)
        await page.screenshot(path=SHOT)
        print(f"\nScreenshot -> {SHOT}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
