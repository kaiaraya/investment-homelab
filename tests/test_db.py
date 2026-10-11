import pytest
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Order, SBLBorrowLot, Position, SessionLog


@pytest.mark.asyncio
async def test_database_models_and_relationships(prepare_test_db):
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as session:
        # 1. Create SBL Borrow Lot
        sbl_lot = SBLBorrowLot(
            lot_id="LOT-8493414",
            broker_tx_id="8493414",
            symbol="AP",
            borrow_qty=5000,
            remaining_qty=5000,
            borrow_price=8.10,
            borrow_fee_rate=3.50,
            borrow_date=date(2026, 9, 8),
            status="ACTIVE"
        )
        session.add(sbl_lot)
        await session.commit()

        # 2. Create Short Position linked to SBL Lot
        pos = Position(
            symbol="AP",
            position_type="SHORT",
            volume=5000,
            avg_cost=8.10,
            current_price=8.15,
            unrealized_pnl=-250.0,
            associated_sbl_lot_id="LOT-8493414"
        )
        session.add(pos)
        await session.commit()

        # 3. Create Order
        order = Order(
            order_id="ORD-TEST-001",
            symbol="AP",
            side="SHORT",
            volume=5000,
            price=8.10,
            status="PENDING"
        )
        session.add(order)

        # 4. Create Session Log
        log = SessionLog(
            event_type="LOGIN_SUCCESS",
            details="Krungsri SSO to TradeMan completed"
        )
        session.add(log)
        await session.commit()

        # Verify queries and relationship
        res_pos = await session.execute(select(Position).where(Position.symbol == "AP"))
        fetched_pos = res_pos.scalar_one()
        assert fetched_pos.volume == 5000
        assert fetched_pos.associated_sbl_lot_id == "LOT-8493414"

        res_orders = await session.execute(select(Order))
        assert len(res_orders.scalars().all()) == 1

        res_logs = await session.execute(select(SessionLog))
        assert len(res_logs.scalars().all()) == 1
