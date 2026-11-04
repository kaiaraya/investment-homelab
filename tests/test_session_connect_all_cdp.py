# -*- coding: utf-8 -*-
"""Unit tests for CDP-first session_connect_all() and /api/v1/session/connect-all."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.mcp.pillars.pillar1_session import session_connect_all


@pytest.fixture
def mock_kde_and_health():
    with (
        patch("app.services.kdeconnect_service.kdeconnect_service.refresh_devices", new_callable=AsyncMock),
        patch("app.services.kdeconnect_service.kdeconnect_service.is_device_reachable", new_callable=AsyncMock, return_value=True),
        patch("app.mcp.pillars.pillar1_session.session_get_health", new_callable=AsyncMock, return_value={"krungsri_trademan": {}, "settrade": {}, "kdeconnect": {"status": "ok"}}),
    ):
        yield


@pytest.mark.asyncio
async def test_session_connect_all_both_authenticated(mock_kde_and_health):
    """Both daemons already active and AUTHENTICATED -> attaches without calling ensure_daemon."""
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state,
        patch("app.services.broker_cdp.daemon_launcher.ensure_daemon", new_callable=AsyncMock) as m_ensure,
    ):
        async def fake_state(broker):
            if broker == "kss":
                return {"state": "AUTHENTICATED", "port": 9333, "page_url": "https://streaming.settrade.com", "pid": 1111}
            return {"state": "AUTHENTICATED", "port": 9334, "page_url": "https://trade.liberator.co.th", "pid": 2222}
        
        m_state.side_effect = fake_state
        
        res = await session_connect_all()
        
        assert res["success"] is True
        assert m_ensure.call_count == 0
        
        actions = res["actions"]
        assert "click2win" not in actions
        assert "settrade_openapi" not in actions
        assert "kdeconnect" in actions
        
        kss = actions["krungsri"]
        assert kss["success"] is True
        assert kss["status"] == "already_up"
        assert kss["state"] == "AUTHENTICATED"
        assert kss["port"] == 9333
        assert kss["pid"] == 1111
        
        lib = actions["liberator"]
        assert lib["success"] is True
        assert lib["status"] == "already_up"
        assert lib["state"] == "AUTHENTICATED"
        assert lib["port"] == 9334
        assert lib["pid"] == 2222


@pytest.mark.asyncio
async def test_session_connect_all_spawns_when_down(mock_kde_and_health):
    """Daemons down -> ensure_daemon called and successfully spawns to AUTHENTICATED."""
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state,
        patch("app.services.broker_cdp.daemon_launcher.ensure_daemon", new_callable=AsyncMock) as m_ensure,
    ):
        m_state.return_value = {"state": "DAEMON_DOWN", "port": 9333, "page_url": None, "pid": None}
        
        async def fake_ensure(broker):
            port = 9333 if broker == "kss" else 9334
            return {"status": "spawned", "state": "AUTHENTICATED", "port": port, "pid": 5000 + port}
        
        m_ensure.side_effect = fake_ensure
        
        res = await session_connect_all()
        
        assert res["success"] is True
        assert m_ensure.call_count == 2
        
        actions = res["actions"]
        assert actions["krungsri"]["success"] is True
        assert actions["krungsri"]["status"] == "spawned"
        assert actions["krungsri"]["state"] == "AUTHENTICATED"
        assert actions["krungsri"]["port"] == 9333
        assert actions["krungsri"]["pid"] == 14333
        
        assert actions["liberator"]["success"] is True
        assert actions["liberator"]["status"] == "spawned"
        assert actions["liberator"]["state"] == "AUTHENTICATED"
        assert actions["liberator"]["port"] == 9334
        assert actions["liberator"]["pid"] == 14334


@pytest.mark.asyncio
async def test_session_connect_all_otp_page_returns_immediately(mock_kde_and_health):
    """If daemon requires OTP -> returns immediately with Thai notification message (no quiet hang)."""
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state,
        patch("app.services.broker_cdp.daemon_launcher.ensure_daemon", new_callable=AsyncMock) as m_ensure,
    ):
        m_state.return_value = {"state": "DAEMON_DOWN", "port": 9333, "page_url": None, "pid": None}
        
        async def fake_ensure(broker):
            if broker == "kss":
                return {"status": "OTP_PAGE", "state": "OTP_PAGE", "port": 9333, "pid": 3333}
            return {"status": "already_up", "state": "AUTHENTICATED", "port": 9334, "pid": 4444}
        
        m_ensure.side_effect = fake_ensure
        
        res = await session_connect_all()
        
        kss = res["actions"]["krungsri"]
        assert kss["success"] is False
        assert kss["state"] == "OTP_PAGE"
        assert kss["port"] == 9333
        assert kss["pid"] == 3333
        assert kss["message"] == "เปิดหน้า login แล้ว รอ OTP ที่การ์ด LINE"


@pytest.mark.asyncio
async def test_session_connect_all_already_at_otp_page(mock_kde_and_health):
    """If daemon_state is already at OTP_PAGE -> returns immediately without calling ensure_daemon."""
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state,
        patch("app.services.broker_cdp.daemon_launcher.ensure_daemon", new_callable=AsyncMock) as m_ensure,
    ):
        async def fake_state(broker):
            if broker == "kss":
                return {"state": "OTP_PAGE", "port": 9333, "page_url": "https://wen075.settrade.com/twofa", "pid": 3333}
            return {"state": "AUTHENTICATED", "port": 9334, "page_url": "https://trade.liberator.co.th", "pid": 4444}
        
        m_state.side_effect = fake_state
        
        res = await session_connect_all()
        
        assert m_ensure.call_count == 0
        kss = res["actions"]["krungsri"]
        assert kss["success"] is False
        assert kss["state"] == "OTP_PAGE"
        assert kss["message"] == "เปิดหน้า login แล้ว รอ OTP ที่การ์ด LINE"


@pytest.mark.asyncio
async def test_session_connect_all_login_page_returns_immediately(mock_kde_and_health):
    """If daemon requires LOGIN_PAGE -> returns immediately with Thai notification message."""
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state,
        patch("app.services.broker_cdp.daemon_launcher.ensure_daemon", new_callable=AsyncMock) as m_ensure,
    ):
        async def fake_state(broker):
            if broker == "liberator":
                return {"state": "LOGIN_PAGE", "port": 9334, "page_url": "https://trade.liberator.co.th/login", "pid": 5555}
            return {"state": "AUTHENTICATED", "port": 9333, "page_url": "https://streaming.settrade.com", "pid": 6666}
        
        m_state.side_effect = fake_state
        
        res = await session_connect_all()
        
        assert m_ensure.call_count == 0
        lib = res["actions"]["liberator"]
        assert lib["success"] is False
        assert lib["state"] == "LOGIN_PAGE"
        assert lib["port"] == 9334
        assert lib["message"] == "เปิดหน้า login แล้ว รอ OTP ที่การ์ด LINE"


@pytest.mark.asyncio
async def test_session_connect_all_never_calls_legacy_logins(mock_kde_and_health):
    """Verify session_login_broker is NEVER called from session_connect_all."""
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state,
        patch("app.mcp.pillars.pillar1_session.session_login_broker", new_callable=AsyncMock) as m_legacy_login,
    ):
        m_state.return_value = {"state": "AUTHENTICATED", "port": 9333, "page_url": None, "pid": 1234}
        
        await session_connect_all()
        
        assert m_legacy_login.call_count == 0


@pytest.mark.asyncio
async def test_session_connect_all_error_handling(mock_kde_and_health):
    """If daemon inspection throws an unexpected exception, error is captured gracefully per broker."""
    with patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state:
        m_state.side_effect = RuntimeError("CDP socket failure")
        
        res = await session_connect_all()
        assert res["success"] is True
        assert res["actions"]["krungsri"]["success"] is False
        assert res["actions"]["krungsri"]["status"] == "error"
        assert res["actions"]["krungsri"]["state"] == "UNKNOWN"
        assert res["actions"]["krungsri"]["port"] == 9333
        assert "CDP socket failure" in res["actions"]["krungsri"]["error"]


@pytest.mark.asyncio
async def test_session_connect_all_api_endpoint_cdp(mock_kde_and_health):
    """Test POST /api/v1/session/connect-all with FastAPI AsyncClient returning CDP-first response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.services.broker_cdp.daemon_launcher.daemon_state", new_callable=AsyncMock) as m_state:
            async def fake_state(broker):
                port = 9333 if broker == "kss" else 9334
                return {"state": "AUTHENTICATED", "port": port, "page_url": "http://localhost", "pid": 8888}
            
            m_state.side_effect = fake_state
            
            resp = await client.post("/api/v1/session/connect-all")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "actions" in data
            assert "health" in data
            
            actions = data["actions"]
            assert "krungsri" in actions
            assert "liberator" in actions
            assert actions["krungsri"]["port"] == 9333
            assert actions["krungsri"]["state"] == "AUTHENTICATED"
            assert actions["liberator"]["port"] == 9334
            assert actions["liberator"]["state"] == "AUTHENTICATED"
