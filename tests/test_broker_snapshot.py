# -*- coding: utf-8 -*-
"""Unit tests for broker snapshot service and pre-market snapshot CLI (SNAP.1)."""
import json
import os
import sys
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.broker_snapshot import (
    BrokerSnapshotService,
    reconcile_kss_data,
    reconcile_liberator_data,
)
import scripts.pre_market_snapshot as cli_module


# --- Mock Data Fixtures ---

@pytest.fixture
def valid_kss_raw():
    return {
        "3024959": {
            "balance": {
                "accountNo": "3024959",
                "accountType": "CREDIT_BALANCE",
                "creditLimit": 1200000.0,
                "cashBalance": 354741.63,
                "lineAvailable": 354741.63,
                "pp": 709483.26,
                "ee": 354741.63,
                "equity": 354741.63,
                "purchasingPower": 709483.26,
                "creditBalance": True,
            },
            "portfolio": {
                "portfolioList": [
                    {
                        "symbol": "AEONTS",
                        "actualVolume": 600,
                        "currentVolume": 600,
                        "marketPrice": 0.0,  # caveat 3: market-price 0 flags prices_stale
                        "averagePrice": 0.0,
                    },
                    {
                        "symbol": "TU",
                        "actualVolume": 3100,
                        "currentVolume": 3100,
                        "marketPrice": 0.0,
                        "averagePrice": 0.0,
                    },
                ]
            },
            "orders": [],
        },
        "3024952": {
            "balance": {
                "accountNo": "3024952",
                "accountType": "CASH_ACCOUNT",
                "creditLimit": 500000.0,
                "cashBalance": 0.0,
                "lineAvailable": 0.0,
                "pp": 0.0,
                "ee": 0.0,
                "equity": 0.0,
                "purchasingPower": 0.0,
                "creditBalance": False,
            },
            "portfolio": {"portfolioList": []},
            "orders": [],
        },
    }


@pytest.fixture
def valid_liberator_raw():
    return {
        "ok": True,
        "profile": {
            "errorCode": 0,
            "result": {
                "accounts": [
                    {
                        "accountNo": "70559382",
                        "type": "CASH BALANCE",
                        "creditLimit": 500000.0,
                        "lineAvailable": 225877.48,
                        "cashBalance": 225877.48,
                        "withdrawAvailable": 225877.48,
                        "investorId": "7055938",
                        "marketVal": 0.0,
                        "unrealizedPL": 0.0,
                    }
                ]
            },
        },
        "portfolio": {
            "errorCode": 0,
            "result": {"list": []},
        },
        "orders": {
            "errorCode": 0,
            "result": {"list": []},
        },
        "market": {
            "errorCode": 0,
            "result": {
                "data": {"st": "OPEN", "roleGroup": "SET0300"}
            },
        },
    }


# --- KSS Reconciliation Tests ---

def test_reconcile_kss_data_valid(valid_kss_raw):
    ok, reason, payload = reconcile_kss_data(valid_kss_raw)
    assert ok is True
    assert reason == "PASS"
    assert payload["status"] == "OK"
    assert "3024959" in payload["accounts"]
    assert "3024952" in payload["accounts"]
    # prices_stale should be True because marketPrice == 0 with volume > 0
    assert payload["accounts"]["3024959"]["prices_stale"] is True
    assert payload["accounts"]["3024952"]["prices_stale"] is False


def test_reconcile_kss_data_open_orders_reconcile(valid_kss_raw):
    # Case: Open orders exist and lineAvailable <= cashBalance
    valid_kss_raw["3024959"]["orders"] = [
        {"orderNo": "101", "showOrderStatus": "Queuing", "symbol": "CPALL"}
    ]
    valid_kss_raw["3024959"]["balance"]["lineAvailable"] = 300000.0
    ok, reason, payload = reconcile_kss_data(valid_kss_raw)
    assert ok is True
    assert len(payload["accounts"]["3024959"]["open_orders"]) == 1


def test_reconcile_kss_data_line_mismatch_fails(valid_kss_raw):
    # Case: 0 open orders but lineAvailable != cashBalance
    valid_kss_raw["3024959"]["balance"]["lineAvailable"] = 300000.0
    ok, reason, payload = reconcile_kss_data(valid_kss_raw)
    assert ok is False
    assert "lineAvailable" in reason


def test_reconcile_kss_data_pp_ratio_fails(valid_kss_raw):
    # Case: purchasing power ratio is way off (e.g. 5.0 instead of ~2.0)
    valid_kss_raw["3024959"]["balance"]["pp"] = 1900000.0
    ok, reason, payload = reconcile_kss_data(valid_kss_raw)
    assert ok is False
    assert "pp/equity ratio" in reason


def test_reconcile_kss_data_endpoint_error_fails(valid_kss_raw):
    # Case: balance endpoint failed with HTTP 401 / session expired
    valid_kss_raw["3024959"]["balance"] = {"http_status": 401, "error": "HTTP_401"}
    ok, reason, payload = reconcile_kss_data(valid_kss_raw)
    assert ok is False
    assert "balance endpoint failed" in reason


