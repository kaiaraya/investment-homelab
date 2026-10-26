import pytest
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import app.brokers.krungsri.sbl_realtime_driver as sbl_mod
from app.brokers.krungsri.sbl_realtime_driver import (
    KrungsriSBLRealtimeDriver,
    krungsri_sbl_driver,
)
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


# ───────────────────────────────────────────────────────────────────────────── #
# 2.11b — check_symbol_risk must FAIL CLOSED on an empty or stale SBL cache
# ───────────────────────────────────────────────────────────────────────────── #
def _driver_with(cache):
    """Fresh driver instance whose cache is exactly ``cache`` (no disk load)."""
    drv = KrungsriSBLRealtimeDriver.__new__(KrungsriSBLRealtimeDriver)
    drv._lock = asyncio.Lock()
    drv._cached_data = cache
    drv._cache_stamp_missing = False
    return drv


def _fresh(**pools):
    data = {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "set50_inventory": pools.get("set50", []),
        "set100_inventory": pools.get("set100", []),
        "newsec_inventory": pools.get("newsec", []),
        "xd_xr_inventory": pools.get("xd", []),
    }
    return data


def test_cache_missing_blocks_symbol():
    """No cache at all → is_blocked True (CACHE_MISS), not a silent pass."""
    drv = _driver_with({})
    with patch.object(drv, "get_cached_data", return_value={}):
        risk = drv.check_symbol_risk("PTT")
    assert risk["is_blocked"] is True
    assert risk["verdict"] == "CACHE_MISS"
    assert risk["available_qty"] == 0
    assert "/sbl sync" in risk["reason"]
    assert risk["cache_state"] == "CACHE_MISS"


def test_cache_stale_blocks_symbol():
    """Cache older than the staleness window → is_blocked True (CACHE_STALE)."""
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    cache = _fresh(set50=[{"symbol": "PTT", "available_qty": 5000, "borrow_fee_pct": 3.5}])
    cache["timestamp"] = old
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache):
        risk = drv.check_symbol_risk("PTT")
        status = drv.cache_status()
    assert risk["is_blocked"] is True
    assert risk["verdict"] == "CACHE_STALE"
    assert risk["available_qty"] == 0
    assert status["state"] == "CACHE_STALE"
    assert status["age_seconds"] > status["staleness_seconds"]


def test_fresh_cache_with_inventory_allows_borrow():
    """Only a fresh snapshot proving available_qty > 0 yields is_blocked False."""
    cache = _fresh(set50=[{"symbol": "PTT", "available_qty": 12345,
                           "borrow_fee_pct": 3.5, "initial_margin_pct": 50.0}])
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache):
        risk = drv.check_symbol_risk("ptt")
    assert risk["is_blocked"] is False
    assert risk["verdict"] == "BORROW_ALLOWED"
    assert risk["available_qty"] == 12345
    assert risk["symbol"] == "PTT"


def test_fresh_cache_xd_marker_blocks_borrow():
    """XD marker on a fresh cache still hard-blocks even with inventory > 0."""
    cache = _fresh(
        set50=[{"symbol": "PTT", "available_qty": 99999, "borrow_fee_pct": 3.5}],
        xd=[{"symbol": "PTT", "book_date": "28/10/2026", "type": "XD"}],
    )
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache):
        risk = drv.check_symbol_risk("PTT")
    assert risk["is_blocked"] is True
    assert risk["verdict"] == "HARD_BLOCKED_XD_XR"
    assert "ชดเชยปันผล" in risk["reason"]


def test_fresh_cache_symbol_absent_blocks_borrow():
    """Fresh cache without the symbol no longer returns is_blocked False."""
    cache = _fresh(set50=[{"symbol": "CPALL", "available_qty": 100, "borrow_fee_pct": 3.5}])
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache):
        risk = drv.check_symbol_risk("ZZZZ")
    assert risk["is_blocked"] is True
    assert risk["verdict"] == "NOT_IN_POOL"
    assert risk["legacy_verdict"] == "UNVERIFIED_INVENTORY"
    assert risk["available_qty"] == 0


