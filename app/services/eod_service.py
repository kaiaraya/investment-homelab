import logging
from datetime import datetime, date, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import event_bus
from app.db.models import Order, Position, SBLBorrowLot, SessionLog
from app.db.session import AsyncSessionLocal
from app.schemas.intelligence import EODReportSummary, EODOrderItem, SBLHoldingItem
from app.browser.trademan_simulator import virtual_simulator
from app.browser.trademan_driver import trademan_driver
from app.services.trade_dispatcher import trade_dispatcher

logger = logging.getLogger(__name__)


class EndOfDayService:
    """
    3.5 & Phase 4: End-of-Day (EOD) Closing & Financial Reconciliation Engine.
    Triggered daily at 16:35 Bangkok time (Market Close).
    Compiles:
    1. Order Execution Breakdown: Succeeded vs Failed/Unmatched, with itemized breakdown
    2. Daily Realized PnL & Portfolio Unrealized PnL
    3. Account Purchasing Power: Excess Equity (EE) & Cash Balance
    4. SBL Borrowed Stocks, Days Held, Accrued Fees & XD Warnings
    5. Dispatches Comprehensive LINE Summary Report
    """

    async def run_eod_summary(self, db: Optional[AsyncSession] = None) -> EODReportSummary:
        """Executes the full 16:35 EOD reporting cycle."""
        logger.info(f"Generating 16:35 End-of-Day (EOD) Summary Report (Mode: {trade_dispatcher.current_mode})...")

        if db is None:
            async with AsyncSessionLocal() as session:
                return await self._process_eod(session)
        else:
            return await self._process_eod(db)

    async def _process_eod(self, db: AsyncSession) -> EODReportSummary:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M น.")
        today_date = date.today()

        # 1. Fetch Orders executed today
        # NOTE: Order.created_at is stored in UTC (SQLite func.now() == CURRENT_TIMESTAMP),
        # so the "today" boundary must ALSO be UTC. Using local midnight (date.today())
        # breaks between 00:00-06:59 BKK when the local date leads UTC by one day and
        # freshly-created orders get filtered out (timezone bug).
        today_start_utc = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        )
        stmt_orders = select(Order).where(Order.created_at >= today_start_utc).order_by(desc(Order.created_at))
        res_orders = await db.execute(stmt_orders)
        all_orders = res_orders.scalars().all()

        matched_orders: List[EODOrderItem] = []
        unmatched_orders: List[EODOrderItem] = []

        for ord in all_orders:
            item = EODOrderItem(
                symbol=ord.symbol,
                side=ord.side,
                volume=ord.volume,
                price=ord.price,
                status=ord.status,
                broker_order_no=ord.broker_order_no,
                failure_reason=ord.error_message,
                created_at=ord.created_at.strftime("%H:%M:%S") if ord.created_at else None
            )
            if ord.status in ["MATCHED", "FILLED"]:
                matched_orders.append(item)
            else:
                unmatched_orders.append(item)

        # 2. Financial Metrics: Realized & Unrealized PnL
        stmt_positions = select(Position).where(Position.volume > 0)
        res_positions = await db.execute(stmt_positions)
        positions = res_positions.scalars().all()

        total_unrealized_pnl = 0.0
        for pos in positions:
            curr_px = pos.current_price or pos.avg_cost
            if pos.position_type == "LONG":
                unrealized = (curr_px - pos.avg_cost) * pos.volume
            else:
                unrealized = (pos.avg_cost - curr_px) * pos.volume
            total_unrealized_pnl += unrealized

        # Realized PnL today
        if trade_dispatcher.is_live:
            # Live TradeMan scraping
            account_summary = await trademan_driver.scrape_account_summary()
            excess_equity = account_summary.get("excess_equity", 0.0)
            cash_balance = account_summary.get("cash_balance", 0.0)
            realized_pnl_today = account_summary.get("realized_pnl_today", 0.0)
        else:
            sim_summary = virtual_simulator.get_account_summary()
            excess_equity = sim_summary.get("excess_equity", 500_000.0)
            cash_balance = sim_summary.get("cash_balance", 500_000.0)
            realized_pnl_today = sim_summary.get("realized_pnl_today", 0.0)

        # 3. SBL Active Lots & Accrued Fees
        stmt_sbl = select(SBLBorrowLot).where(SBLBorrowLot.remaining_qty > 0)
        res_sbl = await db.execute(stmt_sbl)
        sbl_lots = res_sbl.scalars().all()

        sbl_holdings: List[SBLHoldingItem] = []
        for lot in sbl_lots:
            b_date = lot.borrow_date if isinstance(lot.borrow_date, date) else today_date
            days_held = max(1, (today_date - b_date).days)
            ref_px = lot.borrow_price or 10.0
            daily_rate = (lot.borrow_fee_rate / 100.0) / 365.0
            accrued = lot.remaining_qty * ref_px * daily_rate * days_held

            xd_warning = None
            if lot.ex_dividend_date:
                days_to_xd = (lot.ex_dividend_date - today_date).days
                if 0 <= days_to_xd <= 3:
                    xd_warning = f"⚠️ หุ้นขึ้นเครื่องหมาย XD ในอีก {days_to_xd} วัน ({lot.ex_dividend_date}) ต้องคืนด่วน!"

            sbl_holdings.append(SBLHoldingItem(
                symbol=lot.symbol,
                borrowed_volume=lot.remaining_qty,
                borrow_date=str(lot.borrow_date),
                days_held=days_held,
                accrued_fee_thb=round(accrued, 2),
                ex_dividend_warning=xd_warning
            ))

        # 4. Compile Summary Object
        summary = EODReportSummary(
            report_time=now_str,
            total_orders=len(all_orders),
            matched_count=len(matched_orders),
            failed_or_unmatched_count=len(unmatched_orders),
            orders_matched=matched_orders,
            orders_unmatched=unmatched_orders,
            realized_pnl_thb=round(realized_pnl_today, 2),
            unrealized_pnl_thb=round(total_unrealized_pnl, 2),
            excess_equity_thb=round(excess_equity, 2),
            cash_balance_thb=round(cash_balance, 2),
            sbl_holdings=sbl_holdings,
            strategy_notes=f"โหมด: {trade_dispatcher.current_mode} | สรุปเวลาตลาดปิด 16:35 น."
        )

        # 5. Build and Dispatch LINE Notification
        flex_card = self._build_eod_flex_card(summary)
        await event_bus.publish_notification(flex_card)

        # 6. Audit Trail
        log = SessionLog(
            event_type="EOD_REPORT_GENERATED",
            details=(
                f"EOD 16:35 Generated. Orders: {summary.matched_count}/{summary.total_orders} Matched, "
                f"Realized PnL: ฿{summary.realized_pnl_thb:,.2f}, EE: ฿{summary.excess_equity_thb:,.2f}"
            )
        )
        db.add(log)
        await db.commit()

        logger.info(f"EOD Report published successfully. EE: ฿{summary.excess_equity_thb:,.2f}")
        return summary

    def _build_eod_flex_card(self, summary: EODReportSummary) -> Dict[str, Any]:
        """Formats the EOD report as an executive LINE Flex Message."""
        # Order rows
        order_rows = []
        if summary.orders_matched:
            for o in summary.orders_matched[:5]:
                order_rows.append({
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"✅ {o.side} {o.symbol}", "size": "xs", "weight": "bold", "color": "#10b981", "flex": 4},
                        {"type": "text", "text": f"{o.volume:,} @ ฿{o.price:.2f}", "size": "xs", "color": "#334155", "align": "end", "flex": 5}
                    ]
                })

        if summary.orders_unmatched:
            for o in summary.orders_unmatched[:3]:
                order_rows.append({
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"❌ {o.side} {o.symbol}", "size": "xs", "weight": "bold", "color": "#ef4444", "flex": 4},
                        {"type": "text", "text": f"{o.status} ({o.volume:,})", "size": "xs", "color": "#94a3b8", "align": "end", "flex": 5}
                    ]
                })

        pnl_color = "#10b981" if summary.realized_pnl_thb >= 0 else "#ef4444"
        pnl_sign = "+" if summary.realized_pnl_thb >= 0 else ""

        body_contents = [
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#f8fafc",
                "paddingAll": "sm",
                "cornerRadius": "md",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "💳 วงเงินคงเหลือ (Excess Equity):", "size": "xs", "color": "#475569", "flex": 6},
                            {"type": "text", "text": f"฿{summary.excess_equity_thb:,.2f}", "size": "sm", "weight": "bold", "color": "#0284c7", "align": "end", "flex": 5}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "xs",
                        "contents": [
                            {"type": "text", "text": "💵 เงินสด (Cash Balance):", "size": "xs", "color": "#64748b", "flex": 6},
                            {"type": "text", "text": f"฿{summary.cash_balance_thb:,.2f}", "size": "xs", "color": "#334155", "align": "end", "flex": 5}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "xs",
                        "contents": [
                            {"type": "text", "text": "💰 Realized PnL วันนี้:", "size": "xs", "color": "#64748b", "flex": 6},
                            {"type": "text", "text": f"{pnl_sign}฿{summary.realized_pnl_thb:,.2f}", "size": "xs", "weight": "bold", "color": pnl_color, "align": "end", "flex": 5}
                        ]
                    }
                ]
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "text",
                "text": f"📊 ผลการส่งคำสั่ง ({summary.matched_count}/{summary.total_orders} สำเร็จ):",
                "size": "xs",
                "weight": "bold",
                "color": "#0f172a",
                "margin": "sm"
            },
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "margin": "xs",
                "contents": order_rows or [{"type": "text", "text": "ไม่มีคำสั่งซื้อขายในวันนี้", "size": "xs", "color": "#94a3b8"}]
            }
        ]

        # SBL summary section
        if summary.sbl_holdings:
            sbl_rows = []
            for s in summary.sbl_holdings[:3]:
                sbl_rows.append({
                    "type": "text",
                    "text": f"• {s.symbol}: ยืม {s.borrowed_volume:,} หุ้น (ถือ {s.days_held} วัน | ดอกเบี้ยสะสม ฿{s.accrued_fee_thb:,.2f})",
                    "size": "xxs",
                    "color": "#475569"
                })
                if s.ex_dividend_warning:
                    sbl_rows.append({
                        "type": "text",
                        "text": s.ex_dividend_warning,
                        "size": "xxs",
                        "color": "#b45309",
                        "weight": "bold"
                    })

            body_contents.append({"type": "separator", "margin": "sm"})
            body_contents.append({
                "type": "text",
                "text": "📦 รายการหุ้นยืม SBL คงค้าง:",
                "size": "xs",
                "weight": "bold",
                "color": "#0f172a",
                "margin": "xs"
            })
            body_contents.append({
                "type": "box",
                "layout": "vertical",
                "spacing": "xxs",
                "contents": sbl_rows
            })

        return {
            "type": "flex",
            "altText": f"🌇 สรุปผลการเทรดสิ้นวัน (EOD 16:35) | EE: ฿{summary.excess_equity_thb:,.2f}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#0f172a",
                    "contents": [
                        {"type": "text", "text": "🌇 สรุปผลการเทรดสิ้นวัน (EOD Report)", "weight": "bold", "size": "sm", "color": "#f59e0b"},
                        {"type": "text", "text": f"เวลา {summary.report_time} (ตลาดปิด)", "size": "xxs", "color": "#94a3b8", "margin": "xs"}
                    ]
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": body_contents
                }
            }
        }


eod_service = EndOfDayService()
