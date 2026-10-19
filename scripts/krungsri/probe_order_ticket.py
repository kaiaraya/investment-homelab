# -*- coding: utf-8 -*-
"""STEP 1.1 probe — TradeMan Order Ticket DOM (read-only, headed, never submits).

Mirrors ``scripts/krungsri/probe_vieworder_actions.py``. Opens a HEADED Chromium
with the saved broker session and dumps the 7 order-ticket DOM items from
TASK-loop1-7 §1.1 into ``docs/artifacts/``:

  1. Symbol box element (div.bg-[#2B313A] under the "Symbol" label) + innerText + outerHTML
  2. Clicking the holdings row ``BCPG`` -> does the ticket symbol change? (root-cause check)
  3. Clicking the symbol box -> does the search modal (``.v-overlay--active``) open,
     with a ``Stock`` filter and a search input?
  4. Typing ``BCPG`` in the modal -> is there an exact match, and does clicking it
     close the modal and set the ticket symbol to ``BCPG``?
  5. Side buttons ``Buy / Sell / Short / Cover`` — is ``span:text-is('COVER')`` present?
  6. ``input[id$='-order-volume']`` / ``input[id$='-order-price']`` placeholder + value
  7. ``#send_order__btn`` present (and confirm we did NOT click it / read ``#pin``)

NEVER clicks Send/Confirm and never enters a PIN. Requires a live logged-in
TradeMan session (human OTP); otherwise the page redirects to /SignIn and every
item reports "not found".
"""
import asyncio
import json
import os
from datetime import datetime

from playwright.async_api import async_playwright

from app.core.config import settings

OUT_DIR = "docs/artifacts"
os.makedirs(OUT_DIR, exist_ok=True)

SYMBOL = "BCPG"
PORTFOLIO_URL = "https://trademan.in.th/Portfolio"

# JS snippet that locates the order-ticket symbol box (same predicate as the
# driver's Tier 3 Anti-DW assertion) and returns {innerText, outerHTML}.
_SYMBOL_BOX_JS = """() => {
    const el = Array.from(document.querySelectorAll("div")).find(d =>
        d.className && d.className.includes("bg-[#2B313A]") &&
        d.parentElement && d.parentElement.innerText.includes("Symbol")
    );
    return el ? {innerText: el.innerText.trim(), outerHTML: el.outerHTML.slice(0, 800)} : null;
}"""

# Tier 1 JS: click the <td> whose text is exactly the target symbol.
_TIER1_CLICK_JS = """(targetSym) => {
    const allTds = Array.from(document.querySelectorAll("td"));
    const targetTd = allTds.find(td => td.innerText && td.innerText.trim() === targetSym);
    if (targetTd) { targetTd.click(); return true; }
    return false;
}"""


