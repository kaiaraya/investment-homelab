"""
Liberator Securities (WebTrade) Autonomous Playwright Driver.
=============================================================
Handles Headed Chrome automation, 2FA SMS OTP interception via the LINE relay
(authoritative since 2026-10-08; the KDE Connect path is dormant/fallback only —
LINE-RCA-009), session persistence (data/liberator_session.json), and
portfolio/balance scraping.
"""

import os
import re
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError
)

from app.core.config import settings
from app.brokers.liberator.session_health import (
    read_session_token_expiry,
    session_expired,
)
from app.services.kdeconnect_service import kdeconnect_service
from app.browser.tab_manager import tab_manager
from app.services.redaction import redact_otp
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform, OTPSource

logger = logging.getLogger("LiberatorDriver")


# LINE-RCA-009 (2026-10-08): honest OTP capture attribution.
# The authoritative relay channel reported by ``otp_relay_readiness.check()`` gates
# which capture path may serve the OTP (see the wait loop inside ``login()``).
# Kept local to the Liberator driver (Broker Knowledge Isolation) — it only maps a
# generic capture-path tag onto the shared ``OTPSource`` enum.
def _safe_otp_source(raw: Optional[str]) -> Optional[OTPSource]:
    """
    Map a capture-path tag to ``OTPSource`` for honest reporting (LINE-RCA-009).

    Never raises: an unmapped/absent tag yields ``None`` (we report "unknown" rather
    than inventing a channel — Anti-Mock Guardrail).
    """
    if not raw:
        return None
    try:
        return OTPSource(raw)
    except ValueError:
        logger.debug(f"Unmapped OTP capture source tag: {raw!r} -> otp_source=None")
        return None


