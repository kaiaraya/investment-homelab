import pytest
from app.services.validator import PreTradeValidator


def test_odd_lot_enforcement():
    v = PreTradeValidator()
    
    # Valid Board lots (multiple of 100)
    ok, err = v.validate_board_lot(100)
    assert ok is True
    assert err is None
    
    ok, err = v.validate_board_lot(5000)
    assert ok is True
    assert err is None

    # Invalid Odd-lots (e.g. 96 shares from video 2)
    ok, err = v.validate_board_lot(96)
    assert ok is False
    assert "Odd-lot rejected" in err

    ok, err = v.validate_board_lot(150)
    assert ok is False
    assert "Odd-lot rejected" in err

    ok, err = v.validate_board_lot(0)
    assert ok is False


def test_set_tick_sizes():
    v = PreTradeValidator()
    
    # Bracket < 2.00 (Tick = 0.01)
    ok, _ = v.validate_tick_size(1.55)
    assert ok is True

    # Bracket 2.00 - 4.98 (Tick = 0.02)
    ok, _ = v.validate_tick_size(2.36)
    assert ok is True
    ok, err = v.validate_tick_size(2.35)
    assert ok is False
    assert "Tick size violation" in err

    # Bracket 5.00 - 9.95 (Tick = 0.05)
    ok, _ = v.validate_tick_size(6.80)
    assert ok is True
    ok, _ = v.validate_tick_size(5.50)
    assert ok is True
    ok, err = v.validate_tick_size(6.82)
    assert ok is False

    # Bracket 10.00 - 24.90 (Tick = 0.10)
    ok, _ = v.validate_tick_size(11.10)
    assert ok is True
    ok, _ = v.validate_tick_size(13.20)
    assert ok is True
    ok, err = v.validate_tick_size(11.15)
    assert ok is False

    # Bracket 25.00 - 99.75 (Tick = 0.25)
    ok, _ = v.validate_tick_size(62.50)
    assert ok is True
    ok, _ = v.validate_tick_size(46.25)
    assert ok is True
    ok, err = v.validate_tick_size(62.60)
    assert ok is False

    # Bracket 200.00 - 399.00 (Tick = 1.00)
    ok, _ = v.validate_tick_size(276.00)
    assert ok is True


def test_max_order_value():
    v = PreTradeValidator()
    
    # Within 1M THB limit
    ok, _ = v.validate_order_value(1000, 50.0)  # 50,000 THB
    assert ok is True

    # Exceeding 1M THB limit
    ok, err = v.validate_order_value(100000, 50.0)  # 5,000,000 THB
    assert ok is False
    assert "Risk ceiling exceeded" in err


def test_idempotency_guard():
    v = PreTradeValidator()
    
    # First submission
    ok, _ = v.check_idempotency("AP", "BUY", 1000, 8.20)
    assert ok is True

    # Immediate duplicate submission
    ok, err = v.check_idempotency("AP", "BUY", 1000, 8.20)
    assert ok is False
    assert "Duplicate order blocked" in err

    # Different symbol or side is allowed
    ok, _ = v.check_idempotency("TRUE", "BUY", 1000, 8.20)
    assert ok is True


def test_short_uptick_rule():
    v = PreTradeValidator()

    # Short STRICTLY above last trade price (allowed)
    ok, err = v.validate_short_uptick(price=8.25, last_trade_price=8.20)
    assert ok is True
    assert err is None

    # Zero-plus tick (equal to last) is NOT allowed - must move up at least 1 tick
    ok, err = v.validate_short_uptick(price=8.20, last_trade_price=8.20)
    assert ok is False
    assert "SET Short Sale Rule Violation" in err

    # Short below last trade price (violation of uptick rule)
    ok, err = v.validate_short_uptick(price=8.15, last_trade_price=8.20)
    assert ok is False
    assert "SET Short Sale Rule Violation" in err


def test_get_next_tick():
    v = PreTradeValidator()

    # Tick bracket 5.00 - 9.95 (Tick = 0.05)
    assert v.get_next_tick(8.20, steps=1) == 8.25
    assert v.get_next_tick(8.20, steps=2) == 8.30
    assert v.get_next_tick(8.20, steps=-1) == 8.15

    # Tick bracket crossing boundary: 9.95 -> 10.00 -> 10.10
    assert v.get_next_tick(9.95, steps=1) == 10.00
    assert v.get_next_tick(10.00, steps=1) == 10.10
    assert v.get_next_tick(10.10, steps=-1) == 10.00

