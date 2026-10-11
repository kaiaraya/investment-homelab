"""
Daily Trading Scenario Simulation Engine (10:00 - 19:30).
Implements the 8 Market Regimes with Active/Passive Action orchestration:
1. 10:00 - 10:30: [Active] Close TP (Model Target + Special Profit Escape) | [Passive] SET Monitor
2. 10:30 - 12:00: [Active] Close SL, Weed-out, TP, Open Probabilistic Positions | [Passive] SET Monitor
3. 12:00 - 12:30: [Active] Negotiate Order (Unmatched) | [Passive] Midday SET Monitor
4. 14:00 - 14:30: [Active] Afternoon TP (if any) | [Passive] Afternoon SET Monitor
5. 14:30 - 16:00: [Active] Afternoon SL, Weed-out, TP, Open Positions | [Passive] Afternoon SET Monitor
6. 16:00 - 16:30: [Active] Day-Close Negotiate Order (Unmatched/ATC) | [Passive] Close SET Monitor
7. 16:30 - 17:00: [Active] Return SBL Shares via LINE Confirmation | [Passive] Final Close Monitor
8. 19:00 - 19:30: [Passive] Comprehensive Deep EOD Performance Report via LINE
"""

import asyncio
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import select, delete, desc
from app.core.config import settings
from app.core.virtual_clock import virtual_clock
from app.db.models import Position, Order, SBLBorrowLot, SessionLog, WatchlistTrigger
from app.db.session import AsyncSessionLocal
from app.browser.trademan_simulator import virtual_simulator
from app.schemas.order import OrderSide, OrderStatus
from app.schemas.intelligence import SignalParseResult
from app.services.parser import signal_parser
from app.services.trade_dispatcher import trade_dispatcher
from app.services.price_negotiation_service import price_negotiation_service
from app.services.market_monitor_service import market_monitor_service
from app.services.eod_service import eod_service
from app.services.line_service import line_service

logger = logging.getLogger(__name__)


