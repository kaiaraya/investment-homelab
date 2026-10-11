from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from app.db.session import get_db
from app.db.models import Order, Position, WatchlistTrigger
from app.core.events import event_bus
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness probe."""
    return {"status": "healthy", "service": settings.PROJECT_NAME}


@router.get("/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    """Comprehensive Homelab readiness and connectivity status."""
    # 1. Test SQLite connection
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # 2. Count DB records
    orders_count = (await db.execute(select(func.count(Order.order_id)))).scalar_one()
    positions_count = (await db.execute(select(func.count(Position.symbol)))).scalar_one()
    triggers_count = (await db.execute(select(func.count(WatchlistTrigger.id)))).scalar_one()

    # 3. Get Event bus stats
    queue_stats = event_bus.get_queue_stats()

    return {
        "status": "ready",
        "database": {
            "connected": db_ok,
            "total_orders": orders_count,
            "total_positions": positions_count,
            "active_watchlist_triggers": triggers_count
        },
        "event_bus": queue_stats,
        "config": {
            "max_order_value_thb": settings.MAX_ORDER_VALUE_THB,
            "order_idempotency_window_sec": settings.ORDER_IDEMPOTENCY_WINDOW_SEC,
            "line_simulation_mode": settings.LINE_SIMULATION_MODE
        }
    }


@router.get("/triggers")
async def list_triggers(db: AsyncSession = Depends(get_db)):
    """List all conditional watchlist monitoring triggers."""
    res = await db.execute(select(WatchlistTrigger).order_by(WatchlistTrigger.created_at.desc()))
    return res.scalars().all()
