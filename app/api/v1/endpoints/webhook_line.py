import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request, Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db
from app.core.security import verify_line_signature
from app.services.line_service import line_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _env_path() -> Path:
    """Locate the repo-root `.env` (the file pydantic-settings reads)."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[4] / ".env"


_last_seen_group_id: str | None = None
_last_seen_user_id: str | None = None


def _write_env_key(key: str, value: str) -> None:
    """
    Persist `KEY=value` into the repo `.env` atomically (single writer for all keys).

    LINE-RCA-003 + LINE-RCA-006: one code path serves both OTP push targets so the
    atomic-replace / never-fail-the-webhook guarantees cannot drift apart.
    """
    try:
        env_path = _env_path()
        lines = env_path.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        replaced = False
        for line in lines:
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out.append(f"{key}={value}")
        tmp = env_path.with_name(env_path.name + ".tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(tmp, env_path)
        logger.info(f"[LINE] {key} captured into {env_path} (OTP push target locked in).")
    except Exception as e:  # never fail the webhook because of a .env write
        logger.warning(f"[LINE] Could not persist {key} to .env: {e}")


def _persist_group_id(group_id: str) -> None:
    """
    Zero-touch onboarding: remember the LINE groupId the bot was invited into.

    Zero-Contradiction: `settings.LINE_GROUP_ID` is the single source of truth for
    the OTP push target. The value is only written when it is still empty, so an
    operator-set groupId is never silently overwritten. The in-process setting is
    updated immediately, so OTP pushes reach the group without restarting uvicorn.
    """
    global _last_seen_group_id
    if not group_id or group_id == _last_seen_group_id:
        return
    _last_seen_group_id = group_id
    logger.info(f"[LINE] source.groupId observed: {group_id}")

    if settings.LINE_GROUP_ID == group_id:
        return
    if settings.LINE_GROUP_ID:
        logger.info("[LINE] LINE_GROUP_ID already configured — leaving it untouched.")
        return

    settings.LINE_GROUP_ID = group_id
    _write_env_key("LINE_GROUP_ID", group_id)


def _persist_user_id(user_id: str) -> None:
    """
    LINE-RCA-006 (2026-10-08): 1:1 fallback capture — the `line_direct` channel.

    When the LINE Official Account is only a *friend* (1:1 chat) and is not inside a
    group — e.g. because `Allow bot to join group chats` is disabled in the Messaging
    API channel (LINE default, see LINE-RCA-005) — the OTP conversation happens in the
    1:1 chat. Such events carry `source.type="user"` + `source.userId` (U...) and NO
    `groupId`, so the group capture never fires and the relay stays `ready=false` even
    though OTP messages ARE arriving.

    The 1:1 chat is a valid push target: `line_service.push_message()` /
    `push_otp_request()` already fall back to `LINE_ADMIN_USER_ID` and the LINE push
    API accepts a userId in `to` exactly like a groupId.

    Guardrails:
      * only called for `source.type == "user"` events — a group event also carries a
        `userId`, but that is the *sender* (a group member), never the operator chat
      * never overwrites an operator-set value
      * `LINE_GROUP_ID` keeps precedence over this fallback (see otp_relay_readiness)
    """
    global _last_seen_user_id
    if not user_id or user_id == _last_seen_user_id:
        return
    _last_seen_user_id = user_id
    logger.info(f"[LINE] source.userId observed (1:1 chat): {user_id}")

    if settings.LINE_ADMIN_USER_ID == user_id:
        return
    if settings.LINE_ADMIN_USER_ID:
        logger.info("[LINE] LINE_ADMIN_USER_ID already configured — leaving it untouched.")
        return

    settings.LINE_ADMIN_USER_ID = user_id
    _write_env_key("LINE_ADMIN_USER_ID", user_id)


# LINE-RCA-008 (2026-10-08): lifecycle events must be able to *release* a captured target.
GROUP_RELEASE_EVENTS = {"leave"}        # the OA itself left / was removed from the group
USER_RELEASE_EVENTS = {"unfollow"}      # operator blocked the OA → the 1:1 chat is gone
# `memberLeft` = some OTHER member left the group: says nothing about the OA → never
# captured, never released (proven live: a `join` at 16:11:18 was followed by
# `memberLeft` + `leave` at 16:12:27, leaving .env pointing at a group the OA had left).


def _release_group_id(group_id: str) -> None:
    """
    LINE-RCA-008: the OA is no longer a member → drop the stale OTP push target.

    Live incident (2026-10-08): the bot joined a group at 16:11:18 (captured into `.env`)
    and left at 16:12:27. The capture write-guard only ever *sets* the value, so
    `.env` kept `LINE_GROUP_ID=Ccd…` → `group/summary` = 404 → push = "Failed to send
    messages" → OTP relay silently dead (gate reported ready). Releasing on `leave` makes
    the system self-healing: the stale target disappears and the 1:1 fallback can take over.
    """
    global _last_seen_group_id
    if not group_id or settings.LINE_GROUP_ID != group_id:
        return  # a different (operator-managed) group is configured — not ours to touch

    settings.LINE_GROUP_ID = None
    _last_seen_group_id = None  # allow a re-`join` of the same group to be re-captured
    _write_env_key("LINE_GROUP_ID", "")
    logger.warning(
        f"[LINE] OA left group {group_id[:3]}… — released stale LINE_GROUP_ID "
        "(OTP relay falls back to the 1:1 chat)"
    )


def _release_user_id(user_id: str) -> None:
    """LINE-RCA-008: operator unfollowed the OA → drop the stale 1:1 push target."""
    global _last_seen_user_id
    if not user_id or settings.LINE_ADMIN_USER_ID != user_id:
        return

    settings.LINE_ADMIN_USER_ID = None
    _last_seen_user_id = None  # allow a re-`follow` of the same user to be re-captured
    _write_env_key("LINE_ADMIN_USER_ID", "")
    logger.warning(
        "[LINE] OA was unfollowed — released stale LINE_ADMIN_USER_ID (1:1 relay target)"
    )


@router.post("/line")
async def receive_line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook endpoint for LINE Messaging API events (OTP responses, Quick Replies, Close commands).
    Validates X-Line-Signature unless in Simulation Mode.

    LINE-RCA-001 (2026-10-08): the LINE Console "Verify" button POSTs an EMPTY body
    carrying a valid signature. The previous `json.loads("")` raised → 400 → the console
    declared the webhook broken. Acknowledge the empty probe with HTTP 200 BEFORE parsing.
    """
    body_bytes = await request.body()

    # 1. Signature Verification (also covers the empty probe: HMAC-SHA256 of b"")
    if not verify_line_signature(body_bytes, x_line_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid LINE signature"
        )

    # 2. LINE Console verification ping — acknowledge without parsing
    if not body_bytes.strip():
        logger.info("[LINE] Webhook verify ping received (empty body) — acknowledged 200.")
        return {"status": "ok", "processed": 0, "results": [], "note": "verify_ping"}

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    events = payload.get("events", [])

    # 2b. LINE Console "Verify" / keep-alive payloads carry an EMPTY `events` array
    #     (different from the raw empty-body probe handled above). Acknowledge them
    #     explicitly AND log them: without this the request is invisible in the log
    #     and cannot be told apart from real group events.
    #     Proven 2026-10-08 (LINE-RCA-001 follow-up): a successful Console "Verify"
    #     only showed up as a bare `200 OK` from the LINE platform IPs.
    if not events:
        logger.info(
            "[LINE] Webhook acknowledged with 0 events (LINE Console verification / keep-alive)."
        )
        return {"status": "ok", "processed": 0, "results": [], "note": "verify_ping"}

    # Observability: log WHICH event types arrived and from WHICH source kind
    # ("user" = 1:1 chat, "group" = group chat, "room" = multi-user room) — but never
    # the ids or message contents. This is what makes a missing groupId diagnosable
    # from the log alone: `source=user` means the sender was in the 1:1 bot chat.
    summary = [
        {"type": e.get("type"), "source": (e.get("source") or {}).get("type")}
        for e in events
    ]
    logger.info(f"[LINE] Received {len(events)} event(s): {summary}")

    # 3. Zero-touch onboarding: capture / release the OTP push target straight from events.
    #    * group `join` / `message`  → `source.groupId` → `LINE_GROUP_ID` (line_group, preferred)
    #    * 1:1 `follow` / `message`  → `source.userId`  → `LINE_ADMIN_USER_ID` (line_direct)
    #    * group `leave`             → release LINE_GROUP_ID  (LINE-RCA-008, self-healing)
    #    * user  `unfollow`          → release LINE_ADMIN_USER_ID
    #    * group `memberLeft`        → ignore (another member left, not the OA)
    #    A group event ALSO carries `source.userId`, but that is the *sender* (a group
    #    member), never the operator chat — hence the `elif` and the `type == "user"` check.
    for event in events:
        event_type = (event.get("type") or "").lower()
        source = event.get("source") or {}
        group_id = source.get("groupId")
        user_id = source.get("userId")

        if event_type in GROUP_RELEASE_EVENTS and group_id:
            _release_group_id(group_id)
        elif event_type in USER_RELEASE_EVENTS and source.get("type") == "user" and user_id:
            _release_user_id(user_id)
        elif event_type == "memberleft":
            continue
        elif group_id:
            _persist_group_id(group_id)
        elif source.get("type") == "user" and user_id:
            _persist_user_id(user_id)

    results = await line_service.process_webhook_events(db, events)

    return {
        "status": "ok",
        "processed": len(results),
        "results": results
    }

