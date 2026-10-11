#!/usr/bin/env python3
"""
Daily Readiness Skill Runner — Investment Homelab
=================================================
คำสั่งเดียวที่ใช้ทุกวัน: **เตรียมความพร้อม OTP Relay (LINE group "a14s homelab") +
Broker Sessions** แล้วคืน GO / NO-GO (exit code) เพื่อให้ไปทดสอบ pillar อื่นได้ทันที

Design (Loop Engineering / Single Source of Truth):
  * OTP relay      -> app.services.otp_relay_readiness.check()  (Invariant 9 — LINE variant)
                      พร้อมเมื่อ: LINE token จริง + LINE_SIMULATION_MODE=False +
                      มี push target (LINE_GROUP_ID ของกลุ่ม "a14s homelab" **หรือ**
                      LINE_ADMIN_USER_ID ของแชท 1:1 — LINE-RCA-006) + backend :8000 listen
                      (KDE Connect ถูกทำเป็น dormant — ไม่ได้ลบ)
  * Krungsri       -> app.brokers.krungsri.session_health.session_file_info() + auth_driver.login()
  * Liberator      -> app.brokers.liberator.session_health.session_health()   + liberator_driver.login()
  * Click2Win      -> file presence only (sandbox, ไม่มี JWT, auto web login ไม่มี OTP)
  * Backend :8000  -> TCP probe + เป็น *gate* ของ OTP relay (LINE webhook เข้ามาที่นี่)

Safety gates (บังคับ):
  * Invariant 9  — ห้ามยิง SMS OTP ถ้า relay ไม่พร้อม: auto re-login ต้องผ่าน
                    otp_relay_readiness.check().ready == True ก่อนทุกครั้ง (ไม่งั้น status=BRIDGE_DOWN)
  * Anti-Mock    — ไม่มีการคืนค่า/ยอดเสมือน; รายงานตามที่ตรวจได้จริงเท่านั้น
  * Broker Knowledge Isolation — ใช้ semantics ของ driver แต่ละโบรกเกอร์แยกกัน
  * User decision (2026-10-08): auto re-login ทันทีเมื่อ relay พร้อม (มือว่างจบในตัวเดียว)

Usage:
  .venv/bin/python scripts/daily_readiness.py                # เตรียมให้พร้อม + GO/NO-GO
  .venv/bin/python scripts/daily_readiness.py --json         # สรุปแบบ machine-readable
  .venv/bin/python scripts/daily_readiness.py --no-login     # ตรวจอย่างเดียว (report-only)
  .venv/bin/python scripts/daily_readiness.py --skip-liberator
  .venv/bin/python scripts/daily_readiness.py --click2win    # auto-login Click2Win ด้วย

Exit code: 0 = GO, 1 = NO-GO
"""

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from datetime import datetime
from typing import Any, Dict

# Ensure repo root importable when run as `python scripts/daily_readiness.py`
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Headed login (Krungsri/Liberator) needs the physical display (mirrors start_homelab.py)
os.environ.setdefault("DISPLAY", ":0")

# ANSI colors (repo convention — same palette as scripts/preflight_check.py)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

# LINE group OTP relay (2026-10-08) — primary OTP channel
LINE_GROUP_NAME = "a14s homelab"
RELAY_FIX_BACKEND = ".venv/bin/python scripts/start_homelab.py  (หรือ uvicorn app.main:app --host 0.0.0.0 --port 8000)"
# Dormant legacy KDE Connect checklist (kept for zero-contradiction; no longer the gate)
MOBILE_CHECKLIST = "learned_workflows/shared/kdeconnect_mobile_otp_checklist.md"
DEVICE_ID = "9507a3fd53f848da9135ebe6253db18a"  # Mi 10T Pro (settings.KDECONNECT_DEVICE_ID)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _hr() -> None:
    print(f"{BOLD}{BLUE}{'=' * 64}{RESET}")


def check_backend() -> Dict[str, Any]:
    """TCP report only. start_homelab.py คือผู้ที่ launch uvicorn (ไม่ทำที่นี่)."""
    up = _port_open("127.0.0.1", 8000)
    print(f"\n{BOLD}0. 🔌 Backend Gateway (uvicorn :8000):{RESET}")
    if up:
        print(f"   {GREEN}✅ FastAPI Gateway is UP on port 8000.{RESET}")
    else:
        print(f"   {YELLOW}⚠️  Port 8000 is DOWN — เปิดด้วย: "
              f"'.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000'{RESET}")
    return {"up": up}


