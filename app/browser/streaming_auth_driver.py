"""
Settrade Streaming (Krungsri SSO) Auth Driver.
=============================================
Playwright automation for the *live* Settrade Streaming trading console
(StreamingPage.jsp) reached via the Krungsri Securities member-portal SSO
(not Settrade direct 2FA).

Reuses ``app.browser.auth_driver.KrumsriAuthDriver`` (Krungsri portal login
#login_username / #login_password / #login + SMS OTP machinery) via subclassing,
but overrides the post-login step to click the **Streaming** SSO link instead of
TradeMan's ``start_SSO.aspx?page=TM``:

    popup('../../Put_SSO_Settrade.aspx?Page=streaming','',screen.width,screen.height)
    -> https://wma1.settrade.com/realtime/streaming7/StreamingPage.jsp

Session persistence uses ``settings.STREAMING_SESSION_PATH`` (data/streaming_session.json)
so the Streaming session never overwrites TradeMan's ``SESSION_STATE_PATH``.

NOTE: a live login triggers an SMS OTP, so this driver is never exercised headlessly
in the unit suite — it is code-only in Phase 1 (TASK-loop1-8).
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from playwright.async_api import (
    async_playwright,
    Page,
)

from app.browser.auth_driver import KrungsriAuthDriver, _safe_otp_source
from app.browser.popup_manager import popup_manager
from app.browser.tab_manager import tab_manager
from app.core.config import settings
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform

logger = logging.getLogger(__name__)

# Streaming SSO entry point on the Krungsri member portal (confirmed Phase 0 probe).
STREAMING_SSO_POPUP_JS = (
    "popup('../../Put_SSO_Settrade.aspx?Page=streaming','',"
    "window.screen.width,window.screen.height)"
)
STREAMING_SSO_SELECTORS = [
    "a:has-text('โปรแกรม Streaming')",
    "a:has-text('Streaming')",
    "a[href*='Put_SSO_Settrade.aspx']",
    "a[href*='Page=streaming']",
    "img[alt*='Streaming' i]",
    "img[src*='streaming' i]",
]

# Order ticket presence is the strongest proof the Streaming console hydrated.
STREAMING_TICKET_SYMBOL_SELECTOR = "input[placeholder='Symbol']"


class StreamingAuthDriver(KrungsriAuthDriver):
    """
    Krungsri SSO -> Settrade Streaming auth driver.

    Inherits the Krungsri portal login + SMS OTP relay machinery from
    ``KrungsriAuthDriver`` (``_detect_otp_prompt``, ``_wait_for_otp_multi_channel``,
    ``_click_otp_submit``, OTP relay readiness gate) and only swaps the SSO target
    and the session file.
    """

    def __init__(self) -> None:
        super().__init__()
        # Keep Krungsri status vocabulary (DISCONNECTED/NAVIGATING/AWAITING_OTP/
        # AUTHENTICATED/FAILED); only the SSO target and session path differ.

    # ------------------------------------------------------------------
    # Browser launch / session persistence (Streaming session file)
    # ------------------------------------------------------------------

    async def launch_browser(self, resume_state: bool = True) -> Page:
        """Launch Chromium and restore the *Streaming* session file (never TradeMan's)."""
        async with self._lock:
            if self.browser and self.page and not self.page.is_closed():
                return self.page

            self.status = "LAUNCHING"
            os.makedirs(os.path.dirname(settings.STREAMING_SESSION_PATH) or "data", exist_ok=True)
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
                    "--use-mock-keychain",
                ],
            }
            if os.path.exists(settings.PLAYWRIGHT_CHROME_EXECUTABLE):
                launch_kwargs["executable_path"] = settings.PLAYWRIGHT_CHROME_EXECUTABLE

            logger.info(f"Launching Chromium for Settrade Streaming (headless={settings.PLAYWRIGHT_HEADLESS})...")
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)

            context_kwargs: Dict[str, Any] = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            }
            if resume_state and os.path.exists(settings.STREAMING_SESSION_PATH):
                logger.info(f"Restoring Streaming session from {settings.STREAMING_SESSION_PATH}")
                context_kwargs["storage_state"] = settings.STREAMING_SESSION_PATH

            self.context = await self.browser.new_context(**context_kwargs)
            self.page = await self.context.new_page()
            self.page.on("dialog", self._handle_dialog)
            tab_manager.set_context(self.context)
            tab_manager.register_tab("streaming", self.page)
            return self.page

    # ------------------------------------------------------------------
    # Session validation
    # ------------------------------------------------------------------

    async def _streaming_page_authenticated(self, page: Optional[Page]) -> bool:
        """True when `page` is on a hydrated StreamingPage.jsp order ticket."""
        if not page or page.is_closed():
            return False
        try:
            url = (page.url or "").lower()
            if "streamingpage" not in url:
                return False
            sym = await page.query_selector(STREAMING_TICKET_SYMBOL_SELECTOR)
            if sym and await sym.is_visible():
                return True
            pin = await page.query_selector("div.bg-color-account-info-group, input#pin")
            return bool(pin and await pin.is_visible())
        except Exception:
            return False

    async def validate_preflight_session(self) -> bool:
        """Pre-flight check used by login()'s reuse branch."""
        return await self._streaming_page_authenticated(self.page)

    def _quarantine_streaming_session(self) -> Optional[str]:
        """Non-destructively preserve a rejected Streaming session (Invariant 8 pattern)."""
        path = settings.STREAMING_SESSION_PATH
        if not os.path.exists(path):
            return None
        backup = f"{path}.stale.bak.json"
        try:
            os.replace(path, backup)
            logger.info(f"Quarantined rejected Streaming session -> {backup}")
            return backup
        except Exception as qe:
            logger.warning(f"Could not quarantine Streaming session (left intact): {qe}")
            return None

    async def verify_saved_session(self) -> bool:
        """Check active tab, then the saved session file, for a live StreamingPage."""
        # 1. Active tab
        if self.page and not self.page.is_closed():
            try:
                if await self._streaming_page_authenticated(self.page):
                    self.status = "AUTHENTICATED"
                    self.last_heartbeat = datetime.now(timezone.utc)
                    await popup_manager.dismiss_popups(self.page)
                    if self.context:
                        await self.context.storage_state(path=settings.STREAMING_SESSION_PATH)
                    return True
            except Exception as e:
                logger.debug(f"Active Streaming page check failed: {e}")

        # 2. Saved session file
        if not os.path.exists(settings.STREAMING_SESSION_PATH) or not self.page or self.page.is_closed():
            return False

        try:
            logger.info(f"Validating saved Streaming session against {settings.STREAMING_URL} ...")
            await self.page.goto(settings.STREAMING_URL, wait_until="domcontentloaded", timeout=20000)
            await self.page.wait_for_timeout(2000)
            await popup_manager.dismiss_popups(self.page)
            if await self._streaming_page_authenticated(self.page):
                self.status = "AUTHENTICATED"
                self.last_heartbeat = datetime.now(timezone.utc)
                if self.context:
                    os.makedirs(os.path.dirname(settings.STREAMING_SESSION_PATH) or "data", exist_ok=True)
                    await self.context.storage_state(path=settings.STREAMING_SESSION_PATH)
                await self._log_event("STREAMING_SESSION_RESTORED", f"Session restored at {self.page.url}")
                return True

            logger.warning("Streaming saved-session validation failed; session expired.")
            self._quarantine_streaming_session()
            self.status = "DISCONNECTED"
            return False
        except Exception as e:
            logger.warning(f"Saved Streaming session check error (file left intact): {e}")
            self.status = "DISCONNECTED"
            return False

    # ------------------------------------------------------------------
    # Post-login SSO (Streaming instead of TradeMan)
    # ------------------------------------------------------------------

    async def _verify_post_login(self, page: Page) -> Page:
        """
        After Krungsri portal login: click the 'โปรแกรม Streaming' SSO link,
        follow the popup/redirect to StreamingPage.jsp, and strictly validate
        the order-ticket symbol input before reporting success.
        """
        active_page = page
        logger.info(f"Verifying Streaming post-login state. Current URL: {active_page.url}")

        # 1. Dismiss announcement modal on the Krungsri portal
        try:
            ack_btn = await active_page.query_selector(
                "text='รับทราบ', button:has-text('รับทราบ'), a:has-text('รับทราบ'), input[value*='รับทราบ']"
            )
            if ack_btn and await ack_btn.is_visible():
                logger.info("Dismissing Krungsri portal announcement 'รับทราบ'...")
                await ack_btn.click()
                await active_page.wait_for_timeout(1500)
        except Exception as e:
            logger.debug(f"Announcement dismiss check: {e}")

        # 2. Already on StreamingPage (redirected straight through)
        if "streamingpage" in (active_page.url or "").lower():
            await popup_manager.dismiss_popups(active_page)
            tab_manager.register_tab("streaming", active_page)
            return active_page

        # 3. On Krungsri portal: click Streaming SSO element (expect popup)
        streaming_clicked = False
        if "krungsrisecurities.com" in (active_page.url or "").lower():
            logger.info("On Krungsri member portal. Locating 'โปรแกรม Streaming' SSO element...")
            for sel in STREAMING_SSO_SELECTORS:
                try:
                    loc = active_page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        logger.info(f"Found Streaming SSO element '{sel}', clicking...")
                        try:
                            async with active_page.expect_popup(timeout=8000) as popup_info:
                                await loc.click()
                            new_page = await popup_info.value
                            logger.info(f"Streaming SSO popup opened: {new_page.url}")
                            active_page = new_page
                            streaming_clicked = True
                            break
                        except Exception:
                            await loc.click()
                            await active_page.wait_for_timeout(3000)
                            streaming_clicked = True
                            break
                except Exception as ex:
                    logger.debug(f"Error trying Streaming SSO selector {sel}: {ex}")

        # 4. Scan all context pages for a Streaming console
        for p in self.context.pages:
            if "streamingpage" in p.url.lower() or "settrade" in p.url.lower():
                logger.info(f"Detected Streaming page in context: {p.url}")
                active_page = p
                streaming_clicked = True
                try:
                    await active_page.bring_to_front()
                except Exception:
                    pass
                break

        # 5. Fallback: JS popup() call (mirrors TradeMan's start_SSO fallback)
        if not streaming_clicked and "krungsrisecurities.com" in (active_page.url or "").lower():
            logger.info("Attempting JS popup call to Put_SSO_Settrade.aspx?Page=streaming...")
            try:
                await active_page.evaluate(STREAMING_SSO_POPUP_JS)
                await active_page.wait_for_timeout(3000)
                for p in self.context.pages:
                    if "streamingpage" in p.url.lower() or "settrade" in p.url.lower():
                        active_page = p
                        streaming_clicked = True
                        try:
                            await active_page.bring_to_front()
                        except Exception:
                            pass
                        break
            except Exception as e:
                logger.debug(f"JS popup trigger for Streaming SSO: {e}")

        # 6. Wait for StreamingPage.jsp to hydrate
        logger.info(f"Waiting for StreamingPage.jsp hydration. Current URL: {active_page.url}")
        for _ in range(40):
            await active_page.wait_for_timeout(1000)
            for p in self.context.pages:
                if "streamingpage" in p.url.lower():
                    active_page = p
                    break
            if "streamingpage" in (active_page.url or "").lower():
                break

        await popup_manager.dismiss_popups(active_page)

        # 7. Strict DOM validation: order-ticket symbol input must be visible
        sym_el = None
        try:
            sym_el = await active_page.wait_for_selector(
                STREAMING_TICKET_SYMBOL_SELECTOR, state="visible", timeout=10000
            )
        except Exception:
            sym_el = None

        if not sym_el:
            for p in self.context.pages:
                try:
                    el = await p.query_selector(STREAMING_TICKET_SYMBOL_SELECTOR)
                    if el and await el.is_visible():
                        active_page = p
                        sym_el = el
                        break
                except Exception:
                    pass

        if not sym_el:
            logger.error(f"Could not verify StreamingPage.jsp order ticket. URL: {active_page.url}")
            self.page = active_page
            await self.take_diagnostic_snapshot("streaming_sso_failed")
            raise RuntimeError(
                f"Streaming SSO verification failed: order-ticket symbol input not visible. "
                f"Current URL: {active_page.url}"
            )

        tab_manager.register_tab("streaming", active_page)
        await tab_manager.scan_and_sync(self.context)
        self.page = active_page
        logger.info(f"Settrade Streaming successfully authenticated and loaded! Final URL: {active_page.url}")
        return active_page

    # ------------------------------------------------------------------
    # Login (Krungsri portal + OTP + Streaming SSO + session persist)
    # ------------------------------------------------------------------

    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_otp: Optional[int] = None,
        force_fresh: bool = False,
    ) -> LoginResult:
        """
        Full Krungsri SSO -> Settrade Streaming login:
        1. Krungsri portal credentials (#login_username / #login_password / #login)
        2. SMS OTP relay (reuses KrungsriAuthDriver OTP machinery)
        3. Streaming SSO link -> StreamingPage.jsp
        4. Persist storage_state to settings.STREAMING_SESSION_PATH
        """
        user = username or settings.KRUNGSRI_USERNAME
        passwd = password or settings.KRUNGSRI_PASSWORD
        otp_timeout = timeout_otp or settings.OTP_TIMEOUT_SECONDS

        if not user or not passwd:
            raise ValueError(
                "Krungsri credentials missing! Please configure KRUNGSRI_USERNAME and KRUNGSRI_PASSWORD in .env"
            )

        # Priority 0: reuse active Streaming session
        if not force_fresh and self.is_authenticated and self.page and not self.page.is_closed():
            if await self.validate_preflight_session():
                logger.info("login() invoked but Streaming is already active and verified. Reusing tab.")
                return LoginResult(
                    success=True,
                    status=AuthStatus.AUTHENTICATED,
                    broker=BrokerPlatform.STREAMING,
                    resumed=True,
                    url=self.page.url,
                    message="Already authenticated. Reusing active Streaming tab.",
                )

        page = await self.launch_browser(resume_state=not force_fresh)

        if not force_fresh and await self.verify_saved_session():
            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.STREAMING,
                resumed=True,
                url=page.url,
                message="Existing Streaming session is active and valid.",
            )

        if force_fresh:
            logger.info("Fresh login requested. Purging previous Streaming session.")
            if os.path.exists(settings.STREAMING_SESSION_PATH):
                try:
                    os.remove(settings.STREAMING_SESSION_PATH)
                except Exception:
                    pass
            if self.context:
                try:
                    await self.context.clear_cookies()
                except Exception:
                    pass

        # Cooldown guard (mirrors auth_driver): prevent duplicate SMS triggers within 60s
        now = datetime.now(timezone.utc)
        if (
            self.last_login_attempt
            and (now - self.last_login_attempt).total_seconds() < 60
            and self.status in ["NAVIGATING", "AWAITING_OTP"]
        ):
            logger.warning("Streaming login already in progress within 60s cooldown. Skipping duplicate trigger.")
            return LoginResult(
                success=False,
                status=AuthStatus.AWAITING_OTP if self.status == "AWAITING_OTP" else AuthStatus.NAVIGATING,
                broker=BrokerPlatform.STREAMING,
                resumed=False,
                message="Login flow already in progress. Please await current attempt or OTP.",
            )
        self.last_login_attempt = now

        otp_source: Optional[str] = None
        try:
            # Step 1: Krungsri login page
            self.status = "NAVIGATING"
            logger.info(f"Navigating to login page: {settings.KRUNGSRI_LOGIN_URL}")
            await page.goto(settings.KRUNGSRI_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Already logged into Krungsri portal -> straight to Streaming SSO
            body_text = await page.inner_text("body")
            if any(k in body_text for k in ["ยินดีต้อนรับ", "ออกจากระบบ", "creditbalance_announcement"]) or "member" in page.url.lower():
                logger.info("User already logged into Krungsri portal! Proceeding to Streaming SSO...")
                page = await self._verify_post_login(page)
                self.page = page
                if self.context:
                    os.makedirs(os.path.dirname(settings.STREAMING_SESSION_PATH) or "data", exist_ok=True)
                    await self.context.storage_state(path=settings.STREAMING_SESSION_PATH)
                self.status = "AUTHENTICATED"
                self.last_heartbeat = datetime.now(timezone.utc)
                return LoginResult(
                    success=True,
                    status=AuthStatus.AUTHENTICATED,
                    broker=BrokerPlatform.STREAMING,
                    resumed=True,
                    url=page.url,
                    message="User was already authenticated; Streaming SSO completed.",
                )

            # OTP relay readiness gate (Invariant 9 — LINE variant)
            from app.services.otp_relay_readiness import otp_relay_readiness

            readiness = await otp_relay_readiness.check(allow_kde_fallback=False)
            otp_channel = readiness.channel
            if not readiness.ready:
                self.status = "BRIDGE_DOWN"
                await self._log_event(
                    "STREAMING_LOGIN_BRIDGE_DOWN",
                    f"Streaming login aborted before SMS OTP trigger — relay not ready: {readiness.reason}",
                )
                return LoginResult(
                    success=False,
                    status=AuthStatus.BRIDGE_DOWN,
                    broker=BrokerPlatform.STREAMING,
                    resumed=False,
                    error_code="BRIDGE_DOWN",
                    message=f"OTP relay (LINE) is not ready: {readiness.reason}. SMS OTP was NOT triggered.",
                )

            # Step 2: Fill credentials
            await page.wait_for_selector("#login_username", state="visible", timeout=15000)
            await page.fill("#login_username", user)
            await asyncio.sleep(0.3)
            await page.fill("#login_password", passwd)
            await asyncio.sleep(0.3)
            logger.info("Submitting Krungsri credentials form...")
            self.status = "CREDENTIALS_SUBMITTED"
            await page.click("#login")
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)

            # Step 3: Invalid-credentials dialog
            if self.last_dialog_message:
                error_msg = self.last_dialog_message
                self.last_dialog_message = None
                if any(k in error_msg for k in ["ไม่ถูกต้อง", "Invalid", "ผิดพลาด", "incorrect"]):
                    self.status = "FAILED"
                    await self._log_event("STREAMING_LOGIN_FAILED", f"Login rejected by Krungsri: {error_msg}")
                    await self.take_diagnostic_snapshot("streaming_login_error_dialog")
                    raise ValueError(f"Krungsri Login Rejected: {error_msg}")

            # Step 4: OTP prompt (reuse inherited detection/wait/submit)
            otp_detected, ref_code, otp_input_sel = await self._detect_otp_prompt(page)
            if otp_detected:
                self.status = "AWAITING_OTP"
                self.current_ref = ref_code
                logger.warning(
                    f"2FA SMS OTP required by Krungsri! Ref: '{ref_code}'. Waiting up to {otp_timeout}s..."
                )
                await self._log_event(
                    "STREAMING_OTP_REQUIRED",
                    f"Awaiting 2FA SMS OTP. Reference Code: {ref_code or 'N/A'}, Timeout: {otp_timeout}s",
                )
                try:
                    from app.services.line_service import line_service

                    await line_service.push_otp_request(
                        ref=ref_code, broker="KRUNGSRI", timeout_seconds=int(otp_timeout)
                    )
                except Exception as e:
                    logger.warning(f"Could not push OTP request to LINE group: {e}")

                wait_start_time = datetime.now(timezone.utc)
                try:
                    otp_val, otp_source = await self._wait_for_otp_multi_channel(
                        otp_timeout=int(otp_timeout),
                        wait_start_time=wait_start_time,
                        otp_input_sel=otp_input_sel,
                        channel=otp_channel,
                    )
                    logger.info(f"Received OTP from {otp_source}! Submitting to Krungsri...")
                    if otp_source != "browser_dom_manual":
                        try:
                            await page.fill(otp_input_sel, otp_val)
                        except Exception:
                            await page.locator(otp_input_sel).press_sequentially(otp_val, delay=50)
                        await asyncio.sleep(0.3)
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
                    await self._log_event("STREAMING_OTP_TIMEOUT", f"Timed out after {otp_timeout}s waiting for OTP.")
                    await self.take_diagnostic_snapshot("streaming_otp_timeout")
                    raise TimeoutError(f"Timed out after {otp_timeout} seconds waiting for SMS OTP.")
                except TimeoutError:
                    self.status = "FAILED"
                    await self._log_event("STREAMING_OTP_TIMEOUT", f"Timed out after {otp_timeout}s waiting for OTP.")
                    await self.take_diagnostic_snapshot("streaming_otp_timeout")
                    raise

            # Step 5: Streaming SSO -> StreamingPage.jsp
            page = await self._verify_post_login(page)
            self.page = page

            # Step 6: Persist Streaming session
            os.makedirs(os.path.dirname(settings.STREAMING_SESSION_PATH) or "data", exist_ok=True)
            await self.context.storage_state(path=settings.STREAMING_SESSION_PATH)
            self.status = "AUTHENTICATED"
            self.last_heartbeat = datetime.now(timezone.utc)
            await self._log_event("STREAMING_LOGIN_SUCCESS", f"Authenticated successfully. URL: {page.url}")

            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.STREAMING,
                resumed=False,
                url=page.url,
                otp_ref=self.current_ref,
                otp_source=_safe_otp_source(otp_source),
                message="Streaming login and session establishment completed successfully.",
            )

        except Exception as e:
            self.status = "FAILED"
            await self.take_diagnostic_snapshot("streaming_login_exception")
            logger.error(f"Streaming login failed: {e}", exc_info=True)
            return LoginResult(
                success=False,
                status=AuthStatus.FAILED,
                broker=BrokerPlatform.STREAMING,
                resumed=False,
                error_code="LOGIN_EXCEPTION",
                message=f"Streaming login error: {e}",
            )

    async def close(self) -> None:
        """Closes the Streaming browser session (reuses parent cleanup)."""
        await super().close()


# Global singleton for the application
streaming_auth_driver = StreamingAuthDriver()
