"""probe_liberator_board_symbol.py — D3 evidence probe (headed, HITL).

Purpose: prove on the LIVE Liberator board HOW to know the Bid/Offer quote currently
shown belongs to the symbol we asked for. Captures two independent proofs:
  (1) DOM  — which element displays the selected symbol (candidate selector for the gate)
  (2) NET  — the XHR/fetch JSON for the quote (symbol field + bid1/offer1/last shape)

Run:  .venv/bin/python scripts/liberator/probe_liberator_board_symbol.py [SYMBOL]
Session: reuses data/liberator_session.json (no OTP).
READ-ONLY: fills the buy/sell footer + Enter (quote lookup only) — NEVER submits an order.
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

SYMBOL = (sys.argv[1] if len(sys.argv) > 1 else "BCH").upper()
STATE = "data/liberator_session.json"
OUT = "data/screenshots"
RELEVANT = ("stock", "bid", "offer", "quote", "price", "info", "vb/")


async def main():
    with open(STATE) as f:
        cookies = json.load(f).get("cookies", [])
    net = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"],
        )
        ctx = await browser.new_context(
            no_viewport=True,
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        async def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
            except Exception:
                return
            try:
                body = await resp.text()
            except Exception as e:  # noqa: BLE001
                body = f"<body err: {e}>"
            net.append({
                "method": resp.request.method,
                "status": resp.status,
                "url": resp.url,
                "post": (resp.request.post_data or "")[:800],
                "body": body[:8000],
            })

        page.on("response", on_response)

        print(f"=== NAV Portfolio (symbol={SYMBOL}) ===")
        await page.goto("https://webtrade.liberator.co.th/Portfolio",
                        wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        print("URL:", page.url)

        sel = "#SearchSymbolList-setBuySellFooter"
        inp = await page.wait_for_selector(sel, timeout=8000)
        if inp is None:
            print(f"!! {sel} not found")
            await browser.close()
            return
        await inp.click()
        await inp.fill("")
        await inp.fill(SYMBOL)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3500)

        os.makedirs(OUT, exist_ok=True)
        await page.screenshot(path=f"{OUT}/lib_board_symbol_{SYMBOL}.png")

        dom = await page.evaluate("""(sym) => {
            const path = (el) => {
                const parts = [];
                let guard = 0;
                while (el && el.nodeType === 1 && parts.length < 6 && guard++ < 10) {
                    let s = el.tagName.toLowerCase();
                    if (el.id) { parts.unshift(s + '#' + el.id); break; }
                    if (el.className && typeof el.className === 'string' && el.className.trim()) {
                        s += '.' + el.className.trim().split(/\\s+/).join('.');
                    }
                    const p = el.parentElement;
                    if (p) { const i = Array.from(p.children).indexOf(el); s += ':nth-child(' + (i + 1) + ')'; }
                    parts.unshift(s);
                    el = el.parentElement;
                }
                return parts.join(' > ');
            };
            const hits = [];
            for (const el of document.querySelectorAll('body *')) {
                const t = (el.innerText || '').trim();
                if (!t || t.length > 40) continue;
                if (t === sym || t.toUpperCase() === sym) {
                    hits.push({
                        tag: el.tagName,
                        id: el.id,
                        cls: (typeof el.className === 'string' ? el.className : ''),
                        text: t,
                        cssPath: path(el),
                        outer: el.outerHTML.slice(0, 300),
                    });
                }
            }
            const fi = document.querySelector('#SearchSymbolList-setBuySellFooter');
            let footerForm = null;
            if (fi) {
                let n = fi;
                for (let i = 0; i < 8 && n && n.parentElement; i++) {
                    n = n.parentElement;
                    if (n.tagName === 'FORM' || /buysell|order|footer/i.test(n.className || '')) { footerForm = n; break; }
                }
                if (!footerForm) footerForm = fi.closest('div, section');
            }
            const depthHeaders = [];
            for (const th of document.querySelectorAll('th, div[role="columnheader"]')) {
                const t = (th.innerText || '').trim();
                if (/bid|offer|\\u0e23\\u0e31\\u0e1a\\u0e0b\\u0e37\\u0e49\\u0e2d|\\u0e02\\u0e32\\u0e22|\\u0e40\\u0e2a\\u0e19\\u0e2d/i.test(t)) depthHeaders.push(t.slice(0, 60));
            }
            return {
                title: document.title,
                input_value: fi ? fi.value : null,
                hits: hits.slice(0, 30),
                footer_html: footerForm ? footerForm.outerHTML.slice(0, 4000) : null,
                depth_headers: depthHeaders.slice(0, 25),
            };
        }""", SYMBOL)

        print("\n=== DOM: elements exactly showing the symbol ===")
        print("input_value:", dom["input_value"])
        for h in dom["hits"]:
            print(json.dumps(h, ensure_ascii=False))
        print("\n=== depth headers:", dom["depth_headers"])
        print("\n=== footer form html (truncated) ===\n" + (dom["footer_html"] or "<none>"))
        with open(f"/tmp/lib_board_dom_{SYMBOL}.json", "w") as f:
            json.dump(dom, f, ensure_ascii=False, indent=2)

        print("\n=== NET (xhr/fetch) ===")
        for n in net:
            tag = "RELEVANT" if any(k in n["url"].lower() for k in RELEVANT) else "        "
            print(f"[{tag}] {n['method']} {n['status']} {n['url']}")
            if tag == "RELEVANT":
                if n["post"]:
                    print("   POST:", n["post"][:400])
                print("   BODY:", n["body"][:1200].replace("\n", " "))
        with open(f"/tmp/lib_board_net_{SYMBOL}.json", "w") as f:
            json.dump(net, f, ensure_ascii=False, indent=2)
        print(f"\nSaved: /tmp/lib_board_dom_{SYMBOL}.json /tmp/lib_board_net_{SYMBOL}.json")
        print(f"Screenshot: {OUT}/lib_board_symbol_{SYMBOL}.png")
        print("(browser stays open 6s — look at the screen)")
        await page.wait_for_timeout(6000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
