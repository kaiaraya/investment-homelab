"""
Test Suite: Next-Gen 6-Pillars Modular MCP Gateway for Investment Homelab.
Validates:
1. FastAPI Server Health & Static Mounts
2. Pillar 1: Session Sentinel (Unified Health, Login, 2FA OTP, Logout)
3. Pillar 2: Account & Portfolio (Accounts, Balances, Holdings, Open Orders)
4. Pillar 3: Trade Execution (Pre-trade Risk Guardrails, Sandbox Execution, Cancel, Modify)
5. Pillar 4: SBL Intelligence (Inventory, Borrow, Return, Corporate Actions)
6. Pillar 6: Tactical Strategy Center (Passive Price Negotiation, EOD Order Cleanup, List Strategies)
7. End-to-End JSON-RPC over MCP SSE Protocol Verification
"""

import os
import json
import time
import socket
import pytest
import asyncio
import threading
import urllib.request
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from starlette.testclient import TestClient

from app.main import app
from app.mcp.server import mcp, get_modular_sse_app
from app.mcp.pillars.overview import mcp_get_6pillars_overview
from app.mcp.pillars.pillar1_session import (
    session_get_health,
    session_login_broker,
    session_submit_otp,
    session_logout_all
)
from app.mcp.pillars.pillar3_trade import (
    trade_place_order,
    trade_cancel_order,
    trade_modify_price
)
from app.mcp.pillars.pillar4_sbl import (
    sbl_get_inventory,
    sbl_borrow_stock,
    sbl_return_stock,
    sbl_check_corporate_actions
)
from app.mcp.pillars.pillar2_portfolio import (
    portfolio_list_accounts,
    switch_account,
    portfolio_get_balances,
    portfolio_holdings,
    current_open_orders,
    portfolio_sync_db
)
from app.schemas.account import (
    AccountType,
    AccountCapability,
    account_context,
    account_guardrail
)
from app.mcp.pillars.pillar6_strategy import (
    strategy_negotiate_unmatched_orders,
    strategy_eod_order_cleanup,
    strategy_list_active
)


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Server Core Health & Static Mounts
# ==============================================================================

