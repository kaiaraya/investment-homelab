import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Query
from app.services.kill_switch_service import kill_switch_service
from app.ai.orchestrator import master_orchestrator
from app.ai.memory import agent_memory

logger = logging.getLogger(__name__)

router = APIRouter()


class KillSwitchRequest(BaseModel):
    reason: str = "Manual User Panic Trigger"
    triggered_by: str = "WEB_CONSOLE"


class ResetRequest(BaseModel):
    authorized_by: str = "WEB_CONSOLE"


class CycleRequest(BaseModel):
    regime: str = "TACTICAL_ON_DEMAND"
    trigger_source: str = "API"


@router.post("/kill-switch/activate")
async def activate_kill_switch(payload: KillSwitchRequest) -> Dict[str, Any]:
    """Activates the Emergency Kill Switch, aborts trades, and cancels open orders."""
    return await kill_switch_service.activate(reason=payload.reason, triggered_by=payload.triggered_by)


@router.post("/kill-switch/reset")
async def reset_kill_switch(payload: ResetRequest) -> Dict[str, Any]:
    """Resets the Emergency Kill Switch and returns system to normal operations."""
    return await kill_switch_service.reset(authorized_by=payload.authorized_by)


@router.get("/kill-switch/status")
async def get_kill_switch_status() -> Dict[str, Any]:
    """Returns the current status of the Emergency Kill Switch."""
    return kill_switch_service.get_status()


@router.post("/cycle/trigger")
async def trigger_agentic_cycle(payload: CycleRequest) -> Dict[str, Any]:
    """Triggers an on-demand PT-MRO Multi-Agent cycle."""
    return await master_orchestrator.execute_pt_mro_cycle(
        regime=payload.regime,
        trigger_source=payload.trigger_source,
    )


@router.get("/audit-trail")
async def get_audit_trail(
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=200, description="Max entries to return"),
) -> Dict[str, Any]:
    """Returns the SQLite persistent audit trail of agent reasoning and decisions."""
    records = await agent_memory.get_recent_audit_trail(agent_name=agent_name, action_type=action_type, limit=limit)
    return {"total": len(records), "records": records}


@router.get("/memory")
async def get_working_memory() -> Dict[str, Any]:
    """Returns the short-term in-memory cache of live quotes and active symbols."""
    return agent_memory.get_all_working_memory()
