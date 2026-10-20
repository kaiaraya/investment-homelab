# -*- coding: utf-8 -*-
"""Shared CDP client & tab resolver for the broker session daemons (KSS + Liberator).

Connects to a running Chrome instance via Chrome DevTools Protocol (CDP)
without launching a new browser or triggering duplicate logins/OTPs.
"""
import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

logger = logging.getLogger("broker_cdp_client")

# Broker slug -> default CDP port.
BROKER_CDP_PORTS = {"kss": 9333, "liberator": 9334}

# Per-broker target-tab keyword maps (url substring / title substring).
# "url_any" matches the URL; "title_any" matches the page title; "url_not" excludes.
TARGET_MAPS = {
    "kss": {
        "streaming": {"url_any": ["streamingpage", "settrade"], "title_any": ["streaming"]},
        "sso": {"url_any": ["member", "krungsri", "start_sso", "login"], "url_not": ["settrade"]},
        "sbl": {"url_any": ["sbl", "borrow"], "title_any": ["sbl"]},
    },
    "liberator": {
        "portfolio": {"url_any": ["/portfolio"], "title_any": ["portfolio"]},
        "trade": {"url_any": ["/trade", "/order"], "title_any": ["trade & order"]},
        "market": {"url_any": ["/market", "/quote"], "title_any": ["market overview"]},
    },
}


def cdp_url_for(broker: str, port: Optional[int] = None) -> str:
    p = port or BROKER_CDP_PORTS[broker]
    return f"http://127.0.0.1:{p}"


def is_cdp_available(cdp_url: str, timeout: float = 2.0) -> bool:
    """Check if the Chrome CDP endpoint is responding."""
    endpoint = f"{cdp_url.rstrip('/')}/json/version"
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "Broker-Probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            return "webSocketDebuggerUrl" in data or "Browser" in data
    except (URLError, OSError, TimeoutError, ValueError):
        return False


async def connect_cdp(cdp_url: str, broker: str = "") -> Tuple[Playwright, Browser, BrowserContext]:
    """Connect to an existing Chrome session over CDP."""
    if not is_cdp_available(cdp_url):
        raise ConnectionError(
            f"Chrome CDP is not running at {cdp_url}. "
            f"Please run 'python scripts/broker_probe.py --broker {broker or '?'} start-session' first."
        )
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError("No active browser context found on CDP connection.")
    ctx = browser.contexts[0]
    return pw, browser, ctx


def _target_matches(spec: Dict[str, Any], url: str, title: str) -> bool:
    url_not = spec.get("url_not", [])
    if url_not and any(k in url for k in url_not):
        return False
    if any(k in url for k in spec.get("url_any", [])):
        return True
    if any(k in title for k in spec.get("title_any", [])):
        return True
    return False


async def resolve_target_tab(ctx: BrowserContext, target: str, broker: str) -> Optional[Page]:
    """Find a page/tab matching the broker's target (e.g. kss 'streaming' / liberator 'trade')."""
    target_clean = (target or "").strip().lower()
    tmap = TARGET_MAPS.get(broker, {})

    for page in ctx.pages:
        url = page.url.lower()
        if target_clean == "any":
            return page
        title = ""
        try:
            title = (await page.title()).lower()
        except Exception:
            pass
        spec = tmap.get(target_clean)
        if spec and _target_matches(spec, url, title):
            return page

    # Broker-specific fallbacks
    if broker == "kss" and target_clean in ("sbl", "margin"):
        # No dedicated SBL page -> fall back to the Streaming page (Short/Cover radios live there).
        for page in ctx.pages:
            url = page.url.lower()
            if "streamingpage" in url or "settrade" in url:
                return page
    elif broker == "liberator":
        for page in ctx.pages:
            if "liberator.co.th" in page.url.lower():
                return page

    return ctx.pages[0] if ctx.pages else None


async def inspect_dom_elements(
    page: Page,
    scope_selector: Optional[str] = None,
    keyword_filter: Optional[str] = None,
    max_elements: int = 100,
) -> List[Dict[str, Any]]:
    """Scoped extraction of interactive and structural DOM elements for probing."""
    js_extract = """([scope, kw, limit]) => {
        let root = document;
        if (scope) {
            const found = document.querySelector(scope);
            if (found) root = found;
        }

        const candidates = root.querySelectorAll(
            'button, input, select, textarea, a, [role="button"], [role="tab"], [role="menuitem"], ' +
            'span.outline-none, span[tabindex], div[tabindex], table, th, td, [data-testid], [id], ' +
            '[class*="order"], [class*="portfolio"], [class*="balance"]'
        );

        const results = [];
        // Comma-separated keywords are OR'd (e.g. "account,order,change").
        const regex = kw ? new RegExp(String(kw).split(',').map(s => s.trim()).filter(Boolean).join('|'), 'i') : null;

        for (let i = 0; i < candidates.length; i++) {
            if (results.length >= limit) break;
            const el = candidates[i];
            const text = (el.innerText || el.value || el.placeholder || '').trim();
            const tag = el.tagName.toLowerCase();
            const id = el.id || '';
            const cls = (el.className || '').toString().slice(0, 80);
            const role = el.getAttribute('role') || '';
            const testId = el.getAttribute('data-testid') || '';
            const name = el.getAttribute('name') || '';
            const type = el.getAttribute('type') || '';
            const ariaLabel = el.getAttribute('aria-label') || '';

            const combined = `${tag} ${id} ${cls} ${role} ${testId} ${name} ${ariaLabel} ${text}`;
            if (regex && !regex.test(combined)) {
                continue;
            }

            const rect = el.getBoundingClientRect();
            const isVisible = !!(rect.width && rect.height && window.getComputedStyle(el).display !== 'none');

            let candidateSel = '';
            if (id) {
                candidateSel = `#${id}`;
            } else if (testId) {
                candidateSel = `[data-testid="${testId}"]`;
            } else if (name) {
                candidateSel = `${tag}[name="${name}"]`;
            } else if (ariaLabel) {
                candidateSel = `${tag}[aria-label="${ariaLabel}"]`;
            } else if (text && text.length < 30 && ['button', 'a', 'span'].includes(tag)) {
                candidateSel = `${tag}:has-text("${text.replace(/"/g, '\\\\"')}")`;
            } else if (cls) {
                candidateSel = `${tag}.${cls.split(' ').filter(Boolean).slice(0, 2).join('.')}`;
            } else {
                candidateSel = tag;
            }

            results.push({
                tag: tag,
                id: id,
                name: name,
                type: type,
                role: role,
                classes: cls,
                aria_label: ariaLabel,
                test_id: testId,
                text: text.slice(0, 100),
                is_visible: isVisible,
                suggested_selector: candidateSel,
                outer_html_sample: el.outerHTML.slice(0, 250)
            });
        }
        return results;
    }"""
    return await page.evaluate(js_extract, [scope_selector, keyword_filter, max_elements])


