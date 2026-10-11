"""
Probe where the TradeMan SPA keeps its API `authenKey` (JWT) and prove that an
in-page fetch of the real quote API works.
==============================================================================
READ-ONLY: resumes the saved session (NO OTP) and runs two page-side scripts:

1. enumerate localStorage / sessionStorage for JWT-looking values,
2. POST ``loadstockinformation`` for a symbol via ``fetch`` in the page context
   (the app's own origin + cookies) and print ``stockInfo`` (lastSalePrice etc.).

SAFETY: no order actions, no PIN. The JWT is never printed in full.

Usage:
    .venv/bin/python scripts/krungsri/probe_quote_api.py --symbol VGI
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

STORAGE_JS = """() => {
    const scan = (store) => {
        const rows = [];
        for (let i = 0; i < store.length; i++) {
            const k = store.key(i);
            let v = '';
            try { v = store.getItem(k) || ''; } catch (e) { v = ''; }
            rows.push({ key: k, len: v.length, looksJwt: v.includes('eyJ'), head: v.slice(0, 40) });
        }
        return rows;
    };
    return { localStorage: scan(localStorage), sessionStorage: scan(sessionStorage),
             cookieLen: (document.cookie || '').length };
}"""

FETCH_JS = """async ([apiBase, symbol, key]) => {
    const r = await fetch(apiBase + '/loadstockinformation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: { symbol: symbol }, authenKey: key })
    });
    let body = null;
    try { body = await r.json(); } catch (e) { body = { parse_error: String(e) }; }
    return { status: r.status, body: body };
}"""

TOKEN_JS = """(prefix) => {
    const hits = [];
    for (const store of [localStorage, sessionStorage]) {
        for (let i = 0; i < store.length; i++) {
            const k = store.key(i);
            let v = '';
            try { v = store.getItem(k) || ''; } catch (e) { continue; }
            if (!v) continue;
            try {
                const o = JSON.parse(v);
                const walk = (node, path) => {
                    if (typeof node === 'string') {
                        if (node.startsWith(prefix)) hits.push({ key: k, path: path, token: node });
                    } else if (node && typeof node === 'object') {
                        for (const kk of Object.keys(node)) walk(node[kk], path + '.' + kk);
                    }
                };
                walk(o, k);
            } catch (e) {
                if (v.startsWith(prefix)) hits.push({ key: k, path: k, token: v });
            }
        }
    }
    return hits;
}"""

API_BASE = "https://api-trademanpro.efinancethai.com/efinTrade.TrademanPro.Stock.API/api"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="VGI")
    args = ap.parse_args()

    print("=" * 78)
    print(" KRUNGSRI TRADEMAN - QUOTE API / authenKey LOCATION PROBE (READ-ONLY)")
    print("=" * 78)

    res = await auth_driver.login(force_fresh=False)
    print(f"[session] success={res.success} msg={res.message}")
    if not res.success:
        return 2
    page = trademan_driver.page
    if not page or page.is_closed():
        print("!! no page")
        return 2

    if "trademan.in.th" not in (page.url or ""):
        await page.goto("https://trademan.in.th/Portfolio")
        await page.wait_for_timeout(5000)

    store = await page.evaluate(STORAGE_JS)
    print(f"\n--- localStorage ({len(store['localStorage'])}) ---")
    for r in store["localStorage"]:
        print(f"   key={r['key']!r} len={r['len']} jwt={r['looksJwt']} head={r['head']!r}")
    print(f"--- sessionStorage ({len(store['sessionStorage'])}) ---")
    for r in store["sessionStorage"]:
        print(f"   key={r['key']!r} len={r['len']} jwt={r['looksJwt']} head={r['head']!r}")

    hits = await page.evaluate(TOKEN_JS, "eyJ")
    print(f"\n--- JWT-looking values found: {len(hits)} ---")
    for h in hits:
        print(f"   store-key={h['key']!r} path={h['path']} token_head={h['token'][:32]}... len={len(h['token'])}")

    if not hits:
        print("!! no JWT found in web storage - API call cannot be reproduced this way.")
        return 1

    token = hits[0]["token"]
    out = await page.evaluate(FETCH_JS, [API_BASE, args.symbol.upper(), token])
    print(f"\n--- IN-PAGE FETCH loadstockinformation({args.symbol}) -> HTTP {out['status']} ---")
    body = out["body"] or {}
    if isinstance(body, dict) and body.get("result"):
        print(f"   result: {json.dumps(body.get('result'), ensure_ascii=False)}")
        info = (body.get("response") or {}).get("stockInfo")
        print(f"   stockInfo: {json.dumps(info, ensure_ascii=False)[:1500]}")
    else:
        print(f"   body: {json.dumps(body, ensure_ascii=False)[:1200]}")
    print("\nDONE - read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
