"""
OTP Relay Readiness Gate — SINGLE SOURCE OF TRUTH
=================================================

Invariant 9 (LINE variant, 2026-10-08)
--------------------------------------
ก่อน `auth_driver.login()` / `liberator_driver.login()` จะ submit credentials และ
**กระตุ้น SMS OTP** ทุกครั้ง ต้องผ่าน gate นี้ก่อน — ถ้า relay ไม่พร้อม ให้ยกเลิกด้วย
`status=BRIDGE_DOWN` โดย **ไม่ยิง SMS OTP** (กัน OTP หมดอายุค้าง + กัน account lock)

ช่องทางปัจจุบัน (2026-10-08): **LINE relay — มี 2 channel ที่ใช้ได้**

  | channel | เงื่อนไข | push target |
  |---------|----------|-------------|
  | `line_group` (preferred) | `LINE_GROUP_ID` ถูกตั้ง | กลุ่ม "a14s homelab" (`groupId` ขึ้นต้น `C`) |
  | `line_direct` (LINE-RCA-006) | `LINE_GROUP_ID` ว่าง แต่ `LINE_ADMIN_USER_ID` ถูกตั้ง | แชท 1:1 กับ OA (`userId` ขึ้นต้น `U`) |

  เงื่อนไขร่วมทั้งสอง channel:
  1. `LINE_OTP_RELAY_ENABLED=True`
  2. `LINE_SIMULATION_MODE=False` และ token ไม่ใช่ค่า mock
  3. **มี push target** = `LINE_GROUP_ID` หรือ `LINE_ADMIN_USER_ID` (auto-capture จาก webhook:
     พิมพ์ข้อความในกลุ่ม → จับ `source.groupId`; พิมพ์ในแชท 1:1 → จับ `source.userId`)
  4. Backend gateway (uvicorn `app.main:app`) ต้อง listen ที่ :8000 เพื่อรับ webhook
     จาก cloudflared tunnel (`LINE_PUBLIC_WEBHOOK_URL`)

  **Precedence:** ถ้ามีทั้งสองค่า `LINE_GROUP_ID` ชนะเสมอ (Zero-Contradiction)

Zero-Contradiction: KDE Connect ถูกทำเป็น **dormant** ไม่ได้ลบ — ผู้เรียกที่ยังต้องการ
ใช้ KDE ส่ง `allow_kde_fallback=True` ได้ (จะยอมรับก็ต่อเมื่อ LINE ไม่พร้อมจริง ๆ)

เรียกใช้จาก: `app/browser/auth_driver.py`, `app/brokers/liberator/driver.py`,
`scripts/daily_readiness.py`, `scripts/preflight_check.py`
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

CHANNEL_LINE_GROUP = "line_group"
CHANNEL_LINE_DIRECT = "line_direct"
CHANNEL_KDE_CONNECT = "kde_connect"
CHANNEL_NONE = "none"

# --- Channel policy helpers (Gate A, 2026-10-08) -----------------------------
# Single source of truth for "which capture path may legitimately serve which
# channel". RULE (LINE-RCA-009): while the authoritative LINE channel is active a
# KDE Connect capture must NOT be accepted — otherwise the OTP still arrives via the
# dormant fallback and we can never prove LINE delivered it (silent drift back to KDE).

_LINE_CHANNELS = (CHANNEL_LINE_GROUP, CHANNEL_LINE_DIRECT)

_CHANNEL_DB_EVENT_TYPES: Dict[str, tuple] = {
    CHANNEL_LINE_GROUP: ("LINE_OTP_RECEIVED",),
    CHANNEL_LINE_DIRECT: ("LINE_OTP_RECEIVED",),
    CHANNEL_KDE_CONNECT: ("KDECONNECT_OTP_RECEIVED",),
}

_EVENT_TYPE_TO_SOURCE: Dict[str, str] = {
    "LINE_OTP_RECEIVED": "line_chat",
    "KDECONNECT_OTP_RECEIVED": "kdeconnect_sms",
}

# Capture-path tags that mean "the phone's SMS notification was scraped" (KDE family).
_KDE_SOURCES = ("kdeconnect_direct", "kdeconnect_sms")
# Capture-path tags that mean "the operator typed the code into LINE".
_LINE_SOURCES = ("line_chat", "session_logs_db")


def channel_allows_kde(channel: str) -> bool:
    """True only when the KDE Connect capture path may serve this channel."""
    return channel == CHANNEL_KDE_CONNECT


def channel_db_event_types(channel: str) -> tuple:
    """
    ``session_logs.event_type`` values that may satisfy this channel.

    Fail-closed: an unknown / ``none`` channel returns an empty tuple, so a stale
    legacy row can never masquerade as the authoritative channel's OTP.
    """
    return _CHANNEL_DB_EVENT_TYPES.get(channel, ())


def channel_accepts_source(channel: str, source: str) -> bool:
    """
    Does ``source`` (a capture-path tag) legitimately serve ``channel``?

    A KDE capture is rejected unless the channel IS kde_connect; conversely a LINE
    capture is rejected for a KDE-only channel. Operator-typed paths (browser DOM,
    API, CLI, in-process event bus) are channel-agnostic and always accepted.
    """
    if source in _KDE_SOURCES:
        return channel_allows_kde(channel)
    if source in _LINE_SOURCES:
        return channel in _LINE_CHANNELS
    return True


def event_type_to_source(event_type: str) -> str:
    """Map a ``session_logs.event_type`` to its honest capture-source tag."""
    return _EVENT_TYPE_TO_SOURCE.get(event_type, str(event_type).lower())



def _port_open(host: str = "127.0.0.1", port: int = 8000, timeout: float = 0.6) -> bool:
    """Plain TCP probe — true when something is listening (no HTTP call)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _probe_target(target_id: str, token: str, timeout: float = 6.0) -> tuple[bool, str]:
    """
    LINE-RCA-007 (2026-10-08): **มี id ≠ ส่งถึงได้**

    ถาม LINE ตรง ๆ ว่า OTP push target ยัง deliverable อยู่ไหม (read-only):

      * `C...` (groupId) → `GET /v2/bot/group/{id}/summary` → 200 = บอทอยู่ในกลุ่มนั้น
      * `R...` (roomId)  → `GET /v2/bot/room/{id}/summary`
      * `U...` (userId)  → `GET /v2/bot/profile/{id}`

    บทเรียนจากของจริง: `.env` มี `LINE_GROUP_ID=Ccd...` (format ถูก, 33 ตัว) แต่
    `group/summary` = **404 Not found** และ push = `{"message":"Failed to send messages"}`
    ⇒ gate เดิม (เช็คแค่ว่า "มีค่าไหม") รายงาน `ready=true` **ทั้งที่ส่ง OTP ไม่ได้เลย**
       = false-GO → เสี่ยงยิง SMS OTP ทิ้ง + login ค้างรอ OTP ที่มองไม่เห็น (Invariant 9)

    คืน `(reachable, detail)` — ไม่ throw เด็ดขาด (network error = unreachable)
    """
    if not target_id:
        return False, "target not set"

    if target_id.startswith("C"):
        url = f"https://api.line.me/v2/bot/group/{target_id}/summary"
    elif target_id.startswith("R"):
        url = f"https://api.line.me/v2/bot/room/{target_id}/summary"
    else:
        url = f"https://api.line.me/v2/bot/profile/{target_id}"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            return True, "reachable"
        return False, f"HTTP {resp.status_code}: {resp.text[:90]}"
    except Exception as e:  # network / timeout → ถือว่า deliver ไม่ได้
        return False, f"{type(e).__name__}: {e}"


