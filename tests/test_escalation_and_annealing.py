"""
Test Suite: Self-Annealing, HITL Escalation via KDE Connect, and Type-Safe MCP Maintenance Responses.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.schemas.mcp_response import (
    MCPToolStatus,
    BaseMCPResponse,
    create_maintenance_response,
    create_admin_attention_response,
    create_success_response
)
from app.services.kdeconnect_service import KdeConnectService
from app.services.workflow_engine import WorkflowEngine
from app.mcp.pillars.pillar2_portfolio import (
    portfolio_holdings,
    switch_account
)


def test_mcp_response_typesafe_contract():
    """Verifies that maintenance and attention responses conform strictly to BaseMCPResponse."""
    maint = create_maintenance_response("Session expired on Click2Win", escalated=True)
    assert maint["success"] is False
    assert maint["status"] == MCPToolStatus.UNDER_MAINTENANCE.value
    assert "ระบบกำลังปรับปรุง" in maint["message"]
    assert maint["maintenance_mode"] is True
    assert maint["escalated_to_admin"] is True
    assert "Session expired" in maint["error"]

    attn = create_admin_attention_response("2FA OTP window timed out")
    assert attn["success"] is False
    assert attn["status"] == MCPToolStatus.NEEDS_ADMIN_ATTENTION.value
    assert attn["escalated_to_admin"] is True

    succ = create_success_response({"account_no": "CW32_E_7338419"})
    assert succ["success"] is True
    assert succ["status"] == MCPToolStatus.SUCCESS.value
    assert succ["data"]["account_no"] == "CW32_E_7338419"


@pytest.mark.asyncio
async def test_kdeconnect_screen_help_alert():
    """Verifies that notify_admin_screen_help sends a ping message with 'มาดูที่จอหน่อย มีปัญหาให้ช่วย'."""
    kde = KdeConnectService()
    with patch.object(kde, "send_critical_alert", new_callable=AsyncMock) as m_crit:
        m_crit.return_value = True
        res = await kde.notify_admin_screen_help("DOM Table not found", workflow_or_step="Step 3: Table Scrape")
        assert res is True
        m_crit.assert_called_once()
        title, body = m_crit.call_args[0]
        assert title == "HITL Escalation"
        assert "มาดูที่จอหน่อย มีปัญหาให้ช่วย" in body
        assert "DOM Table not found" in body
        assert "Step 3: Table Scrape" in body


@pytest.mark.asyncio
async def test_workflow_engine_4step_self_annealing_and_escalation(tmp_path):
    """
    Verifies that WorkflowEngine:
    1. Dismisses popups on initial failure
    2. Tries fallback selectors and succeeds if fallback works
    3. Escalates to KDE Connect and returns maintenance response if all fallbacks fail
    """
    engine = WorkflowEngine()

    # Create dummy workflow spec
    wf_name = "test_anneal_wf"
    engine.save_workflow_spec(
        name=wf_name,
        title="Test Anneal Workflow",
        description="Test workflow for self-annealing verification",
        steps=[
            {
                "action": "CLICK",
                "selector": "#non-existent-button",
                "fallback_selectors": ["#fallback-button"],
                "description": "Click target"
            }
        ]
    )

    # Scenario 1: Fallback selector succeeds
    mock_page = MagicMock()
    mock_el = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=[
        Exception("Timeout waiting for #non-existent-button"),  # initial fails
        mock_el  # fallback succeeds
    ])
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.is_closed = False

    with patch("app.services.workflow_engine.get_broker_driver") as m_bd, \
         patch("app.browser.popup_manager.popup_manager.dismiss_popups", new_callable=AsyncMock) as m_dismiss:
        m_bd.return_value = MagicMock(page=mock_page)

        res = await engine.execute_workflow(wf_name)
        assert res["success"] is True
        assert res["status"] == "SUCCESS"
        m_dismiss.assert_called_once()

    # Scenario 2: All fallbacks fail -> Escalates to KDE Connect and returns MAINTENANCE
    mock_page2 = MagicMock()
    mock_page2.wait_for_selector = AsyncMock(side_effect=Exception("Selector not found"))
    mock_page2.wait_for_timeout = AsyncMock()
    mock_page2.screenshot = AsyncMock()
    mock_page2.is_closed = False

    with patch("app.services.workflow_engine.get_broker_driver") as m_bd2, \
         patch("app.browser.popup_manager.popup_manager.dismiss_popups", new_callable=AsyncMock), \
         patch("app.services.kdeconnect_service.KdeConnectService.notify_admin_screen_help", new_callable=AsyncMock) as m_kde:

        m_bd2.return_value = MagicMock(page=mock_page2)
        res2 = await engine.execute_workflow(wf_name)

        assert res2["success"] is False
        assert res2["status"] == MCPToolStatus.NEEDS_ADMIN_ATTENTION.value
        assert "ระบบกำลังปรับปรุง" in res2["message"]
        assert res2["escalated_to_admin"] is True
        m_kde.assert_called_once()
        assert "ติดขัด" in m_kde.call_args[1]["reason"]


@pytest.mark.asyncio
async def test_portfolio_holdings_maintenance_on_exception():
    """Verifies that an exception in portfolio_holdings returns a maintenance response instead of mock empty array."""
    with patch("app.browser.click2win_driver.click2win_driver.scrape_portfolio", side_effect=RuntimeError("Browser DOM detached")), \
         patch("app.services.kdeconnect_service.KdeConnectService.notify_admin_screen_help", new_callable=AsyncMock) as m_kde:

        res = await portfolio_holdings(platform="CLICK2WIN")
        assert res["success"] is False
        assert res["status"] == MCPToolStatus.UNDER_MAINTENANCE.value
        assert "ระบบกำลังปรับปรุง" in res["message"]
        assert res["maintenance_mode"] is True
        assert res["escalated_to_admin"] is True
        assert "Browser DOM detached" in res["error"]
        m_kde.assert_called_once()
