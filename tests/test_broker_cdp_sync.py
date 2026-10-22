# -*- coding: utf-8 -*-
"""B.3 portfolio auto-sync (``sync_portfolio_from_cdp``) — unit tests.

Covers the pure normalisation helpers and the end-to-end UPSERT path against a *fake
DOM* (a canned ``page.evaluate`` result standing in for the live Streaming/WebTrade
DOM). No browser is launched — ``manager.get_tab`` is stubbed with a fake page.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.models import BrokerAccount, Position
from app.services.broker_cdp import sync_service


# ── fake DOM / page ────────────────────────────────────────────────────────────
class FakePage:
    """A page whose ``evaluate`` returns a fixed JS result (the "fake DOM")."""

    def __init__(self, evaluate_result: dict, has_portfolio_btn: bool = True):
        self._result = evaluate_result
        self._has_portfolio_btn = has_portfolio_btn
        self.evaluate_calls = 0

    async def evaluate(self, js: str):
        self.evaluate_calls += 1
        return self._result

    async def query_selector(self, sel: str):
        if not self._has_portfolio_btn:
            return None
        el = MagicMock()
        el.is_visible = AsyncMock(return_value=True)
        el.click = AsyncMock()
        return el

    async def wait_for_timeout(self, ms: int):
        return None


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
def test_map_kss_account_type():
    assert sync_service.map_kss_account_type("Credit Balance") == "CREDIT_BALANCE"
    assert sync_service.map_kss_account_type("Cash") == "CASH_BALANCE"
    assert sync_service.map_kss_account_type("  MARGIN  ") == "CREDIT_BALANCE"
    assert sync_service.map_kss_account_type(None) is None
    assert sync_service.map_kss_account_type("") is None


def test_map_liberator_account_type():
    assert sync_service.map_liberator_account_type("CASH BALANCE") == "CASH_BALANCE"
    assert sync_service.map_liberator_account_type("credit balance") == "CREDIT_BALANCE"
    assert sync_service.map_liberator_account_type("") is None


def test_extract_account_no():
    assert sync_service.extract_account_no("3024959 (Equity)") == "3024959"
    assert sync_service.extract_account_no("7055938") == "7055938"
    assert sync_service.extract_account_no("no account here") is None


def test_to_float_anti_mock():
    assert sync_service._to_float("1,234.56") == 1234.56
    assert sync_service._to_float("0.00") == 0.0
    assert sync_service._to_float(None) is None
    assert sync_service._to_float("—") is None


def test_clean_kss_symbol_suffixes():
    assert sync_service._clean_kss_symbol("TISCO (S)") == ("TISCO", "S")
    assert sync_service._clean_kss_symbol("TU (B)") == ("TU", "B")
    assert sync_service._clean_kss_symbol("PTT") == ("PTT", None)
    assert sync_service._clean_kss_symbol("KBANK (M)") == ("KBANK", None)  # unknown marker -> None


# ── UPSERT path (fake DOM) ─────────────────────────────────────────────────────
KSS_FAKE = {
    "account_no": "3024959 (Equity)",
    "balances": {
        "account_type": "Credit Balance",
        "credit_limit": "500,000.00",
        "line_available": "1,234,567.89",
        "excess_equity": "200,000.00",
    },
    "holdings": [
        {"symbol": "AP", "position_type": "SHORT", "volume": 2000, "available_volume": 500,
         "avg_cost": 8.10, "current_price": 8.15, "market_value": 16300.0, "unrealized_pnl": -100.0},
        {"symbol": "PTT", "position_type": "LONG", "volume": 1000, "available_volume": 1000,
         "avg_cost": 32.50, "current_price": 33.00, "market_value": 33000.0, "unrealized_pnl": 500.0},
    ],
}

LIBERATOR_FAKE = {
    "account_type": "CASH BALANCE",
    "line_available": "225,877.48",
    "cash_balance": "125,767.47",
    "credit_limit": "500,000.00",
    "holdings": [
        {"symbol": "KBANK", "position_type": "LONG", "available_volume": 300, "volume": 300,
         "avg_cost": 150.0, "current_price": 152.0, "market_value": 45600.0,
         "unrealized_pnl": 600.0, "unrealized_pnl_pct": 1.33},
    ],
}


@pytest.mark.asyncio
async def test_sync_kss_upserts_account_and_positions(prepare_test_db, patch_get_tab):
    from tests.conftest import TestingSessionLocal

    patch_get_tab(FakePage(KSS_FAKE))
    async with TestingSessionLocal() as db:
        res = await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    assert res["account_no"] == "3024959"
    assert res["account_type"] == "CREDIT_BALANCE"
    assert res["line_available"] == 1234567.89
    assert res["positions"] == 2

    async with TestingSessionLocal() as db:
        acc = (await db.execute(select(BrokerAccount))).scalars().one()
        assert acc.account_no == "3024959"
        assert acc.broker == "KRUNGSRI"
        assert acc.account_type == "CREDIT_BALANCE"
        assert acc.line_available == 1234567.89
        assert acc.excess_equity == 200000.0

        rows = (await db.execute(select(Position).order_by(Position.symbol))).scalars().all()
        assert {(r.account_no, r.symbol, r.volume) for r in rows} == {
            ("3024959", "AP", 2000),
            ("3024959", "PTT", 1000),
        }
        ap = next(r for r in rows if r.symbol == "AP")
        assert ap.position_type == "SHORT"
        assert ap.market_value == 16300.0


@pytest.mark.asyncio
async def test_sync_liberator_upserts(prepare_test_db, patch_get_tab):
    from tests.conftest import TestingSessionLocal

    patch_get_tab(FakePage(LIBERATOR_FAKE, has_portfolio_btn=False))
    async with TestingSessionLocal() as db:
        res = await sync_service.sync_portfolio_from_cdp("lib", db=db)
        await db.commit()

    assert res["broker"] == "LIBERATOR"
    assert res["account_no"] == "7055938"  # fallback from settings
    assert res["line_available"] == 225877.48
    assert res["cash_balance"] == 125767.47
    # total_equity = cash_balance + market_value = 125767.47 + 45600
    assert res["total_equity"] == pytest.approx(171367.47)

    async with TestingSessionLocal() as db:
        acc = (await db.execute(select(BrokerAccount))).scalars().one()
        assert acc.broker == "LIBERATOR"
        assert acc.account_type == "CASH_BALANCE"
        assert acc.credit_limit == 500000.0

        pos = (await db.execute(select(Position))).scalars().one()
        assert pos.account_no == "7055938"
        assert pos.symbol == "KBANK"
        assert pos.volume == 300
        assert pos.unrealized_pnl_pct == 1.33


@pytest.mark.asyncio
async def test_sync_kss_short_suffix_and_borrowed_excluded(prepare_test_db, patch_get_tab):
    """``(S)`` suffix -> SHORT position; ``(B)`` suffix -> excluded (SBL borrow lot)."""
    from tests.conftest import TestingSessionLocal

    fake = {
        "account_no": "3024959 (Equity)",
        "balances": {"account_type": "Credit Balance", "credit_limit": "1,200,000.00",
                     "line_available": "634,864.16", "excess_equity": "317,432.08"},
        "holdings": [
            {"symbol": "TISCO (S)", "position_type": "LONG", "volume": 300,
             "available_volume": 300, "avg_cost": 124.29, "current_price": 124.50,
             "market_value": 37350.0, "unrealized_pnl": -62.74},
            {"symbol": "TU (B)", "position_type": "LONG", "volume": 3100,
             "available_volume": 3100, "avg_cost": 0.0, "current_price": 12.70,
             "market_value": 39370.0, "unrealized_pnl": 0.0},
        ],
    }
    patch_get_tab(FakePage(fake))
    async with TestingSessionLocal() as db:
        res = await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    assert res["positions"] == 1  # only TISCO; TU (B) is a borrow lot, not a position
    async with TestingSessionLocal() as db:
        rows = (await db.execute(select(Position))).scalars().all()
        assert len(rows) == 1
        assert rows[0].symbol == "TISCO"
        assert rows[0].position_type == "SHORT"
        assert rows[0].volume == 300


@pytest.mark.asyncio
async def test_sync_is_upsert_not_duplicate(prepare_test_db, patch_get_tab):
    """A second sync of the same account updates rows, never duplicates them."""
    from tests.conftest import TestingSessionLocal

    patch_get_tab(FakePage(KSS_FAKE))
    async with TestingSessionLocal() as db:
        await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    updated = dict(KSS_FAKE)
    updated["balances"] = dict(KSS_FAKE["balances"], line_available="999,999.00")
    patch_get_tab(FakePage(updated))
    async with TestingSessionLocal() as db:
        await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    async with TestingSessionLocal() as db:
        accs = (await db.execute(select(BrokerAccount))).scalars().all()
        assert len(accs) == 1
        assert accs[0].line_available == 999999.0
        positions = (await db.execute(select(Position))).scalars().all()
        assert len(positions) == 2


@pytest.mark.asyncio
async def test_sync_zeroes_stale_positions(prepare_test_db, patch_get_tab):
    """A holding no longer on the frontend is zeroed (external close), not left stale."""
    from tests.conftest import TestingSessionLocal

    patch_get_tab(FakePage(KSS_FAKE))
    async with TestingSessionLocal() as db:
        await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    # PTT disappears from the next scrape -> volume 0; AP (SHORT) flagged for SBL return.
    only_ap = {"account_no": "3024959 (Equity)",
               "balances": dict(KSS_FAKE["balances"]),
               "holdings": [KSS_FAKE["holdings"][0]]}
    patch_get_tab(FakePage(only_ap))
    async with TestingSessionLocal() as db:
        await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    async with TestingSessionLocal() as db:
        rows = {r.symbol: r for r in (await db.execute(select(Position))).scalars().all()}
        assert rows["PTT"].volume == 0
        assert rows["AP"].volume == 2000
        assert rows["AP"].is_sbl_pending_return is False  # AP still open


@pytest.mark.asyncio
async def test_sync_unknown_broker_raises(prepare_test_db, patch_get_tab):
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as db:
        with pytest.raises(ValueError):
            await sync_service.sync_portfolio_from_cdp("nope", db=db)


@pytest.mark.asyncio
async def test_sync_unreadable_balance_is_none(prepare_test_db, patch_get_tab):
    """An unreadable balance cell is stored as None (Anti-Mock), never a fake 0.00."""
    from tests.conftest import TestingSessionLocal

    bad = {"account_no": "3024952 (Equity)",
           "balances": {"account_type": "Cash", "credit_limit": None, "line_available": None},
           "holdings": []}
    patch_get_tab(FakePage(bad))
    async with TestingSessionLocal() as db:
        await sync_service.sync_portfolio_from_cdp("kss", db=db)
        await db.commit()

    async with TestingSessionLocal() as db:
        acc = (await db.execute(select(BrokerAccount))).scalars().one()
        assert acc.account_no == "3024952"
        assert acc.account_type == "CASH_BALANCE"
        assert acc.line_available is None
        assert acc.credit_limit is None


@pytest.mark.asyncio
async def test_sync_kss_unreadable_account_no_fails_closed(prepare_test_db, patch_get_tab):
    """If KSS's active account_no can't be read off the header, write nothing (RCA-011)."""
    from tests.conftest import TestingSessionLocal

    bad = {"account_no": "", "balances": {"account_type": "Cash"}, "holdings": []}
    patch_get_tab(FakePage(bad))
    async with TestingSessionLocal() as db:
        with pytest.raises(RuntimeError):
            await sync_service.sync_portfolio_from_cdp("kss", db=db)

    async with TestingSessionLocal() as db:
        assert (await db.execute(select(BrokerAccount))).scalars().all() == []
