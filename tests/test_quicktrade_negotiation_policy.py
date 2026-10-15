"""Policy tests for the Quick Trade passive negotiation core (Pillar 6).

The module under test is pure and browser-free: importing it here (no playwright)
is itself part of the contract, mirroring the probe-script test.
"""
import pytest

from app.services.quicktrade_negotiation_service import (
    NegotiationOutcome,
    OrderSnapshot,
    Quote,
    compute_passive_price,
    plan_negotiation,
)


def test_module_imports_without_playwright():
    import app.services.quicktrade_negotiation_service as mod
    assert [k for k in mod.__dict__ if "playwright" in k.lower()] == []


# --- compute_passive_price ------------------------------------------------

def test_buy_targets_best_bid():
    d = compute_passive_price("BUY", best_bid=10.00, best_offer=10.05, last=10.02)
    assert d.outcome is NegotiationOutcome.OK
    assert d.target_price == 10.00


def test_sell_targets_best_offer():
    d = compute_passive_price("SELL", best_bid=10.00, best_offer=10.05, last=10.02)
    assert d.outcome is NegotiationOutcome.OK
    assert d.target_price == 10.05


@pytest.mark.parametrize("side", ["SHORT", "OPEN_SHORT"])
@pytest.mark.parametrize("offer,last,expected", [
    (10.05, 10.00, 10.05),   # offer above last -> passive offer
    (10.00, 10.00, 10.00),   # offer == last -> last (no violation)
])
def test_short_targets_max_of_offer_and_last(side, offer, last, expected):
    d = compute_passive_price(side, best_bid=9.95, best_offer=offer, last=last)
    assert d.outcome is NegotiationOutcome.OK
    assert d.target_price == expected


@pytest.mark.parametrize("side", ["SHORT", "OPEN_SHORT"])
def test_short_uptick_violation_when_offer_below_last(side):
    d = compute_passive_price(side, best_bid=9.95, best_offer=9.98, last=10.00)
    assert d.outcome is NegotiationOutcome.UPTICK_VIOLATION
    assert d.target_price is None


def test_cover_and_long_follow_buy_side():
    for side in ("COVER", "LONG"):
        d = compute_passive_price(side, best_bid=10.00, best_offer=10.05, last=10.02)
        assert d.outcome is NegotiationOutcome.OK
        assert d.target_price == 10.00


def test_missing_quote_fails_closed():
    assert compute_passive_price("BUY", None, 10.05, 10.02).outcome is NegotiationOutcome.NO_QUOTE
    assert compute_passive_price("SELL", 10.00, None, 10.02).outcome is NegotiationOutcome.NO_QUOTE
    assert compute_passive_price("SHORT", 9.95, 9.98, None).outcome is NegotiationOutcome.NO_QUOTE


def test_unsupported_side():
    d = compute_passive_price("SHORT_SELL", 10.00, 10.05, 10.02)
    assert d.outcome is NegotiationOutcome.UNSUPPORTED_SIDE


# --- plan_negotiation -----------------------------------------------------

def _order(side="SHORT", price=29.25, balance=500):
    return OrderSnapshot(order_no="11008198", symbol="MTC", side=side,
                         price=price, balance=balance, account_no="3024959")


def test_plan_no_change_when_target_equals_current():
    d = plan_negotiation(_order(price=29.25),
                         Quote(symbol="MTC", best_bid=29.00, best_offer=29.25, last=29.00))
    assert d.outcome is NegotiationOutcome.NO_CHANGE
    assert d.target_price == 29.25


def test_plan_preserves_volume():
    d = plan_negotiation(_order(balance=700),
                         Quote(symbol="MTC", best_bid=29.00, best_offer=29.50, last=29.25))
    assert d.outcome is NegotiationOutcome.OK
    assert d.volume == 700                  # invariant 3: volume untouched
    assert d.current_price == 29.25


def test_plan_propagates_uptick_violation():
    d = plan_negotiation(_order(), Quote(symbol="MTC", best_bid=28.00, best_offer=29.00, last=29.50))
    assert d.outcome is NegotiationOutcome.UPTICK_VIOLATION
    assert d.target_price is None


