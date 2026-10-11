import pytest
from app.ai.orchestrator import MasterOrchestrator
from app.services.kill_switch_service import kill_switch_service
from app.db.init_db import init_db


@pytest.mark.asyncio
async def test_master_orchestrator_pt_mro_cycle():
    """Verify MasterOrchestrator completes full PT-MRO cycle and logs to memory."""
    await init_db()
    await kill_switch_service.reset(authorized_by="TEST_SETUP")

    orchestrator = MasterOrchestrator()

    # 1. Execute Pre-Market Regime Cycle
    res_pre = await orchestrator.execute_pt_mro_cycle(regime="PRE_MARKET", trigger_source="UNIT_TEST")
    assert res_pre["regime"] == "PRE_MARKET"
    assert res_pre["trigger_source"] == "UNIT_TEST"
    assert "tasks_executed" in res_pre
    assert res_pre["tasks_executed"] >= 1

    # 2. Execute Auto-Trading Regime Cycle
    res_auto = await orchestrator.execute_pt_mro_cycle(regime="AUTO_TRADING", trigger_source="UNIT_TEST")
    assert res_auto["regime"] == "AUTO_TRADING"
    assert len(res_auto["results"]) >= 1

    # 3. Test Kill Switch Abort Behavior
    await kill_switch_service.activate(reason="Abort Cycle Test", triggered_by="UNIT_TEST")
    res_aborted = await orchestrator.execute_pt_mro_cycle(regime="AUTO_TRADING", trigger_source="UNIT_TEST")
    assert res_aborted["status"] == "ABORTED"
    assert res_aborted["reason"] == "KILL_SWITCH_ACTIVE"

    # Reset
    await kill_switch_service.reset(authorized_by="TEST_TEARDOWN")
