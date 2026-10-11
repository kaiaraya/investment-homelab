import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.browser.trademan_driver import trademan_driver
from app.core.config import settings
from app.core.events import event_bus
from app.db.models import Order, SessionLog, SBLBorrowLot
from app.db.session import AsyncSessionLocal
from app.schemas.order import OrderCreate, OrderSide, OrderStatus
from app.services.trade_dispatcher import trade_dispatcher
from app.services.validator import validator

logger = logging.getLogger(__name__)


class TradeCenterService:
    """
    3.3 Trade Center (Operates 10:00 - 17:30 Bangkok time)
    Central execution hub enforcing:
    1. Broker & SET Regulations (Odd-lot % 100 == 0, Tick sizes, SBL check prior to Short, Uptick rule).
    2. Interactive LINE Confirmation Cards before submitting orders.
    3. Dual Engine Execution (TEST via Virtual Simulator vs LIVE via Playwright TradeManDriver).
    """

    def __init__(self):
        self._pending_batches: Dict[str, Dict[str, Any]] = {}

    def prepare_batch_approval_card(
        self,
        immediate_orders: list,
        watchlist_triggers: list,
        warnings: list
    ) -> Dict[str, Any]:
        """
        Creates a consolidated Batch Review Flex Card for Daily Orders.
        """
        batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        mode_badge = trade_dispatcher.get_mode_badge()
        mode_color = trade_dispatcher.get_mode_color()

        valid_immediates = [o for o in immediate_orders if getattr(o, "is_valid_lot", True)]
        total_val = sum(o.volume * o.price for o in valid_immediates)

        card_title = f"📋 สรุปคำสั่ง Daily Order ประจำวัน"
        card_text = (
            f"โหมดการทำงาน: {mode_badge}\n"
            f"• คำสั่งส่งทันที (Immediate): {len(valid_immediates)} รายการ (มูลค่า ฿{total_val:,.2f})\n"
            f"• คำสั่งเฝ้าระวัง (Triggers): {len(watchlist_triggers)} รายการ\n"
            f"• รายการไม่ผ่านเกณฑ์: {len(warnings)} รายการ"
        )

        orders_payload_data = [
            {"symbol": o.symbol, "side": o.side.value if hasattr(o.side, "value") else str(o.side), "volume": o.volume, "price": o.price}
            for o in valid_immediates
        ]

        self._pending_batches[batch_id] = {
            "batch_id": batch_id,
            "orders": orders_payload_data,
            "triggers": watchlist_triggers,
            "warnings": warnings,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        card = {
            "type": "BATCH_REVIEW_CARD",
            "batch_id": batch_id,
            "title": card_title,
            "text": card_text,
            "badge": mode_badge,
            "badge_color": mode_color,
            "immediate_orders": orders_payload_data,
            "triggers_count": len(watchlist_triggers),
            "warnings": warnings,
            "confirm_payload": f"action=batch_approve&batch_id={batch_id}",
            "cancel_payload": f"action=batch_cancel&batch_id={batch_id}"
        }
        return {"batch_id": batch_id, "card": card}

    async def execute_batch_orders(
        self,
        db: AsyncSession,
        batch_id: str
    ) -> Dict[str, Any]:
        """
        Executes all valid immediate orders in an approved batch.
        """
        batch_data = self._pending_batches.get(batch_id)
        if not batch_data:
            return {"success": False, "error": f"Batch {batch_id} not found or expired"}

        orders_to_run = batch_data.get("orders", [])
        results = []

        logger.info(f"[TradeCenter] Executing batch {batch_id} with {len(orders_to_run)} orders (Mode: {trade_dispatcher.current_mode})")

        for ord_info in orders_to_run:
            sym = ord_info["symbol"]
            side = ord_info["side"]
            vol = ord_info["volume"]
            px = ord_info["price"]

            res = await self.execute_confirmed_order(
                db=db,
                symbol=sym,
                side=side,
                volume=vol,
                price=px,
                source=f"line_batch_{batch_id}"
            )
            results.append(res)

        # Clear batch from cache
        del self._pending_batches[batch_id]

        summary_msg = f"🚀 ดำเนินการยิงคำสั่ง Daily Order ครบ {len(results)} รายการ (โหมด: {trade_dispatcher.get_mode_badge()}):\n"
        for r in results:
            icon = "✅" if r["success"] else "❌"
            summary_msg += f"{icon} {r.get('symbol', '')} ({r.get('side', '')}) {r.get('volume', 0):,} หุ้น @ ฿{r.get('price', 0):.2f} -> {r.get('status')}\n"

        await event_bus.publish_notification({
            "type": "BATCH_EXECUTION_COMPLETED",
            "text": summary_msg,
            "batch_id": batch_id,
            "results": results
        })

        return {
            "success": True,
            "batch_id": batch_id,
            "processed": len(results),
            "results": results,
            "summary_message": summary_msg
        }

    async def prepare_order_approval(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        source: str = "line_chat",
        last_trade_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Validates order against broker rules and prepares a LINE confirmation card.
        Does NOT execute immediately until user approves.
        """
        symbol = symbol.upper()
        side = side.upper()

        # Pre-trade validation
        ok, err = validator.validate_all(
            symbol=symbol,
            side=side,
            volume=volume,
            price=price,
            record_idempotency=False,
            last_trade_price=last_trade_price
        )
        if not ok:
            logger.warning(f"Trade Center rejected pre-order: {err}")
            return {
                "success": False,
                "status": "VALIDATION_FAILED",
                "error": err,
                "message": f"❌ คำสั่งไม่ผ่านเกณฑ์โบรกเกอร์: {err}"
            }

        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        total_thb = volume * price
        badge = trade_dispatcher.get_mode_badge()

        card = {
            "type": "TRADE_CONFIRMATION_CARD",
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": price,
            "total_thb": total_thb,
            "mode": trade_dispatcher.current_mode,
            "badge": badge,
            "title": f"ขอยืนยันคำสั่ง {side} {symbol}",
            "text": (
                f"📋 รายละเอียดคำสั่ง:\n"
                f"• หุ้น: {symbol} ({side})\n"
                f"• จำนวน: {volume:,} หุ้น (Board lot OK)\n"
                f"• ราคา: ฿{price:.2f}\n"
                f"• มูลค่า: ฿{total_thb:,.2f}\n"
                f"• โหมด: {badge}\n\n"
                f"กรุณากดยืนยันเพื่อดำเนินการส่งคำสั่ง"
            ),
            "confirm_payload": f"action=confirm_order&order_id={order_id}&symbol={symbol}&side={side}&volume={volume}&price={price}",
            "cancel_payload": f"action=cancel_order&order_id={order_id}"
        }

        await event_bus.publish_notification(card)
        return {"success": True, "status": "AWAITING_USER_APPROVAL", "card": card}

    async def execute_confirmed_order(
        self,
        db: AsyncSession,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        order_id: Optional[str] = None,
        source: str = "line_user_confirmed"
    ) -> Dict[str, Any]:
        """
        Executes order via TradeDispatcher (routes to Virtual Simulator or Live Driver).
        """
        order_id = order_id or f"ORD-{uuid.uuid4().hex[:8].upper()}"
        symbol = symbol.upper()
        side = side.upper()

        logger.info(f"Executing confirmed order: {side} {volume} {symbol} @ ฿{price:.2f} (Mode: {trade_dispatcher.current_mode})")

        # Dispatch via central router
        exec_res = await trade_dispatcher.dispatch_order(
            symbol=symbol,
            side=side,
            volume=volume,
            price=price
        )

        broker_order_no = exec_res.get("broker_order_no")
        is_success = exec_res.get("success", False)
        status_val = exec_res.get("status", OrderStatus.SUBMITTED.value if is_success else OrderStatus.FAILED.value)
        err_msg = exec_res.get("error")
        badge = trade_dispatcher.get_mode_badge()

        # Record in SQLite orders table
        order_record = Order(
            order_id=order_id,
            broker_order_no=broker_order_no,
            symbol=symbol,
            side=side,
            volume=volume,
            price=price,
            status=status_val,
            error_message=err_msg,
            source=source
        )
        db.add(order_record)

        log = SessionLog(
            event_type="TRADE_CENTER_EXECUTED",
            details=f"Order {order_id}: {side} {volume} {symbol} @ ฿{price:.2f} -> {status_val} ({broker_order_no})"
        )
        db.add(log)
        await db.commit()

        # Send confirmation report to LINE
        report_msg = (
            f"{'✅ ส่งคำสั่งสำเร็จ' if is_success else '❌ ส่งคำสั่งล้มเหลว'}\n"
            f"• หุ้น: {symbol} ({side})\n"
            f"• จำนวน: {volume:,} หุ้น @ ฿{price:.2f}\n"
            f"• หมายเลขออเดอร์: {broker_order_no or 'N/A'}\n"
            f"• สถานะ: {status_val}"
        )
        if err_msg:
            report_msg += f"\n• สาเหตุ: {err_msg}"

        await event_bus.publish_notification({
            "type": "ORDER_EXECUTION_RESULT",
            "text": report_msg,
            "order_id": order_id,
            "success": is_success
        })

        return {
            "success": is_success,
            "order_id": order_id,
            "broker_order_no": broker_order_no,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": price,
            "status": status_val,
            "message": report_msg
        }

    async def _ensure_sbl_borrowed(self, db: AsyncSession, symbol: str, volume: int) -> Dict[str, Any]:
        """
        Ensures SBL shares exist before firing a Short sale.
        """
        stmt = select(SBLBorrowLot).where(
            SBLBorrowLot.symbol == symbol,
            SBLBorrowLot.remaining_qty >= volume,
            SBLBorrowLot.status == "ACTIVE"
        )
        res = await db.execute(stmt)
        lot = res.scalar_one_or_none()

        if lot:
            logger.info(f"Active SBL lot {lot.lot_id} available for {symbol} ({lot.remaining_qty} shares)")
            return {"success": True, "lot_id": lot.lot_id}

        # If not already borrowed, simulate/request SBL borrow
        logger.info(f"No existing SBL lot found for {symbol}. Requesting SBL borrow for {volume} shares...")
        borrow_tx = f"SBL-{int(datetime.now().timestamp())}"
        new_lot = SBLBorrowLot(
            lot_id=f"LOT-{borrow_tx}",
            broker_tx_id=borrow_tx,
            symbol=symbol,
            borrow_qty=volume,
            remaining_qty=volume,
            borrow_date=datetime.now().date(),
            status="ACTIVE"
        )
        db.add(new_lot)
        await db.commit()
        return {"success": True, "lot_id": new_lot.lot_id}


trade_center_service = TradeCenterService()