# --- G4 tick-size / G5 tick distance (loop 1) ------------------------------ #

def test_plan_rejects_a_price_that_is_not_a_legal_set_tick():
    """Above 25 THB the SET tick is 0.25, so 29.37 can never be amended to (G4)."""
    d = plan_negotiation(_order(side="BUY", price=29.25),
                         Quote(symbol="MTC", best_bid=29.37, best_offer=29.50, last=29.25))
    assert d.outcome is NegotiationOutcome.INVALID_TICK_SIZE
    assert d.target_price == 29.37            # the computed price is shown, never hidden
    assert "tick" in d.reason.lower()


def test_plan_rejects_more_than_the_configured_tick_distance():
    """29.00 -> 30.00 is 4 SET ticks (> LINE_NEGO_MAX_TICKS=3) -> fail closed (G5)."""
    d = plan_negotiation(_order(side="BUY", price=29.00),
                         Quote(symbol="MTC", best_bid=30.00, best_offer=30.25, last=29.00))
    assert d.outcome is NegotiationOutcome.MAX_TICKS_EXCEEDED
    assert "4 tick" in d.reason and "LINE_NEGO_MAX_TICKS=3" in d.reason


def test_plan_allows_exactly_the_configured_tick_distance():
    d = plan_negotiation(_order(side="BUY", price=29.00),
                         Quote(symbol="MTC", best_bid=29.75, best_offer=30.00, last=29.00))
    assert d.outcome is NegotiationOutcome.OK
    assert d.target_price == 29.75


def test_plan_honours_an_explicit_max_ticks():
    d = plan_negotiation(_order(side="BUY", price=29.00),
                         Quote(symbol="MTC", best_bid=30.00, best_offer=30.25, last=29.00),
                         max_ticks=4)
    assert d.outcome is NegotiationOutcome.OK


def test_tick_distance_counts_set_ticks_and_fails_closed():
    from app.services.quicktrade_negotiation_service import tick_distance
    assert tick_distance(29.00, 29.75) == 3
    assert tick_distance(29.75, 29.00) == 3
    assert tick_distance(29.25, 29.25) == 0
    assert tick_distance(None, 29.00) is None
    assert tick_distance(29.00, None) is None
    assert tick_distance("bad", 29.00) is None


# --------------------------------------------------------------------------- #
# orchestration: negotiate_order_price() binds the policy to the Quick Trade driver
# --------------------------------------------------------------------------- #
class _StubDriver:
    """Records what the orchestration asks the broker to do — no browser."""

    def __init__(self, order=None, quote=None, amend=None):
        self._order = order or {'success': False, 'error': 'no order'}
        self._quote = quote or {'success': False, 'error': 'no quote'}
        self._amend = amend or {'success': True, 'submitted': True, 'dry_run': False}
        self.amend_calls = []
        self.quote_calls = []
        self.order_calls = []

    async def get_order(self, order_no, account_no=None):
        self.order_calls.append((order_no, account_no))
        return dict(self._order)

    async def get_quote(self, symbol, account_no=None):
        self.quote_calls.append((symbol, account_no))
        return dict(self._quote)

    async def amend_price(self, order_no, new_price, account_no, trade_date=None, pin=None, dry_run=None):
        self.amend_calls.append({'order_no': order_no, 'new_price': new_price, 'account_no': account_no,
                                 'trade_date': trade_date, 'pin': pin, 'dry_run': dry_run})
        return dict(self._amend)


def _patch_driver(monkeypatch, stub):
    import app.brokers.krungsri.quicktrade_driver as drv
    monkeypatch.setattr(drv, 'quicktrade_driver', stub)
    return stub


@pytest.mark.asyncio
async def test_negotiate_order_price_resolves_snapshot_and_amends(monkeypatch):
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'SHORT', 'price': 29.25,
               'balance': 500, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 29.25, 'best_offer': 29.50, 'last': 29.00},
    ))

    res = await negotiate_order_price('11008198')
    assert res['success'] is True and res['outcome'] == 'OK'
    assert res['target_price'] == 29.50 and res['volume'] == 500
    assert stub.amend_calls[0]['account_no'] == '3024959'      # account discovered by get_order
    assert stub.amend_calls[0]['new_price'] == 29.50


