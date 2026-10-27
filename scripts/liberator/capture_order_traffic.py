# -*- coding: utf-8 -*-
"""Capture the Liberator WebTrade *order placement* network request.

Injects a fetch/XHR interceptor into every open Liberator tab and logs the
method/url/headers/body/response of each request to a local JSONL file. The
goal is to discover the write endpoint the footer ticket calls when an order
is actually submitted — including how the PIN is transmitted (plaintext /
hash / encrypted) — so we can later replicate it with a direct httpx call
and drop the slow, fragile DOM automation entirely.

Sensitive data (session cookie, PIN) is written ONLY to the local output
file. Stdout prints a redacted summary (method/url/status, no body, no cookie).

Run:  .venv/bin/python scripts/liberator/capture_order_traffic.py
Stop:  Ctrl-C (or kill the process). The file keeps appending.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.broker_cdp.client import connect_cdp  # noqa: E402

CDP_URL = "http://127.0.0.1:9334"
BROKER = "liberator"
OUT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "handoff", "liberator_order_capture.jsonl"
))

_INJECT = r"""
() => {
  if (window.__order_capture_installed) return 'already';
  window.__order_capture_installed = true;
  window.__order_capture = [];
  const cap = window.__order_capture;
  const push = (e) => { cap.push(e); if (cap.length > 800) cap.shift(); };

  const cleanHeaders = (h) => {
    if (!h) return {};
    const o = {};
    if (typeof Headers !== 'undefined' && h instanceof Headers) {
      h.forEach((v, k) => { o[k] = v; });
      return o;
    }
    for (const k in h) { try { o[k] = String(h[k]); } catch (e) {} }
    return o;
  };
  const bodyText = async (b) => {
    if (b == null) return null;
    if (typeof b === 'string') return b;
    try { return await b.clone().text(); } catch (e) { return String(b); }
  };

  // --- fetch ---
  const of = window.fetch;
  window.fetch = async function (...args) {
    const input = args[0], init = args[1] || {};
    const url = (typeof input === 'string') ? input : (input && input.url) || '';
    const method = (init.method || 'GET').toUpperCase();
    const headers = cleanHeaders(init.headers);
    const reqBody = await bodyText(init.body);
    const entry = { t: Date.now(), kind: 'fetch', method, url, headers, reqBody, status: null, respBody: null };
    push(entry);
    try {
      const r = await of.apply(this, args);
      entry.status = r.status;
      try { entry.respBody = (await r.clone().text()).slice(0, 8000); } catch (e) {}
      return r;
    } catch (err) {
      entry.status = 'ERR:' + String(err);
      throw err;
    }
  };

  // --- XMLHttpRequest ---
  const oxhr = XMLHttpRequest.prototype.open;
  const osend = XMLHttpRequest.prototype.send;
  const osrh = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__cap = { t: Date.now(), kind: 'xhr', method: String(method).toUpperCase(), url, headers: {}, reqBody: null, status: null, respBody: null };
    push(this.__cap);
    return oxhr.apply(this, [method, url, ...rest]);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    if (this.__cap) { try { this.__cap.headers[k] = String(v); } catch (e) {} }
    return osrh.apply(this, [k, v]);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (this.__cap) {
      this.__cap.reqBody = (typeof body === 'string') ? body : (body ? String(body) : null);
    }
    this.addEventListener('load', () => {
      if (this.__cap) {
        this.__cap.status = this.status;
        try { this.__cap.respBody = String(this.responseText || '').slice(0, 8000); } catch (e) {}
      }
    });
    return osend.apply(this, [body]);
  };

  return 'installed';
}
"""


def _summarize(e: dict) -> str:
    method = e.get("method", "?")
    url = e.get("url", "?")
    status = e.get("status", "pending")
    return f"[capture] {method} {url}  -> status={status}"


async def main() -> None:
    pw, browser, ctx = await connect_cdp(CDP_URL, BROKER)
    targets = [p for p in ctx.pages if "liberator.co.th" in (p.url or "").lower()]
    if not targets:
        targets = ctx.pages
    print(f"[capture] injecting into {len(targets)} tab(s)")
    for p in targets:
        try:
            r = await p.evaluate(_INJECT)
            print(f"[capture]   {p.url!r} -> {r}")
        except Exception as e:
            print(f"[capture]   inject failed on {p.url!r}: {e}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print(f"[capture] output -> {OUT}")
    print("[capture] LISTENING — place the order on the headed browser now. Ctrl-C to stop.")

    seen: dict = {}
    try:
        while True:
            for p in targets:
                try:
                    entries = await p.evaluate("() => window.__order_capture || []")
                except Exception:
                    continue
                base = seen.get(id(p), 0)
                for e in entries[base:]:
                    if e.get("method") in ("POST", "PUT", "PATCH", "DELETE"):
                        with open(OUT, "a", encoding="utf-8") as f:
                            f.write(json.dumps(e, default=str, ensure_ascii=False) + "\n")
                        print(_summarize(e))
                seen[id(p)] = len(entries)
            await asyncio.sleep(0.7)
    except KeyboardInterrupt:
        print("[capture] stopped")
    finally:
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
