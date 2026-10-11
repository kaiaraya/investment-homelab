"""
Unit tests for the Liberator broker plugin account/portfolio extensions.

Part of the Pillar 2 rename/refactor (Pillar 2 = Account & Portfolio).
Covers the new `get_open_orders()` (canonical order normalization + open-only filter)
and `switch_account_type()` (single-account Cash guard) on LiberatorBrokerPlugin.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.brokers.liberator.plugin import liberator_plugin


@pytest.mark.asyncio
async def test_get_open_orders_normalizes_and_filters_open_only():
    raw = {
        "orders": [
            {"order_no": "1234567", "time": "10:01:02", "symbol": "ptt", "side": "buy",
             "price": 33.5, "volume": 1000, "matched": 200, "balance": 800, "status": "Open"},
            {"order_no": "9999999", "time": "09:55:00", "symbol": "PTT", "side": "SELL",
             "price": 34.0, "volume": 100, "matched": 100, "balance": 0, "status": "Matched"},
            {"order_no": "8888888", "time": "09:56:00", "symbol": "AOT", "side": "BUY",
             "price": 60.0, "volume": 100, "matched": 0, "balance": 100, "status": "Cancelled"},
        ]
    }
    with patch(
        "app.brokers.liberator.plugin.liberator_driver.scrape_portfolio",
        new=AsyncMock(return_value=raw),
    ):
        orders = await liberator_plugin.get_open_orders()

    assert len(orders) == 1
    o = orders[0]
    assert o["broker_order_no"] == "1234567"
    assert o["symbol"] == "PTT"
    assert o["side"] == "BUY"
    assert o["volume"] == 1000
    assert o["matched_volume"] == 200
    assert o["balance"] == 800
    assert o["price"] == 33.5
    assert o["status"] == "Open"


@pytest.mark.asyncio
async def test_get_open_orders_returns_empty_when_no_orders():
    with patch(
        "app.brokers.liberator.plugin.liberator_driver.scrape_portfolio",
        new=AsyncMock(return_value={"orders": []}),
    ):
        orders = await liberator_plugin.get_open_orders()
    assert orders == []


@pytest.mark.asyncio
async def test_get_open_orders_partial_fill_stays_open():
    raw = {"orders": [
        {"order_no": "5550001", "symbol": "DELTA", "side": "SELL",
         "price": 900.0, "volume": 500, "matched": 300, "balance": 200, "status": "Partial"},
    ]}
    with patch(
        "app.brokers.liberator.plugin.liberator_driver.scrape_portfolio",
        new=AsyncMock(return_value=raw),
    ):
        orders = await liberator_plugin.get_open_orders()
    assert len(orders) == 1
    assert orders[0]["balance"] == 200
    assert orders[0]["matched_volume"] == 300


@pytest.mark.asyncio
async def test_switch_account_type_single_account_guard():
    assert await liberator_plugin.switch_account_type("CASH") is True
    assert await liberator_plugin.switch_account_type("cash_balance") is True
    assert await liberator_plugin.switch_account_type("MARGIN") is False
    assert await liberator_plugin.switch_account_type("DERIVATIVES") is False
    assert await liberator_plugin.switch_account_type("TFEX") is False
