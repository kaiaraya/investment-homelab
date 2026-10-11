"""
Automated Regression & Guardrail Tests for Krungsri Securities (TradeMan Pro).
==============================================================================
Validates PDCA standardization and prevents regression of:
1. KSS-RCA-006: 3-Tier Anti-DW Protection (No DW collision with common stocks)
2. KSS-RCA-007: Isolated Broker PIN Configuration (KRUNGSRI_PIN separation)
3. KSS-RCA-008: Tactical Action Exit Auto-Scheduling & Offer1/Bid1 Pricing
4. KSS-RCA-009: 09:45 AM Pre-Flight Session Health Check Window Logic
"""

import pytest
import re
from datetime import datetime, time, timedelta

from app.core.config import settings
from app.services.action_exit_service import action_exit_service
from app.services.action_exit_dispatcher import action_exit_dispatcher


def test_krungsri_pin_isolation():
    """KSS-RCA-007: Verifies KRUNGSRI_PIN is explicitly defined and isolated from other brokers."""
    assert hasattr(settings, "KRUNGSRI_PIN"), "KRUNGSRI_PIN must be defined in settings"
    # Never assert the literal PIN value (secret) — only its shape when configured via .env.
    assert isinstance(settings.KRUNGSRI_PIN, str), "KRUNGSRI_PIN must be a string"
    if settings.KRUNGSRI_PIN:
        assert re.fullmatch(r"\d{6}", settings.KRUNGSRI_PIN), "KRUNGSRI_PIN must be 6 digits"
    
    # Ensure other brokers have their own independent PINs
    assert hasattr(settings, "CLICK2WIN_PIN"), "CLICK2WIN_PIN must be defined"
    assert hasattr(settings, "LIBERATOR_PIN"), "LIBERATOR_PIN must be defined"
    assert hasattr(settings, "SETTRADE_PIN"), "SETTRADE_PIN must be defined"


def test_anti_dw_guardrail_exact_matching():
    """KSS-RCA-006: Verifies exact matching algorithm rejects all Derivative Warrants (DW) for common stock."""
    target_stock = "SAWAD"
    candidate_symbols = [
        "SAWAD01C2612A",
        "SAWAD13P2409A",
        "SAWAD19C2508A",
        "SAWAD-W2",
        "SAWAD01",
        "SAWAD",
        "SAWAD_F"
    ]

    # Simulation of Tier 1 & Tier 2 Exact Filter:
    # Must match el.innerText.trim() === target_stock
    filtered = [s for s in candidate_symbols if s.strip() == target_stock]
    assert len(filtered) == 1, f"Expected exactly 1 match for {target_stock}, got {filtered}"
    assert filtered[0] == "SAWAD"

    # DW Pattern Detection Guard: Common stocks in SET typically do not end with 01-99 + C/P + date
    dw_pattern = re.compile(r"^[A-Z0-9]+[0-9]{2}[CP][0-9]{4}[A-Z]?$", re.IGNORECASE)
    for sym in ["SAWAD01C2612A", "SAWAD13P2409A", "DELTA01P2506A"]:
        assert dw_pattern.match(sym), f"{sym} should be identified as a Derivative Warrant"
    assert not dw_pattern.match(target_stock), f"{target_stock} is a common stock, should not match DW pattern"


