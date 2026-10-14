"""CLI-RCA-011 (P2a) — read-only probe of the TradeMan /Portfolio "Account Info" panel.

Purpose: capture the *shape* of every label/value in the portfolio summary and in the
expanded Account Info panel so P2b can pin the real selectors. A human runs this while the
market is open; it never logs in, never fires OTP, never touches an order, and never writes
session state (Invariant 8).

Safety contract
---------------
* read-only — ``new_context(storage_state=...)`` only; the storage state is never written back
* the only clicks allowed: the account dropdown (its toggle + an option) and the Account Info chevron
* output is shape-only via :func:`sanitize` — no money figure and no account number is written
* an expired session is reported to the human, who signs in by hand (no auto-login / OTP)

Usage (human, live):
    .venv/bin/python scripts/krungsri/probe_account_info.py
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

PORTFOLIO_URL = "https://trademan.in.th/Portfolio"

#: The two allowed click targets (runbook: learned_workflows/krungsri/trademan_portfolio_dom.md).
ACCOUNT_OPTION_SELECTOR = '#dropDownAccountPort div.absolute span:text-is("%s")'
#: P2b pins the real chevron — kept in one constant so live tuning touches a single line.
ACCOUNT_INFO_CHEVRON_SELECTOR = "button[aria-label*='Account Info' i], #accountInfoChevron"

#: Labels to look for — Thai and English (every label found is kept, not only these).
TARGET_LABELS = (
    "Trading A/C", "Credit Limit", "Line Available", "Excess Equity",
    "Margin Required", "%MM", "Cash Balance",
    "วงเงิน", "วงเงินคงเหลือ", "หลักประกัน", "เงินสดคงเหลือ", "มูลค่าหลักประกัน",
)

_NUM_RE = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_PCT_RE = re.compile(r"^-?[\d,]+(?:\.\d+)?%$")
_EMPTY_TOKENS = {"", "-", "--", "–", "—", "n/a", "N/A"}

#: F2: every digit run worth hiding — comma groups and decimals included.
_NUM_RUN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
#: F2: a string that is really a *value*, not a label (money / percent / negative / parentheses /
#: currency). Anchored on a digit so a legitimate label such as ``%MM`` is never dropped.
_VALUE_LIKE_RE = re.compile(
    r"^[+-]?\s*(?:฿|THB|USD|\$)?\s*\(?\s*\d[\d,]*(?:\.\d+)?\s*\)?\s*(?:%|฿|THB|USD|\$)?$",
    re.IGNORECASE,
)


def _redact(text: Any) -> str:
    """Replace every figure/account-number-like digit run (comma groups included) with ``<num>``.

    F2: a plain ``\\d{6,}`` never matched ``123,456.78``, so a money figure could reach the file
    as the ``label`` of a leaf element. Now any run of 4+ digits — commas stripped, decimals
    ignored — is hidden, which catches both ``3024959`` and ``250,000.00``.
    """
    def _swap(match: "re.Match[str]") -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return "<num>" if len(digits) >= 4 else match.group(0)

    return _NUM_RUN_RE.sub(_swap, str(text or "").strip())


def _is_value_like(text: Any) -> bool:
    """True when ``text`` is a value rather than a label — e.g. ``123,456.78`` / ``(1,000.00)``.

    A leaf whose visible text is a figure is a *value*: the row is dropped, never redacted.
    ``%MM`` (a real label in :data:`TARGET_LABELS`) deliberately does not match.
    """
    return bool(_VALUE_LIKE_RE.match(str(text or "").strip()))


def _value_shape(raw: Any) -> str:
    """Classify a value WITHOUT echoing it — one of the five agreed shapes."""
    txt = str(raw or "").strip()
    if txt in _EMPTY_TOKENS:
        return "empty"
    if _PCT_RE.match(txt):
        return "#.##%"
    if _NUM_RE.match(txt):
        return "-#,###.##" if txt.startswith("-") else "#,###.##"
    return "text"


def sanitize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reduce raw probe rows to ``{label, selector_path, value_path, value_shape}`` — shape only.

    ``value_shape`` is one of ``"#,###.##"`` / ``"-#,###.##"`` / ``"#.##%"`` / ``"empty"`` /
    ``"text"``. A row without a ``label`` — or whose ``label`` is really a figure (F2) — is
    dropped; a missing ``value_path`` becomes ``""`` (F3); malformed input never raises.
    """
    out: List[Dict[str, Any]] = []
    for item in items or []:
        row = item or {}
        raw_label = str(row.get("label") or "").strip()
        if _is_value_like(raw_label):       # F2: a figure in the label slot is a value, not a label
            continue
        label = _redact(raw_label)
        if not label:
            continue
        out.append({
            "label": label,
            "selector_path": _redact(row.get("selector_path")),
            "value_path": _redact(row.get("value_path")),
            "value_shape": _value_shape(row.get("value")),
        })
    return out


