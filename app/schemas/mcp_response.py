"""
Type-Safe Response Schemas and Guardrail Protocol for MCP Tools.
Ensures zero-hallucination, explicit maintenance states, and HITL escalation tracking.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MCPToolStatus(str, Enum):
    """Execution status for all MCP Tool invocations across all 6 Pillars."""
    SUCCESS = "SUCCESS"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"
    NEEDS_ADMIN_ATTENTION = "NEEDS_ADMIN_ATTENTION"
    GUARDRAIL_REJECTED = "GUARDRAIL_REJECTED"
    FAILED = "FAILED"


class BaseMCPResponse(BaseModel):
    """
    Standard Type-Safe MCP Tool response payload.
    Used by remote agents to safely evaluate execution state without guessing.
    """
    success: bool
    status: MCPToolStatus = MCPToolStatus.SUCCESS
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    escalated_to_admin: bool = False
    maintenance_mode: bool = False


def create_maintenance_response(
    reason: str,
    escalated: bool = True,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Constructs a safe, truthful response indicating system maintenance / uncertainty.
    Prevents remote agents from executing dangerous trades on missing or mock data.
    """
    return BaseMCPResponse(
        success=False,
        status=MCPToolStatus.UNDER_MAINTENANCE,
        message="ระบบกำลังปรับปรุง โปรดติดต่อ Admin เนื่องจากข้อมูลยังไม่พร้อม (มีความเสี่ยงสูง)",
        error=reason,
        escalated_to_admin=escalated,
        maintenance_mode=True,
        data=details
    ).model_dump()


def create_admin_attention_response(
    reason: str,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Constructs an escalation response when a workflow anomaly requires on-screen human inspection.
    """
    return BaseMCPResponse(
        success=False,
        status=MCPToolStatus.NEEDS_ADMIN_ATTENTION,
        message=f"ระบบต้องการความช่วยเหลือจาก Admin: {reason}",
        error=reason,
        escalated_to_admin=True,
        data=details
    ).model_dump()


def create_success_response(
    data: Optional[Dict[str, Any]] = None,
    message: str = "Operation completed successfully"
) -> Dict[str, Any]:
    """
    Constructs a standard successful MCP Tool response.
    """
    return BaseMCPResponse(
        success=True,
        status=MCPToolStatus.SUCCESS,
        message=message,
        data=data
    ).model_dump()