@pytest.mark.asyncio
async def test_negotiate_order_price_pins_the_margin_account(monkeypatch):
    """Loop 1: the in-place amendment is MARGIN-only — never a discovered/foreign account."""
    from app.core.config import settings
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    margin = str(settings.TRADEMAN_ACCOUNT_NO_MARGIN).strip()
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.00,
               'balance': 100, 'account_no': '9999999'},      # a foreign account must be ignored
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 29.25, 'best_offer': 29.50, 'last': 29.00},
    ))

    res = await negotiate_order_price('11008198')

    assert res['success'] is True
    assert stub.order_calls == [('11008198', margin)]         # ledger read is pinned to MARGIN
    assert stub.amend_calls[0]['account_no'] == margin


@pytest.mark.asyncio
async def test_negotiate_order_price_fails_closed_when_the_market_is_too_far(monkeypatch):
    """G5 end-to-end: a target further than LINE_NEGO_MAX_TICKS never reaches the broker."""
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.00,
               'balance': 100, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 30.00, 'best_offer': 30.25, 'last': 29.00},
    ))

    res = await negotiate_order_price('11008198')

    assert res['success'] is False and res['outcome'] == 'MAX_TICKS_EXCEEDED'
    assert 'LINE_NEGO_MAX_TICKS' in res['error'] and stub.amend_calls == []


@pytest.mark.asyncio
async def test_negotiate_order_price_reports_unknown_order(monkeypatch):
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    _patch_driver(monkeypatch, _StubDriver(order={'success': False, 'error': 'order not found'}))

    res = await negotiate_order_price('999')
    assert res['success'] is False and 'not found' in res['error']


@pytest.mark.asyncio
async def test_negotiate_order_price_fails_closed_on_missing_quote(monkeypatch):
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.00,
               'balance': 100, 'account_no': '3024959'},
        quote={'success': False, 'error': 'quote unavailable'},
    ))

    res = await negotiate_order_price('11008198')
    assert res['success'] is False and stub.amend_calls == []


@pytest.mark.asyncio
async def test_negotiate_order_price_propagates_uptick_violation(monkeypatch):
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'SHORT', 'price': 29.25,
               'balance': 500, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 29.25, 'best_offer': 29.00, 'last': 29.25},
    ))

    res = await negotiate_order_price('11008198')
    assert res['success'] is False and res['outcome'] == 'UPTICK_VIOLATION'
    assert stub.amend_calls == []


@pytest.mark.asyncio
async def test_negotiate_order_price_execute_false_never_amends(monkeypatch):
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.00,
               'balance': 100, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 29.25, 'best_offer': 29.50, 'last': 29.00},
    ))

    res = await negotiate_order_price('11008198', execute=False)
    assert res['outcome'] == 'OK' and res['amendment'] is None and stub.amend_calls == []


@pytest.mark.asyncio
async def test_negotiate_order_price_dry_run_reports_unsubmitted_amendment(monkeypatch):
    """DRY-RUN: the plan succeeds but nothing reaches the broker — `success` must not imply it did."""
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.00,
               'balance': 100, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 29.25, 'best_offer': 29.50, 'last': 29.00},
        amend={'success': True, 'submitted': False, 'dry_run': True, 'status': 'STAGED_DRY_RUN'},
    ))

    res = await negotiate_order_price('11008198', dry_run=True)
    assert res['success'] is True and res['outcome'] == 'OK'
    assert res['amendment']['submitted'] is False                  # honest: staged only
    assert res['submitted'] is False and res['dry_run'] is True     # top-level mirror for REST callers


@pytest.mark.asyncio
async def test_negotiate_order_price_reports_amendment_failure(monkeypatch):
    """A rejected amendment must surface as failure, never as a silent OK."""
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.00,
               'balance': 100, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 29.25, 'best_offer': 29.50, 'last': 29.00},
        amend={'success': False, 'submitted': False, 'dry_run': False, 'error': 'broker rejected price'},
    ))

    res = await negotiate_order_price('11008198')
    assert res['success'] is False and res['error'] == 'broker rejected price'
    assert res['submitted'] is False
