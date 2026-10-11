"""
Probe the LIVE Krungsri TradeMan 'View Order' ledger action column (col [9]).
============================================================================
READ-ONLY by default: resumes the saved session (``data/session_state.json``,
NO OTP) and dumps every ledger row's cells plus the RAW ``outerHTML`` of the
actions cell (last ``<td>``) — that is where the per-row controls live.

TradeMan has NO native in-place "Change" button (confirmed by operator
2026-10-09), so the amend path MUST be Cancel + Re-submit. This probe pins the
exact Cancel control + confirmation modal selectors.

With ``--click-cancel`` it clicks the row's Cancel control to reveal the
confirmation modal/overlay and dumps it, plus the XHR the click fires.

SAFETY: this script NEVER types a PIN, NEVER clicks Confirm / ตกลง / ยืนยัน,
and NEVER submits. No order is ever cancelled or modified by running it.

Usage:
    .venv/bin/python scripts/krungsri/probe_order_actions_ui.py
    .venv/bin/python scripts/krungsri/probe_order_actions_ui.py --order-no 1234567
    .venv/bin/python scripts/krungsri/probe_order_actions_ui.py --click-cancel --order-no 1234567
"""

import argparse
import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DISPLAY", ":0")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from app.core.config import settings  # noqa: E402

settings.PLAYWRIGHT_HEADLESS = False

from app.browser.auth_driver import auth_driver  # noqa: E402
from app.browser.trademan_driver import trademan_driver  # noqa: E402

SHOT_DIR = os.path.join(PROJECT_ROOT, "data", "screenshots")

# Ledger rows: deterministic table isolation (same rule as trademan_driver._VIEW_ORDER_ROWS_JS)
# but ALSO returns the raw outerHTML of the actions cell (last <td>) + every clickable child.
ROWS_JS = """() => {
    const tables = Array.from(document.querySelectorAll('table'));
    const hdr = tables.find(t => {
        const ths = Array.from(t.querySelectorAll('thead th')).map(x => (x.textContent || '').trim());
        return ths.includes('Order No.') && ths.includes('Status') && ths.includes('Symbol');
    });
    if (!hdr) return { ok: false, reason: 'no_view_order_header',
        headers: tables.map(t => Array.from(t.querySelectorAll('thead th')).map(x => (x.textContent || '').trim())) };
    let scope = hdr.parentElement;
    while (scope && !scope.querySelector('div.overflow-y-auto.scrollbar-container')) scope = scope.parentElement;
    let body = scope ? scope.querySelector('div.overflow-y-auto.scrollbar-container table') : null;
    if (!body) body = tables.find(t => t !== hdr && t.querySelector('tr') && t.querySelector('tr').querySelectorAll('td').length >= 9);
    if (!body) return { ok: false, reason: 'no_view_order_body' };
    const rows = [];
    Array.from(body.querySelectorAll('tr')).forEach((tr) => {
        const tds = Array.from(tr.querySelectorAll('td'));
        if (tds.length < 9) return;
        tr.setAttribute('data-probe-idx', String(rows.length));
        const act = tds[tds.length - 1];
        const clickables = [];
        act.querySelectorAll('button, a, i, span, div, svg, img').forEach(el => {
            const txt = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            const cls = (typeof el.className === 'string') ? el.className : '';
            const ttl = el.getAttribute ? (el.getAttribute('title') || '') : '';
            const tag = el.tagName.toLowerCase();
            if (txt || ttl || tag === 'img' || tag === 'svg') {
                clickables.push({ tag: tag, id: el.id || null,
                    text: txt.slice(0, 40), title: ttl, cls: String(cls).slice(0, 90) });
            }
        });
        rows.push({
            idx: rows.length,
            cells: tds.map(td => (td.innerText || '').trim()),
            nCells: tds.length,
            actionHTML: act ? act.outerHTML : '',
            clickables: clickables
        });
    });
    return { ok: true, nRows: rows.length, rows: rows };
}"""