#: Dump every leaf element's label + its sibling text (shape-only via ``sanitize``).
#: F3: each row also carries the real CSS path of the label (``selector_path``) and of the sibling
#: that holds the value (``value_path``), so P2b can map a label straight onto a selector.
_PANEL_JS = """() => {
    const cssPath = (el) => {
        const parts = [];
        let node = el;
        for (let depth = 0; node && depth < 6; depth += 1) {
            if (node.id) { parts.unshift('#' + node.id); break; }
            let part = (node.tagName || '').toLowerCase();
            const cls = Array.from(node.classList || [])
                .filter((c) => c && !/[0-9:]/.test(c)).slice(0, 2);
            if (cls.length) part += '.' + cls.join('.');
            const parent = node.parentElement;
            if (parent) {
                const same = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
                if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(node) + 1) + ')';
            }
            parts.unshift(part);
            node = parent;
        }
        return parts.join(' > ');
    };
    const rows = [];
    document.querySelectorAll('span, div, td, p').forEach((el) => {
        const label = (el.innerText || '').trim();
        if (!label || label.length > 60 || el.children.length > 0) return;
        const parent = el.parentElement;
        let value = parent ? (parent.innerText || '').trim() : '';
        if (value.startsWith(label)) value = value.slice(label.length).trim();
        const sib = el.nextElementSibling;
        const sibText = sib ? (sib.innerText || '').trim() : '';
        rows.push({
            label: label,
            value: value.slice(0, 40),
            selector_path: cssPath(el),
            value_path: sibText ? cssPath(sib) : '',
        });
    });
    return rows;
}"""


def _wait_enter(prompt: str) -> None:
    input(f"\n[Enter] {prompt}")


async def main() -> None:
    import argparse
    import json
    import os
    from datetime import datetime

    from app.core.config import settings

    parser = argparse.ArgumentParser(description="Read-only TradeMan Account Info probe (CLI-RCA-011).")
    parser.add_argument("--out-dir", default="data/probe_out")
    parser.add_argument("--account-type", choices=["CASH", "MARGIN", "BOTH"], default="BOTH")
    args = parser.parse_args()

    # Imported inside main() so unit tests can import this module without a browser runtime.
    from playwright.async_api import async_playwright
    from app.browser.popup_manager import popup_manager

    targets = {
        "CASH": settings.TRADEMAN_ACCOUNT_NO_CASH,
        "MARGIN": settings.TRADEMAN_ACCOUNT_NO_MARGIN,
    }
    if args.account_type != "BOTH":
        targets = {args.account_type: targets[args.account_type]}
    targets = {k: v for k, v in targets.items() if v}

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            executable_path=settings.PLAYWRIGHT_CHROME_EXECUTABLE or None,
        )
        # READ-ONLY session reuse (Invariant 8): never capture/write the storage state back.
        context = await browser.new_context(storage_state=settings.SESSION_STATE_PATH)
        page = await context.new_page()
        await page.goto(PORTFOLIO_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await popup_manager.dismiss_popups(page)

        if any(tok in (page.url or "").lower() for tok in ("signin", "login")):
            _wait_enter("session หมดอายุ — login เองในหน้าต่างนี้ (ห้าม OTP อัตโนมัติ) แล้วกด Enter")
            await page.wait_for_timeout(1500)

        for acc_type, acc_no in targets.items():
            print(f"\n=== {acc_type} ===")
            _wait_enter(f"พร้อมอ่านบัญชี {acc_type} แล้วหรือยัง (dropdown ควรชี้ที่บัญชีนี้)")
            await page.keyboard.press("Escape")          # F1: close any open dropdown without clicking
            await page.click("#dropDownAccountPort")     # F4: options render only once this is open
            await page.wait_for_timeout(500)
            option = page.locator(ACCOUNT_OPTION_SELECTOR % acc_no)
            if await option.count():
                await option.first.click()               # the ONLY account-selecting click
                await page.wait_for_timeout(1200)
            else:
                await page.keyboard.press("Escape")
                print(f"  ! ไม่พบ dropdown option ของ {acc_type} — สลับบัญชีเองแล้วกด Enter")
                _wait_enter(f"สลับ dropdown ให้ชี้ที่ {acc_type} เองแล้วกด Enter")

            collapsed = sanitize(await page.evaluate(_PANEL_JS))

            _wait_enter(f"dump แถบล่างของ {acc_type} แล้ว — กด Enter เพื่อคลิก chevron ขยาย Account Info")
            try:
                await page.click(ACCOUNT_INFO_CHEVRON_SELECTOR, timeout=5000)
                await page.wait_for_timeout(1200)
            except Exception as exc:                     # noqa: BLE001 — probe is best-effort
                print(f"  ! คลิก chevron ไม่ได้ ({exc}) — คลิกเองในหน้าต่างแล้วกด Enter")
                _wait_enter("คลิก chevron เองแล้วกด Enter")
            expanded = sanitize(await page.evaluate(_PANEL_JS))

            path = os.path.join(args.out_dir, f"account_info_{acc_type}_{stamp}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    {"account_type": acc_type, "targets": list(TARGET_LABELS),
                     "collapsed": collapsed, "expanded": expanded},
                    fh, ensure_ascii=False, indent=2,
                )
            print(f"  → เขียนผลแล้ว: {path}  (collapsed={len(collapsed)} expanded={len(expanded)} rows)")

        _wait_enter("เสร็จแล้ว — กด Enter เพื่อปิดเบราว์เซอร์")
        await browser.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
