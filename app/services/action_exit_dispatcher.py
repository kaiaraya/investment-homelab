"""
Pillar 6 Tactical Action Exit Dispatcher Daemon.
================================================
Background worker that:
1. Runs Daily 09:45 AM Pre-Flight Session Health Check on Krungsri TradeMan (Account 3024959 Margin)
   and triggers proactive OTP alerts to KDE Connect before 10:00 AM market open.
2. Continuously monitors SCHEDULED action exit orders and dispatches them automatically when
   the tactical execution window arrives (Win: 10:00-10:30 + jitter, Loss: 10:30-12:00 + jitter).
3. Follows Best Offer 1 for SELL (Long exit) and Best Bid 1 for COVER (Short exit) to queue at the
   front of the market line, supporting both SELL and COVER.
4. Continuously polls Order Status until matched (Open -> Matched) and pushes completion alerts.
"""

import asyncio
import json
import logging
import random
from datetime import datetime, time, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import select
from app.core.config import settings
from app.db.models import Order
from app.db.session import AsyncSessionLocal
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.services.kdeconnect_service import kdeconnect_service
from app.core.sse_broadcaster import sse_broadcaster

logger = logging.getLogger("ActionExitDispatcher")


class ActionExitDispatcher:
    def __init__(self, check_interval_seconds: int = 15):
        self.check_interval_seconds = check_interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_preflight_date: Optional[str] = None
        self._last_negotiate_round1_date: Optional[str] = None
        self._last_negotiate_round2_date: Optional[str] = None
        self._last_poll_time: float = 0.0
        self._lock = asyncio.Lock()

    def start(self) -> None:
        """Starts the background action exit dispatcher loop."""
        if self._running:
            logger.warning("[ActionExitDispatcher] Already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        logger.info("[ActionExitDispatcher] Started background daemon (15s check loop).")

    async def stop(self) -> None:
        """Stops the background action exit dispatcher loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[ActionExitDispatcher] Stopped background daemon.")

    async def _main_loop(self) -> None:
        """Main periodic polling loop."""
        while self._running:
            try:
                now_bkk = datetime.now()

                # 1. Daily 09:45 AM Pre-Flight Session Health Check
                await self._check_preflight_session(now_bkk)

                # 2. Dispatch Scheduled Action Exit Orders
                await self._dispatch_scheduled_orders(now_bkk)

                # 3. Autonomous Price Negotiation Rounds (11:00 AM & 15:30 PM)
                await self._check_price_negotiation_rounds(now_bkk)

                # 4. Poll Open Orders for Matched Status (every 60s)
                now_ts = asyncio.get_event_loop().time()
                if now_ts - self._last_poll_time >= 60.0:
                    self._last_poll_time = now_ts
                    await self._poll_matched_orders(now_bkk)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ActionExitDispatcher] Loop error: {e}", exc_info=True)

            await asyncio.sleep(self.check_interval_seconds)

    async def _check_preflight_session(self, now_bkk: datetime) -> None:
        """
        Runs pre-flight authentication check at 09:45 AM.
        Verifies TradeMan session for Account 3024959 (Margin).
        If session expired, initiates login and alerts phone if OTP is needed.
        """
        today_str = now_bkk.strftime("%Y-%m-%d")
        
        # Check window: 09:45 - 09:55 AM on weekdays (Monday=0 to Friday=4)
        is_weekday = now_bkk.weekday() < 5
        is_time_window = (now_bkk.hour == 9 and 45 <= now_bkk.minute <= 55)

        if not (is_weekday and is_time_window):
            return

        if self._last_preflight_date == today_str:
            return  # Already run today

        logger.info(f"[ActionExitDispatcher] Running 09:45 Pre-Flight Session Check for {today_str}...")
        self._last_preflight_date = today_str

        try:
            # 1. Check if auth_driver is authenticated
            is_valid = await auth_driver.check_session_validity()
            if not is_valid:
                logger.warning("[ActionExitDispatcher] Session invalid or expired at 09:45. Initiating proactive login...")
                login_res = await auth_driver.login(force_fresh=True)
                if login_res.requires_otp:
                    title = "🔐 [TradeMan Action Required] OTP Needed for 10:00 Market Open"
                    msg = (
                        f"ระบบเตรียมความพร้อม Action Exit ประจำเช้า:\n"
                        f"Krungsri TradeMan ต้องการ OTP เพื่อเข้าสู่ระบบ (Ref: {login_res.ref_code or 'N/A'})\n"
                        f"👉 กรุณากรอก OTP หรือส่งเข้า Telegram/Console ด่วนก่อน 10:00 น.!"
                    )
                    await kdeconnect_service.send_critical_alert(title, msg)
                    return
                elif not login_res.success:
                    title = "⚠️ [TradeMan Pre-Flight Alert] Login Failed"
                    msg = f"ไม่สามารถต่ออายุ Session TradeMan ได้: {login_res.message}"
                    await kdeconnect_service.send_critical_alert(title, msg)
                    return

            # Session is valid and healthy!
            title = "✅ [TradeMan Pre-Flight 09:45] Session Ready"
            msg = (
                f"Session Krungsri TradeMan (Account 3024959 Margin) มีสถานะสมบูรณ์พร้อมยิงคำสั่ง Action Exit\n"
                f"ตลาดเปิด 10:00 น. ระบบจะทำการยิงคำสั่งตามเวลาที่กำหนดโดยอัตโนมัติ"
            )
            await kdeconnect_service.send_critical_alert(title, msg)
            logger.info("[ActionExitDispatcher] 09:45 Pre-Flight Check passed successfully.")

        except Exception as e:
            logger.error(f"[ActionExitDispatcher] Pre-flight check error: {e}")

    async def _check_price_negotiation_rounds(self, now_bkk: datetime) -> None:
        """
        Pillar 6 Tactical Price Negotiation Autonomous Daemon:
        Runs at 11:00 AM (Round 1) and 15:30 PM (Round 2) on weekdays.
        Evaluates open unmatched orders on Liberator and Krungsri, and auto-negotiates prices.
        """
        today_str = now_bkk.strftime("%Y-%m-%d")
        is_weekday = now_bkk.weekday() < 5
        if not is_weekday:
            return

        is_round_1 = (now_bkk.hour == 11 and 0 <= now_bkk.minute <= 5)
        is_round_2 = (now_bkk.hour == 15 and 30 <= now_bkk.minute <= 35)

        if is_round_1 and self._last_negotiate_round1_date != today_str:
            self._last_negotiate_round1_date = today_str
            logger.info(f"[ActionExitDispatcher] 🤖 Triggering 11:00 AM Price Negotiation Round 1 for {today_str}...")
            await self._run_autonomous_negotiation(round_label="Round 1 (11:00 น.)")

        elif is_round_2 and self._last_negotiate_round2_date != today_str:
            self._last_negotiate_round2_date = today_str
            logger.info(f"[ActionExitDispatcher] 🤖 Triggering 15:30 PM Price Negotiation Round 2 for {today_str}...")
            await self._run_autonomous_negotiation(round_label="Round 2 (15:30 น.)")

    async def _run_autonomous_negotiation(self, round_label: str) -> None:
        try:
            from app.brokers.liberator.driver import liberator_driver
            neg_res = await liberator_driver.negotiate_price()
            if neg_res.get("action") == "AMENDED_IN_PLACE":
                title = f"🎯 [Auto ต่อราคา {round_label}] Liberator"
                msg = (
                    f"ทำการต่อราคาคำสั่งซื้อขายอัตโนมัติสำเร็จ (แก้ในที่ ไม่เสียคิว):\n"
                    f"{neg_res.get('message')}\n"
                    f"• Order number คงเดิม: #{neg_res.get('order_no')} ({neg_res.get('symbol')})\n"
                    f"• ราคา: ฿{float(neg_res.get('old_price') or 0):.2f} -> ฿{float(neg_res.get('new_price') or 0):.2f}\n"
                    f"👉 ใช้ปุ่ม Change ของโบรกเกอร์ — ไม่มีการส่งคำสั่งใหม่"
                )
                await kdeconnect_service.send_critical_alert(title, msg)
            elif neg_res.get("action") == "NONE":
                logger.info(
                    f"[ActionExitDispatcher] Negotiation {round_label}: "
                    f"{neg_res.get('message', 'no amend needed')}"
                )
            elif neg_res.get("open_count") == 0:
                logger.info(f"[ActionExitDispatcher] Negotiation {round_label}: All Liberator orders already filled (0 open).")
        except Exception as e:
            logger.error(f"[ActionExitDispatcher] Autonomous negotiation error: {e}")

    async def _dispatch_scheduled_orders(self, now_bkk: datetime) -> None:
        """
        Finds all orders in status 'SCHEDULED' and checks if their target execution time has arrived.
        """
        async with AsyncSessionLocal() as db:
            stmt = select(Order).where(
                Order.status == "SCHEDULED",
                Order.source.like("action_exit_%")
            )
            result = await db.execute(stmt)
            scheduled_orders = result.scalars().all()

        if not scheduled_orders:
            return

        for order in scheduled_orders:
            try:
                meta = {}
                if order.error_message and order.error_message.strip().startswith("{"):
                    meta = json.loads(order.error_message)

                # Determine target scheduled time
                target_time_str = meta.get("scheduled_time")
                if not target_time_str:
                    # Calculate from window_start + jitter_minutes
                    window_start = meta.get("window_start", "10:00")
                    jitter = int(meta.get("jitter_minutes", 0))
                    try:
                        sh, sm = map(int, window_start.split(":"))
                        target_dt = now_bkk.replace(hour=sh, minute=sm, second=0, microsecond=0) + timedelta(minutes=jitter)
                        target_time_str = target_dt.strftime("%H:%M")
                        meta["scheduled_time"] = target_time_str
                    except Exception:
                        target_time_str = "10:00"

                target_h, target_m = map(int, target_time_str.split(":"))
                target_time = time(target_h, target_m, 0)

                # Check if current time has reached or passed target time
                # Market sessions in SET: Morning session (10:00 - 12:30), Afternoon (14:30 - 16:30)
                if now_bkk.time() >= target_time:
                    logger.info(
                        f"[ActionExitDispatcher] 🎯 Firing Scheduled Order {order.order_id}: "
                        f"{order.side} {order.volume:,} {order.symbol} @ ฿{order.price:.2f} "
                        f"(Target Time: {target_time_str}, Current: {now_bkk.strftime('%H:%M:%S')})"
                    )
                    await self._execute_action_exit_order(order, meta)

            except Exception as e:
                logger.error(f"[ActionExitDispatcher] Error evaluating order {order.order_id}: {e}")

    async def _execute_action_exit_order(self, order: Order, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an action exit order on Krungsri TradeMan Margin (Account 3024959).
        Enforces user decision: Follow Best Offer 1 for SELL, Best Bid 1 for COVER.
        """
        async with self._lock:
            # Re-verify status to prevent race conditions
            async with AsyncSessionLocal() as db:
                curr_order = await db.get(Order, order.order_id)
                if not curr_order or curr_order.status != "SCHEDULED":
                    return {"success": False, "message": "Order is no longer SCHEDULED"}

                curr_order.status = "EXECUTING"
                await db.commit()

            symbol = order.symbol.upper()
            side = order.side.upper()
            volume = order.volume
            briefing_price = order.price
            account_no = meta.get("account_no", "3024959")
            pin = getattr(settings, "KRUNGSRI_PIN", "") or settings.TRADING_PIN

            # 1. Pricing Strategy:
            # User Decision: Option 3 -> Follow Best Offer 1 for SELL / Best Bid 1 for COVER to queue at front.
            target_price = briefing_price
            market_quote = None
            try:
                market_quote = await trademan_driver.get_market_bid_offer(symbol)
                if side in ["SELL", "SHORT"]:
                    # Follow Best Offer 1 to queue at best asking price
                    best_offer = market_quote.get("offer_1")
                    if best_offer and best_offer > 0:
                        target_price = float(best_offer)
                        logger.info(f"[ActionExitDispatcher] Follow Best Offer 1 for SELL {symbol}: ฿{target_price:.2f} (Briefing: ฿{briefing_price:.2f})")
                elif side in ["BUY", "COVER"]:
                    # Follow Best Bid 1 to queue at best bidding price
                    best_bid = market_quote.get("bid_1")
                    if best_bid and best_bid > 0:
                        target_price = float(best_bid)
                        logger.info(f"[ActionExitDispatcher] Follow Best Bid 1 for COVER {symbol}: ฿{target_price:.2f} (Briefing: ฿{briefing_price:.2f})")
            except Exception as q_err:
                logger.warning(f"[ActionExitDispatcher] Could not fetch market quote for {symbol}: {q_err}. Using briefing price ฿{briefing_price:.2f}")

            # 2. Execute via Live Driver (Multi-Broker: Krungsri vs Liberator)
            target_broker = meta.get("broker", "KRUNGSRI").upper()
            if target_broker == "LIBERATOR" or "liberator" in str(order.source).lower():
                from app.brokers.liberator.driver import liberator_driver
                logger.info(f"[ActionExitDispatcher] Calling liberator_driver.execute_order for {side} {volume:,} {symbol} @ ฿{target_price:.2f}...")
                res = await liberator_driver.execute_order(
                    symbol=symbol,
                    side=side,
                    volume=volume,
                    price=target_price,
                    pin=pin or getattr(settings, "LIBERATOR_PIN", ""),
                    account_no=account_no or getattr(settings, "LIBERATOR_USERNAME", "7055938")
                )
            else:
                logger.info(f"[ActionExitDispatcher] Calling trademan_driver.execute_order for {side} {volume:,} {symbol} @ ฿{target_price:.2f}...")
                res = await trademan_driver.execute_order(
                    symbol=symbol,
                    side=side,
                    volume=volume,
                    price=target_price,
                    pin=pin,
                    account_no=account_no
                )

            # 3. Update Database Record
            async with AsyncSessionLocal() as db:
                db_order = await db.get(Order, order.order_id)
                if not db_order:
                    return res

                if res.get("success", False):
                    broker_order_no = res.get("broker_order_no") or f"KSS-{int(datetime.now().timestamp())}"
                    status = res.get("status", "OPEN")
                    db_order.status = "MATCHED" if status == "MATCHED" else "OPEN"
                    db_order.broker_order_no = str(broker_order_no)
                    db_order.price = target_price
                    meta["executed_at"] = datetime.now().isoformat()
                    meta["executed_price"] = target_price
                    meta["market_quote"] = market_quote
                    meta["broker_order_no"] = broker_order_no
                    db_order.error_message = json.dumps(meta, ensure_ascii=False)
                    await db.commit()

                    # Push Immediate KDE Connect Notification
                    try:
                        status_label = "จับคู่สำเร็จ (MATCHED)" if status == "MATCHED" else "เข้าคิวเรียบร้อย (OPEN / Queued)"
                        title = f"🚀 [Action Exit Auto-Traded] {symbol} {side}"
                        msg = (
                            f"คำสั่งส่งเข้าตลาด Krungsri สำเร็จ:\n"
                            f"• {side} {volume:,} {symbol} @ ฿{target_price:.2f}\n"
                            f"• บัญชี: {account_no} (Margin)\n"
                            f"• สถานะ: {status_label}\n"
                            f"• Broker Order: {broker_order_no}"
                        )
                        await kdeconnect_service.send_critical_alert(title, msg)
                    except Exception as notif_err:
                        logger.debug(f"KDE notification error: {notif_err}")

                    # Broadcast SSE update
                    try:
                        await sse_broadcaster.broadcast("action_exit_executed", {
                            "order_id": db_order.order_id,
                            "symbol": symbol,
                            "side": side,
                            "volume": volume,
                            "price": target_price,
                            "status": db_order.status,
                            "broker_order_no": broker_order_no
                        })
                    except Exception:
                        pass

                    logger.info(f"[ActionExitDispatcher] Successfully executed {symbol}: status={db_order.status}, order_no={broker_order_no}")
                else:
                    err_msg = res.get("error", "Unknown execution error")
                    db_order.status = "FAILED"
                    meta["failed_at"] = datetime.now().isoformat()
                    meta["failure_reason"] = err_msg
                    db_order.error_message = json.dumps(meta, ensure_ascii=False)
                    await db.commit()

                    try:
                        title = f"❌ [Action Exit FAILED] {symbol} {side}"
                        msg = f"ส่งคำสั่ง {side} {volume:,} {symbol} ล้มเหลว:\n{err_msg}\n👉 ตรวจสอบในหน้า /console"
                        await kdeconnect_service.send_critical_alert(title, msg)
                    except Exception:
                        pass

                    logger.error(f"[ActionExitDispatcher] Execution failed for {symbol}: {err_msg}")

            return res

    async def _poll_matched_orders(self, now_bkk: datetime) -> None:
        """
        Continuously polls TradeMan order status for OPEN orders.
        Detects transitions from OPEN (O) -> MATCHED (M) and triggers celebration notifications.
        """
        async with AsyncSessionLocal() as db:
            stmt = select(Order).where(
                Order.status.in_(["OPEN", "SUBMITTED"]),
                Order.source.like("action_exit_%")
            )
            result = await db.execute(stmt)
            open_orders = result.scalars().all()

        if not open_orders:
            return

        logger.debug(f"[ActionExitDispatcher] Polling status for {len(open_orders)} open action exit orders...")
        try:
            unmatched = await trademan_driver.scrape_unmatched_orders()
            unmatched_symbols = {item.get("symbol", "").upper() for item in unmatched}

            for o in open_orders:
                sym = o.symbol.upper()
                # If symbol is no longer in unmatched/open list, it has been filled (MATCHED)!
                if sym not in unmatched_symbols:
                    logger.info(f"[ActionExitDispatcher] 🎉 Order for {sym} is no longer in open queue -> MATCHED!")
                    async with AsyncSessionLocal() as db:
                        curr = await db.get(Order, o.order_id)
                        if curr and curr.status in ["OPEN", "SUBMITTED"]:
                            curr.status = "MATCHED"
                            meta = {}
                            if curr.error_message and curr.error_message.strip().startswith("{"):
                                meta = json.loads(curr.error_message)
                            meta["matched_at"] = datetime.now().isoformat()
                            curr.error_message = json.dumps(meta, ensure_ascii=False)
                            await db.commit()

                            title = f"🎉 [Action Exit MATCHED] {sym}"
                            msg = (
                                f"คำสั่งจับคู่สำเร็จเรียบร้อย (100% MATCHED):\n"
                                f"• {curr.side} {curr.volume:,} {sym} @ ฿{curr.price:.2f}\n"
                                f"• พอร์ต: Margin 3024959\n"
                                f"• Broker Order: {curr.broker_order_no}\n"
                                f"👉 ล็อคกำไร / เคลียร์ความเสี่ยงสำเร็จตามแผนยุทธวิธี!"
                            )
                            await kdeconnect_service.send_critical_alert(title, msg)

                            try:
                                await sse_broadcaster.broadcast("action_exit_matched", {
                                    "order_id": curr.order_id,
                                    "symbol": sym,
                                    "side": curr.side,
                                    "volume": curr.volume,
                                    "price": curr.price,
                                    "status": "MATCHED"
                                })
                            except Exception:
                                pass

        except Exception as e:
            logger.debug(f"[ActionExitDispatcher] Poll matched orders error: {e}")

    async def dispatch_order_now(self, order_id: str) -> Dict[str, Any]:
        """
        Manual bypass / instant trigger: Immediately executes a scheduled order without waiting for the time window.
        """
        async with AsyncSessionLocal() as db:
            order = await db.get(Order, order_id)
            if not order:
                return {"success": False, "message": "Order not found"}
            if order.status not in ["SCHEDULED", "AWAITING_HITL_CONFIRMATION"]:
                return {"success": False, "message": f"Cannot dispatch order in {order.status} state"}

            meta = {}
            if order.error_message and order.error_message.strip().startswith("{"):
                meta = json.loads(order.error_message)

            order.status = "SCHEDULED"
            await db.commit()

        logger.info(f"[ActionExitDispatcher] Instant dispatch triggered for order {order_id} ({order.symbol})")
        return await self._execute_action_exit_order(order, meta)


# Global singleton daemon instance
action_exit_dispatcher = ActionExitDispatcher()
