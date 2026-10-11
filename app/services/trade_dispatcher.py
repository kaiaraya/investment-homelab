"""
Unified Execution Dispatcher & Mode Switcher.
Routes trade execution between:
1. TEST MODE: Virtual TradeMan Simulator (Safe isolated sandbox)
2. LIVE MODE: Real TradeMan Browser Automation (Krungsri Securities)
Enforces 3-tier safety guardrails (PIN Challenge, Value Limit, Visual Badges).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.browser.trademan_driver import trademan_driver
from app.browser.broker_factory import get_broker_driver
from app.browser.trademan_simulator import virtual_simulator
from app.core.config import settings
from app.db.models import SessionLog
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


import random
import asyncio


class TradeExecutionDispatcher:
    """
    Central Trade Dispatcher with Dual Execution Engines (TEST vs LIVE)
    and Step-by-Step Sequential Anti-Bot Pacing.
    """

    def __init__(self):
        self._current_mode: str = settings.TRADING_MODE.upper()
        self._queue_lock = asyncio.Lock()
        self.pacing_enabled: bool = True

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def is_live(self) -> bool:
        return self._current_mode == "LIVE"

    def get_mode_badge(self) -> str:
        if self.is_live:
            return "⚡ LIVE TRADING (ส่งคำสั่งจริง)"
        return "🛡️ TEST MODE (จำลองเสมือนจริง)"

    def get_mode_color(self) -> str:
        """Returns HEX color for LINE Flex cards based on mode."""
        if self.is_live:
            return "#DC2626"  # Red / Amber for Live
        return "#2563EB"      # Blue / Cyan for Test

    async def switch_mode(self, target_mode: str, pin: Optional[str] = None) -> Dict[str, Any]:
        """
        Switches between TEST and LIVE execution engines.
        Switching to LIVE requires the correct TRADING_PIN for safety.
        """
        mode = target_mode.upper().strip()
        if mode not in ["TEST", "LIVE"]:
            return {
                "success": False,
                "error": f"Invalid mode '{target_mode}'. Must be 'TEST' or 'LIVE'."
            }

        if mode == self._current_mode:
            return {
                "success": True,
                "mode": self._current_mode,
                "badge": self.get_mode_badge(),
                "message": f"ระบบทำงานอยู่ในโหมด {self._current_mode} อยู่แล้ว"
            }

        # Guardrail: Switching to LIVE requires Trading PIN
        if mode == "LIVE":
            expected_pin = settings.TRADING_PIN
            if not pin or pin.strip() != expected_pin:
                logger.warning("[Dispatcher] Attempted switch to LIVE rejected: Invalid or missing PIN")
                await self._log_event("MODE_SWITCH_REJECTED", f"Attempted switch to LIVE rejected (Invalid PIN)")
                return {
                    "success": False,
                    "mode": self._current_mode,
                    "error": "❌ รหัส PIN ไม่ถูกต้อง ไม่สามารถเปิดโหมด LIVE ได้เพื่อความปลอดภัย"
                }

        self._current_mode = mode
        logger.warning(f"[Dispatcher] Switched trading mode to: {self._current_mode}")
        await self._log_event("MODE_SWITCHED", f"Trading mode switched to {self._current_mode} (Badge: {self.get_mode_badge()})")

        return {
            "success": True,
            "mode": self._current_mode,
            "badge": self.get_mode_badge(),
            "message": f"✅ สลับเข้าสู่โหมด {self.get_mode_badge()} เรียบร้อยแล้ว"
        }

    async def dispatch_order(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        current_market_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Dispatches order to either Virtual Simulator or Live TradeMan.
        Enforces Sequential Execution Queue and Anti-Bot Human Pacing (3.0 - 6.0s cooldown).
        """
        async with self._queue_lock:
            symbol = symbol.upper()
            side = side.upper()
            total_val = volume * price

            logger.info(f"[Dispatcher] Dispatching {side} {volume:,} {symbol} @ ฿{price:.2f} (Mode: {self._current_mode})")

            # 1. LIVE MODE ROUTE
            if self.is_live:
                # Check Live Value Limit Guardrail
                if total_val > settings.LIVE_ORDER_VALUE_LIMIT_THB:
                    err_msg = (
                        f"คำสั่งมูลค่า ฿{total_val:,.2f} เกินเพดานความปลอดภัยโหมด LIVE "
                        f"(จำกัดไม่เกิน ฿{settings.LIVE_ORDER_VALUE_LIMIT_THB:,.2f})"
                    )
                    logger.warning(f"[Dispatcher] Live order rejected: {err_msg}")
                    await self._log_event("LIVE_ORDER_BLOCKED", f"{side} {volume} {symbol}: {err_msg}")
                    return {
                        "success": False,
                        "status": "REJECTED_VALUE_LIMIT",
                        "mode": "LIVE",
                        "error": err_msg
                    }

                # Execute via Real Playwright Driver
                broker_drv = get_broker_driver()
                res = await broker_drv.execute_order(
                    symbol=symbol,
                    side=side,
                    volume=volume,
                    price=price
                )
                res["mode"] = "LIVE"
                res["badge"] = self.get_mode_badge()

                # Step-by-step Anti-Bot Pacing: Wait cooldown before next order in queue
                if self.pacing_enabled:
                    cooldown = random.uniform(3.0, 6.0)
                    logger.info(f"[Dispatcher] Anti-bot step-by-step delay: {cooldown:.2f}s before next order")
                    await asyncio.sleep(cooldown)

                return res

            # 2. TEST MODE ROUTE (Virtual Simulator)
            res = await virtual_simulator.execute_simulated_order(
                symbol=symbol,
                side=side,
                volume=volume,
                price=price,
                current_market_price=current_market_price
            )
            res["mode"] = "TEST"
            res["badge"] = self.get_mode_badge()
            return res

    async def dispatch_price_modification(
        self,
        broker_order_no: str,
        new_price: float,
        current_market_price: Optional[float] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        volume: Optional[int] = None,
        pin: Optional[str] = None,
        bypass_dry_run: bool = False,
        force_live: bool = False,
    ) -> Dict[str, Any]:
        """Dispatches order price modification (Price Negotiation Center)."""
        is_live_exec = self.is_live or force_live
        if is_live_exec:
            broker_drv = get_broker_driver()
            res = await broker_drv.modify_order_price(
                broker_order_no=broker_order_no,
                symbol=symbol or "",
                side=side or "BUY",
                new_price=new_price,
                remaining_volume=volume or 0,
                pin=pin,
                bypass_dry_run=bypass_dry_run,
            )
            res["mode"] = "LIVE"
            return res

        res = virtual_simulator.modify_order_price(
            broker_order_no=broker_order_no,
            new_price=new_price,
            current_market_price=current_market_price
        )
        res["mode"] = "TEST"
        return res

    async def dispatch_sbl_return(
        self,
        lot_id: str,
        return_qty: Optional[int] = None
    ) -> Dict[str, Any]:
        """Dispatches SBL share return request."""
        if self.is_live:
            res = await trademan_driver.return_sbl_shares(lot_id=lot_id, return_qty=return_qty)
            res["mode"] = "LIVE"
            return res

        res = virtual_simulator.execute_sbl_return(lot_id=lot_id, return_qty=return_qty)
        res["mode"] = "TEST"
        return res

    async def _log_event(self, event_type: str, details: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                log_entry = SessionLog(event_type=event_type, details=details)
                db.add(log_entry)
                await db.commit()
        except Exception as e:
            logger.warning(f"Dispatcher log failed ({event_type}): {e}")


# Global singleton dispatcher instance
trade_dispatcher = TradeExecutionDispatcher()
