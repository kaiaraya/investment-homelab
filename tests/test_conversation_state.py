"""
Unit tests for the per-user LINE conversation state machine engine
(`app/services/conversation_state.py`) — 2026-10-12.

Covers (see `docs/handoff/TASK-line-conversation-state.md`):

  * flow specs: trigger matching (+ `QUERY PTT` pre-select), step order, terminal step
  * pure parsers: symbol / metric validation
  * store lifecycle: start / get / advance / touch / clear / purge / snapshot
  * TTL eviction (deterministic via a frozen clock) + per-user isolation
  * authorization gate (Decision A): simulation OR 1:1 OA chat OR configured group;
    `LINE_ADMIN_USER_ID` is deliberately NOT part of the decision

No DB, no LINE API, no network — the engine is I/O free by design.
"""

import pytest

from app.core.config import settings
from app.services import conversation_state as conv

T = conv.CONVERSATION_TTL_SECONDS


@pytest.fixture(autouse=True)
def _clean_conversations():
    """The store is a module singleton — never leak state between tests."""
    conv.conversation_state.reset()
    conv.conversation_state.set_ttl(T)
    yield
    conv.conversation_state.reset()
    conv.conversation_state.set_ttl(T)


@pytest.fixture
def frozen_clock(monkeypatch):
    """Freeze `conversation_state._now()` so TTL behaviour is deterministic."""
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(conv, "_now", lambda: clock["t"])
    return clock


# --------------------------------------------------------------------------- #
# Flow specs
# --------------------------------------------------------------------------- #
def test_bare_trigger_matches_flow_without_preselect():
    matched = conv.conversation_state.match_flow("เช็คหุ้น")
    assert matched is not None
    flow, preselect = matched
    assert flow.name == "symbol_query"
    assert preselect is None


def test_trigger_with_symbol_preselects_it():
    flow, preselect = conv.conversation_state.match_flow("QUERY PTT")
    assert flow.name == "symbol_query"
    assert preselect == "PTT"


def test_non_trigger_text_matches_nothing():
    for text in ("hello", "action", "set", "Close AP", "849201", ""):
        assert conv.conversation_state.match_flow(text) is None


def test_flow_spec_step_order_and_terminal():
    spec = conv.SYMBOL_QUERY_FLOW
    assert spec.first_step() == "await_symbol"
    assert spec.step_keys() == ["await_symbol", "await_metric"]
    assert spec.next_step("await_symbol") == "await_metric"
    assert spec.next_step("await_metric") == spec.terminal_step
    assert spec.step_spec("await_symbol") is not None
    assert spec.step_spec(spec.terminal_step) is None


def test_parse_symbol_accepts_and_normalizes():
    assert conv.parse_symbol(" ptt ") == (True, "PTT", None)


def test_parse_symbol_rejects_malformed():
    for bad in ("", "TOOLONGSYMBOL", "!!!", "PTT;DROP"):
        ok, value, err = conv.parse_symbol(bad)
        assert ok is False and value is None and err


def test_parse_metric_accepts_keywords_and_digits():
    assert conv.parse_metric("1")[1] == "position"
    assert conv.parse_metric("พอร์ต")[1] == "position"
    assert conv.parse_metric("2")[1] == "orders"
    assert conv.parse_metric("3")[1] == "tpsl"
    assert conv.parse_metric("tpsl")[1] == "tpsl"


def test_parse_metric_rejects_unknown():
    ok, value, err = conv.parse_metric("9")
    assert ok is False and value is None and err


# --------------------------------------------------------------------------- #
# Store lifecycle
# --------------------------------------------------------------------------- #
def test_store_starts_empty_and_get_is_none():
    store = conv.ConversationStateStore()
    assert store.snapshot()["active_count"] == 0
    assert store.get("nobody") is None
    assert store.get(None) is None


def test_start_then_get_returns_state(frozen_clock):
    store = conv.ConversationStateStore()
    state = store.start("U1", "symbol_query", chat_type="user")
    assert state.step == "await_symbol"
    assert store.get("U1") is state
    assert store.is_active("U1") is True
    assert store.is_active("U2") is False


def test_start_flow_with_preselect_skips_first_step(frozen_clock):
    store = conv.ConversationStateStore()
    state = store.start_flow("U1", "symbol_query", preselect="AOT")
    assert state.step == "await_metric"
    assert state.slots["symbol"] == "AOT"


def test_advance_stores_slots_and_reaches_terminal(frozen_clock):
    store = conv.ConversationStateStore()
    store.start("U1", "symbol_query")
    state = store.advance("U1", symbol="PTT")
    assert state.step == "await_metric" and state.slots["symbol"] == "PTT"
    state = store.advance("U1", metric="orders")
    assert state.step == "report" and state.slots["metric"] == "orders"


def test_advance_ignores_none_valued_slots(frozen_clock):
    store = conv.ConversationStateStore()
    store.start("U1", "symbol_query")
    assert "symbol" not in store.advance("U1", symbol=None).slots


def test_advance_returns_none_without_active_state(frozen_clock):
    store = conv.ConversationStateStore()
    assert store.advance("ghost", symbol="PTT") is None


