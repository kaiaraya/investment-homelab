"""``reconcile_sbl_lots`` — the broker ledger must win over our own cache."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.db.models import SBLBorrowLot
from app.services.sbl_ledger_service import reconcile_sbl_lots


def _scrape(rows, source="sbl_read_cdp", success=True):
    return patch(
        "app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.scrape_full_pool",
        new_callable=AsyncMock,
        return_value={
            "success": success,
            "source": source,
            "active_borrow_transactions": rows,
        },
    )


def _tx(ref, symbol, qty, price, day="02/11/2026"):
    return {
        "ref_no": ref,
        "tran_date": day,
        "symbol": symbol,
        "type": "B",
        "quantity": qty,
        "borrow_price": price,
    }


async def _lots(db):
    res = await db.execute(select(SBLBorrowLot))
    return {lot.broker_tx_id: lot for lot in res.scalars().all()}


@pytest.mark.asyncio
async def test_creates_missing_lots_and_closes_returned_ones(db_session):
    db_session.add(SBLBorrowLot(
        lot_id="SBL-OLD-B1", broker_tx_id="B1", symbol="OLD",
        borrow_qty=1000, remaining_qty=1000, borrow_price=1.0,
        borrow_date=date(2026, 10, 20), status="ACTIVE",
    ))
    await db_session.commit()

    with _scrape([_tx("B9", "TPIPP", 32000, 1.58)]):
        report = await reconcile_sbl_lots(db_session)

    assert report["ok"] is True
    assert report["created"] == 1
    assert report["closed"] == 1

    lots = await _lots(db_session)
    assert lots["B9"].remaining_qty == 32000
    assert lots["B9"].borrow_price == 1.58
    assert lots["B9"].borrow_date == date(2026, 11, 2)
    assert lots["B1"].status == "FULLY_RETURNED"
    assert lots["B1"].remaining_qty == 0


@pytest.mark.asyncio
async def test_clamps_cache_down_to_broker_quantity(db_session):
    db_session.add(SBLBorrowLot(
        lot_id="SBL-TPIPP-B9", broker_tx_id="B9", symbol="TPIPP",
        borrow_qty=32000, remaining_qty=32000, borrow_price=1.58,
        borrow_date=date(2026, 11, 2), status="ACTIVE",
    ))
    await db_session.commit()

    with _scrape([_tx("B9", "TPIPP", 12000, 1.58)]):
        report = await reconcile_sbl_lots(db_session)

    assert report["updated"] == 1
    lots = await _lots(db_session)
    assert lots["B9"].remaining_qty == 12000


@pytest.mark.asyncio
async def test_empty_ledger_never_wipes_the_book(db_session):
    db_session.add(SBLBorrowLot(
        lot_id="SBL-PTT-B1", broker_tx_id="B1", symbol="PTT",
        borrow_qty=100, remaining_qty=100, borrow_price=42.0,
        borrow_date=date(2026, 10, 29), status="ACTIVE",
    ))
    await db_session.commit()

    with _scrape([]):
        report = await reconcile_sbl_lots(db_session)

    assert report["ok"] is False
    assert report["code"] == "SBL_LEDGER_EMPTY"
    lots = await _lots(db_session)
    assert lots["B1"].status == "ACTIVE"
    assert lots["B1"].remaining_qty == 100


@pytest.mark.asyncio
async def test_non_live_source_is_refused(db_session):
    db_session.add(SBLBorrowLot(
        lot_id="SBL-PTT-B1", broker_tx_id="B1", symbol="PTT",
        borrow_qty=100, remaining_qty=100, borrow_price=42.0,
        borrow_date=date(2026, 10, 29), status="ACTIVE",
    ))
    await db_session.commit()

    with _scrape([_tx("B2", "TIDLOR", 3000, 16.4)], source="playwright_fallback"):
        report = await reconcile_sbl_lots(db_session)

    assert report["ok"] is False
    assert report["code"] == "SBL_NOT_LIVE"
    lots = await _lots(db_session)
    assert "B2" not in lots
    assert lots["B1"].status == "ACTIVE"


@pytest.mark.asyncio
async def test_scrape_failure_does_not_raise(db_session):
    with patch(
        "app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.scrape_full_pool",
        new_callable=AsyncMock,
        side_effect=RuntimeError("CDP gone"),
    ):
        report = await reconcile_sbl_lots(db_session)

    assert report["ok"] is False
    assert report["code"] == "SBL_SCRAPE_FAILED"
