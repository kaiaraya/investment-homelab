"""
Unit & Integration Test Suite for DailyScenarioRunner (10:00 - 19:30 Time-Warp Engine).
Verifies:
1. Loading freeform markdown strategy and database seeding.
2. Step-by-step execution across all 8 time windows.
3. 10:00 Morning TP (Model Target + Special Profit Escape).
4. 10:30 Hard Cut Loss (SL), Weed-out, and Opening Probabilistic Positions (BDMS, AP).
5. 12:00 Price Negotiation on Unmatched Orders (TRUE).
6. 16:30 SBL Return for Covered Lots (PR9).
7. 19:00 Deep EOD Performance Report.
8. Full Day simulation run.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from app.core.virtual_clock import virtual_clock
from app.db.models import Position, Order, SBLBorrowLot
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.schemas.order import OrderSide
from app.schemas.intelligence import (
    SignalParseResult,
    ExtractedOrder,
    ExtractedWatchlistTrigger,
    ExtractedHoldPosition
)
from app.services.parser import signal_parser
from app.services.daily_scenario_runner import daily_scenario_runner


SAMPLE_MARKDOWN = """
# กลยุทธ์การเทรดประจำวัน (Daily Action Plan)
## 5.1 Hard Exit & Cut Loss Triggers
TIDLOR: SELL 2,000 หุ้น Cut Loss -4.2% ตามวินัยจำกัดความเสี่ยง 2.0%

## 5.2 Dynamic TP & Strong Runners
CKP: SELL 8,000 หุ้น ที่เป้าหมาย Dynamic TP +5% (฿2.48)
SINGER: SELL 3,700 หุ้น ล็อกกำไรหนีเมื่อมีกำไร (+1.94%)

## 5.3 Weed-out Watchlist
CPALL: SELL 800 หุ้น เคลียร์ทิ้งคืนกระสุน (ถือ 9 วัน)
PR9: COVER 2,700 หุ้น ปิด Short คืน SBL

