import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.init_db import init_db
from app.api.v1.api import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("homelab")


# Hide high-frequency /console polling requests from the uvicorn access log
# (errors and all other requests are still logged).
_QUIET_POLL_PATHS = (
    "/api/v1/orders/hitl/pending",
    "/api/v1/session/health",
    "/api/v1/agentic/kill-switch",
)


class _PollingAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 5:
            path, status = str(args[2]), args[4]
            if path.startswith(_QUIET_POLL_PATHS) and isinstance(status, int) and status < 400:
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(_PollingAccessFilter())


from app.browser.session_sentinel import session_sentinel
from app.browser.auth_driver import auth_driver
from app.services.phase3_scheduler import phase3_scheduler
from app.services.action_exit_dispatcher import action_exit_dispatcher
from app.ai.orchestrator import master_orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler: initializes DB tables, session monitor, Phase 3 scheduler, and background resources."""
    logger.info("Starting Investment Homelab Gateway...")
    await init_db()
    logger.info("Database initialized. Ready to receive webhooks.")
    await session_sentinel.start()
    
    # Start Tactical Action Exit Autonomous Dispatcher & 09:45 Pre-Flight Daemon
    # Slim-gateway: defaults OFF (ENABLE_ACTION_EXIT_DISPATCHER=False) so an OTP/auth-only
    # boot does not spawn the Pillar-2 order-exit daemon. Enable when testing exits.
    if settings.ENABLE_ACTION_EXIT_DISPATCHER:
        action_exit_dispatcher.start()
        logger.info("Tactical Action Exit Autonomous Dispatcher started.")
    else:
        logger.info("Action-Exit Dispatcher is DISABLED (ENABLE_ACTION_EXIT_DISPATCHER=False).")

    # Start Autonomous PT-MRO Master Orchestrator Daemon
    if settings.ENABLE_AGENTIC_ORCHESTRATOR:
        master_orchestrator.start_background_loop()
        logger.info("Autonomous MasterOrchestrator PT-MRO background loop started.")
    else:
        logger.info("MasterOrchestrator is DISABLED (ENABLE_AGENTIC_ORCHESTRATOR=False).")

    if settings.ENABLE_INTRADAY_SCHEDULER:
        logger.info("Starting Intraday Scheduler (8 Market Regimes)...")
        await phase3_scheduler.start()
    else:
        logger.info("Intraday Scheduler is DISABLED (ENABLE_INTRADAY_SCHEDULER=False). Running in Isolated/Debug mode.")

    # Note: /console launch is strictly managed by scripts/start_homelab.py after its readiness stages pass
    # (Stage 1 OTP relay (LINE group) + Stage 2 Krungsri login gates; Stage 3 Liberator is optional).

    yield
    logger.info("Shutting down Investment Homelab Gateway...")
    if settings.ENABLE_AGENTIC_ORCHESTRATOR:
        await master_orchestrator.stop_background_loop()
    if settings.ENABLE_ACTION_EXIT_DISPATCHER:
        await action_exit_dispatcher.stop()
    if settings.ENABLE_INTRADAY_SCHEDULER:
        await phase3_scheduler.stop()
    await session_sentinel.stop()
    await auth_driver.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Semi-Automated Trading & SBL Lifecycle Homelab Gateway",
    lifespan=lifespan
)

# Enable CORS for local testing and future Web Dashboard (Phase 5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import HTMLResponse
from app.console import CONSOLE_HTML

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", response_class=HTMLResponse)
@app.get("/console", response_class=HTMLResponse)
async def test_console():
    """Interactive Phase 1 Test Console with 1-click test actions."""
    return HTMLResponse(content=CONSOLE_HTML)


@app.get("/api")
async def api_info():
    return {
        "app": settings.PROJECT_NAME,
        "status": "online",
        "console": "/console",
        "docs": "/docs",
        "api_v1": settings.API_V1_STR
    }


@app.get("/health")
async def root_health():
    return {"status": "healthy"}


# ------------------------------------------------------------------------------
# Static Screenshots & Remote MCP Server (SSE Transport)
# ------------------------------------------------------------------------------
import os
from fastapi.staticfiles import StaticFiles
from app.mcp.server import get_modular_sse_app

# 1. Mount Static Screenshots Directory for Tailscale HTTP Access
SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")

# 2. Mount Next-Gen 6-Pillars Modular MCP Server at root (/sse and /messages/)
app.mount("/", get_modular_sse_app())
