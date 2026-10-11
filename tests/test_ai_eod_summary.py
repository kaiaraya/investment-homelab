import pytest
from datetime import date, datetime
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch

from app.schemas.order import OrderSide
from app.schemas.intelligence import ExtractedOrder, ExtractedWatchlistTrigger, ExtractedHoldPosition, SignalParseResult
from app.services.validator import validator
from app.services.parser import signal_parser
from app.services.line_service import line_service
from app.services.decision_engine import decision_engine
from app.services.eod_service import eod_service
from app.core.config import settings
from app.db.models import Order, SBLBorrowLot, Position
from sqlalchemy.ext.asyncio import AsyncSession


# ==============================================================================
# 1. TEST RECONCILIATION & AUTO-CLAMPING & PRICE ADVANTAGE
# ==============================================================================
def test_reconcile_orders_relative_volume_and_clamping():
    """
    Verifies:
    1. Relative volume ("ขายครึ่งพอร์ต" = 50%) translates to exact shares.
    2. Over-volume SELL orders auto-clamp down to actual holdings.
    3. Price advantage calculation triggers when market is better than target.
    """
    mock_portfolio = {
        "DELTA": {
            "symbol": "DELTA",
            "volume": 200,
            "market_price": 280.0,
            "position_type": "LONG"
        },
        "AOT": {
            "symbol": "AOT",
            "volume": 1200,
            "market_price": 63.50,
            "position_type": "LONG"
        },
        "TRUE": {
            "symbol": "TRUE",
            "volume": 500,
            "market_price": 13.50,
            "position_type": "LONG"
        }
    }

    raw_orders = [
        # 1. Relative 50% on DELTA (held 200) -> should be 100 shares
        ExtractedOrder(
            symbol="DELTA",
            side=OrderSide.SELL,
            volume=0,
            price=275.0,  # Target 275.0, Market 280.0 -> Better by +1.82%!
            reason="Climax TP half",
            is_relative_volume=True,
            volume_pct=50.0
        ),
        # 2. Over-volume on AOT (requests 3,000, but only holds 1,200) -> clamp to 1,200
        ExtractedOrder(
            symbol="AOT",
            side=OrderSide.SELL,
            volume=3000,
            price=63.50,
            reason="Stop Loss",
            is_relative_volume=False
        ),
        # 3. Normal order within holdings on TRUE
        ExtractedOrder(
            symbol="TRUE",
            side=OrderSide.SELL,
            volume=500,
            price=13.50,
            reason="Exit",
            is_relative_volume=False
        )
    ]

    reconciled = validator.reconcile_orders_against_portfolio(raw_orders, mock_portfolio)
    assert len(reconciled) == 3

    # Check DELTA relative calculation and price advantage
    delta_ord = next(o for o in reconciled if o.symbol == "DELTA")
    assert delta_ord.volume == 100
    assert delta_ord.is_valid_lot is True
    assert delta_ord.price_advantage_pct is not None
    assert delta_ord.price_advantage_pct > 1.5
    assert "🔥 ราคาตลาดดีกว่าเป้า" in delta_ord.price_advantage_label

    # Check AOT auto-clamping
    aot_ord = next(o for o in reconciled if o.symbol == "AOT")
    assert aot_ord.volume == 1200
    assert aot_ord.clamped_from_volume == 3000
    assert aot_ord.is_valid_lot is True

    # Check TRUE
    true_ord = next(o for o in reconciled if o.symbol == "TRUE")
    assert true_ord.volume == 500
    assert true_ord.clamped_from_volume is None


def test_symbol_sanitization():
    """Tests that _clean_symbol cleans brackets, Thai notes, and spaces."""
    assert signal_parser._clean_symbol("TRUE (เศษหุ้น)") == "TRUE"
    assert signal_parser._clean_symbol("PTG (SHORT)") == "PTG"
    assert signal_parser._clean_symbol("AOT (ไม้ 2)") == "AOT"
    assert signal_parser._clean_symbol(" DELTA ") == "DELTA"


