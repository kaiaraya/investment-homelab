"""
Pillar 1 session login — CDP session daemon tests.

Verifies session_login_broker for KRUNGSRI and LIBERATOR routes through
app.services.broker_cdp.daemon_launcher (ensure_daemon / restart_daemon).
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_session_login_broker_liberator_calls_daemon_launcher(monkeypatch):
    from app.mcp.pillars import pillar1_session
    from app.services.broker_cdp import daemon_launcher

    mock_ensure = AsyncMock(return_value={
        "status": "ready",
        "broker": "lib",
        "port": 9334,
        "pid": 1234,
        "page_url": "https://trade.liberator.co.th/",
        "state": "AUTHENTICATED",
    })
    monkeypatch.setattr(daemon_launcher, "ensure_daemon", mock_ensure)

    res = await pillar1_session.session_login_broker("LIBERATOR", force_fresh=False)

    assert res["platform"] == "LIBERATOR"
    assert res["success"] is True
    assert res["status"] == "AUTHENTICATED"
    mock_ensure.assert_awaited_once_with("lib")


@pytest.mark.asyncio
async def test_session_login_broker_krungsri_force_fresh_restarts_daemon(monkeypatch):
    from app.mcp.pillars import pillar1_session
    from app.services.broker_cdp import daemon_launcher

    mock_restart = AsyncMock(return_value={
        "status": "ready",
        "broker": "kss",
        "port": 9333,
        "pid": 5678,
        "page_url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp",
        "state": "AUTHENTICATED",
    })
    monkeypatch.setattr(daemon_launcher, "restart_daemon", mock_restart)

    res = await pillar1_session.session_login_broker("KRUNGSRI", force_fresh=True)

    assert res["platform"] == "TRADEMAN"
    assert res["success"] is True
    assert res["status"] == "AUTHENTICATED"
    mock_restart.assert_awaited_once_with("kss")
