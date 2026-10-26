"""Unit tests for ``app/services/nego_pricer.py`` — the pure price planner."""
import pytest

from app.services.nego_pricer import plan_price


def test_buy_match_hits_offer():
    r = plan_price("BUY", "match", bid=10.0, offer=10.1, last=10.05, old_price=9.9)
    assert r["ok"] is True and r["price"] == 10.1


def test_buy_lure_joins_bid():
    r = plan_price("BUY", "lure", bid=10.0, offer=10.1, last=10.05, old_price=9.9)
    assert r["ok"] is True and r["price"] == 10.0


def test_sell_match_hits_bid():
    r = plan_price("SELL", "match", bid=10.0, offer=10.1, last=10.05, old_price=10.2)
    assert r["ok"] is True and r["price"] == 10.0


def test_sell_lure_joins_offer():
    r = plan_price("SELL", "lure", bid=10.0, offer=10.1, last=10.05, old_price=10.2)
    assert r["ok"] is True and r["price"] == 10.1


def test_cover_is_a_buy_side():
    r = plan_price("COVER", "match", bid=10.0, offer=10.1, last=10.05, old_price=10.2)
    assert r["ok"] is True and r["price"] == 10.1


def test_short_match_at_bid_legal_when_bid_above_last():
    # bid 10.1 > last 10.0 -> legal
    r = plan_price("SHORT", "match", bid=10.1, offer=10.2, last=10.0, old_price=10.3)
    assert r["ok"] is True and r["price"] == 10.1


def test_short_match_refused_when_bid_not_above_last():
    # bid 9.9 <= last 10.0 -> uptick violation
    r = plan_price("SHORT", "match", bid=9.9, offer=10.0, last=10.0, old_price=10.1)
    assert r["ok"] is False and "uptick" in r["reason"]


def test_short_lure_uses_offer_when_above_last():
    r = plan_price("SHORT", "lure", bid=9.9, offer=10.1, last=10.0, old_price=10.2)
    assert r["ok"] is True and r["price"] == 10.1


def test_short_lure_bumps_above_last_when_offer_not_above():
    # offer == last == 10.0 -> must step one tick above last
    r = plan_price("SHORT", "lure", bid=9.9, offer=10.0, last=10.0, old_price=10.2)
    assert r["ok"] is True and r["price"] > 10.0


def test_missing_leg_fails_closed():
    assert plan_price("BUY", "match", bid=10.0, offer=None, last=10.0, old_price=9.9)["ok"] is False
    assert plan_price("SELL", "match", bid=None, offer=10.1, last=10.0, old_price=10.2)["ok"] is False
    assert plan_price("BUY", "lure", bid=None, offer=10.1, last=10.0, old_price=9.9)["ok"] is False


def test_short_without_last_fails_closed():
    r = plan_price("SHORT", "match", bid=10.1, offer=10.2, last=None, old_price=10.3)
    assert r["ok"] is False and "last" in r["reason"]


def test_no_change_when_price_equals_old():
    r = plan_price("BUY", "match", bid=10.0, offer=10.1, last=10.05, old_price=10.1)
    assert r["ok"] is False and r["reason"] == "NO_CHANGE"


def test_unknown_mode_or_side():
    assert plan_price("BUY", "weird", bid=10.0, offer=10.1, last=10.05, old_price=9.9)["ok"] is False
    assert plan_price("HOLD", "match", bid=10.0, offer=10.1, last=10.05, old_price=9.9)["ok"] is False