def test_per_user_isolation(frozen_clock):
    store = conv.ConversationStateStore()
    store.start("U1", "symbol_query")
    store.advance("U1", symbol="PTT")
    store.start("U2", "symbol_query")
    assert store.get("U1").slots == {"symbol": "PTT"}
    assert store.get("U2").slots == {}
    assert store.snapshot()["active_count"] == 2


def test_clear_removes_only_that_user(frozen_clock):
    store = conv.ConversationStateStore()
    store.start("U1", "symbol_query")
    store.start("U2", "symbol_query")
    assert store.clear("U1") is True
    assert store.clear("U1") is False
    assert store.get("U1") is None and store.get("U2") is not None
    assert store.clear(None) is False


def test_touch_refreshes_ttl_without_moving_step(frozen_clock):
    store = conv.ConversationStateStore()
    state = store.start("U1", "symbol_query")
    frozen_clock["t"] += T - 10
    store.touch("U1")
    frozen_clock["t"] += 60            # past the original deadline, inside the new one
    assert store.get("U1") is state
    assert state.step == "await_symbol"


def test_state_expires_after_ttl(frozen_clock):
    store = conv.ConversationStateStore()
    store.start("U1", "symbol_query")
    frozen_clock["t"] += T - 1
    assert store.is_active("U1") is True
    frozen_clock["t"] += 2             # now >= expires_at
    assert store.get("U1") is None
    assert store.snapshot()["active_count"] == 0


def test_zero_ttl_expires_immediately(frozen_clock):
    store = conv.ConversationStateStore(ttl_seconds=0)
    store.start("U1", "symbol_query")
    assert store.get("U1") is None


def test_purge_expired_counts_only_expired(frozen_clock):
    store = conv.ConversationStateStore(ttl_seconds=10)
    store.start("U1", "symbol_query")
    frozen_clock["t"] += 5
    store.start("U2", "symbol_query")
    frozen_clock["t"] += 6             # U1 expired, U2 still alive
    assert store.purge_expired() == 1
    assert store.purge() >= 0
    assert store.is_active("U2") is True


def test_get_flow_accessor_exposes_the_registry():
    """
    `line_service` imports the SINGLETON (which shadows the module name), so the
    flow registry must be reachable through an accessor — regression guard for the
    `conversation_state.FLOWS` AttributeError found on 2026-10-12.
    """
    store = conv.ConversationStateStore()
    assert store.get_flow("symbol_query") is conv.SYMBOL_QUERY_FLOW
    assert store.get_flow("does_not_exist") is None
    assert store.get_flow(None) is None
    assert store.flow_names == ["symbol_query"]


def test_is_cancel_and_restart_keywords():
    store = conv.ConversationStateStore()
    assert store.is_cancel("ยกเลิก") and store.is_cancel("CANCEL")
    assert store.is_restart("เริ่มใหม่") and store.is_restart("Restart")
    assert not store.is_cancel("PTT") and not store.is_restart("PTT")


def test_snapshot_is_json_safe(frozen_clock):
    import json

    store = conv.ConversationStateStore()
    store.start("U1", "symbol_query")
    snapshot = store.snapshot()
    assert snapshot["ttl_seconds"] == T
    json.dumps(snapshot)  # must not raise


# --------------------------------------------------------------------------- #
# Authorization gate (operator Decision A, 2026-10-12)
#   allow = simulation OR 1:1 chat with the OA OR the configured private group
#   `LINE_ADMIN_USER_ID` is deliberately NOT consulted
# --------------------------------------------------------------------------- #
def test_gate_allows_everyone_in_simulation_mode(monkeypatch):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", True)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    store = conv.ConversationStateStore()
    assert store.is_authorized("U_ANY", source_type="room") is True
    assert store.is_authorized(None, source_type=None) is True


def test_gate_allows_one_to_one_oa_chat(monkeypatch):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    store = conv.ConversationStateStore()
    assert store.is_authorized("U_OP", source_type="user") is True
    # a 1:1 source without a userId cannot be keyed → denied
    assert store.is_authorized(None, source_type="user") is False


def test_gate_allows_only_the_configured_group(monkeypatch):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_OPERATOR_GROUP")
    store = conv.ConversationStateStore()
    assert store.is_authorized("U1", source_type="group", group_id="C_OPERATOR_GROUP") is True
    assert store.is_authorized("U1", source_type="group", group_id="C_OTHER_GROUP") is False


def test_gate_denies_unknown_room_and_missing_group_config(monkeypatch):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    store = conv.ConversationStateStore()
    assert store.is_authorized("U1", source_type="room", group_id=None) is False
    assert store.is_authorized("U1", source_type="group", group_id="C_X") is False


def test_gate_ignores_line_admin_user_id(monkeypatch):
    """
    Decision A: even when the sender IS the stored `LINE_ADMIN_USER_ID`, a
    non-1:1 / non-group source must still be denied — the value is never consulted.
    """
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_OP")
    store = conv.ConversationStateStore()
    assert store.is_authorized("U_OP", source_type="room") is False
