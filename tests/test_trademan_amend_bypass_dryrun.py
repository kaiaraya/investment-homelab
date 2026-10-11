"""
KSS-RCA-017 regression: ``execute_order`` must honour ``bypass_dry_run``.

The LIVE amend path (``trademan_driver.modify_order_price``) runs
``cancel_order(bypass_dry_run=True)`` and then ``execute_order(...)``. Before the
fix ``execute_order`` had no ``bypass_dry_run`` parameter (it was swallowed by
``**kwargs``) and its ``DRY_RUN_MODE`` guard always returned a fabricated
``SIM-<epoch>`` "success". The amend therefore cancelled the real order but never
re-submitted it -- the position was silently lost -- while still reporting
``AMENDED`` (Anti-Mock violation).

These tests pin the guard for BOTH directions with no live browser
(``page is None``), which is exactly the fail-closed branch of ``execute_order``.
"""
import pytest
from unittest.mock import AsyncMock, PropertyMock, patch

from app.browser.trademan_driver import trademan_driver
from app.services.validator import validator


def _no_page():
    """Force the driver into the 'no browser session' fail-closed branch."""
    return patch.object(
        type(trademan_driver), "page", new_callable=PropertyMock, return_value=None
    )


@pytest.mark.asyncio
async def test_execute_order_dry_run_without_bypass_simulates(monkeypatch):
    """DRY_RUN_MODE + bypass_dry_run=False -> simulated id (unchanged behaviour)."""
    monkeypatch.setattr("app.browser.trademan_driver.settings.DRY_RUN_MODE", True)
    validator.clear_idempotency_cache()

    with _no_page(), patch.object(trademan_driver, "_log_event", new=AsyncMock()):
        res = await trademan_driver.execute_order("PTT", "BUY", 1000, 34.00)

    assert res["success"] is True
    assert res["status"] == "SIMULATED_SUCCESS"
    assert res["broker_order_no"].startswith("SIM-")


@pytest.mark.asyncio
async def test_execute_order_bypass_dry_run_never_fabricates_sim_id(monkeypatch):
    """KSS-RCA-017: bypass_dry_run=True must fail closed, never fake a SIM- success.

    A fabricated id here means the amend cancels the broker order and reports
    success without re-submitting it (the original order is lost).
    """
    monkeypatch.setattr("app.browser.trademan_driver.settings.DRY_RUN_MODE", True)
    validator.clear_idempotency_cache()

    with _no_page(), patch.object(trademan_driver, "_log_event", new=AsyncMock()):
        res = await trademan_driver.execute_order(
            "PTT", "BUY", 1000, 34.00, bypass_dry_run=True
        )

    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert "SIM-" not in (res.get("broker_order_no") or "")
    assert "browser session" in res["error"].lower()
