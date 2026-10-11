"""
Unit & Integration Test Suite for Pillar 4 SBL Remote MCP Capabilities.
Tests:
1. SBL candidate classification (BORROW_ALLOWED, CAUTION_XD_RISK, OUT_OF_STOCK).
2. SET SBL daily accrued fee calculation formula.
3. FastMCP tool registration and direct invocation of sbl_audit_short_candidates.
4. Architectural discovery metadata in 6-Pillars overview.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.mcp.server import mcp
from app.mcp.pillars.pillar4_sbl import sbl_audit_short_candidates
from app.mcp.pillars.overview import mcp_get_6pillars_overview
from app.services.sbl_intelligence_service import sbl_intelligence_service


@pytest.fixture
def mock_sbl_data():
    return {
        "status": "SUCCESS",
        "data": {
            "set50_inventory": [
                {
                    "symbol": "CPALL",
                    "borrow_fee_pct": 3.5,
                    "available_qty": 2_660_300,
                    "initial_margin_pct": 50.0
                },
                {
                    "symbol": "DELTA",
                    "borrow_fee_pct": 3.5,
                    "available_qty": 850_000,
                    "initial_margin_pct": 50.0
                },
                {
                    "symbol": "EMPTY_STOCK",
                    "borrow_fee_pct": 3.5,
                    "available_qty": 0,
                    "initial_margin_pct": 50.0
                }
            ],
            "xd_xr_inventory": [
                {
                    "symbol": "BANPU",
                    "borrow_fee_pct": 3.5,
                    "available_qty": 500_000,
                    "initial_margin_pct": 50.0,
                    "sign": "XD"
                },
                {
                    "symbol": "SCB",
                    "borrow_fee_pct": 3.5,
                    "available_qty": 0,
                    "initial_margin_pct": 50.0,
                    "sign": "XD"
                }
            ],
            "sbl_portfolio_lots": []
        }
    }


@pytest.mark.asyncio
async def test_sbl_audit_candidates_classification(mock_sbl_data):
    """
    Verifies that audit_sbl_candidates correctly classifies:
    - CPALL -> BORROW_ALLOWED (has available inventory, no XD)
    - BANPU -> CAUTION_XD_RISK (in XD/XR table, high dividend compensation risk)
    - EMPTY_STOCK -> OUT_OF_STOCK (0 available inventory)
    - NONEXISTENT -> OUT_OF_STOCK (not in inventory)
    """
    with patch("app.browser.trademan_driver.trademan_driver.scrape_sbl_all_tabs", new_callable=AsyncMock) as m_scrape:
        m_scrape.return_value = mock_sbl_data
        
        candidates = ["CPALL", "BANPU", "EMPTY_STOCK", "NONEXISTENT"]
        res = await sbl_intelligence_service.audit_sbl_candidates(candidates, sbl_data=mock_sbl_data)

        assert res["success"] is True
        assert res["summary"]["total_audited"] == 4
        assert res["summary"]["borrow_allowed_count"] == 1
        assert res["summary"]["caution_xd_count"] == 1
        assert res["summary"]["out_of_stock_count"] == 2

        # 1. CPALL: Allowed
        cpall = res["candidates"]["CPALL"]
        assert cpall["verdict"] == "BORROW_ALLOWED"
        assert cpall["action_allowed"] is True
        assert cpall["available_qty"] == 2_660_300
        assert cpall["has_xd_risk"] is False

        # 2. BANPU: Hard Blocked XD
        banpu = res["candidates"]["BANPU"]
        assert banpu["verdict"] == "HARD_BLOCKED_XD_XR"
        assert banpu["action_allowed"] is False
        assert banpu["has_xd_risk"] is True
        assert "ชดเชยปันผล" in banpu["warning_message"]

        # 3. EMPTY_STOCK: Out of stock
        empty = res["candidates"]["EMPTY_STOCK"]
        assert empty["verdict"] == "OUT_OF_STOCK"
        assert empty["action_allowed"] is False

        # 4. NONEXISTENT: Out of stock
        nonexistent = res["candidates"]["NONEXISTENT"]
        assert nonexistent["verdict"] == "OUT_OF_STOCK"
        assert nonexistent["action_allowed"] is False


@pytest.mark.asyncio
async def test_sbl_daily_fee_math(mock_sbl_data):
    """
    Verifies the daily fee per 100,000 THB calculation:
    Formula: (100,000 * 3.50%) / 365 = ~9.59 THB/day
    """
    res = await sbl_intelligence_service.audit_sbl_candidates(["CPALL"], sbl_data=mock_sbl_data)
    cpall = res["candidates"]["CPALL"]
    
    expected_daily_fee = round((100000.0 * 0.035) / 365, 2)  # 9.59
    assert cpall["daily_fee_per_100k_thb"] == expected_daily_fee
    assert cpall["daily_fee_per_100k_thb"] == 9.59


@pytest.mark.asyncio
async def test_mcp_pillar4_tool_invocation(mock_sbl_data):
    """
    Verifies calling sbl_audit_short_candidates through Pillar 4 MCP function.
    """
    mock_cached = dict(mock_sbl_data["data"])
    mock_cached["success"] = True
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.get_cached_data", return_value=mock_cached):
        # Test empty input handling
        empty_res = await sbl_audit_short_candidates([])
        assert empty_res["success"] is False
        assert "No valid symbols" in empty_res["error"]

        # Test valid symbols
        audit_res = await sbl_audit_short_candidates(["CPALL", "DELTA", "BANPU"])
        assert audit_res["success"] is True
        assert "CPALL" in audit_res["candidates"]
        assert "DELTA" in audit_res["candidates"]
        assert "BANPU" in audit_res["candidates"]
        assert audit_res["candidates"]["DELTA"]["verdict"] == "BORROW_ALLOWED"
        assert audit_res["candidates"]["BANPU"]["verdict"] == "HARD_BLOCKED_XD_XR"


@pytest.mark.asyncio
async def test_mcp_server_registration_and_overview():
    """
    Verifies that:
    1. sbl_audit_short_candidates is registered on the master MCP server.
    2. mcp_get_6pillars_overview lists sbl_audit_short_candidates in Pillar 4 tools.
    """
    # 1. Check MCP server registered tools
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "sbl_audit_short_candidates" in tool_names
    assert "sbl_get_inventory" in tool_names

    # 2. Check 6-Pillars overview metadata
    overview = await mcp_get_6pillars_overview()
    pillar4_tools = overview["six_pillars"]["pillar4_sbl"]["tools"]
    assert "sbl_audit_short_candidates" in pillar4_tools
    assert "sbl_get_inventory" in pillar4_tools
