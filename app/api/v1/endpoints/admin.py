"""
Admin / Console Control Endpoints
=================================
Operator controls backing the redesigned `/console`:

1. ``GET  /admin/feature-matrix``      — Pillar × Broker feature table (SSOT: app.core.feature_matrix)
2. ``GET  /admin/components``          — component toggle registry + current values + restart policy
3. ``POST /admin/components/{key}``    — flip a boolean component: atomic ``.env`` write + live
                                          in-process ``settings`` update
4. ``POST /admin/reload``              — REAL process reload via ``os.execv`` (re-exec uvicorn)

Design notes
------------
* **SSOT**: the toggle list lives here; the feature table lives in ``app.core.feature_matrix``.
* **Atomic .env writes**: reuse the single writer ``webhook_line._write_env_key`` (LINE-RCA-003:
  "single writer for all keys") so daemon restarts survive a process reload.
* **In-process update**: flags read per-request (safety / LINE) take effect immediately; flags
  read once at boot (background daemons) are marked ``restart_required`` and need ``/admin/reload``.
* **Trading safety**: ``TRADING_MODE`` (TEST/LIVE) is *deliberately NOT togglable here* — switching
  to LIVE must go through the authenticated LINE ``MODE LIVE <PIN>`` flow, never a single web click.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.feature_matrix import build_matrix_payload
from app.api.v1.endpoints.webhook_line import _write_env_key

logger = logging.getLogger("AdminConsole")

router = APIRouter()

GATEWAY_PORT_DEFAULT = 8000


# ─── Component registry (SSOT for the /console toggle panel) ────────────────────
# group            : "daemons" | "safety" | "line"
# restart_required : True  -> the value is read once at boot -> needs POST /admin/reload
#                    False -> read per-request -> takes effect immediately
COMPONENTS: List[Dict[str, Any]] = [
    # ---- Background daemons (boot-time; require reload) ----
    {
        "key": "intraday_scheduler",
        "env_key": "ENABLE_INTRADAY_SCHEDULER",
        "label": "Intraday Scheduler (8 regimes)",
        "group": "daemons",
        "restart_required": True,
        "description": "ตัวจัดตารางระหว่างวัน (pre-market -> auto-trade -> EOD). เดิมชื่อ Phase 3 Scheduler.",
    },
    {
        "key": "action_exit_dispatcher",
        "env_key": "ENABLE_ACTION_EXIT_DISPATCHER",
        "label": "Action-Exit Dispatcher (P6)",
        "group": "daemons",
        "restart_required": True,
        "description": "Daemon ปิดไม้ตาม tactical window + 09:45 pre-flight (ปิดไว้ก่อน).",
    },
    {
        "key": "agentic_orchestrator",
        "env_key": "ENABLE_AGENTIC_ORCHESTRATOR",
        "label": "Agentic Orchestrator (P7)",
        "group": "daemons",
        "restart_required": True,
        "description": "PT-MRO multi-agent background loop (ปิดไว้ก่อน).",
    },
    # ---- Safety flags (per-request; immediate) ----
    {
        "key": "dry_run_mode",
        "env_key": "DRY_RUN_MODE",
        "label": "DRY_RUN (ไม่ส่งคำสั่งจริง)",
        "group": "safety",
        "restart_required": False,
        "description": "True = เตรียมคำสั่งแต่ไม่ submit PIN จริง. False = ส่งออเดอร์จริง.",
    },
    {
        "key": "hitl_live_gate",
        "env_key": "ENABLE_HITL_LIVE_GATE",
        "label": "HITL Gate (เงินจริง)",
        "group": "safety",
        "restart_required": False,
        "description": "บังคับยืนยัน 1-click ที่ /console ก่อนยิงออเดอร์เงินจริง.",
    },
    {
        "key": "hitl_sandbox_gate",
        "env_key": "ENABLE_HITL_SANDBOX_GATE",
        "label": "HITL Gate (Sandbox)",
        "group": "safety",
        "restart_required": False,
        "description": "บังคับ HITL บน Click2Win sandbox (ทดสอบโดยไม่เสี่ยงเงินจริง).",
    },
    # ---- LINE channel (per-request; immediate) ----
    {
        "key": "line_simulation_mode",
        "env_key": "LINE_SIMULATION_MODE",
        "label": "LINE Simulation Mode",
        "group": "line",
        "restart_required": False,
        "description": "True = ไม่ยิง LINE จริง. ต้องเป็น False จึงจะส่งการ์ด/OTP ออกจริง.",
    },
    {
        "key": "line_otp_relay_enabled",
        "env_key": "LINE_OTP_RELAY_ENABLED",
        "label": "LINE OTP Relay Gate",
        "group": "line",
        "restart_required": False,
        "description": "Master switch ของ OTP readiness gate (Invariant 9).",
    },
    {
        "key": "progress_notifications",
        "env_key": "ENABLE_PROGRESS_NOTIFICATIONS",
        "label": "Progress Notifications (⏳/✅)",
        "group": "line",
        "restart_required": False,
        "description": "ส่งข้อความความคืบหน้า 1 บรรทัดเข้า LINE.",
    },
]

COMPONENTS_BY_KEY: Dict[str, Dict[str, Any]] = {c["key"]: c for c in COMPONENTS}
COMPONENTS_BY_ENV: Dict[str, Dict[str, Any]] = {c["env_key"]: c for c in COMPONENTS}


class ComponentToggleRequest(BaseModel):
    enabled: bool = Field(..., description="Target boolean value for the component flag")


# ─── Feature matrix ─────────────────────────────────────────────────────────────
@router.get("/feature-matrix", summary="Pillar × Broker feature matrix (SSOT)")
async def get_feature_matrix() -> Dict[str, Any]:
    """Return the machine-readable Pillar × Broker feature table."""
    return build_matrix_payload()


# ─── Component toggles ──────────────────────────────────────────────────────────
def _component_payload(comp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": comp["key"],
        "env_key": comp["env_key"],
        "label": comp["label"],
        "group": comp["group"],
        "restart_required": comp["restart_required"],
        "description": comp["description"],
        "enabled": bool(getattr(settings, comp["env_key"], False)),
    }


@router.get("/components", summary="List component toggles with live values")
async def list_components() -> Dict[str, Any]:
    """Return every toggle, its current in-process value, and whether it needs a reload."""
    return {
        "components": [_component_payload(c) for c in COMPONENTS],
        "groups": [
            {"key": "daemons", "label": "Background Daemons", "restart_required": True},
            {"key": "safety", "label": "Safety Gates", "restart_required": False},
            {"key": "line", "label": "LINE Channel", "restart_required": False},
        ],
        "trading_mode": settings.TRADING_MODE,
        "trading_mode_note": "TRADING_MODE เปลี่ยนได้ทาง LINE (MODE LIVE <PIN>) เท่านั้น — ไม่ให้ toggle บนเว็บ",
    }


@router.post("/components/{key}", summary="Toggle a component flag (atomic .env + live settings)")
async def toggle_component(key: str, payload: ComponentToggleRequest) -> Dict[str, Any]:
    """
    Flip a boolean component flag.

    * Written atomically to the repo ``.env`` (survives restart / reload).
    * Applied to the live in-process ``settings`` immediately (so per-request flags
      like DRY_RUN / LINE_SIMULATION_MODE take effect at once).
    * ``restart_required`` components still need ``POST /admin/reload`` to actually
      (re)start or stop their background daemon.
    """
    comp = COMPONENTS_BY_KEY.get(key)
    if comp is None:
        raise HTTPException(status_code=404, detail=f"Unknown component '{key}'")

    env_key = comp["env_key"]
    value_txt = "true" if payload.enabled else "false"

    # 1. Atomic .env persistence (SSOT single-writer from webhook_line)
    _write_env_key(env_key, value_txt)

    # 2. Live in-process update
    try:
        setattr(settings, env_key, payload.enabled)
    except Exception as e:  # pragma: no cover - pydantic guard
        logger.error(f"Could not update live settings.{env_key}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update settings.{env_key}: {e}")

    logger.info(
        f"[Admin] Component '{key}' -> {value_txt} "
        f"(settings.{env_key}, restart_required={comp['restart_required']})"
    )

    return {
        "success": True,
        "component": _component_payload(comp),
        "env_written": f"{env_key}={value_txt}",
        "restart_required": comp["restart_required"],
        "message": (
            f"ตั้งค่า {env_key}={value_txt} เรียบร้อย — ต้องกด Reload เพื่อเริ่ม/หยุด daemon"
            if comp["restart_required"]
            else f"ตั้งค่า {env_key}={value_txt} มีผลทันที (ไม่ต้อง reload)"
        ),
    }


# ─── Real process reload (os.execv) ─────────────────────────────────────────────
def _detect_gateway_port() -> int:
    """Best-effort: recover the uvicorn ``--port`` from argv, else the default."""
    argv = sys.argv
    if "--port" in argv:
        try:
            return int(argv[argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass
    return GATEWAY_PORT_DEFAULT


def _uvicorn_argv() -> List[str]:
    """
    Rebuild the uvicorn argv for a faithful in-place restart.

    Prefer the *real* argv when the process was launched as ``python -m uvicorn ...``
    (or via the ``uvicorn`` console script); otherwise fall back to the canonical
    ``python -m uvicorn app.main:app --host 0.0.0.0 --port <port>`` form.
    ``--reload`` is intentionally dropped (AGENTS.md: the gateway runs WITHOUT --reload).
    """
    argv = list(sys.argv)
    first = argv[0] if argv else ""
    looks_like_uvicorn = "uvicorn" in os.path.basename(first) or "uvicorn" in first
    if looks_like_uvicorn and "app.main:app" in argv:
        args = [a for a in argv[1:] if a != "--reload"]
        return [sys.executable, "-m", "uvicorn", *args]
    return [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", str(_detect_gateway_port()),
    ]


def _exec_reload() -> None:  # pragma: no cover - process is replaced, not returning
    """Replace the current process image with a fresh gateway (real reload)."""
    argv = _uvicorn_argv()
    logger.critical(f"[Admin] RELOAD via os.execv -> {' '.join(argv)}")
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, argv)


@router.post("/reload", summary="Restart the gateway process in-place (os.execv)")
async def reload_gateway(background: BackgroundTasks) -> Dict[str, Any]:
    """
    Re-exec the uvicorn process so a fresh gateway boots (real reload — not a soft flag flip).

    The HTTP response is sent first; the actual ``os.execv`` runs a moment later in the
    background so the browser receives confirmation before the socket drops and rebinds.
    """
    port = _detect_gateway_port()
    argv = _uvicorn_argv()
    logger.warning(f"[Admin] Reload requested — will re-exec: {' '.join(argv)}")

    async def _delayed_exec() -> None:
        await asyncio.sleep(0.75)  # let the response flush to the browser
        try:
            _exec_reload()
        except Exception as e:  # pragma: no cover
            logger.error(f"[Admin] os.execv failed: {e}")

    background.add_task(_delayed_exec)
    return {
        "success": True,
        "action": "RELOAD_SCHEDULED",
        "port": port,
        "command": " ".join(argv),
        "message": "กำลังรีสตาร์ท gateway (os.execv) — หน้านี้จะ reconnect เองใน 1-3 วินาที",
    }
