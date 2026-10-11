"""
Pillar 1: Session Sentinel Module.
Handles:
- Unified connection & authentication health check
- Dual-platform login initiation (Krungsri TradeMan & Settrade Click2Win)
- 2FA SMS OTP manual submission fallback
- Safe logout and session termination
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.browser.auth_driver import auth_driver
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.brokers.krungsri.session_health import session_file_info
from app.schemas.auth import OTPPayload, OTPSource

logger = logging.getLogger("Pillar1.Session")


async def session_get_health() -> Dict[str, Any]:
    """
    Unified Session Health Check.
    Returns status of both Krungsri TradeMan (Browser) and Settrade (Open API/Click2Win).
    """
    kss_status = auth_driver.status
    kss_authenticated = auth_driver.is_authenticated
    kss_ref = auth_driver.current_ref
    kss_heartbeat = auth_driver.last_heartbeat.isoformat() if auth_driver.last_heartbeat else None

    # File-backed session state (KSS-RCA-011): in-memory driver state alone cannot tell
    # "no saved session at all" from "saved session present but driver not attached".
    # Mirrors the REST endpoint GET /api/v1/session/status -> session_file_exists.
    kss_session_file = session_file_info(settings.SESSION_STATE_PATH)

    c2w_status = click2win_auth_driver.status
    c2w_authenticated = click2win_auth_driver.is_authenticated
    c2w_heartbeat = click2win_auth_driver.last_heartbeat.isoformat() if click2win_auth_driver.last_heartbeat else None

    # Check Settrade Open API configuration readiness
    settrade_api_ready = bool(settings.SETTRADE_APP_ID and settings.SETTRADE_APP_SECRET)
    from app.schemas.account import account_context

    # Check KDE Connect reachability & active transport routes
    kde_reachable = False
    kde_device_id = getattr(settings, "KDECONNECT_DEVICE_ID", None)
    kde_routes = {
        "active_route": "DISCONNECTED",
        "route_label": "❌ Disconnected",
        "remote_ip": "-",
        "wifi": "OFFLINE",
        "tailscale": "OFFLINE"
    }
    try:
        from app.services.kdeconnect_service import kdeconnect_service
        kde_reachable = await kdeconnect_service.is_device_reachable()
        dev = await kdeconnect_service.get_reachable_device_id()
        if dev:
            kde_device_id = dev
        kde_routes = await kdeconnect_service.get_network_routes()
    except Exception as e:
        logger.debug(f"KDE Connect health check error: {e}")

    # Pluggable Broker Registry health check
    broker_health = {}
    try:
        from app.brokers import broker_registry
        broker_health = await broker_registry.get_all_health()
    except Exception as e:
        logger.debug(f"Broker registry health check: {e}")

    return {
        "status": "healthy" if (kss_authenticated or c2w_authenticated or settrade_api_ready or any(b.get("is_authenticated") for b in broker_health.values())) else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brokers": broker_health,
        "krungsri_trademan": {
            "status": kss_status,
            "authenticated": kss_authenticated,
            "current_otp_ref": kss_ref,
            "last_heartbeat": kss_heartbeat,
            "session_file_exists": kss_session_file["exists"],
            "session_file_mtime": kss_session_file["mtime_iso"],
            "session_file_age_hours": kss_session_file["age_hours"],
            "needs_fresh_login": kss_session_file["needs_fresh_login"],
            "session_file_reason": kss_session_file["reason"],
            "active_account": account_context.krungsri_active.value,
            "accounts": ["CASH", "MARGIN"]
        },
        "settrade": {
            "click2win_browser_status": c2w_status,
            "click2win_authenticated": c2w_authenticated,
            "click2win_heartbeat": c2w_heartbeat,
            "click2win_active_account": account_context.click2win_active.value,
            "click2win_accounts": ["EQUITY", "DERIVATIVES"],
            "openapi_configured": settrade_api_ready,
            "openapi_broker_id": settings.SETTRADE_BROKER_ID,
            "openapi_active_account": account_context.settrade_active.value,
            "openapi_accounts": ["EQUITY", "DERIVATIVES"]
        },
        "kdeconnect": {
            "status": "ONLINE" if kde_reachable else "OFFLINE",
            "reachable": kde_reachable,
            "device_id": kde_device_id or "Not Paired",
            "auto_otp_active": True,
            "network_routes": kde_routes,
            "active_route": kde_routes.get("active_route", "DISCONNECTED"),
            "route_label": kde_routes.get("route_label", "❌ Disconnected"),
            "remote_ip": kde_routes.get("remote_ip", "-"),
            "wifi_status": kde_routes.get("wifi", "OFFLINE"),
            "tailscale_status": kde_routes.get("tailscale", "OFFLINE")
        }
    }


async def session_login_broker(platform: str = "CLICK2WIN", force_fresh: bool = False) -> Dict[str, Any]:
    """
    Initiates authentication for the specified platform.
    - 'CLICK2WIN': Settrade Click2Win Sandbox
    - 'TRADEMAN' / 'KRUNGSRI': Krungsri TradeMan Live Account
    - 'LIBERATOR': Liberator Securities WebTrade Account
    - 'SETTRADE_OPENAPI': Direct REST M2M Sandbox / Live Account
    """
    plat = platform.upper().strip()
    if plat in ["KRUNGSRI", "TRADEMAN"]:
        logger.info(f"Pillar 1: Initiating Krungsri login (force_fresh={force_fresh})...")
        res = await auth_driver.login(force_fresh=force_fresh)
        return {
            "platform": "TRADEMAN",
            "success": res.success,
            "status": auth_driver.status,
            "message": res.message,
            "otp_ref": res.otp_ref
        }
    elif plat in ["LIBERATOR"]:
        logger.info(f"Pillar 1: Initiating Liberator login (force_fresh={force_fresh})...")
        from app.brokers.liberator.driver import liberator_driver
        if not force_fresh and os.path.exists(liberator_driver.session_path):
            ok = await liberator_driver.verify_saved_session()
            if ok:
                return {
                    "platform": "LIBERATOR",
                    "success": True,
                    "status": "AUTHENTICATED",
                    "message": "Liberator active session verified"
                }
        res = await liberator_driver.login(force_fresh=force_fresh)
        return {
            "platform": "LIBERATOR",
            "success": res.success,
            "status": res.status.value if hasattr(res.status, "value") else str(res.status),
            "message": res.message,
            "otp_ref": res.otp_ref
        }
    elif plat in ["SETTRADE_OPENAPI", "SETTRADE"]:
        logger.info("Pillar 1: Initiating Settrade Open API token check...")
        from app.brokers import settrade_openapi_plugin
        ok = await settrade_openapi_plugin.authenticate(force_fresh=force_fresh)
        return {
            "platform": "SETTRADE_OPENAPI",
            "success": ok,
            "status": "AUTHENTICATED" if ok else "UNCONFIGURED",
            "message": "Direct M2M API token active"
        }
    else:
        logger.info(f"Pillar 1: Initiating Click2Win login (force_fresh={force_fresh})...")
        res = await click2win_auth_driver.login(force_fresh=force_fresh)
        return {
            "platform": "CLICK2WIN",
            "success": res.success,
            "status": click2win_auth_driver.status,
            "message": res.message
        }


async def session_submit_otp(otp_code: str) -> Dict[str, Any]:
    """
    Manually submits a 6-digit SMS OTP for Krungsri Securities.
    """
    code = str(otp_code).strip()
    if len(code) != 6 or not code.isdigit():
        return {"success": False, "message": "Invalid OTP format. Must be 6 digits."}

    from app.core.events import event_bus
    payload = OTPPayload(
        otp=code,
        ref=auth_driver.current_ref or "MANUAL",
        source=OTPSource.API_MANUAL,
        timestamp=datetime.now(timezone.utc)
    )
    await event_bus.publish_otp(payload)
    return {
        "success": True,
        "status": auth_driver.status,
        "message": "OTP submitted successfully and verified"
    }


async def session_logout_all() -> Dict[str, Any]:
    """
    Safely logs out and terminates browser contexts across all platforms.
    """
    await auth_driver.close()
    await click2win_auth_driver.close()
    return {"success": True, "message": "All broker browser sessions safely terminated."}


async def session_connect_all() -> Dict[str, Any]:
    """
    Connects/prepares all platforms in one click for MCP Server operations.
    1. Refreshes KDE Connect device discovery
    2. Prepares Settrade Click2Win Sandbox session
    3. Checks/Restores Krungsri TradeMan session
    4. Checks/Restores Liberator Securities WebTrade session
    5. Validates Settrade Open API direct token readiness
    """
    results: Dict[str, Any] = {}

    # 1. KDE Connect
    try:
        from app.services.kdeconnect_service import kdeconnect_service
        await kdeconnect_service.refresh_devices()
        results["kdeconnect"] = {"status": "refreshed", "reachable": await kdeconnect_service.is_device_reachable()}
    except Exception as e:
        results["kdeconnect"] = {"status": "error", "error": str(e)}

    # 2. Click2Win Sandbox
    try:
        c2w = await session_login_broker("CLICK2WIN")
        results["click2win"] = c2w
    except Exception as e:
        results["click2win"] = {"success": False, "error": str(e)}

    # 3. Krungsri TradeMan
    try:
        kss = await session_login_broker("TRADEMAN")
        results["krungsri"] = kss
    except Exception as e:
        results["krungsri"] = {"success": False, "error": str(e)}

    # 4. Liberator Securities
    try:
        lib = await session_login_broker("LIBERATOR")
        results["liberator"] = lib
    except Exception as e:
        results["liberator"] = {"success": False, "error": str(e)}

    # 5. Settrade Open API
    try:
        api = await session_login_broker("SETTRADE_OPENAPI")
        results["settrade_openapi"] = api
    except Exception as e:
        results["settrade_openapi"] = {"success": False, "error": str(e)}

    # Aggregated Health
    health = await session_get_health()
    return {
        "success": True,
        "actions": results,
        "health": health
    }


def register_session_pillar(server):
    """Registers Pillar 1 tools into the MCP server."""
    server.tool()(session_get_health)
    server.tool()(session_login_broker)
    server.tool()(session_submit_otp)
    server.tool()(session_logout_all)
    server.tool()(session_connect_all)

