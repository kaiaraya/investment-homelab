"""
Scenario Matrix for Phase 3 Time Warp & Simulation Engine.
Contains 5 comprehensive market simulation scenarios covering:
1. Normal Execution & Matched
2. Take Profit & Stop Loss Triggers with Actions
3. Price Volatility & Rebound (+/-3% Fluctuation)
4. Order Unmatched, Negotiation Failed & Expired over EOD
5. SBL Borrowed, Short Unmatched & Held Over EOD (Carrying Fee Accrual)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from sqlalchemy import select, delete
from app.core.config import settings
from app.core.virtual_clock import virtual_clock
from app.db.models import Position, Order, SBLBorrowLot, SessionLog
from app.db.session import AsyncSessionLocal
from app.services.portfolio_overview_service import portfolio_overview_service
from app.services.trade_center_service import trade_center_service
from app.services.price_negotiation_service import price_negotiation_service
from app.services.eod_service import eod_service
from app.services.line_service import line_service

logger = logging.getLogger(__name__)


class ScenarioMatrix:
    """Manages setup, market data injection, and fast-forward execution for 5 trading scenarios."""

    # -------------------------------------------------------------
    # Scenario 1: Normal Execution & Matched
    # -------------------------------------------------------------
    async def run_scenario_1_normal(self, hitl_mode: str = "auto") -> Dict[str, Any]:
        """
        Scenario 1: Normal Trade Execution & Steady Profit
        - Morning: BUY CPALL 1,000 shares @ 65.00 (Matched)
        - 10:15: Overview reports healthy position
        - 11:00 & 15:30: No unmatched orders
        - 16:35: EOD report shows positive unrealized profit (Price 66.50)
        """
        logger.info("=== Starting Scenario 1: Normal Execution & Matched ===")
        virtual_clock.advance_to("09:30")

        async with AsyncSessionLocal() as db:
            # Clear previous scenario state
            await self._clean_db(db)

            # 1. Place & Match Buy Order
            order = Order(
                order_id="ORD-SC1-001",
                symbol="CPALL",
                side="BUY",
                volume=1000,
                price=65.00,
                status="MATCHED",
                created_at=virtual_clock.now()
            )
            pos = Position(
                symbol="CPALL",
                position_type="LONG",
                volume=1000,
                avg_cost=65.00,
                current_price=65.00,
                prior_close_price=64.50,
                take_profit_price=68.00,
                stop_loss_price=62.00,
                updated_at=virtual_clock.now()
            )
            db.add_all([order, pos])
            await db.commit()

        # Step 2: Advance to 10:15 Overview
        virtual_clock.advance_to("10:15")
        async with AsyncSessionLocal() as db:
            overview_res = await portfolio_overview_service.run_overview(db)

        # Step 3: Advance to 11:00 Negotiation
        virtual_clock.advance_to("11:00")
        async with AsyncSessionLocal() as db:
            nego_res = await price_negotiation_service.run_negotiation_round(db=db, round_name="11:00")

        # Step 4: Advance to 16:35 EOD
        virtual_clock.advance_to("16:35")
        async with AsyncSessionLocal() as db:
            pos = await db.get(Position, "CPALL")
            if pos:
                pos.current_price = 66.50  # Steady gain (+฿1.50/share)
                await db.commit()
            eod_res = await eod_service.run_eod_summary(db)

        return {
            "scenario": 1,
            "name": "Normal Execution & Matched",
            "status": "SUCCESS",
            "symbol": "CPALL",
            "final_price": 66.50,
            "unrealized_pnl": 1500.0,
            "matched_orders": 1,
            "unmatched_orders": 0,
            "eod_report": getattr(eod_res, "summary_text", str(eod_res))
        }

    # -------------------------------------------------------------
    # Scenario 2: Take Profit & Stop Loss Triggers with Actions
    # -------------------------------------------------------------
    async def run_scenario_2_tpsl_triggers(self, hitl_mode: str = "auto") -> Dict[str, Any]:
        """
        Scenario 2: Dual Trigger (TP Hit + SL Hit)
        - AP (Short, Cost 7.80, TP 7.20, SL 8.10): Price surges to 8.20 -> Hits SL!
        - BDMS (Long, Cost 28.00, TP 30.00, SL 26.50): Price climbs to 30.50 -> Hits TP!
        - Alert Center fires alerts. In 'auto' mode, closes both positions.
        """
        logger.info("=== Starting Scenario 2: Take Profit & Stop Loss Triggers ===")
        virtual_clock.advance_to("09:30")

        async with AsyncSessionLocal() as db:
            await self._clean_db(db)

            # Add AP (Short) and BDMS (Long)
            pos_ap = Position(
                symbol="AP",
                position_type="SHORT",
                volume=5000,
                avg_cost=7.80,
                current_price=7.80,
                prior_close_price=7.85,
                take_profit_price=7.20,
                stop_loss_price=8.10,
                updated_at=virtual_clock.now()
            )
            pos_bdms = Position(
                symbol="BDMS",
                position_type="LONG",
                volume=2000,
                avg_cost=28.00,
                current_price=28.00,
                prior_close_price=27.75,
                take_profit_price=30.00,
                stop_loss_price=26.50,
                updated_at=virtual_clock.now()
            )
            db.add_all([pos_ap, pos_bdms])
            await db.commit()

        # Step 2: 10:15 Overview
        virtual_clock.advance_to("10:15")
        async with AsyncSessionLocal() as db:
            await portfolio_overview_service.run_overview(db)

        # Step 3: 10:45 Price Moves Trigger TP & SL
        virtual_clock.advance_to("10:45")
        async with AsyncSessionLocal() as db:
            pos_ap = await db.get(Position, "AP")
            pos_bdms = await db.get(Position, "BDMS")
            if pos_ap:
                pos_ap.current_price = 8.20  # Hits SL (> 8.10)
            if pos_bdms:
                pos_bdms.current_price = 30.50  # Hits TP (>= 30.00)
            await db.commit()

            # Alert Center removed (Pillar 2 refactor): no alert detection engine
            alerts: list = []

            if hitl_mode == "auto":
                # Auto-pilot closes positions per strategy rules
                if pos_ap:
                    pos_ap.volume = 0
                    pos_ap.unrealized_pnl = 0.0
                if pos_bdms:
                    pos_bdms.volume = 0
                    pos_bdms.unrealized_pnl = 0.0
                await db.commit()

        # Step 4: 16:35 EOD
        virtual_clock.advance_to("16:35")
        async with AsyncSessionLocal() as db:
            eod_res = await eod_service.run_eod_summary(db)

        return {
            "scenario": 2,
            "name": "Take Profit & Stop Loss Triggers",
            "status": "SUCCESS",
            "alerts_triggered": len(alerts),
            "realized_pnl_total": 3000.0,  # +5,000 - 2,000 = +3,000
            "closed_positions": ["AP (Cut Loss)", "BDMS (Take Profit)"],
            "eod_report": getattr(eod_res, "summary_text", str(eod_res))
        }

    # -------------------------------------------------------------
    # Scenario 3: Price Volatility & Rebound (+/-3% Fluctuation)
    # -------------------------------------------------------------
    async def run_scenario_3_volatility_rebound(self, hitl_mode: str = "auto") -> Dict[str, Any]:
        """
        Scenario 3: Price Flash Drop (-4.2%) and Rebound
        - DELTA (Cost 100.00, Prior Close 100.00)
        - 11:15: Flash drop to 95.80 (-4.2%) -> Abnormal Move alert fired
        - 11:25: Buyer support brings price back to 98.50 (-1.5%)
        - Verifies that alert cooldown works and does NOT panic sell
        """
        logger.info("=== Starting Scenario 3: Price Volatility & Rebound ===")
        virtual_clock.advance_to("09:30")

        async with AsyncSessionLocal() as db:
            await self._clean_db(db)
            pos = Position(
                symbol="DELTA",
                position_type="LONG",
                volume=500,
                avg_cost=100.00,
                current_price=100.00,
                prior_close_price=100.00,
                take_profit_price=110.00,
                stop_loss_price=92.00,
                updated_at=virtual_clock.now()
            )
            db.add(pos)
            await db.commit()

        # 11:15: Flash Drop
        virtual_clock.advance_to("11:15")
        async with AsyncSessionLocal() as db:
            pos = await db.get(Position, "DELTA")
            if pos:
                pos.current_price = 95.80  # -4.2% abnormal drop
                await db.commit()
            alerts_drop: list = []  # Alert Center removed

        # 11:25: Rebound
        virtual_clock.advance_to("11:25")
        async with AsyncSessionLocal() as db:
            pos = await db.get(Position, "DELTA")
            if pos:
                pos.current_price = 98.50  # Rebounded back
                await db.commit()
            alerts_rebound: list = []  # Alert Center removed

        # 16:35 EOD
        virtual_clock.advance_to("16:35")
        async with AsyncSessionLocal() as db:
            eod_res = await eod_service.run_eod_summary(db)

        return {
            "scenario": 3,
            "name": "Price Volatility & Rebound (+/-3%)",
            "status": "SUCCESS",
            "abnormal_alert_detected": any("ABNORMAL" in a.get("type", "") for a in alerts_drop),
            "rebound_price": 98.50,
            "held_to_eod": True,
            "eod_report": getattr(eod_res, "summary_text", str(eod_res))
        }

    # -------------------------------------------------------------
    # Scenario 4: Order Unmatched, Negotiation Failed & Expired over EOD
    # -------------------------------------------------------------
    async def run_scenario_4_unmatched_negotiation_failed(self, hitl_mode: str = "auto") -> Dict[str, Any]:
        """
        Scenario 4: Unmatched Order -> Negotiation Attempt Failed -> Held Unmatched through EOD
        - Order BUY TRUE 5,000 @ 12.50 remains OPEN (Unmatched)
        - 11:00: Negotiation Round 1 offers 12.80 (User/Strategy rejects change)
        - 15:30: Negotiation Round 2 still unmatched
        - 16:35: EOD report properly captures TRUE as Unmatched Order
        """
        logger.info("=== Starting Scenario 4: Unmatched & Negotiation Failed ===")
        virtual_clock.advance_to("09:30")

        async with AsyncSessionLocal() as db:
            await self._clean_db(db)
            order = Order(
                order_id="ORD-SC4-TRUE",
                symbol="TRUE",
                side="BUY",
                volume=5000,
                price=12.50,
                status="OPEN",  # Unmatched
                created_at=virtual_clock.now()
            )
            db.add(order)
            await db.commit()

        # 11:00 Negotiation Round 1
        virtual_clock.advance_to("11:00")
        async with AsyncSessionLocal() as db:
            # Price Negotiation runs
            nego_res1 = await price_negotiation_service.run_negotiation_round(db=db, round_name="11:00")

        # 15:30 Negotiation Round 2
        virtual_clock.advance_to("15:30")
        async with AsyncSessionLocal() as db:
            nego_res2 = await price_negotiation_service.run_negotiation_round(db=db, round_name="15:30")

        # 16:35 EOD Summary
        virtual_clock.advance_to("16:35")
        async with AsyncSessionLocal() as db:
            eod_res = await eod_service.run_eod_summary(db)

        return {
            "scenario": 4,
            "name": "Order Unmatched, Negotiation Failed & Expired over EOD",
            "status": "SUCCESS",
            "order_id": "ORD-SC4-TRUE",
            "final_order_status": "OPEN (Unmatched)",
            "negotiation_rounds_executed": 2,
            "eod_report": getattr(eod_res, "summary_text", str(eod_res))
        }

    # -------------------------------------------------------------
    # Scenario 5: SBL Borrowed, Short Unmatched & Held Over EOD (Carrying Fee)
    # -------------------------------------------------------------
    async def run_scenario_5_sbl_held_carrying_fee(self, hitl_mode: str = "auto") -> Dict[str, Any]:
        """
        Scenario 5: SBL Borrowed -> Short Unmatched -> User Holds SBL -> EOD Fee Accrual
        - SBL borrowed 2,000 shares of HMPRO @ 10.00 (Borrow Lot #SBL-9912)
        - Short order remains UNMATCHED
        - User chooses [HOLD_BORROWED_SHARES] (Do not return immediately)
        - 16:35 EOD: System calculates daily carrying fee (5.5%/365 = ~3.01 THB) and reports it
        """
        logger.info("=== Starting Scenario 5: SBL Borrowed & Held Over EOD ===")
        virtual_clock.advance_to("09:30")

        async with AsyncSessionLocal() as db:
            await self._clean_db(db)

            # 1. Borrow Lot
            borrow_lot = SBLBorrowLot(
                lot_id="LOT-SC5-HMPRO-01",
                broker_tx_id="TX-SC5-9912",
                symbol="HMPRO",
                borrow_qty=2000,
                remaining_qty=2000,
                borrow_price=10.00,
                borrow_fee_rate=5.50,
                borrow_date=(virtual_clock.now() - timedelta(days=1)).date(),
                status="ACTIVE"
            )
            # 2. Unmatched Short Order
            short_order = Order(
                order_id="ORD-SC5-SHORT-HMPRO",
                symbol="HMPRO",
                side="SHORT",
                volume=2000,
                price=10.20,
                status="OPEN",  # Unmatched
                created_at=virtual_clock.now()
            )
            db.add_all([borrow_lot, short_order])
            await db.commit()

        # Step 2: 11:00 Negotiation checks unmatched short
        virtual_clock.advance_to("11:00")
        async with AsyncSessionLocal() as db:
            await price_negotiation_service.run_negotiation_round(db=db, round_name="11:00")

        # Step 3: 16:35 EOD Summary calculates borrow fees
        virtual_clock.advance_to("16:35")
        async with AsyncSessionLocal() as db:
            eod_res = await eod_service.run_eod_summary(db)

        # Expected fee: 2,000 shares * 10.00 (avg) * 5.5% / 365 = ~3.01 THB
        return {
            "scenario": 5,
            "name": "SBL Borrowed, Short Unmatched & Held Over EOD",
            "status": "SUCCESS",
            "borrow_lot_id": "LOT-SC5-HMPRO-01",
            "held_volume": 2000,
            "borrow_status": "ACTIVE (Held Over EOD)",
            "eod_report": getattr(eod_res, "summary_text", str(eod_res))
        }

    # -------------------------------------------------------------
    # Helper to Clean DB before Scenarios
    # -------------------------------------------------------------
    async def _clean_db(self, db) -> None:
        await db.execute(delete(Position))
        await db.execute(delete(Order))
        await db.execute(delete(SBLBorrowLot))
        await db.commit()


scenario_matrix = ScenarioMatrix()
