from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.db.session import get_db
from app.schemas.order import OrderResponse
from app.services.order_service import order_service
from app.core.events import event_bus
from app.core.config import settings

router = APIRouter()


class RolloverRequest(BaseModel):
    order_ids: List[str]


@router.get("", response_model=List[OrderResponse])
async def list_orders(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List historical and active orders, optionally filtered by status (PENDING, FILLED, REJECTED, etc.)."""
    return await order_service.get_orders(db, status=status, limit=limit)


@router.get("/queue/status")
async def get_queue_status():
    """Get internal asyncio Event Bus and queue statistics for Phase 2/3 workers."""
    return event_bus.get_queue_stats()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve specific order details by ID."""
    order = await order_service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found"
        )
    return order


@router.post("/eod/expire")
async def expire_eod_orders(db: AsyncSession = Depends(get_db)):
    """Mark all pending day orders as EXPIRED_EOD at market close."""
    count = await order_service.expire_eod_orders(db)
    return {"status": "ok", "expired_count": count}


@router.post("/rollover")
async def rollover_orders(
    payload: RolloverRequest,
    db: AsyncSession = Depends(get_db)
):
    """Carry over important orders (Cut loss / Exit) to tomorrow's queue."""
    count = await order_service.carry_over_orders(db, payload.order_ids)
    return {"status": "ok", "carried_over_count": count}


@router.delete("/clear")
async def clear_test_data(db: AsyncSession = Depends(get_db)):
    """Clears test orders, watchlist triggers, and session logs for fresh testing."""
    from sqlalchemy import delete
    from app.db.models import Order, WatchlistTrigger, SessionLog
    await db.execute(delete(Order))
    await db.execute(delete(WatchlistTrigger))
    await db.execute(delete(SessionLog))
    await db.commit()
    from app.services.validator import validator
    validator.clear_idempotency_cache()
    return {"status": "ok", "message": "All test orders, triggers, and logs cleared successfully"}


class QuickOrderRequest(BaseModel):
    symbol: str
    side: str = "BUY"  # BUY, SELL, OPEN_SHORT, COVER, LONG, SHORT
    position: Optional[str] = "AUTO"  # OPEN, CLOSE, AUTO
    volume: int = 100
    price: float = 0.0
    broker: str = "CLICK2WIN"  # CLICK2WIN, TRADEMAN, LIBERATOR, SETTRADE_OPENAPI
    account_type: Optional[str] = "EQUITY"


@router.post("/quick-execute")
async def quick_execute_order(payload: QuickOrderRequest, db: AsyncSession = Depends(get_db)):
    """Executes a direct order via Pillar 3 Trade Execution Engine with Guardrails and logs to DB."""
    import uuid
    from app.db.models import Order
    from app.core.config import settings
    from app.services.validator import validator

    # Strict Pre-Trade Asset Segregation & Guardrails Validation
    ok, err = validator.validate_all(
        symbol=payload.symbol,
        side=payload.side,
        volume=payload.volume,
        price=payload.price,
        position=payload.position
    )
    if not ok:
        return {"success": False, "status": "REJECTED", "error": err}

    broker_norm = payload.broker.upper()
    is_real_money = broker_norm in ["KRUNGSRI", "TRADEMAN", "LIBERATOR"] and settings.ENABLE_HITL_LIVE_GATE
    is_sandbox_hitl = broker_norm == "CLICK2WIN" and getattr(settings, "ENABLE_HITL_SANDBOX_GATE", False)
    if is_real_money or is_sandbox_hitl:
        order_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        order_rec = Order(
            order_id=order_id,
            broker_order_no=None,
            symbol=payload.symbol.upper(),
            side=payload.side.upper(),
            position=payload.position.upper() if payload.position else "AUTO",
            volume=payload.volume,
            price=payload.price,
            status="AWAITING_HITL_CONFIRMATION",
            error_message="Waiting for Human 1-Click Confirmation on /console Cockpit",
            source=f"{payload.broker.lower()}"
        )
        db.add(order_rec)
        await db.commit()

        # Send Critical Actionable Alert to KDE Connect mobile
        try:
            from app.services.kdeconnect_service import kdeconnect_service
            pos_label = f" ({payload.position.upper()})" if payload.position else ""
            title = f"⚠️ [Live Trade Confirmation] {payload.broker.upper()}"
            msg = f"คำสั่งซื้อขายจริง: {payload.side.upper()}{pos_label} {payload.volume} {payload.symbol.upper()} @ ฿{payload.price:.2f}\nเปิด /console เพื่อกดยืนยันส่งคำสั่ง!"
            await kdeconnect_service.send_critical_alert(title, msg)
        except Exception as e:
            logger.debug(f"KDE Connect alert error: {e}")

        # Broadcast event to Cockpit SSE
        try:
            from app.core.sse_broadcaster import sse_broadcaster
            await sse_broadcaster.broadcast("hitl_order_pending", {
                "order_id": order_id,
                "symbol": payload.symbol.upper(),
                "side": payload.side.upper(),
                "position": payload.position.upper() if payload.position else "AUTO",
                "volume": payload.volume,
                "price": payload.price,
                "broker": payload.broker.upper()
            })
        except Exception:
            pass

        return {
            "success": True,
            "hitl_required": True,
            "order_id": order_id,
            "status": "AWAITING_HITL_CONFIRMATION",
            "message": f"คำสั่ง {payload.symbol.upper()} ({payload.side.upper()}) เข้าสู่คิว HITL Gate เรียบร้อย แจ้งเตือนไปยังมือถือแล้ว กรุณากดยืนยันที่หน้าจอ /console"
        }

    from app.mcp.pillars.pillar3_trade import trade_place_order
    res = await trade_place_order(
        symbol=payload.symbol,
        side=payload.side,
        volume=payload.volume,
        price=payload.price,
        position=payload.position or "AUTO",
        platform=payload.broker,
        account_type=payload.account_type
    )
    
    # Persist in DB for Live Cockpit & Orders Journal
    order_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
    status_str = "SUBMITTED" if res.get("success") else "REJECTED"
    order_rec = Order(
        order_id=order_id,
        broker_order_no=str(res.get("order_no") or ""),
        symbol=payload.symbol.upper(),
        side=payload.side.upper(),
        position=payload.position.upper() if payload.position else "AUTO",
        volume=payload.volume,
        price=payload.price,
        status=status_str,
        error_message=res.get("reason"),
        source=f"{payload.broker.lower()}"
    )
    db.add(order_rec)
    await db.commit()
    
    return res


