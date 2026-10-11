"""
Pillar 6 Tactical Action Exit Service.
Parses daily natural-language action exit briefings (Thai text with tags, emojis, P&L, ATR)
and queues orders into SQLite with AWAITING_HITL_CONFIRMATION, tactical time windows,
volatility deviation guards, and passive limit order placement.
"""

import re
import json
import uuid
import random
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, time, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Order
from app.services.validator import validator
from app.services.kdeconnect_service import kdeconnect_service
from app.core.sse_broadcaster import sse_broadcaster

logger = logging.getLogger("ActionExitService")


class ActionExitItem:
    def __init__(
        self,
        tag: str,
        symbol: str,
        position: str,
        side: str,
        volume: int,
        price: float,
        pnl_pct: float,
        atr_val: Optional[float],
        reason: str,
        is_profit: bool,
        window: str,
        window_start: str,
        window_end: str,
        jitter_minutes: int,
        pricing_rule: str,
        deviation_guard: str
    ):
        self.tag = tag
        self.symbol = symbol
        self.position = position
        self.side = side
        self.volume = volume
        self.price = price
        self.pnl_pct = pnl_pct
        self.atr_val = atr_val
        self.reason = reason
        self.is_profit = is_profit
        self.window = window
        self.window_start = window_start
        self.window_end = window_end
        self.jitter_minutes = jitter_minutes
        self.pricing_rule = pricing_rule
        self.deviation_guard = deviation_guard

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "symbol": self.symbol,
            "position": self.position,
            "side": self.side,
            "volume": self.volume,
            "price": self.price,
            "pnl_pct": self.pnl_pct,
            "atr_val": self.atr_val,
            "reason": self.reason,
            "is_profit": self.is_profit,
            "window": self.window,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "jitter_minutes": self.jitter_minutes,
            "pricing_rule": self.pricing_rule,
            "deviation_guard": self.deviation_guard
        }


