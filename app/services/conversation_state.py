"""
Per-user LINE Conversation State Machine — ENGINE ONLY (2026-10-12)
===================================================================

Problem
-------
Every LINE command today is **single-shot**: `app/services/line_service.py`
`_handle_text_message()` is one linear if/elif chain and each branch answers and
returns. A multi-step flow (e.g. query one symbol, and later
symbol → side → volume → price → confirm) has nowhere to keep the half-collected
slots between two webhook deliveries.

This module IS that place: a **lightweight, per-user, TTL-evicted** conversation
store plus **declarative flow specs**. It performs no I/O — no DB, no LINE API,
no network — so it is unit-testable in isolation. The orchestrator that drives it
and executes the terminal step is `line_service._handle_conversation_turn()`.

Design
------
* keyed by ``source.userId`` — works for the group chat (the sender is a group
  member) and for the 1:1 chat with the OA (``source.type == "user"``).
* one in-memory dict with lazy TTL eviction (``CONVERSATION_TTL_SECONDS``).
  Same convention as ``TradeCenterService._pending_batches`` /
  ``ActionCenterService._pending_actions`` (this gateway is a single-process
  uvicorn app; a restart drops in-flight conversations by design).
* **Authorization gate** (operator Decision A, 2026-10-12): a flow may only be
  started/advanced by an authorized sender. ``LINE_ADMIN_USER_ID`` is
  deliberately NOT consulted — the 1:1 chat with the OA itself is the operator
  channel, and the private group (``LINE_GROUP_ID``) is the second channel.

ORDER SAFETY (hard contract — see ``docs/handoff/TASK-line-conversation-state.md``)
----------------------------------------------------------------------------------
Any future ``order_entry`` flow terminal step MUST route through
``trade_center_service.prepare_order_approval()`` — which runs
``validator.validate_all`` (board-lot, SET tick size, value ceiling, SHORT
uptick) and only emits a confirmation card. Execution stays with the existing
``confirm_order`` postback → ``execute_confirmed_order`` → ``trade_dispatcher``
(PIN-gated LIVE mode + value limit + HITL gate). A flow must NEVER call
``trade_dispatcher.dispatch_order()`` or a broker driver directly.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Flow lifetime in seconds (module constant — no `settings` entry yet, keeps the
#: change surface small; override per-instance via ``ConversationStateStore(ttl_seconds=...)``).
CONVERSATION_TTL_SECONDS: int = 300

#: Words that abandon the active flow.
CANCEL_WORDS = frozenset({"cancel", "ยกเลิก", "ออก", "quit", "exit", "ปิด"})
#: Words that restart the active flow from its first step.
RESTART_WORDS = frozenset({"restart", "เริ่มใหม่", "new", "reset"})

#: A SET symbol: letters/digits/'.' up to 10 chars (TFEX symbols carry digits).
SYMBOL_RE = re.compile(r"^[A-Za-z0-9.]{1,10}$")


def _now() -> float:
    """Indirection point so tests can freeze/advance time."""
    return time.time()


# --------------------------------------------------------------------------- #
# Value parsers (pure — used both by the flow spec and by the unit tests)
# --------------------------------------------------------------------------- #
def parse_symbol(text: str) -> Tuple[bool, Any, Optional[str]]:
    """Validate a stock symbol. Returns ``(ok, value, error_message)``."""
    raw = (text or "").strip().upper()
    if not SYMBOL_RE.match(raw):
        return (
            False,
            None,
            "⚠️ สัญลักษณ์ไม่ถูกต้อง — พิมพ์ตัวอักษร/ตัวเลขไม่เกิน 10 ตัว "
            "(เช่น PTT, AOT) หรือ CANCEL",
        )
    return True, raw, None


#: Accepted answers for the "which metric" step → canonical metric key.
_METRIC_MAP: Dict[str, str] = {
    "1": "position", "พอร์ต": "position", "position": "position", "หุ้น": "position",
    "2": "orders", "คำสั่ง": "orders", "orders": "orders",
    "3": "tpsl", "ตั้งค่า": "tpsl", "tp/sl": "tpsl", "tpsl": "tpsl",
}


def parse_metric(text: str) -> Tuple[bool, Any, Optional[str]]:
    """Validate the metric chooser. Returns ``(ok, value, error_message)``."""
    value = _METRIC_MAP.get((text or "").strip().lower())
    if not value:
        return (
            False,
            None,
            "⚠️ เลือกไม่ถูกต้อง — พิมพ์ 1) สรุปพอร์ต  2) คำสั่งล่าสุด  3) TP/SL & Trigger "
            "(หรือ CANCEL)",
        )
    return True, value, None


# --------------------------------------------------------------------------- #
# Flow declaration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StepSpec:
    """One collected slot of a flow."""

    key: str
    prompt: str
    slot: str
    parse: Callable[[str], Tuple[bool, Any, Optional[str]]]


@dataclass(frozen=True)
class FlowSpec:
    """Declarative multi-step flow."""

    name: str
    title: str
    trigger: re.Pattern
    steps: Tuple[StepSpec, ...]
    terminal_step: str = "report"

    def first_step(self) -> str:
        return self.steps[0].key

    def step_keys(self) -> List[str]:
        return [s.key for s in self.steps]

    def step_spec(self, key: str) -> Optional[StepSpec]:
        """The spec for ``key`` — ``None`` once the flow reaches its terminal step."""
        for spec in self.steps:
            if spec.key == key:
                return spec
        return None

    def next_step(self, key: str) -> str:
        """Next step after ``key`` (the terminal step when ``key`` is the last one)."""
        keys = self.step_keys()
        if key in keys and keys.index(key) + 1 < len(keys):
            return keys[keys.index(key) + 1]
        return self.terminal_step


SYMBOL_QUERY_FLOW = FlowSpec(
    name="symbol_query",
    title="ตรวจสอบหุ้นรายตัว",
    trigger=re.compile(
        r"^(?:query|check|เช็คหุ้น|ถามหุ้น|ข้อมูลหุ้น)(?:\s+([A-Za-z0-9.]{1,10}))?$",
        re.IGNORECASE,
    ),
    steps=(
        StepSpec(
            key="await_symbol",
            slot="symbol",
            prompt=(
                "🔎 ตรวจสอบหุ้นรายตัว\n"
                "พิมพ์สัญลักษณ์หุ้นที่ต้องการ (เช่น PTT, AOT) หรือ CANCEL เพื่อยกเลิก"
            ),
            parse=parse_symbol,
        ),
        StepSpec(
            key="await_metric",
            slot="metric",
            prompt=(
                "เลือกข้อมูลที่ต้องการ:\n"
                "1) 📦 สรุปพอร์ต\n"
                "2) 🧾 คำสั่งล่าสุด\n"
                "3) 🎯 TP/SL & Trigger\n"
                "(พิมพ์ CANCEL เพื่อยกเลิก)"
            ),
            parse=parse_metric,
        ),
    ),
)

#: flow name → spec. `order_entry` is reserved (design-only, see module docstring).
FLOWS: Dict[str, FlowSpec] = {SYMBOL_QUERY_FLOW.name: SYMBOL_QUERY_FLOW}


# --------------------------------------------------------------------------- #
# State + store
# --------------------------------------------------------------------------- #
@dataclass
class ConversationState:
    """The half-collected slots of one user's in-flight flow."""

    user_id: str
    flow: str
    step: str
    slots: Dict[str, Any] = field(default_factory=dict)
    chat_id: Optional[str] = None
    chat_type: str = "user"
    created_at: float = 0.0
    updated_at: float = 0.0
    expires_at: float = 0.0

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else _now()) >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "flow": self.flow,
            "step": self.step,
            "slots": dict(self.slots),
            "chat_type": self.chat_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }


