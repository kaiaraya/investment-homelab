#!/usr/bin/env python3
"""
Investment Homelab - Master Startup & Sequential Readiness Orchestrator
========================================================================
Sequentially guarantees system readiness before opening the operations cockpit:
  Stage 1: Verify the OTP Relay is READY (LINE group "a14s homelab") — 2026-10-08
           - Relay = LINE Bot group push/receive. KDE Connect/Tailscale is DORMANT (kept, not deleted).
           - Required: LINE token จริง + LINE_SIMULATION_MODE=False + LINE_GROUP_ID
             + the FastAPI gateway listening on :8000 (webhook entry point — started here if down).
           - If not ready: escalate to LINE ('a14s homelab') with actionable steps and
             degrade + SKIP BOTH broker logins (Krungsri & Liberator share this OTP channel);
             continue to the Cockpit (no abort).
  Stage 2: Verify Krungsri TradeMan Session Gate (hard gate)
           - If valid session exists in data/session_state.json: Zero-OTP pass (<2s).
           - If missing or expired: Headed login on DISPLAY=:0, OTP typed into the LINE group.
           - If login fails: escalate to LINE ('a14s homelab') with actionable steps, then stop startup.
  Stage 3: Verify Liberator WebTrade Session Gate (optional, no headed login at startup)
           - Cached-session check only; otherwise prompts the user to 'Connect All Brokers' on /console.
  Stage 4: Verify FastAPI Gateway on Port 8000 & Launch /console Cockpit
           - Web Console is opened ONLY after the preceding readiness stages have resolved.
           - `--keep-open` keeps the windows open and (best-effort) moves the /console window
             to `--workspace` (default 2) via wmctrl so the broker OTP window stays unobstructed.
           - Displays ALL SYSTEMS GO banner and Terminal CLI Test Runner panel.
"""

import os
import sys

# Ensure project root is in sys.path when invoked directly as scripts/start_homelab.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import time
import socket
import signal
import asyncio
import logging
import subprocess
import urllib.request
from datetime import datetime
from typing import Optional

# ANSI Colors & Formatting
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"

# Fix 4: Truthful per-stage readiness for the final banner.
# Optimistic defaults so a stage that is intentionally skipped (--skip-*) is NOT
# reported as degraded; a stage only flips to False when it actually ran and failed.
STARTUP_STATUS: dict[str, bool] = {"kde": True, "krungsri": True, "liberator": True}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("HomelabStartup")

# Suppress overly noisy logs during startup
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

from app.core.config import settings
from app.services.kdeconnect_service import kdeconnect_service
from app.services.line_service import line_service
from app.services.otp_relay_readiness import otp_relay_readiness
from app.browser.auth_driver import auth_driver

# LINE group OTP relay (2026-10-08) — primary OTP channel
LINE_GROUP_NAME = "a14s homelab"


