"""
Pillar 6: Tactical Strategy Center Module.

Extracted from learned workflow:
- click2win_price_negotiation.md

Capabilities:
1. strategy_negotiate_unmatched_orders:
   - Scans open orders in Queuing(SX) / Unmatched status.
   - Fetches real-time Bid1/Offer1 from the active broker driver board.
   - Adjusts price according to 'PASSIVE_LURE' tactic (ล่อตลาดให้มากิน ไม่รีบ):
     * BUY orders adjusted to Bid 1 (highest passive buyer queue)
     * SELL orders adjusted to Offer 1 (lowest passive seller queue)
   - Scheduled for rounds 11:00 (Pre-noon) and 15:30 (Afternoon open).
2. strategy_eod_order_cleanup:
   - Cancels all unmatched orders at 16:30 before market close.
3. Extensible for future algorithmic strategies (Trailing Stop, Grid, DCA).
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.services.line_service import line_service
from app.mcp.pillars.pillar2_portfolio import current_open_orders
from app.browser.broker_factory import get_broker_driver
from app.mcp.pillars.pillar3_trade import trade_modify_price, trade_cancel_order

logger = logging.getLogger("Pillar6.Strategy")


async def strategy_negotiate_unmatched_orders(
    round_name: str = "11:00",
    tactic: str = "PASSIVE_LURE"  # "PASSIVE_LURE" (Bid1/Offer1) or "AGGRESSIVE" (Cross spread)
) -> Dict[str, Any]:
    """
    Executes the Price Negotiation Strategy on unmatched orders (Queuing(SX)).
    Runs at 11:00 and 15:30 rounds to optimize execution while avoiding slippage.
    """
    logger.info(f"Pillar 6: Starting Price Negotiation (Round: {round_name}, Tactic: {tactic})")

    # 1. Fetch unmatched orders from Pillar 5
    open_orders_res = await current_open_orders()
    unmatched_orders = open_orders_res.get("unmatched_orders", [])

    if not unmatched_orders:
        return {
            "success": True,
            "round": round_name,
            "message": "No unmatched queuing orders found. Nothing to negotiate.",
            "negotiated_count": 0
        }

    negotiated_results = []
    for order in unmatched_orders:
        order_no = str(order.get("order_no", ""))
        symbol = str(order.get("symbol", "")).upper()
        side = str(order.get("side", "")).upper()
        old_price = float(order.get("price", 0.0))
        vol = int(order.get("unmatched_vol") or order.get("volume", 0))

        # 2. Get live market Bid1 / Offer1 from the active broker driver board
        quote = await get_broker_driver().get_market_bid_offer(symbol)
        bid1 = quote.get("bid_1") or old_price
        offer1 = quote.get("offer_1") or old_price

        # 3. Determine new negotiated price based on tactic
        if tactic.upper() == "PASSIVE_LURE":
            # "ล่อตลาดให้มากิน ไม่รีบ": วางคิวหน้าร้าน ไม่กระโดดข้ามฝั่ง
            new_price = bid1 if side in ["BUY", "COVER"] else offer1
        else:
            # "AGGRESSIVE": เคาะขวา/โยนซ้ายทันที
            new_price = offer1 if side in ["BUY", "COVER"] else bid1

        if new_price and new_price != old_price:
            logger.info(f"Pillar 6: Negotiating {symbol} Order #{order_no} from {old_price} -> {new_price}")
            mod_res = await trade_modify_price(order_no=order_no, new_price=new_price, symbol=symbol)
            negotiated_results.append({
                "order_no": order_no,
                "symbol": symbol,
                "side": side,
                "old_price": old_price,
                "new_price": new_price,
                "tactic": tactic,
                "success": mod_res.get("success", False)
            })

    # 4. Notify via LINE
    if negotiated_results and not settings.LINE_SIMULATION_MODE:
        msg = f"🤝 [PRICE NEGOTIATION ROUND: {round_name}]\nAdjusted {len(negotiated_results)} order(s):\n"
        for r in negotiated_results:
            msg += f"• {r['symbol']} ({r['side']}): {r['old_price']} ➔ {r['new_price']} ({r['tactic']})\n"
        await line_service.send_alert(msg)

    return {
        "success": True,
        "round": round_name,
        "negotiated_count": len(negotiated_results),
        "results": negotiated_results
    }


async def strategy_eod_order_cleanup(platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Cancels all unmatched/queuing orders at End-of-Day (16:30) to prevent overnight open order risk.
    """
    logger.info("Pillar 6: Executing EOD Order Cleanup...")
    open_orders_res = await current_open_orders(platform=platform)
    unmatched_orders = open_orders_res.get("unmatched_orders", [])

    if not unmatched_orders:
        return {
            "success": True,
            "message": "No open unmatched orders to cleanup.",
            "cancelled_count": 0
        }

    cancelled = []
    for order in unmatched_orders:
        order_no = str(order.get("order_no", ""))
        symbol = str(order.get("symbol", "")).upper()
        plat = platform or open_orders_res.get("platform", "CLICK2WIN")
        res = await trade_cancel_order(order_no=order_no, platform=plat, symbol=symbol)
        cancelled.append({
            "order_no": order_no,
            "symbol": symbol,
            "success": res.get("success", False)
        })

    if not settings.LINE_SIMULATION_MODE:
        msg = f"🧹 [EOD ORDER CLEANUP]\nCancelled {len(cancelled)} open order(s) before market close."
        await line_service.send_alert(msg)

    return {
        "success": True,
        "cancelled_count": len(cancelled),
        "cancelled_orders": cancelled
    }


async def strategy_action_exit_from_text(
    briefing_text: str,
    broker: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingests daily tactical action exit briefings (Thai text with tags, emojis, volumes, prices, reasons),
    allocates morning session execution windows (10:00-10:30 for profits, 10:30-12:00 for losses),
    configures passive limit order pricing, and queues orders for HITL Human-in-the-Loop approval.
    """
    from app.services.action_exit_service import action_exit_service
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        return await action_exit_service.evaluate_and_queue_action_exits(
            text=briefing_text,
            db=session,
            broker_override=broker
        )


async def strategy_list_active() -> Dict[str, Any]:
    """
    Returns available tactical strategies that can be triggered on-demand by AI agents.
    """
    return {
        "strategies": [
            {
                "name": "ACTION_EXIT_FROM_TEXT",
                "description": "Ingests natural language action exit briefings, queues into HITL gate with morning windows and volatility guards."
            },
            {
                "name": "PRICE_NEGOTIATION",
                "default_tactic": "PASSIVE_LURE",
                "description": "Scans unmatched/queuing orders and adjusts prices to Bid1/Offer1 passively."
            },
            {
                "name": "EOD_ORDER_CLEANUP",
                "description": "Cancels all unmatched orders at 16:30 before market close."
            }
        ]
    }


def register_strategy_pillar(server):
    """Registers Pillar 6 tools into the MCP server."""
    server.tool()(strategy_action_exit_from_text)
    server.tool()(strategy_negotiate_unmatched_orders)
    server.tool()(strategy_eod_order_cleanup)
    server.tool()(strategy_list_active)


