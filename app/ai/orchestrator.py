import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.ai.agents import (
    SessionSentinelAgent,
    MarketAnalystAgent,
    OrderExecutionAgent,
    SBLManagerAgent,
    PortfolioRiskAgent,
)
from app.ai.memory import agent_memory
from app.core.config import settings

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """
    Central PT-MRO Master Orchestrator implementing Nick Saraev's Agentic Architecture:
    - Planning: Evaluates market conditions & active regime to formulate plans.
    - Tools: Coordinates the 5 Specialized Sub-Agents and their deterministic tools.
    - Memory: Manages Dual-Store context (In-memory working state + SQLite persistent audit).
    - Reflection: Inspects outputs against DoD and dispatches failures to Self-Annealing.
    - Orchestration: Coordinates background regime cycles and on-demand MCP invocations.
    """

    def __init__(self):
        self.session_agent = SessionSentinelAgent()
        self.market_agent = MarketAnalystAgent()
        self.order_agent = OrderExecutionAgent()
        self.sbl_agent = SBLManagerAgent()
        self.portfolio_agent = PortfolioRiskAgent()

        self._running = False
        self._background_task: Optional[asyncio.Task] = None
        self._current_regime = "INITIALIZING"

    # =========================================================================
    # PT-MRO Core Lifecycle
    # =========================================================================

    async def execute_pt_mro_cycle(self, regime: str, trigger_source: str = "SCHEDULE") -> Dict[str, Any]:
        """
        Executes a complete Planning -> Tools -> Memory -> Reflection -> Orchestration cycle.
        """
        self._current_regime = regime
        agent_memory.set_working_key("active_regime", regime)

        # 0. Kill Switch Gate Check
        from app.services.kill_switch_service import kill_switch_service
        if kill_switch_service.is_active():
            logger.warning(f"Cycle [{regime}] aborted: Emergency Kill Switch is ACTIVE.")
            return {"status": "ABORTED", "reason": "KILL_SWITCH_ACTIVE", "regime": regime}

        # 1. Planning (P)
        plan = await self._plan_regime_actions(regime)
        await agent_memory.log_decision(
            agent_name="MasterOrchestrator",
            action_type="PLAN",
            regime=regime,
            thought=f"Formulated execution plan with {len(plan['tasks'])} sub-tasks for regime: {regime}",
            input_context={"trigger_source": trigger_source},
            output_result=plan,
            is_success=True,
        )

        cycle_results = []
        overall_success = True

        # 2. Tools & Sub-Agent Execution (T) & Memory (M)
        for task in plan.get("tasks", []):
            task_name = task.get("name")
            target_agent = task.get("agent")
            payload = task.get("payload", {})

            try:
                task_res = await self._dispatch_task(target_agent, task_name, payload)
                cycle_results.append({"task": task_name, "agent": target_agent, "result": task_res, "status": "SUCCESS"})
            except Exception as task_err:
                logger.error(f"Error executing task [{task_name}] by [{target_agent}]: {task_err}")
                overall_success = False

                # 3. Reflection & Self-Annealing (R)
                reflection = await self._reflect_and_anneal(task_name, target_agent, task_err)
                cycle_results.append({
                    "task": task_name,
                    "agent": target_agent,
                    "status": "RECOVERED" if reflection.get("recovered") else "FAILED",
                    "reflection": reflection,
                })

        # 4. Orchestration & State Consolidation (O)
        final_summary = {
            "regime": regime,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger_source": trigger_source,
            "overall_success": overall_success,
            "tasks_executed": len(cycle_results),
            "results": cycle_results,
        }

        await agent_memory.log_decision(
            agent_name="MasterOrchestrator",
            action_type="ORCHESTRATION_CYCLE_COMPLETE",
            regime=regime,
            thought=f"Completed PT-MRO cycle for {regime}. Success: {overall_success}",
            output_result=final_summary,
            is_success=overall_success,
        )

        return final_summary

    async def _plan_regime_actions(self, regime: str) -> Dict[str, Any]:
        """Formulates deterministic task lists according to regime specifications."""
        regime_upper = regime.upper()

        if "PRE_MARKET" in regime_upper or "09:30" in regime_upper:
            return {
                "regime": regime_upper,
                "tasks": [
                    {"name": "check_health", "agent": "session_agent", "payload": {}},
                    {"name": "sync_portfolio", "agent": "portfolio_agent", "payload": {}},
                    {"name": "audit_corporate_actions", "agent": "sbl_agent", "payload": {}},
                ]
            }

        elif "AUTO_TRADING" in regime_upper or "TACTICAL" in regime_upper:
            return {
                "regime": regime_upper,
                "tasks": [
                    {"name": "audit_risk_and_tpsl", "agent": "portfolio_agent", "payload": {}},
                    {"name": "negotiate_prices", "agent": "order_agent", "payload": {}},
                ]
            }

        elif "DAY_CLOSE" in regime_upper or "16:00" in regime_upper:
            return {
                "regime": regime_upper,
                "tasks": [
                    {"name": "purge_eod_orders", "agent": "order_agent", "payload": {}},
                ]
            }

        elif "POST_MARKET" in regime_upper or "EOD" in regime_upper or "16:35" in regime_upper:
            return {
                "regime": regime_upper,
                "tasks": [
                    {"name": "generate_eod_summary", "agent": "portfolio_agent", "payload": {}},
                    {"name": "logout_all", "agent": "session_agent", "payload": {}},
                ]
            }

        # Default fallback regime
        return {
            "regime": regime_upper,
            "tasks": [
                {"name": "check_health", "agent": "session_agent", "payload": {}},
            ]
        }

    async def _dispatch_task(self, agent_name: str, task_name: str, payload: Dict[str, Any]) -> Any:
        """Dispatches a task dynamically to the corresponding specialized Sub-Agent."""
        if agent_name == "session_agent":
            method = getattr(self.session_agent, task_name)
            return await method(**payload)
        elif agent_name == "market_agent":
            method = getattr(self.market_agent, task_name)
            return await method(**payload)
        elif agent_name == "order_agent":
            method = getattr(self.order_agent, task_name)
            return await method(**payload)
        elif agent_name == "sbl_agent":
            method = getattr(self.sbl_agent, task_name)
            return await method(**payload)
        elif agent_name == "portfolio_agent":
            method = getattr(self.portfolio_agent, task_name)
            return await method(**payload)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")

    async def _reflect_and_anneal(self, task_name: str, agent_name: str, error: Exception) -> Dict[str, Any]:
        """Reflects on error and delegates to Self-Annealing Engine."""
        from app.services.self_annealing_engine import self_annealing_engine
        logger.warning(f"Reflection triggered for [{agent_name}] during [{task_name}]: {error}")
        return await self_annealing_engine.handle_execution_failure(
            workflow_name=f"{agent_name}_{task_name}",
            failed_step=task_name,
            error=error,
        )

    # =========================================================================
    # Background Autonomous Loop
    # =========================================================================

    def start_background_loop(self) -> None:
        """Starts the autonomous PT-MRO background loop."""
        if self._running:
            return
        self._running = True
        self._background_task = asyncio.create_task(self._run_loop())
        logger.info("Autonomous MasterOrchestrator PT-MRO background loop started.")

    async def stop_background_loop(self) -> None:
        """Stops the autonomous PT-MRO background loop."""
        self._running = False
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        logger.info("Autonomous MasterOrchestrator PT-MRO background loop stopped.")

    async def _run_loop(self) -> None:
        """Periodic background evaluation loop."""
        while self._running:
            try:
                # Run health check & risk audit pulse every 60 seconds
                await asyncio.sleep(60)
                if not self._running:
                    break
                await self.execute_pt_mro_cycle(regime="PULSE_HEARTBEAT", trigger_source="DAEMON")
            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error(f"Error in MasterOrchestrator background loop: {loop_err}")
                await asyncio.sleep(10)


# Global orchestrator singleton instance
master_orchestrator = MasterOrchestrator()
