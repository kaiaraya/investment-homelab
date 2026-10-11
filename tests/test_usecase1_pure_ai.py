import os
import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock

from app.schemas.order import OrderSide
from app.schemas.intelligence import (
    ExtractedOrder,
    ExtractedWatchlistTrigger,
    ExtractedHoldPosition,
    SignalParseResult
)
from app.services.parser import signal_parser
from app.services.line_service import line_service
from app.db.models import Position, SBLBorrowLot, WatchlistTrigger, Order
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


USECASE1_PATH = "ตัวอย่างคำสั่ง/usecase1.md"


# ==============================================================================
# 3. TEST CAROUSEL CARD WITH PORTFOLIO OVERVIEW BUBBLE
# ==============================================================================
def test_build_carousel_with_portfolio_overview_bubble():
    """
    Verifies that build_order_carousel_card renders:
    1. Action bubble for AOT
    2. Portfolio Overview Bubble for hold positions
    3. Summary bubble
    """
    immediate_orders = [
        ExtractedOrder(
            symbol="AOT",
            side=OrderSide.SELL,
            volume=600,
            price=62.25,
            reason="Stop Loss 2.0%"
        )
    ]
    hold_positions = [
        ExtractedHoldPosition(symbol="FORTH", volume=2500, position_type="LONG", days_held=5, group_type="ACTIVE_SWING"),
        ExtractedHoldPosition(symbol="BCH", volume=4500, position_type="SHORT", days_held=2, group_type="ACTIVE_SWING"),
        ExtractedHoldPosition(symbol="CPALL", volume=800, position_type="LONG", days_held=9, group_type="WEED_OUT", warning_note="Time-Exit วันที่ 9/10"),
        ExtractedHoldPosition(symbol="PR9", volume=2700, position_type="SHORT", days_held=1, group_type="WEED_OUT", warning_note="ปริ่ม Stop 2.0% | SBL 2,700 หุ้น")
    ]
    watchlist_triggers = [
        ExtractedWatchlistTrigger(symbol="JMT", action="SELL", volume=3500, condition="PRICE_BELOW", trigger_price=10.40, notes="Trailing Stop Breakeven"),
        ExtractedWatchlistTrigger(symbol="JMT", action="SELL", volume=3500, condition="PRICE_ABOVE", trigger_price=10.90, notes="Dynamic TP Target +5%")
    ]

    card = line_service.build_order_carousel_card(
        orders=immediate_orders,
        batch_id="B-USECASE-1",
        mode_badge="🧪 [MODE: TEST]",
        strategy_summary="Model V3S-MD-TP Conservative Regime",
        hold_positions=hold_positions,
        watchlist_triggers=watchlist_triggers
    )

    assert card["type"] == "flex"
    assert card["contents"]["type"] == "carousel"
    bubbles = card["contents"]["contents"]

    # Must contain 3 bubbles: AOT action card + Portfolio Overview + Batch summary
    assert len(bubbles) == 3

    # Bubble 1: AOT Order
    aot_bubble_str = str(bubbles[0])
    assert "SELL AOT" in aot_bubble_str
    assert "600 หุ้น" in aot_bubble_str

    # Bubble 2: Portfolio Overview
    portfolio_bubble_str = str(bubbles[1])
    assert "สรุปสถานะพอร์ตคงค้าง" in portfolio_bubble_str
    assert "Active Swings" in portfolio_bubble_str
    assert "Weed-Out" in portfolio_bubble_str
    assert "CPALL" in portfolio_bubble_str
    assert "Time-Exit วันที่ 9/10" in portfolio_bubble_str
    assert "PR9" in portfolio_bubble_str

    # Bubble 3: Batch Summary
    summary_bubble_str = str(bubbles[2])
    assert "สรุปคำสั่งชุด BATCH" in summary_bubble_str


# ==============================================================================
# 4. TEST SBL LINKAGE AND POSITION TP/SL DATABASE UPDATE
# ==============================================================================
@pytest.mark.asyncio
async def test_line_service_sbl_and_position_update(db_session: AsyncSession):
    """
    Tests end-to-end webhook text handling:
    1. Pre-seeds JMT position without TP/SL.
    2. Pre-seeds active SBLBorrowLot for PR9.
    3. Simulates sending strategy text.
    4. Confirms JMT position in DB receives TP/SL.
    5. Confirms PR9 hold position receives SBL borrow fee metadata.
    """
    # 1. Seed JMT position in DB
    jmt_pos = Position(
        symbol="JMT",
        position_type="LONG",
        volume=3500,
        avg_cost=10.40,
        current_price=10.70
    )
    db_session.add(jmt_pos)

    # 2. Seed active SBL lot for PR9
    pr9_sbl = SBLBorrowLot(
        lot_id="SBL-PR9-001",
        broker_tx_id="TX-PR9",
        symbol="PR9",
        borrow_qty=2700,
        remaining_qty=2700,
        borrow_price=19.20,
        borrow_fee_rate=3.50,
        borrow_date=date(2026, 9, 1),
        status="ACTIVE"
    )
    db_session.add(pr9_sbl)
    await db_session.commit()

    # 3. Simulate parsing result from AI
    mock_ai_res = SignalParseResult(
        total_parsed=5,
        immediate_orders=[
            ExtractedOrder(symbol="AOT", side=OrderSide.SELL, volume=600, price=62.25, reason="Stop Loss 2%")
        ],
        watchlist_triggers=[
            ExtractedWatchlistTrigger(symbol="JMT", action="SELL", volume=3500, condition="PRICE_BELOW", trigger_price=10.40, notes="Trailing Stop"),
            ExtractedWatchlistTrigger(symbol="JMT", action="SELL", volume=3500, condition="PRICE_ABOVE", trigger_price=10.90, notes="Dynamic TP")
        ],
        hold_positions=[
            ExtractedHoldPosition(symbol="PR9", volume=2700, position_type="SHORT", days_held=1, group_type="WEED_OUT", warning_note="ปริ่ม Stop 2.0%")
        ],
        source_method="gemini_3.6_flash"
    )

    with patch.object(signal_parser, "parse_strategy_with_ai", return_value=mock_ai_res):
        with patch.object(line_service, "_send_reply", return_value=None):
            event = {
                "replyToken": "mock_token",
                "message": {"type": "text", "text": "Model V3S-MD-TP Action Recommendations 5.1 Hard Exit AOT"}
            }
            res = await line_service._handle_text_message(db_session, event["message"]["text"], event)

    assert res["status"] == "DAILY_ORDER_BATCH_PREPARED"

    # Verify JMT Position has TP and SL updated in database
    stmt_jmt = select(Position).where(Position.symbol == "JMT")
    pos_res = await db_session.execute(stmt_jmt)
    updated_jmt = pos_res.scalar_one()
    assert updated_jmt.stop_loss_price == 10.40
    assert updated_jmt.take_profit_price == 10.90

    # Verify PR9 has SBL tag appended
    pr9_hold = mock_ai_res.hold_positions[0]
    assert "SBL 2,700 หุ้น" in pr9_hold.warning_note
    assert "ดอกเบี้ยสะสม" in pr9_hold.warning_note
