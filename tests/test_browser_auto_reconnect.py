import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.browser.auth_driver import auth_driver
from app.browser.session_sentinel import session_sentinel
from app.core.events import event_bus
from app.services.line_service import line_service
from app.db.models import SessionLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_auto_reconnect_silent_cookie_recovery(db_session: AsyncSession):
    """
    Verifies that when session drops during trading hours,
    Auto-Reconnect first attempts silent cookie verification (verify_saved_session).
    If valid, resets reconnect_attempts and sends success notification.
    """
    session_sentinel.reconnect_attempts = 0
    session_sentinel._reconnecting = False

    with patch.object(session_sentinel, "is_trading_hours", return_value=True):
        with patch.object(auth_driver, "verify_saved_session", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = True
            with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
                success = await session_sentinel.trigger_auto_reconnect()
                assert success is True
                assert session_sentinel.reconnect_attempts == 0
                mock_verify.assert_awaited_once()
                mock_push.assert_awaited_once()
                assert "ฟื้นฟูอัตโนมัติสำเร็จ" in mock_push.call_args[0][0]


@pytest.mark.asyncio
async def test_auto_reconnect_max_attempts_critical_alert(db_session: AsyncSession):
    """
    Verifies that after 3 failed reconnect attempts:
    1. System halts auto-reconnection.
    2. Sends a Critical Alert to LINE.
    3. Logs AUTO_RECONNECT_HALTED in session_logs.
    """
    session_sentinel.reconnect_attempts = 3
    session_sentinel._reconnecting = False

    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        success = await session_sentinel.trigger_auto_reconnect()
        assert success is False
        mock_push.assert_awaited_once()
        alert_msg = mock_push.call_args[0][0]
        assert "CRITICAL ALERT" in alert_msg
        assert "ครบ 3 ครั้งแล้วแต่ไม่สำเร็จ" in alert_msg

    # Verify DB log
    stmt = select(SessionLog).where(SessionLog.event_type == "AUTO_RECONNECT_HALTED")
    res = await db_session.execute(stmt)
    log = res.scalars().first()
    assert log is not None
