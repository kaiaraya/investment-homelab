import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_console_html_rendering():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/console")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        body = res.text
        # Check core 6-Pillars cockpit elements
        assert "Investment Homelab - Operations Cockpit" in body
        assert "Krungsri TradeMan" in body
        assert "Liberator WebTrade" in body
        assert "Direct Order Execution (Sandbox / Broker)" in body
        assert "Tactical Strategy Tools" in body
        assert "btnMasterConnect" in body
        assert "hitlOtpBanner" in body
        # 2026-10-10 redesign: component toggles + real reload + Pillar x Broker matrix
        assert "btnReloadGateway" in body
        assert "controlPanel" in body
        assert "featureMatrixTable" in body
        assert "featureMatrixBody" in body
        assert "componentToggles" in body
        assert "tradingModeBadge" in body
        assert "loadControlPanel" in body
        assert "toggleComponent" in body
        assert "reloadGateway" in body
        # Ensure deactivated monitor/alert UI and pruned legacy components are NOT present
        assert "openApiBrokerId" not in body
        # 2026-10-10: "Click2Win Sandbox" + "KDE Connect Bridge" cards (and readiness Step 1) removed.
        # Assert card-specific markers only: the bare phrase "Click2Win Sandbox" still legitimately
        # appears in the Order Execution panel copy, so match the card title span (emoji + text).
        assert "🎯 Click2Win Sandbox" not in body
        assert "📱 KDE Connect Bridge" not in body
        assert "Hardware Bridge (KDE Connect)" not in body
        assert "c2wStatusPill" not in body
        assert "triggerKdePing" not in body
        assert '<tbody id="favWatchlistTableBody">' not in body
        assert '<span id="pollingStatusBadge"' not in body
        assert '<div id="tpSlModalBox"' not in body
        assert "Real-Time Watchlist & Multi-Account Cockpit" not in body
        assert "Real-Time Multi-Account TP/SL Monitoring Dashboard" not in body
        # Monitor & Alert feature endpoints must be fully removed (404)
        res_gone = await client.get("/api/v1/phase3/monitors/active")
        assert res_gone.status_code == 404
        assert "5 Scenario Simulator" not in body
        assert "Time Warp" not in body
        assert "10:00 - 19:30 Full Lifecycle" not in body
        assert "MacroDroid Signal Ingestion" not in body


from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_unified_health_and_connect_all_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/api/v1/session/health")
        assert res.status_code == 200
        data = res.json()
        assert "krungsri_trademan" in data
        assert "settrade" in data
        assert "kdeconnect" in data
        assert "status" in data["kdeconnect"]

        # 2. Connect all brokers (mocked to prevent live browser launches)
        mock_connect_res = {
            "success": True,
            "actions": {
                "kdeconnect": {"status": "refreshed", "reachable": True},
                "click2win": {"success": True, "status": "AUTHENTICATED"},
                "krungsri": {"success": True, "status": "AUTHENTICATED"}
            },
            "health": data
        }
        with patch("app.mcp.pillars.pillar1_session.session_connect_all", new_callable=AsyncMock) as m_conn:
            m_conn.return_value = mock_connect_res
            res_connect = await client.post("/api/v1/session/connect-all")
            assert res_connect.status_code == 200
            conn_data = res_connect.json()
            assert conn_data.get("success") is True
            assert "actions" in conn_data
            assert "kdeconnect" in conn_data["actions"]


@pytest.mark.asyncio
async def test_quick_execute():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Quick execute (mocked order dispatch)
        order_payload = {
            "symbol": "TRUE",
            "side": "BUY",
            "volume": 100,
            "price": 13.20,
            "broker": "CLICK2WIN",
            "account_type": "EQUITY"
        }
        with patch("app.mcp.pillars.pillar3_trade.trade_place_order", new_callable=AsyncMock) as m_place:
            m_place.return_value = {
                "success": True,
                "order_no": "C2W-MOCK-001",
                "symbol": "TRUE",
                "side": "BUY",
                "volume": 100,
                "price": 13.20,
                "status": "QUEUING"
            }
            res_order = await client.post("/api/v1/orders/quick-execute", json=order_payload)
            assert res_order.status_code == 200
            order_data = res_order.json()
            assert order_data.get("success") is True or "status" in order_data or "order_no" in order_data


@pytest.mark.asyncio
async def test_hitl_live_order_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Submit order for real-money broker (KRUNGSRI) to trigger HITL gate
        hitl_payload = {
            "symbol": "BDMS",
            "side": "BUY",
            "volume": 100,
            "price": 28.50,
            "broker": "KRUNGSRI"
        }
        res_exec = await client.post("/api/v1/orders/quick-execute", json=hitl_payload)
        assert res_exec.status_code == 200
        data = res_exec.json()
        assert data.get("hitl_required") is True
        assert data.get("status") == "AWAITING_HITL_CONFIRMATION"
        order_id = data.get("order_id")
        assert order_id is not None

        # 2. Check pending HITL orders
        res_pending = await client.get("/api/v1/orders/hitl/pending")
        assert res_pending.status_code == 200
        pending_list = res_pending.json()
        assert any(item["order_id"] == order_id for item in pending_list)

        # 3. Confirm order execution (mock broker dispatch to isolate from live browser/validator idempotency)
        from app.brokers.base import OrderResult
        with patch("app.brokers.krungsri.plugin.KrungsriBrokerPlugin.place_order", new_callable=AsyncMock) as m_trade:
            m_trade.return_value = OrderResult(success=True, order_id=order_id, broker_name="krungsri", message="Order confirmed and dispatched")
            res_confirm = await client.post(f"/api/v1/orders/hitl/{order_id}/confirm")
            assert res_confirm.status_code == 200
            confirm_data = res_confirm.json()
            assert confirm_data.get("success") is True
            assert confirm_data.get("order_id") == order_id

        # 4. Submit a second order and test rejection
        hitl_payload2 = {
            "symbol": "BDMS",
            "side": "BUY",
            "volume": 100,
            "price": 28.75,
            "broker": "KRUNGSRI"
        }
        res_exec2 = await client.post("/api/v1/orders/quick-execute", json=hitl_payload2)
        data2 = res_exec2.json()
        order_id2 = data2.get("order_id")
        assert order_id2 is not None

        res_reject = await client.post(f"/api/v1/orders/hitl/{order_id2}/reject")
        assert res_reject.status_code == 200
        reject_data = res_reject.json()
        assert reject_data.get("status") == "CANCELLED"