## ไม้เปิดใหม่ตามความน่าจะเป็น
BDMS: BUY 1,500 หุ้น @ 28.00 (Ranking #1 ไม่ติดกับดักรายใหญ่)
AP: SHORT 5,000 หุ้น @ 8.10 (ยืม SBL)
"""

MOCK_PARSE_RESULT = SignalParseResult(
    source_method="gemini_3.6_flash",
    total_parsed=6,
    immediate_orders=[
        ExtractedOrder(symbol="TIDLOR", side=OrderSide.SELL, volume=2000, price=18.20, reason="Cut loss -4.2%"),
        ExtractedOrder(symbol="CKP", side=OrderSide.SELL, volume=8000, price=2.48, reason="Dynamic TP +5%"),
        ExtractedOrder(symbol="SINGER", side=OrderSide.SELL, volume=3700, price=10.50, reason="Special Profit Escape")
    ],
    watchlist_triggers=[
        ExtractedWatchlistTrigger(symbol="CKP", action="SELL", volume=8000, condition="PRICE_ABOVE", trigger_price=2.48, notes="Dynamic TP")
    ],
    hold_positions=[
        ExtractedHoldPosition(symbol="CPALL", volume=800, position_type="LONG", group_type="WEED_OUT", days_held=9, warning_note="Time-exit 9/10"),
        ExtractedHoldPosition(symbol="PR9", volume=2700, position_type="SHORT", group_type="WEED_OUT", days_held=2, warning_note="Weed-out Short")
    ],
    strategy_summary="สรุปกลยุทธ์ประจำวัน: ปิด TP CKP/SINGER, SL TIDLOR, Weed-out CPALL/PR9"
)


@pytest.fixture(autouse=True)
async def setup_test_env():
    await init_db()
    virtual_clock.set_real_time_mode()
    daily_scenario_runner.toggle_live_line(False)  # Ensure Live LINE is OFF during tests

    with patch.object(signal_parser, "parse_strategy_with_ai", new=AsyncMock(return_value=MOCK_PARSE_RESULT)):
        yield

    virtual_clock.set_real_time_mode()


@pytest.mark.asyncio
async def test_load_markdown_strategy():
    # Load strategy
    res = await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    assert res is not None
    assert res["total_parsed"] >= 5

    async with AsyncSessionLocal() as db:
        # Check that positions are properly seeded
        positions = (await db.execute(select(Position))).scalars().all()
        symbols = {p.symbol for p in positions}
        assert "CKP" in symbols
        assert "SINGER" in symbols
        assert "TIDLOR" in symbols
        assert "CPALL" in symbols
        assert "PR9" in symbols

        # Check SBL lot seeded
        sbl_pr9 = (await db.execute(select(SBLBorrowLot).where(SBLBorrowLot.symbol == "PR9"))).scalars().first()
        assert sbl_pr9 is not None
        assert sbl_pr9.borrow_qty == 2700

        # Check unmatched order for negotiation seeded
        ord_true = (await db.execute(select(Order).where(Order.symbol == "TRUE"))).scalars().first()
        assert ord_true is not None
        assert ord_true.status == "OPEN"


@pytest.mark.asyncio
async def test_slot_1000_morning_tp():
    await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    res = await daily_scenario_runner.run_step("slot_1000")

    assert res["slot_id"] == "slot_1000"
    assert res["status"] == "SUCCESS"
    assert len(res["active_actions"]) >= 2  # CKP TP and SINGER Special Escape
    assert any("CKP" in act for act in res["active_actions"])
    assert any("SINGER" in act for act in res["active_actions"])
    assert len(res["passive_actions"]) >= 1  # SET Monitor snapshot

    async with AsyncSessionLocal() as db:
        pos_singer = await db.get(Position, "SINGER")
        assert pos_singer.volume == 0  # Fully closed


@pytest.mark.asyncio
async def test_slot_1030_auto_trading_window():
    await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    # Run slot 10:00 first to advance
    await daily_scenario_runner.run_step("slot_1000")
    # Run slot 10:30
    res = await daily_scenario_runner.run_step("slot_1030")

    assert res["slot_id"] == "slot_1030"
    assert res["status"] == "SUCCESS"

    # Verify SL on TIDLOR
    assert any("TIDLOR" in act and "SL" in act for act in res["active_actions"])
    # Verify Weed-out on CPALL and PR9
    assert any("CPALL" in act and "Weed-out" in act for act in res["active_actions"])
    assert any("PR9" in act and "Cover" in act for act in res["active_actions"])
    # Verify New entries for BDMS and AP
    assert any("BDMS" in act and "BUY" in act for act in res["active_actions"])
    assert any("AP" in act and "SHORT" in act for act in res["active_actions"])

    async with AsyncSessionLocal() as db:
        pos_tidlor = await db.get(Position, "TIDLOR")
        assert pos_tidlor.volume == 0  # Cut loss executed

        pos_bdms = await db.get(Position, "BDMS")
        assert pos_bdms is not None
        assert pos_bdms.volume == 1500

        pos_ap = await db.get(Position, "AP")
        assert pos_ap is not None
        assert pos_ap.position_type == "SHORT"
        assert pos_ap.volume == 5000


@pytest.mark.asyncio
async def test_slot_1200_price_negotiation():
    await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    res = await daily_scenario_runner.run_step("slot_1200")

    assert res["slot_id"] == "slot_1200"
    assert any("TRUE" in act and "12.60" in act for act in res["active_actions"])

    async with AsyncSessionLocal() as db:
        ord_true = await db.get(Order, "ORD-NEGO-TRUE-01")
        assert ord_true.status == "MATCHED"
        assert ord_true.price == 12.60


@pytest.mark.asyncio
async def test_slot_1630_sbl_return():
    await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    await daily_scenario_runner.run_step("slot_1030")  # Covers PR9
    res = await daily_scenario_runner.run_step("slot_1630")

    assert res["slot_id"] == "slot_1630"
    assert any("PR9" in act and "คืนหุ้น" in act for act in res["active_actions"])

    async with AsyncSessionLocal() as db:
        sbl_pr9 = (await db.execute(select(SBLBorrowLot).where(SBLBorrowLot.symbol == "PR9"))).scalars().first()
        assert sbl_pr9.status == "RETURNED"


@pytest.mark.asyncio
async def test_slot_1900_eod_summary():
    await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    res = await daily_scenario_runner.run_step("slot_1900")

    assert res["slot_id"] == "slot_1900"
    assert len(res["passive_actions"]) >= 1
    assert "Realized PnL" in res["passive_actions"][0]


@pytest.mark.asyncio
async def test_run_full_day_simulation():
    await daily_scenario_runner.load_markdown_strategy(SAMPLE_MARKDOWN)
    res = await daily_scenario_runner.run_full_day()

    assert res["status"] == "COMPLETED"
    assert res["total_slots"] == 8
    assert len(res["timeline"]) == 8

    # Verify runner status
    status = daily_scenario_runner.get_status()
    assert status["logs_count"] >= 8
