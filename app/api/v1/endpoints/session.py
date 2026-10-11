import os
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from app.browser.auth_driver import auth_driver
from app.core.config import settings
from app.core.events import event_bus
from app.schemas.auth import LoginResult, OTPPayload, OTPSource

router = APIRouter()


class LoginRequest(BaseModel):
    username: Optional[str] = Field(default=None, description="Krungsri username (optional, defaults to .env)")
    password: Optional[str] = Field(default=None, description="Krungsri password (optional, defaults to .env)")
    otp_timeout: Optional[int] = Field(default=None, description="Timeout in seconds to await OTP")
    force_fresh: bool = Field(default=False, description="Force fresh login bypassing saved cookies")


class SessionStatusResponse(BaseModel):
    status: str
    is_authenticated: bool
    current_url: Optional[str] = None
    current_ref: Optional[str] = None
    last_heartbeat: Optional[str] = None
    session_file_exists: bool
    otp_queue_size: int


class SubmitOtpRequest(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit SMS OTP")
    ref: Optional[str] = Field(default=None, description="Reference code")


@router.get("/status", response_model=SessionStatusResponse)
async def get_session_status():
    """Returns the current status of the Playwright browser session."""
    has_state_file = os.path.exists(settings.SESSION_STATE_PATH)
    return SessionStatusResponse(
        status=auth_driver.status,
        is_authenticated=auth_driver.is_authenticated,
        current_url=auth_driver.current_url,
        current_ref=auth_driver.current_ref,
        last_heartbeat=auth_driver.last_heartbeat.isoformat() if auth_driver.last_heartbeat else None,
        session_file_exists=has_state_file,
        otp_queue_size=event_bus.otp_queue.qsize()
    )


@router.post("/login", response_model=LoginResult)
async def trigger_login(request: Optional[LoginRequest] = None):
    """
    Triggers Krungsri Securities automated login.
    If 2FA SMS OTP is required, enters 'AWAITING_OTP' status and waits for KDE Connect auto-capture or web entry.
    """
    req = request or LoginRequest()
    try:
        result = await auth_driver.login(
            username=req.username,
            password=req.password,
            timeout_otp=req.otp_timeout,
            force_fresh=req.force_fresh
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except TimeoutError as te:
        raise HTTPException(status_code=408, detail=str(te))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login execution error: {str(e)}")


@router.post("/submit-otp")
async def submit_otp_directly(payload: SubmitOtpRequest):
    """
    Directly feeds an OTP into the EventBus queue to satisfy an awaiting login flow.
    """
    clean_otp = payload.otp.strip()
    if not (clean_otp.isdigit() and len(clean_otp) == 6):
        raise HTTPException(status_code=400, detail="OTP must be exactly 6 digits.")

    published_otp = await event_bus.publish_otp(
        OTPPayload(
            source=OTPSource.API_MANUAL,
            otp=clean_otp,
            ref=payload.ref
        )
    )
    return {
        "success": True,
        "message": f"OTP {published_otp.masked_otp} published to event queue successfully.",
        "data": published_otp.model_dump()
    }


@router.post("/logout")
async def logout_session():
    """Closes active browser session and removes saved cookies."""
    await auth_driver.close()
    if os.path.exists(settings.SESSION_STATE_PATH):
        try:
            os.remove(settings.SESSION_STATE_PATH)
        except Exception:
            pass
    return {
        "success": True,
        "status": "DISCONNECTED",
        "message": "Session closed and state cleared."
    }


@router.post("/headless")
async def configure_headless(headless: bool = Query(..., description="Set true for headless (background), false for headed (visible)")):
    """Configures whether browser runs in Headless or Headed mode."""
    settings.PLAYWRIGHT_HEADLESS = headless
    return {
        "success": True,
        "headless": settings.PLAYWRIGHT_HEADLESS,
        "message": f"Browser mode updated to {'HEADLESS' if headless else 'HEADED'}. Effective on next launch/restart."
    }


# ------------------------------------------------------------------------------
# Unified 4-Service Cockpit Endpoints (Pillar 1)
# ------------------------------------------------------------------------------

@router.get("/health")
async def get_unified_health():
    """Returns aggregated real-time health for Krungsri, Click2Win, Settrade Open API, and KDE Connect."""
    from app.mcp.pillars.pillar1_session import session_get_health
    return await session_get_health()


@router.post("/connect-all")
async def trigger_connect_all():
    """Triggers 1-click connection/preparation for all brokers and hardware bridges."""
    from app.mcp.pillars.pillar1_session import session_connect_all
    return await session_connect_all()


class BrokerLoginRequest(BaseModel):
    platform: str = Field(default="CLICK2WIN", description="CLICK2WIN or KRUNGSRI / TRADEMAN")
    force_fresh: bool = Field(default=False, description="Force fresh login bypassing saved cookies")


@router.post("/login-broker")
async def trigger_broker_login(payload: BrokerLoginRequest):
    """Initiates login for the requested platform (Click2Win or Krungsri)."""
    from app.mcp.pillars.pillar1_session import session_login_broker
    return await session_login_broker(platform=payload.platform, force_fresh=payload.force_fresh)


@router.post("/kdeconnect/ping", summary="Ping paired Android device via KDE Connect")
async def ping_kdeconnect_device():
    """Sends high priority test ping to phone and returns refreshed network routes."""
    from app.services.kdeconnect_service import kdeconnect_service
    success = await kdeconnect_service.send_critical_alert("Homelab Ping", "🔔 Homelab Ping: Connection Verified!")
    routes = await kdeconnect_service.get_network_routes()
    return {
        "success": success,
        "message": "Ping sent to phone successfully" if success else "Failed to send ping to phone",
        "network_routes": routes
    }


@router.get("/brokers")
async def list_registered_brokers():
    """Returns metadata, status, and capabilities for all registered broker plugins."""
    from app.brokers import broker_registry
    return {
        "success": True,
        "brokers": broker_registry.list_all()
    }


@router.get("/brokers/{broker_name}/summary")
async def get_broker_summary(broker_name: str):
    """Retrieves real-time account summary and balance metrics for a registered broker."""
    from app.brokers import broker_registry
    plugin = broker_registry.get(broker_name.lower())
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_name}' not found")
    summary = await plugin.get_account_summary()
    return {
        "success": True,
        "broker_name": broker_name,
        "summary": summary.model_dump() if hasattr(summary, "model_dump") else summary.dict()
    }


@router.get("/brokers/{broker_name}/portfolio")
async def get_broker_portfolio(broker_name: str):
    """Retrieves full portfolio snapshot, cash balance, and stock holdings for a registered broker."""
    from app.brokers import broker_registry
    plugin = broker_registry.get(broker_name.lower())
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_name}' not found")
    port = await plugin.get_portfolio()
    return {
        "success": True,
        "broker_name": broker_name,
        "account_no": port.account_no,
        "summary": port.account_summary.model_dump() if hasattr(port.account_summary, "model_dump") else port.account_summary.dict(),
        "positions": [p.model_dump() if hasattr(p, "model_dump") else p.dict() for p in port.positions],
        "as_of": port.as_of.isoformat()
    }



