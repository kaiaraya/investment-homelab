#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KSS DOM Probe CLI & Handoff Generator.

Probe DOM elements across Krungsri SSO, Streaming, and SBL Realtime
using an existing persistent Chrome CDP session without re-logging in.

Commands:
  status         Check Chrome CDP connection and active tabs.
  start-session  Launch Chrome with CDP and run initial login.
  probe          Inspect and extract DOM elements from target tab.
  handoff        Generate a standardized handoff document for agents.

Examples:
  .venv/bin/python scripts/kss_probe.py status
  .venv/bin/python scripts/kss_probe.py probe --target streaming --focus "account,order"
  .venv/bin/python scripts/kss_probe.py probe --target sbl --focus "borrow,short"
  .venv/bin/python scripts/kss_probe.py handoff --target sbl
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add project root to sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.kss.cdp_client import (
    DEFAULT_CDP_PORT,
    DEFAULT_CDP_URL,
    connect_cdp,
    inspect_dom_elements,
    is_cdp_available,
    resolve_target_tab,
)

PROBE_DATA_DIR = os.path.join(REPO_ROOT, "data", "probes")
HANDOFF_DIR = os.path.join(REPO_ROOT, "docs", "handoff")


async def cmd_status(args: argparse.Namespace) -> int:
    """Show CDP status and active tabs."""
    cdp_url = args.cdp_url
    print(f"\n[KSS Probe] Checking CDP endpoint: {cdp_url}")

    if not is_cdp_available(cdp_url):
        print(f"❌ CDP is NOT running at {cdp_url}")
        print("💡 Tip: Run 'python scripts/kss_probe.py start-session' to start the session.\n")
        return 1

    print("✅ CDP is running and responsive.")
    try:
        pw, browser, ctx = await connect_cdp(cdp_url)
        pages = ctx.pages
        print(f"📊 Active Tabs: {len(pages)}")
        for idx, page in enumerate(pages):
            try:
                title = await page.title()
            except Exception:
                title = "(unknown)"
            url = page.url
            # classify
            tag = "OTHER"
            if "streamingpage" in url.lower() or "settrade" in url.lower():
                tag = "STREAMING"
            elif "member" in url.lower() or "krungsri" in url.lower():
                tag = "KRUNGSRI-SSO"
            elif "sbl" in url.lower() or "borrow" in url.lower():
                tag = "SBL"

            print(f"  [{idx}] [{tag:12}] {title[:35]} -> {url[:60]}")
        await browser.close()
        await pw.stop()
        print("")
        return 0
    except Exception as e:
        print(f"❌ Failed to inspect context: {e}")
        return 1


