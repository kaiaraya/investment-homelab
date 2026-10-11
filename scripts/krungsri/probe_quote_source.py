"""
Probe the LIVE Krungsri TradeMan market-quote source (Bid 1 / Offer 1 / Last).
==============================================================================
READ-ONLY: resumes the saved session (``data/session_state.json``, NO OTP),
opens the Buy/Sell side panel, selects the SHORT side + a symbol, then:

1. captures the XHR the app fires (URL + JSON body) to locate the quote API,
2. dumps the Buy/Sell panel markup (the natural home of Bid/Offer/Last),
3. dumps every visible price-ish leaf element (with its viewport x/y so the
   right-hand panel is easy to spot).

SAFETY: NOTHING is submitted. ``#send_order__btn`` is never clicked, no PIN is
typed. Selecting a side/symbol only pre-fills the form.

Usage:
    .venv/bin/python scripts/krungsri/probe_quote_source.py --symbol VGI
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

# Dump the Buy/Sell panel (walk up from #send_order__btn to the first ancestor with
# enough text) + every visible price-ish leaf element with its on-screen position.
PANEL_JS = """() => {
    const vis = el => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
    const out = { found: false, panelHTML: '', priceLeaves: [], labels: [] };
    const btn = document.getElementById('send_order__btn');
    if (btn) {
        let node = btn, hops = 0;
        while (node && hops < 10) {
            node = node.parentElement; hops++;
            if (node && (node.innerText || '').length > 400) { out.found = true; out.panelHTML = node.outerHTML; break; }
        }
    }
    const priceRe = /\\d{1,3}(?:,\\d{3})*(?:\\.\\d{1,4})?/;
    document.querySelectorAll('span,div,i,b,strong,td,p').forEach(el => {
        if (el.children.length !== 0 || !vis(el)) return;
        const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (!t || t.length > 26) return;
        const r = el.getBoundingClientRect();
        if (priceRe.test(t) && /^[\\d,\\.]+$/.test(t.replace(/\\s/g, ''))) {
            out.priceLeaves.push({ tag: el.tagName.toLowerCase(), id: el.id || null,
                cls: (typeof el.className === 'string' ? el.className : '').slice(0, 80),
                text: t, x: Math.round(r.x), y: Math.round(r.y) });
        }
    });
    out.priceLeaves = out.priceLeaves.slice(0, 120);
    document.querySelectorAll('span,div,label').forEach(el => {
        if (el.children.length !== 0 || !vis(el)) return;
        const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (t && t.length <= 30 && /(ราคา|ล่าสุด|Last|Bid|Offer|เสนอ|ซื้อ|ขาย|เปิด|สูงสุด|ต่ำสุด|Volume|On Hand|ยอด)/.test(t)) {
            out.labels.push({ tag: el.tagName.toLowerCase(), id: el.id || null, text: t });
        }
    });
    out.labels = out.labels.slice(0, 80);
    return out;
}"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="VGI", help="Symbol to load into the order form")
    ap.add_argument("--side", default="SHORT", help="Side button to select (default SHORT)")
    ap.add_argument("--hold", type=int, default=0, help="Keep window open N seconds")
    args = ap.parse_args()

    os.makedirs(SHOT_DIR, exist_ok=True)

    print("=" * 78)
    print(" KRUNGSRI TRADEMAN - MARKET QUOTE SOURCE PROBE (READ-ONLY, no send, no PIN)")
    print("=" * 78)

    res = await auth_driver.login(force_fresh=False)
    print(f"[session] success={res.success} resumed={getattr(res, 'resumed', None)} msg={res.message}")
    if not res.success:
        print("!! session not usable - aborting (no OTP fired).")
        return 2

    page = trademan_driver.page
    if not page or page.is_closed():
        print("!! no TradeMan page - aborting.")
        return 2

    xhr = []
    SKIP = ("google", "facebook", "doubleclick", "analytics", "gstatic", "youtubeads", "yimg")

    async def _on_response(resp):
        url = resp.url or ""
        if any(h in url.lower() for h in SKIP):
            return
        try:
            ct = (resp.headers or {}).get("content-type", "")
        except Exception:
            ct = ""
        if "json" not in (ct or ""):
            return
        try:
            body = await resp.text()
        except Exception:
            return
        markers = [k for k in ("bid", "offer", "last", "priorclose", "marketprice", "quote") if k in body.lower()]
        req = resp.request
        hdrs = {k: v for k, v in (req.headers or {}).items()
                if k.lower() in ("content-type", "authorization", "x-api-key", "x-token", "requestverificationtoken", "origin")}
        xhr.append({"method": req.method, "url": url, "status": resp.status,
                    "markers": markers, "post_data": (req.post_data or "")[:1500],
                    "headers": hdrs, "body": body[:8000]})

    page.on("response", _on_response)

    await page.goto("https://trademan.in.th/Portfolio")
    await page.wait_for_timeout(6000)

    # Save the pre-selection XHR (page load -> quotes/watchlist payloads)
    print(f"\n--- JSON XHR after Portfolio load ({len(xhr)}) ---")
    for x in xhr:
        print(f"   {x['status']} {x['method']} {x['url'][:150]}  markers={x['markers']}")
    with open(os.path.join(PROJECT_ROOT, "data", "krungsri_quote_xhr.json"), "w", encoding="utf-8") as f:
        json.dump(xhr, f, ensure_ascii=False, indent=2)

    # Open the Buy/Sell side panel (do NOT click Send)
    if not await page.evaluate("() => !!document.getElementById('send_order__btn')"):
        toggle = await page.query_selector("div[title='Buy/Sell'], #myMenu div:has-text('Buy/Sell')")
        if toggle:
            await toggle.click()
            await page.wait_for_timeout(1200)

    # Select side + symbol (pre-fills the form only)
    side_loc = page.locator(f"span:text-is('{args.side}')").first
    if await side_loc.count() and await side_loc.is_visible():
        await side_loc.click()
        await page.wait_for_timeout(500)
    await page.evaluate("""(sym) => {
        const tds = Array.from(document.querySelectorAll('td'));
        const m = tds.find(td => td.innerText && td.innerText.trim() === sym);
        if (m) m.click();
    }""", args.symbol)
    await page.wait_for_timeout(2000)

    data = await page.evaluate(PANEL_JS)
    print(f"\n--- BUY/SELL PANEL found={data['found']} ({len(data['panelHTML'])} chars) ---")
    with open(os.path.join(PROJECT_ROOT, "data", "krungsri_buysell_panel.html"), "w", encoding="utf-8") as f:
        f.write(data["panelHTML"])
    print("-> data/krungsri_buysell_panel.html")

    print("\n--- LABELS (market-related) ---")
    seen = set()
    for l in data["labels"]:
        k = (l["text"], l["id"])
        if k in seen:
            continue
        seen.add(k)
        print(f"   <{l['tag']}> id={l['id']} text={l['text']!r}")

    print("\n--- PRICE-ISH LEAVES (x>1000 = right panel) ---")
    for p in data["priceLeaves"]:
        print(f"   x={p['x']:>5} y={p['y']:>5} <{p['tag']}> id={p['id']} text={p['text']!r} cls={p['cls']!r}")

    print(f"\n--- JSON XHR after side/symbol selection ({len(xhr)}) ---")
    for x in xhr:
        print(f"   {x['status']} {x['method']} {x['url'][:150]}  markers={x['markers']}")
    with open(os.path.join(PROJECT_ROOT, "data", "krungsri_quote_xhr.json"), "w", encoding="utf-8") as f:
        json.dump(xhr, f, ensure_ascii=False, indent=2)
    print("-> data/krungsri_quote_xhr.json")

    await page.screenshot(path=os.path.join(SHOT_DIR, "krungsri_quote_probe.png"))
    print("-> data/screenshots/krungsri_quote_probe.png")

    if args.hold:
        await page.wait_for_timeout(args.hold * 1000)
    print("\nDONE - NOTHING submitted, no PIN typed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