def test_fresh_cache_zero_inventory_is_out_of_stock():
    cache = _fresh(set100=[{"symbol": "DELTA", "available_qty": 0, "borrow_fee_pct": 3.5}])
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache):
        risk = drv.check_symbol_risk("DELTA")
    assert risk["is_blocked"] is True
    assert risk["verdict"] == "OUT_OF_STOCK"


def test_disk_cache_without_timestamp_is_treated_as_stale(tmp_path, monkeypatch):
    """A persisted cache carrying no timestamp cannot be trusted → stale."""
    cache_file = tmp_path / "krungsri_sbl_realtime.json"
    cache_file.write_text(json.dumps({
        "success": True,
        "set50_inventory": [{"symbol": "PTT", "available_qty": 5000, "borrow_fee_pct": 3.5}],
        "xd_xr_inventory": [],
    }), encoding="utf-8")
    monkeypatch.setattr(sbl_mod, "CACHE_FILE", str(cache_file))

    drv = KrungsriSBLRealtimeDriver()
    status = drv.cache_status()
    risk = drv.check_symbol_risk("PTT")
    assert status["state"] == "CACHE_STALE"
    assert risk["is_blocked"] is True
    assert risk["verdict"] == "CACHE_STALE"


def test_save_cache_to_disk_stamps_timestamp(tmp_path, monkeypatch):
    """Every snapshot written to disk carries a timestamp, and reloads as fresh."""
    cache_file = tmp_path / "krungsri_sbl_realtime.json"
    monkeypatch.setattr(sbl_mod, "CACHE_FILE", str(cache_file))

    drv = KrungsriSBLRealtimeDriver()
    drv._save_cache_to_disk({
        "success": True,
        "set50_inventory": [{"symbol": "PTT", "available_qty": 10, "borrow_fee_pct": 3.5}],
        "xd_xr_inventory": [],
    })
    stored = json.loads(cache_file.read_text(encoding="utf-8"))
    assert stored.get("timestamp")

    reloaded = KrungsriSBLRealtimeDriver()
    assert reloaded.cache_status()["state"] == "CACHE_FRESH"
    assert reloaded.check_symbol_risk("PTT")["verdict"] == "BORROW_ALLOWED"


@pytest.mark.asyncio
async def test_pool_read_path_returns_zero_without_raising_on_empty_cache():
    """/sbl pool path must render 0 instead of raising when there is no cache."""
    drv = _driver_with({})
    with patch.object(drv, "get_cached_data", return_value={}), \
         patch.object(settings, "SESSION_STATE_PATH", "/nonexistent/session_state.json"):
        avail = await drv.scrape_sbl_available_inventory("PTT")
    assert avail == 0


@pytest.mark.asyncio
async def test_pool_read_path_returns_zero_on_stale_cache_without_scraping():
    """Stale cache → 0 and no browser scrape (keeps the SSO session intact)."""
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    cache = _fresh(set50=[{"symbol": "PTT", "available_qty": 5000, "borrow_fee_pct": 3.5}])
    cache["timestamp"] = old
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache), \
         patch.object(drv, "scrape_full_pool", new_callable=AsyncMock) as m_scrape:
        avail = await drv.scrape_sbl_available_inventory("PTT")
    assert avail == 0
    m_scrape.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_sbl_borrow_blocked_by_stale_cache():
    """The borrow flow itself refuses to start on a stale snapshot."""
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    cache = _fresh(set50=[{"symbol": "PTT", "available_qty": 5000, "borrow_fee_pct": 3.5}])
    cache["timestamp"] = old
    drv = _driver_with(cache)
    with patch.object(drv, "get_cached_data", return_value=cache):
        res = await drv.execute_sbl_borrow("PTT", 100)
    assert res["success"] is False
    assert res["status"] == "BLOCKED_BY_STALE_CACHE"