@dataclass
class OtpRelayReadiness:
    """Result of an OTP relay readiness probe."""

    ready: bool
    channel: str
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "channel": self.channel,
            "reason": self.reason,
            **self.details,
        }


class OtpRelayReadinessService:
    """Answers one question only: *can we capture an OTP right now?*"""

    async def check(
        self,
        *,
        require_gateway: bool = True,
        allow_kde_fallback: bool = False,
        gateway_port: int = 8000,
    ) -> OtpRelayReadiness:
        token = settings.LINE_CHANNEL_ACCESS_TOKEN or ""
        group_id = settings.LINE_GROUP_ID
        direct_id = getattr(settings, "LINE_ADMIN_USER_ID", None)
        # Precedence (LINE-RCA-006): a group target always wins over the 1:1 fallback.
        target_id = group_id or direct_id
        enabled = bool(getattr(settings, "LINE_OTP_RELAY_ENABLED", True))
        simulation = bool(settings.LINE_SIMULATION_MODE)
        token_ok = bool(token) and token != "mock_line_channel_token"

        details: Dict[str, Any] = {
            "line_relay_enabled": enabled,
            "line_simulation_mode": simulation,
            "line_token_configured": token_ok,
            "line_group_id_configured": bool(group_id),
            "line_group_id": group_id,
            "line_direct_id_configured": bool(direct_id),
            "line_direct_id": direct_id,
            "line_target_kind": "group" if group_id else ("direct" if direct_id else None),
            "line_group_reachable": None,   # LINE-RCA-007: เติมค่าจาก probe เท่านั้น
            "line_direct_reachable": None,
            "public_webhook_url": getattr(settings, "LINE_PUBLIC_WEBHOOK_URL", ""),
            "gateway_port": gateway_port,
            "gateway_up": None,
        }

        # --- 1. LINE relay (primary) ------------------------------------------
        #     channel = line_group  -> OTP is pushed into the "a14s homelab" group
        #     channel = line_direct -> OTP is pushed into the 1:1 bot chat (LINE-RCA-006)
        ready_reason = {
            "group": "LINE group relay ready (bot 'a14s homelab' + gateway up)",
            "direct": "LINE 1:1 relay ready (operator chat via LINE_ADMIN_USER_ID + gateway up)",
        }

        if not enabled:
            reason = "LINE OTP relay disabled (LINE_OTP_RELAY_ENABLED=False)"
        elif simulation:
            reason = "LINE_SIMULATION_MODE=True — push/receive is mocked"
        elif not token_ok:
            reason = "LINE_CHANNEL_ACCESS_TOKEN missing or still the mock value"
        elif not target_id:
            reason = (
                "LINE_GROUP_ID / LINE_ADMIN_USER_ID not set — no OTP push target. "
                "Send one message either in the 'a14s homelab' group or in the 1:1 bot "
                "chat; the webhook auto-captures groupId (preferred) or userId"
            )
        else:
            gateway_up = await asyncio.to_thread(_port_open, "127.0.0.1", gateway_port)
            details["gateway_up"] = gateway_up
            if require_gateway and not gateway_up:
                reason = (
                    f"Backend gateway is DOWN on :{gateway_port} — the LINE webhook "
                    "cannot be received (start uvicorn app.main:app)"
                )
            else:
                # LINE-RCA-007: มี id ≠ ส่งถึงได้ → ต้องพิสูจน์ deliverability จริงก่อนเปิด gate
                # Fail-closed: ถ้ามี LINE_GROUP_ID แต่ส่งไม่ได้ → NO-GO ทันที *ไม่ fallback ไป 1:1*
                # เพราะ `line_service.push_message` ยังคงยิงเข้า LINE_GROUP_ID ก่อนเสมอ
                # (gate ต้องสะท้อน target ที่ driver ใช้จริง — Zero-Contradiction)
                if group_id:
                    reachable, probe_detail = await _probe_target(group_id, token)
                    details["line_group_reachable"] = reachable
                    details["line_group_probe"] = probe_detail
                    if reachable:
                        return OtpRelayReadiness(
                            ready=True,
                            channel=CHANNEL_LINE_GROUP,
                            reason=ready_reason["group"],
                            details=details,
                        )
                    reason = (
                        f"LINE group push target not deliverable — group {group_id[:3]}… {probe_detail} "
                        "(สาเหตุที่พบบ่อย: บอทออกจากกลุ่มแล้ว/ยังไม่ถูกเชิญ/ค่าใน .env ผิด — "
                        "เชิญ OA @678clhio เข้ากลุ่มใหม่ แล้วพิมพ์ข้อความ 1 ครั้ง "
                        "หรือลบ LINE_GROUP_ID ออกจาก .env เพื่อใช้แชท 1:1 แทน)"
                    )
                elif direct_id:
                    reachable, probe_detail = await _probe_target(direct_id, token)
                    details["line_direct_reachable"] = reachable
                    details["line_direct_probe"] = probe_detail
                    if reachable:
                        return OtpRelayReadiness(
                            ready=True,
                            channel=CHANNEL_LINE_DIRECT,
                            reason=ready_reason["direct"],
                            details=details,
                        )
                    reason = (
                        f"LINE 1:1 push target not deliverable — {probe_detail} "
                        "(พิมพ์ข้อความในแชท 1:1 กับ OA @678clhio อีกครั้งเพื่อยืนยัน/อัปเดต userId)"
                    )
                else:
                    reason = "LINE push target missing"

        # --- 2. KDE Connect (dormant legacy fallback) --------------------------
        if allow_kde_fallback:
            try:
                from app.services.kdeconnect_service import kdeconnect_service

                if await kdeconnect_service.is_device_reachable():
                    details["line_reason"] = reason
                    return OtpRelayReadiness(
                        ready=True,
                        channel=CHANNEL_KDE_CONNECT,
                        reason=f"LINE relay not ready ({reason}) — falling back to KDE Connect",
                        details=details,
                    )
            except Exception as e:  # never fatal
                details["kde_error"] = str(e)

        return OtpRelayReadiness(
            ready=False,
            channel=CHANNEL_NONE,
            reason=reason,
            details=details,
        )

    async def is_ready(self, **kwargs: Any) -> bool:
        """Convenience boolean wrapper."""
        return (await self.check(**kwargs)).ready


# Global singleton (same convention as kdeconnect_service / auth_driver)
otp_relay_readiness = OtpRelayReadinessService()
