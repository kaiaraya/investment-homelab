#!/usr/bin/env python3
"""
Pre-Flight Readiness & Connectivity Inspector for Investment Homelab.
====================================================================
Quickly verifies all dependencies, hardware bridges, and broker states in <2 seconds
BEFORE running any tests or trading operations:
1. Backend Daemon (Uvicorn / FastAPI / MCP SSE)
2. Hardware Bridge (KDE Connect D-Bus to Android Mi 10T)
3. Krungsri TradeMan Session (Live)
4. Settrade Click2Win Session (Simulation)
5. Liberator WebTrade Session (Live)
6. Market Status (Open / Closed / Weekend)
7. Zombie Process Hygiene (Chrome / Playwright cleanup)

Broker sessions are reported with their OWN driver semantics (Broker Knowledge
Isolation). Liberator reuses the driver's real JWT-expiry guard via
app.brokers.liberator.session_health, and Krungsri reuses the shared storage-state
inspector via app.brokers.krungsri.session_health, so preflight never reports a
missing/stale session as "✅ exists" (LIB-RCA-007 / KSS-RCA-011).
"""

import sys
import os
import time
import socket
import subprocess
import urllib.request
import json
from datetime import datetime

# Ensure the repo root is importable when run directly (e.g.
# `python scripts/preflight_check.py`) so `app.*` modules resolve.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from app.core.config import settings
except Exception:  # preflight must still run even if app config cannot load
    settings = None

