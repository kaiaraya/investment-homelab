"""
Unit tests for the Pillar 2 Order Ledger (`current_orders`).

Part of TASK-pillar2-order-ledger: lists ALL orders sent to the broker with a
Matched / Partially-Matched / Unmatched / Cancelled / Rejected classification,
for Krungsri TradeMan and Liberator (Click2Win not yet implemented).
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.mcp.pillars.pillar2_portfolio import (
    current_orders,
    _classify_order_category,
)


def test_classify_order_category_matrix():
    # Fully matched
    assert _classify_order_category(1000, 1000, 0, "Matched") == "MATCHED"
    assert _classify_order_category(500, 500, 0, "M") == "MATCHED"
    # Partial fill stays open
    assert _classify_order_category(1000, 300, 700, "Partial") == "PARTIALLY_MATCHED"
    # Open / queued
    assert _classify_order_category(1000, 0, 1000, "Open") == "UNMATCHED"
    assert _classify_order_category(1000, 0, 1000, "Queuing(SX)") == "UNMATCHED"
    assert _classify_order_category(0, 0, 0, "O") == "UNMATCHED"
    # Cancelled / rejected
    assert _classify_order_category(1000, 0, 1000, "Cancelled(CX)") == "CANCELLED"
    assert _classify_order_category(1000, 0, 0, "C") == "CANCELLED"
    assert _classify_order_category(1000, 0, 0, "Rejected") == "REJECTED"
    # Unknown
    assert _classify_order_category(0, 0, 0, "") == "UNKNOWN"


@pytest.mark.asyncio
async def test_current_orders_liberator_counts_matched_and_unmatched():
    rows = [
        {"broker_order_no": "1", "symbol": "BCH", "side": "SELL", "volume": 100,
         "matched_volume": 100, "balance": 0, "price": 11.2, "status": "Matched"},
        {"broker_order_no": "2", "symbol": "BCP", "side": "BUY", "volume": 200,
         "matched_volume": 50, "balance": 150, "price": 40.0, "status": "Partial"},
        {"broker_order_no": "3", "symbol": "IVL", "side": "BUY", "volume": 100,
         "matched_volume": 0, "balance": 100, "price": 30.0, "status": "Open"},
        {"broker_order_no": "4", "symbol": "RCL", "side": "SELL", "volume": 100,
         "matched_volume": 0, "balance": 100, "price": 15.0, "status": "Cancelled"},
    ]
    with patch("app.brokers.liberator.plugin.liberator_plugin.get_all_orders",
               new=AsyncMock(return_value=rows)):
        res = await current_orders(platform="LIBERATOR")

    assert res["success"] is True
    assert res["platform"] == "LIBERATOR"
    assert res["account_type"] == "CASH"
    assert res["total"] == 4
    assert res["matched_count"] == 1
    assert res["partially_matched_count"] == 1
    assert res["unmatched_count"] == 1
    assert res["cancelled_count"] == 1
    cats = {o["broker_order_no"]: o["status_category"] for o in res["orders"]}
    assert cats["1"] == "MATCHED"
    assert cats["2"] == "PARTIALLY_MATCHED"
    assert cats["3"] == "UNMATCHED"
    assert cats["4"] == "CANCELLED"


@pytest.mark.asyncio
async def test_current_orders_include_closed_false_filters_terminal():
    rows = [
        {"broker_order_no": "1", "symbol": "PTT", "side": "BUY", "volume": 100,
         "matched_volume": 100, "balance": 0, "price": 34.0, "status": "Matched"},
        {"broker_order_no": "2", "symbol": "AOT", "side": "BUY", "volume": 100,
         "matched_volume": 0, "balance": 100, "price": 60.0, "status": "Cancelled"},
    ]
    with patch("app.brokers.liberator.plugin.liberator_plugin.get_all_orders",
               new=AsyncMock(return_value=rows)):
        res = await current_orders(platform="LIBERATOR", include_closed=False)

    assert res["total"] == 1
    assert res["orders"][0]["broker_order_no"] == "1"


@pytest.mark.asyncio
async def test_current_orders_krungsri_routes_to_trademan_driver():
    rows = [
        {"broker_order_no": "11012916", "symbol": "AAV", "side": "SELL", "volume": 57000,
         "matched_volume": 0, "balance": 57000, "price": 0.84, "status": "O"},
        {"broker_order_no": "11011353", "symbol": "SAWAD", "side": "SELL", "volume": 2200,
         "matched_volume": 2200, "balance": 0, "price": 22.5, "status": "M"},
    ]
    with patch("app.mcp.pillars.pillar2_portfolio.trademan_driver.scrape_all_orders",
               new=AsyncMock(return_value=rows)):
        res = await current_orders(platform="KRUNGSRI", account_type="MARGIN")

    assert res["platform"] == "KRUNGSRI"
    assert res["account_type"] == "MARGIN"
    assert res["matched_count"] == 1
    assert res["unmatched_count"] == 1


@pytest.mark.asyncio
async def test_current_orders_click2win_not_implemented_notice():
    res = await current_orders(platform="CLICK2WIN")
    assert res["success"] is False
    assert res["platform"] == "CLICK2WIN"
