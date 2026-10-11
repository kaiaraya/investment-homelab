import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.trademan_driver import trademan_driver
from app.browser.broker_factory import get_broker_driver
from app.browser.trademan_simulator import virtual_simulator
from app.core.config import settings
from app.core.events import event_bus
from app.db.models import Order, SessionLog
from app.db.session import AsyncSessionLocal
from app.services.trade_dispatcher import trade_dispatcher
from app.services.validator import validator

logger = logging.getLogger(__name__)


class PriceNegotiationService:
    """
    3.4 Price Negotiation Center (Runs at 11:00 and 15:30 Bangkok time)
    Features:
    1. Checks all open/unmatched orders on TradeMan (or Virtual Simulator).
    2. Inspects Top Bid (Bid 1) and Top Offer (Offer 1).
    3. Negotiates prices patiently:
       - BUY / COVER -> Aim for Bid 1
       - SELL -> Aim for Offer 1
       - SHORT -> Aim for Offer 1 / strict Last + 1 tick (SET Uptick: must be > Last)
       - A SHORT already at the best offer (or 1 tick above) is left alone to wait
    4. If already at target price, skips.
    5. Dispatches approval cards to LINE (Strict Human-in-the-Loop).
    6. Modifies order upon user confirmation (Change button or Cancel & Re-submit).
    """

    async def run_negotiation_round(self, db: Optional[AsyncSession] = None, round_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Executes a scheduled price negotiation round.
        """
        time_label = round_name or datetime.now().strftime("%H:%M น.")
        logger.info(f"Starting 3.4 Price Negotiation round at {time_label} (Mode: {trade_dispatcher.current_mode})...")

        if db is None:
            async with AsyncSessionLocal() as session:
                return await self._process_round(session)
        else:
            return await self._process_round(db)

    async def _process_round(self, db: AsyncSession) -> List[Dict[str, Any]]:
        # 1. Scrape all open/unmatched orders (Virtual Simulator or Live TradeMan)
        broker_drv = get_broker_driver()
        if hasattr(broker_drv, "scrape_unmatched_orders"):
            unmatched_orders = await broker_drv.scrape_unmatched_orders()
        elif trade_dispatcher.is_live:
            unmatched_orders = await trademan_driver.scrape_unmatched_orders()
        else:
            unmatched_orders = virtual_simulator.get_open_orders()
        proposals: List[Dict[str, Any]] = []

        for ord_info in unmatched_orders:
            proposal = await self.evaluate_order_negotiation(ord_info)
            if proposal and proposal.get("needs_adjustment"):
                proposals.append(proposal)
                await self._dispatch_negotiation_card(proposal)

        # Log round completion
        log = SessionLog(
            event_type="PRICE_NEGOTIATION_ROUND_COMPLETED",
            details=f"Checked {len(unmatched_orders)} unmatched orders. Proposed adjustments for {len(proposals)} orders."
        )
        db.add(log)
        await db.commit()

        logger.info(f"Price Negotiation round finished. {len(proposals)} proposals sent.")
        return proposals

    async def evaluate_order_negotiation(self, order_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluates an unmatched order against Bid1 / Offer1.
        """
        symbol = order_info["symbol"].upper()
        side = order_info["side"].upper()
        current_order_price = order_info["price"]
        order_no = order_info["broker_order_no"]
        volume = order_info["volume"]

        # Fetch market Bid 1 / Offer 1
        broker_drv = get_broker_driver()
        quote = await broker_drv.get_market_bid_offer(symbol)
        bid_1 = quote.get("bid_1")
        offer_1 = quote.get("offer_1")
        last = quote.get("last")  # Anti-Mock: use the REAL last trade price only (no backfill)

        target_price: Optional[float] = None
        reason: str = ""

        if side in ["BUY", "COVER"]:
            # Buy/Cover: patient fill at Top Bid (Bid 1)
            target_price = bid_1 or current_order_price
            reason = f"ปรับตามราคา Bid 1 (฿{target_price:.2f}) เพื่อเพิ่มโอกาสจับคู่แบบไม่เร่งรีบ"
        elif side == "SELL":
            # Sell (Long exit): wait at Top Offer (Offer 1)
            target_price = offer_1 or current_order_price
            reason = f"ปรับตามราคา Offer 1 (฿{target_price:.2f}) เพื่อรอผู้ซื้อคิวแรก"
        elif side == "SHORT":
            # SET Short Sale rule is STRICT (validator SSOT): the short price
            # must be > last traded price (no zero-plus tick). Anti-Mock: when
            # `last` is unavailable we fail-closed and propose nothing - never
            # backfill from the order's own price.
            if not last:
                logger.warning(
                    f"SHORT {symbol} ({order_no}): last trade price unavailable - "
                    "fail-closed, no negotiation proposed."
                )
                return {
                    "broker_order_no": order_no,
                    "symbol": symbol,
                    "side": side,
                    "current_price": current_order_price,
                    "target_price": current_order_price,
                    "needs_adjustment": False,
                    "needs_review": True,
                    "reason": (
                        f"SHORT {symbol}: ราคาซื้อขายล่าสุด (last) อ่านไม่ได้ - "
                        f"ยืนยันกฎ Uptick ไม่ได้ (fail-closed ไม่เสนอปรับราคา)"
                    ),
                }
            # Already well placed: the order sits at the best offer, or 1 tick
            # above it -> leave it alone and wait for the market to move up
            # (user rule 2026-10-09: "price = best offer หรือมากกว่า 1 ช่อง ถือว่า OK").
            if offer_1 is not None and current_order_price <= validator.get_next_tick(offer_1, steps=1):
                logger.debug(
                    f"SHORT {symbol} ({order_no}) already at/above best offer "
                    f"฿{offer_1:.2f} - waiting for the market to move up."
                )
                return {
                    "broker_order_no": order_no,
                    "symbol": symbol,
                    "side": side,
                    "current_price": current_order_price,
                    "target_price": current_order_price,
                    "needs_adjustment": False,
                    "reason": (
                        f"SHORT {symbol} ตั้งราคาไว้ที่/เหนือ best offer แล้ว "
                        f"(฿{current_order_price:.2f} ≤ ฿{validator.get_next_tick(offer_1, steps=1):.2f}) "
                        f"- รอราคาขยับขึ้นเอง"
                    ),
                }
            floor = validator.get_next_tick(last, steps=1)
            target_price = max(offer_1 or 0.0, floor)
            ok, uptick_err = validator.validate_short_uptick(target_price, last)
            if not ok:
                logger.warning(f"SHORT {symbol} ({order_no}): {uptick_err}")
                return {
                    "broker_order_no": order_no,
                    "symbol": symbol,
                    "side": side,
                    "current_price": current_order_price,
                    "target_price": current_order_price,
                    "needs_adjustment": False,
                    "needs_review": True,
                    "reason": uptick_err,
                }
            reason = f"ปรับตามกฎ Uptick (฿{target_price:.2f} > ราคาล่าสุด ฿{last:.2f}) ที่ Offer 1"

        # Check if adjustment is actually needed
        if target_price is None or abs(target_price - current_order_price) < 0.001:
            logger.debug(f"Order {order_no} ({symbol}) already at optimal price ฿{current_order_price:.2f}. No change.")
            return {
                "broker_order_no": order_no,
                "symbol": symbol,
                "side": side,
                "current_price": current_order_price,
                "target_price": current_order_price,
                "needs_adjustment": False
            }

        return {
            "broker_order_no": order_no,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "current_price": current_order_price,
            "target_price": target_price,
            "reason": reason,
            "needs_adjustment": True
        }

    async def _dispatch_negotiation_card(self, proposal: Dict[str, Any]) -> None:
        """
        Sends an interactive price adjustment card to LINE.
        """
        sym = proposal["symbol"]
        side = proposal["side"]
        order_no = proposal["broker_order_no"]
        curr_p = proposal["current_price"]
        new_p = proposal["target_price"]
        vol = proposal["volume"]

        card = {
            "type": "PRICE_NEGOTIATION_CARD",
            "broker_order_no": order_no,
            "symbol": sym,
            "side": side,
            "current_price": curr_p,
            "new_price": new_p,
            "volume": vol,
            "title": f"💬 ขออนุมัติต่อราคา {side} {sym}",
            "text": (
                f"📊 ออเดอร์ {sym} ({side}) ยังไม่ Match:\n"
                f"• ออเดอร์เดิม: ฿{curr_p:.2f} ({vol:,} หุ้น)\n"
                f"• ราคาแนะนำใหม่: ฿{new_p:.2f}\n"
                f"• เหตุผล: {proposal['reason']}\n\n"
                f"คุณต้องการปรับราคาของออเดอร์นี้หรือไม่?"
            ),
            "confirm_payload": f"action=approve_negotiation&order_no={order_no}&symbol={sym}&side={side}&new_price={new_p}&volume={vol}",
            "cancel_payload": f"action=keep_order_price&order_no={order_no}"
        }

        logger.info(f"Dispatched Price Negotiation Card to LINE for {order_no} ({sym})")
        await event_bus.publish_notification(card)

    async def execute_price_adjustment(
        self,
        db: AsyncSession,
        broker_order_no: str,
        symbol: str,
        side: str,
        new_price: float,
        volume: int,
        bypass_dry_run: bool = False,
        force_live: bool = False
    ) -> Dict[str, Any]:
        """
        Executes order modification after user confirms via LINE or Web Console.
        """
        logger.info(
            f"Executing price adjustment for {broker_order_no} ({symbol} {side}) "
            f"to ฿{new_price:.2f} (bypass_dry_run={bypass_dry_run}, force_live={force_live})"
        )

        res = await trade_dispatcher.dispatch_price_modification(
            broker_order_no=broker_order_no,
            new_price=new_price,
            symbol=symbol,
            side=side,
            volume=volume,
            bypass_dry_run=bypass_dry_run,
            force_live=force_live
        )

        # Update order in DB if found
        stmt = select(Order).where(Order.broker_order_no == broker_order_no)
        db_res = await db.execute(stmt)
        order = db_res.scalar_one_or_none()
        if order:
            order.is_negotiated = True
            order.original_price = order.price
            order.negotiated_price = new_price
            order.price = new_price

        log = SessionLog(
            event_type="PRICE_ADJUSTMENT_EXECUTED",
            details=f"Order {broker_order_no} ({symbol} {side}) adjusted to ฿{new_price:.2f} ({res.get('status')})"
        )
        db.add(log)
        await db.commit()

        # Send confirmation report to LINE
        report_msg = (
            f"✅ ปรับราคาคำสั่งเรียบร้อยแล้ว\n"
            f"• หุ้น: {symbol} ({side})\n"
            f"• หมายเลขออเดอร์: {broker_order_no}\n"
            f"• ราคาใหม่: ฿{new_p:.2f}" if (new_p := new_price) else ""
        )
        await event_bus.publish_notification({
            "type": "PRICE_ADJUSTMENT_RESULT",
            "text": report_msg,
            "success": res.get("success", False)
        })

        return res

    async def scan_and_evaluate_live_orders(self) -> List[Dict[str, Any]]:
        """
        Scrapes open orders directly from real TradeMan DOM and calculates
        Top Bid (Bid 1) / Top Offer (Offer 1) alongside proposed negotiated prices.
        """
        broker_drv = get_broker_driver()
        raw_orders = await broker_drv.scrape_unmatched_orders()
        evaluated: List[Dict[str, Any]] = []

        for ord_info in raw_orders:
            proposal = await self.evaluate_order_negotiation(ord_info)
            quote = await broker_drv.get_market_bid_offer(ord_info["symbol"])
            item = {
                "broker_order_no": ord_info.get("broker_order_no", ""),
                "symbol": ord_info.get("symbol", "").upper(),
                "side": ord_info.get("side", "BUY").upper(),
                "volume": ord_info.get("volume", 0),
                "current_price": ord_info.get("price", 0.0),
                "status": ord_info.get("status", "OPEN"),
                "bid_1": quote.get("bid_1"),
                "offer_1": quote.get("offer_1"),
                "last": quote.get("last"),
                "target_price": proposal.get("target_price", ord_info.get("price", 0.0)) if proposal else ord_info.get("price", 0.0),
                "reason": proposal.get("reason", "") if proposal else "",
                "needs_adjustment": proposal.get("needs_adjustment", False) if proposal else False,
            }
            evaluated.append(item)

        logger.info(f"Scanned {len(evaluated)} live unmatched orders from TradeMan.")
        return evaluated

    async def dispatch_single_order_card(self, proposal: Dict[str, Any]) -> None:
        """Dispatches an interactive price adjustment card to LINE for a single order."""
        await self._dispatch_negotiation_card(proposal)


price_negotiation_service = PriceNegotiationService()
