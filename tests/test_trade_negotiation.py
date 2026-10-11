import pytest
from app.core.config import settings
from app.db.models import Order
from app.services.trade_center_service import trade_center_service
from app.services.price_negotiation_service import price_negotiation_service


@pytest.mark.asyncio
async def test_trade_center_pre_order_approval_and_execution(db_session):
    # 1. Prepare approval card for valid order
    prep_res = await trade_center_service.prepare_order_approval(
        symbol="TRUE",
        side="BUY",
        volume=1000,
        price=13.20
    )
    assert prep_res["success"] is True
    assert prep_res["status"] == "AWAITING_USER_APPROVAL"
    assert "confirm_payload" in prep_res["card"]

    # 2. Prepare approval card for invalid odd-lot order (e.g. 96 shares)
    invalid_prep = await trade_center_service.prepare_order_approval(
        symbol="TRUE",
        side="BUY",
        volume=96,
        price=13.20
    )
    assert invalid_prep["success"] is False
    assert invalid_prep["status"] == "VALIDATION_FAILED"

    # 3. Simulate user confirmation execution under DRY_RUN_MODE=True
    exec_res = await trade_center_service.execute_confirmed_order(
        db=db_session,
        symbol="TRUE",
        side="BUY",
        volume=1000,
        price=13.20,
        order_id="ORD-TEST-CONFIRM"
    )
    assert exec_res["success"] is True
    assert "SIM-" in exec_res["broker_order_no"]

    # Verify order is saved in DB
    order = await db_session.get(Order, "ORD-TEST-CONFIRM")
    assert order is not None
    assert order.status in ["SUBMITTED", "MATCHED"]


# =============================================================================
# SHORT price negotiation (strict SET Uptick rule) - KSS-RCA (2026-10-09)
# =============================================================================
from app.services.validator import validator  # noqa: E402


def _short_order(price: float, order_no: str = "C260109000001"):
    return {
        "symbol": "AP",
        "side": "SHORT",
        "price": price,
        "broker_order_no": order_no,
        "volume": 1000,
    }


def _patch_quote(monkeypatch, quote):
    """Patch the broker driver factory to serve a fixed market quote."""

    class _FakeDriver:
        async def get_market_bid_offer(self, symbol):  # noqa: D401
            return dict(quote)

    monkeypatch.setattr(
        "app.services.price_negotiation_service.get_broker_driver",
        lambda: _FakeDriver(),
    )


@pytest.mark.asyncio
async def test_short_negotiation_fail_closed_when_last_missing(monkeypatch):
    """Anti-Mock: with no real `last`, propose nothing (no backfill)."""
    _patch_quote(monkeypatch, {"bid_1": None, "offer_1": None, "last": None})

    proposal = await price_negotiation_service.evaluate_order_negotiation(
        _short_order(price=8.20)
    )

    assert proposal["needs_adjustment"] is False
    assert proposal["needs_review"] is True
    assert proposal["target_price"] == 8.20  # never a fabricated move
    assert "fail-closed" in proposal["reason"]


@pytest.mark.asyncio
async def test_short_negotiation_strict_floor_is_last_plus_one_tick(monkeypatch):
    """When no depth is available, target = last + 1 tick (strictly > last)."""
    _patch_quote(monkeypatch, {"bid_1": None, "offer_1": None, "last": 8.20})

    proposal = await price_negotiation_service.evaluate_order_negotiation(
        _short_order(price=8.10)
    )

    assert proposal["needs_adjustment"] is True
    assert proposal["target_price"] == 8.25  # 8.20 + 0.05 (tick band < 10.00)
    ok, _ = validator.validate_short_uptick(proposal["target_price"], 8.20)
    assert ok is True


@pytest.mark.asyncio
async def test_short_negotiation_skip_when_at_best_offer(monkeypatch):
    """User rule: already at the best offer -> do nothing, wait for uptick."""
    _patch_quote(monkeypatch, {"bid_1": None, "offer_1": 8.20, "last": 8.15})

    proposal = await price_negotiation_service.evaluate_order_negotiation(
        _short_order(price=8.20)
    )

    assert proposal["needs_adjustment"] is False
    assert proposal["target_price"] == 8.20
    assert "best offer" in proposal["reason"]


@pytest.mark.asyncio
async def test_short_negotiation_skip_when_one_tick_above_offer(monkeypatch):
    """User rule: best offer + 1 tick is also acceptable -> do nothing."""
    _patch_quote(monkeypatch, {"bid_1": None, "offer_1": 8.20, "last": 8.15})

    proposal = await price_negotiation_service.evaluate_order_negotiation(
        _short_order(price=8.25)  # offer_1 + 1 tick
    )

    assert proposal["needs_adjustment"] is False
    assert proposal["target_price"] == 8.25
    assert "best offer" in proposal["reason"]


@pytest.mark.asyncio
async def test_short_negotiation_reprices_when_far_above_offer(monkeypatch):
    """More than 1 tick above the best offer -> re-price down to Offer 1."""
    _patch_quote(monkeypatch, {"bid_1": None, "offer_1": 8.20, "last": 8.15})

    proposal = await price_negotiation_service.evaluate_order_negotiation(
        _short_order(price=8.35)  # offer_1 + 3 ticks -> stale, move down
    )

    assert proposal["needs_adjustment"] is True
    assert proposal["target_price"] == 8.20  # max(offer_1, last + 1 tick)
    ok, _ = validator.validate_short_uptick(proposal["target_price"], 8.15)
    assert ok is True
