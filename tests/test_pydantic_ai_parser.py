import os
import pytest
from pydantic_ai.models.test import TestModel

from app.schemas.order import OrderSide
from app.schemas.intelligence import (
    SignalParseResult,
    ExtractedOrder,
    ExtractedWatchlistTrigger,
    ExtractedHoldPosition,
)
from app.ai.signal_agent import create_signal_agent, PydanticAISignalParser
from app.services.parser import signal_parser

USECASE1_PATH = "ตัวอย่างคำสั่ง/usecase1.md"


# ==============================================================================
# 1. TEST PYDANTIC-AI AGENT TYPE-SAFE VALIDATION
# ==============================================================================
@pytest.mark.asyncio
async def test_pydantic_ai_agent_type_safety():
    """
    Validates that the PydanticAI Agent strictly enforces type annotations
    and returns a valid SignalParseResult.
    """
    expected_data = SignalParseResult(
        total_parsed=3,
        immediate_orders=[
            ExtractedOrder(
                symbol="AOT",
                side=OrderSide.SELL,
                volume=600,
                price=62.25,
                reason="Stop Loss 2.0%"
            )
        ],
        watchlist_triggers=[
            ExtractedWatchlistTrigger(
                symbol="JMT",
                action="SELL",
                volume=3500,
                condition="PRICE_BELOW",
                trigger_price=10.40,
                notes="Trailing Stop Breakeven"
            )
        ],
        hold_positions=[
            ExtractedHoldPosition(
                symbol="CPALL",
                volume=800,
                position_type="LONG",
                days_held=9,
                group_type="WEED_OUT"
            )
        ],
        strategy_summary="วันนี้มีคำสั่งตัดขาดทุน AOT 600 หุ้น และยก Trailing Stop JMT",
        source_method="pydantic_ai_deepseek"
    )

    test_model = TestModel(custom_output_args=expected_data.model_dump())
    agent = create_signal_agent(model_override=test_model)

    parser = PydanticAISignalParser(agent=agent)
    res = await parser.parse_strategy("sample strategy text")

    # Assertions on returned Pydantic Model
    assert isinstance(res, SignalParseResult)
    assert res.source_method == "pydantic_ai_deepseek"
    assert len(res.immediate_orders) == 1
    assert res.immediate_orders[0].symbol == "AOT"
    assert res.immediate_orders[0].side == OrderSide.SELL
    assert res.immediate_orders[0].volume == 600
    assert res.immediate_orders[0].price == 62.25
    assert len(res.watchlist_triggers) == 1
    assert res.watchlist_triggers[0].symbol == "JMT"
    assert len(res.hold_positions) == 1
    assert res.hold_positions[0].symbol == "CPALL"
    assert res.hold_positions[0].days_held == 9


# ==============================================================================
# 2. TEST DUAL-ENGINE PARSER ON ACTUAL usecase1.md
# ==============================================================================
@pytest.mark.asyncio
async def test_dual_engine_strategy_parsing():
    """
    Tests parsing actual usecase1.md through signal_parser.parse_strategy_with_ai.
    Ensures that either via PydanticAI Gemini or Deterministic Fallback:
    1. Returns a valid SignalParseResult instance (Type-Safe).
    2. Correctly extracts AOT SELL 600 @ 62.25.
    3. Extracts runners (JMT, CKP).
    4. Extracts hold positions (CPALL, FORTH, etc.).
    """
    assert os.path.exists(USECASE1_PATH), f"{USECASE1_PATH} not found"
    with open(USECASE1_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    res = await signal_parser.parse_strategy_with_ai(text)

    # 1. Type validation
    assert isinstance(res, SignalParseResult)
    assert res.total_parsed >= 10
    assert res.source_method in ["pydantic_ai_deepseek", "pydantic_ai_gemini", "gemini_3.6_flash", "deterministic_fallback"]

    # 2. Check Immediate Orders: AOT SELL 600 @ 62.25
    aot_orders = [o for o in res.immediate_orders if o.symbol == "AOT"]
    assert len(aot_orders) == 1
    aot = aot_orders[0]
    assert aot.side == OrderSide.SELL
    assert aot.volume == 600
    assert aot.price == 62.25

    # 3. Check Watchlist Triggers (JMT or CKP)
    trig_symbols = {t.symbol for t in res.watchlist_triggers}
    assert "JMT" in trig_symbols or "CKP" in trig_symbols

    # 4. Check Hold positions
    hold_symbols = {h.symbol for h in res.hold_positions}
    assert "CPALL" in hold_symbols or "FORTH" in hold_symbols or "VIH" in hold_symbols
