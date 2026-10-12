#!/usr/bin/env python3
"""
scripts/dev_resume_session.py — Krungsri TradeMan Zero-OTP resume helper (never fires SMS OTP)
================================================================================================
จุดประสงค์: ตรวจ + รีเฟรช session file ที่ Start Homelab login ไว้ (`data/session_state.json`)
โดยไม่ยิง SMS OTP ซ้ำ (Invariant 9 — Zero-OTP). ใช้ระหว่าง dev loop หลังแก้โค้ด / restart gateway
เพื่อให้ `auth_driver.login(force_fresh=False)` (หรือ Stage 2 ของ start_homelab) ผ่านใน <2s.

หลักการ (single source of truth):
  - ไฟล์ session → `app.brokers.krungsri.session_health.session_file_info()` (KSS-RCA-011)
  - resume   → `auth_driver.verify_saved_session()` (โหลด cookie + DOM check `#dropDownAccountPort`)
               เส้นทางนี้ *ไม่* แตะ OTP เลย ต่างจาก `auth_driver.login()` ที่ถ้า verify ล้มจะตกไป
               login เต็มรูปแบบ + ยิง SMS OTP

Usage:
  .venv/bin/python scripts/dev_resume_session.py                 # resume + refresh แล้วปิด browser
  .venv/bin/python scripts/dev_resume_session.py --keep-open     # resume แล้วเปิด browser ทิ้งไว้
  .venv/bin/python scripts/dev_resume_session.py --report        # report-only (ไม่เปิด browser)

Exit code: 0 = session valid/resumed · 1 = needs fresh login (run scripts/start_homelab.py) · 2 = error
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings
from app.brokers.krungsri.session_health import session_file_info


def decide_action(info: Dict) -> str:
    """Pure decision: map session_file_info() output → 'resume' | 'fresh_login'."""
    if not info.get("exists"):
        return "fresh_login"
    if info.get("needs_fresh_login"):
        return "fresh_login"
    return "resume"


def format_report(info: Dict, action: str) -> str:
    """Render-friendly session report for the terminal."""
    lines = [
        "Krungsri TradeMan session report:",
        f"  file:      {settings.SESSION_STATE_PATH}",
        f"  exists:    {info.get('exists')}",
        f"  mtime:     {info.get('mtime_iso')}",
        f"  age_hours: {info.get('age_hours')}",
        f"  cookies:   {info.get('cookie_count')}",
        f"  reason:    {info.get('reason')}",
        f"  action:    {action}",
    ]
    return "\n".join(lines)


async def _resume(keep_open: bool) -> int:
    info = session_file_info(settings.SESSION_STATE_PATH)
    action = decide_action(info)

    if action == "fresh_login":
        print(format_report(info, action))
        print("\n⚠️  ไม่มี session ที่ใช้ได้ (MISSING/STALE) — Zero-OTP resume ทำไม่ได้")
        print("   👉 รัน `scripts/start_homelab.py` เพื่อ login ใหม่ (username/password/OTP ผ่าน LINE)")
        print("      โปรแกรมนี้จะ *ไม่* ยิง SMS OTP ให้เอง (Invariant 9)")
        return 1

    print(format_report(info, action))
    print("\n🔄 กำลัง resume session แบบ Zero-OTP (ไม่ยิง OTP) ...")

    from app.browser.auth_driver import auth_driver

    try:
        await auth_driver.launch_browser(resume_state=True)
        ok = await auth_driver.verify_saved_session()
    except Exception as exc:  # pragma: no cover - browser/network failure
        print(f"❌ resume error: {exc}")
        return 2

    if ok:
        print("✅ Zero-OTP resume สำเร็จ — session valid & refreshed")
        print(f"   • status: {auth_driver.status}")
        print(f"   • url:    {auth_driver.current_url}")
    else:
        print("❌ resume ล้มเหลว — session หมดอายุจริง (DOM #dropDownAccountPort ไม่พบ)")
        print("   👉 รัน `scripts/start_homelab.py` เพื่อ login ใหม่ (จะยิง SMS OTP ผ่าน LINE)")

    if not keep_open:
        try:
            await auth_driver.close()
        except Exception:  # pragma: no cover
            pass
    return 0 if ok else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="report-only (ไม่เปิด browser)")
    parser.add_argument("--keep-open", action="store_true", help="resume แล้วเปิด browser ทิ้งไว้")
    args = parser.parse_args()

    if args.report:
        info = session_file_info(settings.SESSION_STATE_PATH)
        action = decide_action(info)
        print(format_report(info, action))
        return 0 if action == "resume" else 1

    return await _resume(keep_open=args.keep_open)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
