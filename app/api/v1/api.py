from fastapi import APIRouter
from app.api.v1.endpoints import (
    webhook_line,
    webhook_signal,
    orders,
    session,
    health,
    phase3,
    cockpit,
    agentic,
    admin
)
from app.api.v1 import live_probe

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health & Status"])
api_router.include_router(session.router, prefix="/session", tags=["Session & Browser"])
api_router.include_router(agentic.router, prefix="/agentic", tags=["Nick Saraev DOE Agentic Engine & Kill Switch"])
api_router.include_router(webhook_line.router, prefix="/webhook", tags=["LINE Webhook"])
api_router.include_router(webhook_signal.router, prefix="/webhook", tags=["Signal Intelligence"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders & Queue"])
api_router.include_router(phase3.router, prefix="/phase3", tags=["Phase 3: 4 Core Centers"])
api_router.include_router(cockpit.router, prefix="/cockpit", tags=["Operations Cockpit SSE"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin Console Control"])
api_router.include_router(live_probe.router, tags=["Simulation & Live Probes"])



