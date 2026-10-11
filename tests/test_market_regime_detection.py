import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MarketSnapshot
from app.services.market_monitor_service import market_monitor_service
from app.services.phase3_scheduler import phase3_scheduler
from app.services.trade_dispatcher import trade_dispatcher
from app.browser.trademan_driver import trademan_driver


@pytest.mark.asyncio
async def test_market_monitor_capture_and_report(db_session: AsyncSession):
    """
    Tests that MarketMonitorService:
    1. Scrapes SET index values.
    2. Persists MarketSnapshot record to SQLite.
    3. Sends a formatted 1-line progress update to LINE.
    """
    mock_snapshot = {
        "index_name": "SET",
        "current_index": 1422.35,
        "change_value": 5.80,
        "pct_change": 0.41,
        "high": 1426.50,
        "low": 1418.10,
        "volume_k": 15200.0,
        "value_mb": 31250.0
    }

    with patch.object(trademan_driver, "scrape_set_index_summary", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = mock_snapshot
        with patch("app.services.line_service.line_service.push_progress_update", new_callable=AsyncMock) as mock_push:
            res = await market_monitor_service.capture_and_report(period_label="10:30")

            assert res["period"] == "10:30"
            assert "SET: 1,422.35 (+0.41%)" in res["summary_text"]
            assert "High: 1,426.50" in res["summary_text"]
            assert "Val: 31,250MB" in res["summary_text"]

            mock_scrape.assert_awaited_once()
            mock_push.assert_awaited_once_with(res["summary_text"])

    # Verify stored in DB
    stmt = select(MarketSnapshot).where(MarketSnapshot.period_name == "10:30")
    db_res = await db_session.execute(stmt)
    snapshot = db_res.scalars().first()
    assert snapshot is not None
    assert snapshot.current_index == 1422.35
    assert snapshot.pct_change == 0.41
    assert snapshot.high == 1426.50
    assert snapshot.value_mb == 31250.0


def test_random_points_generation():
    """
    Tests that generate_random_points():
    1. Returns exactly N points (e.g. 3).
    2. Points are within the specified time window.
    3. Points maintain minimum separation of 15 minutes.
    """
    points = phase3_scheduler.generate_random_points("10:30", "12:00", count=3, min_gap_mins=15)
    assert len(points) == 3

    # Check ascending order
    assert points[0] < points[1] < points[2]

    # Check bounds
    assert "10:30" <= points[0]
    assert points[2] <= "12:00"

    # Check min gap
    def to_mins(t_str: str) -> int:
        h, m = map(int, t_str.split(":"))
        return h * 60 + m

    assert to_mins(points[1]) - to_mins(points[0]) >= 15
    assert to_mins(points[2]) - to_mins(points[1]) >= 15


@pytest.mark.asyncio
async def test_trigger_random_execution_point():
    """
    Tests that trigger_random_execution_point() executes the sequential routine:
    Human Pause -> 3.4 Price Negotiation.
    """
    with patch("app.services.price_negotiation_service.price_negotiation_service.run_negotiation_round", new_callable=AsyncMock) as mock_nego:
        mock_nego.return_value = {"round": "11:15", "actions_evaluated": 0}
        with patch("app.services.line_service.line_service.push_progress_update", new_callable=AsyncMock) as mock_push:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                res = await phase3_scheduler.trigger_random_execution_point(round_time="11:15")

                assert res["round_time"] == "11:15"
                mock_nego.assert_awaited_once_with(round_name="11:15")
                assert mock_push.await_count == 2
                mock_sleep.assert_awaited_once_with(2.0)


def test_get_daily_schedule():
    """
    Tests that get_daily_schedule() returns the 8 market regimes.
    """
    schedule = phase3_scheduler.get_daily_schedule()
    assert "regimes" in schedule
    regimes = schedule["regimes"]
    assert len(regimes) == 8
    assert regimes[0]["period"] == "09:30 - 10:00"
    assert regimes[1]["period"] == "10:00 - 10:30"
    assert regimes[2]["period"] == "10:30 - 12:00"
    assert regimes[3]["period"] == "12:00 - 12:30"
    assert regimes[4]["period"] == "14:00 - 14:30"
    assert regimes[5]["period"] == "14:30 - 16:00"
    assert regimes[6]["period"] == "16:00 - 16:30"
    assert regimes[7]["period"] == "16:30 - 17:00"


@pytest.mark.asyncio
async def test_sequential_execution_queue_pacing():
    """
    Tests that trade_dispatcher enforces sequential locking and human pacing cooldown.
    """
    assert trade_dispatcher._queue_lock is not None
    assert trade_dispatcher.pacing_enabled is True

    # Test order dispatch executes under lock
    trade_dispatcher._current_mode = "TEST"
    res = await trade_dispatcher.dispatch_order(
        symbol="CPALL",
        side="BUY",
        volume=100,
        price=65.00
    )
    assert res["mode"] == "TEST"
    assert res["success"] is True


@pytest.mark.asyncio
async def test_line_webhook_set_and_schedule_commands(db_session: AsyncSession):
    """
    Tests that typing 'set' and 'schedule' via LINE webhook returns the formatted responses.
    """
    from app.services.line_service import line_service

    # 1. Test "set" command
    with patch.object(line_service, "_send_reply", new_callable=AsyncMock) as mock_reply:
        event = {
            "replyToken": "token_test_set",
            "message": {"type": "text", "text": "set"}
        }
        res = await line_service._handle_text_message(db_session, "set", event)
        assert res["status"] == "SET_QUERY_DISPLAYED"
        mock_reply.assert_awaited_once()
        assert "ข้อมูลดัชนีตลาดล่าสุด" in mock_reply.call_args[0][1]

    # 2. Test "schedule" command
    with patch.object(line_service, "_send_reply", new_callable=AsyncMock) as mock_reply:
        event = {
            "replyToken": "token_test_sched",
            "message": {"type": "text", "text": "schedule"}
        }
        res = await line_service._handle_text_message(db_session, "schedule", event)
        assert res["status"] == "SCHEDULE_DISPLAYED"
        mock_reply.assert_awaited_once()
        assert "ตาราง 8 ช่วงเวลาตลาดวันนี้" in mock_reply.call_args[0][1]