# Scan the page for market-price widgets (to locate the real "Last" trade source).
MARKET_SCAN_JS = """() => {
    const re = /(ราคาล่าสุด|Last|ล่าสุด|Bid|Offer|เสนอซื้อ|เสนอขาย|ราคาเปิด|ราคาสูงสุด|ราคาต่ำสุด|เปลี่ยนแปลง)/;
    const out = [];
    document.querySelectorAll('span,div,td,th,label,b,strong').forEach(el => {
        const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (t && t.length <= 40 && re.test(t) && el.children.length === 0) {
            out.push({ tag: el.tagName.toLowerCase(), id: el.id || null,
                cls: (typeof el.className === 'string' ? el.className : '').slice(0, 70), text: t });
        }
    });
    return out.slice(0, 80);
}"""

MODAL_JS = """() => {
    const vis = el => { const r = el.getBoundingClientRect(); return r.width > 12 && r.height > 12; };
    const out = { url: location.href, overlays: [], inputs: [], buttons: [] };
    document.querySelectorAll('[role=dialog], [class*=modal], [class*=popup], [class*=overlay]').forEach(el => {
        if (vis(el)) out.overlays.push({
            tag: el.tagName.toLowerCase(), id: el.id || null,
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 130),
            html: el.outerHTML.slice(0, 4000),
            text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 600)
        });
    });
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!vis(el)) return;
        out.inputs.push({ tag: el.tagName.toLowerCase(), id: el.id || null, name: el.name || null,
            type: el.type || null, value: el.value || '', ph: el.placeholder || null });
    });
    document.querySelectorAll('button, a, [role=button]').forEach(el => {
        const txt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (txt && txt.length <= 26 && vis(el)) out.buttons.push({
            tag: el.tagName.toLowerCase(), id: el.id || null, text: txt,
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 90) });
    });
    return out;
}"""

