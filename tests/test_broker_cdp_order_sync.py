# -*- coding: utf-8 -*-
"""B.7 manual-order sync (``sync_orders_from_cdp``) — unit tests.

Covers the pure normalisation helpers, the row parsers, and the end-to-end diff
against a *fake DOM* (a canned ``page.evaluate`` result standing in for the live
Streaming/WebTrade order ledger). No browser is launched — ``manager.get_tab`` is
stubbed with a fake page, exactly like ``test_broker_cdp_sync.py``.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.models import Order
from app.services.broker_cdp import sync_service


# ── fake DOM / page ────────────────────────────────────────────────────────────
class FakePage:
    """A page whose ``evaluate`` returns a fixed JS result (the "fake DOM")."""

    def __init__(self, evaluate_result: dict):
        self._result = evaluate_result

    async def evaluate(self, js: str):
        return self._result


class _FakeTab:
    def __init__(self, page):
        self._page = page

    async def __aenter__(self):
        return self._page

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def patch_get_tab(monkeypatch):
    def _patch(page):
        monkeypatch.setattr(sync_service, "get_tab", lambda cdp, target: _FakeTab(page))
    return _patch


# ── pure helpers ───────────────────────────────────────────────────────────────
def test_map_ledger_side():
    assert sync_service.map_ledger_side("Buy") == "BUY"
    assert sync_service.map_ledger_side("Sell") == "SELL"
    assert sync_service.map_ledger_side("Short") == "SHORT"
    assert sync_service.map_ledger_side("Cover") == "COVER"
    assert sync_service.map_ledger_side("Cover(M)") == "COVER"  # match marker stripped
    assert sync_service.map_ledger_side("B") == "BUY"
    assert sync_service.map_ledger_side("S") == "SELL"
    assert sync_service.map_ledger_side("H") == "SHORT"
    assert sync_service.map_ledger_side("C") == "COVER"
    assert sync_service.map_ledger_side("SHORT-SELL") == "SHORT"
    assert sync_service.map_ledger_side(None) is None  # unreadable -> skip (Anti-Mock)
    assert sync_service.map_ledger_side("") is None
    assert sync_service.map_ledger_side("XYZ") is None


def test_map_ledger_status():
    assert sync_service.map_ledger_status("Matched(M)") == "FILLED"
    assert sync_service.map_ledger_status("Filled") == "FILLED"
    assert sync_service.map_ledger_status("Cancelled") == "CANCELLED"
    assert sync_service.map_ledger_status("Rejected") == "REJECTED"
    assert sync_service.map_ledger_status("Expired") == "EXPIRED_EOD"
    assert sync_service.map_ledger_status("Partial") == "OPEN"
    assert sync_service.map_ledger_status("Queuing") == "QUEUED"
    assert sync_service.map_ledger_status("Open") == "QUEUED"
    assert sync_service.map_ledger_status("") == "QUEUED"  # unknown -> live/queued


# ── row parsers (real PROBE column layouts) ────────────────────────────────────
def test_parse_kss_order_rows():
    rows = [["11009293", "20/10", "10:20:07", "CPF", "Cover", "20.30",
             "2,400", "2,400", "0", "0", "Matched(M)", "Detail"]]
    orders = sync_service._parse_kss_order_rows(rows)
    assert len(orders) == 1
    o = orders[0]
    assert o["broker_order_no"] == "11009293"
    assert o["symbol"] == "CPF"
    assert o["side"] == "Cover"
    assert o["price"] == 20.30
    assert o["volume"] == 2400
    assert o["matched_volume"] == 2400
    assert o["balance"] == 0
    assert o["cancelled_volume"] == 0
    assert o["status"] == "Matched(M)"


def test_parse_kss_order_rows_live_checkbox_layout():
    """Real live row (order 11010191): leading checkbox cell + trailing action cells."""
    rows = [["", "11010191", "21/10", "10:18:36", "TU", "Cover", "12.60", "3,100",
             "0", "3,100", "0", "Queuing(O)", "Change", "Detail", "Cancel"]]
    orders = sync_service._parse_kss_order_rows(rows)
    assert len(orders) == 1
    o = orders[0]
    assert o["broker_order_no"] == "11010191"
    assert o["time"] == "21/10 10:18:36"
    assert o["symbol"] == "TU" and o["side"] == "Cover"
    assert o["price"] == 12.60 and o["volume"] == 3100
    assert o["matched_volume"] == 0 and o["balance"] == 3100
    assert o["status"] == "Queuing(O)"


def test_parse_kss_order_rows_skips_truncated_rows():
    """A row without the full cell contract is skipped, never half-parsed."""
    assert sync_service._parse_kss_order_rows([["", "11010191", "21/10", "TU"]]) == []


def test_parse_liberator_order_rows():
    rows = [["9001", "10:20:07", "KBANK", "Buy", "150.00", "100", "0", "100", "0", "Queuing"]]
    orders = sync_service._parse_liberator_order_rows(rows)
    assert len(orders) == 1
    o = orders[0]
    assert o["broker_order_no"] == "9001"
    assert o["symbol"] == "KBANK"
    assert o["side"] == "Buy"
    assert o["price"] == 150.0
    assert o["volume"] == 100
    assert o["matched_volume"] == 0
    assert o["balance"] == 100
    assert o["cancelled_volume"] == 0
    assert o["status"] == "Queuing"


# ── scrape (fake DOM) ──────────────────────────────────────────────────────────
KSS_ORDER_FAKE = {
    "account_no": "3024959 (Equity)",
    "rows": [
        ["11009293", "20/10", "10:20:07", "CPF", "Cover", "20.30",
         "2,400", "2,400", "0", "0", "Matched(M)", "Detail"],
        ["11010001", "21/10", "09:58:00", "KBANK", "Buy", "150.00",
         "100", "0", "100", "0", "Queuing", "Detail"],
    ],
}

LIBERATOR_ORDER_FAKE = {
    "rows": [
        ["9001", "10:20:07", "KBANK", "Buy", "150.00", "100", "0", "100", "0", "Queuing"],
    ],
}


@pytest.mark.asyncio
async def test_scrape_orders_kss(patch_get_tab):
    patch_get_tab(FakePage(KSS_ORDER_FAKE))
    snap = await sync_service.scrape_orders_from_cdp("kss")
    assert snap["broker"] == "KRUNGSRI"
    assert snap["account_no"] == "3024959"
    assert len(snap["orders"]) == 2
    assert {o["broker_order_no"] for o in snap["orders"]} == {"11009293", "11010001"}


@pytest.mark.asyncio
async def test_scrape_orders_liberator(patch_get_tab):
    patch_get_tab(FakePage(LIBERATOR_ORDER_FAKE))
    snap = await sync_service.scrape_orders_from_cdp("lib")
    assert snap["broker"] == "LIBERATOR"
    assert snap["account_no"] == "7055938"  # settings fallback
    assert len(snap["orders"]) == 1
    assert snap["orders"][0]["broker_order_no"] == "9001"


# ── sync / diff (fake DOM) ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sync_records_new_manual_order(prepare_test_db, patch_get_tab):
    from tests.conftest import TestingSessionLocal

    patch_get_tab(FakePage(KSS_ORDER_FAKE))
    res = await sync_service.sync_orders_from_cdp("kss")

    assert res["scraped"] == 2
    assert res["new_manual_count"] == 2
    assert res["new_manual_orders"] == ["11009293", "11010001"]

    async with TestingSessionLocal() as db:
        rows = (await db.execute(select(Order).order_by(Order.broker_order_no))).scalars().all()
        assert len(rows) == 2
        by_bno = {r.broker_order_no: r for r in rows}
        filled = by_bno["11009293"]
        assert filled.source == "manual_sync"
        assert filled.side == "COVER"
        assert filled.status == "FILLED"
        assert filled.symbol == "CPF"
        assert filled.volume == 2400
        assert filled.matched_volume == 2400
        assert filled.account_no == "3024959"
        assert filled.broker == "KRUNGSRI"

        queued = by_bno["11010001"]
        assert queued.source == "manual_sync"
        assert queued.side == "BUY"
        assert queued.status == "QUEUED"
        assert queued.symbol == "KBANK"


@pytest.mark.asyncio
async def test_sync_is_idempotent(prepare_test_db, patch_get_tab):
    from tests.conftest import TestingSessionLocal

    patch_get_tab(FakePage(KSS_ORDER_FAKE))
    first = await sync_service.sync_orders_from_cdp("kss")
    second = await sync_service.sync_orders_from_cdp("kss")

    assert first["new_manual_count"] == 2
    assert second["new_manual_count"] == 0  # broker_order_no already known
    async with TestingSessionLocal() as db:
        assert len((await db.execute(select(Order))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_sync_skips_known_broker_order_no(prepare_test_db, patch_get_tab):
    """A bot-placed order already in `orders` is never re-recorded as manual."""
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as db:
        db.add(Order(order_id="ORD-TEST1", broker_order_no="11010001", symbol="KBANK",
                     side="BUY", volume=100, price=150.0, status="SUBMITTED", source="api"))
        await db.commit()

    patch_get_tab(FakePage(KSS_ORDER_FAKE))
    res = await sync_service.sync_orders_from_cdp("kss")

    assert res["new_manual_orders"] == ["11009293"]  # only the unknown one
    assert res["new_manual_count"] == 1


@pytest.mark.asyncio
async def test_sync_skips_unreadable_rows_fail_closed(prepare_test_db, patch_get_tab):
    """Unreadable side / symbol / price / volume -> skipped, never fabricated."""
    from tests.conftest import TestingSessionLocal

    fake = {
        "account_no": "3024959 (Equity)",
        "rows": [
            ["11020001", "21/10", "10:00:00", "KBANK", "???", "150.00",
             "100", "0", "100", "0", "Queuing", "Detail"],  # bad side
            ["11020002", "21/10", "10:01:00", "", "Buy", "150.00",
             "100", "0", "100", "0", "Queuing", "Detail"],      # empty symbol
            ["11020003", "21/10", "10:02:00", "PTT", "Buy", "",   # unreadable price
             "100", "0", "100", "0", "Queuing", "Detail"],
            ["11020004", "21/10", "10:03:00", "PTT", "Buy", "32.00",
             "0", "0", "0", "0", "Cancelled", "Detail"],         # zero volume
        ],
    }
    patch_get_tab(FakePage(fake))
    res = await sync_service.sync_orders_from_cdp("kss")

    assert res["scraped"] == 4
    assert res["new_manual_count"] == 0
    assert res["skipped"] == 4
    async with TestingSessionLocal() as db:
        assert (await db.execute(select(Order))).scalars().all() == []


@pytest.mark.asyncio
async def test_sync_unknown_broker_raises(prepare_test_db, patch_get_tab):
    with pytest.raises(ValueError):
        await sync_service.sync_orders_from_cdp("nope")
