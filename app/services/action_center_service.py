import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import SessionLog
from app.services.trade_dispatcher import trade_dispatcher

logger = logging.getLogger(__name__)


class ActionCenterService:
    """
    Action Center Service for LINE UX Optimization:
    1. Collects pending TP/SL and Abnormal Price trigger actions into a consolidated queue.
    2. Prevents notification spam (Alert Fatigue) by replacing multi-card spam with 1-line alerts.
    3. Provides a single unified Action Center interface on LINE with [Approve All], [Reject All],
       or granular per-stock approval.
    4. Delivers scheduled Lunchtime (12:00) reminders for any unapproved actions before afternoon session.
    """
    def __init__(self):
        # Key: action_id (e.g. "ACT-AOT-SELL"), Value: action dict
        self._pending_actions: Dict[str, Dict[str, Any]] = {}

    def get_pending_count(self) -> int:
        return len(self._pending_actions)

    def get_pending_actions(self) -> List[Dict[str, Any]]:
        return list(self._pending_actions.values())

    def clear_all(self) -> None:
        self._pending_actions.clear()

    def add_pending_action(self, action_data: Dict[str, Any]) -> str:
        """
        Adds or updates a pending trade action in the Action Center queue.
        """
        symbol = str(action_data.get("symbol", "")).upper()
        side = str(action_data.get("action") or action_data.get("side", "SELL")).upper()
        action_id = f"ACT-{symbol}-{side}"

        self._pending_actions[action_id] = {
            "id": action_id,
            "symbol": symbol,
            "action": side,
            "volume": int(action_data.get("volume", 0)),
            "price": float(action_data.get("price", 0.0)),
            "target_price": float(action_data.get("target_price", action_data.get("price", 0.0))),
            "reason": action_data.get("reason", "SL_HIT"),
            "message": action_data.get("message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "PENDING"
        }
        logger.info(f"[ActionCenter] Added pending action {action_id} for {side} {symbol}")
        return action_id

    def remove_pending_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        return self._pending_actions.pop(action_id, None)

    def reject_single(self, action_id: str) -> bool:
        """Rejects and dismisses a single pending action."""
        if action_id in self._pending_actions:
            del self._pending_actions[action_id]
            logger.info(f"[ActionCenter] Rejected single action {action_id}")
            return True
        return False

    def reject_all(self) -> int:
        """Clears all pending actions in queue."""
        count = len(self._pending_actions)
        self._pending_actions.clear()
        logger.info(f"[ActionCenter] Rejected all {count} pending actions")
        return count

    async def approve_single(self, action_id: str, db: AsyncSession) -> Dict[str, Any]:
        """
        Executes a single approved action via TradeDispatcher (under DRY_RUN / LIVE guard).
        """
        item = self.remove_pending_action(action_id)
        if not item:
            return {"success": False, "error": f"ไม่พบคำสั่ง {action_id} หรือถูกดำเนินการไปแล้ว"}

        res = await trade_dispatcher.dispatch_order(
            symbol=item["symbol"],
            side=item["action"],
            volume=item["volume"],
            price=item["price"]
        )

        log = SessionLog(
            event_type="ACTION_CENTER_APPROVED_SINGLE",
            details=f"Approved {action_id}: {res.get('status')} (Mode: {res.get('mode')})"
        )
        db.add(log)
        await db.commit()

        res["symbol"] = item["symbol"]
        res["action"] = item["action"]
        return res

    async def approve_all(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Executes all pending actions currently in the queue.
        """
        actions = list(self._pending_actions.values())
        self._pending_actions.clear()

        results: List[Dict[str, Any]] = []
        for item in actions:
            try:
                res = await trade_dispatcher.dispatch_order(
                    symbol=item["symbol"],
                    side=item["action"],
                    volume=item["volume"],
                    price=item["price"]
                )
                res["symbol"] = item["symbol"]
                res["action"] = item["action"]
                results.append(res)
            except Exception as e:
                logger.error(f"[ActionCenter] Error approving {item['id']}: {e}")
                results.append({"symbol": item["symbol"], "action": item["action"], "success": False, "error": str(e)})

        log = SessionLog(
            event_type="ACTION_CENTER_APPROVED_ALL",
            details=f"Executed batch approval for {len(results)} items"
        )
        db.add(log)
        await db.commit()

        return results

    # ==========================================
    # LINE Flex Card Builders
    # ==========================================

    def build_action_center_card(self) -> Dict[str, Any]:
        """
        Builds the consolidated Action Center Flex Card message.
        """
        pending = self.get_pending_actions()
        now_ts = int(time.time())

        # Empty State
        if not pending:
            return {
                "type": "flex",
                "altText": "📋 Action Center: ไม่มีรายการรออนุมัติ",
                "contents": {
                    "type": "bubble",
                    "header": {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#0f172a",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📋 ACTION CENTER",
                                "weight": "bold",
                                "color": "#38bdf8",
                                "size": "md"
                            }
                        ]
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#1e293b",
                        "spacing": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": "✅ ไม่มีรายการรออนุมัติในขณะนี้",
                                "color": "#4ade80",
                                "weight": "bold",
                                "size": "sm"
                            },
                            {
                                "type": "text",
                                "text": "ทุกสถานะในพอร์ตยังอยู่ในเกณฑ์ควบคุมความเสี่ยงปกติ ระบบจะแจ้งเตือนทันทีเมื่อมีรายการใหม่",
                                "color": "#94a3b8",
                                "size": "xs",
                                "wrap": True
                            }
                        ]
                    }
                }
            }

        # Multiple / Single pending items
        item_contents: List[Dict[str, Any]] = []
        for idx, item in enumerate(pending):
            sym = item["symbol"]
            side = item["action"]
            vol = item["volume"]
            price = item["price"]
            reason = item["reason"]
            act_id = item["id"]

            side_color = "#ef4444" if side in ["SELL", "SHORT"] else "#22c55e"
            badge_text = "🚨 ตัดขาดทุน (SL)" if "SL" in reason else ("🎯 ล็อกกำไร (TP)" if "TP" in reason else "⚡ ผันผวนผิดปกติ")

            item_box = {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0f172a",
                "cornerRadius": "md",
                "paddingAll": "sm",
                "margin": "sm" if idx > 0 else "none",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": f"{side} {sym}", "weight": "bold", "color": side_color, "size": "sm"},
                            {"type": "text", "text": badge_text, "color": "#cbd5e1", "size": "xs", "align": "end"}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "xs",
                        "contents": [
                            {"type": "text", "text": f"จำนวน: {vol:,} หุ้น", "color": "#94a3b8", "size": "xs"},
                            {"type": "text", "text": f"ราคา: ฿{price:.2f}", "color": "#f8fafc", "size": "xs", "align": "end", "weight": "bold"}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "margin": "sm",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#22c55e" if side == "BUY" else "#ef4444",
                                "height": "sm",
                                "action": {
                                    "type": "postback",
                                    "label": f"✅ อนุมัติ {sym}",
                                    "data": f"action=approve_action&id={act_id}&ts={now_ts}",
                                    "displayText": f"✅ อนุมัติ {side} {sym}"
                                }
                            },
                            {
                                "type": "button",
                                "style": "secondary",
                                "height": "sm",
                                "action": {
                                    "type": "postback",
                                    "label": "❌ ปฏิเสธ",
                                    "data": f"action=reject_action&id={act_id}",
                                    "displayText": f"❌ ปฏิเสธ {sym}"
                                }
                            }
                        ]
                    }
                ]
            }
            item_contents.append(item_box)

        # Bubble Card
        bubble = {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0f172a",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "📋 ACTION CENTER", "weight": "bold", "color": "#38bdf8", "size": "md"},
                            {"type": "text", "text": f"รออนุมัติ {len(pending)} รายการ", "weight": "bold", "color": "#f59e0b", "size": "sm", "align": "end"}
                        ]
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1e293b",
                "spacing": "xs",
                "contents": item_contents
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0f172a",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0284c7",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": f"✅ อนุมัติทั้งหมด ({len(pending)} รายการ)",
                            "data": f"action=approve_all_actions&ts={now_ts}",
                            "displayText": "✅ อนุมัติทั้งหมดในคิว Action Center"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "❌ ยกเลิกทั้งหมด",
                            "data": f"action=reject_all_actions&ts={now_ts}",
                            "displayText": "❌ ยกเลิกคำสั่งทั้งหมดใน Action Center"
                        }
                    }
                ]
            }
        }

        return {
            "type": "flex",
            "altText": f"📋 Action Center: รอการอนุมัติ {len(pending)} รายการ",
            "contents": bubble
        }

    def build_lunchtime_reminder_card(self) -> Dict[str, Any]:
        """
        Builds the 12:00 Lunchtime Reminder Flex Card.
        """
        pending = self.get_pending_actions()
        now_ts = int(time.time())

        items_summary: List[Dict[str, Any]] = []
        for item in pending:
            items_summary.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "xs",
                "contents": [
                    {"type": "text", "text": f"• {item['action']} {item['symbol']}", "color": "#f8fafc", "size": "xs", "weight": "bold"},
                    {"type": "text", "text": f"{item['volume']:,} หุ้น @ ฿{item['price']:.2f}", "color": "#94a3b8", "size": "xs", "align": "end"}
                ]
            })

        bubble = {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0f172a",
                "contents": [
                    {
                        "type": "text",
                        "text": "🍱 สรุปเตือนรอบพักเที่ยง (12:00 น.)",
                        "weight": "bold",
                        "color": "#f59e0b",
                        "size": "md"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1e293b",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": f"คุณมี {len(pending)} รายการรอการตัดสินใจที่ยังไม่ได้กดอนุมัติ:",
                        "color": "#cbd5e1",
                        "size": "xs"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#0f172a",
                        "cornerRadius": "sm",
                        "paddingAll": "sm",
                        "contents": items_summary
                    },
                    {
                        "type": "text",
                        "text": "กรุณาพิจารณากดอนุมัติหรือยกเลิกก่อนเปิดตลาดภาคบ่าย (14:30 น.)",
                        "color": "#64748b",
                        "size": "xxs",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0f172a",
                "spacing": "xs",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0284c7",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": f"✅ อนุมัติทั้งหมด ({len(pending)} รายการ)",
                            "data": f"action=approve_all_actions&ts={now_ts}",
                            "displayText": "✅ อนุมัติคำสั่งค้างทั้งหมดก่อนตลาดบ่าย"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "📋 เปิดดู Action Center",
                            "text": "action"
                        }
                    }
                ]
            }
        }

        return {
            "type": "flex",
            "altText": f"🍱 แจ้งเตือนพักเที่ยง: มี {len(pending)} รายการรออนุมัติ",
            "contents": bubble
        }


action_center_service = ActionCenterService()
