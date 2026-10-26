import pytest
import os
from unittest.mock import AsyncMock, patch

from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver
from app.core.config import settings


@pytest.mark.asyncio
async def test_sbl_borrow_snippet_files_exist():
    """Verify that the SBL borrow and return JS snippet files exist and are non-empty."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    borrow_js = os.path.join(root, "data", "bookmarklets", "sbl_borrow.js")
    return_js = os.path.join(root, "data", "bookmarklets", "sbl_return.js")
    assert os.path.exists(borrow_js)
    assert os.path.exists(return_js)
    with open(borrow_js, "r", encoding="utf-8") as f:
        content = f.read()
        assert "#MainCenter_lbBorrow" in content
        assert "BLOCKED_BY_XD_XR" in content
    with open(return_js, "r", encoding="utf-8") as f:
        content = f.read()
        assert "RadSave" in content
        assert "Return.aspx" in content


@pytest.mark.asyncio
async def test_execute_sbl_borrow_xd_hard_block():
    """Verify that execute_sbl_borrow refuses symbols flagged with XD/XR in cache."""
    mock_cache = {
        "xd_xr_inventory": [
            {"symbol": "PTT", "book_date": "28/10/2026", "type": "XD"}
        ]
    }
    with patch.object(krungsri_sbl_driver, "get_cached_data", return_value=mock_cache):
        res = await krungsri_sbl_driver.execute_sbl_borrow("PTT", 100)
    assert res["success"] is False
    assert res["status"] == "BLOCKED_BY_XD_XR"
    assert "XD" in res["error"]


@pytest.mark.asyncio
async def test_execute_sbl_borrow_dry_run_js_first():
    """Verify that execute_sbl_borrow delegates to js_runner with dry_run=True when DRY_RUN_MODE is active."""
    mock_cdp_return = {
        "success": True,
        "data": {
            "success": True,
            "status": "DRY_RUN_ARMED",
            "dry_run": True,
            "symbol": "TU",
            "volume": 100,
            "purchasing_power": 669627.64,
            "message": "[DRY-RUN] SBL borrow form filled for TU 100 shares. PostBack held."
        }
    }
    with patch.object(settings, "DRY_RUN_MODE", True):
        with patch.object(krungsri_sbl_driver, "get_cached_data", return_value={"xd_xr_inventory": []}):
            with patch("scripts.broker_cdp.js_runner.run_snippet", new_callable=AsyncMock, return_value=mock_cdp_return) as m_runner:
                res = await krungsri_sbl_driver.execute_sbl_borrow("TU", 100)
    assert res["success"] is True
    assert res["status"] == "DRY_RUN_ARMED"
    assert res["source"] == "sbl_borrow_js"
    assert res["dry_run"] is True
    m_runner.assert_awaited_once()


@pytest.mark.asyncio
async def test_return_sbl_shares_dry_run_js_first():
    """Verify that return_sbl_shares delegates to sbl_return.js via js_runner."""
    mock_cdp_return = {
        "success": True,
        "data": {
            "success": True,
            "status": "DRY_RUN_ARMED",
            "dry_run": True,
            "contract": {"ref_no": "B494354", "symbol": "TU", "quantity": 3100},
            "return_qty": 100,
            "message": "[DRY-RUN] Contract B494354 (TU) found. Return held."
        }
    }
    with patch.object(settings, "DRY_RUN_MODE", True):
        with patch("scripts.broker_cdp.js_runner.run_snippet", new_callable=AsyncMock, return_value=mock_cdp_return) as m_runner:
            res = await krungsri_sbl_driver.return_sbl_shares("B494354", 100, symbol="TU")
    assert res["success"] is True
    assert res["status"] == "DRY_RUN_ARMED"
    assert res["source"] == "sbl_return_js"
    assert res["dry_run"] is True
    m_runner.assert_awaited_once()
