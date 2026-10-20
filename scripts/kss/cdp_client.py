# -*- coding: utf-8 -*-
"""CDP Client & Tab Resolver for KSS Persistent Session.

Connects to a running Chrome instance via Chrome DevTools Protocol (CDP)
without launching a new browser or triggering duplicate logins/OTPs.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
import urllib.request

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

logger = logging.getLogger("kss_cdp_client")

DEFAULT_CDP_PORT = 9333
DEFAULT_CDP_URL = f"http://127.0.0.1:{DEFAULT_CDP_PORT}"


def is_cdp_available(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 2.0) -> bool:
    """Check if the Chrome CDP endpoint is responding."""
    endpoint = f"{cdp_url.rstrip('/')}/json/version"
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "KSS-Probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            return "webSocketDebuggerUrl" in data or "Browser" in data
    except (URLError, OSError, TimeoutError, ValueError):
        return False


async def connect_cdp(cdp_url: str = DEFAULT_CDP_URL) -> Tuple[Playwright, Browser, BrowserContext]:
    """Connect to existing Chrome session over CDP."""
    if not is_cdp_available(cdp_url):
        raise ConnectionError(
            f"Chrome CDP is not running at {cdp_url}. "
            f"Please run 'python scripts/kss_probe.py start-session' first."
        )
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError("No active browser context found on CDP connection.")
    ctx = browser.contexts[0]
    return pw, browser, ctx


async def resolve_target_tab(ctx: BrowserContext, target: str) -> Optional[Page]:
    """Find a page/tab matching target: 'sso', 'streaming', 'sbl', or 'any'."""
    target_clean = (target or "").strip().lower()

    for page in ctx.pages:
        url = page.url.lower()
        title = ""
        try:
            title = (await page.title()).lower()
        except Exception:
            pass

        if target_clean in ("streaming", "settrade"):
            if "streamingpage" in url or "settrade" in url or "streaming" in title:
                return page
        elif target_clean in ("sso", "member", "portal", "kss"):
            if any(k in url for k in ["member", "krungsri", "start_sso", "login"]) and "settrade" not in url:
                return page
        elif target_clean in ("sbl", "margin"):
            if "sbl" in url or "borrow" in url or "sbl" in title:
                return page
        elif target_clean == "any":
            return page

    # Fallback for SBL: if no dedicated SBL page was found, check if a streaming page is present
    if target_clean in ("sbl", "margin"):
        for page in ctx.pages:
            if "streamingpage" in page.url.lower() or "settrade" in page.url.lower():
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
            'span.outline-none, span[tabindex], div[tabindex], table, th, td, [data-testid], [id]'
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

            // Generate candidate selector
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
                candidateSel = `${tag}:has-text("${text.replace(/"/g, '\\"')}")`;
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
