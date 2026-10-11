"""
Pillars Architecture Metadata & Discovery Tool for MCP Agents.
Exposes comprehensive documentation, schemas, and broker capabilities
directly to Remote AI Agents connecting via Model Context Protocol.
"""

from typing import Any, Dict, List
from datetime import datetime, timezone

from app.brokers import broker_registry


async def mcp_get_6pillars_overview() -> Dict[str, Any]:
    """
    Returns the comprehensive architectural blueprint of the Pillars of Investment Homelab,
    including registered brokers, transport types, available MCP tools, guardrails, and connection endpoints.
    AI Agents can use this tool to discover available trading capabilities and plan execution workflows.
    """
    brokers_meta = []
    for name, info in broker_registry.list_all().items():
        brokers_meta.append({
            "id": name,
            "name": info.get("display_name", name),
            "transport": info.get("transport", "UNKNOWN"),
            "is_configured": info.get("is_configured", False),
            "supported_markets": info.get("supported_markets", []),
            "supports_sbl": info.get("supports_sbl", False),
            "supports_direct_api": info.get("supports_direct_api", False)
        })

    return {
        "system": {
            "name": "Investment Homelab 6-Pillars Trading Gateway",
            "version": "2.0.0",
            "architecture": "6-Pillars Domain-Driven Architecture with Pluggable Multi-Broker Engine",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoints": {
                "mcp_sse_tailscale": "http://100.88.217.33:8000/sse",
                "mcp_sse_local": "http://localhost:8000/sse",
                "operations_cockpit": "http://localhost:8000/console",
                "cockpit_stream": "http://localhost:8000/api/v1/cockpit/stream",
                "api_docs": "http://localhost:8000/docs"
            }
        },
        "registered_brokers": brokers_meta,
        "six_pillars": {
            "pillar1_session": {
                "name": "Pillar 1: Session Sentinel",
                "description": "Unified authentication, session lifecycle, and 2FA SMS OTP routing across all brokers and hardware bridges.",
                "key_capabilities": [
                    "Unified multi-broker session health monitoring across 4 brokers",
                    "KDE Connect SMS OTP hardware bridge over Tailscale/LAN",
                    "Multi-tab Playwright session reuse & auto-recovery",
                    "Clean logout and session cookie management"
                ],
                "tools": [
                    "session_get_health",
                    "session_login_broker",
                    "session_submit_otp",
                    "session_logout_all",
                    "session_connect_all"
                ]
            },
            "pillar3_trade": {
                "name": "Pillar 3: Trade Execution",
                "description": "Risk-validated order dispatching, price modification, and order cancellation across all brokers.",
                "key_capabilities": [
                    "Pre-trade odd-lot validation (Volume % 100 == 0)",
                    "Purchasing power & account capability enforcement",
                    "Dynamic routing to active broker plugin (Click2Win / Settrade / Krungsri / Liberator)",
                    "Direct REST order execution (<50ms) or Playwright browser execution"
                ],
                "tools": [
                    "trade_place_order",
                    "trade_cancel_order",
                    "trade_modify_price"
                ]
            },
            "pillar4_sbl": {
                "name": "Pillar 4: SBL Intelligence",
                "description": "Stock Borrowing and Lending management for covered short selling (Krungsri TradeMan Pro exclusive).",
                "key_capabilities": [
                    "Multi-page SBL available inventory scraping",
                    "Borrow execution with Broker Lot Tracking ID",
                    "Return execution to stop interest accrual",
                    "XD & corporate action dividend compensation risk check",
                    "Automated candidate short viability audit (BORROW_ALLOWED, CAUTION_XD_RISK, OUT_OF_STOCK)"
                ],
                "tools": [
                    "sbl_get_inventory",
                    "sbl_borrow_stock",
                    "sbl_return_stock",
                    "sbl_check_corporate_actions",
                    "sbl_audit_short_candidates"
                ]
            },
            "pillar2_portfolio": {
                "name": "Pillar 2: Account & Portfolio",
                "description": "Multi-account directory, account switching, purchasing-power balances, holdings, and open orders across Krungsri, Liberator, Click2Win and Settrade Open API.",
                "key_capabilities": [
                    "Multi-account directory & capability inspection (Cash, Margin, Equity, TFEX)",
                    "Account switching per broker (Krungsri CASH/MARGIN, Liberator single-account CASH)",
                    "Purchasing power balances (Cash Balance, Line Available, Credit Limit, Excess Equity)",
                    "Holdings aggregation (Symbol, Volume, Avg Cost, Market Price, Unrealized PnL)",
                    "Unmatched open orders query (Queuing/SX)",
                    "SQLite snapshot synchronization"
                ],
                "tools": [
                    "portfolio_list_accounts",
                    "switch_account",
                    "portfolio_get_balances",
                    "portfolio_holdings",
                    "current_open_orders",
                    "portfolio_sync_db"
                ]
            },
            "pillar6_strategy": {
                "name": "Pillar 6: Tactical Strategy Center",
                "description": "Time-based tactical order execution and automated order book management.",
                "key_capabilities": [
                    "Passive price negotiation for queuing orders at 11:00 & 15:30 (sniping Best Bid 1 / Best Offer 1)",
                    "End-of-Day unmatched order cleanup at 16:35 (prevents overnight lingering orders)",
                    "Strategy execution status reporting"
                ],
                "tools": [
                    "strategy_negotiate_unmatched_orders",
                    "strategy_eod_order_cleanup",
                    "strategy_list_active"
                ]
            }
        },
        "guardrails": [
            {
                "name": "Pre-trade Odd-Lot Guard",
                "rule": "Volume % 100 == 0 strictly enforced before dispatching equity orders"
            },
            {
                "name": "Account Capability Matrix",
                "rule": "Stock orders restricted to EQUITY/CASH accounts; TFEX restricted to DERIVATIVES accounts; SBL strictly restricted to Krungsri MARGIN accounts"
            },
            {
                "name": "Krungsri Read-Only Safety Mode",
                "rule": "Orders on Krungsri live accounts are blocked in safety mode unless explicit confirmation is provided"
            }
        ]
    }
