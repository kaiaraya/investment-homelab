"""probe_liberator_quote_api.py — D3 fix design proof (READ-ONLY, headless).

Proves the API-based quote path end-to-end against the live broker using the SAME
session cookie jar as the driver (context.request shares cookies):

  1. GET  /vb/config          -> master list : [SYMBOL, orderBookId, ...] tuples
  2. resolve SYMBOL -> orderBookId
  3. POST /vb/stock/info      {"orderBookIds":[id]}  -> n(symbol) + l(last) + bp/bv/op/ov
  4. POST /vb/stock/bid-offer {"orderBookId": id}    -> 10-level depth bp/bv/op/ov

Never submits an order (only whitelisted quote endpoints).
Run: .venv/bin/python scripts/liberator/probe_liberator_quote_api.py [SYMBOL]
"""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

SYMBOL = (sys.argv[1] if len(sys.argv) > 1 else "BCH").upper()
BASE = "https://webtrade.liberator.co.th"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def find_rows(node, symbol, out):
    """Recursively collect array rows whose [0] == symbol (tuple-style master data)."""
    if isinstance(node, list):
        if (len(node) >= 2 and isinstance(node[0], str)
                and node[0].upper() == symbol and isinstance(node[1], (str, int))):
            out.append(node)
        for x in node:
            find_rows(x, symbol, out)
    elif isinstance(node, dict):
        for x in node.values():
            find_rows(x, symbol, out)


async def main():
    cookies = json.load(open("data/liberator_session.json")).get("cookies", [])
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome",
                                    args=["--no-sandbox", "--disable-setuid-sandbox"])
        ctx = await b.new_context(user_agent=UA)
        await ctx.add_cookies(cookies)
        hdr = {"Content-Type": "application/json"}

        r = await ctx.request.get(f"{BASE}/vb/config")
        cfg = await r.json()
        json.dump(cfg, open("/tmp/lib_vb_config.json", "w"), ensure_ascii=False)
        print("=== /vb/config status:", r.status, "===")
        node = cfg.get("result", {}).get("data", {}).get("config", {})
        for grp, v in (node.items() if isinstance(node, dict) else []):
            if isinstance(v, dict):
                print(f"  group {grp!r}: keys={list(v.keys())}")
                for k2, v2 in v.items():
                    if isinstance(v2, list):
                        print(f"    {grp}.{k2}: list len={len(v2)} sample={v2[:1]}")

        rows = []
        find_rows(cfg, SYMBOL, rows)
        print(f"\n=== rows matching {SYMBOL}: {len(rows)} ===")
        for row in rows[:5]:
            print("  ", json.dumps(row[:8], ensure_ascii=False))
        obid = rows[0][1] if rows else None
        print("resolved orderBookId =", obid)

        if obid is not None:
            r2 = await ctx.request.post(f"{BASE}/vb/stock/info", headers=hdr,
                                        data=json.dumps({"orderBookIds": [int(obid)]}))
            info = await r2.json()
            lst = info.get("result", {}).get("list", [])
            print(f"\n=== /vb/stock/info status {r2.status} -> list len {len(lst)} ===")
            if lst:
                s = lst[0]
                print("  n(symbol)=", s.get("n"), "| ne(name)=", s.get("ne"),
                      "| l(last)=", s.get("l"), "| bp=", s.get("bp"), s.get("bv"),
                      "| op=", s.get("op"), s.get("ov"))

            r3 = await ctx.request.post(f"{BASE}/vb/stock/bid-offer", headers=hdr,
                                        data=json.dumps({"orderBookId": int(obid)}))
            bo = await r3.json()
            d = bo.get("result", {}).get("data", {})
            print(f"\n=== /vb/stock/bid-offer status {r3.status} ===")
            print("  bp:", d.get("bp"), "\n  bv:", d.get("bv"),
                  "\n  op:", d.get("op"), "\n  ov:", d.get("ov"))

        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
