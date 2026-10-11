"""
Test Suite for Time Warp Engine & 5 Comprehensive Simulation Scenarios.
Verifies:
1. VirtualClock time acceleration, fast-forwarding, pause, and resume
2. Scenario 1: Normal Execution & Matched
3. Scenario 2: Take Profit & Stop Loss Dual Triggers
4. Scenario 3: Abnormal Volatility & Price Rebound (+/-3%) — alert detection REMOVED 2026-10-06 (Pillar 2 refactor)
5. Scenario 4: Unmatched Order & Negotiation Expiry over EOD
6. Scenario 5: SBL Borrowed & Held Over EOD with Daily Fee Accrual
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta

from app.core.virtual_clock import virtual_clock
from app.services.scenario_matrix import scenario_matrix
from app.db.init_db import init_db


@pytest.fixture(autouse=True)
async def setup_clock_and_db():
    await init_db()
    virtual_clock.set_real_time_mode()
    yield
    virtual_clock.set_real_time_mode()


@pytest.mark.asyncio
async def test_virtual_clock_controls():
    # 1. Fast-forward to 10:15
    dt = virtual_clock.advance_to("10:15")
    assert dt.strftime("%H:%M") == "10:15"
    assert virtual_clock.mode == "FAST_FORWARD"

    # 2. Advance by 45 minutes -> 11:00
    dt2 = virtual_clock.advance_minutes(45)
    assert dt2.strftime("%H:%M") == "11:00"

    # 3. Pause & Resume
    virtual_clock.pause()
    assert virtual_clock.mode == "PAUSED"
    virtual_clock.resume()
    assert virtual_clock.mode in ["FAST_FORWARD", "ACCELERATED"]

    # 4. Reset to real time
    virtual_clock.set_real_time_mode()
    assert virtual_clock.mode == "REAL_TIME"


@pytest.mark.asyncio
async def test_scenario_1_normal():
    res = await scenario_matrix.run_scenario_1_normal(hitl_mode="auto")
    assert res["status"] == "SUCCESS"
    assert res["symbol"] == "CPALL"
    assert res["final_price"] == 66.50
    assert res["unrealized_pnl"] == 1500.0


@pytest.mark.asyncio
async def test_scenario_2_tpsl_triggers():
    res = await scenario_matrix.run_scenario_2_tpsl_triggers(hitl_mode="auto")
    assert res["status"] == "SUCCESS"
    # Alert Center (Phase 3.2) removed 2026-10-06 (Pillar 2 refactor) — no alert engine,
    # so no alert events are produced; TP/SL closure is driven by strategy rules instead.
    assert res["alerts_triggered"] == 0
    assert res["realized_pnl_total"] == 3000.0
    assert len(res["closed_positions"]) == 2


@pytest.mark.asyncio
async def test_scenario_3_volatility_rebound():
    res = await scenario_matrix.run_scenario_3_volatility_rebound(hitl_mode="auto")
    assert res["status"] == "SUCCESS"
    # Alert Center (Phase 3.2) removed 2026-10-06 — abnormal-move alerts no longer detected;
    # the position is simply held through the rebound to EOD.
    assert res["abnormal_alert_detected"] is False
    assert res["rebound_price"] == 98.50
    assert res["held_to_eod"] is True


@pytest.mark.asyncio
async def test_scenario_4_unmatched_negotiation():
    res = await scenario_matrix.run_scenario_4_unmatched_negotiation_failed(hitl_mode="auto")
    assert res["status"] == "SUCCESS"
    assert res["order_id"] == "ORD-SC4-TRUE"
    assert "OPEN" in res["final_order_status"]
    assert res["negotiation_rounds_executed"] == 2


@pytest.mark.asyncio
async def test_scenario_5_sbl_held_fee():
    res = await scenario_matrix.run_scenario_5_sbl_held_carrying_fee(hitl_mode="auto")
    assert res["status"] == "SUCCESS"
    assert res["borrow_lot_id"] == "LOT-SC5-HMPRO-01"
    assert res["held_volume"] == 2000
    assert "ACTIVE" in res["borrow_status"]
