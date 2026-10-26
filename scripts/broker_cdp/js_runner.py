#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JS snippet runner for persistent CDP daemon sessions (Streaming 9333 / Liberator 9334).

Executes pre-authored bookmarklets or raw JS strings in the context of the live broker tab
via Playwright / Chrome DevTools Protocol without re-logging in or launching new browsers.
"""
import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, Optional

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402
from app.services.validator import validator  # noqa: E402

BOOKMARKLET_DIR = os.path.join(REPO, "data", "bookmarklets")


async def run_snippet(
    broker: str,
    snippet_name: Optional[str] = None,
    snippet_path: Optional[str] = None,
    raw_js: Optional[str] = None,
    target_kind: Optional[str] = None,
    timeout_s: float = 120.0,
    arg: Optional[Any] = None,
) -> Dict[str, Any]:
    code = ""
    if raw_js:
        code = raw_js
    elif snippet_path and os.path.exists(snippet_path):
        with open(snippet_path, "r", encoding="utf-8") as f:
            code = f.read()
    elif snippet_name:
        p = os.path.join(BOOKMARKLET_DIR, f"{snippet_name}.js")
        if not os.path.exists(p):
            p = os.path.join(BOOKMARKLET_DIR, snippet_name)
        if not os.path.exists(p):
            return {"success": False, "error": f"Snippet not found: {snippet_name} (checked {p})"}
        with open(p, "r", encoding="utf-8") as f:
            code = f.read()
    else:
        return {"success": False, "error": "No snippet or code provided"}

    broker_norm = "liberator" if broker in ("lib", "liberator") else "kss"
    if not target_kind:
        if snippet_name and "sbl" in snippet_name.lower():
            target_kind = "sbl"
        else:
            target_kind = "streaming" if broker_norm == "kss" else "portfolio"

    try:
        pw, browser, ctx = await connect_cdp(cdp_url_for(broker_norm), broker_norm)
    except Exception as ex:
        return {"success": False, "error": f"Failed to connect CDP for {broker_norm}: {ex}"}

    try:
        page = await resolve_target_tab(ctx, target_kind, broker_norm)
        if not page:
            page = ctx.pages[0] if ctx.pages else None
        if not page:
            return {"success": False, "error": f"No target page found for {broker_norm} ({target_kind})"}

        await page.bring_to_front()
        eval_str = code.strip()
        if arg is not None:
            if eval_str.endswith("()"):
                eval_str = eval_str[:-2] + f"({json.dumps(arg)})"
            else:
                eval_str = f"({eval_str})({json.dumps(arg)})"
        result = await asyncio.wait_for(page.evaluate(eval_str), timeout=timeout_s)
        return {"success": True, "data": result, "tab_url": page.url}
    except Exception as ex:
        return {"success": False, "error": f"Eval error: {type(ex).__name__}: {ex}"}
    finally:
        try:
            await browser.close()
            await pw.stop()
        except Exception:
            pass


async def get_quote_js(broker: str, symbol: str, timeout_s: float = 5.0) -> Dict[str, Any]:
    """Execute getQuote JS snippet via active CDP session and return normalized quote envelope.

    Returns a dict adhering to the _broker_quote contract with keys:
    {symbol, success, status, source, bid_1, offer_1, last, prior_close, ceiling, floor, board_lot, flag}
    """
    clean_sym = (symbol or "").strip().upper()
    if not clean_sym:
        return {
            "symbol": "",
            "success": False,
            "status": "QUOTE_UNAVAILABLE",
            "source": "unavailable",
            "error": "Blank symbol",
            "bid_1": None,
            "offer_1": None,
            "last": None,
            "prior_close": None,
            "ceiling": None,
            "floor": None,
            "board_lot": 100,
            "flag": None,
        }

    broker_key = "lib" if broker in ("lib", "liberator") else "kss"
    target_broker = "liberator" if broker_key == "lib" else "kss"
    source_name = "streaming_js" if broker_key == "kss" else "liberator_js"

    res = await run_snippet(
        broker=target_broker,
        snippet_name="quote",
        target_kind="streaming" if target_broker == "kss" else "portfolio",
        timeout_s=timeout_s,
        arg=clean_sym,
    )

    if not res.get("success"):
        return {
            "symbol": clean_sym,
            "success": False,
            "status": "QUOTE_UNAVAILABLE",
            "source": "unavailable",
            "error": res.get("error", "CDP eval failed"),
            "bid_1": None,
            "offer_1": None,
            "last": None,
            "prior_close": None,
            "ceiling": None,
            "floor": None,
            "board_lot": 100,
            "flag": None,
        }

    data = res.get("data") or {}
    if not isinstance(data, dict) or data.get("error"):
        err = data.get("error") if isinstance(data, dict) else "Invalid JS quote response"
        return {
            "symbol": clean_sym,
            "success": False,
            "status": "QUOTE_UNAVAILABLE",
            "source": "unavailable",
            "error": str(err),
            "bid_1": None,
            "offer_1": None,
            "last": None,
            "prior_close": None,
            "ceiling": None,
            "floor": None,
            "board_lot": 100,
            "flag": None,
        }

    def _to_float(v: Any) -> Optional[float]:
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    bid_1 = _to_float(data.get("bid"))
    offer_1 = _to_float(data.get("ask"))
    last = _to_float(data.get("last"))
    prior_close = _to_float(data.get("close"))
    ceiling = _to_float(data.get("ceiling"))
    floor = _to_float(data.get("floor"))

    if bid_1 is None and offer_1 is None and last is None:
        return {
            "symbol": clean_sym,
            "success": False,
            "status": "QUOTE_UNAVAILABLE",
            "source": "unavailable",
            "error": "No Bid/Offer/Last returned by JS quote",
            "bid_1": None,
            "offer_1": None,
            "last": None,
            "prior_close": prior_close,
            "ceiling": ceiling,
            "floor": floor,
            "board_lot": 100,
            "flag": None,
        }

    return {
        "symbol": clean_sym,
        "success": True,
        "status": "OK",
        "source": source_name,
        "bid_1": bid_1,
        "offer_1": offer_1,
        "last": last,
        "prior_close": prior_close,
        "ceiling": ceiling,
        "floor": floor,
        "board_lot": 100,
        "flag": None,
    }


def adjust_price_by_ticks(price: float, steps: int = 0) -> float:
    """Calculate next tick price using SET spread table rules."""
    return validator.get_next_tick(price, steps=steps)


def calculate_offset_price(
    quote: Dict[str, Any],
    side: str = "BUY",
    offset_mode: str = "passive",
    ticks: int = 0,
) -> float:
    """Calculate limit order price relative to market quote using tick offsets.

    - BUY/COVER:
        passive: Bid - abs(ticks) (or last - abs(ticks))
        aggressive: Ask + abs(ticks) (cross spread)
    - SELL/SHORT:
        passive: Ask + abs(ticks) (or last + abs(ticks))
        aggressive: Bid - abs(ticks) (cross spread)
    """
    clean_side = (side or "BUY").upper()
    bid = quote.get("bid_1") or quote.get("bid") or quote.get("last")
    ask = quote.get("offer_1") or quote.get("ask") or quote.get("last")
    last = quote.get("last") or bid or ask or 0.0

    if clean_side in ("BUY", "COVER"):
        base_price = (ask if offset_mode == "aggressive" else bid) or last
        step_dir = abs(ticks) if offset_mode == "aggressive" else -abs(ticks)
    else:
        base_price = (bid if offset_mode == "aggressive" else ask) or last
        step_dir = -abs(ticks) if offset_mode == "aggressive" else abs(ticks)

    return adjust_price_by_ticks(float(base_price), steps=step_dir)


async def trigger_stepper(broker: str, steps: int = 0, target_kind: Optional[str] = None) -> Dict[str, Any]:
    """Trigger DOM price stepper buttons (+ / -) in the active broker session via CDP."""
    if steps == 0:
        return {"success": True, "steps": 0, "message": "No steps to trigger"}

    broker_norm = "liberator" if broker in ("lib", "liberator") else "kss"
    snippet_code = f"""(() => {{{{ 
        const steps = {steps};
        const host = location.hostname;
        if (host.includes('liberator.co.th')) {{{{ 
            const popup = document.querySelector('#popup_price');
            if (!popup) return {{{{ success: false, reason: '#popup_price not open' }}}};
            const btn = steps > 0
                ? popup.querySelector('.bg-more-than')
                : popup.querySelector('.bg-less-than');
            if (!btn) return {{{{ success: false, reason: 'Stepper button not found in popup' }}}};
            for (let i = 0; i < Math.abs(steps); i++) {{{{ 
                btn.click();
            }}}}
            const input = document.querySelector('#price');
            return {{{{ success: true, steps, newPrice: input ? input.value : null }}}};
        }}}} else if (host.includes('settrade.com')) {{{{ 
            const container = document.querySelector('.z-index-smart-price-volume, .css-zxyhmd');
            if (!container) return {{{{ success: false, reason: 'Streaming stepper container not visible' }}}};
            const btn = steps > 0
                ? container.querySelector('.bg-color-gainer-100')
                : container.querySelector('.bg-color-loser-100');
            if (!btn) return {{{{ success: false, reason: 'Streaming stepper button not found' }}}};
            for (let i = 0; i < Math.abs(steps); i++) {{{{ 
                btn.click();
            }}}}
            const input = document.querySelector('input[name=\"price-input\"]');
            return {{{{ success: true, steps, newPrice: input ? input.value : null }}}};
        }}}}
        return {{{{ success: false, reason: 'Unsupported host: ' + host }}}};
    }} Zebra()""".replace(' Zebra', '')

    return await run_snippet(
        broker=broker_norm,
        raw_js=snippet_code,
        target_kind=target_kind,
        timeout_s=10.0,
    )


def main():
    parser = argparse.ArgumentParser(description="Execute JS snippets on active CDP tabs")
    parser.add_argument("--broker", required=True, choices=["kss", "liberator"], help="Target broker session")
    parser.add_argument("--snippet", help="Snippet name from data/bookmarklets (quote, orders, portfolio, balance, dom_dump, sbl_read)")
    parser.add_argument("--file", help="Path to .js file")
    parser.add_argument("--eval", help="Raw JS code string")
    parser.add_argument("--tab", help="Target tab hint (streaming, sbl, portfolio, orders)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Evaluation timeout seconds")
    args = parser.parse_args()

    res = asyncio.run(run_snippet(
        broker=args.broker,
        snippet_name=args.snippet,
        snippet_path=args.file,
        raw_js=args.eval,
        target_kind=args.tab,
        timeout_s=args.timeout
    ))
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