async def ensure_mobile_bridge(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Gate หลักของทั้งระบบ: ช่องทาง OTP relay ต้อง live ก่อนจะยิง login ใด ๆ (Invariant 9).

    ช่องทางปัจจุบัน (2026-10-08): LINE relay — กลุ่ม "a14s homelab" (LINE_GROUP_ID) หรือ
    แชท 1:1 กับ OA (LINE_ADMIN_USER_ID, LINE-RCA-006)
    ตรวจผ่าน `app.services.otp_relay_readiness` (single source of truth — ตัวเดียวกับที่
    auth_driver / liberator_driver ใช้จริง) health check กับ gate จึงไม่ขัดกันเอง

    คืนค่า dict ที่มี key `reachable` / `refreshed` / `pinged` เหมือนเดิม เพื่อความเข้ากันได้
    กับผู้เรียกและ unit test เดิม (Zero-Contradiction)
    """
    from app.core.config import settings
    from app.services.otp_relay_readiness import otp_relay_readiness

    print(f"\n{BOLD}1. 📱 OTP Relay (LINE: กลุ่ม '{LINE_GROUP_NAME}' หรือแชท 1:1):{RESET}")
    print(f"   {BLUE}webhook:{RESET} {getattr(settings, 'LINE_PUBLIC_WEBHOOK_URL', '')}")

    readiness = await otp_relay_readiness.check()
    reachable = bool(readiness.ready)
    refreshed = False  # kept for backward compatibility (ไม่มี refresh step ในเส้นทาง LINE)

    if reachable:
        target_desc = (
            f"group '{LINE_GROUP_NAME}'"
            if readiness.channel == "line_group"
            else "1:1 chat with the OA"
        )
        print(f"   {GREEN}✅ relay พร้อม (channel={readiness.channel}) — {target_desc} + gateway up{RESET}")
    else:
        print(f"   {RED}❌ relay ไม่พร้อม: {readiness.reason}{RESET}")
        for k, v in readiness.details.items():
            print(f"      • {k} = {v}")

    pinged = False
    if reachable and not args.no_ping:
        # Human-confirm (stepwise-approval §5): push a readiness note into the LINE group
        try:
            from app.services.line_service import line_service
            pinged = await line_service.push_message(
                f"✅ [{LINE_GROUP_NAME}] OTP relay พร้อม — เริ่มเตรียม session ได้\n"
                "(เมื่อมีคำขอ OTP ระบบจะแจ้งในกลุ่มนี้ ให้พิมพ์รหัส 6 หลักตอบกลับได้เลย)"
            )
        except Exception as e:
            print(f"   {YELLOW}   LINE push notice: {e}{RESET}")
        if pinged:
            print(f"   {GREEN}✅ ส่งข้อความยืนยันเข้าแชท LINE แล้ว (human confirm: เช็คในกลุ่ม หรือในแชท 1:1 กับ OA){RESET}")
        else:
            print(f"   {YELLOW}⚠️  ส่งข้อความยืนยันเข้าแชท LINE ไม่สำเร็จ{RESET}")

    if not reachable:
        # HITL escalation — ไม่วนไม่รู้จบ (root_cause_and_escalation Invariant 4)
        print(f"   {RED}⛔ relay DOWN — login ใหม่จะถูกยกเลิก (ห้ามยิง SMS OTP){RESET}")
        print(f"   {YELLOW}👉 HITL: แก้ตามลำดับนี้แล้วรันซ้ำ{RESET}")
        print(f"      1) เปิด backend (ต้อง listen :8000): {RELAY_FIX_BACKEND}")
        print(f"      2) ตรวจ tunnel: {getattr(settings, 'LINE_PUBLIC_WEBHOOK_URL', '')}")
        print(f"      3) พิมพ์ข้อความ 1 ครั้งในกลุ่ม '{LINE_GROUP_NAME}' หรือในแชท 1:1 กับ OA")
        print(f"         (webhook จะ auto-capture LINE_GROUP_ID / LINE_ADMIN_USER_ID ลง .env ให้เอง)")
        print(f"   {YELLOW}   (dormant KDE Connect checklist: {MOBILE_CHECKLIST}){RESET}")
        try:
            from app.services.line_service import line_service
            await line_service.send_system_notification(
                "OTP relay ไม่พร้อม",
                readiness.reason,
                action_required=f"เปิด backend :8000 + พิมพ์ข้อความ 1 ครั้งในกลุ่ม LINE '{LINE_GROUP_NAME}' หรือในแชท 1:1 กับ OA",
                severity="CRITICAL",
            )
        except Exception:
            pass

    return {
        "reachable": reachable,
        "refreshed": refreshed,
        "pinged": pinged,
        "channel": readiness.channel,
        "reason": readiness.reason,
    }


async def ensure_krungsri(args: argparse.Namespace, bridge_ok: bool) -> Dict[str, Any]:
    """
    Krungsri TradeMan: ใช้ `session_file_info` (KSS-RCA-011) ตัดสิน verdict แล้วเรียก
    `auth_driver.login()` ซึ่ง self-healing อยู่แล้ว (reuse active tab → verify saved →
    fresh login + SMS OTP). Gate ด้วย bridge_ok (Invariant 9) เสมอ.
    """
    from app.core.config import settings
    from app.brokers.krungsri.session_health import session_file_info

    print(f"\n{BOLD}2. 🔑 Krungsri TradeMan Session (Live):{RESET}")
    path = getattr(settings, "SESSION_STATE_PATH", "data/session_state.json")
    info = session_file_info(path)
    age_h = info["age_hours"]
    age_str = f"{age_h:.1f}h" if age_h is not None else "n/a"
    print(f"   file: {path}")
    print(f"   verdict: {info['reason']} | exists={info['exists']} | cookies={info['cookie_count']} | age={age_str}")

    out: Dict[str, Any] = {"path": path, "verdict": info["reason"],
                           "needs_fresh_login": info["needs_fresh_login"],
                           "authenticated": None, "status": "UNKNOWN", "message": ""}

    if not bridge_ok:
        print(f"   {RED}⛔ BRIDGE_DOWN — ยกเลิก auto login (ไม่ยิง SMS OTP; Invariant 9){RESET}")
        out["status"] = "BRIDGE_DOWN"
        return out
    if args.no_login:
        print(f"   {YELLOW}⏭️  --no-login: ข้าม auto re-login (report-only){RESET}")
        out["status"] = "SKIPPED"
        return out

    from app.browser.auth_driver import auth_driver
    settings.PLAYWRIGHT_HEADLESS = False  # headed — ต้องมีจอให้ user เห็น/กรอก OTP ได้
    print(f"   … auth_driver.login(): reuse → verify → fresh+SMS OTP (อัตโนมัติผ่าน KDE Connect)…")
    try:
        res = await auth_driver.login(
            username=settings.KRUNGSRI_USERNAME,
            password=settings.KRUNGSRI_PASSWORD,
            timeout_otp=settings.OTP_TIMEOUT_SECONDS,
            force_fresh=args.force_fresh,
        )
        out["authenticated"] = bool(res.success)
        out["message"] = res.message
        out["status"] = "AUTHENTICATED" if res.success else "FAILED"
    except Exception as e:
        out["authenticated"] = False
        out["message"] = str(e)
        out["status"] = "ERROR"
    finally:
        try:
            await auth_driver.close()
        except Exception:
            pass

    if out["authenticated"]:
        print(f"   {GREEN}✅ Krungsri TradeMan พร้อมใช้งาน (session saved){RESET}")
    else:
        print(f"   {RED}❌ Krungsri login ไม่สำเร็จ: {out['message']}{RESET}")
    return out


async def ensure_liberator(args: argparse.Namespace, bridge_ok: bool) -> Dict[str, Any]:
    """
    Liberator WebTrade: ใช้ `session_health` (LIB-RCA-006/007) ตรวจ JWT exp แล้วเรียก
    `liberator_driver.login()` (headed + KDE Connect OTP) เมื่อจำเป็น.

    NOTE (Zero-Contradiction): ต่างจาก start_homelab.py Stage 3 ที่ *ไม่* ทำ headed login
    — daily skill นี้ทำ headed login ให้ Liberator ตาม user decision 2026-10-08
    โดยมี gate is_device_reachable() คั่น (Invariant 9) และมี human confirm ที่ ping มือถือ
    """
    from app.core.config import settings
    from app.brokers.liberator.session_health import session_health

    print(f"\n{BOLD}3. 🛡️ Liberator WebTrade Session (Live):{RESET}")
    path = getattr(settings, "LIBERATOR_SESSION_PATH", "data/liberator_session.json")
    health = session_health(path)
    rem = health.get("remaining_seconds")
    print(f"   file: {path}")
    print(f"   exists={health['exists']} | expired={health['expired']} | "
          f"remaining={rem if rem is not None else 'n/a'}s")

    out: Dict[str, Any] = {"path": path, "exists": health["exists"],
                           "expired": health["expired"],
                           "authenticated": None, "status": "UNKNOWN", "message": ""}

    if not bridge_ok:
        print(f"   {RED}⛔ BRIDGE_DOWN — ยกเลิก auto login (ไม่ยิง SMS OTP; Invariant 9){RESET}")
        out["status"] = "BRIDGE_DOWN"
        return out
    if args.no_login:
        print(f"   {YELLOW}⏭️  --no-login: ข้าม auto re-login (report-only){RESET}")
        out["status"] = "SKIPPED"
        return out

    from app.brokers.liberator.driver import liberator_driver
    print(f"   … liberator_driver.login(): verify → fresh+SMS OTP ถ้าจำเป็น…")
    try:
        res = await liberator_driver.login(
            username=settings.LIBERATOR_USERNAME,
            password=settings.LIBERATOR_PASSWORD,
            force_fresh=args.force_fresh,
        )
        out["authenticated"] = bool(res.success)
        out["message"] = res.message
        out["status"] = "AUTHENTICATED" if res.success else "FAILED"
    except Exception as e:
        out["authenticated"] = False
        out["message"] = str(e)
        out["status"] = "ERROR"
    finally:
        try:
            await liberator_driver.close()
        except Exception:
            pass

    if out["authenticated"]:
        print(f"   {GREEN}✅ Liberator WebTrade พร้อมใช้งาน{RESET}")
    else:
        print(f"   {RED}❌ Liberator login ไม่สำเร็จ: {out['message']}{RESET}")
    return out


def inspect_click2win(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Click2Win (Settrade sandbox) ไม่มี JWT → ตรวจได้แค่ file presence + cookie count
    (ตรงกับ semantics ของ preflight_check.click2win_session_status — ไม่รายงาน ✅ เท็จ)
    """
    from app.core.config import settings

    print(f"\n{BOLD}4. 🎮 Settrade Click2Win (Simulation):{RESET}")
    path = getattr(settings, "CLICK2WIN_SESSION_PATH", "data/click2win_session.json")
    exists = os.path.exists(path)
    cookies = 0
    age_h = None
    if exists:
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        try:
            with open(path, "r", encoding="utf-8") as f:
                cookies = len(json.load(f).get("cookies", []))
        except Exception:
            pass

    if exists:
        print(f"   {BLUE}ℹ️  Saved file present ({cookies} cookies, {age_h:.1f}h old).{RESET}")
    else:
        print(f"   {BLUE}ℹ️  No saved session — ใช้ auto web login (ไม่มี SMS OTP){RESET}")
    if args.click2win:
        print(f"   {YELLOW}ℹ️  --click2win: (optional) auto web-login ยังไม่ผูกใน runner นี้ "
              f"— ใช้ 'Connect All Brokers' ที่ /console หรือ MCP broker_login แทน{RESET}")
    return {"path": path, "exists": exists, "cookies": cookies, "age_hours": age_h}


def _krungsri_ready(res: Dict[str, Any]) -> bool:
    """
    ตัดสินความพร้อม Krungsri แบบซื่อตรง (Anti-Mock):
      AUTHENTICATED        -> True
      FAILED/ERROR/BRIDGE_DOWN -> False
      SKIPPED (report-only)-> ใช้ offline verdict: RECENT = พร้อม (ยังไม่ต้อง re-login)
    """
    st = res.get("status")
    if st == "AUTHENTICATED":
        return True
    if st in ("FAILED", "ERROR", "BRIDGE_DOWN"):
        return False
    if st == "SKIPPED":
        return not bool(res.get("needs_fresh_login", True))
    return False


def _liberator_ready(res: Dict[str, Any]) -> bool:
    """แบบเดียวกับ Krungsri แต่ใช้ JWT guard ของ Liberator (expired / exists)."""
    st = res.get("status")
    if st == "AUTHENTICATED":
        return True
    if st in ("FAILED", "ERROR", "BRIDGE_DOWN"):
        return False
    if st == "SKIPPED":
        return bool(res.get("exists")) and not bool(res.get("expired", True))
    return False


async def run(args: argparse.Namespace) -> Dict[str, Any]:
    _hr()
    print(f"{BOLD}{BLUE}  🚀 DAILY READINESS — Mobile Bridge + Broker Sessions{RESET}")
    print(f"   {datetime.now().strftime('%A %Y-%m-%d %H:%M:%S')}")
    _hr()

    backend = check_backend()

    bridge = await ensure_mobile_bridge(args)
    bridge_ok = bool(bridge["reachable"])

    krungsri = await ensure_krungsri(args, bridge_ok)
    liberator: Dict[str, Any] = {"status": "SKIPPED", "authenticated": None, "message": "skipped"}
    if not args.skip_liberator:
        liberator = await ensure_liberator(args, bridge_ok)
    else:
        print(f"\n{BOLD}3. 🛡️ Liberator WebTrade Session (Live):{RESET}")
        print(f"   {YELLOW}⏭️  --skip-liberator: ข้าม{RESET}")

    click2win = inspect_click2win(args)

    # ---- GO / NO-GO decision -------------------------------------------------
    # NOTE: ในโหมด --no-login (report-only) เรา *ตั้งใจ* ข้าม login จึงตัดสินด้วย
    # offline verdict (session file) แทน `authenticated` — ห้ามรายงาน NO-GO ปลอม
    # จากเหตุ "ข้ามโดยเจตนา" (Anti-Mock: verdict ต้องสะท้อนความจริง)
    reasons = []
    if not bridge_ok:
        reasons.append(
            f"OTP relay (LINE) DOWN — OTP bridge ไม่พร้อม: {bridge.get('reason')}"
        )
    if not _krungsri_ready(krungsri):
        reasons.append(f"Krungsri TradeMan ไม่พร้อม ({krungsri.get('status')} / verdict={krungsri.get('verdict')})")
    if not args.skip_liberator and not _liberator_ready(liberator):
        reasons.append(f"Liberator ไม่พร้อม ({liberator.get('status')})")

    verdict = "GO" if not reasons else "NO-GO"

    print(f"\n{BOLD}{BLUE}{'=' * 64}{RESET}")
    if verdict == "GO":
        print(f"{BOLD}{GREEN}  ✅ GO — พร้อมทดสอบ pillar ถัดไป{RESET}")
        print(f"   • OTP relay     : LIVE (channel={bridge.get('channel')})")
        print(f"   • Krungsri      : {krungsri.get('status')}")
        if not args.skip_liberator:
            print(f"   • Liberator     : {liberator.get('status')}")
    else:
        print(f"{BOLD}{RED}  ⛔ NO-GO — ยังไม่พร้อม (ต้อง HITL){RESET}")
        for r in reasons:
            print(f"   • {r}")
        if not bridge_ok:
            print(f"   👉 เปิด backend :8000 + พิมพ์ข้อความ 1 ครั้งในกลุ่ม LINE '{LINE_GROUP_NAME}' หรือในแชท 1:1 กับ OA แล้วรันซ้ำ")
            print(f"      (ห้ามยิง SMS OTP ถ้า relay ไม่พร้อม — Invariant 9)")
    print(f"{BOLD}{BLUE}{'=' * 64}{RESET}")

    summary = {
        "timestamp": _now_iso(),
        "backend": backend,
        "mobile_bridge": bridge,
        "krungsri": krungsri,
        "liberator": liberator,
        "click2win": click2win,
        "verdict": verdict,
        "reasons": reasons,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Daily readiness: prepare the LINE group OTP relay + broker sessions (GO/NO-GO)."
    )
    parser.add_argument("--json", action="store_true", help="พิมพ์สรุปแบบ JSON ท้ายสุด")
    parser.add_argument("--no-login", action="store_true",
                        help="ตรวจอย่างเดียว ไม่ auto re-login (report-only)")
    parser.add_argument("--force-fresh", action="store_true",
                        help="บังคับ fresh login (purge cookies + SMS OTP)")
    parser.add_argument("--no-ping", action="store_true",
                        help="ไม่ส่งข้อความยืนยันเข้าแชท LINE (กลุ่ม/1:1)")
    parser.add_argument("--skip-liberator", action="store_true", help="ข้าม Liberator")
    parser.add_argument("--click2win", action="store_true", help="(optional) พิจารณา Click2Win")
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    """แยกออกมาเพื่อให้ unit test เรียกได้โดยไม่ต้องรัน asyncio.run()."""
    return build_parser().parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    summary = asyncio.run(run(args))
    return 0 if summary["verdict"] == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())

