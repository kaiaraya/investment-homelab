import pytest
from httpx import AsyncClient
from app.core.events import event_bus


@pytest.mark.asyncio
async def test_line_webhook_otp_relayed(client: AsyncClient):
    payload = {
        "events": [
            {
                "type": "message",
                "timestamp": 1718000000000,
                "message": {
                    "type": "text",
                    "id": "msg_001",
                    "text": "849201"
                }
            }
        ]
    }
    headers = {"X-Line-Signature": "mock_signature"}
    response = await client.post("/api/v1/webhook/line", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["results"][0]["status"] == "OTP_RELAYED"
    assert data["results"][0]["otp"] == "849201"
    assert event_bus.otp_queue.qsize() > 0


@pytest.mark.asyncio
async def test_line_webhook_verify_ping_empty_body(client: AsyncClient):
    """
    LINE-RCA-001 (2026-10-08): the LINE Console "Verify" button POSTs an EMPTY body
    with a valid signature. It must be acknowledged with HTTP 200 (not 400 from a
    failed `json.loads("")`), otherwise the console reports the webhook as broken.
    """
    response = await client.post(
        "/api/v1/webhook/line",
        content=b"",
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["processed"] == 0
    assert data["note"] == "verify_ping"


@pytest.mark.asyncio
async def test_line_webhook_captures_group_id(client: AsyncClient, tmp_path, monkeypatch):
    """
    Zero-touch onboarding: a message from a LINE group must persist `source.groupId`
    into `.env` as LINE_GROUP_ID (the OTP push target) when it is not yet configured.
    """
    from app.api.v1.endpoints import webhook_line
    from app.core.config import settings

    env_file = tmp_path / ".env"
    env_file.write_text("LINE_CHANNEL_SECRET=dummy\n", encoding="utf-8")

    monkeypatch.setattr(webhook_line, "_env_path", lambda: env_file)
    monkeypatch.setattr(webhook_line, "_last_seen_group_id", None)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)

    payload = {
        "events": [
            {
                "type": "message",
                "source": {
                    "type": "group",
                    "groupId": "C_test_group_123",
                    "userId": "U_test_user_456",
                },
                "message": {"type": "text", "id": "msg_003", "text": "hello homelab"},
            }
        ]
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200
    assert settings.LINE_GROUP_ID == "C_test_group_123"
    assert "LINE_GROUP_ID=C_test_group_123" in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_verify_ping_empty_events(client: AsyncClient):
    """
    LINE-RCA-001 follow-up (2026-10-08): the *real* LINE Console "Verify" request is a
    JSON body with an EMPTY `events` array (not the raw empty body). It must also be
    acknowledged with HTTP 200 + note="verify_ping", otherwise the console reports the
    webhook as broken.
    """
    payload = {"destination": "U_test_bot", "events": []}
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["processed"] == 0
    assert data["note"] == "verify_ping"


@pytest.mark.asyncio
async def test_line_webhook_join_event_captures_group_id(
    client: AsyncClient, tmp_path, monkeypatch
):
    """
    LINE-RCA-003 follow-up (2026-10-08): when the bot is invited into a group LINE
    sends a `join` event whose `source.groupId` must be captured WITHOUT waiting for
    the first message. This is the exact gap observed live: the bot was in the group
    but LINE_GROUP_ID stayed empty because no event had been recorded.

    It must also be answered with HTTP 200 so LINE does not retry/mark the webhook bad.
    """
    from app.api.v1.endpoints import webhook_line
    from app.core.config import settings

    env_file = tmp_path / ".env"
    env_file.write_text("LINE_CHANNEL_SECRET=dummy\n", encoding="utf-8")

    monkeypatch.setattr(webhook_line, "_env_path", lambda: env_file)
    monkeypatch.setattr(webhook_line, "_last_seen_group_id", None)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "join",
                "timestamp": 1718000000000,
                "source": {
                    "type": "group",
                    "groupId": "C_join_group_789",
                    "userId": "U_test_user_456",
                },
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200
    assert settings.LINE_GROUP_ID == "C_join_group_789"
    assert "LINE_GROUP_ID=C_join_group_789" in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_1to1_captures_direct_target_not_group(
    client: AsyncClient, tmp_path, monkeypatch
):
    """
    LINE-RCA-006 (2026-10-08, Path B): a message typed in the **1:1 bot chat** carries
    `source.type="user"` and NO `groupId`.

      * `LINE_GROUP_ID`     must stay EMPTY — a user id is never a group id (LINE-RCA-004)
      * `LINE_ADMIN_USER_ID` must be captured instead — that is the `line_direct` push
        target which makes the relay usable without a group at all

    This is the exact live symptom observed: the operator typed "Hi" in the 1:1 chat,
    the webhook received `['message']` with HTTP 200, and every target stayed empty.
    """
    from app.api.v1.endpoints import webhook_line
    from app.core.config import settings

    env_file = tmp_path / ".env"
    env_file.write_text("LINE_CHANNEL_SECRET=dummy\n", encoding="utf-8")

    monkeypatch.setattr(webhook_line, "_env_path", lambda: env_file)
    monkeypatch.setattr(webhook_line, "_last_seen_group_id", None)
    monkeypatch.setattr(webhook_line, "_last_seen_user_id", None)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "message",
                "timestamp": 1718000000000,
                "source": {"type": "user", "userId": "U_1to1_chat"},
                "message": {"type": "text", "id": "msg_1to1", "text": "Hi"},
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200

    body = env_file.read_text(encoding="utf-8")
    assert settings.LINE_GROUP_ID is None
    assert "LINE_GROUP_ID" not in body

    assert settings.LINE_ADMIN_USER_ID == "U_1to1_chat"
    assert "LINE_ADMIN_USER_ID=U_1to1_chat" in body


@pytest.mark.asyncio
async def test_line_webhook_group_event_does_not_capture_direct_target(
    client: AsyncClient, tmp_path, monkeypatch
):
    """
    A group event ALSO carries `source.userId` — but that is the *sender* (a group
    member), NOT the operator's 1:1 chat. Capturing it would push OTP messages to a
    random group member's private chat. Only `source.type == "user"` may set
    `LINE_ADMIN_USER_ID`.
    """
    from app.api.v1.endpoints import webhook_line
    from app.core.config import settings

    env_file = tmp_path / ".env"
    env_file.write_text("LINE_CHANNEL_SECRET=dummy\n", encoding="utf-8")

    monkeypatch.setattr(webhook_line, "_env_path", lambda: env_file)
    monkeypatch.setattr(webhook_line, "_last_seen_group_id", None)
    monkeypatch.setattr(webhook_line, "_last_seen_user_id", None)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "message",
                "timestamp": 1718000000000,
                "source": {
                    "type": "group",
                    "groupId": "C_group_only",
                    "userId": "U_group_member",
                },
                "message": {"type": "text", "id": "msg_grp", "text": "hello group"},
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200

    body = env_file.read_text(encoding="utf-8")
    assert settings.LINE_GROUP_ID == "C_group_only"
    assert "LINE_GROUP_ID=C_group_only" in body
    assert settings.LINE_ADMIN_USER_ID is None
    assert "LINE_ADMIN_USER_ID" not in body


@pytest.mark.asyncio
async def test_line_webhook_operator_set_direct_id_is_never_overwritten(
    client: AsyncClient, tmp_path, monkeypatch
):
    """
    Zero-Contradiction: an operator-set `LINE_ADMIN_USER_ID` must win over the
    auto-captured value (same rule that already protects `LINE_GROUP_ID`).
    """
    from app.api.v1.endpoints import webhook_line
    from app.core.config import settings

    env_file = tmp_path / ".env"
    env_file.write_text("LINE_ADMIN_USER_ID=U_operator_pinned\n", encoding="utf-8")

    monkeypatch.setattr(webhook_line, "_env_path", lambda: env_file)
    monkeypatch.setattr(webhook_line, "_last_seen_user_id", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_operator_pinned")

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "message",
                "timestamp": 1718000000000,
                "source": {"type": "user", "userId": "U_someone_else"},
                "message": {"type": "text", "id": "msg_pin", "text": "Hi"},
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )
    assert response.status_code == 200
    assert settings.LINE_ADMIN_USER_ID == "U_operator_pinned"
    assert "U_someone_else" not in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_close_command(client: AsyncClient):
    payload = {
        "events": [
            {
                "type": "message",
                "timestamp": 1718000000000,
                "message": {
                    "type": "text",
                    "id": "msg_002",
                    "text": "Close AP"
                }
            }
        ]
    }
    headers = {"X-Line-Signature": "mock_signature"}
    response = await client.post("/api/v1/webhook/line", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["status"] == "COMMAND_DISPATCHED"
    assert data["results"][0]["symbol"] == "AP"
    assert event_bus.command_queue.qsize() > 0


# ---------------------------------------------------------------------------
# LINE-RCA-008 (2026-10-08): lifecycle release — a captured target the OA can no longer
# reach must be dropped, otherwise `.env` stays poisoned forever and the OTP relay dies
# silently (live proof: `join` 16:11:18 → captured; `leave` 16:12:27 → group/summary 404
# → push "Failed to send messages" while the old gate still reported ready=true).
# ---------------------------------------------------------------------------


def _lifecycle_env(tmp_path, monkeypatch, *, line_group_id, admin_user_id):
    from app.api.v1.endpoints import webhook_line
    from app.core.config import settings

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"LINE_CHANNEL_SECRET=dummy\n{line_group_id or ''}\n", encoding="utf-8"
    )
    monkeypatch.setattr(webhook_line, "_env_path", lambda: env_file)
    monkeypatch.setattr(webhook_line, "_last_seen_group_id", None)
    monkeypatch.setattr(webhook_line, "_last_seen_user_id", None)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", line_group_id)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", admin_user_id)
    return env_file, settings


@pytest.mark.asyncio
async def test_line_webhook_leave_event_releases_stale_group_id(
    client: AsyncClient, tmp_path, monkeypatch
):
    """`leave` for the configured group → LINE_GROUP_ID cleared (in-process + .env)."""
    env_file, settings = _lifecycle_env(
        tmp_path, monkeypatch, line_group_id="C_stale_group", admin_user_id=None
    )

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "leave",
                "timestamp": 1718000000000,
                "source": {"type": "group", "groupId": "C_stale_group"},
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )

    assert response.status_code == 200
    assert settings.LINE_GROUP_ID is None
    assert "LINE_GROUP_ID=\n" in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_leave_event_ignores_other_group(
    client: AsyncClient, tmp_path, monkeypatch
):
    """A `leave` from a group we do NOT target must never clear the configured target."""
    env_file, settings = _lifecycle_env(
        tmp_path, monkeypatch, line_group_id="C_our_group", admin_user_id=None
    )

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "leave",
                "timestamp": 1718000000000,
                "source": {"type": "group", "groupId": "C_some_other_group"},
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )

    assert response.status_code == 200
    assert settings.LINE_GROUP_ID == "C_our_group"
    assert "LINE_GROUP_ID=" not in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_member_left_event_never_captures_or_releases(
    client: AsyncClient, tmp_path, monkeypatch
):
    """`memberLeft` is about another member — it must neither capture nor release a target."""
    env_file, settings = _lifecycle_env(
        tmp_path, monkeypatch, line_group_id=None, admin_user_id=None
    )

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "memberLeft",
                "timestamp": 1718000000000,
                "source": {
                    "type": "group",
                    "groupId": "C_group_we_left",
                    "userId": "U_member",
                },
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )

    assert response.status_code == 200
    assert settings.LINE_GROUP_ID is None
    assert "LINE_GROUP_ID" not in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_unfollow_event_releases_direct_target(
    client: AsyncClient, tmp_path, monkeypatch
):
    """`unfollow` (operator blocked the OA) → LINE_ADMIN_USER_ID cleared."""
    env_file, settings = _lifecycle_env(
        tmp_path, monkeypatch, line_group_id=None, admin_user_id="U_operator_1to1"
    )

    payload = {
        "destination": "U_test_bot",
        "events": [
            {
                "type": "unfollow",
                "timestamp": 1718000000000,
                "source": {"type": "user", "userId": "U_operator_1to1"},
            }
        ],
    }
    response = await client.post(
        "/api/v1/webhook/line",
        json=payload,
        headers={"X-Line-Signature": "mock_signature"},
    )

    assert response.status_code == 200
    assert settings.LINE_ADMIN_USER_ID is None
    assert "LINE_ADMIN_USER_ID=\n" in env_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_line_webhook_rejoin_after_leave_recaptures_same_group(
    client: AsyncClient, tmp_path, monkeypatch
):
    """
    Self-healing round trip: `leave` releases, a later `join` for the SAME group must be
    re-captured (the module-level `_last_seen_group_id` de-dup guard has to be reset).
    """
    env_file, settings = _lifecycle_env(
        tmp_path, monkeypatch, line_group_id="C_round_trip", admin_user_id=None
    )

    for event_type in ("leave", "join"):
        payload = {
            "destination": "U_test_bot",
            "events": [
                {
                    "type": event_type,
                    "timestamp": 1718000000000,
                    "source": {"type": "group", "groupId": "C_round_trip"},
                }
            ],
        }
        response = await client.post(
            "/api/v1/webhook/line",
            json=payload,
            headers={"X-Line-Signature": "mock_signature"},
        )
        assert response.status_code == 200

    assert settings.LINE_GROUP_ID == "C_round_trip"
    assert "LINE_GROUP_ID=C_round_trip" in env_file.read_text(encoding="utf-8")
