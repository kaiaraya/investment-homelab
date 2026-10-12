import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.browser.trademan_simulator import virtual_simulator
from app.core.config import settings
from app.core.events import event_bus
from app.schemas.auth import OTPPayload, OTPSource
from app.ai.otp_agent import extract_otp_from_text
from app.services import otp_relay_registry
from datetime import date
from app.db.models import SessionLog, WatchlistTrigger, Position, SBLBorrowLot, Order
from app.services.conversation_state import conversation_state
from app.services.parser import signal_parser
from app.services.portfolio_overview_service import portfolio_overview_service
from app.services.price_negotiation_service import price_negotiation_service
from app.services.trade_center_service import trade_center_service
from app.services.trade_dispatcher import trade_dispatcher
from app.services.validator import validator
from app.services.decision_engine import decision_engine

logger = logging.getLogger(__name__)


class LineMessagingService:
    """
    Enhanced LINE Bot Service for AutoTrade Homelab:
    1. Relays SMS OTP responses
    2. Handles execution engine mode switching (MODE TEST / MODE LIVE <PIN>)
    3. Ingests rich Daily Strategy Reports (5.1, 5.2, 5.3) & performs Live Portfolio Reconciliation
    4. Issues Batch Review Cards & processes Interactive Postback actions
    5. Coordinates SBL return inquiries & Price Negotiation cards
    6. Communicates via Tailscale-backed real LINE Messaging API or local event bus
    """

    async def process_webhook_events(
        self,
        db: AsyncSession,
        events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        results = []

        for event in events:
            event_type = event.get("type")

            if event_type == "message":
                msg = event.get("message", {})
                if msg.get("type") == "text":
                    text = msg.get("text", "").strip()
                    res = await self._handle_text_message(db, text, event)
                    results.append(res)

            elif event_type == "postback":
                postback = event.get("postback", {})
                data = postback.get("data", "")
                res = await self._handle_postback(db, data, event)
                results.append(res)

        return results

    async def _handle_text_message(
        self,
        db: AsyncSession,
        text: str,
        raw_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        reply_token = raw_event.get("replyToken")

        # 0. Emergency Panic / Kill Switch Commands: "PANIC", "KILL", "STOP ALL", "RESET"
        clean_text = text.strip().upper()
        if clean_text in ("PANIC", "KILL", "STOP ALL", "EMERGENCY STOP"):
            from app.services.kill_switch_service import kill_switch_service
            res = await kill_switch_service.activate(reason=f"Triggered via LINE command: {text}", triggered_by="LINE_USER")
            reply_text = "🚨 [EMERGENCY KILL SWITCH ACTIVATED]\nระบบหยุดการเทรดอัตโนมัติทั้งหมดทันที และส่งคำขอยกเลิกออเดอร์ค้างทั้งหมดเรียบร้อยแล้ว\nพิมพ์ 'RESET' หรือ 'RESUME' เพื่อปลดล็อก"
            await self._send_reply(reply_token, reply_text)
            return {"status": "KILL_SWITCH_ACTIVATED", "details": res}

        if clean_text in ("RESET", "RESUME", "RESET KILL SWITCH", "RESUME TRADING"):
            from app.services.kill_switch_service import kill_switch_service
            res = await kill_switch_service.reset(authorized_by="LINE_USER")
            reply_text = "✅ [KILL SWITCH RESET]\nปลดล็อกระบบเรียบร้อยแล้ว ระบบกลับสู่สภาวะพร้อมทำงานตามปกติ"
            await self._send_reply(reply_token, reply_text)
            return {"status": "KILL_SWITCH_RESET", "details": res}

        # 1. Check for Mode Switch / Status Commands: "MODE", "MODE TEST", "MODE LIVE 123456"
        mode_match = re.match(r'^MODE(?:\s+(TEST|LIVE)(?:\s+(\w+))?)?$', text, re.IGNORECASE)
        if mode_match:
            target_mode, pin = mode_match.groups()
            if not target_mode:
                # Query current mode
                badge = trade_dispatcher.get_mode_badge()
                reply_text = f"ℹ️ สถานะโหมดปัจจุบัน: {badge}\n• พิมพ์ 'MODE TEST' เพื่อสลับสู่โหมดจำลอง\n• พิมพ์ 'MODE LIVE <PIN>' เพื่อสลับสู่โหมดส่งคำสั่งจริง"
                await self._send_reply(reply_token, reply_text)
                return {"status": "MODE_QUERY", "mode": trade_dispatcher.current_mode}
            else:
                switch_res = await trade_dispatcher.switch_mode(target_mode, pin=pin)
                msg = switch_res.get("message") or switch_res.get("error")
                await self._send_reply(reply_token, msg)
                return {"status": "MODE_SWITCH", "result": switch_res}

        # 2. Multi-Broker OTP Relay (Exact 6 digits, SMS text, or AI extraction)
        # LINE-RCA-010: attribute the OTP to the broker whose request is newest
        # (latest-request-wins — operator decision 2026-10-08). The relay is
        # broker-agnostic, so the row is ALWAYS persisted to the PRIMARY DB via
        # `otp_relay_registry` — never through the injected `db` (that session is
        # platform-aware: with TRADING_PLATFORM=CLICK2WIN it pointed at
        # investment_homelab_click2win.db and every driver, which polls the primary
        # DB, timed out despite the operator typing the code).
        otp_extract = await extract_otp_from_text(text)
        if otp_extract.otp:
            pending = await otp_relay_registry.resolve_pending_request()
            broker_tag = pending.broker if pending else None
            ref_code = (
                otp_extract.ref
                or (pending.ref if pending else None)
                or getattr(auth_driver, "current_ref", None)
            )
            if broker_tag is None and getattr(auth_driver, "current_ref", None):
                # Legacy path (request made before this upgrade): no marker exists, but
                # the Krungsri driver demonstrably published this ref while awaiting.
                broker_tag = "KRUNGSRI"
            broker_name = otp_relay_registry.broker_label(broker_tag)

            otp_payload = await event_bus.publish_otp(
                OTPPayload(
                    source=OTPSource.LINE_CHAT,
                    otp=otp_extract.otp,
                    ref=ref_code,
                    broker=broker_tag,
                )
            )

            # Cross-process hand-off → PRIMARY DB (what every driver polls).
            await otp_relay_registry.record_otp_received(
                otp_payload.otp, ref=ref_code, broker=broker_tag
            )

            target_label = broker_name or "โบรกเกอร์ที่รออยู่"
            reply_msg = (
                f"🔑 ได้รับรหัส OTP {otp_payload.masked_otp} แล้ว (Ref: {ref_code or 'N/A'})\n"
                f"กำลังยืนยันตัวตนกับ {target_label}..."
            )
            await self._send_reply(reply_token, reply_msg)
            return {
                "status": "OTP_RELAYED",
                "otp": otp_payload.otp,
                "ref": ref_code,
                "broker": broker_tag,
            }

        # 2.5 Per-user conversation state machine (multi-step flows — 2026-10-12)
        # Placement is deliberate: AFTER kill-switch / MODE / OTP so an emergency
        # stop always wins and an OTP is never swallowed by a flow slot, and BEFORE
        # every single-shot matcher so a flow answer is not re-interpreted as a new
        # command. With no `source.userId` (unit tests / internal callers) it
        # short-circuits to None and every matcher below behaves exactly as before.
        conv_res = await self._handle_conversation_turn(db, text, raw_event)
        if conv_res is not None:
            return conv_res

        # 2.8 Check for Action Center command: "action", "Action", "รออนุมัติ", "pending", "action center", "รายการรออนุมัติ"
        action_match = re.match(r'^(?:action|action\s+center|รออนุมัติ|pending|รายการรออนุมัติ)$', text.strip(), re.IGNORECASE)
        if action_match:
            from app.services.action_center_service import action_center_service
            card = action_center_service.build_action_center_card()
            await self._send_reply(reply_token, card)
            return {"status": "ACTION_CENTER_DISPLAYED", "pending_count": action_center_service.get_pending_count()}

        # 2.9 Check for SET / Market Query command: "set", "ตลาด", "ดัชนี", "market", "set index"
        set_match = re.match(r'^(?:set|ตลาด|ดัชนี|market|set\s+index)$', text.strip(), re.IGNORECASE)
        if set_match:
            from app.services.market_monitor_service import market_monitor_service
            res = await market_monitor_service.capture_and_report(period_label="LIVE")
            reply_text = (
                f"📈 ข้อมูลดัชนีตลาดล่าสุด:\n{res['summary_text']}\n\n"
                f"• High: {res['snapshot']['high']:,.2f}\n"
                f"• Low: {res['snapshot']['low']:,.2f}\n"
                f"• Vol: {res['snapshot']['volume_k']:,.0f}K\n"
                f"• Val: {res['snapshot']['value_mb']:,.0f}MB"
            )
            await self._send_reply(reply_token, reply_text)
            return {"status": "SET_QUERY_DISPLAYED", "snapshot": res["snapshot"]}

        # 2.10 Check for Schedule command: "schedule", "รอบเวลา", "ตารางเวลา", "timeline"
        sched_match = re.match(r'^(?:schedule|รอบเวลา|ตารางเวลา|timeline)$', text.strip(), re.IGNORECASE)
        if sched_match:
            from app.services.phase3_scheduler import phase3_scheduler
            pts_m = ", ".join(phase3_scheduler.morning_random_points)
            pts_a = ", ".join(phase3_scheduler.afternoon_random_points)
            reply_text = (
                "🗓️ ตาราง 8 ช่วงเวลาตลาดวันนี้:\n"
                "• 09:30-10:00: Pre-Market Login & 3.1 Overview\n"
                "• 10:00-10:30: Retail Open (มอนิเตอร์ SET)\n"
                f"• 10:30-12:00: Auto Trade รอบ 1 (สุ่ม: {pts_m})\n"
                "• 12:00-12:30: พักเที่ยง & เตือนคำสั่งค้าง\n"
                "• 14:00-14:30: Retail Open รอบบ่าย\n"
                f"• 14:30-16:00: Auto Trade รอบ 2 (สุ่ม: {pts_a})\n"
                "• 16:00-16:30: ปิดตลาด / ATC\n"
                "• 16:30-17:00: สรุปสิ้นวัน EOD Report"
            )
            await self._send_reply(reply_token, reply_text)
            return {"status": "SCHEDULE_DISPLAYED", "schedule": phase3_scheduler.get_daily_schedule()}

        # 3. Check for Daily Strategy / Trade Intent in Thai natural language or rich report
        is_daily_strategy = (
            any(k in text for k in ["5.1", "5.2", "5.3", "Hard Exit", "Climax TP", "Active Swings", "Weed-Out", "dailyorder", "ขาย", "คัท", "ทำกำไร", "ปิดสถานะ"])
            or ("SELL" in text.upper() and ("ตลาด" in text or "หุ้น" in text or "พอร์ต" in text))
            or (any(action in text.upper() for action in ["SELL", "BUY", "SHORT", "COVER"]) and any(c.isdigit() for c in text))
        )
        if is_daily_strategy:
            parsed = await signal_parser.parse_strategy_with_ai(text)
            if parsed.error_message:
                error_reply = (
                    f"⚠️ AI Ingestion ขัดข้อง:\n{parsed.error_message}\n\n"
                    "คำแนะนำ: กรุณาลองส่งข้อความใหม่อีกครั้ง หรือตรวจสอบ API Key / การเชื่อมต่อเครือข่าย"
                )
                await self._send_reply(reply_token, error_reply)
                return {"status": "AI_PARSE_ERROR", "error": parsed.error_message}

            if parsed.total_parsed > 0:
                # 1. Fetch live portfolio holdings
                if trade_dispatcher.is_live:
                    holdings_list = await trademan_driver.scrape_portfolio()
                else:
                    holdings_list = virtual_simulator.get_portfolio_snapshot()

                holdings_dict = {h["symbol"].upper(): h for h in holdings_list}

                # 2. Perform Live Portfolio Reconciliation with Auto-Clamping & Price Advantage
                reconciled_orders = validator.reconcile_orders_against_portfolio(
                    parsed.immediate_orders,
                    holdings_dict
                )
                valid_orders = [o for o in reconciled_orders if o.is_valid_lot and o.volume > 0]
                warnings = []
                for o in reconciled_orders:
                    if getattr(o, "clamped_from_volume", None):
                        warnings.append(f"⚠️ {o.symbol}: ปรับลดจาก {o.clamped_from_volume:,} เหลือ {o.volume:,} ตามพอร์ตจริง")
                    elif not o.is_valid_lot and o.validation_error:
                        warnings.append(f"❌ {o.symbol}: {o.validation_error}")

                # 3. Reconcile SHORT Hold Positions with SBL Borrow Lots in DB
                try:
                    stmt_sbl = select(SBLBorrowLot).where(SBLBorrowLot.status == "ACTIVE")
                    res_sbl = await db.execute(stmt_sbl)
                    active_sbl_lots = {s.symbol.upper(): s for s in res_sbl.scalars().all()}
                    for hp in parsed.hold_positions:
                        if getattr(hp, "position_type", "LONG") == "SHORT" and hp.symbol.upper() in active_sbl_lots:
                            lot = active_sbl_lots[hp.symbol.upper()]
                            days = (date.today() - lot.borrow_date).days if lot.borrow_date else 1
                            fee_rate = lot.borrow_fee_rate or 3.50
                            ref_px = lot.borrow_price or getattr(hp, "cost_price", 10.0) or 10.0
                            daily_fee = (lot.borrow_qty * ref_px * (fee_rate / 100.0)) / 365.0
                            accrued = daily_fee * max(days, 1)
                            sbl_tag = f"SBL {lot.borrow_qty:,} หุ้น (ถือ {days} วัน | ดอกเบี้ยสะสม ฿{accrued:,.2f})"
                            if hp.warning_note:
                                hp.warning_note += f" | {sbl_tag}"
                            else:
                                hp.warning_note = sbl_tag
                except Exception as e:
                    logger.warning(f"SBL reconciliation failed: {e}")

                # 4. Generate Batch Review ID & State
                batch_res = trade_center_service.prepare_batch_approval_card(
                    immediate_orders=valid_orders,
                    watchlist_triggers=parsed.watchlist_triggers,
                    warnings=warnings
                )

                # 5. Save watchlist triggers to DB and update Position TP/SL
                if parsed.watchlist_triggers:
                    for trg in parsed.watchlist_triggers:
                        wt = WatchlistTrigger(
                            symbol=trg.symbol,
                            action=trg.action,
                            volume=trg.volume,
                            condition_type=trg.condition,
                            trigger_price=trg.trigger_price,
                            status="ACTIVE",
                            notes=getattr(trg, "notes", "") or getattr(trg, "current_status", "")
                        )
                        db.add(wt)

                        # Update Position TP/SL in DB if position exists
                        try:
                            stmt_pos = select(Position).where(Position.symbol == trg.symbol)
                            res_pos = await db.execute(stmt_pos)
                            pos_obj = res_pos.scalar_one_or_none()
                            if pos_obj:
                                if trg.condition == "PRICE_BELOW":
                                    pos_obj.stop_loss_price = trg.trigger_price
                                elif trg.condition == "PRICE_ABOVE":
                                    pos_obj.take_profit_price = trg.trigger_price
                        except Exception as pe:
                            logger.warning(f"Failed to update TP/SL for position {trg.symbol}: {pe}")

                    await db.commit()

                # 6. Dispatch Carousel Flex Message to LINE (including Portfolio Overview Bubble)
                carousel_card = self.build_order_carousel_card(
                    orders=valid_orders,
                    batch_id=batch_res["batch_id"],
                    mode_badge=trade_dispatcher.get_mode_badge(),
                    strategy_summary=parsed.strategy_summary,
                    hold_positions=parsed.hold_positions,
                    watchlist_triggers=parsed.watchlist_triggers
                )
                await event_bus.publish_notification(carousel_card)
                await self._send_reply(reply_token, carousel_card)

                log = SessionLog(
                    event_type="LINE_DAILY_ORDER_INGESTED",
                    details=f"Batch {batch_res['batch_id']} ({parsed.source_method}): Parsed {parsed.total_parsed} items. Immediates: {len(valid_orders)}. Triggers: {len(parsed.watchlist_triggers)}. Hold: {len(parsed.hold_positions)}"
                )
                db.add(log)
                await db.commit()

                return {
                    "status": "DAILY_ORDER_BATCH_PREPARED",
                    "batch_id": batch_res["batch_id"],
                    "immediate_count": len(valid_orders),
                    "trigger_count": len(parsed.watchlist_triggers),
                    "hold_count": len(parsed.hold_positions),
                    "warnings": warnings,
                    "source_method": parsed.source_method
                }

        # 4. Check if user is setting TP/SL in Thai natural language (e.g. "CPALL TP 68 SL 62")
        if any(keyword in text.upper() for keyword in ["TP", "SL", "เป้า", "คัท", "STOP"]) and not is_daily_strategy:
            tpsl_res = await signal_parser.parse_multi_stock_tpsl(text)
            if tpsl_res and tpsl_res.items:
                applied = await portfolio_overview_service.apply_tpsl_items(db, tpsl_res.items)
                summary_lines = [f"✅ บันทึกระดับ TP/SL สำเร็จ ({len(applied)} รายการ):"]
                for it in applied:
                    tp_str = f"฿{it['tp']:.2f}" if it['tp'] else "ไม่ได้ตั้ง"
                    sl_str = f"฿{it['sl']:.2f}" if it['sl'] else "ไม่ได้ตั้ง"
                    summary_lines.append(f"• {it['symbol']} ({it['side']}): TP={tp_str} | SL={sl_str}")

                reply_msg = "\n".join(summary_lines)
                await event_bus.publish_notification({
                    "type": "TPSL_UPDATED",
                    "text": reply_msg,
                    "items": applied
                })
                await self._send_reply(reply_token, reply_msg)

                log = SessionLog(
                    event_type="LINE_TPSL_CONFIGURED",
                    details=f"Configured TP/SL for: {[a['symbol'] for a in applied]} (via {tpsl_res.source_method})"
                )
                db.add(log)
                await db.commit()
                return {"status": "TPSL_CONFIGURED", "items": applied}

        # 5. Check for direct trade commands: "BUY TRUE 1000 @ 13.20" or "SHORT AP 5000 @ 8.20"
        trade_match = re.search(r'\b(BUY|SELL|SHORT|COVER)\s+([A-Z0-9]+)\s+([0-9,]+)(?:\s*(?:@|ราคา)\s*([0-9.]+))?', text, re.IGNORECASE)
        if trade_match:
            side_str, symbol, vol_str, price_str = trade_match.groups()
            side = side_str.upper()
            symbol = symbol.upper()
            volume = int(vol_str.replace(",", ""))
            price = float(price_str) if price_str else 0.0

            if price > 0:
                card_res = await trade_center_service.prepare_order_approval(
                    symbol=symbol,
                    side=side,
                    volume=volume,
                    price=price,
                    source="line_command"
                )
                if card_res.get("card"):
                    await self._send_reply(reply_token, card_res["card"]["text"])
                return {"status": "TRADE_APPROVAL_DISPATCHED", "result": card_res}

        # 6. Check if user sent a Close Position command (e.g. "Close AP" or "CLOSE HMPRO")
        close_match = re.match(r'^(?:close|sell)\s+([A-Z0-9]+)$', text, re.IGNORECASE)
        if close_match:
            symbol = close_match.group(1).upper()
            cmd_data = {
                "source": "line_chat",
                "command": "CLOSE_POSITION",
                "symbol": symbol
            }
            await event_bus.publish_command(cmd_data)

            log = SessionLog(
                event_type="LINE_COMMAND_RECEIVED",
                details=f"Close command received for {symbol}"
            )
            db.add(log)
            await db.commit()
            reply_txt = f"⚡ ได้รับคำสั่งปิดสถานะ {symbol} เรียบร้อยแล้ว กำลังเตรียมส่งคำสั่ง..."
            await self._send_reply(reply_token, reply_txt)
            return {"status": "COMMAND_DISPATCHED", "action": "CLOSE_POSITION", "symbol": symbol}

        return {"status": "IGNORED", "text": text}

    # ------------------------------------------------------------------ #
    # Per-user conversation state machine (multi-step flows — 2026-10-12)
    # Engine + flow specs live in `app/services/conversation_state.py`
    # (see `docs/handoff/TASK-line-conversation-state.md`).
    # ------------------------------------------------------------------ #
    async def _handle_conversation_turn(
        self,
        db: AsyncSession,
        text: str,
        raw_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Drive the per-user FSM for one inbound text message.

        Returns a result dict when the machine consumed the message, or ``None`` so
        the single-shot command chain can continue (idle behaviour is unchanged).

        Rules
        -----
        * key = ``source.userId`` — without it (internal callers, legacy events,
          LINE "verify" pings) the machine is skipped entirely;
        * authorization gate = `conversation_state.is_authorized()` (Decision A):
          simulation OR the 1:1 chat with the OA OR the configured private group.
          An unauthorized sender never creates state;
        * an active flow owns the message: an unparseable answer re-prompts without
          advancing (and refreshes the TTL); ``CANCEL`` abandons; ``RESTART`` resets.
        """
        source = raw_event.get("source") or {}
        user_id = source.get("userId")
        if not user_id:
            return None

        reply_token = raw_event.get("replyToken")
        source_type = source.get("type")
        group_id = source.get("groupId")

        if not conversation_state.is_authorized(user_id, source_type=source_type, group_id=group_id):
            logger.warning("[Conversation] unauthorized sender denied (source_type=%s)", source_type)
            await self._send_reply(reply_token, "⛔ คำสั่งนี้สำหรับผู้ดูแลระบบเท่านั้น")
            return {"status": "CONVERSATION_UNAUTHORIZED", "user_id": user_id}

        state = conversation_state.get(user_id)

        # -- explicit cancel --------------------------------------------------
        if conversation_state.is_cancel(text):
            if state is None:
                return None  # no flow in progress → let the other handlers see it
            conversation_state.clear(user_id)
            await self._send_reply(reply_token, "🚫 ยกเลิกการทำงานที่ค้างอยู่แล้ว")
            return {"status": "CONVERSATION_CANCELLED", "flow": state.flow}

        # -- explicit restart of an active flow -------------------------------
        if state is not None and conversation_state.is_restart(text):
            flow_spec = conversation_state.get_flow(state.flow)
            conversation_state.clear(user_id)
            if flow_spec is not None:
                return await self._start_conversation_flow(reply_token, user_id, flow_spec, None, source)

        # -- idle: only an explicit trigger opens a flow ----------------------
        if state is None:
            matched = conversation_state.match_flow(text)
            if not matched:
                return None
            flow_spec, preselect = matched
            return await self._start_conversation_flow(reply_token, user_id, flow_spec, preselect, source)

        # -- active flow: parse the answer for the current step ---------------
        flow_spec = conversation_state.get_flow(state.flow)
        if flow_spec is None:
            conversation_state.clear(user_id)
            return None

        step_spec = flow_spec.step_spec(state.step)
        if step_spec is None:
            # unknown / terminal step seen outside the terminal handler → reset,
            # never guess what the user meant.
            conversation_state.clear(user_id)
            return None

        is_valid, value, error = step_spec.parse(text)
        if not is_valid:
            conversation_state.touch(user_id)  # keep the flow alive, do not advance
            await self._send_reply(reply_token, error or step_spec.prompt)
            return {"status": "CONVERSATION_RETRY", "flow": flow_spec.name, "step": step_spec.key}

        state = conversation_state.advance(user_id, **{step_spec.slot: value})

        next_spec = flow_spec.step_spec(state.step)
        if next_spec is not None:
            await self._send_reply(reply_token, next_spec.prompt)
            return {
                "status": "CONVERSATION_STEP",
                "flow": flow_spec.name,
                "step": state.step,
                "slots": dict(state.slots),
            }

        return await self._execute_conversation_terminal(db, state, reply_token)

    async def _start_conversation_flow(
        self,
        reply_token: Optional[str],
        user_id: str,
        flow_spec: Any,
        preselect: Optional[str],
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Open ``flow_spec`` for this user and prompt the opening step."""
        state = conversation_state.start_flow(
            user_id,
            flow_spec.name,
            preselect=preselect,
            chat_id=source.get("groupId"),
            chat_type=source.get("type") or "user",
        )
        step_spec = flow_spec.step_spec(state.step)
        prompt = step_spec.prompt if step_spec else "✅ พร้อมดำเนินการ"
        await self._send_reply(reply_token, prompt)
        return {
            "status": "CONVERSATION_STARTED",
            "flow": flow_spec.name,
            "step": state.step,
            "slots": dict(state.slots),
        }

    async def _execute_conversation_terminal(
        self,
        db: AsyncSession,
        state: Any,
        reply_token: Optional[str],
    ) -> Dict[str, Any]:
        """
        Run the terminal step of a completed flow, then clear the state.

        Every flow terminal step must be **read-only or routed through the existing
        validated services** — for orders that is `trade_center_service.prepare_order_approval()`
        (=> `validator.validate_all`) + the HITL gate. See the module docstring of
        `app/services/conversation_state.py`.
        """
        text_result: Optional[str] = None
        evidence: Dict[str, Any] = {}

        if state.flow == "symbol_query":
            text_result, evidence = await self._execute_symbol_query(
                db, state.slots.get("symbol", ""), state.slots.get("metric")
            )

        if not text_result:
            text_result = "⚠️ ไม่สามารถประมวลผลได้ กรุณาเริ่มใหม่ด้วยคำสั่งเดิม"
            evidence = {"error": "no_terminal_handler", "flow": state.flow}

        conversation_state.clear(state.user_id)
        await self._send_reply(reply_token, text_result)
        return {"status": "CONVERSATION_COMPLETED", "flow": state.flow, "result": evidence}

    async def _execute_symbol_query(
        self,
        db: AsyncSession,
        symbol: str,
        metric: Optional[str] = None,
    ) -> tuple:
        """
        Build the on-demand per-symbol report — **DB ONLY** (Anti-Mock / Invariant 7).

        Reads `positions`, `sbl_borrow_lots`, `watchlist_triggers` and the 5 most
        recent `orders` rows for the symbol. It deliberately does NOT scrape the
        broker: a chat lookup must never trigger a fresh login / SMS OTP. When the
        symbol is unknown it says so honestly instead of inventing numbers.

        Returns ``(reply_text, evidence_dict)``.
        """
        from sqlalchemy import desc

        sym = (symbol or "").strip().upper()
        if not sym:
            return "⚠️ ไม่พบสัญลักษณ์หุ้น กรุณาเริ่มใหม่", {"symbol": None, "data_found": False}

        pos = (await db.execute(select(Position).where(Position.symbol == sym))).scalar_one_or_none()
        sbl_lots = (await db.execute(
            select(SBLBorrowLot).where(
                SBLBorrowLot.symbol == sym, SBLBorrowLot.status == "ACTIVE"
            )
        )).scalars().all()
        triggers = (await db.execute(
            select(WatchlistTrigger).where(
                WatchlistTrigger.symbol == sym, WatchlistTrigger.status == "ACTIVE"
            )
        )).scalars().all()
        orders = (await db.execute(
            select(Order).where(Order.symbol == sym).order_by(desc(Order.created_at)).limit(5)
        )).scalars().all()

        want = metric or "position"
        has_any = bool(pos or sbl_lots or triggers or orders)
        evidence: Dict[str, Any] = {
            "symbol": sym,
            "metric": want,
            "has_position": pos is not None,
            "active_sbl_lots": len(sbl_lots),
            "active_triggers": len(triggers),
            "recent_orders": len(orders),
            "data_found": has_any,
        }

        if not has_any:
            return (
                f"ℹ️ ไม่พบข้อมูลหุ้น {sym} ในระบบ Homelab\n"
                "• ไม่มี position / SBL lot / trigger / order ที่บันทึกไว้\n"
                "• ข้อมูลนี้อ่านจากฐานข้อมูลเท่านั้น (ไม่กระตุ้นการล็อกอินโบรกเกอร์) — "
                "หากเพิ่งเทรด ให้รัน Portfolio Overview เพื่อซิงค์ก่อน",
                evidence,
            )

        lines = [f"📊 ข้อมูลหุ้น {sym}"]

        if pos:
            side_label = "🔴 SHORT" if (pos.position_type or "").upper() == "SHORT" else "🟢 LONG"
            price_txt = f" | ราคาล่าสุด ฿{pos.current_price:,.2f}" if pos.current_price else ""
            pnl_txt = ""
            if pos.unrealized_pnl is not None:
                cost = (pos.avg_cost or 0.0) * (pos.volume or 0)
                pct = (pos.unrealized_pnl / cost * 100.0) if cost else 0.0
                pnl_txt = f" | PnL {pos.unrealized_pnl:+,.2f} ({pct:+.2f}%)"
            lines.append(
                f"{side_label} {pos.volume:,} หุ้น @ เฉลี่ย ฿{pos.avg_cost:,.2f}{price_txt}{pnl_txt}"
            )
            tp = f"฿{pos.take_profit_price:,.2f}" if pos.take_profit_price else "ไม่ได้ตั้ง"
            sl = f"฿{pos.stop_loss_price:,.2f}" if pos.stop_loss_price else "ไม่ได้ตั้ง"
            lines.append(f"🎯 TP: {tp} | SL: {sl}")
        else:
            lines.append("📦 ไม่มี position ของหุ้นนี้ในพอร์ต")

        if want == "orders":
            if orders:
                lines.append("🧾 คำสั่งล่าสุด (5 รายการ):")
                for o in orders:
                    when = o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "N/A"
                    lines.append(f"• {o.side} {o.volume:,} @ ฿{o.price:,.2f} → {o.status} ({when})")
            else:
                lines.append("🧾 ยังไม่มีคำสั่งซื้อขายของหุ้นนี้ในระบบ")
        elif want == "tpsl":
            if triggers:
                lines.append("🛡️ Watchlist Trigger ที่เฝ้าอยู่:")
                for t in triggers:
                    lines.append(
                        f"• {t.condition_type} ฿{t.trigger_price:,.2f} → {t.action} {t.volume:,} หุ้น"
                    )
            else:
                lines.append("🛡️ ไม่มี Watchlist Trigger ที่ active สำหรับหุ้นนี้")
            lines.append(f'💡 พิมพ์ เช่น "{sym} ตั้ง TP 14 SL 12.50" เพื่ออัปเดต')
        else:  # position
            for lot in sbl_lots:
                lines.append(
                    f"🔁 SBL ค้างยืม {lot.remaining_qty:,} หุ้น "
                    f"(ดอกเบี้ย {lot.borrow_fee_rate:.2f}%/ปี, ยืม {lot.borrow_date})"
                )
            for t in triggers:
                lines.append(
                    f"🛡️ Trigger {t.action} {t.volume:,} เมื่อ {t.condition_type} ฿{t.trigger_price:,.2f}"
                )

        return "\n".join(lines), evidence

    async def _handle_postback(
        self,
        db: AsyncSession,
        data: str,
        raw_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        params = {k: v[0] for k, v in parse_qs(data).items()}
        action = params.get("action", "")
        reply_token = raw_event.get("replyToken")

        # 0. Check Card Expiration / TTL (3 minutes)
        ts_str = params.get("ts")
        if ts_str:
            try:
                ts = int(ts_str)
                now = int(time.time())
                if now - ts > settings.CARD_TTL_SECONDS:
                    reply_txt = (
                        f"⏳ การ์ดคำสั่งนี้หมดอายุแล้ว ({settings.CARD_TTL_SECONDS} วินาที) "
                        f"ราคาตลาดอาจเปลี่ยนแปลง เพื่อความปลอดภัยกรุณาส่งคำสั่งเพื่อขอราคาตลาดใหม่"
                    )
                    await self._send_reply(reply_token, reply_txt)
                    await decision_engine.handle_unanswered_timeout(
                        batch_id=params.get("batch_id", "EXPIRED_BATCH"),
                        orders=[]
                    )
                    return {"status": "CARD_EXPIRED", "batch_id": params.get("batch_id")}
            except ValueError:
                pass

        log = SessionLog(
            event_type="LINE_POSTBACK_RECEIVED",
            details=f"Action: {action} | Payload: {data}"
        )
        db.add(log)
        await db.commit()

        # 1. Action Center Postbacks: approve_all_actions, reject_all_actions, approve_action, reject_action
        if action == "approve_all_actions":
            from app.services.action_center_service import action_center_service
            results = await action_center_service.approve_all(db)
            reply_txt = f"✅ [อนุมัติทั้งหมด] ส่งคำสั่งในคิว Action Center เรียบร้อย ({len(results)} รายการ)"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "ALL_APPROVED", "results": results}

        elif action == "reject_all_actions":
            from app.services.action_center_service import action_center_service
            count = action_center_service.reject_all()
            reply_txt = f"❌ [ยกเลิกทั้งหมด] ยกเลิกคำสั่งรออนุมัติใน Action Center เรียบร้อย ({count} รายการ)"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "ALL_REJECTED", "count": count}

        elif action == "approve_action":
            from app.services.action_center_service import action_center_service
            act_id = params.get("id", "")
            res = await action_center_service.approve_single(act_id, db)
            if res.get("success"):
                reply_txt = f"✅ อนุมัติคำสั่ง {res.get('action')} {res.get('symbol')} เรียบร้อยแล้ว (สถานะ: {res.get('status')})"
            else:
                reply_txt = f"⚠️ อนุมัติไม่สำเร็จ: {res.get('error', 'ไม่พบคำสั่งหรือถูกดำเนินการไปแล้ว')}"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "ACTION_APPROVED", "result": res}

        elif action == "reject_action":
            from app.services.action_center_service import action_center_service
            act_id = params.get("id", "")
            success = action_center_service.reject_single(act_id)
            reply_txt = f"❌ ปฏิเสธและยกเลิกคำสั่ง {act_id} แล้ว" if success else "⚠️ ไม่พบคำสั่งนี้ในคิว"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "ACTION_REJECTED", "action_id": act_id}

        # 1.1 Batch Approve: action=batch_approve
        elif action == "batch_approve":
            batch_id = params.get("batch_id", "")
            batch_res = await trade_center_service.execute_batch_orders(db, batch_id)
            reply_txt = batch_res.get("summary_message", "ดำเนินการยิงคำสั่งเรียบร้อยแล้ว")
            await self._send_reply(reply_token, reply_txt)
            return {"status": "BATCH_APPROVED", "result": batch_res}

        # 1.1 Single Order Approve from Carousel: action=single_approve
        elif action == "single_approve":
            symbol = params.get("symbol", "").upper()
            side = params.get("side", "").upper()
            volume = int(params.get("volume", 0))
            price = float(params.get("price", 0.0))
            batch_id = params.get("batch_id", "")

            exec_res = await trade_center_service.execute_confirmed_order(
                db=db,
                symbol=symbol,
                side=side,
                volume=volume,
                price=price,
                source="line_carousel_single"
            )
            order_no = exec_res.get("broker_order_no", "N/A")
            reply_txt = f"⚡ อนุมัติยิงเดี่ยว: {side} {volume:,} {symbol} @ ฿{price:.2f} -> {exec_res.get('status')} (Order: {order_no})"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "SINGLE_ORDER_APPROVED", "result": exec_res}

        # 1.2 Single Order Skip from Carousel: action=single_skip
        elif action == "single_skip":
            symbol = params.get("symbol", "").upper()
            reply_txt = f"⏭️ ข้ามการส่งคำสั่งของ {symbol} ตามที่คุณเลือก"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "SINGLE_ORDER_SKIPPED", "symbol": symbol}

        # 2. Batch Cancel: action=batch_cancel
        elif action == "batch_cancel":
            batch_id = params.get("batch_id", "")
            reply_txt = f"🛑 ยกเลิกการส่งคำสั่งของรอบ {batch_id} เรียบร้อยแล้ว"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "BATCH_CANCELLED", "batch_id": batch_id}

        # 3. Single Order Confirm: action=confirm_order
        elif action == "confirm_order":
            symbol = params.get("symbol", "").upper()
            side = params.get("side", "").upper()
            volume = int(params.get("volume", 0))
            price = float(params.get("price", 0.0))
            order_id = params.get("order_id")

            exec_res = await trade_center_service.execute_confirmed_order(
                db=db,
                symbol=symbol,
                side=side,
                volume=volume,
                price=price,
                order_id=order_id,
                source="line_interactive_button"
            )
            reply_txt = exec_res.get("message", "ส่งคำสั่งเรียบร้อยแล้ว")
            await self._send_reply(reply_token, reply_txt)
            return {"status": "ORDER_EXECUTED", "result": exec_res}

        # 4. Single Order Cancel: action=cancel_order
        elif action == "cancel_order":
            order_id = params.get("order_id", "N/A")
            reply_txt = f"🛑 คำสั่ง {order_id} ถูกยกเลิกโดยผู้ใช้เรียบร้อยแล้ว"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "ORDER_CANCELLED", "order_id": order_id}

        # 5. Trigger Execute: action=trigger_execute
        elif action == "trigger_execute":
            symbol = params.get("symbol", "").upper()
            side = params.get("side", "").upper()
            volume = int(params.get("vol", 0))
            price = float(params.get("price", 0.0))

            exec_res = await trade_center_service.execute_confirmed_order(
                db=db,
                symbol=symbol,
                side=side,
                volume=volume,
                price=price,
                source="line_trigger_execute"
            )
            reply_txt = f"⚡ อนุมัติยิงคำสั่ง Trigger: {side} {volume:,} {symbol} @ ฿{price:.2f} ({exec_res.get('status')})"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "TRIGGER_EXECUTED", "result": exec_res}

        # 6. Trigger Adjust Stop: action=trigger_adjust_stop
        elif action == "trigger_adjust_stop":
            symbol = params.get("symbol", "").upper()
            new_stop = float(params.get("new_stop", 0.0))
            reply_txt = f"📉 เลื่อนจุด Stop ของ {symbol} ไปที่ ฿{new_stop:.2f} เรียบร้อยแล้ว"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "TRIGGER_STOP_ADJUSTED", "symbol": symbol, "new_stop": new_stop}

        # 7. Price Negotiation Adjust: action=approve_negotiation
        elif action == "approve_negotiation":
            order_no = params.get("order_no", "")
            symbol = params.get("symbol", "").upper()
            side = params.get("side", "").upper()
            new_price = float(params.get("new_price", 0.0))
            volume = int(params.get("volume", 0))

            adj_res = await price_negotiation_service.execute_price_adjustment(
                db=db,
                broker_order_no=order_no,
                symbol=symbol,
                side=side,
                new_price=new_price,
                volume=volume
            )
            reply_txt = f"🎯 ปรับราคา {symbol} ({order_no}) เป็น ฿{new_price:.2f} เรียบร้อยแล้ว"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "PRICE_NEGOTIATION_APPROVED", "result": adj_res}

        # 8. SBL Return Confirm: action=sbl_return_confirm
        elif action == "sbl_return_confirm":
            lot_id = params.get("lot_id", "")
            symbol = params.get("symbol", "").upper()
            qty = int(params.get("qty", 0))

            ret_res = await trade_dispatcher.dispatch_sbl_return(lot_id=lot_id, return_qty=qty)
            reply_txt = f"✅ คืนหุ้น SBL Lot #{lot_id} ({symbol} {qty:,} หุ้น) เรียบร้อยแล้ว หยุดคิดดอกเบี้ยยืมหุ้นทันที"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "SBL_RETURN_CONFIRMED", "result": ret_res}

        # 9. SBL Hold Shares: action=sbl_hold_shares
        elif action == "sbl_hold_shares":
            lot_id = params.get("lot_id", "")
            symbol = params.get("symbol", "").upper()
            reply_txt = f"⏸️ พักหุ้น {symbol} (Lot #{lot_id}) ไว้ในพอร์ตเพื่อเตรียมเปิด Short รอบต่อไป"
            await self._send_reply(reply_token, reply_txt)
            return {"status": "SBL_SHARES_HELD", "lot_id": lot_id}

        return {"status": "POSTBACK_PROCESSED", "data": data}

    async def _reconcile_daily_orders_with_portfolio(self, immediate_orders: list) -> Dict[str, Any]:
        """
        Cross-checks Daily Order items against real TradeMan / Simulator portfolio holdings.
        """
        # Fetch current holdings
        if trade_dispatcher.is_live:
            holdings = await trademan_driver.scrape_portfolio()
        else:
            holdings = virtual_simulator.get_portfolio_snapshot()

        holdings_by_sym = {h["symbol"].upper(): h for h in holdings}
        adjusted_orders = []
        warnings = []

        for ord_item in immediate_orders:
            sym = ord_item.symbol.upper()
            side = ord_item.side.value if hasattr(ord_item.side, "value") else str(ord_item.side)
            vol = ord_item.volume

            # Check Odd-lot rule
            if vol % 100 != 0 or vol < 100:
                ord_item.is_valid_lot = False
                ord_item.validation_error = f"เศษหุ้น {vol:,} หุ้น โบรกเกอร์ไม่อนุญาตบนกระดานปกติ (ต้อง % 100 == 0)"
                warnings.append(f"⚠️ {sym}: {ord_item.validation_error}")
                continue

            # Check sell holdings
            if side == "SELL":
                curr_pos = holdings_by_sym.get(sym)
                if not curr_pos or curr_pos.get("volume", 0) <= 0:
                    warnings.append(f"⚠️ {sym}: ไม่พบหุ้นในพอร์ตจริง (อาจถูกขายไปแล้ว) ข้ามรายการนี้")
                    continue
                avail_vol = curr_pos.get("volume", 0)
                if avail_vol < vol:
                    warnings.append(f"⚠️ {sym}: ในพอร์ตมี {avail_vol:,} หุ้น (น้อยกว่า {vol:,} หุ้นในข้อความ) ปรับลดจำนวนตามจริง")
                    ord_item.volume = avail_vol

            adjusted_orders.append(ord_item)

        return {"adjusted_orders": adjusted_orders, "warnings": warnings}

    def _build_batch_flex_message(self, batch_res: Dict[str, Any]) -> Dict[str, Any]:
        card = batch_res.get("card", {})
        batch_id = card.get("batch_id", "")
        orders = card.get("immediate_orders", [])
        warnings = card.get("warnings", [])
        triggers_count = card.get("triggers_count", 0)
        mode_badge = trade_dispatcher.get_mode_badge()

        # Build order rows
        order_rows = []
        for o in orders:
            sym = o.get("symbol", "")
            side = o.get("side", "")
            vol = o.get("volume", 0)
            px = o.get("price", 0.0)
            side_color = "#ef4444" if side in ["SELL", "SHORT"] else "#10b981"

            order_rows.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{side} {sym}",
                        "weight": "bold",
                        "color": side_color,
                        "size": "sm",
                        "flex": 4
                    },
                    {
                        "type": "text",
                        "text": f"{vol:,} หุ้น",
                        "size": "sm",
                        "color": "#475569",
                        "align": "end",
                        "flex": 3
                    },
                    {
                        "type": "text",
                        "text": f"@ ฿{px:.2f}",
                        "size": "sm",
                        "color": "#0f172a",
                        "weight": "bold",
                        "align": "end",
                        "flex": 3
                    }
                ]
            })

        # Warning rows if any
        warning_boxes = []
        if warnings:
            for w in warnings[:3]:
                warning_boxes.append({
                    "type": "text",
                    "text": w,
                    "size": "xs",
                    "color": "#b45309",
                    "wrap": True
                })

        body_contents = [
            {
                "type": "text",
                "text": f"🚨 รายการคำสั่ง Hard Exit ({len(orders)} ไม้):",
                "weight": "bold",
                "size": "sm",
                "color": "#0f172a"
            },
            {
                "type": "box",
                "layout": "vertical",
                "margin": "sm",
                "spacing": "xs",
                "contents": order_rows or [{
                    "type": "text",
                    "text": "ไม่มีคำสั่ง Hard Exit ที่ต้องดำเนินการ",
                    "size": "xs",
                    "color": "#64748b"
                }]
            },
            {"type": "separator", "margin": "md"}
        ]

        if triggers_count > 0:
            body_contents.append({
                "type": "text",
                "text": f"📋 บันทึก Watchlist Triggers: {triggers_count} ไม้ (เฝ้าระวัง)",
                "size": "xs",
                "color": "#475569",
                "margin": "sm"
            })

        if warning_boxes:
            body_contents.append({
                "type": "box",
                "layout": "vertical",
                "margin": "sm",
                "backgroundColor": "#fef3c7",
                "cornerRadius": "md",
                "paddingAll": "sm",
                "contents": warning_boxes
            })

        return {
            "type": "flex",
            "altText": f"📊 แผนคำสั่ง Daily Order ({len(orders)} ไม้) รออนุมัติ",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#0f172a",
                    "contents": [
                        {
                            "type": "text",
                            "text": "⚡ INVESTMENT HOMELAB",
                            "weight": "bold",
                            "size": "xs",
                            "color": "#38bdf8"
                        },
                        {
                            "type": "text",
                            "text": "Human-in-the-Loop Approval",
                            "weight": "bold",
                            "size": "md",
                            "color": "#ffffff",
                            "margin": "xs"
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "margin": "sm",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "โหมด: ",
                                    "size": "xs",
                                    "color": "#94a3b8"
                                },
                                {
                                    "type": "text",
                                    "text": mode_badge,
                                    "size": "xs",
                                    "weight": "bold",
                                    "color": "#34d399"
                                }
                            ]
                        }
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": body_contents
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#10b981",
                            "action": {
                                "type": "postback",
                                "label": "✅ อนุมัติยิงคำสั่งทั้งหมด",
                                "data": f"action=batch_approve&batch_id={batch_id}",
                                "displayText": "✅ อนุมัติยิงคำสั่งทั้งหมด"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "❌ ยกเลิกทั้งหมด",
                                "data": f"action=batch_cancel&batch_id={batch_id}",
                                "displayText": "❌ ยกเลิกทั้งหมด"
                            }
                        }
                    ]
                }
            },
            "quickReply": {
                "items": [
                    {
                        "type": "action",
                        "action": {
                            "type": "postback",
                            "label": "✅ อนุมัติทั้งหมด",
                            "data": f"action=batch_approve&batch_id={batch_id}",
                            "displayText": "✅ อนุมัติยิงคำสั่งทั้งหมด"
                        }
                    },
                    {
                        "type": "action",
                        "action": {
                            "type": "postback",
                            "label": "❌ ยกเลิก",
                            "data": f"action=batch_cancel&batch_id={batch_id}",
                            "displayText": "❌ ยกเลิกทั้งหมด"
                        }
                    }
                ]
            }
        }

    def build_trade_approval_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds a dedicated Human-in-the-Loop Trade Approval Flex Card for Stop Loss / Take Profit triggers.
        """
        sym = data.get("symbol", "")
        action = data.get("action", "SELL")
        vol = data.get("volume", 0)
        price = data.get("price", 0.0)
        reason = data.get("reason", "SL_HIT")
        desc = data.get("description", "")
        confirm_data = data.get("confirm_action", f"action=confirm_order&symbol={sym}&side={action}&volume={vol}&price={price}")
        cancel_data = data.get("cancel_action", f"action=cancel_order&symbol={sym}")

        is_sl = "SL" in reason
        badge_text = "🚨 STOP LOSS TRIGGERED" if is_sl else "🎯 TAKE PROFIT TRIGGERED"
        badge_bg = "#dc2626" if is_sl else "#16a34a"
        action_color = "#f87171" if is_sl else "#4ade80"

        return {
            "type": "flex",
            "altText": f"🚨 [ด่วน] ขอยืนยันคำสั่ง {action} {sym} ({badge_text})",
            "contents": {
                "type": "bubble",
                "size": "mega",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#0f172a",
                    "paddingAll": "16px",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "⚡ INVESTMENT HOMELAB", "color": "#38bdf8", "weight": "bold", "size": "xs"},
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": badge_bg,
                                    "cornerRadius": "4px",
                                    "paddingStart": "8px",
                                    "paddingEnd": "8px",
                                    "paddingTop": "2px",
                                    "paddingBottom": "2px",
                                    "contents": [
                                        {"type": "text", "text": badge_text, "color": "#ffffff", "weight": "bold", "size": "xxs"}
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "text",
                            "text": f"ขอยืนยันคำสั่ง {action} {sym}",
                            "color": "#ffffff",
                            "weight": "bold",
                            "size": "xl",
                            "margin": "sm"
                        }
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#1e293b",
                    "paddingAll": "16px",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "xs",
                            "contents": [
                                {"type": "text", "text": "ชื่อหุ้น:", "color": "#94a3b8", "size": "sm", "flex": 2},
                                {"type": "text", "text": sym, "color": "#f8fafc", "weight": "bold", "size": "sm", "flex": 4}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "xs",
                            "contents": [
                                {"type": "text", "text": "คำสั่งแนะนำ:", "color": "#94a3b8", "size": "sm", "flex": 2},
                                {"type": "text", "text": f"{action} {vol:,} หุ้น", "color": action_color, "weight": "bold", "size": "sm", "flex": 4}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "xs",
                            "contents": [
                                {"type": "text", "text": "ราคาปัจจุบัน:", "color": "#94a3b8", "size": "sm", "flex": 2},
                                {"type": "text", "text": f"฿{price:.2f}", "color": "#f8fafc", "weight": "bold", "size": "sm", "flex": 4}
                            ]
                        },
                        {"type": "separator", "margin": "md", "color": "#334155"},
                        {
                            "type": "text",
                            "text": desc,
                            "color": "#cbd5e1",
                            "size": "xs",
                            "margin": "md",
                            "wrap": True
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#0f172a",
                    "paddingAll": "12px",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#dc2626" if is_sl else "#16a34a",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": f"✅ อนุมัติ {action} {sym}",
                                "data": confirm_data,
                                "displayText": f"✅ ขอยืนยันอนุมัติคำสั่ง {action} {sym} จำนวน {vol:,} หุ้น"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "color": "#334155",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": "❌ ปฏิเสธ / ถือต่อ",
                                "data": cancel_data,
                                "displayText": f"❌ ปฏิเสธคำสั่ง {action} {sym} ขอถือสถานะต่อ"
                            }
                        }
                    ]
                }
            }
        }


    def build_order_carousel_card(
        self,
        orders: list,
        batch_id: str,
        mode_badge: str,
        strategy_summary: Optional[str] = None,
        hold_positions: Optional[list] = None,
        watchlist_triggers: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Builds an interactive LINE Flex Message Carousel:
        1. Individual bubble card per stock order.
        2. Shows Price Advantage Badge (🔥 ราคาตลาดดีกว่าเป้า!) if market price is favorable.
        3. Shows Warning tag if volume was auto-clamped.
        4. Individual [✅ ยิงไม้นี้] & [❌ ข้ามไม้นี้] buttons with TTL timestamp.
        5. Final Summary Bubble with [✅ อนุมัติยิงทุกไม้ที่เหลือ] & [❌ ยกเลิกทั้งหมด].
        """
        bubbles = []
        now_ts = int(time.time())

        # If no orders, return a single notification bubble
        if not orders:
            return {
                "type": "flex",
                "altText": "📋 ไม่มีคำสั่งซื้อขายที่ต้องส่งในขณะนี้",
                "contents": {
                    "type": "bubble",
                    "header": {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#0f172a",
                        "contents": [
                            {"type": "text", "text": "⚡ INVESTMENT HOMELAB", "color": "#38bdf8", "weight": "bold", "size": "xs"},
                            {"type": "text", "text": "ไม่มีคำสั่งที่ต้องยิง", "color": "#ffffff", "weight": "bold", "size": "md", "margin": "xs"}
                        ]
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "ระบบกระทบยอดพอร์ตเรียบร้อย ไม่มีหุ้นที่เข้าเกณฑ์ส่งคำสั่ง", "size": "sm", "color": "#64748b"}
                        ]
                    }
                }
            }

        for idx, o in enumerate(orders):
            sym = getattr(o, "symbol", "")
            side = getattr(o, "side", "")
            side_str = side.value if hasattr(side, "value") else str(side)
            vol = getattr(o, "volume", 0)
            px = getattr(o, "price", 0.0)
            reason = getattr(o, "reason", "ตามวินัยกลยุทธ์")
            price_adv = getattr(o, "price_advantage_label", None)
            clamped_from = getattr(o, "clamped_from_volume", None)

            side_color = "#ef4444" if side_str in ["SELL", "SHORT"] else "#10b981"

            bubble_body = []

            # 1. Price Advantage Badge (เมื่อได้ราคาดีกว่าเป้า)
            if price_adv:
                bubble_body.append({
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#ecfdf5",
                    "cornerRadius": "md",
                    "paddingAll": "sm",
                    "margin": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": price_adv,
                            "size": "xs",
                            "weight": "bold",
                            "color": "#047857",
                            "wrap": True
                        }
                    ]
                })

            # 2. Clamped Volume Warning
            if clamped_from:
                bubble_body.append({
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#fffbeb",
                    "cornerRadius": "md",
                    "paddingAll": "xs",
                    "margin": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"⚠️ ปรับลดจาก {clamped_from:,} เหลือ {vol:,} หุ้น ตามพอร์ตจริง",
                            "size": "xxs",
                            "color": "#b45309",
                            "wrap": True
                        }
                    ]
                })

            # 3. Order Details Rows
            bubble_body.extend([
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {"type": "text", "text": "จำนวน:", "size": "sm", "color": "#64748b", "flex": 4},
                        {"type": "text", "text": f"{vol:,} หุ้น", "size": "sm", "weight": "bold", "color": "#0f172a", "align": "end", "flex": 6}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": "ราคาเป้าหมาย:", "size": "sm", "color": "#64748b", "flex": 4},
                        {"type": "text", "text": f"฿{px:.2f}", "size": "sm", "weight": "bold", "color": "#0284c7", "align": "end", "flex": 6}
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"เหตุผล: {reason}", "size": "xxs", "color": "#94a3b8", "wrap": True}
                    ]
                }
            ])

            bubble = {
                "type": "bubble",
                "size": "mega",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#0f172a",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"ไม้ {idx+1}/{len(orders)}",
                                    "size": "xxs",
                                    "color": "#94a3b8",
                                    "flex": 4
                                },
                                {
                                    "type": "text",
                                    "text": mode_badge,
                                    "size": "xxs",
                                    "color": "#38bdf8",
                                    "align": "end",
                                    "flex": 6
                                }
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "xs",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"{side_str} {sym}",
                                    "size": "lg",
                                    "weight": "bold",
                                    "color": side_color
                                }
                            ]
                        }
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": bubble_body
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#10b981",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": f"✅ ยิงไม้นี้ ({sym})",
                                "data": f"action=single_approve&batch_id={batch_id}&symbol={sym}&side={side_str}&volume={vol}&price={px}&ts={now_ts}",
                                "displayText": f"✅ ยิง {side_str} {vol:,} {sym} @ ฿{px:.2f}"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": f"❌ ข้ามไม้นี้ ({sym})",
                                "data": f"action=single_skip&batch_id={batch_id}&symbol={sym}",
                                "displayText": f"❌ ข้าม {sym}"
                            }
                        }
                    ]
                }
            }
            bubbles.append(bubble)

        # Bubble: Portfolio Overview Bubble (Active Swings & Weed-Out Watchlist)
        if hold_positions:
            swings = [h for h in hold_positions if getattr(h, "group_type", "ACTIVE_SWING") == "ACTIVE_SWING"]
            weed_outs = [h for h in hold_positions if getattr(h, "group_type", "ACTIVE_SWING") == "WEED_OUT"]

            hold_body_contents = []

            hold_body_contents.append({
                "type": "text",
                "text": f"📊 สถานะพอร์ตคงค้าง ({len(hold_positions)} ไม้)",
                "weight": "bold",
                "size": "sm",
                "color": "#0f172a"
            })

            # Runners section (if any triggers)
            if watchlist_triggers:
                runner_texts = []
                for trg in watchlist_triggers[:4]:
                    t_sym = getattr(trg, "symbol", "")
                    t_act = getattr(trg, "action", "")
                    t_cond = ">=" if getattr(trg, "condition", "") == "PRICE_ABOVE" else "<="
                    t_px = getattr(trg, "trigger_price", 0.0)
                    runner_texts.append(f"• {t_sym}: {t_act} หาก {t_cond} ฿{t_px:.2f}")
                
                hold_body_contents.append({
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#f0fdf4",
                    "cornerRadius": "md",
                    "paddingAll": "xs",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": "🎯 เฝ้าระวัง Dynamic TP / Trailing Stop:", "size": "xxs", "weight": "bold", "color": "#15803d"}
                    ] + [{"type": "text", "text": rt, "size": "xxs", "color": "#166534"} for rt in runner_texts]
                })

            # Active swings section
            if swings:
                swing_strs = []
                for s in swings[:6]:
                    s_sym = getattr(s, "symbol", "")
                    s_pt = getattr(s, "position_type", "LONG")
                    s_vol = getattr(s, "volume", 0)
                    s_days = getattr(s, "days_held", None)
                    day_str = f" ({s_days} วัน)" if s_days is not None else ""
                    pt_tag = "[S]" if s_pt == "SHORT" else ""
                    swing_strs.append(f"{s_sym}{pt_tag} {s_vol:,}{day_str}")
                
                hold_body_contents.append({
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"🟢 รอบปกติ Active Swings ({len(swings)} ไม้):", "size": "xxs", "weight": "bold", "color": "#0369a1"},
                        {"type": "text", "text": " • ".join(swing_strs) + (f" ...และอีก {len(swings)-6} ไม้" if len(swings) > 6 else ""), "size": "xxs", "color": "#334155", "wrap": True}
                    ]
                })

            # Weed-out watchlist section
            if weed_outs:
                wo_items = []
                for w in weed_outs:
                    w_sym = getattr(w, "symbol", "")
                    w_pt = getattr(w, "position_type", "LONG")
                    w_vol = getattr(w, "volume", 0)
                    w_warn = getattr(w, "warning_note", "") or getattr(w, "note", "")
                    pt_tag = "[SHORT] " if w_pt == "SHORT" else ""
                    warn_str = f" ⚠️ {w_warn}" if w_warn else ""
                    wo_items.append({
                        "type": "text",
                        "text": f"• {pt_tag}{w_sym} ({w_vol:,} หุ้น){warn_str}",
                        "size": "xxs",
                        "color": "#b45309" if "Stop" in warn_str or "Exit" in warn_str or "SBL" in warn_str else "#64748b",
                        "weight": "bold" if "Stop" in warn_str or "Exit" in warn_str else "regular",
                        "wrap": True
                    })

                hold_body_contents.append({
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#fffbeb",
                    "cornerRadius": "md",
                    "paddingAll": "xs",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"🟡 กลุ่มเฝ้าระวัง Weed-Out ({len(weed_outs)} ไม้):", "size": "xxs", "weight": "bold", "color": "#b45309"}
                    ] + wo_items
                })

            hold_bubble = {
                "type": "bubble",
                "size": "mega",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#0f172a",
                    "contents": [
                        {"type": "text", "text": "💼 สรุปสถานะพอร์ตคงค้าง", "weight": "bold", "size": "sm", "color": "#38bdf8"},
                        {"type": "text", "text": f"รวมทั้งหมด {len(hold_positions)} ไม้ | Active Swings & Weed-Out", "size": "xxs", "color": "#94a3b8"}
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": hold_body_contents
                }
            }
            bubbles.append(hold_bubble)

        # Final Summary Card in the Carousel
        summary_bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0f172a",
                "contents": [
                    {"type": "text", "text": "⚡ สรุปคำสั่งชุด BATCH", "weight": "bold", "size": "sm", "color": "#38bdf8"},
                    {"type": "text", "text": f"Batch: {batch_id}", "size": "xxs", "color": "#94a3b8", "margin": "xxs"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📋 รวมคำสั่งทั้งหมด: {len(orders)} ไม้",
                        "weight": "bold",
                        "size": "sm",
                        "color": "#0f172a"
                    },
                    {
                        "type": "text",
                        "text": strategy_summary or "พร้อมส่งคำสั่งเข้ากระดาน TradeMan ตามวินัยกลยุทธ์",
                        "size": "xs",
                        "color": "#64748b",
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": f"⏱️ การ์ดมีอายุ {settings.CARD_TTL_SECONDS} วินาที",
                        "size": "xxs",
                        "color": "#94a3b8"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0284c7",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "✅ อนุมัติยิงทุกไม้ที่เหลือ",
                            "data": f"action=batch_approve&batch_id={batch_id}&ts={now_ts}",
                            "displayText": "✅ อนุมัติยิงทุกไม้ที่เหลือ"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "❌ ยกเลิกทั้งหมด",
                            "data": f"action=batch_cancel&batch_id={batch_id}",
                            "displayText": "❌ ยกเลิกทั้งหมด"
                        }
                    }
                ]
            }
        }
        bubbles.append(summary_bubble)

        return {
            "type": "flex",
            "altText": f"📊 แผนคำสั่ง Carousel ({len(orders)} ไม้) รออนุมัติ",
            "contents": {
                "type": "carousel",
                "contents": bubbles
            }
        }

    async def _send_reply(self, reply_token: Optional[str], message_or_text: Any):
        """Sends reply back to LINE via Messaging API or logs in simulation."""
        if not reply_token:
            return

        if isinstance(message_or_text, str):
            messages = [{"type": "text", "text": message_or_text}]
        elif isinstance(message_or_text, dict):
            messages = [message_or_text]
        elif isinstance(message_or_text, list):
            messages = message_or_text
        else:
            messages = [{"type": "text", "text": str(message_or_text)}]

        # If live credentials configured and not in simulation
        if settings.LINE_CHANNEL_ACCESS_TOKEN and not settings.LINE_SIMULATION_MODE and settings.LINE_CHANNEL_ACCESS_TOKEN != "mock_line_channel_token":
            url = "https://api.line.me/v2/bot/message/reply"
            headers = {
                "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                "replyToken": reply_token,
                "messages": messages
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    logger.info(f"[LINE API] Reply sent (HTTP {resp.status_code})")
                    if resp.status_code >= 400:
                        logger.error(f"[LINE API] Error response: {resp.text}")
            except Exception as e:
                logger.error(f"[LINE API] Reply error: {e}")
        else:
            summary = messages[0].get("text") or messages[0].get("altText") or str(messages[0])
            logger.info(f"[LINE SIMULATION] Reply to {reply_token}: {summary}")

    async def push_message(self, message_or_text: Any, to_user_id: Optional[str] = None) -> bool:
        """
        Pushes a proactive message/card via LINE Messaging API or logs in simulation.

        Target resolution (2026-10-08, LINE Group OTP relay):
          1. explicit `to_user_id`
          2. `settings.LINE_GROUP_ID`  ← "a14s homelab" group (OTP push target)
          3. `settings.LINE_ADMIN_USER_ID` (legacy 1:1 relay)
          4. broadcast (no target configured)
        """
        user_id = to_user_id or settings.LINE_GROUP_ID or settings.LINE_ADMIN_USER_ID

        if isinstance(message_or_text, str):
            messages = [{"type": "text", "text": message_or_text}]
        elif isinstance(message_or_text, dict):
            messages = [message_or_text]
        elif isinstance(message_or_text, list):
            messages = message_or_text
        else:
            messages = [{"type": "text", "text": str(message_or_text)}]

        if settings.LINE_CHANNEL_ACCESS_TOKEN and not settings.LINE_SIMULATION_MODE and settings.LINE_CHANNEL_ACCESS_TOKEN != "mock_line_channel_token":
            headers = {
                "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }
            if user_id:
                url = "https://api.line.me/v2/bot/message/push"
                payload = {"to": user_id, "messages": messages}
                target_desc = f"user {user_id}"
            else:
                url = "https://api.line.me/v2/bot/message/broadcast"
                payload = {"messages": messages}
                target_desc = "broadcast to followers"

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    logger.info(f"[LINE API] Push sent via {target_desc} (HTTP {resp.status_code})")
                    if resp.status_code >= 400:
                        logger.error(f"[LINE API] Push error response: {resp.text}")
                        return False
                return True
            except Exception as e:
                logger.error(f"[LINE API] Push error: {e}")
                return False
        else:
            summary = messages[0].get("text") or messages[0].get("altText") or str(messages[0])
            logger.info(f"[LINE SIMULATION] Push: {summary}")
            return True

    async def push_otp_request(
        self,
        ref: Optional[str] = None,
        broker: str = "KRUNGSRI",
        timeout_seconds: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        ขอ OTP ผ่าน LINE relay (กลุ่ม "a14s homelab" หรือแชท 1:1 กับ OA — LINE-RCA-006)

        Pushes a 2FA OTP request message to the active LINE target so the operator can
        paste the 6-digit code there. The incoming message is then picked up by
        `webhook_line.py` → `_handle_text_message()` → `otp_relay_registry.record_otp_received()`
        (persisted into the PRIMARY DB) and polled by the awaiting broker driver.

        LINE-RCA-010: also records an `OTP_REQUESTED` marker (broker + ref) in the
        primary DB *before* pushing, so the webhook ACK can name the broker that
        actually asked (latest-request-wins) instead of hard-coding Krungsri.

        Invariant 9 (LINE variant): the CALLER must have already verified that the LINE
        relay is ready before invoking this. This method only sends a notification —
        it never triggers the broker SMS OTP itself.
        """
        from app.services.otp_relay_registry import (
            broker_label as _broker_label,
            record_request as _record_request,
        )

        broker_tag = (broker or "").upper()
        label = _broker_label(broker_tag) or (broker or "Broker")
        ttl = timeout_seconds or settings.OTP_TIMEOUT_SECONDS

        # Record the pending request in the PRIMARY DB before the push (best-effort).
        await _record_request(broker_tag, ref=ref, ttl_seconds=int(ttl))

        chat_word = "กลุ่มนี้" if settings.LINE_GROUP_ID else "แชทนี้"
        text = (
            f"🔐 [2FA OTP REQUIRED]\n"
            f"โบรกเกอร์: {label}\n"
            f"{'Ref: ' + ref if ref else 'Ref: (ไม่ระบุ)'}\n\n"
            f"👉 พิมพ์รหัส OTP 6 หลักตอบใน{chat_word}ได้เลย\n"
            f"⏱️ หมดเวลาใน {ttl} วินาที"
        )
        if notes:
            text += f"\n\n📝 {notes}"

        target = settings.LINE_GROUP_ID or settings.LINE_ADMIN_USER_ID
        logger.warning(f"[LINE OTP REQUEST] broker={label} ref={ref or 'N/A'} target={target or 'broadcast'}")
        return await self.push_message(text)

    async def push_progress_update(self, text: str):
        """Pushes a concise 1-line real-time status or milestone update if enabled."""
        logger.info(f"[PROGRESS] {text}")
        if getattr(settings, "ENABLE_PROGRESS_NOTIFICATIONS", False):
            await self.push_message(text)
        else:
            logger.debug(f"[PROGRESS MUTED] {text}")

    async def send_alert(self, text: str):
        """Convenience method to push real-time alerts and trigger notifications."""
        await self.push_message(text)

    async def send_system_notification(
        self,
        title: str,
        message: str,
        action_required: Optional[str] = None,
        severity: str = "WARNING"
    ):
        """
        Sends an out-of-band System Remediation Notification to the user via 'a14s homelab' LINE Bot.
        Used specifically when the hardware bridge (KDE Connect / Tailscale) is disconnected or
        requires human intervention on mobile, allowing the user to take action before operations begin.
        """
        icon = "🚨" if severity == "CRITICAL" else ("⚠️" if severity == "WARNING" else "ℹ️")
        formatted_text = f"{icon} [a14s homelab - System Alert]\n{title}\n\n{message}"
        if action_required:
            formatted_text += f"\n\n👉 สิ่งที่ต้องทำ:\n{action_required}"

        logger.warning(f"[SYSTEM NOTIFICATION -> a14s homelab] {title}")
        await self.push_message(formatted_text)


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:6].upper()


line_service = LineMessagingService()