async def cmd_probe(args: argparse.Namespace) -> int:
    """Inspect elements on the target page and save results."""
    cdp_url = args.cdp_url
    target = args.target
    focus = args.focus
    scope = args.scope
    limit = args.limit

    print(f"\n🔍 Probing target='{target}' with focus='{focus or 'ALL'}' on {cdp_url}...")

    pw, browser, ctx = await connect_cdp(cdp_url)
    page = await resolve_target_tab(ctx, target)
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

    # Save to data/probes
    os.makedirs(PROBE_DATA_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(PROBE_DATA_DIR, f"probe_{target}_{stamp}.json")

    payload = {
        "timestamp": stamp,
        "target": target,
        "focus": focus,
        "scope": scope,
        "url": url,
        "title": title,
        "element_count": len(elements),
        "elements": elements,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"💾 Probe results saved to: {out_file}")

    # Preview table
    print("\n--- Top Matches ---")
    for el in elements[:10]:
        text_preview = el["text"][:30] if el["text"] else ""
        vis = "VISIBLE" if el["is_visible"] else "HIDDEN"
        print(f"  {el['suggested_selector']:<35} | {vis:<7} | {text_preview}")

    await browser.close()
    await pw.stop()
    return 0


async def cmd_handoff(args: argparse.Namespace) -> int:
    """Generate Handoff Markdown from latest or specified probe result."""
    target = args.target
    os.makedirs(PROBE_DATA_DIR, exist_ok=True)
    os.makedirs(HANDOFF_DIR, exist_ok=True)

    # Find latest probe file for target
    files = [
        os.path.join(PROBE_DATA_DIR, f)
        for f in os.listdir(PROBE_DATA_DIR)
        if f.startswith(f"probe_{target}_") and f.endswith(".json")
    ]
    if not files:
        # Run probe first
        print(f"No existing probe found for '{target}'. Running probe first...")
        args.focus = None
        args.scope = None
        args.limit = 40
        rc = await cmd_probe(args)
        if rc != 0:
            return rc
        files = [
            os.path.join(PROBE_DATA_DIR, f)
            for f in os.listdir(PROBE_DATA_DIR)
            if f.startswith(f"probe_{target}_") and f.endswith(".json")
        ]

    latest_file = sorted(files)[-1]
    with open(latest_file, "r", encoding="utf-8") as f:
        probe_data = json.load(f)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    handoff_filename = f"PROBE-{target.upper()}-{stamp}.md"
    handoff_path = os.path.join(HANDOFF_DIR, handoff_filename)

    lines = [
        f"# Handoff: DOM Probe Report — {target.upper()}",
        "",
        f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Target**: `{target}`",
        f"- **Source URL**: `{probe_data.get('url')}`",
        f"- **Page Title**: `{probe_data.get('title')}`",
        f"- **Raw Probe JSON**: `{os.path.basename(latest_file)}`",
        "",
        "## 1. Discovered Selectors & Elements",
        "",
        "| Suggested Selector | Tag | Visible | Sample Text | Role / TestID |",
        "|---|---|---|---|---|",
    ]

    for el in probe_data.get("elements", [])[:30]:
        sel = el.get("suggested_selector", "").replace("|", "\\|")
        tag = el.get("tag", "")
        vis = "✅" if el.get("is_visible") else "❌"
        txt = (el.get("text") or "").replace("\n", " ").replace("|", "\\|")[:40]
        meta = el.get("role") or el.get("test_id") or el.get("name") or "-"
        lines.append(f"| `{sel}` | `{tag}` | {vis} | {txt} | `{meta}` |")

    lines.extend([
        "",
        "## 2. Recommended Next Steps for Implementation Agent",
        f"- Verify element interactions using persistent CDP session without re-authenticating.",
        f"- Add scraper/action logic in `app/brokers/{target}/` or `app/browser/` using the verified selectors above.",
        f"- Verify changes with: `.venv/bin/python scripts/verify_changes.py <changed_file>`",
        "",
    ])

    with open(handoff_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n📋 Handoff document generated successfully: {handoff_path}\n")
    return 0


def cmd_start_session(args: argparse.Namespace) -> int:
    """Launch the background or foreground session daemon."""
    daemon_script = os.path.join(REPO_ROOT, "scripts", "kss", "kss_session_daemon.py")
    cmd = [sys.executable, daemon_script, str(args.interval)]
    print(f"\n🚀 Starting KSS Session Daemon: {' '.join(cmd)}")
    import subprocess
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="KSS Persistent Probe Toolkit")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help=f"CDP URL (default: {DEFAULT_CDP_URL})")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Check CDP session status and tabs")

    # start-session
    p_start = subparsers.add_parser("start-session", help="Start Chrome with CDP and login daemon")
    p_start.add_argument("--interval", type=int, default=300, help="Heartbeat interval in seconds (default: 300)")

    # probe
    p_probe = subparsers.add_parser("probe", help="Probe DOM elements in target tab")
    p_probe.add_argument("--target", default="streaming", choices=["streaming", "sbl", "sso", "any"])
    p_probe.add_argument("--focus", default=None, help="Regex / keyword filter for text or attributes")
    p_probe.add_argument("--scope", default=None, help="CSS selector scope to restrict inspection")
    p_probe.add_argument("--limit", type=int, default=50, help="Max elements to capture")

    # handoff
    p_handoff = subparsers.add_parser("handoff", help="Generate Handoff Markdown from probe results")
    p_handoff.add_argument("--target", default="streaming", choices=["streaming", "sbl", "sso"])

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