@router.get("/hitl/pending")
async def list_pending_hitl_orders(db: AsyncSession = Depends(get_db)):
    """Returns all orders currently waiting for 1-Click Human confirmation."""
    import json
    from sqlalchemy import select
    from app.db.models import Order
    stmt = select(Order).where(Order.status == "AWAITING_HITL_CONFIRMATION").order_by(Order.created_at.desc())
    res = await db.execute(stmt)
    orders = res.scalars().all()
    results = []
    for o in orders:
        meta = {}
        if o.error_message and o.error_message.strip().startswith("{"):
            try:
                meta = json.loads(o.error_message)
            except Exception:
                pass

        results.append({
            "order_id": o.order_id,
            "symbol": o.symbol,
            "side": o.side,
            "position": o.position,
            "volume": o.volume,
            "price": o.price,
            "broker": meta.get("broker") or o.source.replace("mcp_", "").replace("console_", "").replace("action_exit_", "").upper(),
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "tag": meta.get("tag"),
            "window": meta.get("window"),
            "pnl_pct": meta.get("pnl_pct"),
            "is_profit": meta.get("is_profit"),
            "reason": meta.get("reason"),
            "pricing_rule": meta.get("pricing_rule"),
            "deviation_guard": meta.get("deviation_guard"),
            "account_no": meta.get("account_no")
        })
    return results


class ActionExitNLRequest(BaseModel):
    text: str
    broker: Optional[str] = None
    auto_schedule: bool = True


@router.post("/action-exit/natural-language")
async def execute_action_exit_from_text(payload: ActionExitNLRequest, db: AsyncSession = Depends(get_db)):
    """
    Parses natural language tactical action exit briefings, validates rules,
    auto-schedules orders for execution windows, and notifies channels.
    """
    from app.services.action_exit_service import action_exit_service
    res = await action_exit_service.evaluate_and_queue_action_exits(
        text=payload.text,
        db=db,
        broker_override=payload.broker,
        auto_schedule=payload.auto_schedule
    )
    return res


@router.post("/action-exit/{order_id}/dispatch-now")
async def dispatch_action_exit_now(order_id: str):
    """
    Bypasses waiting for tactical window and forces immediate execution of a scheduled action exit order.
    """
    from app.services.action_exit_dispatcher import action_exit_dispatcher
    res = await action_exit_dispatcher.dispatch_order_now(order_id)
    return res