async def inspect_sbl_application(page: Page) -> Dict[str, Any]:
    """Specialized extraction for Krungsri SBL Real Time (/sblweb/MainSBL.aspx).

    Extracts: active inventory / borrowable stocks & volumes, Purchasing Power &
    Borrow form selectors, active borrow contracts & return buttons.
    """
    js_sbl = """() => {
        const clean = s => (s || '').trim();

        let pp = '';
        const ppEl = document.querySelector('#ctl00_MainCenter_ctl00_MainCenter_pnlBorrowPanel') || document.body;
        if (ppEl) {
            const ppMatch = ppEl.innerText.match(/PP\\s*=\\s*([0-9,.]+)/i);
            if (ppMatch) pp = ppMatch[1];
        }
        const cusCodeEl = document.querySelector('#ctl00_MainCenter_txtCusCode, #ctl00_MainCenter_txSearchCode');
        const cusNameEl = document.querySelector('#ctl00_MainCenter_lbCusName');

        const borrowForm = {
            purchasing_power: pp,
            customer_code: cusCodeEl ? (cusCodeEl.value || cusCodeEl.innerText) : '',
            customer_name: cusNameEl ? cusNameEl.innerText : '',
            symbol_input_selector: '#ctl00_MainCenter_txtSymbol',
            symbol_input_exists: !!document.querySelector('#ctl00_MainCenter_txtSymbol'),
            qty_input_selector: '#ctl00_MainCenter_txtQty',
            qty_input_exists: !!document.querySelector('#ctl00_MainCenter_txtQty'),
            borrow_button_selector: '#MainCenter_lbBorrow',
            borrow_button_exists: !!document.querySelector('#MainCenter_lbBorrow')
        };

        const navTabs = [];
        ['#MainCenter_lbSet50', '#MainCenter_lbSet100', '#MainCenter_lbNewSec', '#MainCenter_lbXD', '#MainCenter_lbRefresh'].forEach(sel => {
            const el = document.querySelector(sel);
            if (el) {
                navTabs.push({ selector: sel, text: clean(el.innerText), visible: el.offsetParent !== null });
            }
        });

        const inventory = [];
        document.querySelectorAll('table tr').forEach(row => {
            const cells = Array.from(row.querySelectorAll('td')).map(td => clean(td.innerText));
            if (cells.length >= 4 && cells[0].length >= 2 && cells[0].length <= 10 && !/symbol|หุ้น|ลำดับ/i.test(cells[0])) {
                const volumeClean = cells[2].replace(/,/g, '');
                if (/^\\d+$/.test(volumeClean)) {
                    inventory.push({
                        symbol: cells[0],
                        fee: cells[1],
                        available_volume: cells[2],
                        im_rate: cells[3]
                    });
                }
            }
        });

        const activeContracts = [];
        const transTable = document.querySelector('#ctl00_MainCenter_rgTrans_ctl00, table[id*="rgTrans"]');
        if (transTable) {
            transTable.querySelectorAll('tr').forEach(row => {
                const cells = Array.from(row.querySelectorAll('td')).map(td => clean(td.innerText));
                const returnBtn = row.querySelector("a[id*='RadReturn'], button:has-text('คืน'), a:has-text('คืน')");
                if (cells.length >= 6 && cells[0].startsWith('B')) {
                    activeContracts.push({
                        ref_no: cells[0],
                        tran_date: cells[1],
                        symbol: cells[3],
                        quantity: cells[5],
                        has_return_button: !!returnBtn,
                        return_button_id: returnBtn ? returnBtn.id : null
                    });
                }
            });
        }

        return {
            page_title: document.title,
            current_url: location.href,
            is_sbl_app: location.href.toLowerCase().includes('sbl') || !!document.querySelector('#MainCenter_lbBorrow'),
            borrow_form: borrowForm,
            navigation_tabs: navTabs,
            inventory_sample: inventory.slice(0, 30),
            total_inventory_stocks_detected: inventory.length,
            active_contracts_for_return: activeContracts
        };
    }"""
    return await page.evaluate(js_sbl)
