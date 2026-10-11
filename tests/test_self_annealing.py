import pytest
from app.services.self_annealing_engine import SelfAnnealingEngine
from app.db.init_db import init_db


@pytest.mark.asyncio
async def test_self_annealing_tier1_and_tier3_flow():
    """Verify 3-tier self-annealing flow on unknown step failure."""
    await init_db()
    engine = SelfAnnealingEngine()

    # Simulate an error on a dummy step
    dummy_error = TimeoutError("Timeout 5000ms waiting for locator('button.submit')")

    result = await engine.handle_execution_failure(
        workflow_name="test_order_submit",
        failed_step="button_submit_click",
        error=dummy_error,
        dom_snapshot="<button disabled class='submit-btn'>Submit</button>",
    )

    assert result is not None
    # Result must either be Tier 2 (if model configured) or Tier 3 (escalated)
    assert result.get("tier") in (2, 3)
    if result.get("tier") == 3:
        assert result.get("status") == "ESCALATED_TO_HUMAN"
    elif result.get("tier") == 2:
        assert result.get("action") == "RUNBOOK_ANNEALED"
