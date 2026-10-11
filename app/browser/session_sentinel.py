import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.browser.auth_driver import auth_driver
from app.brokers.krungsri.session_health import session_file_info
from app.core.config import settings
from app.core.events import event_bus
from app.db.session import AsyncSessionLocal
from app.db.models import SessionLog
from app.services.line_service import line_service

logger = logging.getLogger(__name__)

# KSS-RCA-009: documented pre-market session check window (Bangkok time, Mon–Fri).
# Kept in sync with app/brokers/krungsri/PDCA_RETROSPECTIVE.md ("09:45 - 09:55 น.")
PREMARKET_WINDOW_START = (9, 45)
PREMARKET_WINDOW_END = (9, 55)


def bkk_now() -> datetime:
    """Current wall-clock time in Bangkok (UTC+7, no DST)."""
    return datetime.now(timezone.utc) + timedelta(hours=7)


def is_premarket_window(now_bkk: datetime) -> bool:
    """KSS-RCA-009: True inside 09:45–09:55 Bangkok on a weekday (Mon–Fri)."""
    if now_bkk.weekday() >= 5:
        return False
    start = now_bkk.replace(
        hour=PREMARKET_WINDOW_START[0], minute=PREMARKET_WINDOW_START[1],
        second=0, microsecond=0,
    )
    end = now_bkk.replace(
        hour=PREMARKET_WINDOW_END[0], minute=PREMARKET_WINDOW_END[1],
        second=59, microsecond=0,
    )
    return start <= now_bkk <= end


def seconds_until_premarket_window(now_bkk: datetime) -> float:
    """
    Seconds until the next weekday 09:45 Bangkok; 0.0 when already inside the window.

    Weekends roll forward to Monday. Used to cap the monitor sleep so the loop
    reliably lands inside the window instead of skipping over it.
    """
    if is_premarket_window(now_bkk):
        return 0.0
    start = now_bkk.replace(
        hour=PREMARKET_WINDOW_START[0], minute=PREMARKET_WINDOW_START[1],
        second=0, microsecond=0,
    )
    candidate = start if now_bkk < start else start + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return max(0.0, (candidate - now_bkk).total_seconds())


