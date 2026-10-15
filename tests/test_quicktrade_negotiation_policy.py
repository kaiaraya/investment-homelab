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


def test_plan_max_ticks_exceeded_states_the_distance():
    """G5 (TASK-loop1-2): a target beyond LINE_NEGO_MAX_TICKS ticks is refused."""
    d = plan_negotiation(_order(side="BUY", price=29.25),
                         Quote(symbol="MTC", best_bid=30.25, best_offer=30.50, last=30.00))
    assert d.outcome is NegotiationOutcome.MAX_TICKS_EXCEEDED
    assert d.target_price is None                      # nothing submittable
    assert "4 ticks" in d.reason and "allowed 3" in d.reason


def test_plan_target_within_max_ticks_is_ok():
    """3 ticks away is still inside the LINE_NEGO_MAX_TICKS=3 default."""
    d = plan_negotiation(_order(side="BUY", price=29.25),
                         Quote(symbol="MTC", best_bid=30.00, best_offer=30.25, last=30.00))
    assert d.outcome is NegotiationOutcome.OK
    assert d.target_price == 30.00


def test_plan_max_ticks_override_is_honoured():
    q = Quote(symbol="MTC", best_bid=30.00, best_offer=30.25, last=30.00)
    assert plan_negotiation(_order(side="BUY", price=29.25), q).outcome is NegotiationOutcome.OK

    d = plan_negotiation(_order(side="BUY", price=29.25), q, max_ticks=1)
    assert d.outcome is NegotiationOutcome.MAX_TICKS_EXCEEDED


def test_plan_tick_size_violation_fails_closed():
    """G4: a quote price off the SET tick grid is never submitted."""
    d = plan_negotiation(_order(side="BUY", price=29.25),
                         Quote(symbol="MTC", best_bid=29.10, best_offer=29.35, last=29.20))
    assert d.outcome is NegotiationOutcome.TICK_SIZE_VIOLATION
    assert d.target_price is None
    assert "tick size" in d.reason


def test_tick_distance_counts_in_the_higher_bracket():
    from app.services.quicktrade_negotiation_service import tick_distance
    assert tick_distance(29.25, 30.25) == 4           # 1.00 THB / 0.25 tick
    assert tick_distance(29.25, 29.25) == 0


def test_plan_short_at_last_price_is_an_uptick_violation():
    """G6 strict (TASK-loop1-2): the zero-plus tick on LastPrice is rejected."""
    d = plan_negotiation(_order(side="SHORT", price=29.25),
                         Quote(symbol="MTC", best_bid=29.00, best_offer=29.50, last=29.50))
    assert d.outcome is NegotiationOutcome.UPTICK_VIOLATION
    assert d.target_price is None                     # nothing submittable
    assert "zero-plus tick" in d.reason


def test_plan_short_strictly_above_last_is_ok():
    d = plan_negotiation(_order(side="SHORT", price=29.25),
                         Quote(symbol="MTC", best_bid=29.00, best_offer=29.75, last=29.50))
    assert d.outcome is NegotiationOutcome.OK
    assert d.target_price == 29.75


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

    async def get_order(self, order_no, account_no=None):
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


@pytest.mark.asyncio
async def test_negotiate_order_price_refuses_far_target_without_amending(monkeypatch):
    """G5 end to end: the driver is never asked to amend and the caller gets the reason."""
    from app.services.quicktrade_negotiation_service import negotiate_order_price
    stub = _patch_driver(monkeypatch, _StubDriver(
        order={'success': True, 'symbol': 'MTC', 'side': 'BUY', 'price': 29.25,
               'balance': 100, 'account_no': '3024959'},
        quote={'success': True, 'symbol': 'MTC', 'best_bid': 30.25, 'best_offer': 30.50, 'last': 30.00},
    ))

    res = await negotiate_order_price('11008198')
    assert res['success'] is False and res['outcome'] == 'MAX_TICKS_EXCEEDED'
    assert res['amendment'] is None and '4 ticks' in res['error']
    assert stub.amend_calls == []
