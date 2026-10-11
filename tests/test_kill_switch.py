import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.kill_switch_service import kill_switch_service
from app.ai.agents.order_agent import OrderExecutionAgent
from app.db.init_db import init_db


@pytest.mark.asyncio
async def test_kill_switch_service_lifecycle():
    """Verify activate, status check, and reset lifecycle of KillSwitchService."""
    await init_db()

    # Reset initially
    await kill_switch_service.reset(authorized_by="TEST_SETUP")
    assert not kill_switch_service.is_active()

    # Activate
    act_res = await kill_switch_service.activate(reason="Unit Test Panic", triggered_by="TEST_RUNNER")
    assert kill_switch_service.is_active()
    assert act_res["status"] == "KILL_SWITCH_ACTIVE"
    assert act_res["reason"] == "Unit Test Panic"

    # Status check
    status = kill_switch_service.get_status()
    assert status["is_active"] is True
    assert status["triggered_by"] == "TEST_RUNNER"

    # Verify OrderExecutionAgent blocks orders
    order_agent = OrderExecutionAgent()
    order_res = await order_agent.execute_order(
        symbol="BDMS",
        side="BUY",
        volume=100,
        price=19.90,
    )
    assert order_res["status"] == "BLOCKED"
    assert "Emergency Kill Switch is ACTIVE" in order_res["error"]

    # Reset
    reset_res = await kill_switch_service.reset(authorized_by="TEST_RUNNER")
    assert not kill_switch_service.is_active()
    assert reset_res["status"] == "KILL_SWITCH_RESET"


@pytest.mark.asyncio
async def test_kill_switch_api_endpoints():
    """Verify HTTP API endpoints for kill switch control."""
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Activate
        res = await client.post("/api/v1/agentic/kill-switch/activate", json={
            "reason": "API Unit Test Panic",
            "triggered_by": "PYTEST"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "KILL_SWITCH_ACTIVE"

        # 2. Status
        res_status = await client.get("/api/v1/agentic/kill-switch/status")
        assert res_status.status_code == 200
        assert res_status.json()["is_active"] is True

        # 3. Reset
        res_reset = await client.post("/api/v1/agentic/kill-switch/reset", json={
            "authorized_by": "PYTEST"
        })
        assert res_reset.status_code == 200
        assert res_reset.json()["status"] == "KILL_SWITCH_RESET"

        # 4. Final Status
        res_final = await client.get("/api/v1/agentic/kill-switch/status")
        assert res_final.json()["is_active"] is False
