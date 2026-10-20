#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified broker DOM probe CLI & handoff generator (KSS + Liberator).

Probe DOM elements across either broker's target tabs using an existing
persistent Chrome CDP session, without re-logging in.

Commands:
  status         Check Chrome CDP connection and active tabs.
  start-session  Launch Chrome with CDP and run initial login / session resume.
  probe          Inspect and extract DOM elements from a target tab.
  handoff        Generate a standardized handoff document for agents.

Examples:
  .venv/bin/python scripts/broker_probe.py --broker kss status
  .venv/bin/python scripts/broker_probe.py --broker kss probe --target streaming --focus "account,order"
  .venv/bin/python scripts/broker_probe.py --broker liberator probe --target trade --focus "buy,sell,change"
  .venv/bin/python scripts/broker_probe.py --broker liberator handoff --target trade
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse

# Add project root to sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.broker_cdp.client import (  # noqa: E402
    cdp_url_for,
    connect_cdp,
    inspect_dom_elements,
    inspect_sbl_application,
    is_cdp_available,
    resolve_target_tab,
)
from scripts.broker_cdp.brokers import BROKERS  # noqa: E402

PROBE_DATA_DIR = os.path.join(REPO_ROOT, "data", "probes")
HANDOFF_DIR = os.path.join(REPO_ROOT, "docs", "handoff")
DAEMON_SCRIPT = os.path.join(REPO_ROOT, "scripts", "broker_cdp", "session_daemon.py")


def _broker(args) -> str:
    return getattr(args, "broker", "kss")


def _cfg(args) -> dict:
    return BROKERS[_broker(args)]


def _classify_tab(broker: str, url: str) -> str:
    u = url.lower()
    if broker == "kss":
        if "streamingpage" in u or "settrade" in u:
            return "STREAMING"
        if "member" in u or "krungsri" in u:
            return "KRUNGSRI-SSO"
        if "sbl" in u or "borrow" in u:
            return "SBL"
        return "OTHER"
    # liberator — match the path, not a bare substring ("webtrade" contains "trade")
    path = urlparse(url).path.lower()
    if "/portfolio" in path:
        return "PORTFOLIO"
    if "/trade" in path or "/order" in path:
        return "TRADE"
    if "/market" in path or "/quote" in path:
        return "MARKET"
    if "/login" in path or "/otp" in path:
        return "LOGIN"
    return "OTHER"


async def cmd_status(args: argparse.Namespace) -> int:
    broker = _broker(args)
    label = _cfg(args)["label"]
    cdp_url = args.cdp_url or cdp_url_for(broker)
    print(f"\n[{label} Probe] Checking CDP endpoint: {cdp_url}")

    if not is_cdp_available(cdp_url):
        print(f"❌ {label} CDP is NOT running at {cdp_url}")
        print(f"💡 Tip: Run 'python scripts/broker_probe.py --broker {broker} start-session' first.\n")
        return 1

    print(f"✅ {label} CDP is running and responsive.")
    try:
        pw, browser, ctx = await connect_cdp(cdp_url, broker)
        pages = ctx.pages
        print(f"📊 Active Tabs: {len(pages)}")
        for idx, page in enumerate(pages):
            try:
                title = await page.title()
            except Exception:
                title = "(unknown)"
            tag = _classify_tab(broker, page.url)
            print(f"  [{idx}] [{tag:12}] {title[:35]} -> {page.url[:60]}")
        await browser.close()
        await pw.stop()
        print("")
        return 0
    except Exception as e:
        print(f"❌ Failed to inspect context: {e}")
        return 1


