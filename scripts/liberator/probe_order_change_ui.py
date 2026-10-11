"""
Probe the LIVE Liberator amend ("Change") UI for a resting order.
=================================================================
READ-ONLY by default: loads the saved session, navigates to /Portfolio and dumps the
order-row markup **untruncated** (per-cell text + full action-cell HTML + full <tr>).

With ``--click-change`` it clicks the row's **Change** control to reveal the amend UI
(footer pre-fill vs modal) and dumps it, plus the XHR traffic the click fires.

SAFETY: this script NEVER types a PIN and NEVER submits. Neither Buy/Sell/Confirm is
clicked, so no order is placed, cancelled or modified by running it.

Usage:
    .venv/bin/python scripts/liberator/probe_order_change_ui.py
    .venv/bin/python scripts/liberator/probe_order_change_ui.py --order-no 11894
    .venv/bin/python scripts/liberator/probe_order_change_ui.py --order-no 11894 --click-change
"""

import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright

STATE_FILE = "data/liberator_session.json"
PORTFOLIO_URL = "https://webtrade.liberator.co.th/Portfolio"
SHOT_DIR = "data/screenshots"

# Per-row action cell = last <td>; the controls are plain Vue <div class="cursor-pointer">.
ROW_JS = """() => {
    const t = document.querySelector('#OrderTableList');
    if (!t) return {found: false, rows: []};
    const out = [];
    t.querySelectorAll('tbody tr').forEach(tr => {
        const tds = Array.from(tr.querySelectorAll('td'));
        const cells = tds.map(td => (td.innerText || '').replace(/\\s+/g, ' ').trim());
        const act = tds.length ? tds[tds.length - 1] : null;
        out.push({
            cells: cells,
            orderNo: (cells[0] || '').replace(/[^0-9]/g, ''),
            actionHTML: act ? act.innerHTML : '',
            actionActions: act ? Array.from(act.querySelectorAll('div.cursor-pointer')).map(d => (d.innerText || '').trim()) : [],
            rowHTML: tr.outerHTML
        });
    });
    return {found: true, rows: out};
}"""

