import pytest
from datetime import date
from sqlalchemy import select

from app.db.models import Position, SBLBorrowLot
from app.services.portfolio_overview_service import portfolio_overview_service
from app.schemas.intelligence import ExtractedTPSL


@pytest.mark.asyncio
async def test_reconcile_portfolio_silent(db_session):
    # Setup initial position in DB
    initial_pos = Position(
        symbol="CPALL",
        position_type="LONG",
        volume=500,
        avg_cost=45.0,
        current_price=45.50
    )
    db_session.add(initial_pos)
    await db_session.commit()

    # Simulate TradeMan scraped holdings (user bought 300 more on mobile -> now 800 shares @ 46.25)
    scraped = [
        {
            "symbol": "CPALL",
            "volume": 800,
            "avg_cost": 46.25,
            "current_price": 46.00,
            "prior_close_price": 46.50,
            "unrealized_pnl": -200.0,
            "pnl_pct": -0.54,
            "position_type": "LONG"
        },
        {
            "symbol": "HMPRO",
            "volume": 1000,
            "avg_cost": 9.50,
            "current_price": 10.00,
            "prior_close_price": 9.80,
            "unrealized_pnl": 500.0,
            "pnl_pct": 5.26,
            "position_type": "LONG"
        }
    ]

    reconciled = await portfolio_overview_service.reconcile_portfolio(db_session, scraped)
    assert len(reconciled) == 2

    # Check that CPALL was updated to 800 shares
    stmt = select(Position).where(Position.symbol == "CPALL")
    res = await db_session.execute(stmt)
    cpall = res.scalar_one()
    assert cpall.volume == 800
    assert cpall.avg_cost == 46.25

    # Check that HMPRO was inserted
    stmt = select(Position).where(Position.symbol == "HMPRO")
    res = await db_session.execute(stmt)
    hmpro = res.scalar_one_or_none()
    assert hmpro is not None
    assert hmpro.volume == 1000


@pytest.mark.asyncio
async def test_detect_sbl_pending_return_on_mobile_close(db_session):
    # Setup open Short position with SBL lot in DB
    short_pos = Position(
        symbol="AP",
        position_type="SHORT",
        volume=5000,
        avg_cost=8.10,
        current_price=8.15,
        is_sbl_pending_return=False
    )
    db_session.add(short_pos)
    await db_session.commit()

    # User closes AP on mobile app -> TradeMan scraped holdings now empty for AP!
    scraped = []
    await portfolio_overview_service.reconcile_portfolio(db_session, scraped)

    stmt = select(Position).where(Position.symbol == "AP")
    res = await db_session.execute(stmt)
    ap = res.scalar_one()
    assert ap.volume == 0
    assert ap.is_sbl_pending_return is True  # Detected mobile close, flagged for SBL return!


@pytest.mark.asyncio
async def test_missing_tpsl_and_apply(db_session):
    pos = Position(
        symbol="TRUE",
        position_type="LONG",
        volume=2000,
        avg_cost=13.00,
        current_price=13.20,
        take_profit_price=None,
        stop_loss_price=None
    )
    db_session.add(pos)
    await db_session.commit()

    missing = await portfolio_overview_service.get_stocks_missing_tpsl(db_session)
    missing_symbols = [m["symbol"] for m in missing]
    assert "TRUE" in missing_symbols

    # Apply TP/SL
    items = [
        ExtractedTPSL(symbol="TRUE", side="LONG", take_profit=14.00, stop_loss=12.50)
    ]
    updated = await portfolio_overview_service.apply_tpsl_items(db_session, items)
    assert len(updated) == 1
    assert updated[0]["tp"] == 14.00
    assert updated[0]["sl"] == 12.50

    # Verify no longer missing
    missing_after = await portfolio_overview_service.get_stocks_missing_tpsl(db_session)
    assert "TRUE" not in [m["symbol"] for m in missing_after]
