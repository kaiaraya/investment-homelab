"""
Pillar 1 session login — focused regression for CLI-RCA-005.

``/login lib`` silently hung because ``session_login_broker`` raised
``NameError: name 'os' is not defined`` in the LIBERATOR branch (missing
``import os``). This test drives the *real* ``session_login_broker`` code path
for LIBERATOR with only the driver mocked, so the ``import os`` fix is actually
exercised (not stubbed away).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_session_login_broker_liberator_imports_os(monkeypatch):
    from app.mcp.pillars import pillar1_session
    from app.brokers.liberator.driver import liberator_driver

    # No saved session file -> os.path.exists(...) must evaluate (would NameError
    # without ``import os``). Use a path that does not exist.
    monkeypatch.setattr(liberator_driver, "session_path", "/nonexistent/lib_session.json")
    login = AsyncMock(return_value=SimpleNamespace(
        success=True,
        status=SimpleNamespace(value="AUTHENTICATED"),
        message="ok",
        otp_ref=None,
    ))
    monkeypatch.setattr(liberator_driver, "login", login)

    res = await pillar1_session.session_login_broker("LIBERATOR", force_fresh=False)

    assert res["platform"] == "LIBERATOR"
    assert res["success"] is True
    assert res["status"] == "AUTHENTICATED"
    login.assert_awaited_once()
