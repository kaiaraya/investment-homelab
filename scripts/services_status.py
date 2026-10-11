#!/usr/bin/env python3
"""
Services Status Inspector for Investment Homelab — READ-ONLY.
=============================================================
Answers one question: *which long-running services are actually up right now?*

It NEVER starts, stops, or mutates anything (zero side effects). It only observes,
so it is safe to run at any time — including while another agent is trading.

Reported services (in order):
  1. Gateway            — uvicorn ``app.main:app`` on :8000 (TCP :8000 + HTTP ``/health``)
  2. Cloudflare tunnel  — ``cloudflared`` process that exposes the public LINE webhook
  3. LINE OTP relay     — ``otp_relay_readiness.check()`` (SINGLE SOURCE OF TRUTH, Invariant 9)
  4. KDE Connect        — real-time D-Bus ``isReachable`` (Invariant 8); DORMANT fallback
  5. In-gateway daemons — slim-gateway config flags (Phase 3 / orchestrator / action-exit)
  6. IDE MCP server     — ``playwright-homelab`` stdio MCP (spawned & owned by the IDE)

Exit codes:
  0 = gateway UP **and** LINE OTP relay READY (GO for OTP/auth work)
  1 = otherwise (NO-GO — see the per-service reason)

Usage:
  .venv/bin/python scripts/services_status.py
  .venv/bin/python scripts/services_status.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import urllib.request

# Ensure the repo root is importable when run directly
# (`python scripts/services_status.py`) so `app.*` modules resolve.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

GATEWAY_PORT = 8000
MCP_MARKER = "app.mcp.mcp_server"


def _port_open(host: str = "127.0.0.1", port: int | None = None, timeout: float = 0.6) -> bool:
    """Plain TCP probe — true when something is listening (no HTTP call)."""
    port = GATEWAY_PORT if port is None else port
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pids_matching(pattern: str) -> list[str]:
    """Return PIDs whose full command line matches ``pattern`` (best effort)."""
    try:
        res = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        return [p for p in res.stdout.strip().splitlines() if p]
    except Exception:
        return []


def _gateway_health(timeout: float = 1.5, port: int | None = None) -> tuple[bool, str]:
    """HTTP probe of the gateway ``/health`` endpoint."""
    port = GATEWAY_PORT if port is None else port
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace").strip()
            return True, (body[:160] or f"HTTP {resp.status}")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- collectors

async def collect_gateway() -> dict:
    if not _port_open():
        return {
            "key": "gateway",
            "name": "Gateway (uvicorn app.main:app)",
            "status": "DOWN",
            "required": True,
            "detail": f"nothing listening on :{GATEWAY_PORT} — start it with "
                      f"'scripts/start_homelab.py' or "
                      f"'.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port {GATEWAY_PORT}'",
        }
    ok, detail = await asyncio.to_thread(_gateway_health)
    if ok:
        return {
            "key": "gateway",
            "name": "Gateway (uvicorn app.main:app)",
            "status": "UP",
            "required": True,
            "detail": f":{GATEWAY_PORT} listening · /health -> {detail}",
        }
    return {
        "key": "gateway",
        "name": "Gateway (uvicorn app.main:app)",
        "status": "DEGRADED",
        "required": True,
        "detail": f":{GATEWAY_PORT} open but /health failed -> {detail}",
    }


def collect_cloudflared() -> dict:
    pids = _pids_matching("cloudflared")
    if pids:
        return {
            "key": "cloudflared",
            "name": "Cloudflare tunnel (LINE webhook)",
            "status": "UP",
            "required": False,
            "detail": f"pid(s) {', '.join(pids)} — public webhook must route to "
                      f"http://127.0.0.1:{GATEWAY_PORT}/api/v1/webhook/line",
        }
    return {
        "key": "cloudflared",
        "name": "Cloudflare tunnel (LINE webhook)",
        "status": "DOWN",
        "required": False,
        "detail": "no 'cloudflared' process — LINE will only work on localhost "
                  "(run 'cloudflared tunnel --config ~/.cloudflared/config.yml run')",
    }


def collect_mcp_server() -> dict:
    pids = _pids_matching(MCP_MARKER)
    if pids:
        return {
            "key": "mcp",
            "name": "IDE MCP server (playwright-homelab)",
            "status": "UP",
            "required": False,
            "detail": f"pid(s) {', '.join(pids)} — stdio MCP spawned by the IDE; "
                      f"it provides the browser tools. NOT an API entrypoint (retired); "
                      f"do not kill it while the IDE is connected",
        }
    return {
        "key": "mcp",
        "name": "IDE MCP server (playwright-homelab)",
        "status": "OFF",
        "required": False,
        "detail": "not running — no browser tools available until the IDE reconnects",
    }


def collect_in_gateway_daemons() -> dict:
    """Report the slim-gateway switches that decide which daemons the gateway starts."""
    try:
        from app.core.config import settings
    except Exception as e:
        return {
            "key": "daemons",
            "name": "In-gateway background daemons",
            "status": "UNKNOWN",
            "required": False,
            "detail": f"could not load app.core.config -> {type(e).__name__}: {e}",
        }
    flags = {
        "intraday_scheduler": bool(getattr(settings, "ENABLE_INTRADAY_SCHEDULER", False)),
        "action_exit_dispatcher": bool(getattr(settings, "ENABLE_ACTION_EXIT_DISPATCHER", False)),
        "master_orchestrator": bool(getattr(settings, "ENABLE_AGENTIC_ORCHESTRATOR", False)),
    }
    on = [k for k, v in flags.items() if v]
    return {
        "key": "daemons",
        "name": "In-gateway background daemons",
        "status": "ON" if on else "SLIM",
        "required": False,
        "detail": ("enabled: " + ", ".join(on)) if on
                  else "all OFF (slim boot: webhook + API + DB + session sentinel only)",
        "flags": flags,
    }


async def collect_otp_relay() -> dict:
    from app.services.otp_relay_readiness import otp_relay_readiness

    res = await otp_relay_readiness.check(
        require_gateway=True, allow_kde_fallback=False, gateway_port=GATEWAY_PORT
    )
    return {
        "key": "otp_relay",
        "name": "LINE OTP relay (authoritative)",
        "status": "UP" if res.ready else "DOWN",
        "required": True,
        "detail": f"channel={res.channel} · {res.reason}",
        "raw": res.to_dict(),
    }


async def collect_kdeconnect() -> dict:
    try:
        from app.services.kdeconnect_service import kdeconnect_service

        reachable = await asyncio.wait_for(kdeconnect_service.is_device_reachable(), timeout=8.0)
    except asyncio.TimeoutError:
        return {
            "key": "kde",
            "name": "KDE Connect bridge (dormant fallback)",
            "status": "TIMEOUT",
            "required": False,
            "detail": "D-Bus reachability probe timed out (bridge may be unpaired)",
        }
    except Exception as e:
        return {
            "key": "kde",
            "name": "KDE Connect bridge (dormant fallback)",
            "status": "UNKNOWN",
            "required": False,
            "detail": f"probe error -> {type(e).__name__}: {e}",
        }
    return {
        "key": "kde",
        "name": "KDE Connect bridge (dormant fallback)",
        "status": "UP" if reachable else "OFF",
        "required": False,
        "detail": ("device reachable (D-Bus isReachable=true) — dormant, LINE is authoritative"
                   if reachable else
                   "device NOT reachable / unpaired — fine while LINE relay is the authoritative channel"),
    }


# ----------------------------------------------------------------- renderers

_STATUS_COLOR = {
    "UP": GREEN,
    "ON": GREEN,
    "SLIM": BLUE,
    "OFF": GRAY,
    "DOWN": RED,
    "DEGRADED": YELLOW,
    "TIMEOUT": YELLOW,
    "UNKNOWN": YELLOW,
}


def _verdict(rows: list[dict]) -> bool:
    gateway = next((r for r in rows if r["key"] == "gateway"), None)
    relay = next((r for r in rows if r["key"] == "otp_relay"), None)
    return bool(gateway and gateway["status"] == "UP" and relay and relay["status"] == "UP")


def _render_human(rows: list[dict], go: bool) -> None:
    print(f"\n{BOLD}{BLUE}================================================================{RESET}")
    print(f"{BOLD}{BLUE}  🧩 INVESTMENT HOMELAB: SERVICES STATUS (read-only){RESET}")
    print(f"{BOLD}{BLUE}================================================================{RESET}")
    for r in rows:
        color = _STATUS_COLOR.get(r["status"], YELLOW)
        tag = " [required]" if r.get("required") else ""
        print(f"\n{BOLD}{r['name']}{tag}{RESET}")
        print(f"   {color}{r['status']}{RESET} · {r['detail']}")
    verdict = f"{GREEN}GO — OTP/auth work can proceed{RESET}" if go else \
              f"{RED}NO-GO — fix the [required] services above{RESET}"
    print(f"\n{BOLD}{BLUE}================================================================{RESET}")
    print(f"  🏁 Verdict: {verdict}")
    print(f"{BOLD}{BLUE}================================================================{RESET}\n")


async def _collect_all() -> list[dict]:
    return [
        await collect_gateway(),
        collect_cloudflared(),
        await collect_otp_relay(),
        await collect_kdeconnect(),
        collect_in_gateway_daemons(),
        collect_mcp_server(),
    ]


def main() -> int:
    global GATEWAY_PORT

    parser = argparse.ArgumentParser(
        description="Read-only status of Investment Homelab services."
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--gateway-port", type=int, default=GATEWAY_PORT,
                        help=f"gateway port to probe (default: {GATEWAY_PORT})")
    args = parser.parse_args()

    GATEWAY_PORT = args.gateway_port

    rows = asyncio.run(_collect_all())
    go = _verdict(rows)

    if args.json:
        print(json.dumps({"verdict": "GO" if go else "NO-GO", "services": rows}, indent=2))
    else:
        _render_human(rows, go)
    return 0 if go else 1


if __name__ == "__main__":
    sys.exit(main())
