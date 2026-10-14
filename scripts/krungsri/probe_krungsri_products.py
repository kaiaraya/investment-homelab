"""
Read-only probe for extra Krungsri SSO products: Streaming, Quick Trade, SBL Real Time.
=======================================================================================
Plan: brain/<conv>/implementation_plan.md (Phase A/B).

Modes
-----
  --product entrypoints  : open the member portal, dump the left-menu product links
                           (href / onclick / img alt) -> start URLs for each product.
  --product streaming|quicktrade|sbl|url
                         : open the product (via --url or the discovered entry), then
                           the OPERATOR drives the headed browser. Each time the operator
                           presses <Enter> in the terminal (optionally typing a label) a
                           snapshot of every open page/frame is captured. Type `q` to finish.

What is captured (no values that identify the session)
------------------------------------------------------
  * page URL (sensitive query params redacted), title, frames, popups
  * DOM landmarks: inputs (id/name/type/placeholder), buttons/links text, table headers
  * network: XHR/fetch method + redacted path + status + content-type + JSON top-level keys
  * WebSocket: redacted URL + frame counts + first-frame JSON keys / length
  * BLOCKED write requests (see SUBMIT GUARD)

SAFETY
------
  * NO login code. Uses `data/session_state.json` only. If the portal shows the login
    form the probe stops with SESSION_EXPIRED (never fires OTP - Invariant 9).
  * SUBMIT GUARD: every non-GET request whose path looks like a write (order/submit/
    confirm/borrow/return/cancel/amend/...) or whose body carries a PIN/password is
    ABORTED at the network layer. The operator should still never press Confirm.
  * No screenshots / HAR / cookies are written. Output: data/probes/krungsri/*.json
    (data/ is git-ignored).

Usage:
    .venv/bin/python scripts/krungsri/probe_krungsri_products.py --product entrypoints
    .venv/bin/python scripts/krungsri/probe_krungsri_products.py --product streaming --url <start url>
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DISPLAY", ":0")

PORTAL_URL = "https://www.krungsrisecurities.com/th/main/default.aspx"
PRODUCT_START_URLS = {
    "streaming": "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming",
    "quicktrade": "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=place_order",
    "sbl": "https://www.krungsrisecurities.com/th/SBL/start.aspx",
}
SESSION_FILE = os.path.join(PROJECT_ROOT, "data", "session_state.json")
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "probes", "krungsri")

# Menu keywords for the left "โปรแกรมซื้อขาย" panel.
PRODUCT_KEYWORDS = {
    "streaming": ("streaming",),
    "quicktrade": ("quick", "quicktrade", "quick trade"),
    "sbl": ("sbl",),
    "trademan": ("trademan",),
    "efin": ("efin",),
    "stockradars": ("stockradar",),
    "blocktrade": ("block",),
}

# ----------------------------------------------------------------------------- pure helpers

_SENSITIVE_PARAM = re.compile(r"(token|sid|session|key|auth|ticket|sso|pass|pin|otp|sig)", re.I)
_WRITE_PATH = re.compile(
    r"(/(order|trade)/(submit|confirm|place|send|cancel|amend|modify|save)|/(place|cancel|amend|modify|borrow|return)_order|/execute_order|/api/.*/(submit|confirm|place|send|cancel|amend))",
    re.I,
)
_READ_PATH = re.compile(r"(list|get|query|inquiry|search|view|load|status|info|history|quote|price)", re.I)
_SECRET_BODY = re.compile(r"(\bpin\b|pincode|pin_code|password|passwd|txtpin|otp)", re.I)
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-]{32,}")


def redact_url(url: str) -> str:
    """Drop values of sensitive query params and long opaque path segments."""
    try:
        parts = urlsplit(url)
    except Exception:
        return "<unparseable>"
    query = [
        (k, "<redacted>" if _SENSITIVE_PARAM.search(k) or _LONG_TOKEN.fullmatch(v or "") else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    path = _LONG_TOKEN.sub("<tok>", parts.path)
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def is_blocked_request(method: str, url: str, post_data: Optional[str]) -> Optional[str]:
    """Return a reason string when the request must be aborted (write / secret), else None."""
    if (method or "GET").upper() in ("GET", "HEAD", "OPTIONS"):
        return None
    body = post_data or ""
    if _SECRET_BODY.search(body):
        return "BODY_HAS_SECRET_FIELD"
    path = urlsplit(url).path
    if _WRITE_PATH.search(path) and not _READ_PATH.search(path):
        return "WRITE_PATH"
    # ASP.NET WebForms postbacks: the target button lives in __EVENTTARGET.
    m = re.search(r"__EVENTTARGET=([^&]*)", body)
    if m and _WRITE_PATH.search(m.group(1)) and not _READ_PATH.search(m.group(1)):
        return "WRITE_POSTBACK"
    return None


def json_shape(payload: Any, depth: int = 0) -> Any:
    """Keys-only shape of a JSON payload (no values)."""
    if depth > 2:
        return "…"
    if isinstance(payload, dict):
        return {k: json_shape(v, depth + 1) for k, v in list(payload.items())[:25]}
    if isinstance(payload, list):
        return [json_shape(payload[0], depth + 1), f"len={len(payload)}"] if payload else []
    return type(payload).__name__


def classify_menu_link(text: str) -> Optional[str]:
    low = (text or "").lower()
    for product, keys in PRODUCT_KEYWORDS.items():
        if any(k in low for k in keys):
            return product
    return None


# ----------------------------------------------------------------------------- DOM snapshot JS

LANDMARKS_JS = r"""() => {
  const t = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const inputs = Array.from(document.querySelectorAll('input, select, textarea'))
    .filter(e => e.type !== 'hidden').slice(0, 60)
    .map(e => ({tag: e.tagName.toLowerCase(), id: e.id, name: e.name, type: e.type,
                placeholder: t(e.placeholder), visible: vis(e)}));
  const buttons = Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a[onclick], [role=button], [role=tab]'))
    .filter(vis).slice(0, 80)
    .map(e => ({tag: e.tagName.toLowerCase(), id: e.id, cls: t(e.className && e.className.baseVal === undefined ? e.className : ''),
                text: t(e.innerText || e.value || e.title || e.getAttribute('aria-label'))}))
    .filter(b => b.text || b.id);
  const tables = Array.from(document.querySelectorAll('table')).filter(vis).slice(0, 15).map(tb => {
    const head = tb.querySelector('thead tr') || tb.querySelector('tr');
    return {id: tb.id, rows: tb.rows.length,
            headers: head ? Array.from(head.cells).slice(0, 15).map(c => t(c.innerText)) : []};
  });
  const loginForm = !!document.querySelector('input[type=password]');
  return {title: document.title, inputs, buttons, tables, login_form_present: loginForm};
}"""

MENU_JS = r"""() => {
  const out = [];
  document.querySelectorAll('a, area, img, [onclick]').forEach(el => {
    const a = el.closest('a') || el;
    const img = el.tagName === 'IMG' ? el : a.querySelector && a.querySelector('img');
    const label = [a.innerText, img && img.alt, img && img.src, a.title, a.id].filter(Boolean).join(' | ');
    out.push({label: label.replace(/\s+/g, ' ').slice(0, 160), href: a.getAttribute && a.getAttribute('href'),
              onclick: a.getAttribute && a.getAttribute('onclick'), target: a.getAttribute && a.getAttribute('target')});
  });
  return out;
}"""


# ----------------------------------------------------------------------------- probe runtime

class Probe:
    def __init__(self, product: str):
        self.product = product
        self.network: Dict[str, Dict[str, Any]] = {}
        self.websockets: Dict[str, Dict[str, Any]] = {}
        self.blocked: List[Dict[str, str]] = []
        self.snapshots: List[Dict[str, Any]] = []
        self.pages: List[Any] = []

    # -- network
    async def guard(self, route, request):
        reason = is_blocked_request(request.method, request.url, request.post_data)
        if reason:
            entry = {"method": request.method, "url": redact_url(request.url), "reason": reason,
                     "at": datetime.now().isoformat(timespec="seconds")}
            self.blocked.append(entry)
            print(f"\n🛑 SUBMIT GUARD blocked {entry['method']} {entry['url']} ({reason})")
            await route.abort()
            return
        await route.continue_()

    async def on_response(self, response):
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        key = f"{req.method} {redact_url(req.url).split('?')[0]}"
        rec = self.network.setdefault(key, {"count": 0, "status": None, "content_type": None, "shape": None})
        rec["count"] += 1
        rec["status"] = response.status
        ctype = (response.headers or {}).get("content-type", "")
        rec["content_type"] = ctype.split(";")[0]
        if rec["shape"] is None and "json" in ctype:
            try:
                rec["shape"] = json_shape(await response.json())
            except Exception:
                rec["shape"] = "unparseable"

    def on_websocket(self, ws):
        key = redact_url(ws.url)
        rec = self.websockets.setdefault(key, {"recv": 0, "sent": 0, "first_recv": None, "first_sent": None})

        def frame(direction, payload):
            rec[direction] += 1
            first = "first_" + direction
            if rec[first] is None:
                if isinstance(payload, (bytes, bytearray)):
                    rec[first] = f"binary len={len(payload)}"
                else:
                    try:
                        rec[first] = {"json_keys": json_shape(json.loads(payload))}
                    except Exception:
                        rec[first] = f"text len={len(payload)} head={re.sub(r'[0-9]', '#', payload[:24])!r}"

        ws.on("framereceived", lambda p: frame("recv", p))
        ws.on("framesent", lambda p: frame("sent", p))

    def attach(self, page):
        self.pages.append(page)
        page.on("response", lambda r: asyncio.ensure_future(self.on_response(r)))
        page.on("websocket", self.on_websocket)

    # -- DOM
    async def snapshot(self, label: str):
        snap = {"label": label, "at": datetime.now().isoformat(timespec="seconds"), "pages": []}
        for page in [p for p in self.pages if not p.is_closed()]:
            entry = {"url": redact_url(page.url), "frames": []}
            for fr in page.frames:
                try:
                    lm = await fr.evaluate(LANDMARKS_JS)
                except Exception as exc:
                    lm = {"error": str(exc)[:120]}
                entry["frames"].append({"url": redact_url(fr.url), **lm})
            snap["pages"].append(entry)
        self.snapshots.append(snap)
        print(f"📸 snapshot '{label}': {len(snap['pages'])} page(s)")

    def dump(self, extra: Dict[str, Any]) -> str:
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, f"probe_{self.product}_{datetime.now():%Y%m%d_%H%M%S}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"product": self.product, **extra, "blocked_requests": self.blocked,
                       "network": self.network, "websockets": self.websockets,
                       "snapshots": self.snapshots}, f, ensure_ascii=False, indent=1)
        return path


async def _read_line(prompt: str) -> str:
    return (await asyncio.get_event_loop().run_in_executor(None, lambda: input(prompt))).strip()


async def run(product: str, url: Optional[str], headless: bool) -> int:
    from playwright.async_api import async_playwright

    if not os.path.exists(SESSION_FILE):
        print("SESSION_EXPIRED: data/session_state.json missing — run daily_readiness first (no login here).")
        return 2

    probe = Probe(product)
    pw = await async_playwright().start()
    launch: Dict[str, Any] = {"headless": headless, "args": ["--no-sandbox", "--window-size=1380,900"]}
    if os.path.exists("/usr/bin/google-chrome"):
        launch["executable_path"] = "/usr/bin/google-chrome"
    browser = await pw.chromium.launch(**launch)
    context = await browser.new_context(storage_state=SESSION_FILE, viewport={"width": 1366, "height": 860})
    await context.route("**/*", probe.guard)
    context.on("page", lambda p: (probe.attach(p), print(f"\n🪟 popup/new tab: {redact_url(p.url)}")))
    page = await context.new_page()
    if page not in probe.pages:
        probe.attach(page)

    extra: Dict[str, Any] = {"started_at": datetime.now().isoformat(timespec="seconds")}
    rc = 0
    target_url = url or PRODUCT_START_URLS.get(product, PORTAL_URL)
    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        lm = await page.evaluate(LANDMARKS_JS)
        if lm.get("login_form_present") and not url:
            print("SESSION_EXPIRED: portal shows a login form. Stopping (Invariant 9 — no OTP from probe).")
            extra["verdict"] = "SESSION_EXPIRED"
            return 2

        if product == "entrypoints":
            links = await page.evaluate(MENU_JS)
            found: Dict[str, List[Dict[str, Any]]] = {}
            for ln in links:
                cat = classify_menu_link(ln["label"])
                if cat:
                    ln["href"] = redact_url(ln["href"]) if ln.get("href", "") and ln["href"].startswith("http") else ln.get("href")
                    if ln not in found.setdefault(cat, []):
                        found[cat].append(ln)
            extra["entrypoints"] = found
            extra["portal_url"] = redact_url(page.url)
            for cat, items in found.items():
                print(f"[{cat}]")
                for it in items[:4]:
                    print(f"   href={it.get('href')} onclick={it.get('onclick')} target={it.get('target')}")
            return 0

        print("\nOperator drives the browser. <Enter> = snapshot (type a label first if you like), q = finish.")
        n = 0
        while True:
            label = await _read_line(f"[{product}] label/Enter/q > ")
            if label.lower() == "q":
                await probe.snapshot("final")
                break
            n += 1
            await probe.snapshot(label or f"snap{n}")
    except Exception as exc:  # report honestly, never fabricate
        extra["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        print(f"ERROR: {extra['error']}")
        rc = 1
    finally:
        path = probe.dump(extra)
        print(f"\n✅ wrote {os.path.relpath(path, PROJECT_ROOT)} | xhr={len(probe.network)} ws={len(probe.websockets)} "
              f"blocked={len(probe.blocked)}")
        await browser.close()
        await pw.stop()
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", required=True,
                    choices=["entrypoints", "streaming", "quicktrade", "sbl", "url"])
    ap.add_argument("--url", help="start URL (from the entrypoints run)")
    ap.add_argument("--headless", action="store_true", help="default is headed")
    args = ap.parse_args()
    return asyncio.run(run(args.product, args.url, args.headless))


if __name__ == "__main__":
    sys.exit(main())