class ConversationStateStore:
    """
    Per-user conversation registry with TTL eviction.

    Deliberately tiny and in-memory: one process, one dict, lazy eviction on read
    (no background sweeper → nothing to cancel at shutdown). ``purge_expired()``
    is exposed for diagnostics/tests.
    """

    def __init__(self, ttl_seconds: int = CONVERSATION_TTL_SECONDS) -> None:
        self._states: Dict[str, ConversationState] = {}
        self._ttl = max(0, int(ttl_seconds))

    # -- config / diagnostics -------------------------------------------------
    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def set_ttl(self, seconds: int) -> None:
        """Adjust the flow timeout (ops/tests). ``0`` expires every state immediately."""
        self._ttl = max(0, int(seconds))

    def reset(self) -> None:
        """Drop every in-flight conversation (test/isolation hook)."""
        self._states.clear()

    def snapshot(self) -> Dict[str, Any]:
        """JSON-safe view of the live conversations (diagnostics)."""
        return {
            "active_count": len(self._states),
            "ttl_seconds": self._ttl,
            "states": {uid: st.to_dict() for uid, st in self._states.items()},
        }

    # -- authorization gate (Decision A) --------------------------------------
    def is_authorized(
        self,
        user_id: Optional[str],
        source_type: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> bool:
        """
        May this sender drive a conversation flow?

        Allow when EITHER:
          1. ``LINE_SIMULATION_MODE=True`` — no real LINE (dev / unit tests);
          2. the message arrived in the configured private group
             (``source.groupId == settings.LINE_GROUP_ID``);
          3. it is the 1:1 chat with the OA (``source.type == "user"`` + a userId).

        ``LINE_ADMIN_USER_ID`` is intentionally NOT consulted (operator Decision A).
        """
        if getattr(settings, "LINE_SIMULATION_MODE", True):
            return True
        configured_group = getattr(settings, "LINE_GROUP_ID", None)
        if group_id and configured_group and group_id == configured_group:
            return True
        if source_type == "user" and bool(user_id):
            return True
        return False

    # -- lifecycle ------------------------------------------------------------
    def get(self, user_id: Optional[str]) -> Optional[ConversationState]:
        """Active state for ``user_id`` (lazily evicted when expired)."""
        if not user_id:
            return None
        state = self._states.get(user_id)
        if state is None:
            return None
        if state.is_expired():
            self._states.pop(user_id, None)
            logger.info("[Conversation] user=%s flow=%s expired", user_id, state.flow)
            return None
        return state

    def is_active(self, user_id: Optional[str]) -> bool:
        return self.get(user_id) is not None

    def start(
        self,
        user_id: str,
        flow: str,
        step: Optional[str] = None,
        slots: Optional[Dict[str, Any]] = None,
        chat_id: Optional[str] = None,
        chat_type: str = "user",
    ) -> ConversationState:
        """Create (or overwrite) the flow state for ``user_id``."""
        now = _now()
        spec = FLOWS.get(flow)
        state = ConversationState(
            user_id=user_id,
            flow=flow,
            step=step or (spec.first_step() if spec else ""),
            slots=dict(slots or {}),
            chat_id=chat_id,
            chat_type=chat_type or "user",
            created_at=now,
            updated_at=now,
            expires_at=now + self._ttl,
        )
        self._states[user_id] = state
        logger.info("[Conversation] start user=%s flow=%s step=%s", user_id, flow, state.step)
        return state

    def start_flow(
        self,
        user_id: str,
        flow: str,
        preselect: Optional[str] = None,
        chat_id: Optional[str] = None,
        chat_type: str = "user",
    ) -> ConversationState:
        """
        Start ``flow``; when ``preselect`` is given (e.g. ``QUERY PTT``) the first
        step's slot is pre-filled and the flow opens on the second step.
        """
        spec = FLOWS[flow]
        slots: Dict[str, Any] = {}
        step = spec.first_step()
        if preselect:
            slots[spec.steps[0].slot] = preselect
            step = spec.next_step(spec.first_step())
        return self.start(user_id, flow, step=step, slots=slots, chat_id=chat_id, chat_type=chat_type)

    def advance(self, user_id: str, **slots: Any) -> Optional[ConversationState]:
        """Store ``slots`` and move to the flow's next step (refreshes the TTL)."""
        state = self.get(user_id)
        if state is None:
            return None
        spec = FLOWS.get(state.flow)
        state.slots.update({k: v for k, v in slots.items() if v is not None})
        if spec is not None:
            state.step = spec.next_step(state.step)
        self.touch(user_id)
        return state

    def touch(self, user_id: str) -> Optional[ConversationState]:
        """Refresh the TTL without moving the step (used on an invalid answer)."""
        state = self._states.get(user_id)
        if state is None:
            return None
        now = _now()
        state.updated_at = now
        state.expires_at = now + self._ttl
        return state

    def clear(self, user_id: Optional[str]) -> bool:
        """Drop the conversation. Returns True when something was removed."""
        if not user_id:
            return False
        removed = self._states.pop(user_id, None)
        if removed is not None:
            logger.info("[Conversation] cleared user=%s flow=%s", user_id, removed.flow)
        return removed is not None

    def purge_expired(self) -> int:
        """Evict every expired conversation; returns how many were dropped."""
        expired = [uid for uid, st in self._states.items() if st.is_expired()]
        for uid in expired:
            self._states.pop(uid, None)
        return len(expired)

    def purge(self) -> int:
        """Alias for :meth:`purge_expired` (diagnostics naming)."""
        return self.purge_expired()

    # -- text helpers ---------------------------------------------------------
    def is_cancel(self, text: str) -> bool:
        """True when ``text`` abandons the active flow."""
        return (text or "").strip().lower() in CANCEL_WORDS

    def is_restart(self, text: str) -> bool:
        """True when ``text`` restarts the active flow from step 1."""
        return (text or "").strip().lower() in RESTART_WORDS

    def match_flow(self, text: str) -> Optional[Tuple[FlowSpec, Optional[str]]]:
        """
        Return ``(flow, preselected_symbol)`` when ``text`` triggers a flow, else None.

        ``QUERY PTT`` → ``(symbol_query, "PTT")``; bare ``QUERY`` → ``(symbol_query, None)``.
        """
        candidate = (text or "").strip()
        for spec in FLOWS.values():
            match = spec.trigger.match(candidate)
            if match:
                groups = match.groups()
                return spec, (groups[0].upper() if groups and groups[0] else None)
        return None

    def get_flow(self, name: Optional[str]) -> Optional[FlowSpec]:
        """
        The spec for ``name`` — accessor for the module-level `FLOWS` registry.

        Callers import the *singleton* (`conversation_state`), which shadows the
        module name, so the registry must be reachable as an attribute/method.
        """
        return FLOWS.get(name or "")

    @property
    def flow_names(self) -> List[str]:
        return list(FLOWS.keys())


#: Global singleton (same convention as `line_service` / `trade_dispatcher`).
conversation_state = ConversationStateStore()
