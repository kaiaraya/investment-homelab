import logging
from typing import Any, Dict, Optional
from app.ai.agents.base import BaseSubAgent
from app.services.sbl_intelligence_service import sbl_intelligence_service

logger = logging.getLogger(__name__)


class SBLManagerAgent(BaseSubAgent):
    """
    Sub-Agent governing SBL Inventory Scrapes, Stock Borrowing, Unmatched Hold Policy,
    Corporate Action Safeguards, and Return upon Cover (SOP-004).
    """

    def __init__(self, model_override: Optional[Any] = None):
        super().__init__(
            name="SBLManagerAgent",
            sop_filename="sop_sbl_lifecycle.md",
            model_override=model_override,
            output_type=str,
        )

    async def check_inventory(self, symbol: str) -> Dict[str, Any]:
        """Scrapes Krungsri SBL portal for available borrow quota."""
        clean_symbol = symbol.strip().upper()
        await self.log_step(
            action_type="SBL_CHECK_INVENTORY",
            thought=f"Checking SBL Available Inventory for {clean_symbol}",
            input_context={"symbol": clean_symbol},
        )
        try:
            inventory = await sbl_intelligence_service.get_available_inventory(clean_symbol)
            await self.log_step(
                action_type="SBL_INVENTORY_RESULT",
                output_result=inventory,
                is_success=True,
            )
            return inventory
        except Exception as exc:
            logger.error(f"Failed to check SBL inventory: {exc}")
            await self.log_step(action_type="SBL_INVENTORY_ERROR", output_result=str(exc), is_success=False)
            return {"symbol": clean_symbol, "available_volume": 0, "error": str(exc)}

    async def borrow_stock(self, symbol: str, volume: int) -> Dict[str, Any]:
        """Borrows stock on Krungsri SBL portal and records borrow transaction."""
        clean_symbol = symbol.strip().upper()
        await self.log_step(
            action_type="SBL_BORROW_REQUEST",
            thought=f"Executing borrow of {volume} shares of {clean_symbol} (Rate: 5.5% p.a.)",
            input_context={"symbol": clean_symbol, "volume": volume},
        )
        try:
            result = await sbl_intelligence_service.borrow_stock(clean_symbol, volume)
            await self.log_step(action_type="SBL_BORROW_SUCCESS", output_result=result, is_success=True)
            return result
        except Exception as exc:
            logger.error(f"SBL borrow failed: {exc}")
            await self.log_step(action_type="SBL_BORROW_ERROR", output_result=str(exc), is_success=False)
            return {"status": "FAILED", "error": str(exc)}

    async def return_stock(self, lot_id: str, volume: Optional[int] = None) -> Dict[str, Any]:
        """Returns borrowed lot to SBL inventory to cease interest accumulation."""
        await self.log_step(
            action_type="SBL_RETURN_REQUEST",
            thought=f"Returning SBL lot #{lot_id} to broker inventory.",
            input_context={"lot_id": lot_id, "volume": volume},
        )
        try:
            result = await sbl_intelligence_service.return_stock(lot_id, volume)
            await self.log_step(action_type="SBL_RETURN_SUCCESS", output_result=result, is_success=True)
            return result
        except Exception as exc:
            logger.error(f"SBL return failed: {exc}")
            await self.log_step(action_type="SBL_RETURN_ERROR", output_result=str(exc), is_success=False)
            return {"status": "FAILED", "error": str(exc)}

    async def audit_corporate_actions(self) -> Dict[str, Any]:
        """Audits active SBL lots against XD (Ex-Dividend) dates to prevent compensation costs."""
        await self.log_step(
            action_type="SBL_XD_AUDIT",
            thought="Auditing active SBL borrow lots against upcoming Ex-Dividend (XD) dates.",
        )
        try:
            report = await sbl_intelligence_service.check_corporate_actions()
            await self.log_step(action_type="SBL_XD_AUDIT_COMPLETE", output_result=report, is_success=True)
            return report
        except Exception as exc:
            logger.error(f"SBL XD audit error: {exc}")
            await self.log_step(action_type="SBL_XD_AUDIT_ERROR", output_result=str(exc), is_success=False)
            return {"error": str(exc)}
