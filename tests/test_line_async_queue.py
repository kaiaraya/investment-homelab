"""
Tests for AsyncCommandQueue in LINE CLI (Loop 2).
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.services.line_cli.queue import AsyncCommandQueue, CommandJob


@pytest.mark.asyncio
async def test_queue_enqueue_and_worker_execution():
    queue = AsyncCommandQueue(maxsize=10)

    executed = []

    async def mock_task():
        executed.append("done")
        return {"status": "ok"}

    queue.start()
    assert queue.is_running is True

    job_id = await queue.enqueue(
        cmd_name="/port all sync",
        func=mock_task,
        push_target="U12345",
        timeout_seconds=2.0
    )

    assert isinstance(job_id, str)
    assert len(job_id) > 0

    # Wait briefly for worker to process
    await asyncio.sleep(0.1)

    assert len(executed) == 1
    assert executed[0] == "done"

    await queue.stop()
    assert queue.is_running is False


@pytest.mark.asyncio
async def test_queue_timeout_handling():
    queue = AsyncCommandQueue(maxsize=10)

    async def slow_task():
        await asyncio.sleep(0.5)
        return {"status": "ok"}

    with patch("app.services.line_service.line_service.push_message", new_callable=AsyncMock) as mock_push:
        queue.start()

        job_id = await queue.enqueue(
            cmd_name="/long_task",
            func=slow_task,
            push_target="U12345",
            timeout_seconds=0.1
        )

        await asyncio.sleep(0.2)

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        assert "หมดเวลา" in args[0]
        assert kwargs.get("to_user_id") == "U12345"

        await queue.stop()


@pytest.mark.asyncio
async def test_queue_status_inspection():
    queue = AsyncCommandQueue(maxsize=10)
    status = queue.get_status()

    assert "running" in status
    assert "pending_count" in status
    assert status["running"] is False
    assert status["pending_count"] == 0


@pytest.mark.asyncio
async def test_webhook_async_queue_delegation_when_running(client, monkeypatch):
    """
    R1: Webhook acknowledges CLI commands with HTTP 200 immediately,
    delegating to async_command_queue when running.
    """
    from app.services.line_cli.queue import async_command_queue
    from app.services.line_service import line_service
    from unittest.mock import AsyncMock

    mock_push = AsyncMock(return_value=True)
    monkeypatch.setattr(line_service, "push_message", mock_push)

    async_command_queue.start()
    try:
        payload = {
            "destination": "U_test_bot",
            "events": [
                {
                    "type": "message",
                    "timestamp": 1718000000000,
                    "replyToken": "tok-async-1",
                    "source": {"type": "user", "userId": "U_ASYNC_USER"},
                    "message": {"type": "text", "id": "m1", "text": "/status"},
                }
            ],
        }
        resp = await client.post("/api/v1/webhook/line", json=payload, headers={"X-Line-Signature": "mock_signature"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "CLI_QUEUED"
        assert "job_id" in data["results"][0]

        # Let the background worker process
        await asyncio.sleep(0.15)
        # Verify result was delivered via push_message
        mock_push.assert_called()
    finally:
        await async_command_queue.stop()


@pytest.mark.asyncio
async def test_webhook_otp_relayed_synchronously_bypasses_queue(client, monkeypatch):
    """
    R1: Critical 2FA OTP relay must be processed synchronously before queuing.
    """
    from app.services.line_cli.queue import async_command_queue

    async_command_queue.start()
    try:
        payload = {
            "events": [
                {
                    "type": "message",
                    "timestamp": 1718000000000,
                    "replyToken": "tok-otp",
                    "source": {"type": "user", "userId": "U_ASYNC_USER"},
                    "message": {"type": "text", "id": "m2", "text": "654321"},
                }
            ]
        }
        resp = await client.post("/api/v1/webhook/line", json=payload, headers={"X-Line-Signature": "mock_signature"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["results"][0]["status"] == "OTP_RELAYED"
        assert data["results"][0]["otp"] == "654321"
    finally:
        await async_command_queue.stop()


@pytest.mark.asyncio
async def test_webhook_halt_bypasses_queue(client, monkeypatch):
    """
    R1 / Guardrail 1: Kill-switch /halt must bypass the queue immediately.
    """
    from app.services.line_cli.queue import async_command_queue
    from app.services.line_service import line_service
    from unittest.mock import AsyncMock

    monkeypatch.setattr(line_service, "_send_reply", AsyncMock())

    async_command_queue.start()
    try:
        payload = {
            "events": [
                {
                    "type": "message",
                    "timestamp": 1718000000000,
                    "replyToken": "tok-halt",
                    "source": {"type": "user", "userId": "U_ASYNC_USER"},
                    "message": {"type": "text", "id": "m3", "text": "/halt"},
                }
            ]
        }
        resp = await client.post("/api/v1/webhook/line", json=payload, headers={"X-Line-Signature": "mock_signature"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["results"][0]["status"] == "KILL_SWITCH_ACTIVATED"
    finally:
        await async_command_queue.stop()
        from app.services.kill_switch_service import kill_switch_service
        await kill_switch_service.reset(authorized_by="TEST")


@pytest.mark.asyncio
async def test_rapid_burst_consecutive_commands_sequential_order():
    """
    Edge case: Rapid burst of commands from same user processed in strict sequential FIFO order.
    """
    queue = AsyncCommandQueue(maxsize=10)
    queue.start()

    log = []

    async def make_job(idx):
        async def _job():
            log.append(f"start_{idx}")
            await asyncio.sleep(0.02)
            log.append(f"end_{idx}")
            return {"status": "ok", "idx": idx}
        return _job

    try:
        job_ids = []
        for i in range(5):
            job_fn = await make_job(i)
            jid = await queue.enqueue(cmd_name=f"/cmd_{i}", func=job_fn, push_target="U_BURST")
            job_ids.append(jid)

        assert len(job_ids) == 5

        # Wait for all to finish
        await asyncio.sleep(0.3)

        expected_sequence = [
            "start_0", "end_0",
            "start_1", "end_1",
            "start_2", "end_2",
            "start_3", "end_3",
            "start_4", "end_4",
        ]
        assert log == expected_sequence
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_queue_full_non_blocking_rejection(client, monkeypatch):
    """
    R1 Edge Case: When AsyncCommandQueue is at capacity (QueueFull),
    it must reject immediately without blocking incoming webhook HTTP request.
    """
    from app.services.line_cli.queue import async_command_queue
    from app.services.line_service import line_service

    mock_send = AsyncMock()
    monkeypatch.setattr(line_service, "_send_reply", mock_send)

    # Force a small queue with capacity 1
    async_command_queue._maxsize = 1
    async_command_queue.start()

    try:
        # Fill the queue with a slow task
        async def slow_job():
            await asyncio.sleep(2.0)
            return {"status": "ok"}

        job1 = await async_command_queue.enqueue(
            cmd_name="/slow",
            func=slow_job,
            push_target="U_TEST",
            timeout_seconds=5.0
        )
        assert job1 is not None

        # Queue is now full (qsize == 1). Second command should be rejected immediately with 200 OK.
        payload = {
            "events": [
                {
                    "type": "message",
                    "timestamp": 1718000000000,
                    "replyToken": "tok-full-queue",
                    "source": {"type": "user", "userId": "U_TEST_USER"},
                    "message": {"type": "text", "id": "m_full", "text": "/status"},
                }
            ]
        }
        resp = await client.post("/api/v1/webhook/line", json=payload, headers={"X-Line-Signature": "mock_signature"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "CLI_QUEUE_FULL"
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert "คิวคำสั่งระบบเต็ม" in args[1]
    finally:
        await async_command_queue.stop()
        async_command_queue._maxsize = 50


@pytest.mark.asyncio
async def test_queue_timeout_and_error_fallback_push_target(monkeypatch):
    """
    R1: When job.push_target is None, timeout and error alerts must fall back
    to settings.LINE_GROUP_ID or settings.LINE_ADMIN_USER_ID.
    """
    from app.core.config import settings
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_HOMELAB_GROUP")

    queue = AsyncCommandQueue(maxsize=10)

    async def slow_job():
        await asyncio.sleep(0.5)

    with patch("app.services.line_service.line_service.push_message", new_callable=AsyncMock) as mock_push:
        queue.start()
        try:
            await queue.enqueue(cmd_name="/slow_no_target", func=slow_job, push_target=None, timeout_seconds=0.05)
            await asyncio.sleep(0.15)
            mock_push.assert_called_once()
            args, kwargs = mock_push.call_args
            assert "หมดเวลา" in args[0]
            assert kwargs.get("to_user_id") == "C_HOMELAB_GROUP"
        finally:
            await queue.stop()