async def main():
    pw = await async_playwright().start()
    args = {"headless": False, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
        args["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    browser = await pw.chromium.launch(**args)
    ctx = await browser.new_context(
        storage_state=settings.SESSION_STATE_PATH,
        viewport={"width": 1400, "height": 950},
    )
    page = await ctx.new_page()

    await page.goto(PORTFOLIO_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(6000)

    artifact = {
        "probe": "probe_order_ticket",
        "symbol": SYMBOL,
        "url": page.url,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "items": {},
    }

    # --- 1. Symbol box (initial) ------------------------------------------------
    artifact["items"]["1_symbol_box"] = await page.evaluate(_SYMBOL_BOX_JS)

    # --- 2. Holdings-row click -> does the ticket symbol change? ----------------
    before = await page.evaluate(_SYMBOL_BOX_JS)
    table_clicked = await page.evaluate(_TIER1_CLICK_JS, SYMBOL)
    await page.wait_for_timeout(1200)
    after = await page.evaluate(_SYMBOL_BOX_JS)
    artifact["items"]["2_holdings_row_click"] = {
        "table_clicked": table_clicked,
        "before": (before or {}).get("innerText"),
        "after": (after or {}).get("innerText"),
        "changed": bool(before and after and before.get("innerText") != after.get("innerText")),
    }

    # --- 3. Click symbol box -> search modal open? Stock filter? input? ---------
    modal_open = False
    modal_state = {}
    try:
        sym_box = page.locator(
            "div:has-text('Symbol') + div, .col-span-3.bg-\\[\\#2B313A\\].cursor-pointer"
        ).first
        if await sym_box.is_visible():
            await sym_box.click()
            await page.wait_for_timeout(800)
    except Exception as e:
        modal_state["sym_box_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    modal_state["modal_open"] = await page.evaluate(
        "() => !!document.querySelector('.v-overlay--active')"
    )
    modal_state["stock_filter_present"] = await page.evaluate(
        """() => {
            const o = document.querySelector('.v-overlay--active');
            if (!o) return false;
            return Array.from(o.querySelectorAll('button, div')).some(
                el => (el.innerText || '').trim() === 'Stock');
        }"""
    )
    modal_state["search_input_present"] = await page.evaluate(
        "() => !!document.querySelector('.v-overlay--active input')"
    )
    artifact["items"]["3_search_modal_open"] = modal_state

    # --- 4. Type symbol in modal -> exact match -> click -> ticket changes? -----
    exact_found = False
    exact_clicked = False
    symbol_after_modal = None
    try:
        search_inp = page.locator(".v-overlay--active input").first
        if await search_inp.is_visible():
            await search_inp.fill(SYMBOL)
            await page.wait_for_timeout(1200)
            exact_found = await page.evaluate(
                """(targetSym) => {
                    const overlay = document.querySelector('.v-overlay--active');
                    if (!overlay) return false;
                    const items = Array.from(overlay.querySelectorAll('*'));
                    return items.some(el => el.innerText && el.innerText.trim() === targetSym
                        && el.children.length === 0);
                }""",
                SYMBOL,
            )
            exact_clicked = await page.evaluate(
                """(targetSym) => {
                    const overlay = document.querySelector('.v-overlay--active');
                    if (!overlay) return false;
                    const items = Array.from(overlay.querySelectorAll('*'));
                    const match = items.find(el => el.innerText && el.innerText.trim() === targetSym
                        && el.children.length === 0);
                    if (match) { match.click(); return true; }
                    return false;
                }""",
                SYMBOL,
            )
            await page.wait_for_timeout(1200)
            symbol_after_modal = await page.evaluate(_SYMBOL_BOX_JS)
    except Exception as e:
        artifact["items"]["4_exact_match_error"] = f"{type(e).__name__}: {str(e)[:160]}"

    artifact["items"]["4_modal_exact_match"] = {
        "exact_found": exact_found,
        "exact_clicked": exact_clicked,
        "modal_still_open": await page.evaluate(
            "() => !!document.querySelector('.v-overlay--active')"
        ),
        "symbol_box_after": (symbol_after_modal or {}).get("innerText"),
    }

    # --- 5. Side buttons Buy/Sell/Short/Cover -----------------------------------
    artifact["items"]["5_side_buttons"] = await page.evaluate(
        """() => {
            const out = {};
            ['BUY', 'SELL', 'SHORT', 'COVER'].forEach(side => {
                const n = Array.from(document.querySelectorAll('span'))
                    .filter(sp => (sp.innerText || '').trim() === side).length;
                out[side] = n;
            });
            return out;
        }"""
    )

    # --- 6. Volume / Price inputs -----------------------------------------------
    artifact["items"]["6_volume_price_inputs"] = await page.evaluate(
        """() => {
            const grab = (sel) => {
                const el = document.querySelector(sel);
                return el ? {
                    present: true,
                    placeholder: el.getAttribute('placeholder'),
                    value: (el.value || ''),
                    id: el.id,
                } : {present: false};
            };
            return {
                volume: grab("input[id$='-order-volume']"),
                price: grab("input[id$='-order-price']"),
            };
        }"""
    )

    # --- 7. Send button (presence only — we must NOT click it) ------------------
    artifact["items"]["7_send_order_btn"] = {
        "send_order__btn_present": await page.evaluate(
            "() => !!document.getElementById('send_order__btn')"
        ),
        "pin_not_checked": (
            "Order Confirm modal (and its #pin input) was NOT opened: "
            "reading it requires clicking Send, which this probe forbids."
        ),
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = f"{OUT_DIR}/probe_order_ticket_{ts}.json"
    html_path = f"{OUT_DIR}/probe_order_ticket_{ts}.html"
    shot_path = f"{OUT_DIR}/probe_order_ticket_{ts}.png"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, ensure_ascii=False, indent=2)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(await page.content())
    await page.screenshot(path=shot_path, full_page=True)

    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    print("SAVED:", json_path, html_path, shot_path)

    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
