"""live_check_quote_gate.py — real-evidence check for LIB-RCA-020 (READ-ONLY, headless).

Drives the PRODUCTION ``LiberatorDriver.get_market_bid_offer`` against the live broker with
the saved session cookies (no OTP, no order, no board interaction) and asserts the two
outcomes the D3 hardening promises:

  * ``BCH``  — a real holding     -> success=True / source="liberator_api" with numbers
  * ``ZZZZ`` — not a real symbol  -> QUOTE_UNAVAILABLE, every number None (fail-closed)

Exit code 0 = both promises hold live; 1 = something drifted (re-run the probe scripts).
Run: .venv/bin/python scripts/liberator/live_check_quote_gate.py
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.brokers.liberator.driver import LiberatorDriver  # noqa: E402

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
GOOD, BAD = "BCH", "ZZZZ"


def _line(sym, res):
    return (f"[{sym}] success={res['success']} status={res['status']} source={res['source']} "
            f"bid1={res['bid_1']} offer1={res['offer_1']} last={res['last']} "
            f"ceiling={res['ceiling']} floor={res['floor']} err={res.get('error')}")


async def main() -> int:
    cookies = json.load(open("data/liberator_session.json")).get("cookies", [])
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox"])
        ctx = await browser.new_context(user_agent=UA)
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()
        await page.goto("https://webtrade.liberator.co.th/Portfolio",
                        wait_until="domcontentloaded", timeout=20000)

        drv = LiberatorDriver()
        drv.page = page                       # no login: the cookie jar is the session
        quotes = {sym: await drv.get_market_bid_offer(sym) for sym in (GOOD, BAD)}
        await browser.close()

    for sym, res in quotes.items():
        print(_line(sym, res))

    good, bad = quotes[GOOD], quotes[BAD]
    checks = {
        "BCH is symbol-verified": (good["success"] is True and good["status"] == "OK"
                                   and good["source"] == "liberator_api"
                                   and good["symbol"] == GOOD),
        "BCH has a readable Bid/Offer/Last": any(good[k] is not None for k in ("bid_1", "offer_1", "last")),
        "ZZZZ fails closed": (bad["success"] is False
                              and bad["status"] == LiberatorDriver.QUOTE_UNAVAILABLE
                              and bad["source"] == "unavailable"),
        "ZZZZ leaks no number": all(bad[k] is None for k in ("bid_1", "offer_1", "last")),
    }
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks.items() if not ok]
    print("RESULT:", "PASS" if not failed else f"FAIL ({', '.join(failed)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
