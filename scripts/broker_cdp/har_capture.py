#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HAR capture over the broker CDP daemons (Streaming/SBL + Liberator).

Connects to the already-authenticated persistent-session Chrome (CDP 9333/9334),
attaches Network listeners, drives the requested phase, and exports:
  - data/har/<broker>_all.har   (HAR 1.2, every request/response incl. bodies)
  - data/har/<broker>_endpoints.json (compact action->endpoint map input)

Usage:
  .venv/bin/python scripts/broker_cdp/har_capture.py --broker kss readonly
  .venv/bin/python scripts/broker_cdp/har_capture.py --broker liberator readonly
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402

HAR_DIR = os.path.join(REPO, "data", "har")
BODY_LIMIT = 12000
# Resource types / methods worth keeping a body for (noise otherwise).
BODY_TYPES = ("xhr", "fetch", "document", "websocket")


class HarCapture:
    def __init__(self):
        self.entries = {}
        self.order = []
        self.phase = "init"
        self._attached = set()
        self.websockets = []  # list of {phase, url}

    def set_phase(self, label: str):
        self.phase = label

    def attach(self, page):
        if id(page) in self._attached:
            return
        self._attached.add(id(page))
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfinished", self._on_requestfinished)
        page.on("requestfailed", self._on_requestfailed)
        page.on("websocket", self._on_websocket)

    def _on_websocket(self, ws):
        self.websockets.append({"phase": self.phase, "url": ws.url})

    def _on_request(self, req):
        rid = id(req)
        try:
            headers = req.headers
        except Exception:
            headers = {}
        post = None
        try:
            post = req.post_data
        except Exception:
            post = None
        self.entries[rid] = {
            "phase": self.phase,
            "started": time.time(),
            "method": req.method,
            "url": req.url,
            "resource_type": getattr(req, "resource_type", ""),
            "req_headers": headers,
            "post_data": post,
            "status": None,
            "resp_headers": None,
            "body": None,
            "mime": None,
            "finished": None,
            "error": None,
        }
        self.order.append(rid)

    async def _on_response(self, resp):
        e = self.entries.get(id(resp.request))
        if e is None:
            return
        e["status"] = resp.status
        try:
            e["resp_headers"] = resp.headers
        except Exception:
            pass
        e["mime"] = (resp.headers or {}).get("content-type", "")
        rt = e["resource_type"]
        if rt in BODY_TYPES or e["method"] in ("POST", "PUT", "PATCH"):
            try:
                e["body"] = (await resp.text())[:BODY_LIMIT]
            except Exception:
                e["body"] = None

    def _on_requestfinished(self, req):
        e = self.entries.get(id(req))
        if e:
            e["finished"] = time.time()

    def _on_requestfailed(self, req):
        e = self.entries.get(id(req))
        if e:
            e["error"] = getattr(req, "failure", None)

    def _entries_sorted(self):
        return [self.entries[rid] for rid in self.order if rid in self.entries]

    def to_har(self, title="", creator="hermes-0a"):
        entries = []
        for e in self._entries_sorted():
            req_headers = [{"name": k, "value": str(v)} for k, v in e["req_headers"].items()]
            post_data = None
            if e["post_data"]:
                post_data = {
                    "mimeType": "application/x-www-form-urlencoded",
                    "text": e["post_data"],
                }
            resp_headers = [{"name": k, "value": str(v)} for k, v in (e["resp_headers"] or {}).items()]
            content = {"size": len(e["body"] or ""), "mimeType": e["mime"] or ""}
            if e["body"]:
                content["text"] = e["body"]
            started = datetime.fromtimestamp(e["started"], tz=timezone.utc).isoformat()
            entries.append({
                "startedDateTime": started,
                "time": 0,
                "request": {
                    "method": e["method"],
                    "url": e["url"],
                    "httpVersion": "HTTP/1.1",
                    "headers": req_headers,
                    "queryString": [],
                    "cookies": [],
                    "headersSize": -1,
                    "bodySize": -1,
                    "postData": post_data,
                },
                "response": {
                    "status": e["status"] or 0,
                    "statusText": "",
                    "httpVersion": "HTTP/1.1",
                    "headers": resp_headers,
                    "cookies": [],
                    "content": content,
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": -1,
                },
                "cache": {},
                "timings": {"send": 0, "wait": 0, "receive": 0},
                "_hermes": {
                    "phase": e["phase"],
                    "resource_type": e["resource_type"],
                    "error": e["error"],
                },
            })
        first = entries[0]["startedDateTime"] if entries else ""
        return {
            "log": {
                "version": "1.2",
                "creator": {"name": creator, "version": "1.0"},
                "pages": [{"id": "page_0", "title": title, "startedDateTime": first}],
                "entries": entries,
            }
        }

    def endpoint_map(self):
        """Compact action->endpoint rows for the P.0a map doc."""
        rows = []
        for e in self._entries_sorted():
            if e["resource_type"] not in ("xhr", "fetch", "document"):
                if e["method"] not in ("POST", "PUT", "PATCH"):
                    continue
            rows.append({
                "phase": e["phase"],
                "method": e["method"],
                "url": e["url"],
                "resource_type": e["resource_type"],
                "status": e["status"],
                "post_data": (e["post_data"] or "")[:2000],
                "response_sample": (e["body"] or "")[:2000],
                "content_type": e["mime"],
            })
        return rows