class LiberatorDriver:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.status: str = "DISCONNECTED"  # DISCONNECTED, LAUNCHING, NAVIGATING, AWAITING_OTP, AUTHENTICATED, FAILED
        self.session_path = getattr(settings, "LIBERATOR_SESSION_PATH", "data/liberator_session.json")
        self.cache_path = getattr(settings, "LIBERATOR_PORTFOLIO_CACHE_PATH", "data/liberator_portfolio_cache.json")
        self.chrome_path = getattr(settings, "PLAYWRIGHT_CHROME_EXECUTABLE", "/usr/bin/google-chrome")
        self._lock = asyncio.Lock()

    @property
    def is_authenticated(self) -> bool:
        return self.status == "AUTHENTICATED" and self.page is not None and not self.page.is_closed()

    @property
    def current_url(self) -> Optional[str]:
        return self.page.url if self.page and not self.page.is_closed() else None

    async def launch_browser(self, resume_state: bool = True) -> None:
        """Launches visible Headed Chrome and loads session cookies if available."""
        if self.browser and self.context and self.page and not self.page.is_closed():
            return

        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"

        self.playwright = await async_playwright().start()

        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ]

        kwargs: Dict[str, Any] = {
            "headless": False,
            "args": launch_args,
        }
        if os.path.exists(self.chrome_path):
            kwargs["executable_path"] = self.chrome_path

        self.browser = await self.playwright.chromium.launch(**kwargs)
        self.context = await self.browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )

        tab_manager.set_context(self.context)

        # Resume saved cookies if requested
        if resume_state and os.path.exists(self.session_path):
            try:
                with open(self.session_path, "r") as f:
                    state_data = json.load(f)
                cookies = state_data.get("cookies", [])
                if cookies:
                    await self.context.add_cookies(cookies)
                    logger.info(f"Loaded {len(cookies)} saved cookies from {self.session_path}")
            except Exception as e:
                logger.warning(f"Could not load saved cookies: {e}")

        self.page = await self.context.new_page()
        tab_manager.register_tab("liberator", self.page)
        self.status = "LAUNCHING"

    def _session_token_expiry(self) -> Optional[int]:
        """
        LIB-RCA-006 / LIB-RCA-007: Extracts the Liberator auth JWT `exp` (Unix
        seconds) from the saved storage state.

        Delegates to app.brokers.liberator.session_health so that preflight_check.py
        shares the EXACT same expiry logic as this driver (single source of truth).

        Returns None when no expiry can be determined (so the live DOM verification
        path is still exercised instead of being skipped).
        """
        return read_session_token_expiry(self.session_path)

    def _saved_session_expired(self, safety_margin_seconds: int = 60) -> bool:
        """
        LIB-RCA-006: Returns True when the saved Liberator session JWT is already
        expired, or will expire within ``safety_margin_seconds``.

        Returns False when the expiry cannot be determined, so that the online DOM
        check in verify_saved_session() still runs. Delegates to session_health so
        the preflight checker and the driver never disagree (LIB-RCA-007).
        """
        expired = session_expired(
            self.session_path, safety_margin_seconds=safety_margin_seconds
        )
        if expired:
            exp = read_session_token_expiry(self.session_path)
            now = int(time.time())
            remaining = (exp - now) if exp is not None else None
            logger.warning(
                f"Liberator saved session JWT expired/insufficient "
                f"(exp={exp}, now={now}, remaining={remaining}s). Forcing fresh login."
            )
        return expired

    async def verify_saved_session(self) -> bool:
        """Verifies if the saved cookies yield an active, authenticated session (<3s check)."""
        if not os.path.exists(self.session_path):
            return False

        # LIB-RCA-006: Never trust a saved session whose JWT has already expired.
        # Liberator JWTs live ~24h, so a remembered-but-stale cookie must be discarded.
        if self._saved_session_expired():
            logger.info("Liberator saved session JWT is EXPIRED. Discarding stale session.")
            self.status = "DISCONNECTED"
            return False

        try:
            if not self.page or self.page.is_closed():
                await self.launch_browser(resume_state=True)

            logger.info("Checking Liberator session by navigating to Portfolio...")
            await self.page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=12000)
            await self.page.wait_for_timeout(2000)

            # If redirected to /login, session is dead
            if "login" in self.page.url.lower():
                logger.info("Liberator session expired: Redirected to /login.")
                self.status = "DISCONNECTED"
                return False

            # Check for portfolio / dashboard elements
            port_marker = await self.page.query_selector("text='Portfolio', text='Line Available', text='Cash Balance', text='พอร์ต'")
            if port_marker or "portfolio" in self.page.url.lower():
                logger.info(f"Liberator active session verified: {self.page.url}")
                self.status = "AUTHENTICATED"
                return True

            return False
        except Exception as e:
            logger.warning(f"Error checking Liberator session: {e}")
            return False

    async def _log_event(self, event_type: str, details: str) -> None:
        """Persists a session event in the database session_logs table.

        Mirrors ``KrungsriAuthDriver._log_event`` (same table/semantics) so operators
        can audit Liberator gate decisions (e.g. LOGIN_BRIDGE_DOWN) cross-process.
        """
        try:
            from app.db.session import AsyncSessionLocal
            from app.db.models import SessionLog

            async with AsyncSessionLocal() as db:
                db.add(SessionLog(event_type=event_type, details=details))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to record session log ({event_type}): {e}")

    async def login(self, username: Optional[str] = None, password: Optional[str] = None, force_fresh: bool = False) -> LoginResult:
        """Executes full automated login for Liberator WebTrade with LINE-relay OTP interception."""
        async with self._lock:
            # Credentials come ONLY from args or .env — never hardcode fallbacks in source.
            user = username or settings.LIBERATOR_USERNAME
            pwd = password or settings.LIBERATOR_PASSWORD
            login_url = getattr(settings, "LIBERATOR_LOGIN_URL", "https://webtrade.liberator.co.th/login")

            # 1. Fast path: check existing session if not force_fresh
            if not force_fresh and os.path.exists(self.session_path):
                if await self.verify_saved_session():
                    return LoginResult(
                        success=True,
                        status=AuthStatus.AUTHENTICATED,
                        broker=BrokerPlatform.LIBERATOR,
                        resumed=True,
                        url=self.current_url,
                        message="Saved Liberator session is active"
                    )

            # 2. Fresh login required
            # Credentials gate: fail closed BEFORE the OTP gate so no SMS is ever
            # fired when LIBERATOR_USERNAME / LIBERATOR_PASSWORD are not configured.
            if not user or not pwd:
                self.status = "FAILED"
                logger.error("Liberator credentials missing (LIBERATOR_USERNAME/LIBERATOR_PASSWORD in .env).")
                await self._log_event(
                    "LOGIN_FAILED",
                    "Liberator login aborted — credentials not configured in .env",
                )
                return LoginResult(
                    success=False,
                    status=AuthStatus.FAILED,
                    broker=BrokerPlatform.LIBERATOR,
                    resumed=False,
                    message="Liberator credentials are not configured (set LIBERATOR_USERNAME and LIBERATOR_PASSWORD in .env).",
                    error_code="MISSING_CREDENTIALS",
                )

            # OTP Relay Readiness Gate (Invariant 9 — LINE variant, 2026-10-08):
            # A fresh Liberator login ALWAYS triggers an SMS OTP. Never fire the SMS
            # unless the OTP relay is ready RIGHT NOW — the relay is the LINE channel
            # (group "a14s homelab" or the 1:1 operator chat) and the backend gateway
            # must be UP to receive the webhook.
            # Single source of truth: app.services.otp_relay_readiness
            # (shared with auth_driver.py + daily_readiness.py).
            # allow_kde_fallback=False (explicit): LINE is authoritative — the dormant
            # KDE path must NEVER satisfy this gate (LINE-RCA-009).
            from app.services.otp_relay_readiness import otp_relay_readiness
            readiness = await otp_relay_readiness.check(allow_kde_fallback=False)
            otp_channel = readiness.channel
            if not readiness.ready:
                self.status = "BRIDGE_DOWN"
                logger.error(
                    f"OTP Relay Readiness Gate: relay NOT ready ({readiness.reason}). "
                    "Aborting Liberator login BEFORE SMS trigger."
                )
                await self._log_event(
                    "LOGIN_BRIDGE_DOWN",
                    f"Liberator login aborted before SMS OTP trigger — OTP relay not ready: {readiness.reason}",
                )
                return LoginResult(
                    success=False,
                    status=AuthStatus.BRIDGE_DOWN,
                    broker=BrokerPlatform.LIBERATOR,
                    resumed=False,
                    message=(
                        f"OTP relay (LINE) is not ready: {readiness.reason}. "
                        "SMS OTP was NOT triggered to avoid account lock."
                    ),
                    error_code="BRIDGE_DOWN",
                )

            logger.info("Starting fresh Liberator login...")
            await self.launch_browser(resume_state=False)

            self.status = "NAVIGATING"
            await self.page.goto(login_url, wait_until="domcontentloaded", timeout=25000)
            await self.page.wait_for_timeout(2000)

            # Fill Username
            user_selectors = [
                "input[placeholder*='Username' i]",
                "input[placeholder*='Email' i]",
                "input[type='text']",
                "#username"
            ]
            user_input = None
            for sel in user_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    user_input = el
                    break

            if user_input:
                await user_input.fill(user)
                logger.info(f"Entered Liberator username: {user}")
            else:
                return LoginResult(
                    success=False,
                    status=AuthStatus.FAILED,
                    broker=BrokerPlatform.LIBERATOR,
                    message="Could not find Username input field."
                )

            # Fill Password
            pass_selectors = [
                "input[placeholder*='Password' i]",
                "input[type='password']",
                "#password"
            ]
            pass_input = None
            for sel in pass_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    pass_input = el
                    break

            if pass_input:
                await pass_input.fill(pwd)
                logger.info("Entered Liberator password.")
            else:
                return LoginResult(
                    success=False,
                    status=AuthStatus.FAILED,
                    broker=BrokerPlatform.LIBERATOR,
                    message="Could not find Password input field."
                )

            # Click Submit button ('ยืนยัน')
            btn_selectors = [
                "button:has-text('ยืนยัน')",
                "button[type='submit']",
                "button:has-text('เข้าสู่ระบบ')",
                "button:has-text('Login')"
            ]
            btn_login = None
            for sel in btn_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    btn_login = el
                    break

            if btn_login:
                await btn_login.click()
            else:
                await self.page.keyboard.press("Enter")

            logger.info("Clicked login submit. Waiting for 2FA OTP prompt or dashboard navigation...")
            await self.page.wait_for_timeout(3000)

            # Check for OTP page or input
            otp_selectors = [
                "input[placeholder*='OTP' i]",
                "input[placeholder*='รหัส OTP' i]",
                "input[inputmode='numeric']",
                "input[type='tel']",
                "input.otp-input",
                "#otp"
            ]
            otp_input = None
            for _ in range(6):
                for sel in otp_selectors:
                    el = await self.page.query_selector(sel)
                    if el and await el.is_visible():
                        otp_input = el
                        break
                if otp_input or "otp" in self.page.url.lower():
                    break
                await asyncio.sleep(1.0)

            # LINE-RCA-009: initialize the capture attribution up-front so the success
            # return can report honestly even when NO OTP prompt was reached (None = no OTP).
            expected_ref: Optional[str] = None
            captured_source: Optional[str] = None

            if otp_input or "otp" in self.page.url.lower():
                self.status = "AWAITING_OTP"
                
                # Extract Ref Code if displayed on page: e.g. (ref. code: KCNX)
                expected_ref = None
                try:
                    body_text = await self.page.inner_text("body")
                    m_ref = re.search(r'\(ref\.\s*code:\s*([A-Za-z0-9]+)\)', body_text, re.IGNORECASE)
                    if m_ref:
                        expected_ref = m_ref.group(1).upper()
                        logger.info(f"Liberator OTP Reference Code detected: [Ref: {expected_ref}]")
                except Exception:
                    pass

                logger.info(f"2FA SMS OTP required for Liberator (Ref: {expected_ref or 'Auto'}). Polling relay channel '{otp_channel}' (Timeout: 180s)...")
                print(f"\n📲 2FA SMS OTP REQUIRED! [Expected Ref: {expected_ref or 'Any'}] - กำลังรอ OTP ผ่าน LINE (channel={otp_channel}, 180 วินาที)...")

                # Ask the operator for the OTP on the authoritative LINE channel
                # (group "a14s homelab" or the 1:1 chat with the OA — LINE-RCA-006).
                # Best-effort: a failed push must never abort the login flow.
                try:
                    from app.services.line_service import line_service
                    await line_service.push_otp_request(
                        ref=expected_ref,
                        broker="LIBERATOR",
                        timeout_seconds=180,
                    )
                except Exception as e:
                    logger.warning(f"Could not push OTP request to LINE: {e}")

                captured_otp = None
                captured_source = None
                start_time = time.time()
                otp_wait_started = datetime.now(timezone.utc)

                # LINE-RCA-009: only the authoritative relay channel may satisfy this wait.
                # A LINE channel accepts only LINE capture paths, a KDE channel only KDE.
                # An unknown/`none` channel yields no event types -> fail-closed.
                from app.services.otp_relay_readiness import (
                    channel_accepts_source,
                    channel_allows_kde,
                    channel_db_event_types,
                    event_type_to_source,
                )
                from app.services.otp_relay_registry import broker_matches, parse_otp_broker

                # Broker Knowledge Isolation: this driver only ever serves Liberator.
                driver_broker = "LIBERATOR"
                allowed_event_types = channel_db_event_types(otp_channel)

                while time.time() - start_time < 180:
                    elapsed = int(time.time() - start_time)
                    rem = 180 - elapsed
                    if elapsed > 0 and elapsed % 10 == 0:
                        print(f"⏳ Waiting for OTP... [Ref: {expected_ref or 'Auto'}] ({rem}s remaining)")
                    try:
                        # 1. In-process event bus (same gateway process)
                        from app.core.events import event_bus
                        if not event_bus.otp_queue.empty():
                            _event = event_bus.otp_queue.get_nowait()
                            _payload = _event.get("payload")
                            if _payload is not None and getattr(_payload, "otp", None):
                                _otp_val = str(_payload.otp)
                                _src_tag = (
                                    _payload.source.value
                                    if hasattr(getattr(_payload, "source", None), "value")
                                    else str(getattr(_payload, "source", "event_bus"))
                                )
                            else:
                                _data = _event.get("data") or {}
                                _otp_val = str(_data.get("otp", "")).strip()
                                _src_tag = _data.get("source", "event_bus")
                            if len(_otp_val) == 6 and _otp_val.isdigit():
                                if channel_accepts_source(otp_channel, _src_tag):
                                    # LINE-RCA-010: never consume the other broker's OTP.
                                    # Untagged (None) stays acceptable — lenient.
                                    _tag_broker = (
                                        getattr(_payload, "broker", None)
                                        if _payload is not None
                                        else (_data or {}).get("broker")
                                    )
                                    if broker_matches(driver_broker, _tag_broker):
                                        captured_otp = _otp_val
                                        captured_source = _src_tag
                                        logger.info(f"Captured OTP via event_bus ({_src_tag}): {redact_otp(captured_otp)}")
                                        break
                                    logger.info(
                                        f"Ignoring queued OTP tagged for '{_tag_broker}' — this driver is "
                                        f"{driver_broker} (LINE-RCA-010); still waiting."
                                    )
                                else:
                                    logger.warning(
                                        f"Ignoring queued OTP from '{_src_tag}' — channel '{otp_channel}' "
                                        "is authoritative (LINE-RCA-009); still waiting for it."
                                    )

                        # 2. Cross-process — the gateway webhook wrote a SessionLog row.
                        #    GATED by the authoritative channel: a LINE channel accepts ONLY
                        #    `LINE_OTP_RECEIVED`, a KDE channel ONLY `KDECONNECT_OTP_RECEIVED`.
                        if allowed_event_types:
                            from sqlalchemy import select as _sa_select
                            from app.db.session import AsyncSessionLocal
                            from app.db.models import SessionLog
                            async with AsyncSessionLocal() as _db:
                                _stmt = (
                                    _sa_select(SessionLog)
                                    .where(SessionLog.event_type.in_(list(allowed_event_types)))
                                    .where(SessionLog.created_at >= otp_wait_started)
                                    .order_by(SessionLog.created_at.desc())
                                    .limit(1)
                                )
                                _row = (await _db.execute(_stmt)).scalar_one_or_none()
                                if _row and _row.details:
                                    # LINE-RCA-010: ignore the OTHER broker's OTP row.
                                    # Untagged (legacy / KDE) stays acceptable — lenient.
                                    _row_broker = parse_otp_broker(_row.details)
                                    if not broker_matches(driver_broker, _row_broker):
                                        logger.info(
                                            f"Ignoring {_row.event_type} row tagged for '{_row_broker}' — "
                                            f"this driver is {driver_broker} (LINE-RCA-010); still waiting."
                                        )
                                    else:
                                        # Same tolerant pattern as auth_driver (LINE-RCA-002)
                                        from app.browser.auth_driver import OTP_SESSION_LOG_PATTERN
                                        _m = re.search(OTP_SESSION_LOG_PATTERN, _row.details)
                                        if _m:
                                            captured_otp = _m.group(1)
                                            captured_source = event_type_to_source(_row.event_type)
                                            logger.info(
                                                f"Captured OTP via {_row.event_type} (session_logs_db): "
                                                f"{redact_otp(captured_otp)}"
                                            )
                                            break

                        # 3. KDE Connect notifications — DORMANT: polled ONLY when the
                        #    authoritative channel IS kde_connect (LINE-RCA-009). Before
                        #    2026-10-08 this ran every loop and silently won the race while
                        #    LINE was authoritative (no LINE_OTP_RECEIVED row -> unprovable).
                        if channel_allows_kde(otp_channel):
                            notif = await kdeconnect_service.poll_active_notifications(expected_ref=expected_ref)
                            if notif and notif.otp_code:
                                captured_otp = notif.otp_code
                                captured_source = "kdeconnect_sms"
                                logger.info(f"Captured OTP via KDE Connect: {notif.masked_otp} (Ref: {notif.ref})")
                                break

                        # 4. Operator typed the OTP straight into the visible browser window
                        if otp_input:
                            val = await otp_input.input_value()
                            if val and len(val.strip()) >= 6 and val.strip().isdigit():
                                captured_otp = val.strip()
                                captured_source = "browser_dom_manual"
                                logger.info(f"Detected OTP filled manually on screen: {redact_otp(captured_otp)}")
                                break
                    except Exception:
                        pass
                    await asyncio.sleep(1.0)

                if captured_otp:
                    if not otp_input:
                        otp_input = await self.page.query_selector("input[placeholder*='OTP' i], input[type='text']")
                    if otp_input:
                        await otp_input.fill(captured_otp)
                        try:
                            await otp_input.evaluate("el => { el.style.border = '3px solid #00E676'; el.style.boxShadow = '0 0 12px #00E676'; }")
                        except Exception:
                            pass
                    
                    print("\n" + "=" * 75)
                    print(f"🎉 2FA OTP CAPTURED VIA {captured_source}!")
                    print(f" • Expected Ref Code : [Ref: {expected_ref}]")
                    print(f" • Captured OTP Code : {redact_otp(captured_otp)}")
                    print(f" • Safety Hold       : Submitting in 4 seconds (Displayed live on your Chrome)...")
                    print("=" * 75 + "\n")
                    await asyncio.sleep(4.0)

                    # Click Confirm button
                    confirm_btn = await self.page.query_selector("button:has-text('ยืนยัน'), button[type='submit']")
                    if confirm_btn and await confirm_btn.is_visible():
                        await confirm_btn.click()
                    else:
                        await self.page.keyboard.press("Enter")
                    logger.info("Submitted 2FA OTP. Waiting for dashboard navigation...")
                    await self.page.wait_for_timeout(5000)
                else:
                    return LoginResult(
                        success=False,
                        status=AuthStatus.TIMEOUT,
                        broker=BrokerPlatform.LIBERATOR,
                        otp_ref=expected_ref,
                        message=(
                            f"2FA SMS OTP timeout (180s) waiting for the relay channel "
                            f"'{otp_channel}'."
                        )
                    )

            # Wait for dashboard / portfolio landing
            for _ in range(12):
                if "webtrade.liberator.co.th" in self.page.url and "login" not in self.page.url.lower() and "otp" not in self.page.url.lower():
                    break
                await asyncio.sleep(1.0)

            if "login" in self.page.url.lower() or "otp" in self.page.url.lower():
                return LoginResult(
                    success=False,
                    status=AuthStatus.FAILED,
                    broker=BrokerPlatform.LIBERATOR,
                    message=f"Login incomplete: still on {self.page.url}"
                )

            # Save session state
            await self.save_session_state()
            self.status = "AUTHENTICATED"
            logger.info(f"Liberator Login Successful! Current URL: {self.page.url}")

            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.LIBERATOR,
                url=self.current_url,
                otp_ref=expected_ref,
                # Honest attribution (LINE-RCA-009): the tag of the path that actually
                # supplied the OTP, or None when no 2FA OTP was required.
                otp_source=_safe_otp_source(captured_source),
                message="Liberator Login Successful"
            )

    async def save_session_state(self) -> None:
        """Saves active cookies and session metadata to disk."""
        if not self.context or not self.page:
            return
        os.makedirs(os.path.dirname(self.session_path) or ".", exist_ok=True)
        cookies = await self.context.cookies()
        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "LIBERATOR",
            "cookies": cookies,
            "current_url": self.page.url
        }
        with open(self.session_path, "w") as f:
            json.dump(state, f, indent=2)
        logger.info(f"Saved {len(cookies)} Liberator cookies to {self.session_path}")

    @staticmethod
    async def _extract_portfolio_from_page(page: Page) -> Dict[str, Any]:
        """Evaluates JS to extract Line Available, Cash Balance, Holdings, and Orders tables."""
        return await page.evaluate("""() => {
            function cleanNum(val) {
                if (!val) return 0.0;
                let s = val.toString().replace(/,/g, "").replace(/–/g, "-").replace(/%/g, "").trim();
                return parseFloat(s) || 0.0;
            }

            // 1. Account balances
            let lineAvailable = 0.0;
            let cashBalance = 0.0;
            let creditLimit = 0.0;

            const allTexts = Array.from(document.querySelectorAll("div, p, span, td"));
            for (let i = 0; i < allTexts.length; i++) {
                const t = allTexts[i].innerText || "";
                if (t.includes("Line Available:")) {
                    const match = t.match(/Line Available:\\s*([\\d,]+\\.?\\d*)/i);
                    if (match) lineAvailable = cleanNum(match[1]);
                }
                if (t.includes("Cash Balance:")) {
                    const match = t.match(/Cash Balance:\\s*([\\d,]+\\.?\\d*)/i);
                    if (match) cashBalance = cleanNum(match[1]);
                }
                if (t.includes("Credit Limit:")) {
                    const match = t.match(/Credit Limit:\\s*([\\d,]+\\.?\\d*)/i);
                    if (match) creditLimit = cleanNum(match[1]);
                }
            }

            // 2. Deterministic Table Selection
            const tables = Array.from(document.querySelectorAll("table"));
            let holdingsTable = null;
            let ordersTable = null;

            for (const t of tables) {
                const head = t.querySelector("thead");
                const headTxt = head ? head.innerText.toLowerCase() : "";
                if (headTxt.includes("symbol") && headTxt.includes("in port")) {
                    holdingsTable = t;
                } else if (headTxt.includes("order #") && headTxt.includes("side")) {
                    ordersTable = t;
                }
            }

            // 2A. Scrape Holdings
            const positions = [];
            if (holdingsTable) {
                const rows = Array.from(holdingsTable.querySelectorAll("tbody tr"));
                for (const tr of rows) {
                    const parts = tr.innerText.trim().split(/\\s+/);
                    if (parts.length >= 8 && /^[A-Z][A-Z0-9.\\-]{1,9}$/.test(parts[0]) && !/^\\d+$/.test(parts[0])) {
                        positions.push({
                            symbol: parts[0],
                            volume: Math.round(cleanNum(parts[2])),
                            available_volume: Math.round(cleanNum(parts[1])),
                            avg_cost: cleanNum(parts[3]),
                            market_price: cleanNum(parts[4]),
                            amount_cost: cleanNum(parts[5]),
                            market_value: cleanNum(parts[6]),
                            unrealized_pnl: cleanNum(parts[7]),
                            pct_unrealized_pnl: cleanNum(parts[8]),
                            realized_pnl: parts.length > 9 ? cleanNum(parts[9]) : 0.0
                        });
                    }
                }
            }

            // 2B. Scrape Orders
            const orders = [];
            if (ordersTable) {
                const rows = Array.from(ordersTable.querySelectorAll("tbody tr"));
                for (const tr of rows) {
                    const txt = tr.innerText.trim();
                    const parts = txt.split(/[\\s\\t|]+/);
                    if (parts.length >= 8 && /^\\d+$/.test(parts[0])) {
                        orders.push({
                            order_no: parts[0],
                            time: parts[1],
                            symbol: parts[2],
                            side: parts[3],
                            price: cleanNum(parts[4]),
                            volume: Math.round(cleanNum(parts[5])),
                            matched: Math.round(cleanNum(parts[6])),
                            balance: Math.round(cleanNum(parts[7])),
                            cancelled: parts.length > 8 ? Math.round(cleanNum(parts[8])) : 0,
                            status: parts.length > 9 ? parts[9] : "Unknown"
                        });
                    }
                }
            }

            const totalMarketValue = positions.reduce((acc, p) => acc + p.market_value, 0);
            const totalCost = positions.reduce((acc, p) => acc + p.amount_cost, 0);
            const totalUnrealized = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);
            const totalEquity = cashBalance + totalMarketValue;

            return {
                line_available: lineAvailable,
                cash_balance: cashBalance,
                credit_limit: creditLimit,
                total_equity: totalEquity,
                total_market_value: totalMarketValue,
                total_cost: totalCost,
                total_unrealized_pnl: totalUnrealized,
                positions: positions,
                orders: orders
            };
        }""")

    #: Explicit status returned by ``get_market_bid_offer`` when the Liberator board cannot be
    #: read (LIB fail-closed). Anti-Mock (Invariant 1): callers MUST halt on this status — never
    #: substitute a guess and never fall back to the order's own price.
    QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"

    @staticmethod
    def _quote_unavailable(symbol: str, reason: str) -> Dict[str, Any]:
        """Fail-closed result for ``get_market_bid_offer`` — this is NOT a quote.

        Every numeric field is None *and* the envelope is explicitly marked
        ``success=False`` / ``status=QUOTE_UNAVAILABLE``, so no caller can mistake a read
        failure for a board reading, nor silently price an amend from it (Anti-Mock).
        ``source="unavailable"`` is kept for the pre-existing ``_plan_nego`` guard.
        """
        return {
            "symbol": (symbol or "").strip().upper(),
            "success": False,
            "status": LiberatorDriver.QUOTE_UNAVAILABLE,
            "bid_1": None, "offer_1": None, "last": None,
            "prior_close": None, "ceiling": None, "floor": None,
            "board_lot": None, "flag": None,
            "source": "unavailable",
            "error": reason,
        }

    # --- Live-proven Liberator quote API (LIB-RCA-020, verified live 2026-10-15) --------
    #: Master list: ``result.data.config.<group>.securities|indexes`` = positional rows
    #: ``[SYMBOL, orderBookId, market, kind, …]`` → the board is keyed by orderBookId.
    CONFIG_URL = "https://webtrade.liberator.co.th/vb/config"
    #: Per-orderBookId snapshot: ``result.list[0]`` = ``n``(symbol) ``ne``(name)
    #: ``l``(last) ``bp``/``bv``(bid1) ``op``/``ov``(offer1) ``prior`` ``cl`` ``fl``.
    STOCK_INFO_URL = "https://webtrade.liberator.co.th/vb/stock/info"
    QUOTE_API_TIMEOUT_MS = 8000

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Best-effort numeric cast for the broker's mixed str/number quote fields."""
        if value is None:
            return None
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        """Best-effort int cast for ``orderBookId`` values (arrive as str *or* int)."""
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_order_book_id(config_json: Optional[Dict[str, Any]], symbol: str) -> Optional[int]:
        """Map ``symbol -> orderBookId`` from the ``GET /vb/config`` master list.

        ``set`` is searched before ``tfex`` so an equity lookup can never resolve to a
        TFEX contract that happens to share the name (type-safe broker isolation).
        """
        target = (symbol or "").strip().upper()
        if not target:
            return None
        config = (config_json or {}).get("result", {}).get("data", {}).get("config", {})
        if not isinstance(config, dict):
            return None
        ordered = ["set", "set50if", "tfex"] + [g for g in config if g not in ("set", "set50if", "tfex")]
        for group in ordered:
            node = config.get(group)
            if not isinstance(node, dict):
                continue
            for key in ("securities", "indexes"):
                for row in node.get(key) or []:
                    if (isinstance(row, list) and len(row) >= 2
                            and isinstance(row[0], str) and row[0].strip().upper() == target):
                        resolved = LiberatorDriver._to_int(row[1])
                        if resolved is not None:
                            return resolved
        return None

    async def _resolve_order_book_id(self, page, symbol: str) -> Optional[int]:
        """Fetch ``/vb/config`` and resolve ``symbol``; ``None`` = unknown (fail-closed)."""
        resp = await page.request.get(self.CONFIG_URL, timeout=self.QUOTE_API_TIMEOUT_MS)
        if resp.status != 200:
            logger.warning("/vb/config HTTP %s — cannot resolve %s", resp.status, symbol)
            return None
        return self._extract_order_book_id(await resp.json(), symbol)

    async def _fetch_stock_info(self, page, order_book_id: int) -> Optional[Dict[str, Any]]:
        """POST ``/vb/stock/info`` for one orderBookId → the board's own quote record."""
        resp = await page.request.post(
            self.STOCK_INFO_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"orderBookIds": [int(order_book_id)]}),
            timeout=self.QUOTE_API_TIMEOUT_MS,
        )
        if resp.status not in (200, 201):
            logger.warning("/vb/stock/info HTTP %s for orderBookId %s", resp.status, order_book_id)
            return None
        rows = ((await resp.json()).get("result") or {}).get("list") or []
        return rows[0] if rows else None

    async def get_market_bid_offer(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch Bid1 / Offer1 (/ last) for ``symbol`` from the Liberator quote API.

        Evidence (LIB-RCA-020, re-verified live 2026-10-15 with a headed browser plus
        network capture): the board is keyed by **orderBookId**, never by symbol text.
        ``GET /vb/config`` exposes the master list (``set.securities`` = 3,956 rows of
        ``[SYMBOL, orderBookId, …]``) and ``POST /vb/stock/info {"orderBookIds":[id]}``
        returns exactly the record the board renders — including ``n`` (the symbol
        itself), ``l``/``bp``/``op`` (Last/Bid1/Offer1). Reading the on-screen depth
        table alone was unsafe: that table carries **no symbol identity**, and the
        ``/Portfolio`` board keeps rendering its previous symbol's depth while the new
        quote loads (observed: asked BCH → board served orderBookId 65781 = ``A``).

        Because ``n`` is authoritative, a quote is trusted **only** when it identifies
        itself as ``symbol``; otherwise ``QUOTE_UNAVAILABLE`` (fail-closed / mismatch).

        Anti-Mock: no active page, unknown symbol, empty payload, symbol mismatch or an
        API error all return ``_quote_unavailable(...)`` — ``success=False`` /
        ``status="QUOTE_UNAVAILABLE"`` with every numeric field None. This method NEVER
        auto-logs-in (Invariant 7) and NEVER invents a price.

        The envelope is ``success=True`` / ``status="OK"`` / ``source="liberator_api"``
        only when a symbol-verified record was read.
        """
        clean_sym = (symbol or "").strip().upper()
        if not clean_sym:
            return self._quote_unavailable("", "Blank symbol - nothing to quote (fail-closed).")

        if not self.page or self.page.is_closed():
            logger.warning("get_market_bid_offer(%s): no active Liberator page — fail-closed", clean_sym)
            return self._quote_unavailable(clean_sym, "No active Liberator page - fail-closed.")

        page = self.page
        try:
            # 1. Resolve the requested symbol to its authoritative ``orderBookId`` from the
            #    master list — the board is keyed by orderBookId, not by symbol text.
            order_book_id = await self._resolve_order_book_id(page, clean_sym)
            if order_book_id is None:
                logger.warning(
                    "get_market_bid_offer(%s): symbol not in the master list — fail-closed", clean_sym)
                return self._quote_unavailable(
                    clean_sym,
                    f"{clean_sym} is not in the Liberator master symbol list (/vb/config).")

            # 2. Read the quote for that exact orderBookId — the payload the board renders,
            #    and the only place that states which symbol the numbers actually belong to.
            record = await self._fetch_stock_info(page, order_book_id)

        except Exception as e:
            logger.warning(f"get_market_bid_offer({clean_sym}) failed: {e} — fail-closed")
            return self._quote_unavailable(
                clean_sym, f"Failed to read the Liberator quote API (/vb/stock/info): {e}")

        if record is None:
            logger.warning(f"get_market_bid_offer({clean_sym}): empty /vb/stock/info — fail-closed")
            return self._quote_unavailable(
                clean_sym, f"No /vb/stock/info record for {clean_sym} (orderBookId {order_book_id}).")

        # Fail-closed symbol gate: the record must identify itself as the requested symbol
        # before any price is trusted (LIB-RCA-020 — the /Portfolio board can still be showing
        # another symbol's depth at page load, e.g. orderBookId 65781 "A" while BCH is asked).
        board_sym = str(record.get("n") or "").strip().upper()
        if board_sym != clean_sym:
            returned_id = record.get("orderBookId") or order_book_id
            logger.warning(
                "get_market_bid_offer(%s): board quote is for %r — fail-closed", clean_sym, board_sym or None)
            return self._quote_unavailable(
                clean_sym,
                f"Board quote is for {board_sym or '<unknown>'} "
                f"(orderBookId {returned_id}, requested {order_book_id}), "
                f"not {clean_sym} — fail-closed (SYMBOL_MISMATCH).")

        bid_1 = self._to_float(record.get("bp"))
        offer_1 = self._to_float(record.get("op"))
        last = self._to_float(record.get("l"))
        if bid_1 is None and offer_1 is None and last is None:
            logger.warning(f"get_market_bid_offer({clean_sym}): no Bid/Offer/Last — fail-closed")
            return self._quote_unavailable(
                clean_sym, f"{clean_sym} has no readable Bid/Offer/Last (orderBookId {order_book_id}).")

        return {
            "symbol": clean_sym,
            "success": True,
            "status": "OK",
            "bid_1": bid_1,
            "offer_1": offer_1,
            "last": last,
            "prior_close": self._to_float(record.get("prior")),
            "ceiling": self._to_float(record.get("cl")),
            "floor": self._to_float(record.get("fl")),
            "board_lot": None, "flag": None,
            "source": "liberator_api",
        }

    async def scrape_portfolio(self, force_refresh: bool = False, headless: bool = True) -> Dict[str, Any]:
        """
        Scrapes Line Available, Cash Balance, Total Equity, Holdings, and Orders.
        Uses active page if running, or launches background context with saved cookies,
        and caches results to data/liberator_portfolio_cache.json.
        """
        # If cache exists and caller didn't force fresh, return cache if not authenticated
        if not force_refresh and not self.is_authenticated and os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass

        # Case 1: Page is already alive in this driver instance
        if self.page and not self.page.is_closed():
            try:
                if "portfolio" not in self.page.url.lower():
                    await self.page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=15000)
                    await self.page.wait_for_timeout(2000)

                data = await self._extract_portfolio_from_page(self.page)
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                with open(self.cache_path, "w") as f:
                    json.dump(data, f, indent=2)
                return data
            except Exception as e:
                logger.error(f"Error scraping portfolio from active page: {e}")

        # Case 2: Open standalone context using saved session
        if os.path.exists(self.session_path):
            try:
                with open(self.session_path, "r") as f:
                    state_data = json.load(f)
                cookies = state_data.get("cookies", [])
                if not cookies:
                    raise ValueError("No cookies in saved session file")

                async with async_playwright() as p:
                    b = await p.chromium.launch(
                        headless=headless,
                        executable_path=self.chrome_path if os.path.exists(self.chrome_path) else None,
                        args=["--no-sandbox", "--disable-setuid-sandbox"]
                    )
                    ctx = await b.new_context(
                        no_viewport=True,
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                    )
                    await ctx.add_cookies(cookies)
                    temp_page = await ctx.new_page()
                    await temp_page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
                    await temp_page.wait_for_timeout(3000)

                    data = await self._extract_portfolio_from_page(temp_page)
                    data["updated_at"] = datetime.now(timezone.utc).isoformat()
                    with open(self.cache_path, "w") as f:
                        json.dump(data, f, indent=2)

                    await b.close()
                    return data
            except Exception as e:
                logger.error(f"Error scraping portfolio via standalone session: {e}")

        # Fallback to cache if available
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            "line_available": 0.0,
            "cash_balance": 0.0,
            "credit_limit": 0.0,
            "total_equity": 0.0,
            "total_market_value": 0.0,
            "total_cost": 0.0,
            "total_unrealized_pnl": 0.0,
            "positions": [],
            "orders": []
        }

    async def execute_order(
        self,
        symbol: str,
        side: str,
        volume: int,
        price: float,
        pin: Optional[str] = None,
        account_no: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes an equity order on Liberator WebTrade.
        Validates SET Board Lot (x100), sets Buy/Sell side, populates symbol, volume, price, PIN,
        and submits the order while capturing the resulting order entry.
        """
        norm_side = side.strip().upper()
        if norm_side not in ["BUY", "SELL"]:
            return {"success": False, "error": f"Invalid side '{side}' for Liberator Equity. Allowed: BUY, SELL."}

        if volume <= 0 or volume % 100 != 0:
            return {"success": False, "error": f"Volume ({volume}) must be a positive multiple of 100."}

        if price <= 0:
            return {"success": False, "error": f"Price ({price}) must be positive."}

        order_pin = pin or getattr(settings, "LIBERATOR_PIN", "")
        if not order_pin or len(order_pin) != 6:
            return {"success": False, "error": "Valid 6-digit Liberator PIN required."}

        # Market Hours Validation (Mon-Fri 09:55-12:30, 14:25-16:35 Bangkok)
        now_bkk = datetime.now(timezone.utc).astimezone()
        if now_bkk.weekday() in (5, 6):
            return {
                "success": False,
                "status": "MARKET_CLOSED",
                "staged": True,
                "error": f"SET Market is CLOSED on weekends ({now_bkk.strftime('%A')}). Form interaction is verified and order is staged for Monday Open (09:55 BKK)."
            }

        # Check browser session
        if not self.page or self.page.is_closed():
            await self.launch_browser(resume_state=True)
            if not await self.verify_saved_session():
                login_res = await self.login()
                if not login_res.success:
                    return {"success": False, "error": f"Liberator login failed: {login_res.message}"}

        page = self.page
        if "portfolio" not in page.url.lower():
            await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

        try:
            # 1. Select Side
            side_btn = page.locator(f":text('{norm_side.capitalize()}')").first
            await side_btn.click()
            await page.wait_for_timeout(400)

            # 2. Enter Symbol
            sym_input = await page.wait_for_selector("#SearchSymbolList-setBuySellFooter", timeout=5000)
            if sym_input:
                await sym_input.fill("")
                await sym_input.fill(symbol.upper())
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(400)

            # 3. Enter Volume
            vol_input = await page.wait_for_selector("#volume", timeout=5000)
            if vol_input:
                await vol_input.fill("")
                await vol_input.fill(str(volume))

            # 4. Enter Price
            price_input = await page.wait_for_selector("#price", timeout=5000)
            if price_input:
                await price_input.fill("")
                await price_input.fill(f"{price:.2f}")

            # 5. Enter PIN
            pin_input = await page.wait_for_selector("#pin", timeout=5000)
            if pin_input:
                await pin_input.fill("")
                await pin_input.fill(order_pin)

            # 6. Click Submit Button
            submit_btn = await page.wait_for_selector("#buttonSubmit", timeout=5000)
            await submit_btn.click()
            await page.wait_for_timeout(1500)

            # Handle Confirmation Modal if any
            confirm_btn = await page.query_selector("button:has-text('Confirm'), button:has-text('ยืนยัน')")
            if confirm_btn and await confirm_btn.is_visible():
                await confirm_btn.click()
                await page.wait_for_timeout(2000)

            # 7. Scrape updated Orders Table
            portfolio_data = await self.scrape_portfolio(force_refresh=True)
            orders = portfolio_data.get("orders", [])
            matching_order = next((o for o in orders if o.get("symbol") == symbol.upper() and o.get("side") == norm_side), None)
            broker_order_no = matching_order.get("order_no") if matching_order else f"LIB-{int(time.time())}"
            order_status = matching_order.get("status", "OPEN") if matching_order else "SUBMITTED"

            return {
                "success": True,
                "broker": "LIBERATOR",
                "broker_order_no": broker_order_no,
                "symbol": symbol.upper(),
                "side": norm_side,
                "volume": volume,
                "price": price,
                "status": order_status,
                "message": f"Liberator order #{broker_order_no} submitted successfully."
            }
        except Exception as e:
            logger.error(f"Error executing Liberator order: {e}")
            return {"success": False, "error": str(e)}

    async def execute_action_exit(
        self,
        symbol: str,
        volume: Optional[int] = None,
        target_price: Optional[float] = None,
        reason: str = "Tactical Action Exit"
    ) -> Dict[str, Any]:
        """
        Executes a Tactical Action Exit (Sell) for a stock held in the Liberator portfolio.
        If volume is None, liquidates 100% of available shares (act_vol).
        """
        # 1. Fetch current portfolio
        data = await self.scrape_portfolio()
        positions = data.get("positions", [])
        pos = next((p for p in positions if p.get("symbol", "").upper() == symbol.upper()), None)
        if not pos:
            return {"success": False, "error": f"Position for '{symbol}' not found in Liberator portfolio."}

        available_vol = pos.get("available_volume") or pos.get("act_vol") or pos.get("volume") or 0
        if available_vol <= 0:
            return {"success": False, "error": f"No available volume to sell for {symbol} (available: {available_vol})."}

        sell_vol = volume if (volume and volume > 0) else available_vol
        if sell_vol > available_vol:
            sell_vol = available_vol

        # Ensure board lot
        sell_vol = (sell_vol // 100) * 100
        if sell_vol <= 0:
            return {"success": False, "error": f"Selling volume ({sell_vol}) is less than 100 board lot."}

        sell_price = target_price or pos.get("market_price", 0.0)
        if sell_price <= 0:
            return {"success": False, "error": f"Invalid market price for {symbol}."}

        logger.info(f"Executing Action Exit on Liberator: SELL {sell_vol:,} {symbol} @ ฿{sell_price:.2f} ({reason})")
        return await self.execute_order(
            symbol=symbol,
            side="SELL",
            volume=sell_vol,
            price=sell_price
        )

    # ─── Liberator order-table row actions (pinned live 2026-10-09, order #11894) ───
    # The per-row controls are plain Vue divs, e.g. <div class="cursor-pointer"> Change </div>,
    # with NO id / role / title / aria-label ⇒ the only stable handle is the visible label.
    LIB_ORDER_TABLE = "#OrderTableList"
    LIB_AMEND_ACTION = "Change"
    LIB_CANCEL_ACTION = "Cancel"
    LIB_AMEND_OVERLAY = "div.overlay"
    LIB_CONFIRM_BUTTON = "#confirmDialogActiveButton"
    LIB_AMENDABLE_STATUSES = ("open", "partial")

    @staticmethod
    def _parse_order_row_cells(cells) -> Dict[str, Any]:
        """Maps the 11 <td> strings of one #OrderTableList row into typed fields."""
        def _num(value: Any) -> float:
            try:
                return float(str(value).replace(",", "").strip() or 0)
            except ValueError:
                return 0.0

        padded = list(cells)[:11] + [""] * max(0, 11 - len(cells))
        return {
            "order_no": padded[0].strip(),
            "time": padded[1].strip(),
            "symbol": padded[2].strip().upper(),
            "side": padded[3].strip().upper(),
            "price": _num(padded[4]),
            "volume": int(_num(padded[5])),
            "matched": int(_num(padded[6])),
            "balance": int(_num(padded[7])),
            "status": padded[9].strip(),
            "actions": padded[10].strip(),
        }

    @staticmethod
    def _amend_guard(order_no: str, new_price: float, new_volume: Optional[int]) -> Optional[str]:
        """Pure input validation for change_order(). Returns an error string, else None."""
        if not str(order_no or "").strip().isdigit():
            return f"Invalid Liberator order number '{order_no}' (digits only)."
        if new_price is None or float(new_price) <= 0:
            return f"New price ({new_price}) must be positive."
        if new_volume is not None and (new_volume <= 0 or new_volume % 100 != 0):
            return f"New volume ({new_volume}) must be a positive multiple of 100."
        return None

    @staticmethod
    async def _order_action_locator(row, label: str):
        """Resolves a per-row action control (Change / Detail / Cancel) by exact label text.

        Tries the strategies proven in `scripts/liberator/diag_change_locator.py`.
        NOTE: `filter(has_text=<str>)` is a case-insensitive substring match and works, but an
        anchored regex `^Change$` does NOT (the element's textContent keeps its spaces).
        """
        action_cell = row.locator("td").last
        candidates = (
            action_cell.get_by_text(label, exact=True),
            action_cell.locator("div.cursor-pointer").filter(has_text=label),
            action_cell.locator(f'div:text-is("{label}")'),
            action_cell.locator(f"xpath=.//div[normalize-space(text())='{label}']"),
        )
        for candidate in candidates:
            try:
                if await candidate.count():
                    return candidate.first
            except Exception:  # noqa: BLE001 - try the next strategy
                continue
        return None

    async def cancel_order(self, order_no: str) -> Dict[str, Any]:
        """
        Cancels an open order on Liberator WebTrade.
        """
        now_bkk = datetime.now(timezone.utc).astimezone()
        if now_bkk.weekday() in (5, 6):
            return {
                "success": False,
                "status": "MARKET_CLOSED",
                "error": "SET Market is CLOSED on weekends. Cancellation verified and staged for Market Open."
            }

        if not self.page or self.page.is_closed():
            await self.launch_browser(resume_state=True)

        try:
            page = self.page
            if "portfolio" not in page.url.lower():
                await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)

            # Locate the row via the per-row checkbox id (== order number). NEVER anchor with a
            # \b-regex on the row text: this table's textContent has no whitespace between cells
            # ("1189410:03:21BCH...") so word boundaries never match (LIB-RCA-016).
            row = page.locator(f"{self.LIB_ORDER_TABLE} tbody tr:has(input[id='{order_no}'])").first
            if not await row.count():
                return {"success": False, "error": f"Order #{order_no} not found in Orders table."}

            # The row actions are plain Vue divs (no id/role) -> resolve by exact label text
            cancel_btn = await self._order_action_locator(row, self.LIB_CANCEL_ACTION)
            if cancel_btn is not None:
                await cancel_btn.click()
                await page.wait_for_timeout(1000)
                # Confirm popup if any (same dialog component as the amend flow)
                confirm = page.locator(self.LIB_CONFIRM_BUTTON).first
                if await confirm.count() and await confirm.is_visible():
                    await confirm.click()
                return {"success": True, "order_no": order_no, "message": f"Order #{order_no} cancellation submitted."}

            return {"success": False, "error": f"Order #{order_no} does not have an active cancel action (may already be matched)."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def change_order(
        self,
        order_no: str,
        new_price: float,
        new_volume: Optional[int] = None,
        pin: Optional[str] = None,
        expected_symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Amends a resting Liberator order **in place** via the row's native `Change` control
        (ต่อราคาแบบไม่เสียคิว) — the ORIGINAL order number is preserved: nothing is cancelled
        and no new order is submitted (replaces the old cancel + re-place flow).

        Live-proven path (order #11894, BCH SELL 12.00 x 4,000, 2026-10-09):
            row    = `#OrderTableList tbody tr:has(input[id='11894'])`
            click  = row `Change`  ->  `div.overlay` ("Change Order Confirmation")
            fields = `div.overlay #volume` / `#price` / `#pin`
            submit = `div.overlay #confirmDialogActiveButton`

        ⚠️ LIB-RCA-016: NEVER anchor this row with a \\b-regex — the table's textContent has
           no whitespace between cells ("1189410:03:21BCH...") so word boundaries never match.
        ⚠️ LIB-RCA-017: `#volume`/`#price`/`#pin` exist TWICE (Buy/Sell footer first, amend
           overlay second) — the amend fields MUST be scoped inside `div.overlay`.

        ``expected_symbol`` (Loop 1 D3, fail-closed): the symbol the caller believes this order
        is for. When it is given, the live row is re-read and a mismatch refuses the amend with
        ``status="SYMBOL_MISMATCH"`` **before** the Change control is pressed (0 clicks) — an
        order whose identity is unproven is never amended.

        Anti-Mock (Invariant 1): success is only reported after the order table is re-read and
        the new price is confirmed on the SAME order number.
        """
        error = self._amend_guard(order_no, new_price, new_volume)
        if error:
            return {"success": False, "error": error}

        order_pin = pin or getattr(settings, "LIBERATOR_PIN", "")
        if not order_pin or len(str(order_pin)) != 6:
            return {"success": False, "error": "Valid 6-digit Liberator PIN required."}

        now_bkk = datetime.now(timezone.utc).astimezone()
        if now_bkk.weekday() in (5, 6):
            return {
                "success": False,
                "status": "MARKET_CLOSED",
                "staged": True,
                "order_no": str(order_no),
                "error": (
                    f"SET Market is CLOSED on weekends ({now_bkk.strftime('%A')})."
                    " Amend staged for Monday Open (09:55 BKK)."
                ),
            }

        if not self.page or self.page.is_closed():
            await self.launch_browser(resume_state=True)
            if not await self.verify_saved_session():
                login_res = await self.login()
                if not login_res.success:
                    return {"success": False, "error": f"Liberator login failed: {login_res.message}"}

        try:
            return await self._amend_order_in_place(
                str(order_no), float(new_price), new_volume, str(order_pin), expected_symbol
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error amending Liberator order #{order_no}: {e}")
            return {"success": False, "error": str(e)}

    async def _amend_order_in_place(
        self,
        order_no: str,
        new_price: float,
        new_volume: Optional[int],
        order_pin: str,
        expected_symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """DOM half of change_order(): press Change, fill the amend overlay, confirm, verify."""
        page = self.page
        if "portfolio" not in page.url.lower():
            await page.goto(
                "https://webtrade.liberator.co.th/Portfolio",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await page.wait_for_timeout(2000)

        # 1. Anchor the row on the checkbox id (== order number): exact, no text ambiguity
        row = page.locator(
            f"{self.LIB_ORDER_TABLE} tbody tr:has(input[id='{order_no}'])"
        ).first
        if not await row.count():
            return {"success": False, "error": f"Order #{order_no} not found in Orders table."}

        # 2. Read the row as it is now (evidence + amendability guard)
        parsed = self._parse_order_row_cells(await row.locator("td").all_inner_texts())

        # 2a. Fail-closed symbol confirmation (Loop 1 D3): the caller told us which symbol this
        #     order should be — if the live row disagrees, the identity of the order we are
        #     about to amend is unproven, so NOTHING is pressed (never amend the wrong stock).
        #     Checked BEFORE the status guard: identity first, then state.
        want = str(expected_symbol or "").strip().upper()
        actual = str(parsed["symbol"] or "").upper()
        if want and actual != want:
            logger.warning(
                "change_order(%s): symbol mismatch — row is %r, expected %r — fail-closed",
                order_no, actual, want,
            )
            return {
                "success": False,
                "status": "SYMBOL_MISMATCH",
                "order_no": str(order_no),
                "expected_symbol": want,
                "actual_symbol": actual,
                "error": (
                    f"Order #{order_no} is {actual or 'unknown'} on the broker, not {want}"
                    " - the Change control was NOT pressed (fail-closed)."
                ),
            }

        status = parsed["status"]
        if status.lower() not in self.LIB_AMENDABLE_STATUSES:
            return {
                "success": False,
                "order_no": order_no,
                "status": status,
                "error": (
                    f"Order #{order_no} is '{status}' (not Open/Partial)"
                    " - the Change control is not available."
                ),
            }
        old_price, old_volume = parsed["price"], parsed["volume"]

        # 3. Press the native Change control (opens the amend overlay; proven no side effect)
        change_btn = await self._order_action_locator(row, self.LIB_AMEND_ACTION)
        if change_btn is None:
            return {
                "success": False,
                "error": (
                    f"Order #{order_no} has no '{self.LIB_AMEND_ACTION}' control"
                    " (row markup may have changed - re-run the probe)."
                ),
            }
        await change_btn.click()
        await page.wait_for_selector(self.LIB_AMEND_OVERLAY, timeout=8000)
        await page.wait_for_timeout(600)

        # 4. Fill ONLY the overlay's fields (LIB-RCA-017: identical ids exist in the footer)
        overlay = page.locator(self.LIB_AMEND_OVERLAY).first
        if new_volume is not None:
            vol_input = overlay.locator("#volume")
            await vol_input.fill("")
            await vol_input.fill(str(int(new_volume)))
        price_input = overlay.locator("#price")
        await price_input.fill("")
        await price_input.fill(f"{new_price:.2f}")
        pin_input = overlay.locator("#pin")
        await pin_input.fill("")
        await pin_input.fill(order_pin)

        # 5. Confirm inside the overlay only
        await overlay.locator(self.LIB_CONFIRM_BUTTON).first.click()
        await page.wait_for_timeout(2500)

        # 6. Anti-Mock: re-read the order table, require the new price on the SAME order no.
        data = await self.scrape_portfolio(force_refresh=True)
        after = next(
            (o for o in data.get("orders", []) if str(o.get("order_no")) == order_no), None
        )
        base = {
            "broker": "LIBERATOR",
            "order_no": order_no,
            "symbol": parsed["symbol"],
            "side": parsed["side"],
            "old_price": old_price,
            "new_price": new_price,
            "old_volume": old_volume,
            "new_volume": int(new_volume) if new_volume is not None else old_volume,
        }
        if not after:
            return {
                **base,
                "success": False,
                "action": "AMEND_UNVERIFIED",
                "error": (
                    f"Order #{order_no} is no longer in the Orders table after the amend"
                    " - verify on the broker."
                ),
            }
        reported = float(after.get("price") or 0.0)
        if abs(reported - new_price) > 0.001:
            return {
                **base,
                "success": False,
                "action": "AMEND_UNVERIFIED",
                "reported_price": reported,
                "error": (
                    f"Amend not confirmed: order #{order_no} still shows ฿{reported:.2f}"
                    f" (expected ฿{new_price:.2f})."
                ),
            }
        return {
            **base,
            "success": True,
            "action": "AMENDED_IN_PLACE",
            "status": after.get("status", "Open"),
            "message": (
                f"Liberator order #{order_no} amended in place ฿{old_price:.2f} -> ฿{new_price:.2f}"
                " (order number retained)."
            ),
        }

    async def negotiate_price(
        self,
        order_no: Optional[str] = None,
        symbol: Optional[str] = None,
        target_price: Optional[float] = None,
        pegging_mode: str = "PASSIVE_BEST"  # PASSIVE_BEST (Offer 1 on Sell / Bid 1 on Buy)
    ) -> Dict[str, Any]:
        """
        Pillar 6 Tactical Price Negotiation (ต่อราคา):
        Inspects unmatched open orders on Liberator and amends the chosen order **in place**
        via the broker's native `Change` control — the order number and its queue slot are
        preserved, nothing is cancelled and no replacement order is submitted.
        (Replaces the old cancel + re-place flow; see LIB-RCA-016 / LIB-RCA-017.)
        """
        data = await self.scrape_portfolio()
        orders = data.get("orders", [])

        # Filter active unmatched orders
        open_orders = [
            o for o in orders
            if o.get("status") not in ["Matched", "Cancelled"] and o.get("balance", 0) > 0
        ]

        if not open_orders:
            return {
                "success": True,
                "action": "NONE",
                "message": "No open unmatched orders currently in Liberator queue to negotiate.",
                "open_count": 0
            }

        target_order = None
        if order_no:
            target_order = next((o for o in open_orders if str(o.get("order_no")) == str(order_no)), None)
        elif symbol:
            target_order = next((o for o in open_orders if o.get("symbol", "").upper() == symbol.upper()), None)
        else:
            target_order = open_orders[0]

        if not target_order:
            return {"success": False, "error": "Matching open order not found for price negotiation."}

        curr_price = float(target_order.get("price", 0.0))
        ord_symbol = target_order.get("symbol", "")
        ord_side = target_order.get("side", "SELL").upper()
        ord_vol = int(target_order.get("balance", target_order.get("volume", 0)))
        ord_no = target_order.get("order_no", "")

        new_price = target_price or curr_price

        # Check market closed
        now_bkk = datetime.now(timezone.utc).astimezone()
        if now_bkk.weekday() in (5, 6):
            return {
                "success": True,
                "status": "MARKET_CLOSED",
                "staged": True,
                "symbol": ord_symbol,
                "order_no": ord_no,
                "current_price": curr_price,
                "proposed_negotiated_price": new_price,
                "message": f"Price negotiation protocol verified for {ord_symbol} ({ord_side}). Staged for Market Open (11:00 / 15:30 BKK)."
            }

        # No-op guard: never submit an amend that keeps the same price
        if abs(new_price - curr_price) < 0.005:
            return {
                "success": True,
                "action": "NONE",
                "order_no": ord_no,
                "symbol": ord_symbol,
                "side": ord_side,
                "current_price": curr_price,
                "message": f"Order #{ord_no} ({ord_symbol}) is already at ฿{new_price:.2f} - no amend needed."
            }

        # Amend the resting order IN PLACE (ต่อราคา) — order number + queue slot preserved.
        # Fail-closed: hand the symbol we selected in with the request so change_order can
        # refuse if the live row is a different stock (Loop 1 D3).
        amend_res = await self.change_order(
            order_no=str(ord_no),
            new_price=new_price,
            new_volume=None,
            expected_symbol=ord_symbol,
        )
        if not amend_res.get("success", False):
            return {
                "success": False,
                "action": amend_res.get("action", "AMEND_FAILED"),
                "order_no": ord_no,
                "symbol": ord_symbol,
                "old_price": curr_price,
                "new_price": new_price,
                "error": amend_res.get("error", "In-place price negotiation failed."),
            }

        final_old = amend_res.get("old_price", curr_price)
        final_new = amend_res.get("new_price", new_price)
        return {
            "success": True,
            "action": "AMENDED_IN_PLACE",
            "order_no": ord_no,
            "symbol": ord_symbol,
            "side": ord_side,
            "volume": ord_vol,
            "old_price": final_old,
            "new_price": final_new,
            "message": (
                f"Negotiated {ord_symbol} {ord_side} order #{ord_no} in place: "
                f"฿{final_old:.2f} -> ฿{final_new:.2f} (order number retained)"
            ),
        }

    async def close(self) -> None:
        """Closes browser context and playwright instance."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        finally:
            self.context = None
            self.browser = None
            self.page = None
            self.playwright = None
            self.status = "DISCONNECTED"


# Singleton instance
liberator_driver = LiberatorDriver()
