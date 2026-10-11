"""
Modular Pillars Architecture for Investment Homelab MCP Gateway.
Pillars:
1. Session Sentinel (Auth & Connection Health)
2. Account & Portfolio (Accounts, Balances, Holdings, Open Orders, Account Switching)
3. Trade Execution (Direct API Orders)
4. SBL Intelligence (Krungsri SBL Multi-page)
5. Tactical Strategy (Price Negotiation 11:00/15:30, EOD Order Cleanup)
6. Agentic Orchestration (PT-MRO Multi-Agent Cycle, Emergency Kill Switch)
"""

from .pillar1_session import register_session_pillar
from .pillar3_trade import register_trade_pillar
from .pillar4_sbl import register_sbl_pillar
from .pillar2_portfolio import register_portfolio_pillar
from .pillar6_strategy import register_strategy_pillar
from .pillar7_agentic import register_agentic_pillar
from .overview import mcp_get_6pillars_overview

__all__ = [
    "register_session_pillar",
    "register_trade_pillar",
    "register_sbl_pillar",
    "register_portfolio_pillar",
    "register_strategy_pillar",
    "register_agentic_pillar",
    "mcp_get_6pillars_overview",
]