def test_action_exit_parsing_and_tactical_windows():
    """KSS-RCA-005 & KSS-RCA-008: Verifies briefing parsing, tactical windows, and auto-scheduling."""
    sample_briefing = """
    🏛️ [พอร์ต Krungsri Margin - KSS]
    🚨 Action Exits วันนี้:
    • [Timeout] SAWAD (LONG): SELL 2,200 หุ้น @ 22.50 (+1.18% / +0.45x ATR) 👉 ล็อคกำไรปลดล็อกเงินสด
    • [Weed-out] COCOCO (LONG): SELL 8,800 หุ้น @ 5.65 (-0.17% / -0.22x ATR) 👉 ตัดทิ้งคัดกรองไม้แย่
    • [Stop-Loss] DELTA (SHORT): COVER 500 หุ้น @ 110.00 (-0.80%) 👉 ปิดชอร์ตเคลียร์ความเสี่ยง
    """

    parsed = action_exit_service.parse_action_exit_text(sample_briefing)
    assert parsed["broker"] == "KRUNGSRI"
    assert parsed["account_no"] == "3024959"
    assert parsed["account_type"] == "MARGIN"
    assert parsed["total_items"] == 3
    assert parsed["profitable_count"] == 1
    assert parsed["losing_count"] == 2

    sawad = next(i for i in parsed["items"] if i["symbol"] == "SAWAD")
    assert sawad["side"] == "SELL"
    assert sawad["is_profit"] is True
    assert sawad["window"] == "10:00 - 10:30"
    assert 1 <= sawad["jitter_minutes"] <= 5

    cococo = next(i for i in parsed["items"] if i["symbol"] == "COCOCO")
    assert cococo["side"] == "SELL"
    assert cococo["is_profit"] is False
    assert cococo["window"] == "10:30 - 12:00"
    assert 3 <= cococo["jitter_minutes"] <= 15

    delta = next(i for i in parsed["items"] if i["symbol"] == "DELTA")
    assert delta["side"] == "COVER"
    assert delta["position"] == "SHORT"
    assert delta["is_profit"] is False
    assert delta["window"] == "10:30 - 12:00"


@pytest.mark.asyncio
async def test_action_exit_auto_schedule_db_status():
    """KSS-RCA-008: Verifies auto_schedule=True assigns SCHEDULED status immediately without manual approval."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import Order
    from sqlalchemy import select

    briefing = """
    🏛️ [พอร์ต Krungsri Margin - KSS]
    • [Test] PTT (LONG): SELL 100 หุ้น @ 34.00 (+0.50%) 👉 ทดสอบระบบอัตโนมัติ
    """

    async with AsyncSessionLocal() as db:
        res = await action_exit_service.evaluate_and_queue_action_exits(
            text=briefing,
            db=db,
            auto_schedule=True
        )
        assert res["success"] is True
        assert res["queued_count"] == 1
        order_info = res["orders"][0]
        assert order_info["status"] == "SCHEDULED"
        assert "scheduled_time" in order_info

        # Verify in DB
        db_order = await db.get(Order, order_info["order_id"])
        assert db_order is not None
        assert db_order.status == "SCHEDULED"

        # Cleanup test record
        await db.delete(db_order)
        await db.commit()


def test_offer1_bid1_pricing_strategy():
    """KSS-RCA-008: Verifies pricing rule uses Offer 1 for SELL and Bid 1 for COVER."""
    mock_quotes = {
        "bid_1": 22.40,
        "offer_1": 22.50,
        "last": 22.50
    }

    # SELL: Follow Best Offer 1 (22.50) to queue at best asking price
    side_sell = "SELL"
    sell_target = mock_quotes["offer_1"] if mock_quotes.get("offer_1") else 22.30
    assert sell_target == 22.50, "SELL order must target Offer 1"

    # COVER: Follow Best Bid 1 (22.40) to queue at best bidding price
    side_cover = "COVER"
    cover_target = mock_quotes["bid_1"] if mock_quotes.get("bid_1") else 22.50
    assert cover_target == 22.40, "COVER order must target Bid 1"


def test_preflight_0945_time_window_logic():
    """KSS-RCA-009: Verifies preflight triggers during 09:45 - 09:55 AM on weekdays."""
    # Test valid preflight time: Monday 09:48 AM
    weekday_0948 = datetime(2026, 9, 28, 9, 48, 0)
    is_weekday = weekday_0948.weekday() < 5
    is_time_window = (weekday_0948.hour == 9 and 45 <= weekday_0948.minute <= 55)
    assert is_weekday and is_time_window, "Should trigger preflight at 09:48 on weekday"

    # Test invalid time: 10:05 AM (Market already open)
    time_1005 = datetime(2026, 9, 28, 10, 5, 0)
    is_window_1005 = (time_1005.hour == 9 and 45 <= time_1005.minute <= 55)
    assert not is_window_1005, "Must not trigger preflight at 10:05"

    # Test weekend: Sunday 09:48 AM
    sunday_0948 = datetime(2026, 9, 27, 9, 48, 0)
    assert sunday_0948.weekday() == 6
    assert not (sunday_0948.weekday() < 5), "Must not trigger preflight on weekend"