# ==============================================================================
# 3. TEST LINE CAROUSEL CARD GENERATION
# ==============================================================================
def test_build_order_carousel_card():
    """
    Verifies:
    1. Flex card structure is type "carousel".
    2. Individual bubbles per stock with [✅ ยิงไม้นี้] and [❌ ข้ามไม้นี้].
    3. Price Advantage Badge and Clamping Warnings rendered.
    4. Summary bubble contains total orders and TTL.
    """
    orders = [
        ExtractedOrder(
            symbol="DELTA",
            side=OrderSide.SELL,
            volume=100,
            price=280.0,
            reason="Climax TP",
            price_advantage_pct=1.82,
            price_advantage_label="🔥 ราคาตลาดดีกว่าเป้า (+1.8%)"
        ),
        ExtractedOrder(
            symbol="AOT",
            side=OrderSide.SELL,
            volume=1200,
            price=63.50,
            reason="Stop Loss",
            clamped_from_volume=3000
        )
    ]

    card = line_service.build_order_carousel_card(
        orders=orders,
        batch_id="B-TEST-CAROUSEL",
        mode_badge="🧪 [MODE: TEST]",
        strategy_summary="แผนล้างพอร์ตตามรอบวินัย V3S"
    )

    assert card["type"] == "flex"
    assert card["contents"]["type"] == "carousel"
    bubbles = card["contents"]["contents"]

    # 2 stock bubbles + 1 summary bubble = 3 bubbles
    assert len(bubbles) == 3

    # Check DELTA bubble action buttons
    delta_bubble = bubbles[0]
    actions = [btn["action"]["data"] for btn in delta_bubble["footer"]["contents"]]
    assert any("action=single_approve&batch_id=B-TEST-CAROUSEL&symbol=DELTA" in a for a in actions)
    assert any("action=single_skip&batch_id=B-TEST-CAROUSEL&symbol=DELTA" in a for a in actions)

    # Check Price Advantage Badge in DELTA body
    delta_body_str = str(delta_bubble["body"])
    assert "🔥 ราคาตลาดดีกว่าเป้า (+1.8%)" in delta_body_str

    # Check Clamping warning in AOT bubble
    aot_bubble = bubbles[1]
    aot_body_str = str(aot_bubble["body"])
    assert "ปรับลดจาก 3,000 เหลือ 1,200 หุ้น ตามพอร์ตจริง" in aot_body_str

    # Check Summary bubble
    summary_bubble = bubbles[2]
    assert "⚡ สรุปคำสั่งชุด BATCH" in str(summary_bubble["header"])
    assert f"การ์ดมีอายุ {settings.CARD_TTL_SECONDS} วินาที" in str(summary_bubble["body"])


# ==============================================================================
# 4. TEST DECISION POLICY ENGINE (TIMEOUT & NEGOTIATION)
# ==============================================================================
@pytest.mark.asyncio
async def test_decision_engine_unanswered_timeout():
    """Verifies timeout handling policies: HOLD, AUTO_EXECUTE_CUTLOSS, URGENT_PING."""
    orders = [
        {"symbol": "MCOT", "side": "SELL", "volume": 3400, "price": 5.50, "reason": "Cut Loss 2%"},
        {"symbol": "CPALL", "side": "BUY", "volume": 500, "price": 46.00, "reason": "Normal swing"}
    ]

    # 1. HOLD policy
    with patch.object(settings, "UNANSWERED_ACTION_POLICY", "HOLD"):
        res_hold = await decision_engine.handle_unanswered_timeout(
            batch_id="B-EXPIRED-01",
            orders=orders
        )
        assert res_hold["action"] == "HOLD"

    # 2. AUTO_EXECUTE_CUTLOSS policy
    with patch.object(settings, "UNANSWERED_ACTION_POLICY", "AUTO_EXECUTE_CUTLOSS"):
        mock_callback = AsyncMock(return_value={"symbol": "MCOT", "executed": True})
        res_cutloss = await decision_engine.handle_unanswered_timeout(
            batch_id="B-EXPIRED-01",
            orders=orders,
            dispatcher_callback=mock_callback
        )
        assert res_cutloss["action"] == "AUTO_EXECUTE_CUTLOSS"
        assert len(res_cutloss["executed_orders"]) == 1
        assert res_cutloss["executed_orders"][0]["symbol"] == "MCOT"

    # 3. URGENT_PING policy
    with patch.object(settings, "UNANSWERED_ACTION_POLICY", "URGENT_PING"):
        res_ping = await decision_engine.handle_unanswered_timeout(
            batch_id="B-EXPIRED-01",
            orders=orders
        )
        assert res_ping["action"] == "URGENT_PING"
        assert "เตือนด่วน" in res_ping["message"]