def check_tcp_port(host: str, port: int, timeout: float = 0.8) -> bool:
    """Quickly tests if a TCP port is open and listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def check_kde_live_transport(phone_ip: str = "100.119.166.62", port: int = 1716) -> tuple[bool, str]:
    """Detects a LIVE KDE Connect transport to the Mi 10T over EITHER physical route.

    The phone can reach this NUC by two transports (mirrors the real topology):
      * Home Wi-Fi : LAN subnet 192.168.1.x / 10.x
      * Tailscale  : 100.x.x.x (tunnels over Wi-Fi *or* mobile 4G/5G when away)

    A raw TCP probe to the Tailscale IP alone FALSE-NEGATIVES when the user is at home
    with Tailscale OFF but Wi-Fi still carrying KDE Connect (the SMS-OTP channel is fine).
    This inspects the live kernel socket table so BOTH transports are honoured.

    Invariant 8: inspects real TCP state only — NEVER the ``kdeconnect-cli`` cache.

    Returns:
        (found, description) — description e.g. "Home Wi-Fi (192.168.1.54:1716)".
    """
    # 1. Tailscale path: direct TCP probe to the phone's Tailscale address.
    if check_tcp_port(phone_ip, port, timeout=1.0):
        return True, f"Tailscale ({phone_ip}:{port})"

    # 2. Home Wi-Fi path: a live ESTABLISHED socket to the phone's LAN address.
    #    Excludes loopback and same-host (gsconnect) self-connections (local == remote IP).
    try:
        res = subprocess.run(["ss", "-tn"], capture_output=True, text=True, timeout=1.5)
        for line in res.stdout.splitlines():
            if f":{port}" not in line or "ESTAB" not in line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local = parts[3].replace("[::ffff:", "").replace("]", "")
            remote = parts[4].replace("[::ffff:", "").replace("]", "")
            remote_ip = remote.rsplit(":", 1)[0]
            local_ip = local.rsplit(":", 1)[0]
            if not remote_ip or remote_ip in ("127.0.0.1", "::1") or remote_ip == local_ip:
                continue
            if remote_ip.startswith("192.168.") or remote_ip.startswith("10."):
                return True, f"Home Wi-Fi ({remote})"
    except Exception:
        pass

    return False, "no live transport"


def send_desktop_notification(title: str, message: str, urgency: str = "normal"):
    """Pushes a local desktop notification via notify-send if available."""
    try:
        subprocess.run(["notify-send", "-u", urgency, title, message], timeout=2.5, capture_output=True)
    except Exception:
        pass


# ==============================================================================
# STAGE 1: Check KDE Connect Hardware Bridge
# ==============================================================================
async def stage1_check_kdeconnect(max_wait_seconds: int = 180) -> bool:
    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_CYAN}📱 [STAGE 1/4] Checking Hardware Bridge (KDE Connect & Tailscale)...{C_RESET}")
    print("=" * 75)

    target_id = getattr(settings, "KDECONNECT_DEVICE_ID", "9507a3fd53f848da9135ebe6253db18a")
    phone_ip = getattr(settings, "KDECONNECT_PHONE_IP", "100.119.166.62")

    async def _probe_live() -> bool:
        nonlocal last_transport
        # 1. LIVE transport probe over EITHER path (Home Wi-Fi LAN *or* Tailscale).
        #    A Tailscale-IP-only TCP probe FALSE-NEGATIVES when the user is at home with
        #    Tailscale OFF but Wi-Fi still carrying KDE Connect (the OTP channel is fine).
        transport_ok, last_transport = check_kde_live_transport(phone_ip, 1716)
        
        # 2. Strict D-Bus reachability (Invariant 8): the authoritative signal is the
        #    live `isReachable` property — the SAME signal the production driver
        #    (`kdeconnect_service.is_device_reachable()`) uses (single source of truth).
        #    `iconName` is deliberately NOT consulted: it reads 'smartphonedisconnected'
        #    even while the phone is reachable (verified live 2026-10-07; KDE-RCA-008).
        dbus_connected = False
        try:
            cmd = [
                "gdbus", "call", "--session",
                "--dest", "org.kde.kdeconnect",
                "--object-path", f"/modules/kdeconnect/devices/{target_id}",
                "--method", "org.freedesktop.DBus.Properties.Get",
                "org.kde.kdeconnect.device", "isReachable"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.2)
            if "true" in res.stdout.strip().lower():
                dbus_connected = True
        except Exception:
            pass

        # 3. Notification/SMS bridge liveness (Fix 3): the SMS OTP path is only usable
        #    when the KDE Connect notifications plugin is actually exposed on D-Bus.
        #    This prevents a false-positive "ready" while OTP interception is dead.
        notifications_ready = False
        try:
            cmd_notif = [
                "gdbus", "call", "--session",
                "--dest", "org.kde.kdeconnect",
                "--object-path", f"/modules/kdeconnect/devices/{target_id}/notifications",
                "--method", "org.freedesktop.DBus.Introspectable.Introspect"
            ]
            res_notif = subprocess.run(cmd_notif, capture_output=True, text=True, timeout=1.5)
            notifications_ready = (
                res_notif.returncode == 0 and "activeNotifications" in res_notif.stdout
            )
        except Exception:
            notifications_ready = False

        return transport_ok and dbus_connected and notifications_ready

    last_transport = "no live transport"

    # Initial probe
    if await _probe_live():
        print(f" {C_GREEN}✅ Hardware Bridge ONLINE:{C_RESET} Xiaomi Mi 10T is active ({last_transport}, D-Bus + SMS/OTP bridge verified)")
        await _ping_device_confirmation(target_id)
        return True

    # Phone is not connected or sleeping — the SMS OTP bridge is unusable.
    alert_title = "⚠️ Investment Homelab: Action Required"
    alert_msg = (
        "ตรวจพบมือถือ Mi 10T ยังไม่เชื่อมต่อ KDE Connect หรือ Tailscale\n"
        "👉 กรุณาเปิด Tailscale และเปิดแอป KDE Connect บนมือถือค้างไว้ เพื่อให้ระบบรับ SMS OTP อัตโนมัติ"
    )
    print(f"\n{C_YELLOW}⚠️  KDE Connect Disconnected / Mobile Phone Asleep!{C_RESET}")
    print(f"   • Transports: Home Wi-Fi (192.168.1.x) & Tailscale ({phone_ip}:1716) — both Unreachable")
    print(f"   • Device ID: {target_id}")
    print(f"   👉 {C_BOLD}กรุณาเปิด Tailscale และเปิดแอป KDE Connect บนมือถือ Mi 10T ค้างไว้{C_RESET}")

    async def _push_troubleshooting(phase: str) -> None:
        """Escalates an actionable SMS-OTP-bridge troubleshooting alert to LINE ('a14s homelab').

        Solo OTP channel: KDE Connect is the ONLY path that reads Krungsri's 2FA SMS OTP,
        so a dead bridge is a hard blocker — the user must fix it on the phone.
        """
        transport_ok, transport_desc = check_kde_live_transport(phone_ip, 1716)
        transport_state = "OPEN" if transport_ok else "CLOSED"
        try:
            print(f"   📲 Sending troubleshooting alert to 'a14s homelab' LINE Bot... ({phase})")
            await line_service.send_system_notification(
                title="SMS OTP Bridge OFFLINE — อ่าน SMS OTP จากมือถือไม่ได้",
                message=(
                    f"ตรวจพบว่า KDE Connect ไม่พร้อมใช้งาน ({phase})\n"
                    "ระบบอ่าน SMS OTP จากมือถือ Mi 10T ไม่ได้ จึงยังไม่สามารถล็อกอิน Krungsri "
                    "อัตโนมัติได้ (Krungsri ส่ง OTP ทาง SMS และนี่คือช่องทางเดียวที่ระบบใช้รับรหัส)\n\n"
                    f"• Transport          : {transport_desc} (TCP {transport_state})\n"
                    f"• KDE Connect ID : {target_id}"
                ),
                action_required=(
                    "1) เปิดแอป Tailscale บนมือถือ แล้วกด Connect\n"
                    "2) เปิดแอป KDE Connect บนมือถือค้างไว้ (ห้ามปัดปิด)\n"
                    f"3) ตรวจว่าโทรศัพท์เข้าถึงได้ที่ {phone_ip}:1716\n"
                    "4) กลับมากด Connect All Brokers ที่ /console อีกครั้ง"
                ),
                severity="CRITICAL",
            )
            print(f"   {C_GREEN}✅ Troubleshooting alert dispatched to LINE.{C_RESET}")
        except Exception as e:
            logger.warning(f"Could not push LINE troubleshooting alert: {e}")

    await _push_troubleshooting("initial probe failed")

    # Push Desktop Notification
    send_desktop_notification(alert_title, alert_msg, urgency="critical")

    # Polling Loop with Spinner
    start_time = time.time()
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0

    print(f"\n⏳ รอการเชื่อมต่อจากมือถือ Mi 10T (Auto-polling ทุก 2 วินาที)...")
    while time.time() - start_time < max_wait_seconds:
        idx += 1
        elapsed = int(time.time() - start_time)
        spin_char = spinner[idx % len(spinner)]
        sys.stdout.write(f"\r   {C_CYAN}{spin_char}{C_RESET} Waiting for Mi 10T ({elapsed}s / {max_wait_seconds}s) - กรุณาเปิดแอป KDE Connect บนมือถือ... ")
        sys.stdout.flush()

        await asyncio.sleep(2.0)

        if await _probe_live():
            print(f"\n\n {C_GREEN}{C_BOLD}🎉 Xiaomi Mi 10T CONNECTED SUCCESSFULLY!{C_RESET}")
            print(f"   • Transport: {last_transport}")
            print(f"   • D-Bus: Smartphone Linked")
            await _ping_device_confirmation(target_id)
            return True

    print(f"\n\n{C_RED}❌ Error: Timeout waiting for KDE Connect hardware bridge.{C_RESET}")
    await _push_troubleshooting(f"wait timeout after {max_wait_seconds}s")
    return False


async def _ping_device_confirmation(target_id: str):
    """Sends a ping vibration to the phone to acknowledge connection."""
    try:
        subprocess.run(
            ["kdeconnect-cli", "-d", target_id, "--ping-msg", "Investment Homelab Bridge Active"],
            capture_output=True, timeout=2.0
        )
        print(f"   📳 Sent verification ping to Mi 10T.")
    except Exception:
        pass


async def push_krungsri_login_alert(phase: str, detail: str) -> None:
    """Escalates a Krungsri TradeMan login failure to LINE ('a14s homelab').

    Krungsri login is a HARD gate in the startup sequence: without a valid TradeMan
    session the system cannot trade, so the operator must act (fix credentials,
    complete the SMS OTP, or restore connectivity). Mirrors Stage 1's nested
    ``_push_troubleshooting`` but lives at module level so it can be unit-tested
    directly (Invariant 6). Never raises: an escalation-transport failure must not
    mask the original login failure.
    """
    try:
        print(f"   📲 Sending Krungsri login-failure alert to 'a14s homelab' LINE Bot... ({phase})")
        await line_service.send_system_notification(
            title="Krungsri TradeMan LOGIN FAILED — ล็อกอินไม่สำเร็จ",
            message=(
                f"ระบบล็อกอิน Krungsri TradeMan ไม่สำเร็จ ({phase})\n"
                f"• รายละเอียด: {detail}\n\n"
                "ระบบหยุด Startup ไว้ (hard gate) เพราะยังไม่สามารถเทรดได้หากไม่ล็อกอินสำเร็จ"
            ),
            action_required=(
                "1) ตรวจ KRUNGSRI_USERNAME / KRUNGSRI_PASSWORD ใน .env\n"
                "2) ตรวจว่าได้รับ SMS OTP และเปิดแอป KDE Connect ค้างไว้บนมือถือ\n"
                "3) ตรวจอินเทอร์เน็ต / TradeMan ไม่ล่ม\n"
                "4) กลับมารัน ./start_homelab.sh ใหม่ (หรือใช้ --force-fresh)"
            ),
            severity="CRITICAL",
        )
        print(f"   {C_GREEN}✅ Krungsri login-failure alert dispatched to LINE.{C_RESET}")
    except Exception as e:
        logger.warning(f"Could not push Krungsri login-failure LINE alert: {e}")


# ==============================================================================
# STAGE 2: Krungsri TradeMan Session Gate
# ==============================================================================
async def stage2_verify_krungsri_session(force_fresh: bool = False) -> bool:
    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_CYAN}🔑 [STAGE 2/4] Verifying Krungsri TradeMan Authentication...{C_RESET}")
    print("=" * 75)

    state_path = getattr(settings, "SESSION_STATE_PATH", "data/session_state.json")
    has_state_file = os.path.exists(state_path)

    # Fast-path check: Existing session state validation
    if has_state_file and not force_fresh:
        print(f" • Checking saved session state in {state_path}...")
        try:
            # Launch minimal browser to verify DOM #dropDownAccountPort
            await auth_driver.launch_browser(resume_state=True)
            if await auth_driver.verify_saved_session():
                print(f" {C_GREEN}{C_BOLD}✅ Krungsri TradeMan Active Session Verified! (Zero-OTP Pass <2s){C_RESET}")
                print(f"   • Status: {auth_driver.status}")
                print(f"   • URL:    {auth_driver.current_url or 'https://trademan.in.th/Portfolio'}")
                await auth_driver.close()
                return True
            else:
                print(f" {C_YELLOW}⚠️ Saved session expired. Proceeding with fresh automated login...{C_RESET}")
                await auth_driver.close()
        except Exception as e:
            print(f" {C_YELLOW}⚠️ Session check notice: {e}. Initiating fresh login...{C_RESET}")
            try:
                await auth_driver.close()
            except Exception:
                pass

    # Fresh Automated Login required
    username = settings.KRUNGSRI_USERNAME
    password = settings.KRUNGSRI_PASSWORD

    if not username or not password:
        print(f" {C_RED}❌ Error: KRUNGSRI_USERNAME or KRUNGSRI_PASSWORD is not configured in .env!{C_RESET}")
        await push_krungsri_login_alert(
            "missing credentials",
            "KRUNGSRI_USERNAME / KRUNGSRI_PASSWORD is not configured in .env",
        )
        return False

    print(f" • Initiating Headed Login for account {C_BOLD}{username[:3]}***{C_RESET} on DISPLAY=:0...")
    settings.PLAYWRIGHT_HEADLESS = False
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    login_task = asyncio.create_task(
        auth_driver.login(
            username=username,
            password=password,
            timeout_otp=settings.OTP_TIMEOUT_SECONDS,
            force_fresh=True
        )
    )

    announced_ref = False
    while not login_task.done():
        await asyncio.sleep(0.5)
        if auth_driver.status == "AWAITING_OTP" and not announced_ref:
            ref_code = auth_driver.current_ref or "Pending"
            announced_ref = True
            print("\n" + "-" * 70)
            print(f"{C_BOLD}{C_YELLOW}📲 2FA SMS OTP REQUIRED BY KRUNGSRI!{C_RESET}")
            print(f" • Reference Code: {C_BOLD}{C_CYAN}[Ref: {ref_code}]{C_RESET}")
            print(f" • 📱 Auto-listening via KDE Connect on Android Mi 10T...")
            print(f" • 💻 (You may also type OTP in the opened Chrome window or here in terminal)")
            print("-" * 70)

    try:
        login_res = await login_task
        if login_res.success:
            print(f"\n {C_GREEN}{C_BOLD}🎉 KRUNGSRI TRADEMAN LOGIN SUCCESSFUL!{C_RESET}")
            print(f"   • Active Tab URL: {auth_driver.current_url}")
            print(f"   • Session state saved to {state_path}")
            await auth_driver.close()
            return True
        else:
            print(f"\n {C_RED}❌ Login failed: {login_res.message}{C_RESET}")
            await push_krungsri_login_alert("login rejected", login_res.message or "unknown login error")
            await auth_driver.close()
            return False
    except Exception as e:
        print(f"\n {C_RED}❌ Login exception: {e}{C_RESET}")
        await push_krungsri_login_alert("login exception", str(e))
        try:
            await auth_driver.close()
        except Exception:
            pass
        return False


# ==============================================================================
# STAGE 3: Liberator WebTrade Session Gate
# ==============================================================================
async def stage3_verify_liberator_session(force_fresh: bool = False) -> bool:
    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_CYAN}🛡️ [STAGE 3/4] Verifying Liberator WebTrade Authentication...{C_RESET}")
    print("=" * 75)

    from app.brokers.liberator.driver import liberator_driver

    state_path = liberator_driver.session_path
    has_state_file = os.path.exists(state_path)

    # Fast-path check: Existing session validation
    if has_state_file and not force_fresh:
        print(f" • Checking saved Liberator session state in {state_path}...")
        try:
            if await liberator_driver.verify_saved_session():
                print(f" {C_GREEN}{C_BOLD}✅ Liberator WebTrade Active Session Verified! (Zero-OTP Pass <2s){C_RESET}")
                print(f"   • Status: {liberator_driver.status}")
                print(f"   • URL:    {liberator_driver.current_url or 'https://webtrade.liberator.co.th/Portfolio'}")
                await liberator_driver.close()
                return True
            else:
                print(f" {C_YELLOW}⚠️ Saved Liberator session is invalid/expired. It will be discarded for a fresh session.{C_RESET}")
                await liberator_driver.close()
        except Exception as e:
            print(f" {C_YELLOW}⚠️ Liberator check notice: {e}. Initiating fresh login...{C_RESET}")
            try:
                await liberator_driver.close()
            except Exception:
                pass

    # No headed login at startup: use the 'Connect All Brokers' button on /console instead.
    print(f" {C_YELLOW}⚠️  LIBERATOR OFFLINE: No valid (unexpired) Liberator session was found.")
    print(f"      • Session file : {state_path} ({'present' if has_state_file else 'missing'})")
    print(f"      • Skipping headed login at startup (anti-2FA-SMS policy).")
    print(f"      • 👉 Use 'Connect All Brokers' on /console to authenticate when needed.{C_RESET}")
    return False


# ==============================================================================
# STAGE 1 (2026-10-08) — OTP Relay Readiness (LINE group, replaces KDE/D-Bus gate)
# ==============================================================================
def ensure_gateway_running(server_port: int = 8000, dev: bool = False) -> Optional[subprocess.Popen]:
    """
    Ensure the FastAPI gateway (uvicorn app.main:app) is listening on `server_port`.

    Single source of truth for gateway startup — used by Stage 1 (the LINE webhook MUST
    be reachable before any SMS OTP is triggered) and by Stage 4 (console launch).
    Returns the Popen handle when WE started it, or None when it was already running.
    """
    if check_tcp_port("127.0.0.1", server_port, timeout=0.8):
        print(f" {C_GREEN}✅ FastAPI Gateway is already ACTIVE on port {server_port}.{C_RESET}")
        return None

    print(f" • Starting FastAPI / Uvicorn Server on port {server_port}{' (dev --reload)' if dev else ''}...")
    server_cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0",
        "--port", str(server_port),
    ]
    if dev:
        server_cmd.append("--reload")

    server_process = subprocess.Popen(
        server_cmd,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    print(" • Waiting for FastAPI health endpoint to come online...")
    for _ in range(24):
        time.sleep(0.5)
        if check_tcp_port("127.0.0.1", server_port, timeout=0.5):
            print(f" {C_GREEN}✅ FastAPI Gateway is UP on port {server_port}.{C_RESET}")
            return server_process

    print(f" {C_RED}❌ Error: Server failed to start on port {server_port}!{C_RESET}")
    return server_process


def move_window_to_workspace(title_substring: str, workspace: int = 2) -> bool:
    """
    Best-effort: move the first X11 window whose title matches `title_substring` to
    `workspace` via wmctrl. Returns True only when wmctrl actually reported success
    (Anti-Mock: never claim a move that did not happen).
    """
    try:
        subprocess.run(
            ["wmctrl", "-a", title_substring],
            capture_output=True, timeout=4, check=False,
        )
        res = subprocess.run(
            ["wmctrl", "-r", title_substring, "-t", str(workspace)],
            capture_output=True, text=True, timeout=4, check=False,
        )
        return res.returncode == 0
    except FileNotFoundError:
        print(f" {C_YELLOW}⚠️  wmctrl not installed — ข้ามการย้ายหน้าต่างไป workspace {workspace}{C_RESET}")
        return False
    except Exception as e:
        print(f" {C_YELLOW}⚠️  wmctrl move failed: {e}{C_RESET}")
        return False


async def stage1_check_otp_relay(server_port: int = 8000, dev: bool = False) -> bool:
    """
    Gate หลัก: OTP relay ต้องพร้อมก่อนจะยิง SMS OTP ใด ๆ (Invariant 9 — LINE variant).

    Relay = LINE group "a14s homelab":
      1. LINE configured (token จริง / SIMULATION ปิด / LINE_GROUP_ID ตั้งแล้ว)
      2. FastAPI gateway listening :8000 — จุดรับ webhook จาก cloudflared tunnel
         ถ้ายังปิดอยู่ จะ "เปิดให้เลย" ที่นี่ เพราะคำตอบ OTP เข้าทาง gateway เท่านั้น

    ตรวจผ่าน `otp_relay_readiness.check()` — ตัวเดียวกับที่ auth_driver /
    liberator_driver / daily_readiness ใช้ (single source of truth, ไม่มี gate ลวง)
    """
    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_CYAN}📱 [STAGE 1/4] Checking OTP Relay (LINE: กลุ่ม '{LINE_GROUP_NAME}' หรือแชท 1:1)...{C_RESET}")
    print("=" * 75)

    # The gateway must be listening for the webhook to receive the OTP reply.
    ensure_gateway_running(server_port=server_port, dev=dev)

    readiness = await otp_relay_readiness.check(require_gateway=True)
    if readiness.ready:
        print(f" {C_GREEN}✅ OTP Relay ONLINE:{C_RESET} channel={readiness.channel} | "
              f"webhook={getattr(settings, 'LINE_PUBLIC_WEBHOOK_URL', '')}")
        try:
            await line_service.push_message(
                f"✅ [{LINE_GROUP_NAME}] OTP relay พร้อม — เริ่มเตรียม session ได้\n"
                "(เมื่อมีคำขอ OTP ระบบจะแจ้งในกลุ่มนี้ ให้พิมพ์รหัส 6 หลักตอบกลับ)"
            )
        except Exception:
            pass
        return True

    print(f" {C_RED}❌ OTP Relay NOT READY:{C_RESET} {readiness.reason}")
    for k, v in readiness.details.items():
        print(f"    • {k} = {v}")

    steps = (
        f"1) เปิด backend : {sys.executable} -m uvicorn app.main:app --host 0.0.0.0 --port {server_port}\n"
        f"2) ตรวจ cloudflared tunnel → {getattr(settings, 'LINE_PUBLIC_WEBHOOK_URL', '')}\n"
        f"3) พิมพ์ข้อความ 1 ครั้งในกลุ่ม LINE '{LINE_GROUP_NAME}' หรือในแชท 1:1 กับ OA "
        f"(auto-capture LINE_GROUP_ID / LINE_ADMIN_USER_ID)"
    )
    print(f" {C_YELLOW}👉 HITL:{C_RESET}\n{steps}")

    try:
        await line_service.send_system_notification(
            f"OTP relay ({LINE_GROUP_NAME}) ไม่พร้อม",
            readiness.reason,
            action_required=steps,
            severity="CRITICAL",
        )
    except Exception:
        pass
    send_desktop_notification(
        "⚠️ Investment Homelab: OTP Relay Not Ready",
        f"{readiness.reason}\n{steps}",
        urgency="critical",
    )
    return False


# ==============================================================================
# STAGE 4: Start Server & Launch /console Cockpit
# ==============================================================================
def stage4_launch_server_and_console(server_port: int = 8000, dev: bool = False,
                                     keep_open: bool = False, workspace: int = 2) -> subprocess.Popen:
    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_CYAN}🚀 [STAGE 4/4] Launching Operations Cockpit & Services...{C_RESET}")
    print("=" * 75)

    is_running = check_tcp_port("127.0.0.1", server_port, timeout=0.8)
    server_process = None

    if not is_running:
        print(f" • Starting FastAPI / Uvicorn Server on port {server_port}{' (dev --reload)' if dev else ''}...")
        venv_python = sys.executable
        server_cmd = [
            venv_python, "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(server_port),
        ]
        if dev:
            server_cmd.append("--reload")
        server_process = subprocess.Popen(server_cmd)
        
        # Wait up to 10s for server to respond
        print(" • Waiting for FastAPI health endpoint to come online...")
        healthy = False
        for _ in range(20):
            time.sleep(0.5)
            if check_tcp_port("127.0.0.1", server_port, timeout=0.5):
                healthy = True
                break
        
        if not healthy:
            print(f" {C_RED}❌ Error: Server failed to start on port {server_port}!{C_RESET}")
            return None
    else:
        print(f" {C_GREEN}✅ FastAPI Gateway is already ACTIVE on port {server_port}.{C_RESET}")

    # Launch Web Console strictly now that the preceding readiness stages have resolved
    console_url = f"http://localhost:{server_port}/console"
    print(f"\n {C_GREEN}{C_BOLD}🌐 OPENING OPERATIONS COCKPIT: {console_url}{C_RESET}")
    # Open exactly once, non-blocking. (Previously xdg-open could exceed a 3s timeout on a
    # cold Chrome start and the webbrowser.open fallback opened a duplicate tab.)
    try:
        subprocess.Popen(
            ["xdg-open", console_url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception as e:
        print(f" {C_YELLOW}⚠️ Could not open browser automatically ({e}). Open {console_url} manually.{C_RESET}")

    # Fix 4: Surface the real readiness of each stage instead of an unconditional banner.
    degraded = [name for name, ok in STARTUP_STATUS.items() if not ok]
    if not degraded:
        send_desktop_notification(
            "🟢 Investment Homelab Ready",
            "KDE Connect Online | Krungsri Authenticated | Operations Cockpit Live",
            urgency="normal"
        )
    else:
        send_desktop_notification(
            "🟡 Investment Homelab Ready (Degraded)",
            f"Not ready: {', '.join(degraded)} | Cockpit Live — use /console to reconnect",
            urgency="normal"
        )

    # Print Readiness Summary Banner and CLI Runner Cheat Sheet
    print("\n" + "=" * 75)
    if not degraded:
        print(f"{C_BOLD}{C_GREEN}🟢 ALL SYSTEMS GO! Investment Homelab Cockpit is Ready for Use{C_RESET}")
    else:
        print(f"{C_BOLD}{C_YELLOW}🟡 HOMELAB READY WITH DEGRADED SERVICES: {', '.join(d.upper() for d in degraded)} NOT READY{C_RESET}")
        print(f"{C_YELLOW}   👉 ใช้ปุ่ม 'Connect All Brokers' บน http://localhost:{server_port}/console เพื่อเชื่อมต่อใหม่{C_RESET}")
    print("=" * 75)
    print(f" • Web Console : {C_CYAN}http://localhost:{server_port}/console{C_RESET}")
    print(f" • Swagger Docs: {C_CYAN}http://localhost:{server_port}/docs{C_RESET}")
    print(f" • Remote MCP  : {C_CYAN}http://100.88.217.33:{server_port}/sse{C_RESET}")
    print("-" * 75)
    print(f"{C_BOLD}💻 Terminal CLI Test Runner (Copy & Paste to Run in Another Terminal):{C_RESET}")
    print(f"   1. SBL Live Audit      : {C_YELLOW}python -m scripts.krungsri.test_sbl_live_audit{C_RESET}")
    print(f"   2. Homelab Pre-Flight  : {C_YELLOW}python scripts/preflight_check.py{C_RESET}")
    print(f"   3. E2E AutoTrade Flow  : {C_YELLOW}python -m scripts.shared.run_autotrade_e2e_test{C_RESET}")
    print(f"   4. Live Action Exit    : {C_YELLOW}python -m scripts.krungsri.execute_live_action_exit{C_RESET}")
    print(f"   5. Krungsri Status     : {C_YELLOW}python -m app.brokers.krungsri.cli status{C_RESET}")
    print(f"   6. Liberator Status    : {C_YELLOW}python -m app.brokers.liberator.cli status{C_RESET}")
    print(f"   7. Click2Win Status    : {C_YELLOW}python -m app.brokers.click2win.cli status{C_RESET}")
    print("=" * 75)
    print(f"{C_DIM}💡 Server is running. Press Ctrl+C in this terminal to stop the server.{C_RESET}\n")

    if keep_open:
        # --keep-open: keep the cockpit window open and move it out of the broker window's way
        # (best-effort via wmctrl — truthful report, never a fake ✅; Anti-Mock Guardrail).
        time.sleep(2.0)
        moved = move_window_to_workspace("Investment Homelab", workspace=workspace)
        if moved:
            print(f" {C_GREEN}✅ --keep-open: ย้ายหน้าต่าง /console ไป workspace {workspace} แล้ว{C_RESET}")
        else:
            print(f" {C_YELLOW}⚠️  --keep-open: ย้ายหน้าต่างอัตโนมัติไม่สำเร็จ{C_RESET}")
            print(f" {C_DIM}    ย้ายเองด้วย: wmctrl -r :ACTIVE: -t {workspace}"
                  f"  (ติดตั้ง: sudo apt install wmctrl){C_RESET}")
        print(f" {C_DIM}💡 --keep-open: คงหน้าต่างทั้งหมดไว้ — ระบบจะไม่ปิดให้เอง{C_RESET}")

    return server_process


def resolve_startup_plan(
    kde_ok: Optional[bool],
    skip_login: bool,
    skip_liberator: bool,
) -> dict[str, bool]:
    """Decide which broker-login stages to run given the KDE-Connect gate result.

    kde_ok:
        True  -> mobile bridge online; run the broker logins as requested by the flags.
        False -> mobile bridge OFFLINE. KDE Connect is the ONLY channel the system uses
                 to read the 2FA SMS OTP, so a fresh broker login is impossible: SKIP
                 both login stages and mark kde/krungsri/liberator DEGRADED (a real
                 failure, NOT an intentional --skip-*).
        None  -> Stage 1 was skipped via --skip-kde; run the logins as requested by flags.

    Returns a dict with:
        kde_ready          : value to store in STARTUP_STATUS["kde"]
        run_krungsri       : whether Stage 2 (Krungsri login) should execute
        run_liberator      : whether Stage 3 (Liberator session) should execute
        degrade_krungsri   : whether to mark STARTUP_STATUS["krungsri"] = False
        degrade_liberator  : whether to mark STARTUP_STATUS["liberator"] = False
    """
    if kde_ok is False:
        return {
            "kde_ready": False,
            "run_krungsri": False,
            "run_liberator": False,
            "degrade_krungsri": True,
            "degrade_liberator": True,
        }

    return {
        "kde_ready": True,
        "run_krungsri": not skip_login,
        "run_liberator": not skip_liberator,
        "degrade_krungsri": False,
        "degrade_liberator": False,
    }


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def run_services_status(port: int) -> int:
    """Delegate to scripts/services_status.py (READ-ONLY). Returns its verdict code."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services_status.py")
    return subprocess.call([sys.executable, script, "--gateway-port", str(port)])