from app.brokers.liberator.session_health import session_health
from app.brokers.krungsri.session_health import session_file_info

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def check_port(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def check_backend_daemon():
    print(f"\n{BOLD}1. 🔌 Backend Services & MCP SSE Gateway:{RESET}")
    is_port_open = check_port("127.0.0.1", 8000)
    if not is_port_open:
        print(f"   {RED}❌ FastAPI Server (port 8000) is DOWN.{RESET}")
        print(f"      👉 Action: Run '.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload' or start as daemon.")
        return False

    # Check SSE endpoint
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/v1/session/status")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            status = data.get("status", "UNKNOWN")
            print(f"   {GREEN}✅ FastAPI Server & API:{RESET} RUNNING (Status: {status})")
            print(f"   {GREEN}✅ MCP SSE Gateway:{RESET} http://localhost:8000/sse (Tailscale: http://100.88.217.33:8000/sse)")
            return True
    except Exception as e:
        print(f"   {YELLOW}⚠️  Port 8000 open, but API health check returned: {e}{RESET}")
        return False


def check_kdeconnect_phone():
    print(f"\n{BOLD}2. 📱 Hardware Bridge (KDE Connect SMS OTP Relay):{RESET}")
    phone_ip = "100.119.166.62"
    target_id = "9507a3fd53f848da9135ebe6253db18a"

    # 1. Quick TCP socket probe to phone's KDE Connect port (1716) over Tailscale
    is_socket_open = check_port(phone_ip, 1716, timeout=1.0)

    # 2. Real-time D-Bus liveness (Invariant 8): the authoritative signal is the
    #    device's live `isReachable` property — the SAME signal the production driver
    #    (`kdeconnect_service.is_device_reachable()`) uses (single source of truth,
    #    LIB-RCA-007). `iconName`/`statusIconName` are UNRELIABLE: `iconName` reads
    #    'smartphonedisconnected' even while the phone is reachable (verified live
    #    2026-10-07). Ref KDE-RCA-008 (REVISED).
    dbus_reachable = False
    try:
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.kde.kdeconnect",
            "--object-path", f"/modules/kdeconnect/devices/{target_id}",
            "--method", "org.freedesktop.DBus.Properties.Get",
            "org.kde.kdeconnect.device", "isReachable",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        dbus_reachable = "true" in res.stdout.strip().lower()
    except Exception:
        dbus_reachable = False

    if is_socket_open and dbus_reachable:
        print(f"   {GREEN}✅ Android Phone (Mi 10T):{RESET} Socket + real-time D-Bus isReachable (device live).")
        print(f"   {YELLOW}👉 สำคัญ:{RESET} กรุณาเปิดแอป KDE Connect บนมือถือ Mi 10T ค้างไว้")
        print(f"      เพื่อให้ MIUI/Android ยอมให้ดึง SMS OTP เข้าสู่ระบบแบบ Real-time ทันที")
        return True
    elif is_socket_open and not dbus_reachable:
        print(f"   {RED}❌ Android Phone (Mi 10T):{RESET} Socket OPEN but D-Bus isReachable = false → แอป KDE Connect บนมือถือหลุด.")
        print(f"      👉 Action: เปิดแอป KDE Connect บนมือถือค้างไว้ แล้วรัน preflight ใหม่ (ห้าม trigger SMS OTP จนกว่าจะ connected)")
        return False
    else:
        print(f"   {RED}❌ Android Phone (Mi 10T):{RESET} Not reachable over Tailscale ({phone_ip}).")
        print(f"      �� Action: ตรวจสอบว่าเปิด Tailscale และแอป KDE Connect บน Mi 10T แล้วหรือยัง")
        return False


def _path(key: str, default: str) -> str:
    """Resolves a broker session path from settings, falling back to a default."""
    if settings is not None:
        try:
            value = getattr(settings, key)
            if value:
                return value
        except Exception:
            pass
    return default


def liberator_session_status(path: str) -> dict:
    """
    Browser-free Liberator session health (LIB-RCA-007).

    Reuses the driver's own JWT-expiry logic (app.brokers.liberator.session_health)
    so preflight and the driver can never disagree about a saved session.
    """
    return session_health(path)


def click2win_session_status(path: str) -> dict:
    """
    Click2Win is a SIMULATION broker (Settrade sandbox) with NO JWT auth token.

    There is no offline way to assert the session is still authenticated, so we
    report only file presence + age + cookie count — never a false "✅ active".
    Live validity is established at the auto web-login step (no SMS OTP).
    """
    status = {"exists": False, "age_seconds": None, "cookie_count": 0}
    if not os.path.exists(path):
        return status

    status["exists"] = True
    status["age_seconds"] = time.time() - os.path.getmtime(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        status["cookie_count"] = len(data.get("cookies", []))
    except Exception:
        pass
    return status


def krungsri_session_status(path: str) -> dict:
    """
    Browser-free Krungsri (TradeMan) session health (KSS-RCA-011 / LIB-RCA-007).

    Reuses the shared inspector (app.brokers.krungsri.session_health) that the MCP
    health payload and SessionSentinel also use, so preflight can never claim a
    missing/stale session is "✅ ready" again.
    """
    return session_file_info(path)


def check_krungsri_session():
    print(f"\n{BOLD}3. 🔑 Krungsri TradeMan Session (Live):{RESET}")
    kss_path = _path("SESSION_STATE_PATH", "data/session_state.json")
    info = krungsri_session_status(kss_path)
    if not info["exists"]:
        print(f"   {YELLOW}⚠️  Krungsri TradeMan:{RESET} No saved session ({kss_path} missing) — fresh login + SMS OTP required.")
        print(f"      👉 To Login: Run '.venv/bin/python -m app.brokers.krungsri.cli login' (Headless=False, OTP auto-fill)")
    elif info["needs_fresh_login"]:
        age_h = info["age_hours"] or 0.0
        print(f"   {RED}⚠️  Krungsri TradeMan:{RESET} Saved session EXPIRED/STALE ({age_h:.1f}h old, verdict={info['reason']}).")
        print(f"      👉 A fresh headed login (+ SMS OTP) is required before trading.")
    else:
        age_h = info["age_hours"] or 0.0
        print(f"   {BLUE}ℹ️  Krungsri TradeMan:{RESET} Saved cookies present ({info['cookie_count']} cookies, {age_h:.1f}h old, modified: {info['mtime_iso']}).")
        print(f"      No offline expiry marker on TradeMan SSO — live DOM check runs at connect.")


def check_click2win_session():
    print(f"\n{BOLD}4. 🎮 Settrade Click2Win Session (Simulation):{RESET}")
    c2w_path = _path("CLICK2WIN_SESSION_PATH", "data/click2win_session.json")
    status = click2win_session_status(c2w_path)
    if not status["exists"]:
        print(f"   {BLUE}ℹ️  Settrade Click2Win (SIMULATION):{RESET} No saved session — uses auto web login (no SMS OTP).")
    else:
        age_h = (status["age_seconds"] or 0) / 3600
        print(f"   {BLUE}ℹ️  Settrade Click2Win (SIMULATION):{RESET} Saved file present ({status['cookie_count']} cookies, {age_h:.1f}h old).")
        print(f"      No JWT on the sandbox — validity is confirmed live at the auto web-login step.")


def check_liberator_session():
    print(f"\n{BOLD}5. 🔑 Liberator WebTrade Session (Live):{RESET}")
    lib_path = _path("LIBERATOR_SESSION_PATH", "data/liberator_session.json")
    health = liberator_session_status(lib_path)
    if not health["exists"]:
        print(f"   {BLUE}ℹ️  Liberator WebTrade:{RESET} No saved session — fresh headed login required.")
    elif health["expired"]:
        ago = abs(health["remaining_seconds"] or 0)
        print(f"   {RED}⚠️  Liberator WebTrade:{RESET} Saved session EXPIRED (~{ago}s ago). Run headed login to refresh.")
    elif health["exp"] is None:
        print(f"   {BLUE}ℹ️  Liberator WebTrade:{RESET} Saved file present (no JWT expiry found). Live DOM check at connect.")
    else:
        print(f"   {GREEN}✅ Liberator WebTrade:{RESET} Session active (JWT valid for ~{health['remaining_seconds']}s).")


def check_market_regime():
    print(f"\n{BOLD}6. 🏛️ Market Schedule & Environment:{RESET}")
    now = datetime.now()
    weekday = now.strftime("%A")
    is_weekend = now.weekday() >= 5
    if is_weekend:
        print(f"   {YELLOW}🗓️  Today is {weekday} (Weekend):{RESET} SET Market is CLOSED.")
        print(f"   {GREEN}💡 Recommendation:{RESET} SBL audits and risk calculations will use High-Fidelity Cached Data.")
        print(f"      (No live broker order submission or SMS OTP required).")
    else:
        print(f"   {GREEN}🗓️  Today is {weekday} (Weekday):{RESET} Live market hours apply.")


def cleanup_stale_processes():
    print(f"\n{BOLD}7. 🧹 Process Hygiene:{RESET}")
    try:
        res = subprocess.run(["pgrep", "-f", "/opt/google/chrome/chrome"], capture_output=True, text=True)
        pids = [p for p in res.stdout.strip().splitlines() if p]
        if pids:
            print(f"   {YELLOW}⚠️  Detected {len(pids)} active/idle Chrome processes.{RESET}")
            if "--clean" in sys.argv:
                subprocess.run(["pkill", "-f", "/opt/google/chrome/chrome"])
                print(f"   {GREEN}✅ Cleaned up idle Chrome processes.{RESET}")
            else:
                print(f"      (Add '--clean' flag to automatically terminate idle Chrome instances).")
        else:
            print(f"   {GREEN}✅ No orphaned Chrome processes detected.{RESET}")
    except Exception:
        pass


def main():
    print(f"\n{BOLD}{BLUE}================================================================{RESET}")
    print(f"{BOLD}{BLUE}  🚀 INVESTMENT HOMELAB: PRE-FLIGHT READINESS CHECK {RESET}")
    print(f"{BOLD}{BLUE}================================================================{RESET}")

    t0 = time.time()
    b_ok = check_backend_daemon()
    k_ok = check_kdeconnect_phone()
    check_krungsri_session()
    check_click2win_session()
    check_liberator_session()
    check_market_regime()
    cleanup_stale_processes()
    duration = time.time() - t0

    print(f"\n{BOLD}{BLUE}================================================================{RESET}")
    print(f"  🏁 Check completed in {duration:.2f}s")
    print(f"{BOLD}{BLUE}================================================================{RESET}\n")


if __name__ == "__main__":
    main()