def test_main_health_and_screenshots_endpoint(client):
    """Verifies FastAPI health check and static screenshots directory."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy"}

    res_static = client.get("/screenshots/")
    assert res_static.status_code in [200, 404]


@pytest.mark.asyncio
async def test_pillar_architecture_overview_discovery():
    """Verifies that mcp_get_6pillars_overview returns complete metadata for AI agents."""
    overview = await mcp_get_6pillars_overview()
    assert "system" in overview
    assert "registered_brokers" in overview
    assert len(overview["registered_brokers"]) >= 4
    broker_ids = [b["id"] for b in overview["registered_brokers"]]
    assert "krungsri" in broker_ids
    assert "click2win" in broker_ids
    assert "settrade_openapi" in broker_ids
    assert "liberator" in broker_ids

    assert "six_pillars" in overview
    assert len(overview["six_pillars"]) == 5
    assert "pillar1_session" in overview["six_pillars"]
    assert "pillar2_portfolio" in overview["six_pillars"]
    assert "pillar3_trade" in overview["six_pillars"]
    assert "pillar4_sbl" in overview["six_pillars"]
    assert "pillar6_strategy" in overview["six_pillars"]
    assert "guardrails" in overview


# ==============================================================================
# 2. Pillar 1: Session Sentinel
# ==============================================================================

@pytest.mark.asyncio
async def test_pillar1_session_sentinel():
    """Verifies Pillar 1 session health, login flows, OTP submission, and logout."""
    # 1. Health check
    health = await session_get_health()
    assert "status" in health
    assert "krungsri_trademan" in health
    assert "settrade" in health

    # 2. Click2Win login
    with patch("app.browser.click2win_auth_driver.click2win_auth_driver.login", new_callable=AsyncMock) as m_c2w:
        m_c2w.return_value = MagicMock(success=True, message="Click2Win authenticated")
        c2w_res = await session_login_broker("CLICK2WIN")
        assert c2w_res["platform"] == "CLICK2WIN"
        assert c2w_res["success"] is True

    # 3. Krungsri login
    with patch("app.browser.auth_driver.auth_driver.login", new_callable=AsyncMock) as m_kss:
        m_kss.return_value = MagicMock(success=False, message="Awaiting 2FA OTP", otp_ref="REF123")
        kss_res = await session_login_broker("KRUNGSRI")
        assert kss_res["platform"] == "TRADEMAN"
        assert kss_res["otp_ref"] == "REF123"

    # 4. OTP submission (invalid and valid)
    bad_otp = await session_submit_otp("123")
    assert bad_otp["success"] is False
    assert "Must be 6 digits" in bad_otp["message"]

    good_otp = await session_submit_otp("123456")
    assert good_otp["success"] is True

    # 5. Logout all
    with patch("app.browser.auth_driver.auth_driver.close", new_callable=AsyncMock), \
         patch("app.browser.click2win_auth_driver.click2win_auth_driver.close", new_callable=AsyncMock):
        logout_res = await session_logout_all()
        assert logout_res["success"] is True
# ==============================================================================
# 4. Pillar 3: Trade Execution
# ==============================================================================

@pytest.mark.asyncio
async def test_pillar3_trade_execution():
    """Verifies Pillar 3 pre-trade risk validation and order actions."""
    # 1. Pre-trade guardrail: Non-board lot volume should be rejected
    invalid_vol = await trade_place_order(
        symbol="PTT",
        side="BUY",
        volume=55,  # Invalid: not multiple of 100
        price=34.0,
        platform="CLICK2WIN"
    )
    assert invalid_vol["success"] is False
    assert invalid_vol["error_type"] == "PRE_TRADE_GUARDRAIL_REJECTION"

    # 2. Pre-trade guardrail: Negative or zero price should be rejected
    invalid_price = await trade_place_order(
        symbol="PTT",
        side="BUY",
        volume=100,
        price=0.0,
        platform="CLICK2WIN"
    )
    assert invalid_price["success"] is False
    assert invalid_price["error_type"] == "PRE_TRADE_GUARDRAIL_REJECTION"

    # 3. Successful Click2Win order dispatch via Browser fallback
    with patch("app.mcp.pillars.pillar3_trade._get_settrade_investor", return_value=None), \
         patch("app.browser.click2win_driver.click2win_driver.execute_order", new_callable=AsyncMock) as m_place:
        m_place.return_value = {"success": True, "order_no": "ORD-101", "status": "QUEUING"}
        res = await trade_place_order(
            symbol="PTT",
            side="BUY",
            volume=100,
            price=34.0,
            platform="CLICK2WIN"
        )
        assert res["success"] is True
        assert res["order_no"] == "ORD-101"

    # 4. Cancel order
    with patch("app.browser.click2win_driver.click2win_driver.cancel_order", new_callable=AsyncMock) as m_cancel:
        m_cancel.return_value = {"success": True, "order_no": "ORD-101", "status": "CANCELLED"}
        c_res = await trade_cancel_order(order_no="ORD-101", platform="CLICK2WIN", symbol="PTT")
        assert c_res["success"] is True

    # 5. Modify order price
    with patch("app.browser.click2win_driver.click2win_driver.modify_order_price", new_callable=AsyncMock) as m_mod:
        m_mod.return_value = {"success": True, "order_no": "ORD-102", "new_price": 34.50}
        m_res = await trade_modify_price(order_no="ORD-101", new_price=34.50, platform="CLICK2WIN", symbol="PTT")
        assert m_res["success"] is True


# ==============================================================================
# 5. Pillar 4: SBL Intelligence
# ==============================================================================

@pytest.mark.asyncio
async def test_pillar4_sbl_intelligence():
    """Verifies Pillar 4 inventory inquiry, dry-run borrowing/returning, and corporate action checks."""
    # 1. SBL pool inventory
    with patch("app.browser.trademan_driver.trademan_driver.scrape_sbl_inventory", new_callable=AsyncMock) as m_pool:
        m_pool.return_value = {"inventory": [{"symbol": "CPALL", "available_vol": 50000, "rate": 4.5}]}
        inv = await sbl_get_inventory(symbols=["CPALL"])
        assert inv["success"] is True
        assert inv["items_count"] == 1

    # 2. SBL borrow stock - Cash account rejection guardrail
    rej_borrow = await sbl_borrow_stock(symbol="CPALL", volume=1000, dry_run=True, account_type="CASH")
    assert rej_borrow["success"] is False
    assert rej_borrow["error_type"] == "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION"

    # SBL borrow stock on MARGIN account (accepted)
    with patch("app.browser.trademan_driver.trademan_driver.execute_sbl_borrow", new_callable=AsyncMock) as m_borrow:
        m_borrow.return_value = {"success": True, "status": "SIMULATED_BORROW_ACCEPTED"}
        borrow_res = await sbl_borrow_stock(symbol="CPALL", volume=1000, dry_run=True, account_type="MARGIN")
        assert borrow_res["success"] is True
        assert borrow_res["dry_run"] is True
        assert borrow_res["account_type"] == "MARGIN"

    # 3. SBL return stock - Cash account rejection guardrail
    rej_return = await sbl_return_stock(symbol="CPALL", volume=1000, dry_run=True, account_type="CASH")
    assert rej_return["success"] is False
    assert rej_return["error_type"] == "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION"

    # SBL return stock on MARGIN account (accepted)
    with patch("app.browser.trademan_driver.trademan_driver.return_sbl_shares", new_callable=AsyncMock) as m_return:
        m_return.return_value = {"success": True, "status": "SIMULATED_RETURN_ACCEPTED"}
        return_res = await sbl_return_stock(symbol="CPALL", volume=1000, dry_run=True, account_type="MARGIN")
        assert return_res["success"] is True
        assert return_res["account_type"] == "MARGIN"

    # 4. Corporate Actions audit
    ca_res = await sbl_check_corporate_actions(symbol="CPALL")
    assert ca_res["success"] is True
    assert "risk_evaluation" in ca_res


# ==============================================================================
# 6. Pillar 2: Account & Portfolio
# ==============================================================================

@pytest.mark.asyncio
async def test_pillar2_portfolio_risk():
    """Verifies Pillar 2 balances, holdings, open orders, and TP/SL risk audit."""
    # 1. Balances check for Click2Win and Krungsri
    with patch("app.browser.click2win_driver.click2win_driver.scrape_accounts_summary", new_callable=AsyncMock) as m_acc:
        m_acc.return_value = {"accounts": [{"account_no": "999001-E", "line_available": 5000000.0}]}
        bal_c2w = await portfolio_get_balances(platform="CLICK2WIN")
        assert bal_c2w["platform"] == "CLICK2WIN"

    with patch("app.browser.trademan_driver.trademan_driver.scrape_account_summary", new_callable=AsyncMock) as m_kss:
        m_kss.return_value = {"excess_equity": 100000.0, "line_available": 150000.0}
        bal_kss = await portfolio_get_balances(platform="KRUNGSRI")
        assert bal_kss["platform"] == "KRUNGSRI"

    # 2. Holdings check
    with patch("app.browser.click2win_driver.click2win_driver.scrape_portfolio", new_callable=AsyncMock) as m_port:
        m_port.return_value = [{"symbol": "PTT", "volume": 500, "avg_cost": 34.0, "unrealized_pl": 250.0}]
        holdings = await portfolio_holdings(platform="CLICK2WIN")
        assert holdings["count"] == 1
        assert holdings["holdings"][0]["symbol"] == "PTT"

    # 3. Open orders check
    with patch("app.browser.click2win_driver.click2win_driver.scrape_unmatched_orders", new_callable=AsyncMock) as m_unmatch:
        m_unmatch.return_value = [{"order_no": "ORD-1", "symbol": "PTT", "status": "Queuing(SX)", "volume": 100, "price": 34.0}]
        orders = await current_open_orders(platform="CLICK2WIN")
        assert orders["unmatched_count"] == 1

    # 4. Portfolio DB sync
    sync_res = await portfolio_sync_db()
    assert sync_res["success"] is True

    # 5. Accounts directory check (all accounts, live vs simulation, markdown table)
    acc_res = await portfolio_list_accounts()
    assert acc_res["success"] is True
    assert acc_res["total_accounts"] in [6, 7]
    assert "markdown_table" in acc_res
    assert "เงินจริง" in acc_res["markdown_table"]
    assert "เงินเสมือน" in acc_res["markdown_table"]
    assert any(a["environment"] == "LIVE" for a in acc_res["accounts"])
    assert any(a["environment"] == "SIMULATION" for a in acc_res["accounts"])

    # Filtered by Krungsri
    kss_acc_res = await portfolio_list_accounts(platform="KRUNGSRI")
    assert kss_acc_res["success"] is True
    assert kss_acc_res["total_accounts"] == 2
    assert all(a["platform"] == "KRUNGSRI" for a in kss_acc_res["accounts"])
    assert all(a["environment"] == "LIVE" for a in kss_acc_res["accounts"])


@pytest.mark.asyncio
async def test_pillar2_kss_balances_bind_only_to_scraped_account():
    """CLI-RCA-011 (P2a): scraped figures attach ONLY to the account whose number was read.

    (a) the dropdown read the MARGIN account -> MARGIN carries the values and CASH is all-None.
    (c) the driver key ``cash_balance`` is really Line Available (selector order), so no
        account may ever expose a ``cash_balance`` figure.
    """
    from app.core.config import settings

    margin_no = settings.TRADEMAN_ACCOUNT_NO_MARGIN or "3024959"
    with patch("app.browser.trademan_driver.trademan_driver.scrape_account_summary", new_callable=AsyncMock) as m_sum:
        m_sum.return_value = {
            "account_no": margin_no,
            "cash_balance": 250_000.0,      # really Line Available (CLI-RCA-011)
            "excess_equity": 900_000.0,
            "authenticated": True,
        }
        res = await portfolio_get_balances(platform="KRUNGSRI")

    by_type = {a["account_type"]: a for a in res["accounts"]}
    assert res["scraped_account_no"] == margin_no
    margin, cash = by_type["MARGIN"], by_type["CASH"]
    assert margin["values_bound"] is True
    assert cash["values_bound"] is False
    # (a) values live ONLY under MARGIN
    assert margin["line_available"] == 250_000.0
    assert margin["excess_equity"] == 900_000.0
    assert cash["line_available"] is None and cash["excess_equity"] is None
    # (c) driver ``cash_balance`` is Line Available -> never surfaced as a cash balance
    assert all(a["cash_balance"] is None for a in res["accounts"])


@pytest.mark.asyncio
async def test_pillar2_kss_balances_unbound_when_account_no_missing():
    """(b) an unreadable/absent account number binds NONE of the values (Anti-Mock)."""
    with patch("app.browser.trademan_driver.trademan_driver.scrape_account_summary", new_callable=AsyncMock) as m_sum:
        m_sum.return_value = {          # no ``account_no`` -> nothing may be bound
            "cash_balance": 250_000.0,
            "excess_equity": 900_000.0,
            "authenticated": True,
        }
        res = await portfolio_get_balances(platform="KRUNGSRI")

    assert res["scraped_account_no"] is None
    assert len(res["accounts"]) == 2
    for acc in res["accounts"]:
        assert acc["values_bound"] is False
        assert acc["line_available"] is None
        assert acc["cash_balance"] is None
        assert acc["excess_equity"] is None


# ==============================================================================
# 7. Pillar 6: Tactical Strategy Center
# ==============================================================================

@pytest.mark.asyncio
async def test_pillar6_tactical_strategy():
    """Verifies Pillar 6 strategy listings, price negotiation, and EOD order cleanup."""
    # 1. Strategy list active
    strat_list = await strategy_list_active()
    assert "strategies" in strat_list
    assert len(strat_list["strategies"]) >= 2

    # 2. Negotiate unmatched orders (PASSIVE_LURE tactic)
    with patch("app.mcp.pillars.pillar6_strategy.current_open_orders", new_callable=AsyncMock) as m_open, \
         patch("app.mcp.pillars.pillar6_strategy.get_broker_driver") as m_drv, \
         patch("app.mcp.pillars.pillar6_strategy.trade_modify_price", new_callable=AsyncMock) as m_mod, \
         patch("app.services.line_service.line_service.send_alert", new_callable=AsyncMock):

        m_open.return_value = {
            "unmatched_orders": [
                {"order_no": "ORD-88", "symbol": "PTT", "side": "BUY", "price": 33.0, "unmatched_vol": 100}
            ]
        }
        m_drv.return_value.get_market_bid_offer = AsyncMock(return_value={"bid_1": 34.0, "offer_1": 34.25})
        m_mod.return_value = {"success": True}

        neg_res = await strategy_negotiate_unmatched_orders(round_name="11:00", tactic="PASSIVE_LURE")
        assert neg_res["success"] is True
        assert neg_res["negotiated_count"] == 1
        assert neg_res["results"][0]["new_price"] == 34.0  # Adjusted to Bid 1 for BUY

    # 3. EOD order cleanup
    with patch("app.mcp.pillars.pillar6_strategy.current_open_orders", new_callable=AsyncMock) as m_open, \
         patch("app.mcp.pillars.pillar6_strategy.trade_cancel_order", new_callable=AsyncMock) as m_cancel, \
         patch("app.services.line_service.line_service.send_alert", new_callable=AsyncMock):

        m_open.return_value = {
            "platform": "CLICK2WIN",
            "unmatched_orders": [
                {"order_no": "ORD-88", "symbol": "PTT"}
            ]
        }
        m_cancel.return_value = {"success": True}

        cleanup_res = await strategy_eod_order_cleanup(platform="CLICK2WIN")
        assert cleanup_res["success"] is True
        assert cleanup_res["cancelled_count"] == 1


# ==============================================================================
# 8. Multi-Account Switching & Strict Capability Guardrails
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_account_capability_guardrails():
    """
    Rigorously verifies:
    1. Dedicated account switching tool: switch_account
    2. SBL guardrail: strict rejection on Click2Win and Krungsri CASH, allowed on Krungsri MARGIN
    3. Trade execution guardrail: stock order on DERIVATIVES rejected, TFEX order on EQUITY rejected
    4. Trade execution: TFEX order allowed on DERIVATIVES
    5. Balances inspection: reports active account & capabilities for all broker accounts
    """
    # 1. Switch Click2Win to DERIVATIVES
    with patch("app.browser.click2win_driver.click2win_driver.switch_account_type", new_callable=AsyncMock) as m_sw:
        m_sw.return_value = True
        sw_res = await switch_account(platform="CLICK2WIN", account_type="DERIVATIVES")
        assert sw_res["success"] is True
        assert sw_res["active_account_type"] == "DERIVATIVES"
        assert AccountCapability.TFEX_TRADE.value in sw_res["capabilities"]
        assert account_context.click2win_active == AccountType.DERIVATIVES

    # 2. Strict rejection: SBL on CLICK2WIN
    sbl_c2w = await sbl_borrow_stock(symbol="PTT", volume=100, platform="CLICK2WIN")
    assert sbl_c2w["success"] is False
    assert sbl_c2w["error_type"] == "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION"
    assert "strictly restricted to Krungsri 'MARGIN'" in sbl_c2w["reason"]

    # 3. Switch Krungsri to CASH, verify SBL rejection
    with patch("app.browser.trademan_driver.trademan_driver.switch_account", new_callable=AsyncMock) as m_kss_sw:
        m_kss_sw.return_value = {
            "success": True,
            "platform": "KRUNGSRI",
            "account_type": "CASH",
            "account_no": "3024959-CASH",
            "status": "AUTHENTICATED_AND_SWITCHED"
        }
        sw_kss_cash = await switch_account(platform="KRUNGSRI", account_type="CASH")
        assert sw_kss_cash["success"] is True
        assert account_context.krungsri_active == AccountType.CASH

    sbl_cash_rej = await sbl_borrow_stock(symbol="CPALL", volume=100, platform="KRUNGSRI")
    assert sbl_cash_rej["success"] is False
    assert sbl_cash_rej["error_type"] == "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION"

    # 4. Switch Krungsri to MARGIN, verify SBL allowed
    with patch("app.browser.trademan_driver.trademan_driver.switch_account", new_callable=AsyncMock) as m_kss_sw2:
        m_kss_sw2.return_value = {
            "success": True,
            "platform": "KRUNGSRI",
            "account_type": "MARGIN",
            "account_no": "3024959",
            "status": "AUTHENTICATED_AND_SWITCHED"
        }
        sw_kss_margin = await switch_account(platform="KRUNGSRI", account_type="MARGIN")
        assert sw_kss_margin["success"] is True
        assert account_context.krungsri_active == AccountType.MARGIN
        assert AccountCapability.SBL_BORROW.value in sw_kss_margin["capabilities"]

    with patch("app.browser.trademan_driver.trademan_driver.execute_sbl_borrow", new_callable=AsyncMock) as m_b:
        m_b.return_value = {"success": True, "status": "BORROW_ACCEPTED"}
        sbl_margin_ok = await sbl_borrow_stock(symbol="CPALL", volume=100, platform="KRUNGSRI")
        assert sbl_margin_ok["success"] is True
        assert sbl_margin_ok["account_type"] == "MARGIN"

    # 5. Trade Guardrails: Click2Win active is currently DERIVATIVES
    # Trading Stock (PTT) on DERIVATIVES account must be strictly rejected
    trade_stock_on_deriv = await trade_place_order(
        symbol="PTT",
        side="BUY",
        volume=100,
        price=34.0,
        platform="CLICK2WIN"
    )
    assert trade_stock_on_deriv["success"] is False
    assert trade_stock_on_deriv["error_type"] == "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION"
    assert "Stock trading is restricted to 'EQUITY' or 'CASH'" in trade_stock_on_deriv["reason"]

    # Switch Click2Win to EQUITY
    with patch("app.browser.click2win_driver.click2win_driver.switch_account_type", new_callable=AsyncMock) as m_sw_eq:
        m_sw_eq.return_value = True
        await switch_account(platform="CLICK2WIN", account_type="EQUITY")
    assert account_context.click2win_active == AccountType.EQUITY

    # Trading TFEX (S50M24) on EQUITY account must be strictly rejected
    trade_tfex_on_equity = await trade_place_order(
        symbol="S50M24",
        side="BUY",
        volume=100,
        price=850.0,
        platform="CLICK2WIN"
    )
    assert trade_tfex_on_equity["success"] is False
    assert trade_tfex_on_equity["error_type"] == "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION"
    assert "TFEX trading is restricted to 'DERIVATIVES' accounts" in trade_tfex_on_equity["reason"]

    # Trading TFEX with explicit account_type="DERIVATIVES" must be accepted
    with patch("app.browser.click2win_driver.click2win_driver.execute_order", new_callable=AsyncMock) as m_ex:
        m_ex.return_value = {"success": True, "order_no": "TFEX-ORD-1"}
        trade_tfex_ok = await trade_place_order(
            symbol="S50M24",
            side="LONG",
            volume=1,
            price=850.0,
            platform="CLICK2WIN",
            account_type="DERIVATIVES"
        )
        assert trade_tfex_ok["success"] is True
        assert trade_tfex_ok["account_type"] == "DERIVATIVES"

    # 6. Balances inspection multi-account verification
    with patch("app.browser.trademan_driver.trademan_driver.scrape_account_summary", new_callable=AsyncMock) as m_sum:
        m_sum.return_value = {"cash_balance": 500_000.0, "excess_equity": 500_000.0}
        bal_res = await portfolio_get_balances(platform="KRUNGSRI")
    assert len(bal_res["accounts"]) == 2
    acc_types = [a["account_type"] for a in bal_res["accounts"]]
    assert "CASH" in acc_types
    assert "MARGIN" in acc_types
    assert any(a["is_active"] for a in bal_res["accounts"])


# ==============================================================================
# 9. End-to-End JSON-RPC over MCP SSE Protocol Verification
# ==============================================================================

def test_mcp_sse_e2e_6pillars_protocol():
    """
    Spawns live Uvicorn instance mounting 6-Pillars Modular MCP Gateway.
    Verifies full JSON-RPC over SSE exchange (initialize and tools/list).
    """
    import uvicorn

    test_port = 8996
    config = uvicorn.Config(app=app, host="127.0.0.1", port=test_port, log_level="warning")
    server = uvicorn.Server(config=config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server ready
    ready = False
    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", test_port), timeout=0.2):
                ready = True
                break
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)

    assert ready, f"Failed to start test Uvicorn server on port {test_port}"

    try:
        # 1. Connect to SSE endpoint
        sse_req = urllib.request.Request(
            f"http://127.0.0.1:{test_port}/sse",
            headers={"Accept": "text/event-stream"}
        )
        sse_resp = urllib.request.urlopen(sse_req, timeout=5)

        l1 = sse_resp.readline().decode().strip()
        l2 = sse_resp.readline().decode().strip()

        assert l1 == "event: endpoint"
        assert "data: /messages/?session_id=" in l2
        endpoint_path = l2.split("data: ")[1].strip()

        # 2. JSON-RPC Initialize
        init_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "AntigravityTestClient", "version": "1.0.0"}
            }
        }).encode()
        post_req = urllib.request.Request(
            f"http://127.0.0.1:{test_port}{endpoint_path}",
            data=init_payload,
            headers={"Content-Type": "application/json"}
        )
        post_resp = urllib.request.urlopen(post_req, timeout=4)
        assert post_resp.status == 202

        # 3. JSON-RPC tools/list
        tools_payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }).encode()
        tools_req = urllib.request.Request(
            f"http://127.0.0.1:{test_port}{endpoint_path}",
            data=tools_payload,
            headers={"Content-Type": "application/json"}
        )
        tools_resp = urllib.request.urlopen(tools_req, timeout=4)
        assert tools_resp.status == 202

        # Read SSE events for 6 Pillars tools
        events_text = ""
        for _ in range(15):
            line = sse_resp.readline().decode()
            events_text += line
            if "trade_place_order" in events_text and "session_get_health" in events_text:
                break

        # Verify that tools from all Pillars are present
        assert "session_get_health" in events_text, "Pillar 1 tool missing"
        assert "trade_place_order" in events_text, "Pillar 3 tool missing"
        assert "sbl_get_inventory" in events_text, "Pillar 4 tool missing"
        assert "portfolio_get_balances" in events_text, "Pillar 2 portfolio tool missing"
        assert "portfolio_list_accounts" in events_text, "portfolio_list_accounts tool missing"
        assert "switch_account" in events_text, "switch_account tool missing"
        assert "strategy_negotiate_unmatched_orders" in events_text, "Pillar 6 tool missing"

    finally:
        server.should_exit = True
        server_thread.join(timeout=2)