def main():
    parser = argparse_helper()
    args = parser.parse_args()

    # `--services` is a READ-ONLY selector: it reports which services are up/down by
    # delegating to scripts/services_status.py (single source of truth) and exits with
    # its verdict code (0=GO, 1=NO-GO). Nothing is started, stopped, or mutated.
    if args.services:
        sys.exit(run_services_status(args.port))

    print("\n" + "=" * 75)
    print(f"{C_BOLD}{C_MAGENTA} ⚡ INVESTMENT HOMELAB - SEQUENTIAL STARTUP ORCHESTRATOR{C_RESET}")
    print("=" * 75)

    # 1. Stage 1: OTP Relay Readiness (MANDATORY OTP-readiness gate — LINE variant, 2026-10-08).
    #    The LINE group "a14s homelab" is the channel the system uses to receive the 2FA OTP
    #    for BOTH Krungsri and Liberator. Stage 1 also guarantees the FastAPI gateway is
    #    listening (the webhook entry point) BEFORE any SMS OTP is triggered. If the relay is
    #    down we do NOT hard-abort; we skip the broker logins (degrade + continue) so the
    #    Cockpit still comes up for manual remediation. resolve_startup_plan() decides this.
    relay_ok: Optional[bool] = None
    if not args.skip_kde:
        relay_ok = asyncio.run(stage1_check_otp_relay(server_port=args.port, dev=args.dev))
    else:
        print(f"\n{C_YELLOW}⚠️  Skipping Stage 1 (OTP relay check) via --skip-relay/--skip-kde.{C_RESET}")

    plan = resolve_startup_plan(relay_ok, args.skip_login, args.skip_liberator)
    STARTUP_STATUS["kde"] = plan["kde_ready"]

    # 2. Stage 2: Krungsri Login Check (hard gate when it actually RUNS)
    if plan["run_krungsri"]:
        login_ok = asyncio.run(stage2_verify_krungsri_session(force_fresh=args.force_fresh))
        STARTUP_STATUS["krungsri"] = login_ok
        if not login_ok:
            print(f"{C_RED}Aborting startup because Krungsri TradeMan session could not be established.{C_RESET}")
            sys.exit(1)
    else:
        if plan["degrade_krungsri"]:
            STARTUP_STATUS["krungsri"] = False
            print(f"\n{C_YELLOW}📵  OTP relay OFFLINE — skipping Krungsri TradeMan login (degraded).{C_RESET}")
        else:
            print(f"\n{C_YELLOW}⚠️  Skipping Stage 2 (Krungsri Login) as requested by --skip-login.{C_RESET}")

    # 3. Stage 3: Liberator WebTrade Session Check (independent, optional, no headed login)
    if plan["run_liberator"]:
        liberator_ok = asyncio.run(stage3_verify_liberator_session(force_fresh=args.force_fresh))
        STARTUP_STATUS["liberator"] = liberator_ok
        if not liberator_ok:
            print(f"{C_YELLOW}⚠️ Notice: Liberator session could not be verified. Continuing...{C_RESET}")
    else:
        if plan["degrade_liberator"]:
            STARTUP_STATUS["liberator"] = False
            print(f"\n{C_YELLOW}📵  OTP relay OFFLINE — skipping Liberator session check (degraded).{C_RESET}")
        else:
            print(f"\n{C_YELLOW}⚠️  Skipping Stage 3 (Liberator) as requested by --skip-liberator.{C_RESET}")

    # 4. Stage 4: Launch Server & Open /console
    server_proc = stage4_launch_server_and_console(
        server_port=args.port, dev=args.dev,
        keep_open=args.keep_open, workspace=args.workspace,
    )

    # Handle Graceful Exit
    def _sig_handler(sig, frame):
        print(f"\n\n{C_YELLOW}🛑 Stopping Investment Homelab Services...{C_RESET}")
        if server_proc and server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                server_proc.kill()
        print(f"{C_GREEN}✅ All services stopped gracefully.{C_RESET}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    # If we started the server subprocess, wait on it; otherwise idle wait
    if server_proc:
        try:
            server_proc.wait()
        except KeyboardInterrupt:
            _sig_handler(None, None)
    else:
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            _sig_handler(None, None)


def argparse_helper():
    import argparse
    parser = argparse.ArgumentParser(description="Investment Homelab Sequential Startup Orchestrator")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--force-fresh", action="store_true", help="Force fresh Krungsri login even if saved session exists")
    parser.add_argument("--skip-kde", "--skip-relay", dest="skip_kde", action="store_true",
                        help="Skip the Stage 1 OTP relay readiness check (legacy name: --skip-kde)")
    parser.add_argument("--skip-login", action="store_true", help="Skip Krungsri login check")
    parser.add_argument("--skip-liberator", action="store_true", help="Skip Liberator session check")
    parser.add_argument("--dev", action="store_true", help="Run uvicorn with --reload (development only)")
    parser.add_argument("--keep-open", action="store_true",
                        help="Keep the cockpit window open and move it to --workspace via wmctrl")
    parser.add_argument("--workspace", type=int, default=2,
                        help="Target X11 workspace for --keep-open (default: 2)")
    parser.add_argument("--services", action="store_true",
                        help="READ-ONLY: print the services status report and exit "
                             "(0=GO, 1=NO-GO) — starts nothing")
    return parser


if __name__ == "__main__":
    main()
