import os
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError
)

import time
from sqlalchemy import select
from app.core.config import settings
from app.core.events import event_bus
from app.db.session import AsyncSessionLocal
from app.db.models import SessionLog
from app.browser.popup_manager import popup_manager
from app.browser.tab_manager import tab_manager
from app.services.redaction import redact_otp, redact_url
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform, OTPPayload, OTPSource

logger = logging.getLogger(__name__)

# LINE-RCA-002 (2026-10-08): tolerant extractor for OTP codes written into
# `session_logs.details` by the relay channels. Real rows look like:
#   "Received OTP 6-digits from LINE: 849201 (Ref: BIPE)"   <- LINE group
#   "Received SMS OTP: 123456"                              <- KDE Connect
# The old pattern `Received (?:SMS )?OTP(?:\s*6-digits)?:` failed on the LINE row
# because of the " from LINE" infix, silently breaking the cross-process OTP path.
# SINGLE SOURCE OF TRUTH — reused by app/brokers/liberator/driver.py.
OTP_SESSION_LOG_PATTERN = r"Received[^:]*OTP[^:]*:\s*([0-9]{6})"


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



class KrungsriAuthDriver:
    """
    Playwright Automation Driver for Krungsri Securities & TradeMan SSO.
    Handles Headed browser login, 2FA SMS OTP detection & submission,
    session cookie persistence, and error snapshotting.
    """
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        self.status: str = "DISCONNECTED"  # DISCONNECTED, LAUNCHING, NAVIGATING, AWAITING_OTP, AUTHENTICATED, FAILED
        self.current_ref: Optional[str] = None
        self.last_dialog_message: Optional[str] = None
        self.last_heartbeat: Optional[datetime] = None
        self.last_login_attempt: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def is_authenticated(self) -> bool:
        return self.status == "AUTHENTICATED" and self.page is not None

    @property
    def current_url(self) -> Optional[str]:
        return self.page.url if self.page else None

    async def _log_event(self, event_type: str, details: str) -> None:
        """Persists a session event in the database session_logs table."""
        try:
            async with AsyncSessionLocal() as db:
                log_entry = SessionLog(event_type=event_type, details=details)
                db.add(log_entry)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to record session log ({event_type}): {e}")

    async def _handle_dialog(self, dialog) -> None:
        """Handles unexpected JavaScript alert/confirm dialogs."""
        self.last_dialog_message = dialog.message
        logger.warning(f"Browser dialog opened: [{dialog.type}] {dialog.message}")
        await self._log_event("BROWSER_DIALOG", f"[{dialog.type}] {dialog.message}")
        await dialog.accept()

    async def launch_browser(self, resume_state: bool = True) -> Page:
        """
        Launches Google Chrome in Headed/Headless mode as configured.
        Loads existing session cookies if available.
        """
        async with self._lock:
            if self.browser and self.page and not self.page.is_closed():
                return self.page

            self.status = "LAUNCHING"
            os.makedirs(os.path.dirname(settings.SESSION_STATE_PATH) or "data", exist_ok=True)
            self.playwright = await async_playwright().start()

            launch_kwargs: Dict[str, Any] = {
                "headless": settings.PLAYWRIGHT_HEADLESS,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1366,768",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-crash-reporter",
                    "--disable-breakpad",
                    "--no-crash-upload",
                    "--password-store=basic",
                    "--use-mock-keychain"
                ]
            }

            if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
                launch_kwargs["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE

            logger.info(f"Launching Chromium browser (headless={settings.PLAYWRIGHT_HEADLESS})...")
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)

            # Check if saved cookies exist
            context_kwargs: Dict[str, Any] = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            }
            if resume_state and os.path.exists(settings.SESSION_STATE_PATH):
                logger.info(f"Restoring session from {settings.SESSION_STATE_PATH}")
                context_kwargs["storage_state"] = settings.SESSION_STATE_PATH

            self.context = await self.browser.new_context(**context_kwargs)
            tab_manager.set_context(self.context)
            self.page = await self.context.new_page()
            self.page.on("dialog", self._handle_dialog)
            tab_manager.register_tab("krungsri_portal", self.page)
            
            return self.page

    async def validate_preflight_session(self) -> bool:
        """
        Pre-flight Just-in-Time session check before executing orders or scraping.
        Quickly verifies whether the current page is authenticated and #dropDownAccountPort is visible.
        """
        if not self.page or self.page.is_closed():
            return False
        try:
            current_url = self.page.url.lower()
            if "trademan.in.th" not in current_url:
                return False
            el = await self.page.query_selector("#dropDownAccountPort, .account-selector")
            return el is not None and await el.is_visible()
        except Exception:
            return False

    @staticmethod
    def _url_is_signin(url: Optional[str]) -> bool:
        """RCA-008: TradeMan redirects a dead session to an auth page whose URL contains
        'signin' or 'login' (case-insensitive). Either means the session is NOT authenticated."""
        u = (url or "").lower()
        return "signin" in u or "login" in u

    async def _account_no_visible(self, page: Optional[Page]) -> bool:
        """RCA-008: the account dropdown renders the active 7-digit account number at
        ``#dropDownAccountPort > div.flex.w-full.justify-between > div`` (see runbook
        trademan_portfolio_dom.md). On a SignIn/expired page the selector is absent or
        empty, so a merely-visible selector is NOT proof of a live session — require an
        actual 7-digit account number in the DOM."""
        if not page:
            return False
        try:
            el = await page.query_selector(
                "#dropDownAccountPort > div.flex.w-full.justify-between > div"
            )
            if not el:
                return False
            text = (await el.inner_text()) or ""
            return bool(re.search(r"\b\d{7}\b", text))
        except Exception:
            return False

    async def verify_saved_session(self) -> bool:
        """
        Strict DOM Validation:
        Checks if the active browser session or saved session in data/session_state.json is still valid.
        MUST verify that TradeMan account element (#dropDownAccountPort) is visible in the DOM.
        If NOT present or timed out, the session is 100% expired/invalid:
        - Purge stale session_state.json
        - Clear context cookies
        - Return False so fresh Krungsri login is triggered.
        """
        # 1. First priority: check if page is already open, not closed, and at trademan.in.th
        if self.page and not self.page.is_closed():
            try:
                current_url = self.page.url.lower()
                if "trademan.in.th" in current_url and not self._url_is_signin(current_url):
                    account_el = await self.page.query_selector("#dropDownAccountPort, .account-selector")
                    if account_el and await account_el.is_visible() and await self._account_no_visible(self.page):
                        title = await self.page.evaluate("() => document.title")
                        logger.info(f"Active TradeMan tab verified with DOM selector (Title: '{title}'). Reusing session.")
                        self.status = "AUTHENTICATED"
                        self.last_heartbeat = datetime.now(timezone.utc)
                        if self.context:
                            os.makedirs(os.path.dirname(settings.SESSION_STATE_PATH) or "data", exist_ok=True)
                            await self.context.storage_state(path=settings.SESSION_STATE_PATH)
                        await self._log_event("SESSION_REUSED", f"Reused active TradeMan tab at {self.page.url}")
                        return True
            except Exception as e:
                logger.debug(f"Direct page responsiveness check failed: {e}")

        # 2. Second priority: If saved session file exists and page is available
        if not os.path.exists(settings.SESSION_STATE_PATH) or not self.page or self.page.is_closed():
            return False

        try:
            target_port_url = getattr(settings, "TRADEMAN_PORTFOLIO_URL", "https://trademan.in.th/Portfolio")
            logger.info(f"Validating existing session cookies with TradeMan Portfolio: {target_port_url} ...")
            await self.page.goto(target_port_url, wait_until="domcontentloaded", timeout=12000)
            await self.page.wait_for_timeout(1000)

            # Strict DOM check: MUST find #dropDownAccountPort within 6s
            account_selector = None
            try:
                account_selector = await self.page.wait_for_selector(
                    "#dropDownAccountPort, .account-selector",
                    state="visible",
                    timeout=6000
                )
            except Exception:
                account_selector = None

            # RCA-008: the dropdown can appear briefly before the app redirects an expired
            # session to /SignIn. Let the page settle, then re-check BOTH the final URL
            # (not signin/login) AND a real 7-digit account number in the DOM.
            await self.page.wait_for_timeout(3000)
            current_url = self.page.url.lower()
            account_no_ok = await self._account_no_visible(self.page)
            if account_selector and "trademan.in.th" in current_url and not self._url_is_signin(current_url) and account_no_ok:
                self.status = "AUTHENTICATED"
                self.last_heartbeat = datetime.now(timezone.utc)
                await popup_manager.dismiss_popups(self.page)
                if self.context:
                    os.makedirs(os.path.dirname(settings.SESSION_STATE_PATH) or "data", exist_ok=True)
                    await self.context.storage_state(path=settings.SESSION_STATE_PATH)
                await self._log_event("SESSION_RESTORED", f"TradeMan session validated successfully via DOM selector at {current_url}")
                return True
            else:
                logger.warning(
                    "TradeMan saved-session validation failed (url=%s, account_no_visible=%s). Session expired.",
                    current_url, account_no_ok,
                )
                # Invariant 8 (non-destructive): NEVER hard-delete the saved Zero-OTP
                # token on a validation miss. Quarantine it instead so the session can
                # be recovered / re-inspected (mirrors Liberator's *.stale.bak.json).
                self._quarantine_session_file()
                self.status = "DISCONNECTED"
                return False
        except Exception as e:
            # Invariant 8: a transient navigation/DOM timeout must NOT destroy the
            # saved Zero-OTP session. Leave the file 100% intact and report the check
            # as inconclusive. (Root cause of the 2026-10-07 zero-OTP session loss.)
            logger.warning(f"Saved session check error or timed out (session file left intact): {e}")
            self.status = "DISCONNECTED"
            return False

    def _quarantine_session_file(self) -> Optional[str]:
        """
        Non-destructively preserves a rejected session file (Invariant 8).

        Renames `settings.SESSION_STATE_PATH` to `<path>.stale.bak.json` instead of
        deleting it, so the Zero-OTP token is never lost and can be re-inspected.
        Returns the backup path when quarantined, otherwise None.
        """
        path = settings.SESSION_STATE_PATH
        if not os.path.exists(path):
            return None
        backup = f"{path}.stale.bak.json"
        try:
            os.replace(path, backup)
            logger.info(f"Quarantined rejected session file non-destructively -> {backup}")
            return backup
        except Exception as qe:
            logger.warning(f"Could not quarantine session file (left intact): {qe}")
            return None

    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_otp: Optional[int] = None,
        force_fresh: bool = False
    ) -> LoginResult:
        """
        Executes full login sequence to Krungsri Securities:
        1. Fill credentials (#login_username, #login_password)
        2. Submit form (#login)
        3. Detect 2FA SMS OTP modal/page & scrape Ref Code
        4. Await OTP from KDE Connect / event bus queue (timeout: 180s)
        5. Submit OTP & wait for SSO to TradeMan (trademan.in.th)
        6. Save storage state to data/session_state.json
        """
        user = username or settings.KRUNGSRI_USERNAME
        passwd = password or settings.KRUNGSRI_PASSWORD
        otp_timeout = timeout_otp or settings.OTP_TIMEOUT_SECONDS

        if not user or not passwd:
            raise ValueError(
                "Krungsri credentials missing! Please configure KRUNGSRI_USERNAME and KRUNGSRI_PASSWORD in .env"
            )

        # Priority 0: If already authenticated on TradeMan and not forcing fresh, reuse immediately
        if not force_fresh and self.is_authenticated and self.page and not self.page.is_closed():
            if await self.validate_preflight_session():
                logger.info("login() invoked but TradeMan is already active and verified with #dropDownAccountPort. Reusing active tab.")
                return LoginResult(
                    success=True,
                    status=AuthStatus.AUTHENTICATED,
                    broker=BrokerPlatform.TRADEMAN,
                    resumed=True,
                    url=self.page.url,
                    message="Already authenticated. Reusing active TradeMan tab."
                )

        page = await self.launch_browser(resume_state=not force_fresh)

        # Step 0: Test existing session if not force_fresh
        if not force_fresh and await self.verify_saved_session():
            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.TRADEMAN,
                resumed=True,
                url=page.url,
                message="Existing session is active and valid."
            )

        if force_fresh:
            logger.info("Fresh login requested. Purging previous cookies and storage state.")
            if os.path.exists(settings.SESSION_STATE_PATH):
                try:
                    os.remove(settings.SESSION_STATE_PATH)
                except Exception:
                    pass
            if self.context:
                try:
                    await self.context.clear_cookies()
                except Exception:
                    pass

        # Cooldown guard: Prevent spamming SMS OTP if a login attempt is already in progress or fired within 60s
        now = datetime.now(timezone.utc)
        if self.last_login_attempt and (now - self.last_login_attempt).total_seconds() < 60 and self.status in ["NAVIGATING", "AWAITING_OTP"]:
            logger.warning("Login flow is already in progress within 60s cooldown. Skipping duplicate trigger.")
            return LoginResult(
                success=False,
                status=AuthStatus.AWAITING_OTP if self.status == "AWAITING_OTP" else AuthStatus.NAVIGATING,
                broker=BrokerPlatform.TRADEMAN,
                resumed=False,
                message="Login flow already in progress. Please await current attempt or OTP."
            )
        self.last_login_attempt = now

        try:
            # Step 1: Navigate to Krungsri Login Page
            self.status = "NAVIGATING"
            logger.info(f"Navigating to login page: {settings.KRUNGSRI_LOGIN_URL}")
            await page.goto(settings.KRUNGSRI_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Check if user is already logged in (e.g. member portal, greeting, or announcement)
            body_text = await page.inner_text("body")
            if any(k in body_text for k in ["ยินดีต้อนรับ", "ออกจากระบบ", "creditbalance_announcement"]) or "member" in page.url.lower():
                logger.info("User already logged into Krungsri portal! Proceeding directly to TradeMan SSO...")
                await self._verify_post_login(page)
                if self.context:
                    os.makedirs(os.path.dirname(settings.SESSION_STATE_PATH) or "data", exist_ok=True)
                    await self.context.storage_state(path=settings.SESSION_STATE_PATH)
                self.status = "AUTHENTICATED"
                self.last_heartbeat = datetime.now(timezone.utc)
                return LoginResult(
                    success=True,
                    status=AuthStatus.AUTHENTICATED,
                    broker=BrokerPlatform.TRADEMAN,
                    resumed=True,
                    url=page.url,
                    message="User was already authenticated; TradeMan SSO completed."
                )

            # OTP Relay Readiness Gate (Invariant 9 — LINE variant, 2026-10-08):
            # A fresh Krungsri login ALWAYS triggers an SMS OTP. Never fire the SMS unless
            # the OTP relay is ready RIGHT NOW. The relay is the LINE channel (group
            # "a14s homelab" or the 1:1 operator chat): the backend gateway must be UP
            # (to receive the webhook) and a LINE push target must be configured.
            # Single source of truth: app.services.otp_relay_readiness
            # (shared with daily_readiness.py + Liberator).
            # Otherwise the OTP arrives but nobody can capture it -> 180s stall -> account-lock risk.
            from app.services.otp_relay_readiness import otp_relay_readiness
            # allow_kde_fallback=False (explicit): LINE is authoritative — the dormant KDE
            # path must NEVER satisfy this gate (LINE-RCA-009).
            readiness = await otp_relay_readiness.check(allow_kde_fallback=False)
            otp_channel = readiness.channel
            if not readiness.ready:
                self.status = "BRIDGE_DOWN"
                logger.error(
                    f"OTP Relay Readiness Gate: relay NOT ready ({readiness.reason}). "
                    "Aborting login BEFORE SMS trigger."
                )
                await self._log_event(
                    "LOGIN_BRIDGE_DOWN",
                    f"Login aborted before SMS OTP trigger — OTP relay not ready: {readiness.reason}",
                )
                return LoginResult(
                    success=False,
                    status=AuthStatus.BRIDGE_DOWN,
                    broker=BrokerPlatform.TRADEMAN,
                    resumed=False,
                    message=(
                        f"OTP relay (LINE) is not ready: {readiness.reason}. "
                        "SMS OTP was NOT triggered to avoid account lock."
                    ),
                    error_code="BRIDGE_DOWN",
                )

            # Step 2: Fill Username & Password
            await page.wait_for_selector("#login_username", state="visible", timeout=15000)
            await page.fill("#login_username", user)
            await asyncio.sleep(0.3)
            await page.fill("#login_password", passwd)
            await asyncio.sleep(0.3)

            # Step 3: Click Login
            logger.info("Submitting credentials form...")
            self.status = "CREDENTIALS_SUBMITTED"
            await page.click("#login")

            # Wait for response or navigation
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)

            # Step 4: Check if an alert dialog was raised (e.g. Invalid password)
            if self.last_dialog_message:
                error_msg = self.last_dialog_message
                self.last_dialog_message = None
                if any(k in error_msg for k in ["ไม่ถูกต้อง", "Invalid", "ผิดพลาด", "incorrect"]):
                    self.status = "FAILED"
                    await self._log_event("LOGIN_FAILED", f"Login rejected by Krungsri: {error_msg}")
                    await self.take_diagnostic_snapshot("login_error_dialog")
                    raise ValueError(f"Krungsri Login Rejected: {error_msg}")

            # LINE-RCA-009: honest attribution — which channel actually supplied the OTP.
            # Remains None when no 2FA prompt was reached (nothing to attribute).
            otp_source: Optional[str] = None

            # Step 5: Check for OTP prompt
            otp_detected, ref_code, otp_input_sel = await self._detect_otp_prompt(page)

            if otp_detected:
                self.status = "AWAITING_OTP"
                self.current_ref = ref_code
                logger.warning(
                    f"2FA SMS OTP required by Krungsri! Ref: '{ref_code}'. "
                    f"Waiting up to {otp_timeout}s for a LINE group / browser / manual entry..."
                )
                await self._log_event(
                    "OTP_REQUIRED",
                    f"Awaiting 2FA SMS OTP. Reference Code: {ref_code or 'N/A'}, Timeout: {otp_timeout}s"
                )

                # Ask the operator for the OTP in the LINE group ("a14s homelab").
                # Best-effort: a failed push must never abort the login flow.
                try:
                    from app.services.line_service import line_service
                    await line_service.push_otp_request(
                        ref=ref_code,
                        broker="KRUNGSRI",
                        timeout_seconds=int(otp_timeout),
                    )
                except Exception as e:
                    logger.warning(f"Could not push OTP request to LINE group: {e}")

                # Wait on EventBus OTP queue or SQLite DB cross-process logs
                wait_start_time = datetime.now(timezone.utc)
                try:
                    otp_val, otp_source = await self._wait_for_otp_multi_channel(
                        otp_timeout=int(otp_timeout),
                        wait_start_time=wait_start_time,
                        otp_input_sel=otp_input_sel,
                        channel=otp_channel,
                    )
                    logger.info(f"Received OTP '{redact_otp(otp_val)}' from {otp_source}! Submitting to Krungsri...")
                    
                    # Fill OTP if not already typed in browser DOM
                    if otp_source != "browser_dom_manual":
                        try:
                            await page.fill(otp_input_sel, otp_val)
                        except Exception:
                            # Fallback: type directly
                            await page.locator(otp_input_sel).press_sequentially(otp_val, delay=50)
                        await asyncio.sleep(0.3)

                    # Click OTP submit button
                    await self._click_otp_submit(page)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    await asyncio.sleep(2.0)

                except asyncio.TimeoutError:
                    self.status = "FAILED"
                    await self._log_event("OTP_TIMEOUT", f"Timed out after {otp_timeout}s waiting for OTP.")
                    await self.take_diagnostic_snapshot("otp_timeout")
                    raise TimeoutError(f"Timed out after {otp_timeout} seconds waiting for SMS OTP.")
                except TimeoutError:
                    self.status = "FAILED"
                    await self._log_event("OTP_TIMEOUT", f"Timed out after {otp_timeout}s waiting for OTP.")
                    await self.take_diagnostic_snapshot("otp_timeout")
                    raise
                    await self._log_event("OTP_TIMEOUT", f"Timed out after {otp_timeout}s waiting for OTP.")
                    await self.take_diagnostic_snapshot("otp_timeout")
                    raise


            # Step 6: Verify successful login and SSO to TradeMan
            # Krungsri member dashboard -> click TradeMan right sidebar button -> TradeMan redirect
            page = await self._verify_post_login(page)
            self.page = page

            # Step 7: Persist session cookies
            await self.context.storage_state(path=settings.SESSION_STATE_PATH)
            self.status = "AUTHENTICATED"
            self.last_heartbeat = datetime.now(timezone.utc)
            await self._log_event("LOGIN_SUCCESS", f"Authenticated successfully. URL: {page.url}")

            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.TRADEMAN,
                resumed=False,
                url=page.url,
                otp_ref=self.current_ref,
                otp_source=_safe_otp_source(otp_source),
                message="Login and session establishment completed successfully."
            )

        except Exception as e:
            self.status = "FAILED"
            await self.take_diagnostic_snapshot("login_exception")
            logger.error(f"Login failed: {e}", exc_info=True)
            raise

    async def _detect_otp_prompt(self, page: Page) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Scans current DOM for OTP input fields and Reference Code text.
        Returns: (is_otp_required, ref_code, input_selector)
        """
        possible_selectors = [
            "input[placeholder*='OTP' i]",
            "#otp",
            "input#otp",
            "input[name*='otp' i]",
            "input[id*='otp' i]",
            "#login_otp",
            "input#login_otp",
            "input[name='otp']",
            "input[type='text'][maxlength='6']",
            "input[type='tel'][maxlength='6']",
            "input#txtOTP",
            "input[name='txtOTP']"
        ]

        otp_input_sel = None
        for sel in possible_selectors:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                otp_input_sel = sel
                try:
                    await el.evaluate("e => { e.style.outline = '3px solid #10b981'; e.style.boxShadow = '0 0 12px #10b981'; }")
                except Exception:
                    pass
                break

        body_text = await page.inner_text("body") if page else ""
        otp_keywords = ["รหัสอ้างอิง", "Ref", "OTP", "One Time Password", "SMS OTP"]
        has_otp_text = any(k in body_text for k in otp_keywords)

        if not otp_input_sel and not has_otp_text:
            return False, None, None

        # Extract Ref Code using regex
        ref_code = None
        ref_match = re.search(r"(?:Ref(?:\.|erence)?|รหัสอ้างอิง)\s*[:：]?\s*([A-Za-z0-9]{3,8})", body_text, re.IGNORECASE)
        if ref_match:
            ref_code = ref_match.group(1).strip()

        # If selector not found by id/name but 6-digit text input exists
        if not otp_input_sel:
            text_inputs = await page.query_selector_all("input[type='text'], input[type='tel'], input[type='number']")
            for inp in text_inputs:
                if await inp.is_visible():
                    max_len = await inp.get_attribute("maxlength")
                    if max_len in ("6", "8", None):
                        otp_input_sel = "input[type='text']:visible, input[type='tel']:visible"
                        break

        return True, ref_code, otp_input_sel or "input[maxlength='6']"

    async def _wait_for_otp_multi_channel(
        self,
        otp_timeout: int,
        wait_start_time: datetime,
        otp_input_sel: Optional[str] = None,
        channel: str = "none",
    ) -> tuple[str, str]:
        """
        Awaits a 6-digit OTP from (in priority order):

        0. Browser DOM input (operator typed it into the visible Chrome window)
        1. In-memory EventBus queue (same process; direct API / webhook relay)
        2. SQLite ``session_logs`` (cross-process: the gateway's webhook wrote it)
        3. Active KDE Connect notifications / SMS packets

        ``channel`` is the authoritative relay channel returned by
        ``otp_relay_readiness.check()`` (``line_group`` / ``line_direct`` /
        ``kde_connect``). It GATES checks 2 and 3 (LINE-RCA-009):

        * check 2 accepts only the ``event_type`` belonging to that channel, and
        * check 3 (KDE) is SKIPPED entirely unless the channel IS ``kde_connect``.

        Before 2026-10-08 check 3 polled KDE unconditionally every 0.5s and silently won
        the race while LINE was meant to be authoritative — the OTP was captured with
        **no** ``LINE_OTP_RECEIVED`` row, so LINE delivery could never be proven.

        Fail-closed default: ``channel="none"`` disables checks 2 and 3, so an unknown
        channel can only ever be served by an operator-typed path.
        """
        from app.services.otp_relay_readiness import (
            channel_accepts_source,
            channel_allows_kde,
            channel_db_event_types,
            event_type_to_source,
        )
        from app.services.otp_relay_registry import broker_matches, parse_otp_broker

        # Broker Knowledge Isolation: this driver only ever serves Krungsri.
        driver_broker = "KRUNGSRI"

        end_time = time.time() + otp_timeout
        while time.time() < end_time:
            # Check 0: Has the user manually typed OTP into the browser in Headed mode?
            if self.page and not self.page.is_closed() and otp_input_sel:
                try:
                    curr_val = await self.page.input_value(otp_input_sel)
                    if curr_val and len(curr_val.strip()) == 6 and curr_val.strip().isdigit():
                        logger.info(f"Detected 6-digit OTP already typed in browser DOM: {redact_otp(curr_val.strip())}")
                        return curr_val.strip(), "browser_dom_manual"
                except Exception:
                    pass

            # Check 1: In-memory queue
            if not event_bus.otp_queue.empty():
                event = event_bus.otp_queue.get_nowait()
                # Support typed OTPPayload
                payload = event.get("payload")
                if isinstance(payload, OTPPayload):
                    if self.current_ref and payload.ref and payload.ref.upper() != self.current_ref.upper():
                        logger.warning(
                            f"Received OTP ref '{payload.ref}' does not match expected '{self.current_ref}'. "
                            "Proceeding leniently."
                        )
                    source_str = payload.source.value if hasattr(payload.source, "value") else str(payload.source)
                    if channel_accepts_source(channel, source_str):
                        # LINE-RCA-010: never consume the other broker's OTP.
                        if broker_matches(driver_broker, getattr(payload, "broker", None)):
                            return payload.otp, source_str
                        logger.info(
                            f"Ignoring queued OTP tagged for '{payload.broker}' — this driver is "
                            f"{driver_broker} (LINE-RCA-010); still waiting for its own OTP."
                        )
                    else:
                        logger.warning(
                            f"Ignoring queued OTP from '{source_str}' — channel '{channel}' is "
                            f"authoritative (LINE-RCA-009); still waiting for the {channel} OTP."
                        )

                data = event.get("data", {})
                otp_val = str(data.get("otp", "")).strip()
                if otp_val and len(otp_val) == 6:
                    ref_val = data.get("ref")
                    if self.current_ref and ref_val and ref_val.upper() != self.current_ref.upper():
                        logger.warning(
                            f"Received OTP ref '{ref_val}' does not match expected '{self.current_ref}'. "
                            "Proceeding leniently."
                        )
                    src_tag = data.get("source", "event_bus")
                    if channel_accepts_source(channel, src_tag):
                        # LINE-RCA-010: never consume the other broker's OTP.
                        if broker_matches(driver_broker, data.get("broker")):
                            return otp_val, src_tag
                        logger.info(
                            f"Ignoring queued OTP tagged for '{data.get('broker')}' — this driver is "
                            f"{driver_broker} (LINE-RCA-010); still waiting for its own OTP."
                        )
                    else:
                        logger.warning(
                            f"Ignoring queued OTP from '{src_tag}' — channel '{channel}' is "
                            f"authoritative (LINE-RCA-009); still waiting for the {channel} OTP."
                        )

            # Check 2: Database session_logs (cross-process) — GATED by the authoritative
            # channel (LINE-RCA-009): a LINE channel accepts ONLY `LINE_OTP_RECEIVED`,
            # a KDE channel accepts ONLY `KDECONNECT_OTP_RECEIVED`. An unknown channel
            # yields no event types → fail-closed (this check is skipped).
            allowed_event_types = channel_db_event_types(channel)
            if allowed_event_types:
                try:
                    async with AsyncSessionLocal() as db:
                        stmt = (
                            select(SessionLog)
                            .where(SessionLog.event_type.in_(list(allowed_event_types)))
                            .where(SessionLog.created_at >= wait_start_time)
                            .order_by(SessionLog.created_at.desc())
                            .limit(1)
                        )
                        res = await db.execute(stmt)
                        log_entry = res.scalar_one_or_none()
                        if log_entry and log_entry.details:
                            # LINE-RCA-010: ignore the OTHER broker's OTP row. An untagged
                            # row (legacy / KDE) stays acceptable — lenient, not fail-closed.
                            row_broker = parse_otp_broker(log_entry.details)
                            if not broker_matches(driver_broker, row_broker):
                                logger.info(
                                    f"Ignoring {log_entry.event_type} row tagged for '{row_broker}' — "
                                    f"this driver is {driver_broker} (LINE-RCA-010); still waiting."
                                )
                            else:
                                # LINE-RCA-002: tolerant pattern (single source of truth)
                                match = re.search(OTP_SESSION_LOG_PATTERN, log_entry.details)
                                if match:
                                    otp_val = match.group(1)
                                    # Honest attribution: tag derived from the row we actually read
                                    return otp_val, event_type_to_source(log_entry.event_type)
                except Exception as e:
                    logger.debug(f"DB check in OTP wait: {e}")

            # Check 3: Active KDE Connect notifications / SMS packets — DORMANT.
            # LINE-RCA-009: this poll used to run unconditionally every 0.5s and silently
            # win the race while LINE was authoritative (no LINE_OTP_RECEIVED row → LINE
            # delivery unprovable). It now runs ONLY when the authoritative channel IS
            # kde_connect (i.e. an operator explicitly re-enabled the fallback).
            if channel_allows_kde(channel):
                try:
                    from app.services.kdeconnect_service import kdeconnect_service
                    # U3 (KDE-RCA-005): anchor the journal scan to the moment we requested the
                    # OTP, so a late/Doze-delayed SMS push is still captured.
                    kde_payload = await kdeconnect_service.poll_active_notifications(
                        expected_ref=self.current_ref,
                        since_ms=int(wait_start_time.timestamp() * 1000),
                    )
                    if kde_payload and kde_payload.otp:
                        logger.info(f"Direct KDE Connect capture in driver: {kde_payload.masked_otp} (Ref: {kde_payload.ref})")
                        return kde_payload.otp, "kdeconnect_direct"
                except Exception as e:
                    logger.debug(f"KDE Connect direct poll in driver: {e}")

            await asyncio.sleep(0.5)

        raise TimeoutError(f"Timed out after {otp_timeout} seconds waiting for SMS OTP.")

    async def _click_otp_submit(self, page: Page) -> None:
        """Finds and clicks OTP submit/confirm button."""

        submit_selectors = [
            "input[type='submit'][value*='ยืนยัน']",
            "form[action*='OTP_SMS_verify'] input[type='submit']",
            "button:has-text('ยืนยัน')",
            "button:has-text('Confirm')",
            "button:has-text('ตกลง')",
            "input[type='submit'][value*='Confirm']",
            "input[type='button'][value*='ยืนยัน']",
            "button[type='submit']",
            "input#btnConfirm",
            "input#btnSubmit",
            "input[type='submit']"
        ]
        for sel in submit_selectors:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                logger.info(f"Clicking OTP submit button with selector: {sel}")
                await btn.click()
                return

        # Fallback: press Enter on the active input
        logger.warning("OTP submit button not identified by selector, pressing Enter...")
        await page.keyboard.press("Enter")

    async def _verify_post_login(self, page: Page) -> Page:
        """
        Verifies login success. On Krungsri Securities portal:
        1. Dismisses any announcement / 'รับทราบ' popups.
        2. Clicks the TradeMan SSO button on the right sidebar (or opens start_SSO.aspx?page=TM).
        3. Captures the TradeMan popup / tab or follows redirect into trademan.in.th.
        4. Validates #dropDownAccountPort in the DOM.
        """
        active_page = page
        logger.info(f"Verifying post-login state. Current URL: {active_page.url}")

        if "login" in active_page.url.lower() and "check_login" not in active_page.url.lower():
            try:
                body_text = await active_page.inner_text("body")
                if any(err in body_text for err in ["ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง", "Invalid"]):
                    raise ValueError("Login failed: Krungsri indicated incorrect credentials.")
            except Exception:
                pass

        # 1. Dismiss announcement modal if present on Krungsri portal
        try:
            ack_btn = await active_page.query_selector("text='รับทราบ', button:has-text('รับทราบ'), a:has-text('รับทราบ'), input[value*='รับทราบ']")
            if ack_btn and await ack_btn.is_visible():
                logger.info("Found announcement 'รับทราบ' button on Krungsri portal, dismissing...")
                await ack_btn.click()
                await active_page.wait_for_timeout(1500)
        except Exception as e:
            logger.debug(f"Announcement dismiss check: {e}")

        # 2. If currently on Krungsri portal (krungsrisecurities.com), trigger TradeMan SSO via right sidebar button
        if "krungsrisecurities.com" in active_page.url.lower():
            logger.info("On Krungsri Securities member portal. Locating TradeMan SSO DOM element on right sidebar...")
            trademan_selectors = [
                "a[href*='start_SSO.aspx?page=TM']",
                "a[title*='Trademan']",
                "img[alt*='Trademan']",
                "img[src*='prelog_icon_10_tm']",
                "#icon_r12_c1",
                "a:has-text('Trademan')"
            ]

            trademan_clicked = False
            for sel in trademan_selectors:
                try:
                    loc = active_page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        logger.info(f"Found TradeMan SSO element with selector '{sel}', clicking...")
                        try:
                            # Expect popup or new tab triggered by window.open
                            async with active_page.expect_popup(timeout=8000) as popup_info:
                                await loc.click()
                            new_page = await popup_info.value
                            logger.info(f"TradeMan SSO popup opened: {redact_url(new_page.url)}")
                            active_page = new_page
                            trademan_clicked = True
                            break
                        except Exception as e:
                            logger.debug(f"Popup expect timed out or handled in-place with {sel}: {e}")
                            await loc.click()
                            await active_page.wait_for_timeout(3000)
                            trademan_clicked = True
                            break
                except Exception as ex:
                    logger.debug(f"Error trying selector {sel}: {ex}")

            # Check if any new page opened in the browser context
            for p in self.context.pages:
                if "trademan.in.th" in p.url.lower() or "start_sso.aspx" in p.url.lower():
                    logger.info(f"Detected TradeMan/SSO page in context: {p.url}")
                    active_page = p
                    trademan_clicked = True
                    try:
                        await active_page.bring_to_front()
                    except Exception:
                        pass
                    break

            # If still on Krungsri and not redirected, try clicking via JS popup function
            if not trademan_clicked and "krungsrisecurities.com" in active_page.url.lower():
                logger.info("Attempting JS popup call to start_SSO.aspx?page=TM...")
                try:
                    await active_page.evaluate("popup('../../th/efin/start_SSO.aspx?page=TM','',1200,800)")
                    await active_page.wait_for_timeout(3000)
                    for p in self.context.pages:
                        if "trademan.in.th" in p.url.lower() or "start_sso.aspx" in p.url.lower():
                            active_page = p
                            trademan_clicked = True
                            await active_page.bring_to_front()
                            break
                except Exception as e:
                    logger.debug(f"JS popup trigger: {e}")

        # 3. Wait for TradeMan SSO redirection to finish naturally
        logger.info(f"Waiting for TradeMan redirection and Nuxt hydration. Current URL: {active_page.url}")
        for _ in range(30):
            await active_page.wait_for_timeout(1000)
            # Scan context pages for trademan
            for p in self.context.pages:
                if "trademan.in.th" in p.url.lower() and "signin" not in p.url.lower():
                    active_page = p
                    break
            # Wait until it moves past openId / efin SSO into actual TradeMan page
            if "trademan.in.th" in active_page.url.lower() and "openid" not in active_page.url.lower() and "signin" not in active_page.url.lower():
                break

        # 3.1 Dismiss any blocking popups (What's new modal dialog - handles multiple stacked overlays)
        if "trademan.in.th" in active_page.url.lower():
            logger.info("TradeMan page active. Handling What's news modal popups...")
            for _ in range(5):
                try:
                    # Check all disable_show checkboxes via DOM evaluate
                    await active_page.evaluate('''() => {
                        document.querySelectorAll("input.disable_show, input[type='checkbox']").forEach(cb => {
                            try { if (!cb.checked) cb.click(); } catch(e) {}
                        });
                        document.querySelectorAll(".v-overlay--active .absolute.top-3.right-3 button, .v-overlay--active button").forEach(btn => {
                            try { btn.click(); } catch(e) {}
                        });
                    }''')
                except Exception:
                    pass

                # Also press Escape to close Vuetify dialogs
                try:
                    await active_page.keyboard.press("Escape")
                except Exception:
                    pass

                await active_page.wait_for_timeout(500)
                # Check if overlays still present
                overlay_count = await active_page.evaluate('''() => document.querySelectorAll(".v-overlay--active .v-dialog").length''')
                if overlay_count == 0:
                    break

            await popup_manager.dismiss_popups(active_page, max_rounds=2)

        # 3.2 Ensure navigation to TradeMan Portfolio tab where #dropDownAccountPort lives
        if "trademan.in.th" in active_page.url.lower() and "portfolio" not in active_page.url.lower():
            logger.info(f"Currently at {active_page.url}. Switching directly to Portfolio tab: {settings.TRADEMAN_PORTFOLIO_URL} ...")
            try:
                port_link = await active_page.query_selector("#Menu_Portfolio_tab a, a[href*='Portfolio'], a:has-text('Portfolio')")
                if port_link and await port_link.is_visible():
                    await port_link.click(force=True)
                    await active_page.wait_for_timeout(2000)
            except Exception:
                pass

            if "portfolio" not in active_page.url.lower():
                try:
                    await active_page.goto(settings.TRADEMAN_PORTFOLIO_URL, wait_until="domcontentloaded", timeout=15000)
                    await active_page.wait_for_timeout(2000)
                except Exception as ge:
                    logger.warning(f"Portfolio goto navigation error: {ge}")

            await popup_manager.dismiss_popups(active_page, max_rounds=2)

        # 4. Strict DOM Validation with Watch-and-Learn HITL Grace Period (90s)
        account_btn = None
        try:
            account_btn = await active_page.wait_for_selector("#dropDownAccountPort, .account-selector", state="visible", timeout=6000)
            if account_btn:
                logger.info("TradeMan Portfolio account selector (#dropDownAccountPort) visible! SSO session verified.")
                try:
                    await active_page.bring_to_front()
                except Exception:
                    pass
        except Exception:
            pass

        # If not visible yet, scan all open tabs/pages in context
        if not account_btn:
            for p in self.context.pages:
                try:
                    btn = await p.query_selector("#dropDownAccountPort, .account-selector")
                    if btn and await btn.is_visible():
                        active_page = p
                        account_btn = btn
                        logger.info(f"TradeMan Portfolio detected on context page: {p.url}")
                        break
                except Exception:
                    pass

        # If still not found, enter Watch-and-Learn Human-In-The-Loop (HITL) mode for up to 90 seconds
        if not account_btn:
            logger.warning(
                "👀 [Watch-and-Learn HITL]: เข้าสู่โหมดร่วมมือกับผู้ใช้ — "
                "หน้าต่าง Chrome เปิดอยู่บนหน้าจอ กรุณาช่วยคลิกปุ่ม TradeMan / เข้าสู่ระบบบนหน้าจอจริง (มีเวลา 90 วินาที)..."
            )
            # Push mobile escalation alert via KDE Connect
            try:
                from app.services.kdeconnect_service import kdeconnect_service
                await kdeconnect_service.notify_admin_screen_help(
                    reason="ช่วยคลิกปุ่ม TradeMan บนหน้าจอกรุงศรีให้หน่อยครับ (ระบบเปิดเบราว์เซอร์รออยู่ 90 วิ)",
                    workflow_or_step="TradeMan SSO Login"
                )
            except Exception as e:
                logger.debug(f"KDE Connect HITL notification error: {e}")

            hitl_start = time.time()
            while time.time() - hitl_start < 90:
                await asyncio.sleep(1.0)
                
                # Check active_page
                try:
                    btn = await active_page.query_selector("#dropDownAccountPort, .account-selector")
                    if btn and await btn.is_visible():
                        account_btn = btn
                        logger.info(f"🎉 ตรวจพบ TradeMan Portfolio (#dropDownAccountPort) สำเร็จบน active page! (URL: {active_page.url})")
                        break
                except Exception:
                    pass

                # If on trademan but not on Portfolio, attempt goto Portfolio
                if "trademan.in.th" in active_page.url.lower() and "portfolio" not in active_page.url.lower():
                    try:
                        logger.info(f"Redirecting active page from {active_page.url} to Portfolio...")
                        await active_page.goto(settings.TRADEMAN_PORTFOLIO_URL, wait_until="domcontentloaded", timeout=8000)
                        await active_page.wait_for_timeout(1500)
                    except Exception:
                        pass

                # Check all tabs in context in case click spawned a new tab/window
                for p in self.context.pages:
                    try:
                        btn = await p.query_selector("#dropDownAccountPort, .account-selector")
                        if btn and await btn.is_visible():
                            active_page = p
                            account_btn = btn
                            logger.info(f"🎉 ตรวจพบ TradeMan Portfolio สำเร็จในแท็บใหม่! (URL: {p.url})")
                            break
                    except Exception:
                        pass

                if account_btn:
                    break

        if not account_btn:
            logger.error(f"Could not find #dropDownAccountPort within 90s grace period! URL: {active_page.url}")
            self.page = active_page
            await self.take_diagnostic_snapshot("trademan_sso_failed")
            raise RuntimeError(f"TradeMan SSO verification failed: #dropDownAccountPort not visible after login. Current URL: {active_page.url}")

        # 5. Check and dismiss any promotional popups or banners via Hybrid AI
        await popup_manager.dismiss_popups(active_page)
        self.page = active_page
        tab_manager.register_tab("trademan", active_page)
        await tab_manager.scan_and_sync(self.context)
        logger.info(f"TradeMan successfully authenticated and loaded! Final URL: {active_page.url}")
        return active_page

    async def smart_keepalive(self) -> Dict[str, Any]:
        """
        Smart Keep-Alive Heartbeat:
        Touches active Krungsri Portal and TradeMan tabs during Thai market hours
        (09:30 - 17:00 ICT, Monday-Friday) to prevent 15-30 min idle session timeouts.
        """
        from datetime import timedelta
        # UTC+7 Bangkok Time
        ict_now = datetime.now(timezone(timedelta(hours=7)))
        is_weekday = ict_now.weekday() < 5
        market_open = ict_now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = ict_now.replace(hour=17, minute=0, second=0, microsecond=0)
        is_market_hours = is_weekday and (market_open <= ict_now <= market_close)

        results = await tab_manager.ping_keepalive()
        self.last_heartbeat = datetime.now(timezone.utc)
        return {
            "timestamp": self.last_heartbeat.isoformat(),
            "is_market_hours": is_market_hours,
            "ping_results": results,
            "active_tabs": tab_manager.list_active_tabs()
        }

    async def take_diagnostic_snapshot(self, prefix: str = "snapshot") -> Dict[str, str]:
        """Captures screenshot and HTML dump for debugging."""
        os.makedirs("data", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = f"data/{prefix}_{timestamp}.png"
        html_path = f"data/{prefix}_{timestamp}.html"

        if self.page:
            try:
                await self.page.screenshot(path=img_path, full_page=True)
                html_content = await self.page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"Diagnostic snapshot saved: {img_path} & {html_path}")
                return {"screenshot": img_path, "html": html_path}
            except Exception as e:
                logger.error(f"Failed to capture diagnostic snapshot: {e}")
        return {}

    async def close(self) -> None:
        """Gracefully closes browser and cleans up resources."""
        async with self._lock:
            self.status = "DISCONNECTED"
            try:
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
            except Exception as e:
                logger.warning(f"Error while closing Playwright driver: {e}")
            finally:
                self.page = None
                self.context = None
                self.browser = None
                self.playwright = None
            logger.info("Playwright browser closed.")


# Global singleton instance for the application
auth_driver = KrungsriAuthDriver()