def save(broker, cap: HarCapture, title: str):
    os.makedirs(HAR_DIR, exist_ok=True)
    har_path = os.path.join(HAR_DIR, f"{broker}_all.har")
    map_path = os.path.join(HAR_DIR, f"{broker}_endpoints.json")
    with open(har_path, "w", encoding="utf-8") as f:
        json.dump(cap.to_har(title=title), f, ensure_ascii=False, indent=2)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(cap.endpoint_map(), f, ensure_ascii=False, indent=2)
    n = len(cap._entries_sorted())
    ws = cap.websockets
    print(f"💾 {broker}: {n} requests -> {har_path}")
    print(f"💾 {broker}: endpoint map -> {map_path}")
    if ws:
        seen_ws = []
        for w in ws:
            if w["url"] not in seen_ws:
                seen_ws.append(w["url"])
        print(f"🔌 {broker}: websockets seen: {seen_ws}")
    return har_path, map_path


# ────────────────────────────────────────────────────────────────────────────
# Read-only phases (no order placement — safe pre-open)
# ────────────────────────────────────────────────────────────────────────────

async def phase_kss_readonly():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    cap = HarCapture()
    for p in ctx.pages:
        cap.attach(p)
    ctx.on("page", lambda p: cap.attach(p))

    # 1. Streaming: reload to capture full initial-load endpoint set, then quote
    streaming = await resolve_target_tab(ctx, "streaming", "kss")
    if streaming:
        await streaming.bring_to_front()
        cap.set_phase("streaming_reload")
        try:
            await streaming.reload(wait_until="domcontentloaded", timeout=45000)
            await streaming.wait_for_timeout(8000)
        except Exception as ex:
            print(f"⚠️ streaming reload: {type(ex).__name__}: {ex}")
        cap.set_phase("streaming_quote_BCPG")
        try:
            sym = streaming.locator('input[placeholder="Symbol"]').first
            await sym.fill("BCPG")
            await streaming.keyboard.press("Enter")
            await streaming.wait_for_timeout(6000)
        except Exception as ex:
            print(f"⚠️ streaming quote step: {type(ex).__name__}: {ex}")

    # 2. SBL: reload to capture inventory + PP load, then each tab PostBack
    sbl = await resolve_target_tab(ctx, "sbl", "kss")
    if sbl:
        await sbl.bring_to_front()
        cap.set_phase("sbl_reload")
        try:
            await sbl.reload(wait_until="domcontentloaded", timeout=45000)
            await sbl.wait_for_timeout(6000)
        except Exception as ex:
            print(f"⚠️ sbl reload: {type(ex).__name__}: {ex}")
        for tab_id, label in [
            ("#MainCenter_lbSet50", "sbl_tab_set50"),
            ("#MainCenter_lbSet100", "sbl_tab_set100"),
            ("#MainCenter_lbNewSec", "sbl_tab_newsec"),
            ("#MainCenter_lbXD", "sbl_tab_xd"),
        ]:
            cap.set_phase(label)
            try:
                el = sbl.locator(tab_id)
                if await el.count():
                    await el.first.click()
                    await sbl.wait_for_timeout(4000)
                else:
                    print(f"⚠️ {tab_id} not found")
            except Exception as ex:
                print(f"⚠️ {label}: {type(ex).__name__}: {ex}")

    save("kss", cap, "KSS Streaming + SBL (read-only)")
    await browser.close()
    await pw.stop()


async def phase_liberator_readonly():
    pw, browser, ctx = await connect_cdp(cdp_url_for("liberator"), "liberator")
    cap = HarCapture()
    for p in ctx.pages:
        cap.attach(p)
    ctx.on("page", lambda p: cap.attach(p))

    page = await resolve_target_tab(ctx, "portfolio", "liberator") or ctx.pages[0]
    await page.bring_to_front()
    cap.set_phase("liberator_portfolio")
    try:
        await page.goto("https://webtrade.liberator.co.th/Portfolio",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(7000)
    except Exception as ex:
        print(f"⚠️ liberator portfolio step: {type(ex).__name__}: {ex}")

    save("liberator", cap, "Liberator WebTrade (read-only)")
    await browser.close()
    await pw.stop()


async def main():
    parser = argparse.ArgumentParser(description="Broker CDP HAR capture")
    parser.add_argument("--broker", required=True, choices=["kss", "liberator"])
    parser.add_argument("phase", choices=["readonly"])
    args = parser.parse_args()

    if args.broker == "kss":
        await phase_kss_readonly()
    else:
        await phase_liberator_readonly()


if __name__ == "__main__":
    asyncio.run(main())
