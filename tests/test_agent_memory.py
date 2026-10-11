import pytest
from app.ai.memory import DualStoreMemory
from app.db.init_db import init_db


@pytest.mark.asyncio
async def test_working_memory_operations():
    """Verify ephemeral working memory operations."""
    mem = DualStoreMemory()
    mem.set_working_key("active_regime", "PRE_MARKET_TEST")
    assert mem.get_working_key("active_regime") == "PRE_MARKET_TEST"

    mem.update_quote("BDMS", {"last_price": 19.90, "change": 0.20})
    quote = mem.get_quote("BDMS")
    assert quote is not None
    assert quote["last_price"] == 19.90
    assert "updated_at" in quote

    snapshot = mem.get_all_working_memory()
    assert "active_regime" in snapshot
    assert "BDMS" in snapshot["latest_quotes"]

    mem.clear_working_memory()
    assert mem.get_quote("BDMS") is None


@pytest.mark.asyncio
async def test_persistent_memory_audit_trail():
    """Verify SQLite persistent logging and retrieval of agent decisions."""
    await init_db()
    mem = DualStoreMemory()

    log_id = await mem.log_decision(
        agent_name="TestAgent",
        action_type="TEST_ACTION",
        regime="UNIT_TEST",
        thought="Testing persistent memory storage.",
        input_context={"param": 42},
        output_result={"success": True},
        is_success=True,
    )
    assert log_id > 0

    records = await mem.get_recent_audit_trail(agent_name="TestAgent", limit=5)
    assert len(records) > 0
    latest = records[0]
    assert latest["agent_name"] == "TestAgent"
    assert latest["action_type"] == "TEST_ACTION"
    assert latest["thought"] == "Testing persistent memory storage."
    assert latest["input_context"] == {"param": 42}
    assert latest["output_result"] == {"success": True}