async def cmd_probe(args: argparse.Namespace) -> int:
    broker = _broker(args)
    cfg = _cfg(args)
    label = cfg["label"]
    cdp_url = args.cdp_url or cdp_url_for(broker)
    target = args.target or cfg["default_target"]
    focus = args.focus
    scope = args.scope
    limit = args.limit

    if target not in cfg["targets"]:
        print(f"❌ Invalid target '{target}' for {label}. Choose from: {', '.join(cfg['targets'])}")
        return 1

    print(f"\n🔍 Probing {label} target='{target}' with focus='{focus or 'ALL'}' on {cdp_url}...")

    pw, browser, ctx = await connect_cdp(cdp_url, broker)
    page = await resolve_target_tab(ctx, target, broker)
    if not page:
        print(f"❌ Could not find a tab matching target='{target}'")
        await browser.close()
        await pw.stop()
        return 1

    title = await page.title()
    url = page.url
    print(f"📍 Connected to tab: '{title}' [{url}]")

    elements = await inspect_dom_elements(
        page,
        scope_selector=scope,
        keyword_filter=focus,
        max_elements=limit,
    )
    print(f"🎯 Matched {len(elements)} elements.")

    sbl_details = None
    if broker == "kss" and target == "sbl":
        print("🌾 Inspecting SBL Real Time application (Borrow / Return / Inventory)...")
        try:
            sbl_details = await inspect_sbl_application(page)
            bform = sbl_details.get("borrow_form", {})
            print(f"  • SBL Application Detected: {sbl_details.get('is_sbl_app')}")
            print(f"  • Purchasing Power (PP):   {bform.get('purchasing_power') or 'N/A'}")
            print(f"  • Borrow Form Ready:       Symbol input={'✅' if bform.get('symbol_input_exists') else '❌'}, "
                  f"Qty input={'✅' if bform.get('qty_input_exists') else '❌'}, "
                  f"Submit btn={'✅' if bform.get('borrow_button_exists') else '❌'}")
            print(f"  • Borrowable Stocks Found: {sbl_details.get('total_inventory_stocks_detected')}")
            print(f"  • Active Return Contracts: {len(sbl_details.get('active_contracts_for_return', []))}")
        except Exception as e:
            print(f"  ⚠️ SBL specific extraction notice: {e}")

    os.makedirs(PROBE_DATA_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(PROBE_DATA_DIR, f"{cfg['probe_prefix']}_{target}_{stamp}.json")

    payload = {
        "timestamp": stamp,
        "broker": broker,
        "target": target,
        "focus": focus,
        "scope": scope,
        "url": url,
        "title": title,
        "element_count": len(elements),
        "elements": elements,
        "sbl_details": sbl_details,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Probe results saved to: {out_file}")

    print("\n--- Top Matches ---")
    for el in elements[:10]:
        text_preview = el["text"][:30] if el["text"] else ""
        vis = "VISIBLE" if el["is_visible"] else "HIDDEN"
        print(f"  {el['suggested_selector']:<35} | {vis:<7} | {text_preview}")

    await browser.close()
    await pw.stop()
    return 0


async def cmd_handoff(args: argparse.Namespace) -> int:
    broker = _broker(args)
    cfg = _cfg(args)
    label = cfg["label"]
    target = args.target or cfg["default_target"]
    os.makedirs(PROBE_DATA_DIR, exist_ok=True)
    os.makedirs(HANDOFF_DIR, exist_ok=True)

    prefix = cfg["probe_prefix"]
    files = [
        os.path.join(PROBE_DATA_DIR, f)
        for f in os.listdir(PROBE_DATA_DIR)
        if f.startswith(f"{prefix}_{target}_") and f.endswith(".json")
    ]
    if not files:
        print(f"No existing probe found for {label} '{target}'. Running probe first...")
        args.target = target
        args.focus = None
        args.scope = None
        args.limit = 40
        rc = await cmd_probe(args)
        if rc != 0:
            return rc
        files = [
            os.path.join(PROBE_DATA_DIR, f)
            for f in os.listdir(PROBE_DATA_DIR)
            if f.startswith(f"{prefix}_{target}_") and f.endswith(".json")
        ]

    latest_file = sorted(files)[-1]
    with open(latest_file, "r", encoding="utf-8") as f:
        probe_data = json.load(f)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    title_tag = target.upper() if broker == "kss" else f"LIBERATOR ({target.upper()})"
    handoff_filename = f"{cfg['handoff_prefix']}-{target.upper()}-{stamp}.md"
    handoff_path = os.path.join(HANDOFF_DIR, handoff_filename)

    lines = [
        f"# Handoff: DOM Probe Report — {title_tag}",
        "",
        f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Broker**: `{broker}`",
        f"- **Target**: `{target}`",
        f"- **Source URL**: `{probe_data.get('url')}`",
        f"- **Page Title**: `{probe_data.get('title')}`",
        f"- **Raw Probe JSON**: `{os.path.basename(latest_file)}`",
        "",
        "## 1. Discovered Selectors & Elements",
        "",
        "| Suggested Selector | Tag | Visible | Sample Text | Role / Meta |",
        "|---|---|---|---|---|",
    ]

    for el in probe_data.get("elements", [])[:30]:
        sel = el.get("suggested_selector", "").replace("|", "\\|")
        tag = el.get("tag", "")
        vis = "✅" if el.get("is_visible") else "❌"
        txt = (el.get("text") or "").replace("\n", " ").replace("|", "\\|")[:40]
        meta = el.get("role") or el.get("test_id") or el.get("name") or "-"
        lines.append(f"| `{sel}` | `{tag}` | {vis} | {txt} | `{meta}` |")

    sbl_info = probe_data.get("sbl_details")
    if sbl_info:
        bform = sbl_info.get("borrow_form", {})
        lines.extend([
            "",
            "## 2. SBL Real Time — Borrow Form Contract",
            "",
            f"- **Purchasing Power (PP)**: `{bform.get('purchasing_power') or 'N/A'}`",
            f"- **Customer Code**: `{bform.get('customer_code') or 'N/A'}`",
            f"- **Customer Name**: `{bform.get('customer_name') or 'N/A'}`",
            "",
            "| Element Role | Selector | Exists in DOM |",
            "|---|---|---|",
            f"| Stock Symbol Input | `{bform.get('symbol_input_selector')}` | {'✅' if bform.get('symbol_input_exists') else '❌'} |",
            f"| Borrow Qty Input | `{bform.get('qty_input_selector')}` | {'✅' if bform.get('qty_input_exists') else '❌'} |",
            f"| Borrow Submit Button | `{bform.get('borrow_button_selector')}` | {'✅' if bform.get('borrow_button_exists') else '❌'} |",
            "",
            "## 3. SBL Inventory Sample (Borrowable Stocks & Available Volume)",
            "",
            "| Symbol | Fee | Available Volume | IM Rate |",
            "|---|---|---|---|",
        ])
        for item in sbl_info.get("inventory_sample", [])[:15]:
            lines.append(f"| `{item.get('symbol')}` | {item.get('fee')} | {item.get('available_volume')} | {item.get('im_rate')} |")

        lines.extend([
            "",
            "## 4. Active Borrow Contracts (For Return)",
            "",
            "| Ref.No | Tran Date | Symbol | Quantity | Has Return Action | Return Button ID |",
            "|---|---|---|---|---|---|",
        ])
        for c in sbl_info.get("active_contracts_for_return", []):
            lines.append(f"| `{c.get('ref_no')}` | {c.get('tran_date')} | `{c.get('symbol')}` | {c.get('quantity')} | {'✅' if c.get('has_return_button') else '❌'} | `{c.get('return_button_id') or '-'}` |")

    lines.extend([
        "",
        "## Recommended Next Steps for Implementation Agent",
        f"- Verify element interactions using persistent CDP session (Port {cfg['port']}) without re-authenticating.",
        f"- Add scraper/action logic in `app/brokers/{broker}/` or `app/browser/` using the verified selectors above.",
        f"- Verify changes with: `.venv/bin/python scripts/verify_changes.py <changed_file>`",
        "",
    ])

    with open(handoff_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n📋 {label} Handoff document generated successfully: {handoff_path}\n")
    return 0


def cmd_start_session(args: argparse.Namespace) -> int:
    broker = _broker(args)
    cmd = [sys.executable, DAEMON_SCRIPT, broker, str(args.interval)]
    print(f"\n🚀 Starting {_cfg(args)['label']} Session Daemon: {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified broker persistent probe toolkit (KSS + Liberator)")
    parser.add_argument("--broker", required=True, choices=sorted(BROKERS), help="Broker slug: kss | liberator")
    parser.add_argument("--cdp-url", default=None, help="Override CDP URL (default: http://127.0.0.1:<broker port>)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Check CDP session status and tabs")

    p_start = subparsers.add_parser("start-session", help="Start Chrome with CDP and login daemon")
    p_start.add_argument("--interval", type=int, default=300, help="Heartbeat interval in seconds (default: 300)")

    p_probe = subparsers.add_parser("probe", help="Probe DOM elements in a target tab")
    p_probe.add_argument("--target", default=None, help="Target tab (broker-dependent; defaults per broker)")
    p_probe.add_argument("--focus", default=None, help="Comma-separated keywords / regex filter for text or attributes")
    p_probe.add_argument("--scope", default=None, help="CSS selector scope to restrict inspection")
    p_probe.add_argument("--limit", type=int, default=50, help="Max elements to capture")

    p_handoff = subparsers.add_parser("handoff", help="Generate Handoff Markdown from probe results")
    p_handoff.add_argument("--target", default=None, help="Target tab (broker-dependent; defaults per broker)")

    args = parser.parse_args()

    if args.command == "status":
        return asyncio.run(cmd_status(args))
    elif args.command == "probe":
        return asyncio.run(cmd_probe(args))
    elif args.command == "handoff":
        return asyncio.run(cmd_handoff(args))
    elif args.command == "start-session":
        return cmd_start_session(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
