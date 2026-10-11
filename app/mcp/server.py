"""
Master 6-Pillars Modular MCP Server Gateway for Investment Homelab.
Mounts all Domain Pillars onto the MCP SSE Transport:
1. Session Sentinel
2. Account & Portfolio
3. Trade Execution
4. SBL Intelligence
5. Tactical Strategy Center
6. Agentic Orchestration
"""

import logging
from mcp.server.mcpserver import MCPServer
from mcp.server.sse import TransportSecuritySettings

from app.mcp.pillars import (
    register_session_pillar,
    register_trade_pillar,
    register_sbl_pillar,
    register_portfolio_pillar,
    register_strategy_pillar,
    register_agentic_pillar,
    mcp_get_6pillars_overview
)

logger = logging.getLogger("ModularMCPServer")

# Master MCP Server instance
mcp = MCPServer(name="InvestmentHomelab-6Pillars-Gateway")

# Register Architecture Overview Discovery Tool
mcp.tool()(mcp_get_6pillars_overview)

# Register all 7 Pillars cleanly
register_session_pillar(mcp)
register_trade_pillar(mcp)
register_sbl_pillar(mcp)
register_portfolio_pillar(mcp)
register_strategy_pillar(mcp)
register_agentic_pillar(mcp)

logger.info("Modular MCP Server: Successfully registered all Domain Pillars and Architecture Overview tool.")


def get_modular_sse_app():
    """
    Returns the Starlette ASGI application for SSE and Messages handling.
    Configured with DNS rebinding protection disabled to permit Tailscale IP traffic seamlessly.
    """
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return mcp.sse_app(
        sse_path="/sse",
        message_path="/messages/",
        transport_security=security
    )


if __name__ == "__main__":
    mcp.run()
