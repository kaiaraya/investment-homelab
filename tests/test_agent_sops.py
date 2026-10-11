import pytest
from pathlib import Path
from app.ai.agents import (
    SessionSentinelAgent,
    MarketAnalystAgent,
    OrderExecutionAgent,
    SBLManagerAgent,
    PortfolioRiskAgent,
)

DIRECTIVES_DIR = Path(__file__).resolve().parent.parent / "directives" / "sops"


def test_sop_files_exist():
    """Verify that all 5 Directive SOP markdown files exist on disk."""
    expected_sops = [
        "sop_session_security.md",
        "sop_market_signals.md",
        "sop_order_execution.md",
        "sop_sbl_lifecycle.md",
        "sop_portfolio_risk.md",
    ]
    for sop_name in expected_sops:
        sop_file = DIRECTIVES_DIR / sop_name
        assert sop_file.exists(), f"Directive SOP missing: {sop_name}"
        content = sop_file.read_text(encoding="utf-8")
        assert len(content) > 100, f"SOP {sop_name} is too short"
        assert "Standard Operating Procedure" in content or "SOP-" in content


def test_sub_agents_initialization():
    """Verify that all 5 Sub-Agents instantiate and load their respective SOPs."""
    session_agent = SessionSentinelAgent()
    assert session_agent.name == "SessionSentinelAgent"
    assert "Session Sentinel & Security" in session_agent.sop_content or "SOP-001" in session_agent.sop_content

    market_agent = MarketAnalystAgent()
    assert market_agent.name == "MarketAnalystAgent"
    assert "Market Intelligence" in market_agent.sop_content or "SOP-002" in market_agent.sop_content

    order_agent = OrderExecutionAgent()
    assert order_agent.name == "OrderExecutionAgent"
    assert "Order Execution" in order_agent.sop_content or "SOP-003" in order_agent.sop_content

    sbl_agent = SBLManagerAgent()
    assert sbl_agent.name == "SBLManagerAgent"
    assert "SBL Lifecycle" in sbl_agent.sop_content or "SOP-004" in sbl_agent.sop_content

    portfolio_agent = PortfolioRiskAgent()
    assert portfolio_agent.name == "PortfolioRiskAgent"
    assert "Portfolio Intelligence" in portfolio_agent.sop_content or "SOP-005" in portfolio_agent.sop_content