class ActionExitService:
    """
    Ingests daily tactical action exit briefings, validates holdings and tick sizes,
    assigns tactical morning session execution windows, and sets up HITL safeguards.
    """

    ITEM_PATTERN = re.compile(
        r"(?:[•\*\-]\s*)?"
        r"\[(?P<tag>[^\]]+)\]\s*"
        r"(?P<symbol>[A-Z0-9]+)\s*"
        r"(?:\((?P<position>LONG|SHORT)\))?\s*:\s*"
        r"(?P<side>BUY|SELL|COVER|SHORT)\s+"
        r"(?P<volume>[\d,]+)\s*(?:หุ้น|shares|contracts|สัญญา)?\s*@\s*"
        r"(?P<price>\d+(?:\.\d+)?)\s*"
        r"(?:\((?P<pnl_block>[^)]+)\))?\s*"
        r"(?:👉\s*(?P<reason>.*))?",
        re.IGNORECASE
    )

    def parse_action_exit_text(self, text: str, default_broker: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses text briefing into broker metadata and action exit items.
        """
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        
        # 1. Detect Broker & Account from headers or parameters
        broker = default_broker or "KRUNGSRI"
        account_no = "3024959"  # Default to Krungsri Margin
        account_type = "MARGIN"

        for line in lines[:3]:
            lower_line = line.lower()
            if "krungsri" in lower_line or "kss" in lower_line or "กรุงศรี" in lower_line:
                broker = "KRUNGSRI"
                if "margin" in lower_line or "sbl" in lower_line:
                    account_no = "3024959"
                    account_type = "MARGIN"
                elif "cash" in lower_line:
                    account_no = "3024952"
                    account_type = "CASH"
            elif "click2win" in lower_line or "c2w" in lower_line or "sandbox" in lower_line:
                broker = "CLICK2WIN"
                account_no = "CW32_E_7338419"
                account_type = "EQUITY"
            elif "liberator" in lower_line:
                broker = "LIBERATOR"
                account_type = "EQUITY"

        items: List[ActionExitItem] = []

        for line in lines:
            match = self.ITEM_PATTERN.search(line)
            if not match:
                continue

            tag = match.group("tag").strip()
            symbol = match.group("symbol").strip().upper()
            position = (match.group("position") or "LONG").strip().upper()
            side = match.group("side").strip().upper()
            volume = int(match.group("volume").replace(",", "").strip())
            price = float(match.group("price").strip())
            reason = (match.group("reason") or "").strip()

            pnl_block = match.group("pnl_block") or ""
            pnl_pct = 0.0
            atr_val = None

            if pnl_block:
                pnl_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", pnl_block)
                if pnl_m:
                    pnl_pct = float(pnl_m.group(1))
                atr_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*x?\s*ATR", pnl_block, re.IGNORECASE)
                if atr_m:
                    atr_val = float(atr_m.group(1))

            # Tactical Window & Jitter Allocation
            # Profit: 10:00 - 10:30 (Lock profit, unlock cash) with 1-5 min jitter
            # Loss: 10:30 - 12:00 (Wait for morning noise to settle, strictly before noon) with 3-15 min jitter
            is_profit = pnl_pct >= 0.0
            if is_profit:
                window = "10:00 - 10:30"
                window_start = "10:00"
                window_end = "10:30"
                jitter_minutes = random.randint(1, 5)
            else:
                window = "10:30 - 12:00"
                window_start = "10:30"
                window_end = "12:00"
                jitter_minutes = random.randint(3, 15)

            pricing_rule = "PASSIVE_BEST (Queue at Offer 1 on Sell / Bid 1 on Cover; No Immediate Match)"
            deviation_guard = "Halt & Critical Alert if price deviates > 3 ticks or > ±1.5% at execution"

            item = ActionExitItem(
                tag=tag,
                symbol=symbol,
                position=position,
                side=side,
                volume=volume,
                price=price,
                pnl_pct=pnl_pct,
                atr_val=atr_val,
                reason=reason,
                is_profit=is_profit,
                window=window,
                window_start=window_start,
                window_end=window_end,
                jitter_minutes=jitter_minutes,
                pricing_rule=pricing_rule,
                deviation_guard=deviation_guard
            )
            items.append(item)

        return {
            "broker": broker,
            "account_no": account_no,
            "account_type": account_type,
            "total_items": len(items),
            "profitable_count": sum(1 for i in items if i.is_profit),
            "losing_count": sum(1 for i in items if not i.is_profit),
            "items": [i.to_dict() for i in items]
        }

    async def evaluate_and_queue_action_exits(
        self,
        text: str,
        db: AsyncSession,
        broker_override: Optional[str] = None,
        auto_schedule: bool = True
    ) -> Dict[str, Any]:
        """
        Parses briefing, validates tick sizes and limits, queues orders into DB as
        SCHEDULED (or AWAITING_HITL_CONFIRMATION if auto_schedule=False), sends actionable KDE Connect alert, and notifies Cockpit.
        """
        parsed = self.parse_action_exit_text(text, default_broker=broker_override)
        if not parsed["items"]:
            return {
                "success": False,
                "message": "No valid action exit lines found matching pattern [TAG] SYMBOL: SIDE VOL @ PRICE",
                "queued_count": 0,
                "orders": []
            }

        broker = parsed["broker"]
        account_no = parsed["account_no"]
        created_orders = []

        for item_data in parsed["items"]:
            symbol = item_data["symbol"]
            side = item_data["side"]
            volume = item_data["volume"]
            price = item_data["price"]
            position = item_data["position"]

            # Validate SET tick size & constraints
            is_valid, err_msg = validator.validate_all(
                symbol=symbol,
                side=side,
                volume=volume,
                price=price,
                position=position
            )
            if not is_valid:
                logger.warning(f"Risk Validator rejected action exit item for {symbol}: {err_msg}")
                continue

            order_id = f"ORD-ACT-{uuid.uuid4().hex[:8].upper()}"

            # Calculate exact scheduled firing time: window_start + jitter_minutes
            sh, sm = map(int, item_data["window_start"].split(":"))
            scheduled_m = sm + item_data["jitter_minutes"]
            scheduled_h = sh + (scheduled_m // 60)
            scheduled_m = scheduled_m % 60
            scheduled_time = f"{scheduled_h:02d}:{scheduled_m:02d}"

            meta_json = json.dumps({
                "tag": item_data["tag"],
                "pnl_pct": item_data["pnl_pct"],
                "atr": item_data["atr_val"],
                "window": item_data["window"],
                "window_start": item_data["window_start"],
                "window_end": item_data["window_end"],
                "jitter_minutes": item_data["jitter_minutes"],
                "scheduled_time": scheduled_time,
                "is_profit": item_data["is_profit"],
                "pricing_rule": item_data["pricing_rule"],
                "deviation_guard": item_data["deviation_guard"],
                "reason": item_data["reason"],
                "account_no": account_no,
                "broker": broker,
                "auto_scheduled": auto_schedule,
                "approved": auto_schedule,
                "approved_at": datetime.now().isoformat() if auto_schedule else None
            }, ensure_ascii=False)

            initial_status = "SCHEDULED" if auto_schedule else "AWAITING_HITL_CONFIRMATION"

            order_rec = Order(
                order_id=order_id,
                broker_order_no=None,
                symbol=symbol,
                side=side,
                position=position,
                volume=volume,
                price=price,
                status=initial_status,
                error_message=meta_json,
                source=f"action_exit_{broker.lower()}",
                is_negotiated=False,
                original_price=price,
                negotiated_price=None
            )
            db.add(order_rec)
            created_orders.append({
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "volume": volume,
                "price": price,
                "position": position,
                "window": item_data["window"],
                "scheduled_time": scheduled_time,
                "status": initial_status,
                "tag": item_data["tag"],
                "pnl_pct": item_data["pnl_pct"],
                "reason": item_data["reason"]
            })

        await db.commit()

        # Send Actionable KDE Connect Push Alert to Xiaomi Mi 10T
        if created_orders:
            try:
                if auto_schedule:
                    alert_title = f"⏰ [{broker} Margin] {len(created_orders)} Action Exits Auto-Scheduled"
                    lines = [f"{o['side']} {o['volume']:,} {o['symbol']} @ ฿{o['price']:.2f} ({o['tag']} | ยิง {o['scheduled_time']} น.)" for o in created_orders]
                    alert_msg = "ตั้งเวลา Auto-Trade เรียบร้อย:\n• " + "\n• ".join(lines) + "\n\n👉 ระบบจะส่งคำสั่งเข้า TradeMan อัตโนมัติเมื่อถึงเวลา"
                else:
                    alert_title = f"🚨 [{broker} Margin] {len(created_orders)} Action Exits Pending Approval"
                    lines = [f"{o['side']} {o['volume']:,} {o['symbol']} @ ฿{o['price']:.2f} ({o['tag']} | {o['window']})" for o in created_orders]
                    alert_msg = "Tactical Exits Queued:\n• " + "\n• ".join(lines) + "\n\n👉 Open /console to 1-Click Approve All or Inspect"
                await kdeconnect_service.send_critical_alert(alert_title, alert_msg)
            except Exception as e:
                logger.error(f"Failed to send KDE Connect alert: {e}")

            # SSE Broadcast to /console
            try:
                for o in created_orders:
                    event_type = "hitl_order_scheduled" if auto_schedule else "hitl_order_pending"
                    await sse_broadcaster.broadcast(event_type, {
                        "order_id": o["order_id"],
                        "symbol": o["symbol"],
                        "side": o["side"],
                        "position": o["position"],
                        "volume": o["volume"],
                        "price": o["price"],
                        "broker": broker,
                        "window": o["window"],
                        "scheduled_time": o["scheduled_time"],
                        "status": o["status"],
                        "tag": o["tag"],
                        "pnl_pct": o["pnl_pct"]
                    })
            except Exception as e:
                logger.debug(f"SSE broadcast error: {e}")

        return {
            "success": True,
            "broker": broker,
            "account_no": account_no,
            "queued_count": len(created_orders),
            "profitable_count": parsed["profitable_count"],
            "losing_count": parsed["losing_count"],
            "orders": created_orders
        }


action_exit_service = ActionExitService()
