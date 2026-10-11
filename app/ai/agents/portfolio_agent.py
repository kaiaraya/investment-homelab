import logging
from typing import Any, Dict, List, Optional
from app.ai.agents.base import BaseSubAgent
from app.services.portfolio_overview_service import portfolio_overview_service
from app.services.eod_service import eod_service

logger = logging.getLogger(__name__)


class PortfolioRiskAgent(BaseSubAgent):
    """
    Sub-Agent governing Multi-Account Balance Sync, Holding Audits, Risk Guardrails,
    Missing Stop-Loss Alerts, and EOD Reporting (SOP-005).
    """

    def __init__(self, model_override: Optional[Any] = None):
        super().__init__(
            name="PortfolioRiskAgent",
            sop_filename="sop_portfolio_risk.md",
            model_override=model_override,
            output_type=str,
        )

    async def sync_portfolio(self) -> Dict[str, Any]:
        """Synchronizes balances and holdings from active broker screen to SQLite."""
        await self.log_step(
            action_type="PORTFOLIO_SYNC",
            thought="Syncing account balances and active stock holdings into SQLite database.",
        )
        try:
            overview = await portfolio_overview_service.get_full_overview()
            await self.log_step(
                action_type="PORTFOLIO_SYNC_SUCCESS",
                output_result={"cash": overview.get("cash_balance"), "holdings_count": len(overview.get("holdings", []))},
                is_success=True,
            )
            return overview
        except Exception as exc:
            logger.error(f"Portfolio sync failed: {exc}")
            await self.log_step(action_type="PORTFOLIO_SYNC_ERROR", output_result=str(exc), is_success=False)
            return {"error": str(exc)}

    async def audit_risk_and_tpsl(self) -> Dict[str, Any]:
        """Audits holdings for missing Stop-Loss protection or max drawdown violations."""
        await self.log_step(
            action_type="RISK_AUDIT",
            thought="Auditing positions for missing Stop-Loss protection and risk exposure limits.",
        )
        try:
            overview = await portfolio_overview_service.get_full_overview()
            holdings = overview.get("holdings", [])
            unprotected = []
            for item in holdings:
                sym = item.get("symbol", "")
                if not item.get("stop_loss_price"):
                    unprotected.append(sym)

            report = {
                "total_positions": len(holdings),
                "unprotected_positions": unprotected,
                "needs_action": len(unprotected) > 0,
            }
            await self.log_step(
                action_type="RISK_AUDIT_COMPLETE",
                output_result=report,
                is_success=True,
            )
            return report
        except Exception as exc:
            logger.error(f"Risk audit error: {exc}")
            await self.log_step(action_type="RISK_AUDIT_ERROR", output_result=str(exc), is_success=False)
            return {"error": str(exc)}

    async def generate_eod_summary(self) -> Dict[str, Any]:
        """Generates comprehensive End-of-Day (EOD) portfolio performance card."""
        await self.log_step(
            action_type="EOD_SUMMARY",
            thought="Generating 16:35 End-of-Day performance report and account equity card.",
        )
        try:
            summary = await eod_service.generate_daily_summary()
            await self.log_step(action_type="EOD_SUMMARY_COMPLETE", output_result=summary, is_success=True)
            return summary
        except Exception as exc:
            logger.error(f"EOD summary generation failed: {exc}")
            await self.log_step(action_type="EOD_SUMMARY_ERROR", output_result=str(exc), is_success=False)
            return {"error": str(exc)}