class SessionSentinel:
    """
    Background worker monitoring the Playwright browser session:
    - Periodically verifies session validity (Heartbeat)
    - Detects session expiration or logout redirects
    - Automatically attempts session restoration (Auto-Reconnect) during trading hours
    - Pushes SMS OTP request to LINE when 2FA is encountered
    - Caps reconnection at 3 attempts with Critical Alert escalation
    - Logs heartbeat and reconnect events to SQLite session_logs
    - Auto-closes session gracefully at EOD (16:35+ Bangkok time)
    """
    def __init__(self, interval_seconds: Optional[int] = None):
        self.interval_seconds = interval_seconds or getattr(settings, "SESSION_HEARTBEAT_INTERVAL", 1800)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self._reconnecting = False
        # Session-file transition watch (KSS-RCA-011): works with NO live tab / outside
        # trading hours, so an overnight drop is never silent. None = unobserved baseline.
        self._last_session_file_exists: Optional[bool] = None
        self._last_session_file_needs_login: Optional[bool] = None
        self._last_premarket_warn_date: Optional[str] = None

    async def start(self) -> None:
        """Starts the sentinel background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"SessionSentinel started (interval: {self.interval_seconds}s)")

    async def stop(self) -> None:
        """Stops the sentinel loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("SessionSentinel stopped.")

    async def _log_event(self, event_type: str, details: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                log_entry = SessionLog(event_type=event_type, details=details)
                db.add(log_entry)
                await db.commit()
        except Exception as e:
            logger.error(f"Sentinel failed to write session log: {e}")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._next_wait_seconds())
                if not self._running:
                    break

                # Session-file transition watch (KSS-RCA-011): deliberately NOT gated by
                # `auth_driver.is_authenticated` / a live tab / trading hours — a dropped
                # saved session must be surfaced proactively even at night.
                await self._check_session_file_transition()

                # KSS-RCA-009 pre-market readiness warning (weekdays 09:45–09:55 BKK).
                await self._check_premarket_warning()

                if auth_driver.is_authenticated and auth_driver.page:
                    await self._perform_health_check()
                
                # Check EOD shutdown (Market close at 16:35 Bangkok time UTC+7)
                await self._check_eod_schedule()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SessionSentinel loop: {e}", exc_info=True)

    def is_trading_hours(self) -> bool:
        """Checks if current time is within Thai trading hours (09:30 - 16:35 Bangkok time, Mon-Fri)."""
        bkk_now = datetime.now(timezone.utc) + timedelta(hours=7)
        if bkk_now.weekday() >= 5:  # Saturday or Sunday
            return False
        # Active between 09:30 and 16:35
        if bkk_now.hour == 9 and bkk_now.minute >= 30:
            return True
        if 10 <= bkk_now.hour < 16:
            return True
        if bkk_now.hour == 16 and bkk_now.minute < 35:
            return True
        return False

    def check_session_file_state(self) -> dict:
        """
        Browser-free snapshot of the saved Krungsri storage state (KSS-RCA-011).

        Delegates to the shared inspector so the sentinel, MCP health payload and
        preflight can never disagree about a saved session (Zero-Contradiction).
        """
        return session_file_info(
            getattr(settings, "SESSION_STATE_PATH", "data/session_state.json")
        )

    async def _alert_session_drop(self, title: str, detail: str) -> None:
        """
        Dual-channel proactive alert for a dropped/expired session.

        Uses both the LINE Messaging API (chat) and KDE Connect (phone push) per
        root_cause_and_escalation.md Invariant 4, and mirrors it onto the event bus
        so the console cockpit reflects the same state.
        """
        text = f"🔴 {title}\n{detail}"
        try:
            await line_service.push_message(text)
        except Exception as e:
            logger.error(f"Sentinel LINE alert failed: {e}")
        try:
            from app.services.kdeconnect_service import kdeconnect_service
            await kdeconnect_service.send_critical_alert(title, detail)
        except Exception as e:
            logger.error(f"Sentinel KDE Connect alert failed: {e}")
        try:
            await event_bus.publish_notification({"type": "SESSION_DROP_ALERT", "text": text})
        except Exception as e:
            logger.error(f"Sentinel event-bus alert failed: {e}")

    async def _check_session_file_transition(self) -> None:
        """
        Detects a session-file DROP or EXPIRY even when there is no live browser tab.

        `auth_driver.status` stays "DISCONNECTED" whenever no tab is attached, so the
        tab-based `_perform_health_check` can never notice that `data/session_state.json`
        vanished (the blindness that blocked Gate D). This watcher runs unconditionally.
        """
        info = self.check_session_file_state()
        exists = bool(info["exists"])
        needs_login = bool(info["needs_fresh_login"])

        prev_exists = self._last_session_file_exists
        prev_needs = self._last_session_file_needs_login

        # First observation = baseline only (avoid alert spam on process startup).
        if prev_exists is None:
            self._last_session_file_exists = exists
            self._last_session_file_needs_login = needs_login
            if not exists:
                await self._log_event(
                    "SESSION_FILE_ABSENT",
                    "No saved Krungsri session file at sentinel startup.",
                )
            return

        if prev_exists and not exists:
            reason = "Saved Krungsri session file disappeared (data/session_state.json missing)."
            logger.warning(f"SessionSentinel: {reason}")
            await self._log_event("SESSION_FILE_LOST", reason)
            await self._alert_session_drop(
                "Session TradeMan หายไปจากเครื่อง",
                f"{reason}\nต้อง login ใหม่ (มี SMS OTP) ก่อนเริ่มเทรด",
            )
        elif exists and needs_login and not prev_needs:
            age = info["age_hours"]
            reason = (
                f"Saved Krungsri session is EXPIRED/STALE "
                f"(age≈{age:.1f}h, verdict={info['reason']}). Fresh login required."
            )
            logger.warning(f"SessionSentinel: {reason}")
            await self._log_event("SESSION_FILE_EXPIRED", reason)
            await self._alert_session_drop(
                "Session TradeMan หมดอายุ",
                f"{reason}\nต้อง login ใหม่ (มี SMS OTP) ก่อนเริ่มเทรด",
            )

        self._last_session_file_exists = exists
        self._last_session_file_needs_login = needs_login

    def _next_wait_seconds(self) -> float:
        """
        Caps the monitor sleep so the loop reliably lands INSIDE the KSS-RCA-009
        pre-market window even when the heartbeat interval (default 1800s) is longer
        than the 10-minute window.

        Outside/before the window the normal interval is used; as 09:45 approaches the
        sleep shrinks to wake exactly at the window start.
        """
        try:
            remaining = seconds_until_premarket_window(bkk_now())
        except Exception:
            return float(self.interval_seconds)
        if remaining <= 0:
            # Already inside the window — re-check soon (alert is deduped per day).
            return float(min(self.interval_seconds, 60))
        return float(min(self.interval_seconds, max(1.0, remaining)))

    def check_premarket_readiness(self) -> dict:
        """
        Side-effect-free pre-market readiness verdict (KSS-RCA-009 / KSS-RCA-011).

        Shared by the sentinel loop, the console cockpit and any operator pre-flight.
        """
        info = self.check_session_file_state()
        now = bkk_now()
        return {
            "in_window": is_premarket_window(now),
            "seconds_until_window": seconds_until_premarket_window(now),
            "needs_fresh_login": bool(info["needs_fresh_login"]),
            "session_file_reason": info["reason"],
        }

    async def _check_premarket_warning(self) -> None:
        """
        Warns ONCE per Bangkok day, inside 09:45–09:55 on a weekday, when the saved
        Krungsri session needs a fresh login — so the operator can run the headed login
        (+2FA SMS OTP) BEFORE 10:00 instead of missing the tactical window (KSS-RCA-009).
        """
        now = bkk_now()
        if not is_premarket_window(now):
            return

        today = now.strftime("%Y-%m-%d")
        if self._last_premarket_warn_date == today:
            return

        info = self.check_session_file_state()
        if not info["needs_fresh_login"]:
            return

        self._last_premarket_warn_date = today
        detail = (
            "Pre-market session check (09:45): session TradeMan ยังต้อง login ใหม่ "
            f"(verdict={info['reason']}). "
            "กรุณา login แบบ headed + รับ SMS OTP ก่อน 10:00 เพื่อไม่ให้พลาดไม้ยุทธวิธี"
        )
        logger.warning(f"SessionSentinel pre-market warning: {detail}")
        await self._log_event("PREMARKET_SESSION_WARNING", detail)
        await self._alert_session_drop("เตรียม login ล่วงหน้าก่อนตลาดเปิด", detail)

    async def _perform_health_check(self) -> None:
        if self._reconnecting:
            return

        if auth_driver.status in ["AUTHENTICATING", "AWAITING_OTP", "NAVIGATING"]:
            return

        page = auth_driver.page
        session_lost = False
        reason = ""

        if not page or page.is_closed():
            session_lost = True
            reason = "Browser page was closed unexpectedly."
        else:
            try:
                current_url = page.url.lower()
                # If redirected to a login page, session has expired
                if "login" in current_url and "check_login" not in current_url:
                    session_lost = True
                    reason = f"Session expired; redirected to: {page.url}"
                else:
                    # Strict DOM validation: must see TradeMan account selector (#dropDownAccountPort)
                    account_el = await page.query_selector("#dropDownAccountPort, .account-selector")
                    if not account_el or not await account_el.is_visible():
                        session_lost = True
                        reason = f"Session expired: TradeMan account selector (#dropDownAccountPort) not visible in DOM at {page.url}"
                    else:
                        title = await page.evaluate("() => document.title")
                        auth_driver.last_heartbeat = datetime.now(timezone.utc)
                        self.reconnect_attempts = 0  # Healthy session resets counter
                        logger.debug(f"Sentinel Heartbeat OK: Title='{title}', URL='{page.url}'")
                        await self._log_event("HEARTBEAT_OK", f"Page responsive and account selector verified. Title: '{title}', URL: {page.url}")
                        return
            except Exception as e:
                session_lost = True
                reason = f"Heartbeat error: {str(e)}"

        if session_lost:
            auth_driver.status = "DISCONNECTED"
            logger.warning(f"SessionSentinel detected session lost: {reason}")
            await self._log_event("SESSION_LOST", reason)

            if self.is_trading_hours():
                await self.trigger_auto_reconnect()

    async def trigger_auto_reconnect(self) -> bool:
        """
        Executes automatic reconnection workflow:
        1. Attempt silent cookie recovery via verify_saved_session().
        2. If invalid, launches login() and pushes OTP Ref Code alert to LINE.
        3. Awaits OTP input via KDE Connect auto-capture or web console.
        4. Caps at 3 attempts with Critical Alert notification.
        """
        if self._reconnecting:
            logger.info("Auto-Reconnect is already in progress.")
            return False

        if auth_driver.status in ["AWAITING_OTP", "AUTHENTICATING", "NAVIGATING"]:
            logger.info(f"Skipping auto-reconnect; auth_driver is currently '{auth_driver.status}'")
            return False

        self._reconnecting = True
        try:
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                alert_text = (
                    "🚨 [CRITICAL ALERT] Session TradeMan หลุดระหว่างวันทำการ!\n"
                    f"ระบบพยายาม Auto-Reconnect ครบ {self.max_reconnect_attempts} ครั้งแล้วแต่ไม่สำเร็จ\n"
                    "⚠️ ระบบหยุดการต่ออัตโนมัติ กรุณาเข้าตรวจสอบ Browser หรือล็อกอินด้วยตนเอง"
                )
                logger.error(alert_text)
                await self._log_event("AUTO_RECONNECT_HALTED", f"Exceeded max attempts ({self.max_reconnect_attempts}).")
                await line_service.push_message(alert_text)
                await event_bus.publish_notification({
                    "type": "CRITICAL_SESSION_ALERT",
                    "text": alert_text
                })
                return False

            self.reconnect_attempts += 1
            logger.info(f"Starting Auto-Reconnect attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}...")
            await self._log_event("AUTO_RECONNECT_ATTEMPT", f"Attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")

            # Step 1: Silent cookie verification
            if await auth_driver.verify_saved_session():
                self.reconnect_attempts = 0
                restore_msg = "🟢 Session TradeMan ได้รับการฟื้นฟูอัตโนมัติสำเร็จผ่าน Cookies เดิมแล้ว"
                logger.info(restore_msg)
                await line_service.push_message(restore_msg)
                await event_bus.publish_notification({
                    "type": "SESSION_RESTORED",
                    "text": restore_msg
                })
                return True

            # Step 2: Fresh Login with Credentials
            login_task = asyncio.create_task(auth_driver.login())

            # Poll for Ref Code detection
            ref_code = None
            for _ in range(15):
                await asyncio.sleep(1.0)
                if auth_driver.status == "AWAITING_OTP" and auth_driver.current_ref:
                    ref_code = auth_driver.current_ref
                    break
                if auth_driver.is_authenticated:
                    break

            if ref_code:
                otp_prompt_msg = (
                    f"⚠️ Session TradeMan หลุดระหว่างวันทำการ!\n"
                    f"ระบบกำลัง Auto-Reconnect (ครั้งที่ {self.reconnect_attempts}/{self.max_reconnect_attempts})\n"
                    f"รหัสอ้างอิง: [Ref: {ref_code}]\n\n"
                    f"📲 กรุณาพิมพ์รหัส SMS OTP 6 หลักลงในแชท LINE นี้ เพื่อต่ออายุ Session"
                )
                logger.warning(f"Pushing OTP request to LINE: Ref={ref_code}")
                await line_service.push_message(otp_prompt_msg)
                await event_bus.publish_notification({
                    "type": "SESSION_OTP_REQUIRED",
                    "text": otp_prompt_msg,
                    "ref": ref_code
                })

            # Await login task completion
            login_res = await login_task
            is_success = False
            if hasattr(login_res, "success"):
                is_success = bool(login_res.success)
            elif isinstance(login_res, dict):
                is_success = bool(login_res.get("success"))

            if is_success or auth_driver.is_authenticated:
                self.reconnect_attempts = 0
                success_msg = "🟢 Auto-Reconnect สำเร็จ! Session TradeMan กลับมาออนไลน์และพร้อมเทรดตามปกติแล้ว"
                logger.info(success_msg)
                await line_service.push_message(success_msg)
                await event_bus.publish_notification({
                    "type": "SESSION_RESTORED",
                    "text": success_msg
                })
                return True
            else:
                logger.warning(f"Auto-Reconnect attempt {self.reconnect_attempts} failed: {login_res}")
                return False

        except Exception as e:
            logger.error(f"Error during Auto-Reconnect attempt {self.reconnect_attempts}: {e}")
            await self._log_event("AUTO_RECONNECT_ERROR", f"Attempt {self.reconnect_attempts} error: {str(e)}")
            return False
        finally:
            self._reconnecting = False

    async def _check_eod_schedule(self) -> None:
        """Closes browser session after Thai stock market close at 16:35+."""
        bkk_now = datetime.now(timezone.utc) + timedelta(hours=7)
        if bkk_now.weekday() < 5:  # Monday to Friday
            if bkk_now.hour == 16 and bkk_now.minute >= 35:
                if auth_driver.is_authenticated:
                    logger.info("EOD reached (16:35 Bangkok time). Performing scheduled EOD logout...")
                    await self._log_event("EOD_LOGOUT", "Scheduled market close logout triggered.")
                    await auth_driver.close()


# Global singleton sentinel
session_sentinel = SessionSentinel()
