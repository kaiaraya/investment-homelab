from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.webhook import SignalTextPayload
from app.schemas.intelligence import SignalParseResult
from app.schemas.order import OrderCreate
from app.core.security import verify_payload_token_or_header
from app.services.parser import signal_parser
from app.services.order_service import order_service

router = APIRouter()


@router.post("/signal-text", response_model=SignalParseResult)
async def parse_and_process_signal_text(
    payload: SignalTextPayload,
    x_homelab_key: str | None = Header(default=None, alias="X-Homelab-Key"),
    db: AsyncSession = Depends(get_db)
):
    """
    Intelligent Signal & Strategy Report Ingestion Endpoint.
    Ingests freeform/markdown trading reports (e.g. 5.1 Hard Exit, 5.2 Climax TP, 5.3 Watchlist triggers).
    Extracts executable orders, trailing stops, and conditional triggers.
    If auto_execute=True, automatically commits and queues validated immediate orders.
    """
    # 1. Verify Secret Key
    verify_payload_token_or_header(payload.auth_token, x_homelab_key)

    # 2. Parse text into structured elements
    result = signal_parser.parse_text(payload.text)

    # 3. If auto_execute requested, commit immediate orders and triggers
    if payload.auto_execute:
        queued_ids = []
        for ext_order in result.immediate_orders:
            if ext_order.is_valid_lot:
                order_in = OrderCreate(
                    symbol=ext_order.symbol,
                    side=ext_order.side,
                    volume=ext_order.volume,
                    price=ext_order.price,
                    source="signal_intelligence"
                )
                order, is_valid = await order_service.create_order(
                    db, order_in, source="signal_intelligence"
                )
                if is_valid:
                    queued_ids.append(order.order_id)
        result.queued_order_ids = queued_ids

        # Persist Watchlist Triggers
        if result.watchlist_triggers:
            await order_service.save_watchlist_triggers(db, result.watchlist_triggers)

    return result