AMEND_UI_JS = """() => {
    const vis = el => { const r = el.getBoundingClientRect(); return r.width > 12 && r.height > 12; };
    const out = { url: location.href, overlays: [], inputs: [], buttons: [], known: {} };
    document.querySelectorAll('[role=dialog], [class*=modal], [class*=popup], [class*=overlay], [class*=drawer]').forEach(el => {
        if (vis(el)) out.overlays.push({
            tag: el.tagName.toLowerCase(), id: el.id || null,
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 130),
            text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 500)
        });
    });
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!vis(el)) return;
        out.inputs.push({
            tag: el.tagName.toLowerCase(), id: el.id || null, name: el.name || null,
            type: el.type || null, value: el.value || '', ph: el.placeholder || null,
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 100)
        });
    });
    document.querySelectorAll('button, [role=button], div.cursor-pointer').forEach(el => {
        const txt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (txt && txt.length <= 26 && vis(el)) out.buttons.push({
            tag: el.tagName.toLowerCase(), id: el.id || null, text: txt,
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 90)
        });
    });
    ['#price', '#volume', '#pin', '#buttonSubmit', '#SearchSymbolList-setBuySellFooter'].forEach(sel => {
        const el = document.querySelector(sel);
        out.known[sel] = el ? {
            exists: true, visible: vis(el), value: el.value !== undefined ? el.value : null,
            text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 200)
        } : { exists: false };
    });
    out.overlayHTML = '';
    out.overlayButtons = [];
    out.overlayInputs = [];
    const ov = Array.from(document.querySelectorAll('div.overlay')).filter(vis)[0];
    if (ov) {
        out.overlayHTML = ov.outerHTML;
        out.overlayButtons = Array.from(ov.querySelectorAll('button, div, span, a'))
            .filter(vis)
            .map(el => ({ tag: el.tagName.toLowerCase(), id: el.id || null,
                          text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
                          cls: (typeof el.className === 'string' ? el.className : '').slice(0, 80) }))
            .filter(b => b.text && b.text.length <= 20);
        out.overlayInputs = Array.from(ov.querySelectorAll('input')).map(el => ({
            id: el.id || null, type: el.type || null, value: el.value || '',
            disabled: el.disabled === true, readonly: el.readOnly === true,
            ph: el.placeholder || null
        }));
    }
    return out;
}"""


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order-no", default=None, help="target order number (default: first row)")
    ap.add_argument("--click-change", action="store_true", help="click the row Change control (NO submit)")
    ap.add_argument("--hold", type=int, default=15, help="seconds to keep window open after clicking")
    args = ap.parse_args()

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

        recording = {"on": False}
        reqs = []
        api_bodies = []

        def on_request(req):
            if recording["on"]:
                reqs.append(f"{req.method} {req.url[:150]} POST={str(req.post_data)[:240]!r}")

        async def on_response(resp):
            if recording["on"] and (
                "bid-offer" in resp.url or "stock/info" in resp.url or "/va/order" in resp.url
            ):
                try:
                    body = await resp.text()
                except Exception as exc:  # noqa: BLE001
                    body = f"<unreadable: {exc}>"
                api_bodies.append({"url": resp.url, "status": resp.status, "body": body[:2500]})

        page.on("request", on_request)
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        print(f"Navigating to {PORTFOLIO_URL} ...")
        await page.goto(PORTFOLIO_URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)
        print(f"   URL   : {page.url}")
        if "login" in page.url.lower():
            print("SESSION NOT AUTHENTICATED. Aborting.")
            await browser.close()
            return

        grid = await page.evaluate(ROW_JS)
        rows = grid.get("rows", [])
        print(f"\n--- ORDER ROWS ({len(rows)}) ---")
        for i, r in enumerate(rows):
            print(f"  [{i}] cells={r['cells']}")
            print(f"      action-controls={r['actionActions']}")

        if not rows:
            print("\nNo rows -> cannot inspect the Change control. Aborting.")
            await browser.close()
            return

        target = None
        for r in rows:
            if args.order_no is None or r["orderNo"] == str(args.order_no):
                target = r
                break
        if target is None:
            print(f"\nOrder {args.order_no} not present in the grid. Aborting.")
            await browser.close()
            return

        print(f"\n--- TARGET ORDER {target['orderNo']} : ACTION CELL (full) ---")
        print(target["actionHTML"])
        os.makedirs(SHOT_DIR, exist_ok=True)
        dump = f"data/liberator_order_row_{target['orderNo']}.html"
        with open(dump, "w") as f:
            f.write(target["rowHTML"])
        print(f"\nFull <tr> HTML -> {dump}  ({len(target['rowHTML'])} chars)")

        if not args.click_change:
            depth = await page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('table').forEach((t, i) => {
                    const h = t.querySelector('thead');
                    const txt = h ? h.innerText.replace(/\\s+/g, ' ').trim() : '';
                    if (/bid/i.test(txt) && /offer/i.test(txt)) {
                        out.push({ index: i, header: txt,
                            rows: Array.from(t.querySelectorAll('tbody tr')).map(tr => (tr.innerText || '').replace(/\\s+/g, ' ').trim()) });
                    }
                });
                return out;
            }""")
            print("\n--- MARKET DEPTH TABLES ---")
            if not depth:
                print("  (none)")
            for d in depth:
                print(f"  table[{d['index']}] hdr={d['header']!r}")
                for r in d["rows"]:
                    print(f"    {r}")
            await page.screenshot(path=f"{SHOT_DIR}/liberator_order_row_only.png")
            print(f"Screenshot -> {SHOT_DIR}/liberator_order_row_only.png")
            print("\n(read-only run: 'Change' NOT clicked)")
            await browser.close()
            return

        # --- Proven resolver (diag_change_locator.py, 2026-10-09) ---
        # WARNING: never anchor the row with a \b-regex on row text -- this Vue table's
        # textContent has NO whitespace between cells ("1189410:03:21BCHSELL..."), so a
        # word boundary after the order number never matches. Anchor on the checkbox id.
        row_loc = page.locator(
            f"#OrderTableList tbody tr:has(input[id='{target['orderNo']}'])"
        ).first
        rows_n = await row_loc.count()
        action_cell = row_loc.locator("td").last
        print(f"\n>>> row resolved={rows_n}  action-cell td count={await action_cell.count()}")

        candidates = [
            ("get_by_text exact", action_cell.get_by_text("Change", exact=True)),
            ("div.cursor-pointer+str", action_cell.locator("div.cursor-pointer").filter(has_text="Change")),
            ("div:text-is", action_cell.locator('div:text-is("Change")')),
            ("xpath normalize-space", action_cell.locator("xpath=.//div[normalize-space(text())='Change']")),
        ]
        change_loc = None
        for name, cand in candidates:
            n = await cand.count()
            print(f"    candidate {name:<22} -> count={n}")
            if n and change_loc is None:
                change_loc = cand.first
        if change_loc is None:
            print("!! could not resolve the Change control with any known strategy. Aborting.")
            await browser.close()
            return
        print(">>> CLICKING 'Change' (opens amend form - NO submit, NO PIN) ...")
        recording["on"] = True
        await change_loc.click()
        await page.wait_for_timeout(4000)
        recording["on"] = False

        print(f"\n--- XHR AFTER CLICK ({len(reqs)}) ---")
        for r in reqs[:40]:
            print(f"  {r}")

        print(f"\n--- API RESPONSE BODIES ({len(api_bodies)}) ---")
        if not api_bodies:
            print("  (none captured)")
        for a in api_bodies:
            print(f"  [{a['status']}] {a['url'][:130]}")
            print(f"     {a['body']}")

        ui = await page.evaluate(AMEND_UI_JS)
        print(f"\n--- AMEND UI  url={ui['url']} ---")
        print("  OVERLAYS:")
        for o in ui["overlays"] or []:
            print(f"    <{o['tag']}> id={o['id']} cls={o['cls']!r}\n       text={o['text']!r}")
        if not ui["overlays"]:
            print("    (none)")
        print("  INPUTS:")
        for i in ui["inputs"]:
            print(f"    <{i['tag']}> id={i['id']} name={i['name']} type={i['type']} value={i['value']!r} ph={i['ph']!r} cls={i['cls']!r}")
        if not ui["inputs"]:
            print("    (none)")
        print("  KNOWN SELECTORS:")
        for k, v in ui["known"].items():
            print(f"    {k} -> {v}")
        print("  BUTTON-ISH (<=26 chars):")
        seen = set()
        for b in ui["buttons"]:
            key = (b["id"], b["text"])
            if key in seen:
                continue
            seen.add(key)
            print(f"    <{b['tag']}> id={b['id']} text={b['text']!r} cls={b['cls']!r}")

        print(f"\n  OVERLAY HTML: {len(ui.get('overlayHTML') or '')} chars")
        if ui.get("overlayHTML"):
            with open("data/liberator_amend_overlay.html", "w") as f:
                f.write(ui["overlayHTML"])
            print("    -> data/liberator_amend_overlay.html")
        print("  OVERLAY INPUTS:")
        for i in ui.get("overlayInputs", []):
            print(f"    #{i['id']} type={i['type']} value={i['value']!r} "
                  f"disabled={i['disabled']} readonly={i['readonly']} ph={i['ph']!r}")
        print("  OVERLAY BUTTONS:")
        seen2 = set()
        for b in ui.get("overlayButtons", []):
            k = (b["tag"], b["id"], b["text"])
            if k in seen2:
                continue
            seen2.add(k)
            print(f"    <{b['tag']}> id={b['id']} text={b['text']!r} cls={b['cls']!r}")

        shot = f"{SHOT_DIR}/liberator_amend_ui_probe.png"
        await page.screenshot(path=shot)
        print(f"\nScreenshot -> {shot}")
        print(f"Holding window {args.hold}s for human inspection ... (nothing is submitted)")
        await page.wait_for_timeout(args.hold * 1000)
        await browser.close()
        print("Closed. NO submit was performed.")


if __name__ == "__main__":
    asyncio.run(main())