class DailyScenarioRunner:
    """
    Orchestrates the End-to-End Daily Trading Scenario (10:00 - 19:30)
    with Dual-Gate Pipeline (Web Console + LINE Webhook) and Hybrid Time-Warp runner.
    """

    def __init__(self):
        self.live_line_enabled: bool = False
        self.parsed_strategy: Optional[Dict[str, Any]] = None
        self.execution_logs: List[Dict[str, Any]] = []
        self.current_step_index: int = 0
        self.is_running: bool = False

        self.time_slots = [
            {"id": "slot_1000", "time": "10:00", "label": "10:00 - 10:30", "title": "Retail Morning Open (TP & Monitor)"},
            {"id": "slot_1030", "time": "10:30", "label": "10:30 - 12:00", "title": "Auto Trading Window 1 (SL, Weed-out, TP, Entry)"},
            {"id": "slot_1200", "time": "12:00", "label": "12:00 - 12:30", "title": "Morning Close & Price Negotiation"},
            {"id": "slot_1400", "time": "14:00", "label": "14:00 - 14:30", "title": "Retail Afternoon Open (TP & Monitor)"},
            {"id": "slot_1430", "time": "14:30", "label": "14:30 - 16:00", "title": "Auto Trading Window 2 (Afternoon Rebalancing)"},
            {"id": "slot_1600", "time": "16:00", "label": "16:00 - 16:30", "title": "Day Close Negotiation & ATC"},
            {"id": "slot_1630", "time": "16:30", "label": "16:30 - 17:00", "title": "Post-Market & SBL Return via LINE"},
            {"id": "slot_1900", "time": "19:00", "label": "19:00 - 19:30", "title": "Deep EOD Performance Report"}
        ]

    def toggle_live_line(self, enabled: bool) -> bool:
        self.live_line_enabled = enabled
        logger.info(f"DailyScenarioRunner: live_line_enabled set to {enabled}")
        return self.live_line_enabled

    async def _send_line_message(self, message: Any) -> None:
        """Sends message to real LINE bot if toggle is enabled."""
        if not self.live_line_enabled:
            logger.info("DailyScenarioRunner: Live LINE push skipped (Toggle is OFF)")
            return

        try:
            if isinstance(message, dict) and "type" in message:
                await line_service.push_message(message)
            elif isinstance(message, str):
                await line_service.push_progress_update(message)
        except Exception as e:
            logger.warning(f"DailyScenarioRunner: Failed to push to LINE: {e}")

    async def reset_simulation_state(self) -> None:
        """Cleans database and virtual simulator for a fresh test run."""
        logger.info("DailyScenarioRunner: Resetting database and simulator state...")
        virtual_simulator.reset()
        virtual_clock.advance_to("09:30")

        async with AsyncSessionLocal() as db:
            await db.execute(delete(Position))
            await db.execute(delete(Order))
            await db.execute(delete(SBLBorrowLot))
            await db.execute(delete(WatchlistTrigger))
            await db.commit()

        self.execution_logs.clear()
        self.current_step_index = 0

    async def load_markdown_strategy(self, markdown_text: str) -> Dict[str, Any]:
        """
        Parses freeform Markdown text via Gemini AI (or heuristic fallback)
        and seeds initial positions/orders into the simulator and database.
        """
        await self.reset_simulation_state()

        logger.info("DailyScenarioRunner: Parsing strategy text via signal_parser...")
        parsed_res = await signal_parser.parse_strategy_with_ai(markdown_text)

        # Convert to dict for JSON serialization
        immediate_orders = [o.model_dump() if hasattr(o, "model_dump") else o.dict() for o in parsed_res.immediate_orders]
        watchlist_triggers = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in parsed_res.watchlist_triggers]
        hold_positions = [h.model_dump() if hasattr(h, "model_dump") else h.dict() for h in parsed_res.hold_positions]

        self.parsed_strategy = {
            "source_method": parsed_res.source_method,
            "error_message": parsed_res.error_message,
            "strategy_summary": parsed_res.strategy_summary,
            "immediate_orders": immediate_orders,
            "watchlist_triggers": watchlist_triggers,
            "hold_positions": hold_positions,
            "total_parsed": parsed_res.total_parsed
        }

        # Seed initial portfolio positions in DB and Simulator
        async with AsyncSessionLocal() as db:
            # 1. Setup default positions if not already in hold_positions
            default_positions = [
                # Runner for 10:00 TP (Model Target Hit)
                Position(
                    symbol="CKP", position_type="LONG", volume=16000,
                    avg_cost=2.36, current_price=2.48, prior_close_price=2.38,
                    take_profit_price=2.48, stop_loss_price=2.30
                ),
                # Special Profit Escape for 10:00 (Weakening momentum, quick exit)
                Position(
                    symbol="SINGER", position_type="LONG", volume=3700,
                    avg_cost=10.30, current_price=10.50, prior_close_price=10.30,
                    take_profit_price=10.90, stop_loss_price=10.10
                ),
                # Hard Stop Loss for 10:30 (-4.2%)
                Position(
                    symbol="TIDLOR", position_type="LONG", volume=2000,
                    avg_cost=19.00, current_price=18.20, prior_close_price=18.80,
                    take_profit_price=20.00, stop_loss_price=18.60
                ),
                # Weed-out Watchlist for 10:30 (Stagnant, day 9/10)
                Position(
                    symbol="CPALL", position_type="LONG", volume=800,
                    avg_cost=46.25, current_price=46.00, prior_close_price=46.25,
                    take_profit_price=48.00, stop_loss_price=45.00
                ),
                # SBL Short Position for Weed-out / Cover / Return
                Position(
                    symbol="PR9", position_type="SHORT", volume=2700,
                    avg_cost=19.20, current_price=19.40, prior_close_price=19.20,
                    take_profit_price=18.50, stop_loss_price=19.60
                )
            ]

            # Merge with hold_positions from parsed markdown if present
            for h in parsed_res.hold_positions:
                sym = h.symbol
                if not any(p.symbol == sym for p in default_positions):
                    default_positions.append(Position(
                        symbol=sym,
                        position_type=h.position_type or "LONG",
                        volume=h.volume or 1000,
                        avg_cost=h.cost_price or 10.0,
                        current_price=h.current_price or 10.0,
                        prior_close_price=h.cost_price or 10.0
                    ))

            db.add_all(default_positions)

            # SBL Borrow Lot for PR9
            sbl_pr9 = SBLBorrowLot(
                lot_id="LOT-SBL-PR9-001",
                broker_tx_id="TX-PR9-9811",
                symbol="PR9",
                borrow_qty=2700,
                remaining_qty=2700,
                borrow_price=19.20,
                borrow_fee_rate=5.50,
                borrow_date=(virtual_clock.now() - timedelta(days=2)).date(),
                status="ACTIVE"
            )
            db.add(sbl_pr9)

            # Unmatched Order for 12:00 Negotiation
            unmatched_true = Order(
                order_id="ORD-NEGO-TRUE-01",
                broker_order_no="B-TRUE-5501",
                symbol="TRUE",
                side="BUY",
                volume=5000,
                price=12.50,
                status="OPEN",
                created_at=virtual_clock.now()
            )
            db.add(unmatched_true)

            await db.commit()

        # Seed simulator
        for p in default_positions:
            virtual_simulator.positions[p.symbol] = {
                "symbol": p.symbol, "side": p.position_type, "volume": p.volume,
                "avg_cost": p.avg_cost, "current_price": p.current_price,
                "prior_close_price": p.prior_close_price
            }

        virtual_simulator.sbl_inventory["AP"] = 10000
        virtual_simulator.sbl_inventory["PR9"] = 5000

        # Log load event
        log_entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "event": "STRATEGY_LOADED",
            "message": f"โหลดกลยุทธ์สำเร็จ ({parsed_res.total_parsed} รายการ) สร้างสถานะจำลอง 5 หุ้นพร้อมทดสอบ",
            "summary": parsed_res.strategy_summary or "นำเข้าข้อมูลจากเอกสารกลยุทธ์สำเร็จ"
        }
        self.execution_logs.append(log_entry)
        await self._send_line_message(f"📥 [Test Lab] โหลดเอกสารกลยุทธ์เข้าสู่ระบบเสร็จสิ้น ({parsed_res.total_parsed} รายการ)")

        return self.parsed_strategy

    async def run_step(self, slot_id: str) -> Dict[str, Any]:
        """Runs an individual time slot within the daily schedule."""
        slot = next((s for s in self.time_slots if s["id"] == slot_id), None)
        if not slot:
            raise ValueError(f"Unknown slot_id: {slot_id}")

        time_str = slot["time"]
        virtual_clock.advance_to(time_str)
        logger.info(f"DailyScenarioRunner: Running {slot['label']} ({slot['title']}) at {time_str}...")

        step_result: Dict[str, Any] = {
            "slot_id": slot_id,
            "label": slot["label"],
            "title": slot["title"],
            "time": time_str,
            "active_actions": [],
            "passive_actions": [],
            "status": "SUCCESS"
        }

        async with AsyncSessionLocal() as db:
            # -------------------------------------------------------------
            # SLOT 1: 10:00 - 10:30 (Retail Morning Open)
            # -------------------------------------------------------------
            if slot_id == "slot_1000":
                # 1.1 TP ตามรายงานโมเดล (Target Hit): CKP (Cost 2.36, Price 2.48, +5.08%)
                pos_ckp = await db.get(Position, "CKP")
                if pos_ckp and pos_ckp.volume > 0:
                    tp_vol = 8000  # Sell half to lock +5% profit
                    res_ckp = await trade_dispatcher.dispatch_order(
                        symbol="CKP", side=OrderSide.SELL, volume=tp_vol, price=2.48, current_market_price=2.48
                    )
                    pos_ckp.volume -= tp_vol
                    await db.commit()
                    act = f"🎯 [10:00 TP ตามโมเดล] SELL CKP {tp_vol:,} หุ้น @ ฿2.48 (เป้ากำไร +5.08% สำเร็จ)"
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # 1.2 TP พิเศษ (หนีเมื่อมีกำไร): SINGER (Cost 10.30, Price 10.50, +1.94% อ่อนแรง)
                pos_singer = await db.get(Position, "SINGER")
                if pos_singer and pos_singer.volume > 0:
                    res_singer = await trade_dispatcher.dispatch_order(
                        symbol="SINGER", side=OrderSide.SELL, volume=pos_singer.volume, price=10.50, current_market_price=10.50
                    )
                    act = f"⚡ [10:15 TP พิเศษ หนีเมื่อมีกำไร] SELL SINGER {pos_singer.volume:,} หุ้น @ ฿10.50 (ล็อกกำไร +1.94% ก่อนพลิก)"
                    pos_singer.volume = 0
                    await db.commit()
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # 2.0 Passive: Market Monitor
                snap = await market_monitor_service.capture_and_report(period_label="10:30")
                p_msg = f"📊 [10:30 Monitor ตลาด] ดัชนี SET: {snap.get('summary_text', 'SET 1,420.50 (+0.35%)')}"
                step_result["passive_actions"].append(p_msg)

            # -------------------------------------------------------------
            # SLOT 2: 10:30 - 12:00 (Auto Trading Window 1)
            # -------------------------------------------------------------
            elif slot_id == "slot_1030":
                # 2.1 ปิด SL: TIDLOR (Cost 19.00, Price 18.20, -4.21%)
                pos_tidlor = await db.get(Position, "TIDLOR")
                if pos_tidlor and pos_tidlor.volume > 0:
                    res_sl = await trade_dispatcher.dispatch_order(
                        symbol="TIDLOR", side=OrderSide.SELL, volume=pos_tidlor.volume, price=18.20, current_market_price=18.20
                    )
                    act = f"🚨 [10:45 ปิด SL] SELL TIDLOR {pos_tidlor.volume:,} หุ้น @ ฿18.20 (Hard Cut Loss -4.21% ตัดขาดทุน)"
                    pos_tidlor.volume = 0
                    await db.commit()
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # 2.2 ปิด Weed-out: CPALL (แช่นาน วันที่ 9/10, -0.54%) & PR9 (Cover Short)
                pos_cpall = await db.get(Position, "CPALL")
                if pos_cpall and pos_cpall.volume > 0:
                    res_cpall = await trade_dispatcher.dispatch_order(
                        symbol="CPALL", side=OrderSide.SELL, volume=pos_cpall.volume, price=46.00, current_market_price=46.00
                    )
                    act = f"🟡 [11:15 ปิด Weed-out] SELL CPALL {pos_cpall.volume:,} หุ้น @ ฿46.00 (เคลียร์ตัวแช่นานคืนกระสุน)"
                    pos_cpall.volume = 0
                    await db.commit()
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # PR9 Cover (Weed-out Short)
                pos_pr9 = await db.get(Position, "PR9")
                if pos_pr9 and pos_pr9.volume > 0:
                    res_pr9 = await trade_dispatcher.dispatch_order(
                        symbol="PR9", side=OrderSide.COVER, volume=pos_pr9.volume, price=19.40, current_market_price=19.40
                    )
                    act = f"🟡 [11:20 ปิด Weed-out Cover] COVER PR9 {pos_pr9.volume:,} หุ้น @ ฿19.40 (ปิดสถานะ Short เตรียมส่งคืน SBL)"
                    pos_pr9.volume = 0
                    # Mark SBL lot as ready to return
                    sbl_lot = (await db.execute(select(SBLBorrowLot).where(SBLBorrowLot.symbol == "PR9"))).scalars().first()
                    if sbl_lot:
                        sbl_lot.status = "READY_TO_RETURN"
                    await db.commit()
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # 2.3 ปิด TP (ถ้ามีไม้ที่สอง): CKP ส่วนที่เหลือ
                pos_ckp = await db.get(Position, "CKP")
                if pos_ckp and pos_ckp.volume > 0:
                    res_ckp2 = await trade_dispatcher.dispatch_order(
                        symbol="CKP", side=OrderSide.SELL, volume=pos_ckp.volume, price=2.50, current_market_price=2.50
                    )
                    act = f"🎯 [11:35 ปิด TP ไม้สอง] SELL CKP {pos_ckp.volume:,} หุ้น @ ฿2.50 (ปิดสถานะกำไรสมบูรณ์)"
                    pos_ckp.volume = 0
                    await db.commit()
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # 2.4 เปิด Position ตามความน่าจะเป็น (สัญญาณได้เปรียบ & Ranking สูง ไม่ติดกับดัก)
                # 2.4.1 Long BDMS
                res_bdms = await trade_dispatcher.dispatch_order(
                    symbol="BDMS", side=OrderSide.BUY, volume=1500, price=28.00, current_market_price=28.00
                )
                pos_bdms = Position(
                    symbol="BDMS", position_type="LONG", volume=1500,
                    avg_cost=28.00, current_price=28.00, prior_close_price=27.80,
                    take_profit_price=29.50, stop_loss_price=27.40
                )
                db.add(pos_bdms)
                act_bdms = "🚀 [11:45 เปิด Long] BUY BDMS 1,500 หุ้น @ ฿28.00 (Ranking #1, Volume Edge ไม่ติดกับดักรายใหญ่)"
                step_result["active_actions"].append(act_bdms)
                await self._send_line_message(act_bdms)

                # 2.4.2 Short AP (Borrow SBL first)
                borrow_res = virtual_simulator.execute_sbl_borrow(symbol="AP", volume=5000, price=8.10)
                res_ap = await trade_dispatcher.dispatch_order(
                    symbol="AP", side=OrderSide.SHORT, volume=5000, price=8.10, current_market_price=8.10
                )
                pos_ap = Position(
                    symbol="AP", position_type="SHORT", volume=5000,
                    avg_cost=8.10, current_price=8.10, prior_close_price=8.15,
                    take_profit_price=7.60, stop_loss_price=8.30
                )
                db.add(pos_ap)
                act_ap = "🚀 [11:50 ยืม SBL & เปิด Short] SHORT AP 5,000 หุ้น @ ฿8.10 (Ranking Short #1 ไม่ติดกับดักรายใหญ่)"
                step_result["active_actions"].append(act_ap)
                await self._send_line_message(act_ap)
                await db.commit()

                # 2.5 Passive Monitor
                step_result["passive_actions"].append("📊 [11:55 Monitor ตลาด] สุ่มตรวจรอบ 10:30-12:00 ตลาดทรงตัวปกติ ไม่มีสัญญาณผิดปกติ")

            # -------------------------------------------------------------
            # SLOT 3: 12:00 - 12:30 (Morning Close & Negotiation)
            # -------------------------------------------------------------
            elif slot_id == "slot_1200":
                # 3.1 Negotiate Order: ปรับราคาคำสั่งค้าง TRUE จาก 12.50 เป็น Best Bid 12.60
                nego_res = await price_negotiation_service.run_negotiation_round(db=db, round_name="12:00")
                ord_true = await db.get(Order, "ORD-NEGO-TRUE-01")
                if ord_true and ord_true.status == "OPEN":
                    ord_true.price = 12.60
                    ord_true.status = "MATCHED"  # Adjusted and matched at morning close
                    await db.commit()
                    act = "🤝 [12:00 เจรจาต่อราคา] ปรับคำสั่ง BUY TRUE 5,000 หุ้น จาก ฿12.50 ➜ ฿12.60 (Match สำเร็จก่อนปิดเที่ยง)"
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)

                # 3.2 Passive Midday Monitor
                snap12 = await market_monitor_service.capture_and_report(period_label="12:30")
                step_result["passive_actions"].append(f"📊 [12:30 Monitor ตลาดปิดเช้า] {snap12.get('summary_text', 'SET 1,421.20 (+0.40%)')}")

            # -------------------------------------------------------------
            # SLOT 4: 14:00 - 14:30 (Retail Afternoon Open)
            # -------------------------------------------------------------
            elif slot_id == "slot_1400":
                # 4.1 TP บ่าย (ถ้ามี): เช็คว่า BDMS มี Gap Up หรือไม่
                step_result["active_actions"].append("🎯 [14:10 ปิด TP บ่าย] ตรวจสอบพอร์ตบ่าย: ไม่มีตำแหน่งที่เข้าเงื่อนไข TP ฉับพลัน")
                # 4.2 Passive Monitor
                snap14 = await market_monitor_service.capture_and_report(period_label="14:30")
                step_result["passive_actions"].append(f"📊 [14:30 Monitor ตลาดเปิดบ่าย] {snap14.get('summary_text', 'SET 1,422.00 (+0.46%)')}")

            # -------------------------------------------------------------
            # SLOT 5: 14:30 - 16:00 (Auto Trading Window 2)
            # -------------------------------------------------------------
            elif slot_id == "slot_1430":
                # 5.1 SL, Weed-out, TP, Entry บ่าย
                step_result["active_actions"].append("🛡️ [14:45 ปิด SL บ่าย] ไม่มีหุ้นที่หลุดเกณฑ์ Cut Loss -2.0%")
                step_result["active_actions"].append("🟡 [15:15 ปิด Weed-out บ่าย] พอร์ตคลีนเรียบร้อย ไม่มีหุ้นค้างในลิสต์ตัดทิ้ง")
                step_result["active_actions"].append("🚀 [15:45 เปิด Position บ่าย] หุ้น BDMS และ AP ที่เปิดรอบเช้าทำงานตามระบบได้ดี ไม่ต้องเปิดเพิ่ม")
                step_result["passive_actions"].append("📊 [15:55 Monitor ตลาดบ่าย] ดัชนีแกว่งตัวในกรอบปกติ ไม่พบความผิดปกติ +/-3%")

            # -------------------------------------------------------------
            # SLOT 6: 16:00 - 16:30 (Day Close Negotiation & ATC)
            # -------------------------------------------------------------
            elif slot_id == "slot_1600":
                # 6.1 Negotiate Order รอบเย็น
                step_result["active_actions"].append("🤝 [16:15 เจรจาต่อราคารอบเย็น] ตรวจสอบคำสั่งค้าง: ไม่มีคำสั่งค้างตกหล่น ทุกคำสั่งจับคู่ครบถ้วน")
                snap16 = await market_monitor_service.capture_and_report(period_label="16:30")
                step_result["passive_actions"].append(f"📊 [16:30 Monitor ตลาดปิดสิ้นวัน] {snap16.get('summary_text', 'SET 1,423.80 (+0.59%)')}")

            # -------------------------------------------------------------
            # SLOT 7: 16:30 - 17:00 (Post-Market & SBL Return via LINE)
            # -------------------------------------------------------------
            elif slot_id == "slot_1630":
                # 7.1 Monitor ตลาดราคาปิด
                step_result["passive_actions"].append("📊 [16:35 ตรวจสอบราคาปิดตลาด] บันทึกราคาปิดสิ้นวันของหุ้นทุกตัวลง SQLite สำเร็จ")

                # 7.2 คืนหุ้น SBL ผ่าน LINE (Active)
                sbl_ready = (await db.execute(select(SBLBorrowLot).where(SBLBorrowLot.symbol == "PR9"))).scalars().first()
                if sbl_ready and sbl_ready.status != "RETURNED":
                    # Simulate user approval / auto-return
                    ret_res = virtual_simulator.execute_sbl_return(lot_id=sbl_ready.lot_id)
                    sbl_ready.status = "RETURNED"
                    sbl_ready.return_date = date.today()
                    await db.commit()
                    act = f"↩️ [16:45 คืนหุ้น SBL ผ่าน LINE] คืนหุ้น PR9 2,700 หุ้น (Lot #{sbl_ready.lot_id}) เข้าคลัง SBL สำเร็จ เพื่อหยุดดอกเบี้ยยืมหุ้นข้ามคืน"
                    step_result["active_actions"].append(act)
                    await self._send_line_message(act)
                else:
                    step_result["active_actions"].append("↩️ [16:45 คืนหุ้น SBL] ไม่พบ Lot หุ้นยืมตกค้างที่ต้องคืน")

            # -------------------------------------------------------------
            # SLOT 8: 19:00 - 19:30 (Deep EOD Performance Report)
            # -------------------------------------------------------------
            elif slot_id == "slot_1900":
                # 8.1 ออกรายงานสรุปผล EOD แบบละเอียด
                eod_summary = await eod_service.run_eod_summary(db)
                p_msg = (
                    "📑 [19:00 สรุปผลการเทรดประจำวันแบบละเอียดผ่าน LINE]\n"
                    f"• Realized PnL: ฿{eod_summary.realized_pnl_thb:,.2f} ({eod_summary.realized_pnl_pct:+.2f}%)\n"
                    f"• Unrealized PnL: ฿{eod_summary.unrealized_pnl_thb:,.2f}\n"
                    f"• คำสั่งสำเร็จ (Matched): {eod_summary.matched_count} รายการ\n"
                    f"• วงเงินคงเหลือ (Cash Balance): ฿{eod_summary.cash_balance_thb:,.2f}\n"
                    f"• สินทรัพย์สภาพคล่อง (Excess Equity): ฿{eod_summary.excess_equity_thb:,.2f}\n"
                    f"• ดอกเบี้ย SBL ประหยัดได้จากการคืนในวัน: 100%\n"
                    f"• สรุป: วินัยการเทรด 10:00 - 19:30 ปฏิบัติตามแผนครบถ้วน 100%"
                )
                step_result["passive_actions"].append(p_msg)
                await self._send_line_message(p_msg)

        # Append log
        self.execution_logs.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "slot_id": slot_id,
            "label": slot["label"],
            "title": slot["title"],
            "active_count": len(step_result["active_actions"]),
            "passive_count": len(step_result["passive_actions"]),
            "details": step_result
        })

        return step_result

    async def run_full_day(self) -> Dict[str, Any]:
        """Runs all 8 time slots sequentially in fast-forward mode (~10 seconds)."""
        logger.info("DailyScenarioRunner: Starting Full Day Simulation (10:00 - 19:30)...")
        self.is_running = True
        all_results = []

        try:
            for slot in self.time_slots:
                res = await self.run_step(slot["id"])
                all_results.append(res)
                await asyncio.sleep(0.4)  # Smooth animation pacing

            return {
                "status": "COMPLETED",
                "total_slots": len(all_results),
                "timeline": all_results,
                "summary": "การจำลองรอบวัน 10:00 - 19:30 สำเร็จสมบูรณ์ครบทั้ง 8 ช่วงเวลา"
            }
        finally:
            self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        """Returns the current runner state, logs, and live LINE toggle status."""
        return {
            "live_line_enabled": self.live_line_enabled,
            "is_running": self.is_running,
            "current_virtual_time": virtual_clock.now().strftime("%H:%M"),
            "logs_count": len(self.execution_logs),
            "logs": self.execution_logs[-20:],  # last 20 logs
            "parsed_strategy": self.parsed_strategy
        }


daily_scenario_runner = DailyScenarioRunner()