# --- Liberator Reconciliation Tests ---

def test_reconcile_liberator_data_valid(valid_liberator_raw):
    ok, reason, payload = reconcile_liberator_data(valid_liberator_raw)
    assert ok is True
    assert reason == "PASS"
    assert payload["status"] == "OK"
    assert "70559382" in payload["accounts"]
    assert payload["market_status"]["st"] == "OPEN"


def test_reconcile_liberator_no_token():
    raw = {"ok": False, "error": "NO_API_TOKEN"}
    ok, reason, payload = reconcile_liberator_data(raw)
    assert ok is False
    assert "NO_API_TOKEN" in reason


def test_reconcile_liberator_error_code(valid_liberator_raw):
    valid_liberator_raw["profile"]["errorCode"] = 1002
    valid_liberator_raw["profile"]["errMsg"] = "Error AccessAuthen"
    ok, reason, payload = reconcile_liberator_data(valid_liberator_raw)
    assert ok is False
    assert "Error AccessAuthen" in reason


def test_reconcile_liberator_balance_mismatch(valid_liberator_raw):
    # Case: lineAvailable != cashBalance when 0 orders & 0 positions
    valid_liberator_raw["profile"]["result"]["accounts"][0]["lineAvailable"] = 100000.0
    ok, reason, payload = reconcile_liberator_data(valid_liberator_raw)
    assert ok is False
    assert "Liberator reconcile failed" in reason


# --- BrokerSnapshotService Tests ---

@pytest.mark.asyncio
async def test_create_snapshot_dry_run(valid_kss_raw, valid_liberator_raw):
    svc = BrokerSnapshotService()
    with patch.object(svc, "fetch_kss_raw", AsyncMock(return_value=valid_kss_raw)), \
         patch.object(svc, "fetch_liberator_raw", AsyncMock(return_value=valid_liberator_raw)):
        ok, snap, path = await svc.create_snapshot(brokers=["kss", "lib"], dry_run=True)
        assert ok is True
        assert path is None
        assert snap["status"] == "OK"
        assert "kss" in snap["brokers"]
        assert "liberator" in snap["brokers"]
        assert snap["market_status"]["st"] == "OPEN"


@pytest.mark.asyncio
async def test_create_snapshot_save_and_immutable(valid_kss_raw, valid_liberator_raw):
    svc = BrokerSnapshotService()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(svc, "fetch_kss_raw", AsyncMock(return_value=valid_kss_raw)), \
             patch.object(svc, "fetch_liberator_raw", AsyncMock(return_value=valid_liberator_raw)):
            ok, snap, path = await svc.create_snapshot(brokers=["kss", "lib"], dry_run=False, snapshot_dir=tmpdir)
            assert ok is True
            assert path is not None
            assert os.path.exists(path)

            # Check file content
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["status"] == "OK"

            # Refuse overwrite (immutability rule)
            ok2, snap2, path2 = await svc.create_snapshot(brokers=["kss", "lib"], dry_run=False, snapshot_dir=tmpdir)
            assert ok2 is False
            assert path2 is None
            assert snap2["status"] == "FAIL_CLOSED"
            assert any("already exists" in err for err in snap2.get("errors", []))


@pytest.mark.asyncio
async def test_create_snapshot_fail_closed_on_error(valid_kss_raw):
    svc = BrokerSnapshotService()
    with patch.object(svc, "fetch_kss_raw", AsyncMock(return_value=valid_kss_raw)), \
         patch.object(svc, "fetch_liberator_raw", AsyncMock(return_value={"ok": False, "error": "NO_API_TOKEN"})):
        ok, snap, path = await svc.create_snapshot(brokers=["kss", "lib"], dry_run=True)
        assert ok is False
        assert snap["status"] == "FAIL_CLOSED"
        assert any("Liberator" in err for err in snap.get("errors", []))


# --- CLI pre_market_snapshot CLI Tests ---

@pytest.mark.asyncio
async def test_cli_main_async_dry_run(valid_kss_raw, valid_liberator_raw):
    # Use mock args directly
    mock_args = MagicMock(all=True, broker=None, dry_run=True, snapshot_dir="data/snapshots")

    with patch.object(cli_module.broker_snapshot_service, "fetch_kss_raw", AsyncMock(return_value=valid_kss_raw)), \
         patch.object(cli_module.broker_snapshot_service, "fetch_liberator_raw", AsyncMock(return_value=valid_liberator_raw)):
        code = await cli_module.main_async(mock_args)
        assert code == 0


@pytest.mark.asyncio
async def test_cli_main_async_fail_closed(valid_kss_raw):
    mock_args = MagicMock(all=True, broker=None, dry_run=True, snapshot_dir="data/snapshots")

    with patch.object(cli_module.broker_snapshot_service, "fetch_kss_raw", AsyncMock(return_value=valid_kss_raw)), \
         patch.object(cli_module.broker_snapshot_service, "fetch_liberator_raw", AsyncMock(return_value={"ok": False, "error": "NO_API_TOKEN"})):
        code = await cli_module.main_async(mock_args)
        assert code == 1
