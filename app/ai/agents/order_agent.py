import logging
from typing import Any, Dict, List, Optional
from app.ai.agents.base import BaseSubAgent
from app.services.validator import validator
from app.services.price_negotiation_service import price_negotiation_service
from app.schemas.order import OrderCreate, OrderSide
from app.core.config import settings

logger = logging.getLogger(__name__)


class OrderExecutionAgent(BaseSubAgent):
    """
    Sub-Agent governing Pre-Trade Guardrails, Runbook-driven Order Execution,
    Tactical Price Negotiation, and EOD Order Purge (SOP-003).
    """

    def __init__(self, model_override: Optional[Any] = None):
        super().__init__(
            name="OrderExecutionAgent",
            sop_filename="sop_order_execution.md",
            model_override=model_override,
            output_type=str,
        )

    async def execute_order(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        pin: Optional[str] = None,
        account_type: str = "CASH_BALANCE",
    ) -> Dict[str, Any]:
        """
        Executes an order adhering strictly to Pre-Trade Guardrails and Runbook procedures.
        """
        clean_symbol = symbol.strip().upper()
        clean_side = side.strip().upper()
        trading_pin = pin or getattr(settings, "TRADING_PIN", "000000")

        # 1. Kill Switch Check
        from app.services.kill_switch_service import kill_switch_service
        if kill_switch_service.is_active():
            msg = "Execution rejected: Emergency Kill Switch is ACTIVE."
            logger.warning(msg)
            await self.log_step(
                action_type="ORDER_BLOCKED_BY_KILL_SWITCH",
                thought=msg,
                input_context={"symbol": clean_symbol, "side": clean_side, "volume": volume},
                is_success=False,
            )
            return {"status": "BLOCKED", "error": msg}

        # 2. Structural Guardrail Validation
        await self.log_step(
            action_type="PRE_TRADE_GUARDRAILS",
            thought=f"Validating board lot and account rules for {clean_side} {volume} {clean_symbol} @ {price}",
            input_context={"symbol": clean_symbol, "side": clean_side, "volume": volume, "price": price},
        )
        is_valid, err_msg = validator.validate_all(
            symbol=clean_symbol,
            side=clean_side,
            volume=volume,
            price=price,
            record_idempotency=False,
        )
        if not is_valid:
            logger.error(f"Order Guardrail Rejected: {err_msg}")
            await self.log_step(
                action_type="GUARDRAIL_REJECTED",
                thought=f"Pre-trade guardrail failed: {err_msg}",
                output_result=err_msg,
                is_success=False,
            )
            return {"status": "REJECTED", "error": err_msg}

        order_req = OrderCreate(
            symbol=clean_symbol,
            side=OrderSide(clean_side),
            volume=volume,
            price=price,
            pin=trading_pin,
        )

        # 3. Execution via Broker Driver / Runbook
        await self.log_step(
            action_type="SUBMITTING_ORDER",
            thought=f"Submitting verified order to broker platform for {clean_symbol}",
        )
        try:
            # Import broker runner
            from app.services.trade_center_service import trade_center_service
            submission = await trade_center_service.execute_verified_order(order_req)
            result = {
                "status": "SUBMITTED",
                "symbol": clean_symbol,
                "side": clean_side,
                "volume": volume,
                "price": price,
                "details": submission,
            }
            await self.log_step(
                action_type="ORDER_SUCCESS",
                output_result=result,
                is_success=True,
            )
            return result
        except Exception as exc:
            logger.error(f"Order submission error: {exc}")
            # Delegate to Self-Annealing Engine if browser locator / network error
            from app.services.self_annealing_engine import self_annealing_engine
            recovery = await self_annealing_engine.handle_execution_failure(
                workflow_name="order_submit",
                failed_step="submit_button_click",
                error=exc,
            )
            await self.log_step(
                action_type="ORDER_EXECUTION_ANNEALED" if recovery.get("recovered") else "ORDER_FAILED",
                output_result={"error": str(exc), "recovery": recovery},
                is_success=recovery.get("recovered", False),
            )
            return {"status": "FAILED", "error": str(exc), "recovery": recovery}

    async def negotiate_prices(self) -> Dict[str, Any]:
        """Scans unmatched orders and adjusts price toward Best Bid 1 / Best Offer 1."""
        await self.log_step(
            action_type="PRICE_NEGOTIATION",
            thought="Inspecting unmatched orders for passive stepping (Bid 1 / Offer 1)",
        )
        try:
            result = await price_negotiation_service.negotiate_unmatched_orders()
            await self.log_step(action_type="NEGOTIATION_COMPLETE", output_result=result, is_success=True)
            return result
        except Exception as exc:
            logger.error(f"Price negotiation failed: {exc}")
            await self.log_step(action_type="NEGOTIATION_ERROR", output_result=str(exc), is_success=False)
            return {"error": str(exc)}

    async def purge_eod_orders(self) -> Dict[str, Any]:
        """Cancels all open / unmatched orders prior to market close."""
        await self.log_step(
            action_type="EOD_PURGE",
            thought="Purging all unmatched and queuing orders before 16:30 close.",
        )
        try:
            from app.services.eod_service import eod_service
            result = await eod_service.cancel_all_pending_orders()
            await self.log_step(action_type="EOD_PURGE_SUCCESS", output_result=result, is_success=True)
            return result
        except Exception as exc:
            logger.error(f"EOD purge error: {exc}")
            await self.log_step(action_type="EOD_PURGE_ERROR", output_result=str(exc), is_success=False)
            return {"error": str(exc)}