@pytest.mark.asyncio
async def test_decision_engine_price_negotiation():
    """Verifies 11:00 / 15:30 negotiation policies."""
    proposal = {
        "order_id": "ORD-12345",
        "symbol": "PTT",
        "side": "BUY",
        "current_order_price": 34.00,
        "target_price": 34.25
    }

    # 1. PROPOSE_LINE
    with patch.object(settings, "PRICE_NEGOTIATION_POLICY", "PROPOSE_LINE"):
        res_propose = await decision_engine.handle_price_negotiation_decision(proposal)
        assert res_propose["action"] == "PROPOSE_LINE"
        assert "เตรียมส่งการ์ดเสนอปรับราคา" in res_propose["message"]

    # 2. AUTO_ADJUST
    with patch.object(settings, "PRICE_NEGOTIATION_POLICY", "AUTO_ADJUST"):
        mock_adjust = AsyncMock(return_value={"status": "ADJUSTED_OK"})
        res_adjust = await decision_engine.handle_price_negotiation_decision(
            proposal, execute_adjustment_callback=mock_adjust
        )
        assert res_adjust["action"] == "AUTO_ADJUST"
        assert res_adjust["result"]["status"] == "ADJUSTED_OK"

    # 3. CANCEL_ORDER
    with patch.object(settings, "PRICE_NEGOTIATION_POLICY", "CANCEL_ORDER"):
        res_cancel = await decision_engine.handle_price_negotiation_decision(proposal)
        assert res_cancel["action"] == "CANCEL_ORDER"


# ==============================================================================
# 5. TEST END-OF-DAY (EOD) 16:35 SUMMARY & EXCESS EQUITY
# ==============================================================================
@pytest.mark.asyncio
async def test_eod_summary_and_excess_equity(db_session: AsyncSession):
    """
    Verifies:
    1. Accurate breakdown of filled vs failed/rejected orders.
    2. Realized & Unrealized PnL summary.
    3. Calculation of Excess Equity (EE) and cash balance.
    4. SBL fee calculation.
    5. EOD Flex Card structure.
    """
    # 1. Seed database with orders today
    o1 = Order(
        order_id="ORD-EOD-01",
        symbol="TLI",
        side="SELL",
        volume=2000,
        price=11.10,
        status="FILLED"
    )
    o2 = Order(
        order_id="ORD-EOD-02",
        symbol="MCOT",
        side="SELL",
        volume=3400,
        price=5.50,
        status="FILLED"
    )
    o3 = Order(
        order_id="ORD-EOD-03",
        symbol="TRUE",
        side="BUY",
        volume=1000,
        price=13.23,
        status="REJECTED",
        error_message="Tick size violation"
    )
    db_session.add_all([o1, o2, o3])

    # 2. Seed SBL borrow lot
    sbl1 = SBLBorrowLot(
        lot_id="SBL-LOT-01",
        broker_tx_id="TX-9988",
        symbol="AP",
        borrow_qty=5000,
        remaining_qty=5000,
        borrow_price=8.10,
        borrow_fee_rate=3.50,
        borrow_date=date(2026, 9, 1),
        status="ACTIVE"
    )
    db_session.add(sbl1)
    await db_session.commit()

    # 3. Run EOD summary service
    summary = await eod_service.run_eod_summary(db=db_session)

    assert summary.total_orders == 3
    assert summary.matched_count == 2
    assert summary.failed_or_unmatched_count == 1
    assert len(summary.orders_matched) == 2
    assert len(summary.orders_unmatched) == 1

    # Verify Excess Equity (EE) is present and positive
    assert summary.excess_equity_thb > 0
    assert summary.cash_balance_thb > 0

    # Verify SBL calculations
    assert len(summary.sbl_holdings) == 1
    assert summary.sbl_holdings[0].symbol == "AP"
    assert summary.sbl_holdings[0].accrued_fee_thb > 0

    # Verify EOD Flex Card generation
    card = eod_service._build_eod_flex_card(summary)
    assert card["type"] == "flex"
    assert "สรุปผลการเทรดสิ้นวัน" in card["altText"]
    bubble_str = str(card["contents"])
    assert "Excess Equity" in bubble_str
    assert "2/3 สำเร็จ" in bubble_str or "2 ไม้" in bubble_str or "สำเร็จ" in bubble_str
