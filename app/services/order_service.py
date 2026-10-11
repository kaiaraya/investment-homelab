import uuid
import logging
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.db.models import Order, SessionLog, WatchlistTrigger
from app.schemas.order import OrderCreate, OrderStatus, OrderSide
from app.services.validator import validator
from app.core.events import event_bus

logger = logging.getLogger(__name__)


class OrderService:
    """
    Manages order creation, database persistence, state transitions,
    and event dispatch to Automation Workers.
    """

    async def create_order(
        self,
        db: AsyncSession,
        order_in: OrderCreate,
        source: str = "api"
    ) -> Tuple[Order, bool]:
        """
        Validates the order and persists to SQLite.
        If valid: status is PENDING and dispatched to event bus.
        If invalid: status is REJECTED with error_message stored in DB.
        """
        order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        
        # 1. Run Pre-trade Risk & Board Lot validations
        is_valid, error_message = validator.validate_all(
            symbol=order_in.symbol,
            side=order_in.side.value,
            volume=order_in.volume,
            price=order_in.price
        )

        status = OrderStatus.PENDING if is_valid else OrderStatus.REJECTED

        # 2. Persist order into SQLite
        order = Order(
            order_id=order_id,
            broker_order_no=order_in.broker_order_no,
            symbol=order_in.symbol.upper(),
            side=order_in.side.value,
            volume=order_in.volume,
            price=order_in.price,
            status=status.value,
            error_message=error_message,
            source=source
        )
        db.add(order)

        # 3. Add Session Log
        log_event = "ORDER_CREATED" if is_valid else "VALIDATION_ERROR"
        details = (
            f"Order {order_id}: {order_in.side.value} {order_in.volume} {order_in.symbol} @ ฿{order_in.price:.2f}"
        )
        if not is_valid:
            details += f" | Rejected: {error_message}"

        log = SessionLog(event_type=log_event, details=details)
        db.add(log)

        await db.commit()
        await db.refresh(order)

        # 4. If valid, dispatch to event bus for worker execution
        if is_valid:
            await event_bus.publish_order({
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "volume": order.volume,
                "price": order.price,
                "status": order.status,
                "source": order.source
            })
            logger.info("Order %s queued for execution", order_id)

        return order, is_valid

    async def get_orders(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Order]:
        """Fetch orders with optional status filter."""
        query = select(Order)
        if status:
            query = query.where(Order.status == status.upper())
        query = query.order_by(Order.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_order_by_id(self, db: AsyncSession, order_id: str) -> Optional[Order]:
        """Fetch a specific order by ID."""
        query = select(Order).where(Order.order_id == order_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def update_order_status(
        self,
        db: AsyncSession,
        order_id: str,
        new_status: OrderStatus,
        broker_order_no: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Optional[Order]:
        """Updates the status of an existing order."""
        order = await self.get_order_by_id(db, order_id)
        if not order:
            return None

        order.status = new_status.value
        if broker_order_no:
            order.broker_order_no = broker_order_no
        if error_message:
            order.error_message = error_message

        await db.commit()
        await db.refresh(order)
        return order

    async def expire_eod_orders(self, db: AsyncSession) -> int:
        """
        Marks all active PENDING/QUEUED orders as EXPIRED_EOD at market close (16:35 น.).
        Prevents stale day orders from firing the next day unexpectedly.
        """
        query = (
            update(Order)
            .where(Order.status.in_([OrderStatus.PENDING.value, OrderStatus.QUEUED.value]))
            .values(
                status=OrderStatus.EXPIRED_EOD.value,
                error_message="Expired at End-of-Day (16:35 Market Close)"
            )
        )
        result = await db.execute(query)
        await db.commit()
        return result.rowcount

    async def carry_over_orders(self, db: AsyncSession, order_ids: List[str]) -> int:
        """
        Sets designated orders to CARRY_OVER_PENDING for execution the next day (e.g. Stop Loss / Exit).
        """
        query = (
            update(Order)
            .where(Order.order_id.in_(order_ids))
            .values(
                status=OrderStatus.CARRY_OVER_PENDING.value,
                error_message="Rolled over to next trading day by user policy"
            )
        )
        result = await db.execute(query)
        await db.commit()
        return result.rowcount

    async def save_watchlist_triggers(
        self,
        db: AsyncSession,
        triggers: list
    ) -> int:
        """Persists conditional watchlist triggers to database."""
        count = 0
        for trg in triggers:
            item = WatchlistTrigger(
                symbol=trg.symbol,
                action=trg.action,
                volume=trg.volume,
                condition_type=trg.condition,
                trigger_price=trg.trigger_price,
                status="ACTIVE",
                notes=trg.current_status
            )
            db.add(item)
            count += 1
        if count > 0:
            await db.commit()
        return count


order_service = OrderService()
