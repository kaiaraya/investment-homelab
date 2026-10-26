"""Unit tests for the N3 nego-menu (ต่อราคา) postback flow.

Covers the four postback actions (``nego_menu`` / ``nego_mode`` /
``nego_confirm`` / ``nego_cancel``) with the CDP scrape, quote, and amend layers
mocked. No broker is touched; the amend path is stubbed to a DRY-RUN result.
"""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.broker_cdp.sync_service as sync
import app.services.market_clock as mc
import app.services.line_cli.handlers as H


def _service():
    s = MagicMock()
    s._send_reply = AsyncMock()
    return s


async def _call(action, **params):
    return await H._handle_nego_postback(
        action, {k: str(v) for k, v in params.items()}, _service(), "rt", None)


_ORDER = {
    "broker_order_no": "12345", "symbol": "PTT", "side": "Buy",
    "price": 33.75, "volume": 1000, "matched_volume": 0, "balance": 1000,
    "status": "Queuing(O)",
}
_QUOTE = {"success": True, "bid_1": 34.0, "offer_1": 34.25, "last": 34.1}


@pytest.mark.asyncio
async def test_nego_menu_out_of_hours(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: False)
    scrape = AsyncMock()
    monkeypatch.setattr(H, "_scrape_nego_orders", scrape)
    res = await _call("nego_menu")
    assert res["status"] == "NEGO_OUT_OF_HOURS"
    scrape.assert_not_awaited()          # never touches the broker outside the window


@pytest.mark.asyncio
async def test_nego_menu_empty(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    monkeypatch.setattr(H, "_scrape_nego_orders", AsyncMock(return_value=[]))
    assert (await _call("nego_menu"))["status"] == "NEGO_MENU_EMPTY"


@pytest.mark.asyncio
async def test_nego_menu_displays_orders(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    monkeypatch.setattr(H, "_scrape_nego_orders", AsyncMock(return_value=[{
        "broker": "kss", "order_no": "12345", "symbol": "PTT", "side": "BUY",
        "price": 34.0, "volume": 1000, "balance": 1000,
    }]))
    res = await _call("nego_menu")
    assert res["status"] == "NEGO_MENU_DISPLAYED" and res["count"] == 1


@pytest.mark.asyncio
async def test_nego_mode_drafts_a_lure_price(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    monkeypatch.setattr(sync, "scrape_orders_from_cdp", AsyncMock(return_value={
        "broker": "KRUNGSRI", "account_no": "3024959", "orders": [_ORDER]}))
    monkeypatch.setattr(H, "_broker_quote", AsyncMock(return_value=_QUOTE))

    res = await _call("nego_mode", broker="kss", order_no="12345", mode="lure")

    assert res["status"] == "NEGO_DRAFTED"
    draft = H._DRAFTS.pop(res["draft_id"])       # clean up; assert the draft was stored
    assert draft is not None
    assert draft["symbol"] == "PTT" and draft["side"] == "BUY"
    assert draft["new_price"] == 34.0             # BUY lure -> join the bid, not the offer


@pytest.mark.asyncio
async def test_nego_mode_match_hits_offer(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    monkeypatch.setattr(sync, "scrape_orders_from_cdp", AsyncMock(return_value={
        "broker": "KRUNGSRI", "account_no": "3024959", "orders": [_ORDER]}))
    monkeypatch.setattr(H, "_broker_quote", AsyncMock(return_value=_QUOTE))

    res = await _call("nego_mode", broker="kss", order_no="12345", mode="match")
    assert res["status"] == "NEGO_DRAFTED"
    draft = H._DRAFTS.pop(res["draft_id"])
    assert draft["new_price"] == 34.25            # BUY match -> hit the offer


@pytest.mark.asyncio
async def test_nego_mode_order_gone(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    monkeypatch.setattr(sync, "scrape_orders_from_cdp", AsyncMock(return_value={
        "broker": "KRUNGSRI", "account_no": "3024959", "orders": []}))
    res = await _call("nego_mode", broker="kss", order_no="99999", mode="match")
    assert res["status"] == "NEGO_ORDER_GONE"


@pytest.mark.asyncio
async def test_nego_mode_bad_postback(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    assert (await _call("nego_mode", broker="bogus", order_no="1", mode="match"))["status"] == "NEGO_BAD_POSTBACK"
    assert (await _call("nego_mode", broker="kss", order_no="1", mode="weird"))["status"] == "NEGO_BAD_POSTBACK"


@pytest.mark.asyncio
async def test_nego_confirm_dry_run(monkeypatch):
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    H._store_draft({
        "draft_id": "DRAFT-X", "created_at": time.time(),
        "broker": "kss", "order_no": "12345", "symbol": "PTT", "side": "BUY",
        "volume": 1000, "old_price": 34.0, "new_price": 34.25, "mode": "match",
    })
    monkeypatch.setattr(H, "_broker_modify", AsyncMock(return_value={
        "success": True, "status": "OPEN", "is_matched": False}))

    res = await _call("nego_confirm", draft_id="DRAFT-X")
    assert res["status"] == "NEGO_CONFIRMED"
    assert res["dry_run"] is True          # TEST dispatcher -> DRY-RUN


@pytest.mark.asyncio
async def test_nego_confirm_replay_is_blocked(monkeypatch):
    """A replayed confirm finds no draft (popped) and must not amend twice."""
    monkeypatch.setattr(mc, "is_nego_window", lambda now=None: True)
    H._store_draft({
        "draft_id": "DRAFT-Y", "created_at": time.time(),
        "broker": "lib", "order_no": "77", "symbol": "CPALL", "side": "SELL",
        "volume": 500, "old_price": 60.0, "new_price": 60.25, "mode": "lure",
    })
    amend = AsyncMock(return_value={"success": True, "status": "OPEN"})
    monkeypatch.setattr(H, "_broker_modify", amend)

    assert (await _call("nego_confirm", draft_id="DRAFT-Y"))["status"] == "NEGO_CONFIRMED"
    assert (await _call("nego_confirm", draft_id="DRAFT-Y"))["status"] == "NEGO_DRAFT_EXPIRED"
    assert amend.await_count == 1           # exactly one amend


@pytest.mark.asyncio
async def test_nego_cancel(monkeypatch):
    H._store_draft({
        "draft_id": "DRAFT-Z", "created_at": time.time(),
        "broker": "kss", "order_no": "1", "symbol": "PTT", "side": "BUY",
        "volume": 100, "old_price": 34.0, "new_price": 34.25, "mode": "match",
    })
    assert (await _call("nego_cancel", draft_id="DRAFT-Z"))["status"] == "NEGO_CANCELLED"
    assert "DRAFT-Z" not in H._DRAFTS
