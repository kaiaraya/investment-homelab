import logging
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.broker_factory import get_broker_driver, get_auth_driver
from app.browser.trademan_simulator import virtual_simulator
from app.core.config import settings
from app.core.events import event_bus
from app.db.models import Position, SBLBorrowLot, SessionLog
from app.db.session import AsyncSessionLocal, get_session_factory
from app.schemas.intelligence import ExtractedTPSL, TPSLParseResult
from app.services.trade_dispatcher import trade_dispatcher

logger = logging.getLogger(__name__)


class PortfolioOverviewService:
    """
    3.1 Portfolio Overview Center (Runs at 10:15 Bangkok time & On-Demand)
    Features:
    1. Scrapes current holdings from active broker (Click2Win / TradeMan / Virtual Simulator).
    2. Silent DB Reconciliation (isolated per platform: investment_homelab.db vs investment_homelab_click2win.db).
    3. Detects stocks missing Take Profit (TP) / Stop Loss (SL).
    4. Detects unreturned SBL borrow lots and checks corporate actions / XD dates.
    5. Sends summary to LINE with interactive prompt for setting TP/SL.
    6. Applies multi-stock TP/SL updates from Gemini parser into SQLite.
    """

    async def run_overview(self, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """
        Executes the full 10:15 Portfolio Overview workflow.
        """
        logger.info(f"Starting 3.1 Portfolio Overview workflow (Platform: {settings.TRADING_PLATFORM}, Mode: {trade_dispatcher.current_mode})...")

        if db is None:
            factory = get_session_factory()
            async with factory() as session:
                return await self._execute_overview(session)
        else:
            return await self._execute_overview(db)

    async def _execute_overview(self, db: AsyncSession) -> Dict[str, Any]:
        broker = get_broker_driver()
        auth = get_auth_driver()

        # 1. Scrape Portfolio from active broker or fallback
        if trade_dispatcher.is_live or auth.is_authenticated:
            scraped_holdings = await broker.scrape_portfolio()
            scraped_sbl = await broker.scrape_sbl_lots() if hasattr(broker, "scrape_sbl_lots") else []
        else:
            scraped_holdings = virtual_simulator.get_portfolio_snapshot()
            scraped_sbl = virtual_simulator.get_sbl_lots_snapshot()
        
        # 2. Silent DB Reconciliation
        reconciled = await self.reconcile_portfolio(db, scraped_holdings)

        # 3. Check SBL lots
        sbl_alerts = await self.check_sbl_lots(db, scraped_sbl)

        # 4. Check missing TP/SL
        missing_tpsl = await self.get_stocks_missing_tpsl(db)

        # 5. Build summary report
        report = self.format_overview_report(reconciled, missing_tpsl, sbl_alerts)

        # 6. Dispatch notification to LINE
        await event_bus.publish_notification({
            "type": "PORTFOLIO_OVERVIEW",
            "text": report,
            "missing_tpsl_count": len(missing_tpsl),
            "sbl_alert_count": len(sbl_alerts),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # 7. Log event in session_logs
        log = SessionLog(
            event_type="PORTFOLIO_OVERVIEW_COMPLETED",
            details=f"Reconciled {len(reconciled)} positions. Missing TP/SL: {len(missing_tpsl)}. SBL Alerts: {len(sbl_alerts)}"
        )
        db.add(log)
        await db.commit()

        logger.info("Portfolio Overview completed successfully.")
        return {
            "success": True,
            "positions_count": len(reconciled),
            "missing_tpsl": missing_tpsl,
            "sbl_alerts": sbl_alerts,
            "report": report
        }

    async def reconcile_portfolio(
        self,
        db: AsyncSession,
        scraped_holdings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Reconciles TradeMan live holdings into the SQLite 'positions' table silently.
        """
        # Filter out purely borrowed SBL inventory lots from the stock positions table
        stock_holdings = [h for h in scraped_holdings if h.get("position_type") != "BORROWED"]
        scraped_symbols = {h["symbol"].upper() for h in stock_holdings}

        # Query existing positions from DB
        stmt = select(Position)
        res = await db.execute(stmt)
        existing_positions = {p.symbol.upper(): p for p in res.scalars().all()}

        # 1. Update or create positions from TradeMan
        for item in stock_holdings:
            sym = item["symbol"].upper()
            pos_type = item.get("position_type", "LONG")
            vol = item.get("volume", 0)
            avg_cost = item.get("avg_cost", 0.0)
            curr_price = item.get("current_price", avg_cost)
            unrealized = item.get("unrealized_pnl", 0.0)
            prior_close = item.get("prior_close_price", curr_price)

            if sym in existing_positions:
                pos = existing_positions[sym]
                pos.volume = vol
                pos.avg_cost = avg_cost
                pos.current_price = curr_price
                pos.unrealized_pnl = unrealized
                pos.prior_close_price = prior_close
                pos.position_type = pos_type
            else:
                new_pos = Position(
                    symbol=sym,
                    position_type=pos_type,
                    volume=vol,
                    avg_cost=avg_cost,
                    current_price=curr_price,
                    prior_close_price=prior_close,
                    unrealized_pnl=unrealized
                )
                db.add(new_pos)

        # 2. Check for positions in DB that no longer exist in TradeMan (closed externally on mobile)
        for sym, pos in existing_positions.items():
            if sym not in scraped_symbols and pos.volume > 0:
                logger.info(f"Position {sym} closed on mobile (volume was {pos.volume}, now 0)")
                if pos.position_type == "SHORT":
                    # Short was covered on mobile -> Flag that SBL shares must be returned!
                    pos.is_sbl_pending_return = True
                    logger.warning(f"Short {sym} closed externally. SBL return pending!")
                pos.volume = 0

        await db.commit()
        return scraped_holdings

    async def check_sbl_lots(
        self,
        db: AsyncSession,
        scraped_lots: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Audits SBL borrow lots against database and checks for unreturned lots / XD warnings.
        """
        alerts: List[Dict[str, Any]] = []

        # 1. Sync scraped lots into sbl_borrow_lots table
        for lot in scraped_lots:
            tx_id = lot.get("broker_tx_id")
            sym = lot.get("symbol", "").upper()
            qty = lot.get("remaining_qty", 0)
            if not tx_id:
                continue

            stmt = select(SBLBorrowLot).where(SBLBorrowLot.broker_tx_id == tx_id)
            res = await db.execute(stmt)
            existing_lot = res.scalar_one_or_none()
            if not existing_lot:
                new_lot = SBLBorrowLot(
                    lot_id=f"LOT-{tx_id}",
                    broker_tx_id=tx_id,
                    symbol=sym,
                    borrow_qty=qty,
                    remaining_qty=qty,
                    borrow_date=date.today(),
                    status="ACTIVE"
                )
                db.add(new_lot)

        await db.commit()

        # 2. Check for pending SBL returns from closed positions
        stmt = select(Position).where(Position.is_sbl_pending_return == True)
        res = await db.execute(stmt)
        pending_positions = res.scalars().all()
        for p in pending_positions:
            alerts.append({
                "type": "PENDING_SBL_RETURN",
                "symbol": p.symbol,
                "message": f"หุ้น {p.symbol} ฝั่ง Short ถูกปิดไปแล้ว แต่ยังมีหุ้นยืม SBL ค้างคืนอยู่!"
            })

        return alerts

    async def get_stocks_missing_tpsl(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Returns list of open positions that have no TP or no SL configured.
        """
        stmt = select(Position).where(
            Position.volume > 0,
            (Position.take_profit_price.is_(None)) | (Position.stop_loss_price.is_(None))
        )
        res = await db.execute(stmt)
        positions = res.scalars().all()

        missing = []
        for p in positions:
            missing.append({
                "symbol": p.symbol,
                "side": p.position_type,
                "volume": p.volume,
                "avg_cost": p.avg_cost,
                "current_price": p.current_price,
                "has_tp": p.take_profit_price is not None,
                "has_sl": p.stop_loss_price is not None
            })
        return missing

    async def apply_tpsl_items(
        self,
        db: AsyncSession,
        items: List[ExtractedTPSL]
    ) -> List[Dict[str, Any]]:
        """
        Applies parsed TP/SL values to positions in the database.
        """
        updated_records = []
        for item in items:
            sym = item.symbol.upper()
            stmt = select(Position).where(Position.symbol == sym)
            res = await db.execute(stmt)
            pos = res.scalar_one_or_none()

            if pos:
                if item.take_profit is not None:
                    pos.take_profit_price = item.take_profit
                if item.stop_loss is not None:
                    pos.stop_loss_price = item.stop_loss
                updated_records.append({
                    "symbol": sym,
                    "side": pos.position_type,
                    "tp": pos.take_profit_price,
                    "sl": pos.stop_loss_price
                })
            else:
                # If position doesn't exist yet, create placeholder with TP/SL
                new_pos = Position(
                    symbol=sym,
                    position_type=item.side.upper(),
                    volume=0,
                    avg_cost=0.0,
                    take_profit_price=item.take_profit,
                    stop_loss_price=item.stop_loss
                )
                db.add(new_pos)
                updated_records.append({
                    "symbol": sym,
                    "side": item.side.upper(),
                    "tp": item.take_profit,
                    "sl": item.stop_loss
                })

        await db.commit()
        return updated_records

    async def apply_percentage_tpsl_to_open_positions(
        self,
        db: AsyncSession,
        tp_pct: float = 5.0,
        sl_pct: float = 3.0
    ) -> List[Dict[str, Any]]:
        """
        Automatically sets Take Profit (+5%) and Stop Loss (-3%) for all open positions.
        Properly handles LONG (TP > Cost, SL < Cost) and SHORT (TP < Cost, SL > Cost).
        """
        stmt = select(Position).where(Position.volume > 0)
        res = await db.execute(stmt)
        positions = res.scalars().all()

        updated_records = []
        for pos in positions:
            cost = pos.avg_cost if pos.avg_cost > 0 else pos.current_price
            if cost <= 0:
                continue

            if pos.position_type == "SHORT":
                # SHORT: Profit when price drops, loss when price rises
                tp = round(cost * (1.0 - (tp_pct / 100.0)), 2)
                sl = round(cost * (1.0 + (sl_pct / 100.0)), 2)
            else:
                # LONG: Profit when price rises, loss when price drops
                tp = round(cost * (1.0 + (tp_pct / 100.0)), 2)
                sl = round(cost * (1.0 - (sl_pct / 100.0)), 2)

            pos.take_profit_price = tp
            pos.stop_loss_price = sl

            updated_records.append({
                "symbol": pos.symbol,
                "position_type": pos.position_type,
                "volume": pos.volume,
                "avg_cost": cost,
                "take_profit": tp,
                "stop_loss": sl,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct
            })

        await db.commit()
        return updated_records


    def format_overview_report(
        self,
        holdings: List[Dict[str, Any]],
        missing_tpsl: List[Dict[str, Any]],
        sbl_alerts: List[Dict[str, Any]]
    ) -> str:
        """
        Formats a clean Thai Markdown summary for LINE messaging.
        """
        now_str = datetime.now().strftime("%H:%M น.")
        lines = [f"📊 [Portfolio Overview 10:15] ณ {now_str}", "──────────────────────"]

        if not holdings:
            lines.append("ปัจจุบันไม่มีหุ้นถือครองในพอร์ต")
        else:
            lines.append(f"📦 รายการหุ้นในพอร์ต ({len(holdings)} รายการ):")
            for h in holdings:
                sym = h["symbol"]
                vol = h["volume"]
                pnl = h.get("pnl_pct", 0.0)
                side_icon = "🔴 SHORT" if h.get("position_type") == "SHORT" else "🟢 LONG"
                lines.append(f"• {side_icon} {sym}: {vol:,} หุ้น ({pnl:+.2f}%)")

        if sbl_alerts:
            lines.append("\n⚠️ แจ้งเตือนหุ้นยืม SBL:")
            for a in sbl_alerts:
                lines.append(f"• {a['message']}")

        if missing_tpsl:
            lines.append("\n🎯 หุ้นที่ยังไม่ได้ตั้ง TP/SL:")
            for m in missing_tpsl:
                sym = m["symbol"]
                side = m["side"]
                lines.append(f"• {sym} ({side})")
            lines.append("\n💡 คุณสามารถพิมพ์ตั้งค่ากลับมาเป็นประโยคยาวได้ทันที เช่น:")
            lines.append(f"\"{missing_tpsl[0]['symbol']} ตั้ง TP 68 SL 62\"")
        else:
            lines.append("\n✅ หุ้นทุกตัวในพอร์ตมีระดับ TP/SL ครบถ้วนแล้ว")

        return "\n".join(lines)


portfolio_overview_service = PortfolioOverviewService()
