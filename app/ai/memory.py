import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from app.db.session import AsyncSessionLocal
from app.db.models import AgentDecisionLog

logger = logging.getLogger(__name__)


class DualStoreMemory:
    """
    PT-MRO Memory Engine implementing a Dual-Store Architecture:
    1. Short-Term Working Memory: In-memory cache for live market quotes,
       active session parameters, streaming subscriptions, and intermediate agent thoughts.
    2. Long-Term Persistent Memory: SQLite-backed audit log storing agent reasoning,
       decisions, tool calls, and reflection feedback.
    """

    def __init__(self):
        self._working_memory: Dict[str, Any] = {
            "active_regime": "INITIALIZING",
            "active_symbols": set(),
            "latest_quotes": {},
            "active_orders": {},
            "unmatched_orders": {},
            "active_trajectories": [],
            "last_heartbeat": None,
        }

    # ==========================================
    # 1. Short-Term Working Memory Operations
    # ==========================================

    def set_working_key(self, key: str, value: Any) -> None:
        """Stores or updates an ephemeral working memory item."""
        self._working_memory[key] = value

    def get_working_key(self, key: str, default: Any = None) -> Any:
        """Retrieves an ephemeral working memory item."""
        return self._working_memory.get(key, default)

    def update_quote(self, symbol: str, quote_data: Dict[str, Any]) -> None:
        """Updates the cached high-frequency quote for a symbol."""
        self._working_memory["latest_quotes"][symbol.upper()] = {
            **quote_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves the cached high-frequency quote for a symbol."""
        return self._working_memory["latest_quotes"].get(symbol.upper())

    def get_all_working_memory(self) -> Dict[str, Any]:
        """Returns a snapshot of the current working memory state (symbols converted to list)."""
        snapshot = dict(self._working_memory)
        if isinstance(snapshot.get("active_symbols"), set):
            snapshot["active_symbols"] = list(snapshot["active_symbols"])
        return snapshot

    def clear_working_memory(self) -> None:
        """Resets ephemeral working memory state."""
        self._working_memory["active_symbols"] = set()
        self._working_memory["latest_quotes"] = {}
        self._working_memory["active_orders"] = {}
        self._working_memory["unmatched_orders"] = {}
        self._working_memory["active_trajectories"] = []

    # ==========================================
    # 2. Long-Term Persistent Memory Operations
    # ==========================================

    async def log_decision(
        self,
        agent_name: str,
        action_type: str,
        regime: Optional[str] = None,
        thought: Optional[str] = None,
        input_context: Optional[Any] = None,
        output_result: Optional[Any] = None,
        is_success: bool = True,
    ) -> int:
        """
        Asynchronously commits an agent decision, tool invocation, or reflection outcome
        to the SQLite persistent audit table.
        """
        ctx_str = json.dumps(input_context, default=str) if isinstance(input_context, (dict, list)) else (str(input_context) if input_context else None)
        out_str = json.dumps(output_result, default=str) if isinstance(output_result, (dict, list)) else (str(output_result) if output_result else None)

        try:
            async with AsyncSessionLocal() as session:
                log_entry = AgentDecisionLog(
                    agent_name=agent_name,
                    action_type=action_type,
                    regime=regime or self._working_memory.get("active_regime"),
                    thought=thought,
                    input_context=ctx_str,
                    output_result=out_str,
                    is_success=is_success,
                )
                session.add(log_entry)
                await session.commit()
                await session.refresh(log_entry)
                logger.debug(f"Logged agent decision #{log_entry.id} for [{agent_name}] -> {action_type}")
                return log_entry.id
        except Exception as exc:
            logger.error(f"Failed to commit agent decision log to SQLite: {exc}")
            return -1

    async def get_recent_audit_trail(
        self,
        agent_name: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the most recent agent decisions and actions from SQLite.
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentDecisionLog).order_by(desc(AgentDecisionLog.id)).limit(limit)
                if agent_name:
                    stmt = stmt.where(AgentDecisionLog.agent_name == agent_name)
                if action_type:
                    stmt = stmt.where(AgentDecisionLog.action_type == action_type)

                result = await session.execute(stmt)
                rows = result.scalars().all()

                return [
                    {
                        "id": row.id,
                        "agent_name": row.agent_name,
                        "action_type": row.action_type,
                        "regime": row.regime,
                        "thought": row.thought,
                        "input_context": json.loads(row.input_context) if row.input_context and row.input_context.startswith(("{", "[")) else row.input_context,
                        "output_result": json.loads(row.output_result) if row.output_result and row.output_result.startswith(("{", "[")) else row.output_result,
                        "is_success": row.is_success,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                    for row in rows
                ]
        except Exception as exc:
            logger.error(f"Failed to query agent audit trail from SQLite: {exc}")
            return []


# Global memory singleton instance
agent_memory = DualStoreMemory()