CANCEL_CANDIDATES = [
    'button:has-text("Cancel")', 'button:has-text("ยกเลิก")', 'a:has-text("Cancel")',
    'a:has-text("ยกเลิก")', '[title*="ancel"]', '[title*="ยกเลิก"]',
    'text="Cancel"', 'text="ยกเลิก"',
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--order-no", default=None, help="Target order no. for --click-cancel")
    ap.add_argument("--click-cancel", action="store_true", help="Click the row's Cancel control (NO confirm/PIN)")
    ap.add_argument("--hold", type=int, default=0, help="Keep browser open N seconds (human inspection)")
    args = ap.parse_args()

    os.makedirs(SHOT_DIR, exist_ok=True)

    print("=" * 78)
    print(" KRUNGSRI TRADEMAN - VIEW ORDER ACTIONS PROBE (READ-ONLY, no PIN, no submit)")
    print("=" * 78)

    # 1. Resume the saved session (no OTP: session_state.json is valid)
    res = await auth_driver.login(force_fresh=False)
    print(f"[session] success={res.success} status={res.status} resumed={getattr(res, 'resumed', None)} msg={res.message}")
    if not res.success:
        print("!! session not usable - aborting probe (no OTP fired).")
        return 2

    page = trademan_driver.page
    if not page or page.is_closed():
        print("!! no TradeMan page after resume - aborting.")
        return 2
    print(f"[page] url={page.url}")

    # 2. Switch to the 'View Order' ledger tab
    ok = await trademan_driver.switch_tab("order_status")
    print(f"[tab] switch_tab('order_status') -> {ok}")
    await page.wait_for_timeout(1500)

    # 3. Dump the ledger rows + actions-cell markup
    data = await page.evaluate(ROWS_JS)
    if not data.get("ok"):
        print(f"!! ledger not found: {data.get('reason')}")
        print("   page headers:", json.dumps(data.get("headers"), ensure_ascii=False))
        await page.screenshot(path=os.path.join(SHOT_DIR, "krungsri_order_probe_no_table.png"))
        return 1

    print(f"\n--- LEDGER: {data['nRows']} row(s) ---")
    for row in data["rows"]:
        cells = row["cells"]
        print(f"\n[#{row['idx']}] nCells={row['nCells']} cells={json.dumps(cells[:-1], ensure_ascii=False)}")
        print(f"   actions-html({len(row['actionHTML'])} chars): {row['actionHTML'][:400]}")
        for c in row["clickables"]:
            print(f"     <{c['tag']}> id={c['id']} title={c['title']!r} text={c['text']!r} cls={c['cls']!r}")

    with open(os.path.join(PROJECT_ROOT, "data", "krungsri_order_actions_dump.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n-> data/krungsri_order_actions_dump.json")

    # 4. Scan for the market 'Last' widget source
    print("\n--- MARKET WIDGET SCAN (find real Last/Bid/Offer source) ---")
    for m in await page.evaluate(MARKET_SCAN_JS):
        print(f"   <{m['tag']}> id={m['id']} cls={m['cls']!r} text={m['text']!r}")

    await page.screenshot(path=os.path.join(SHOT_DIR, "krungsri_order_actions_probe.png"), full_page=False)
    return await _maybe_click_cancel(args, page, data)


async def _maybe_click_cancel(args, page, data) -> int:
    """Optionally click the target row's Cancel control (reveals modal; NEVER confirms)."""
    if not args.click_cancel:
        if args.hold:
            print(f"\nHolding window {args.hold}s for human inspection (nothing submitted) ...")
            await page.wait_for_timeout(args.hold * 1000)
        print("\nDONE - NO submit / NO cancel confirmed / NO PIN typed.")
        return 0

    target = None
    for row in data["rows"]:
        if args.order_no and row["cells"] and args.order_no in row["cells"][0]:
            target = row
            break
    if target is None and not args.order_no and data["rows"]:
        target = data["rows"][0]
    if target is None:
        print(f"\n!! --click-cancel: no row matched order-no={args.order_no!r}; aborting click.")
        return 1

    print(f"\n>>> CLICKING Cancel on row idx={target['idx']} order={target['cells'][0]!r} (NO confirm, NO PIN) ...")
    row_loc = page.locator(f'tr[data-probe-idx="{target["idx"]}"]')
    clicked = False
    for sel in CANCEL_CANDIDATES:
        loc = row_loc.locator(sel)
        try:
            n = await loc.count()
        except Exception:
            n = 0
        print(f"    candidate {sel!r} -> count={n}")
        if n:
            try:
                await loc.first.click()
                clicked = True
                break
            except Exception as e:
                print(f"    click failed: {e}")
    if not clicked:
        print("!! could not click any Cancel candidate.")
        return 1

    await page.wait_for_timeout(2000)
    modal = await page.evaluate(MODAL_JS)
    print(f"\n--- CONFIRM UI  url={modal['url']} ---")
    print("  OVERLAYS:")
    for o in modal["overlays"] or []:
        print(f"    <{o['tag']}> id={o['id']} cls={o['cls']!r}\n       text={o['text']!r}\n       html={o['html'][:1200]}")
    if not modal["overlays"]:
        print("    (none)")
    print("  INPUTS:")
    for i in modal["inputs"]:
        print(f"    <{i['tag']}> id={i['id']} name={i['name']} type={i['type']} value={i['value']!r} ph={i['ph']!r}")
    print("  BUTTONS:")
    for b in modal["buttons"]:
        print(f"    <{b['tag']}> id={b['id']} text={b['text']!r} cls={b['cls']!r}")
    await page.screenshot(path=os.path.join(SHOT_DIR, "krungsri_cancel_confirm_probe.png"))
    print("-> data/screenshots/krungsri_cancel_confirm_probe.png")

    dump_path = os.path.join(PROJECT_ROOT, "data", "krungsri_cancel_confirm.html")
    with open(dump_path, "w", encoding="utf-8") as f:
        f.write("\n\n<!-- ===== OVERLAY ===== -->\n\n".join(o["html"] for o in (modal["overlays"] or [])))
    print(f"-> data/krungsri_cancel_confirm.html ({os.path.getsize(dump_path)} bytes)")

    if args.hold:
        print(f"\nHolding window {args.hold}s for human inspection (nothing submitted) ...")
        await page.wait_for_timeout(args.hold * 1000)

    print("\nDONE - NO submit / NO cancel confirmed / NO PIN typed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
