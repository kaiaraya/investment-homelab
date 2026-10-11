"""
Pillar 7: Nick Saraev DOE Agentic Multi-Agent & Emergency Safety Controller
Exposes remote tools to trigger PT-MRO cycles, inspect agent reasoning audit trails,
and trigger/reset the Emergency Kill Switch.
"""

import logging
from typing import Any, Dict, Optional
from mcp.server.mcpserver import MCPServer
from app.ai.orchestrator import master_orchestrator
from app.ai.memory import agent_memory
from app.services.kill_switch_service import kill_switch_service

logger = logging.getLogger("Pillar7Agentic")


def register_agentic_pillar(mcp: MCPServer) -> None:
    """Registers the Agentic Orchestration & Safety Controller tools on the MCP server."""

    @mcp.tool()
    async def agent_trigger_cycle(
        regime: str = "AUTO_TRADING",
        trigger_source: str = "REMOTE_MCP",
    ) -> Dict[str, Any]:
        """
        Executes an on-demand PT-MRO Multi-Agent cycle (Planning, Tools, Memory, Reflection, Orchestration).
        Args:
            regime: Target market regime ('PRE_MARKET', 'AUTO_TRADING', 'DAY_CLOSE', 'POST_MARKET').
            trigger_source: Origin of trigger ('REMOTE_MCP', 'USER_IDE', 'EXTERNAL_CRON').
        """
        logger.info(f"MCP: Triggering PT-MRO cycle for regime: {regime} from {trigger_source}")
        return await master_orchestrator.execute_pt_mro_cycle(
            regime=regime,
            trigger_source=trigger_source,
        )

    @mcp.tool()
    async def agent_get_audit_trail(
        agent_name: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Retrieves the persistent SQLite audit trail of agent thoughts, decisions, tool invocations, and reflection outcomes.
        Args:
            agent_name: Filter by agent ('MasterOrchestrator', 'SessionSentinelAgent', 'MarketAnalystAgent', 'OrderExecutionAgent', 'SBLManagerAgent', 'PortfolioRiskAgent').
            action_type: Filter by action ('PLAN', 'TOOL_CALL', 'REFLECTION', 'ANNEAL', 'KILL_SWITCH').
            limit: Number of recent records to return (1-100).
        """
        records = await agent_memory.get_recent_audit_trail(agent_name=agent_name, action_type=action_type, limit=limit)
        return {"count": len(records), "records": records}

    @mcp.tool()
    async def emergency_panic_kill_switch(
        reason: str = "Triggered via Remote MCP Panic Tool",
        triggered_by: str = "REMOTE_MCP_USER",
    ) -> Dict[str, Any]:
        """
        EMERGENCY KILL SWITCH: Freezes all autonomous agent trading, immediately requests
        cancellation of all open/unmatched orders on the broker, and alerts user via LINE & mobile push.
        """
        logger.critical(f"MCP: EMERGENCY KILL SWITCH invoked by {triggered_by}: {reason}")
        return await kill_switch_service.activate(reason=reason, triggered_by=triggered_by)

    @mcp.tool()
    async def emergency_reset_kill_switch(
        authorized_by: str = "REMOTE_MCP_USER",
    ) -> Dict[str, Any]:
        """
        Resets the Emergency Kill Switch and restores normal trading operations.
        """
        logger.info(f"MCP: Resetting Emergency Kill Switch by {authorized_by}")
        return await kill_switch_service.reset(authorized_by=authorized_by)

    @mcp.tool()
    async def agent_get_working_memory() -> Dict[str, Any]:
        """
        Retrieves the current short-term working memory cache (active symbols, quotes, active regime, kill switch status).
        """
        return {
            "kill_switch_active": kill_switch_service.is_active(),
            "working_memory": agent_memory.get_all_working_memory(),
        }

    logger.info("Registered Pillar 7 (Nick Saraev DOE Agentic & Safety Controller) MCP tools.")
