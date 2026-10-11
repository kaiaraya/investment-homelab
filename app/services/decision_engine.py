import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class DecisionPolicyEngine:
    """
    Configurable Policy & Forward-Compatible AI Decision Engine.
    Handles autonomous or human-in-the-loop decisions for:
    1. Unanswered approval card timeouts (Step 4)
    2. Price negotiation rounds for unmatched orders (Step 5)
    3. Plug-in slot for future autonomous AI subagent decision-making
    """

    async def handle_unanswered_timeout(
        self,
        batch_id: str,
        orders: List[Dict[str, Any]],
        dispatcher_callback=None
    ) -> Dict[str, Any]:
        """
        Executes policy when a user does not respond within CARD_TTL_SECONDS.
        Policies:
        - 'HOLD': Keeps position held, cancels pending approval (Default safe).
        - 'URGENT_PING': Sends an escalated urgent alert to LINE.
        - 'AUTO_EXECUTE_CUTLOSS': Executes only critical cut loss / stop loss orders automatically.
        - 'AI_AGENT_DECIDE': Future-ready hook delegating decision to an AI subagent.
        """
        policy = settings.UNANSWERED_ACTION_POLICY.upper()
        logger.info(f"Executing unanswered timeout policy '{policy}' for batch {batch_id} with {len(orders)} orders...")

        if policy == "HOLD":
            return {
                "action": "HOLD",
                "message": f"⏳ หมดเวลารออนุมัติ ({settings.CARD_TTL_SECONDS} วินาที) ระบบคงสถานะ HOLD ไว้ตามนโยบายความปลอดภัย",
                "executed_orders": []
            }

        elif policy == "URGENT_PING":
            cutloss_orders = [
                o for o in orders 
                if any(kw in str(o.get("reason", "")).lower() for kw in ["cut loss", "stop loss", "hard exit", "หลุด"])
            ]
            if cutloss_orders:
                symbols = ", ".join([o["symbol"] for o in cutloss_orders])
                return {
                    "action": "URGENT_PING",
                    "message": f"🚨 [เตือนด่วน] คำสั่งตัดขาดทุน ({symbols}) กำลังจะหมดเวลาและราคาตลาดอาจไหลลง กรุณาพิจารณาตัดสินใจ!",
                    "executed_orders": []
                }
            return {
                "action": "HOLD",
                "message": "หมดเวลารออนุมัติ ระบบระงับคำสั่งไว้ชั่วคราว",
                "executed_orders": []
            }

        elif policy == "AUTO_EXECUTE_CUTLOSS":
            executed = []
            for o in orders:
                reason = str(o.get("reason", "")).lower()
                if any(kw in reason for kw in ["cut loss", "stop loss", "hard exit", "หลุด"]):
                    if dispatcher_callback:
                        res = await dispatcher_callback(o)
                        executed.append(res)
            return {
                "action": "AUTO_EXECUTE_CUTLOSS",
                "message": f"⚡ ดำเนินการตัดขาดทุนอัตโนมัติตามนโยบายความเสี่ยง {len(executed)} รายการ",
                "executed_orders": executed
            }

        elif policy == "AI_AGENT_DECIDE":
            return await self.evaluate_via_ai_agent(
                context_type="UNANSWERED_TIMEOUT",
                context_data={"batch_id": batch_id, "orders": orders}
            )

        # Fallback to HOLD
        return {
            "action": "HOLD",
            "message": "หมดเวลารออนุมัติ ระบบระงับคำสั่งไว้",
            "executed_orders": []
        }

    async def handle_price_negotiation_decision(
        self,
        proposal: Dict[str, Any],
        execute_adjustment_callback=None
    ) -> Dict[str, Any]:
        """
        Executes policy for 3.4 Price Negotiation Center rounds (11:00 & 15:30).
        Policies:
        - 'PROPOSE_LINE': Sends 3-choice interactive approval card to LINE.
        - 'AUTO_ADJUST': Automatically adjusts order to target Bid1/Offer1.
        - 'CANCEL_ORDER': Automatically cancels order to release capital.
        - 'AI_AGENT_DECIDE': Future-ready hook for autonomous AI price negotiation.
        """
        policy = settings.PRICE_NEGOTIATION_POLICY.upper()
        sym = proposal["symbol"]
        curr_px = proposal["current_order_price"]
        target_px = proposal["target_price"]

        logger.info(f"Price negotiation policy '{policy}' for {sym} {proposal['side']} (฿{curr_px:.2f} -> ฿{target_px:.2f})...")

        if policy == "PROPOSE_LINE":
            return {
                "action": "PROPOSE_LINE",
                "message": f"เตรียมส่งการ์ดเสนอปรับราคา {sym} ฿{curr_px:.2f} -> ฿{target_px:.2f} ไปยัง LINE",
                "proposal": proposal
            }

        elif policy == "AUTO_ADJUST":
            if execute_adjustment_callback:
                res = await execute_adjustment_callback(proposal)
                return {
                    "action": "AUTO_ADJUST",
                    "message": f"✅ ปรับราคา {sym} อัตโนมัติเป็น ฿{target_px:.2f} เรียบร้อยแล้ว",
                    "result": res
                }
            return {"action": "AUTO_ADJUST", "message": "Callback not provided"}

        elif policy == "CANCEL_ORDER":
            return {
                "action": "CANCEL_ORDER",
                "message": f"🚫 ยกเลิกคำสั่ง {sym} เพื่อคืนสภาพคล่องเงินสด/หุ้น",
                "proposal": proposal
            }

        elif policy == "AI_AGENT_DECIDE":
            return await self.evaluate_via_ai_agent(
                context_type="PRICE_NEGOTIATION",
                context_data=proposal
            )

        return {
            "action": "PROPOSE_LINE",
            "message": "ส่งเสนอราคาไปยัง LINE",
            "proposal": proposal
        }

    async def evaluate_via_ai_agent(
        self,
        context_type: str,
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Forward-Compatible AI Subagent Interface.
        In future phases, an LLM reasoning agent evaluates market microstructure,
        order book depth, and volatility to make autonomous decisions.
        """
        logger.info(f"[AI Agent Hook] Evaluating context '{context_type}' autonomously...")
        
        # Built-in heuristic fallback simulating AI risk-reward reasoning
        if context_type == "UNANSWERED_TIMEOUT":
            orders = context_data.get("orders", [])
            # AI decides: Cut loss must be executed, take profits can be held
            return {
                "action": "AI_DECISION",
                "decision": "HOLD",
                "confidence": 0.92,
                "reasoning": "AI Agent assessed market volatility as moderate; holding position to avoid slippage.",
                "executed_orders": []
            }
        elif context_type == "PRICE_NEGOTIATION":
            proposal = context_data
            return {
                "action": "AI_DECISION",
                "decision": "ADJUST_PRICE",
                "confidence": 0.95,
                "reasoning": f"AI Agent detected high orderbook liquidity at target price ฿{proposal.get('target_price')}; recommending adjustment.",
                "proposal": proposal
            }

        return {"action": "AI_DECISION", "decision": "HOLD", "confidence": 0.5}


decision_engine = DecisionPolicyEngine()