@router.post("/hitl/{order_id}/confirm")
async def confirm_hitl_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """Confirms and schedules or dispatches the live order to the target broker."""
    import json
    from sqlalchemy import select
    from app.db.models import Order
    from app.brokers import broker_registry
    from app.brokers.base import OrderRequest

    stmt = select(Order).where(Order.order_id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "AWAITING_HITL_CONFIRMATION":
        return {"success": False, "message": f"Order is already in {order.status} state"}

    # Check if this is a timed tactical action exit order
    is_action_exit = order.source.startswith("action_exit_")
    meta = {}
    if order.error_message and order.error_message.strip().startswith("{"):
        try:
            meta = json.loads(order.error_message)
        except Exception:
            pass

    # If action exit with scheduled window, mark SCHEDULED
    if is_action_exit and meta.get("window"):
        order.status = "SCHEDULED"
        meta["approved"] = True
        meta["approved_at"] = datetime.now().isoformat()
        order.error_message = json.dumps(meta, ensure_ascii=False)
        await db.commit()

        try:
            from app.services.kdeconnect_service import kdeconnect_service
            title = f"⏰ [Action Exit Scheduled] {order.symbol}"
            msg = f"อนุมัติคำสั่งเรียบร้อย: {order.side} {order.volume:,} {order.symbol} @ ฿{order.price:.2f}\n(ตั้งเวลารอส่งช่วง Window: {meta.get('window')} พร้อม Deviation Guard)"
            await kdeconnect_service.send_critical_alert(title, msg)
        except Exception as e:
            logger.debug(f"KDE Connect alert error: {e}")

        return {
            "success": True,
            "order_id": order.order_id,
            "status": "SCHEDULED",
            "message": f"อนุมัติคำสั่ง {order.symbol} สำเร็จ เข้าสู่คิวตั้งเวลาส่งช่วง {meta.get('window')}"
        }

    # Otherwise direct live execution to broker
    broker_slug = order.source.replace("mcp_", "").replace("console_", "").replace("action_exit_", "").lower()
    target_broker = broker_registry.get(broker_slug)
    if not target_broker:
        target_broker = broker_registry.get("click2win")

    order_req = OrderRequest(
        symbol=order.symbol,
        side=order.side,
        position=order.position or "AUTO",
        volume=order.volume,
        price=order.price,
        pin=settings.CLICK2WIN_PIN if broker_slug == "click2win" else settings.TRADING_PIN
    )
    trade_res = await target_broker.place_order(order_req)
    if trade_res.success:
        raw_resp = getattr(trade_res, "raw_response", {}) or {}
        is_matched = raw_resp.get("is_matched", False)
        order.status = "FILLED" if is_matched else "SUBMITTED"
        order.broker_order_no = str(trade_res.order_id or "")
        try:
            from app.services.kdeconnect_service import kdeconnect_service
            pos_info = f" ({order.position})" if order.position else ""
            if is_matched:
                title = f"🎉 [Order Matched] {target_broker.metadata.name.upper()}"
                msg = f"คำสั่งจับคู่สำเร็จ (MATCHED)!: {order.side}{pos_info} {order.volume} {order.symbol} @ ฿{order.price:.2f}\n(Broker Order: {order.broker_order_no})"
            else:
                title = f"✅ [Order Submitted] {target_broker.metadata.name.upper()}"
                msg = f"ส่งคำสั่งเข้าตลาดสำเร็จ (Queuing): {order.side}{pos_info} {order.volume} {order.symbol} @ ฿{order.price:.2f}\n(Broker Order: {order.broker_order_no})"
            await kdeconnect_service.send_critical_alert(title, msg)
        except Exception as e:
            logger.debug(f"KDE Connect alert error: {e}")
    else:
        order.status = "REJECTED"
        order.error_message = trade_res.message
    await db.commit()

    return {
        "success": trade_res.success,
        "order_id": order.order_id,
        "status": order.status,
        "message": trade_res.message
    }


@router.post("/hitl/{order_id}/reject")
async def reject_hitl_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """Rejects/Cancels an order proposal in AWAITING_HITL_CONFIRMATION status."""
    from sqlalchemy import select
    from app.db.models import Order

    stmt = select(Order).where(Order.order_id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = "CANCELLED"
    order.error_message = "Rejected by user at /console HITL gate"
    await db.commit()
    return {"success": True, "order_id": order.order_id, "status": "CANCELLED"}


@router.post("/{order_id}/cancel-broker")
async def cancel_broker_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """Cancels an active/submitted order directly on the target broker via Playwright / API."""
    from sqlalchemy import select
    from app.db.models import Order
    from app.brokers import broker_registry

    stmt = select(Order).where(Order.order_id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    broker_slug = order.source.replace("mcp_", "").replace("console_", "").lower()
    target_broker = broker_registry.get(broker_slug) or broker_registry.get("click2win")

    broker_no = order.broker_order_no or order.order_id
    success = await target_broker.cancel_order(
        order_id=broker_no,
        symbol=order.symbol
    )
    if success:
        order.status = "CANCELLED"
        order.error_message = f"Cancelled on {target_broker.metadata.name}"
        try:
            from app.services.kdeconnect_service import kdeconnect_service
            title = f"🛑 [Order Cancelled] {target_broker.metadata.name.upper()}"
            msg = f"ยกเลิกคำสั่งสำเร็จ: {order.side} {order.volume} {order.symbol} @ ฿{order.price:.2f} ({broker_no})"
            await kdeconnect_service.send_critical_alert(title, msg)
        except Exception:
            pass
    await db.commit()
    return {
        "success": success,
        "order_id": order.order_id,
        "broker_order_no": broker_no,
        "status": order.status,
        "message": f"Order {broker_no} cancelled on {target_broker.metadata.name}" if success else f"Failed to cancel {broker_no}"
    }

