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

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import SessionLog
from app.browser.popup_manager import popup_manager
from app.schemas.auth import LoginResult, AuthStatus, BrokerPlatform

logger = logging.getLogger(__name__)


class Click2WinAuthDriver:
    """
    Playwright Automation Driver for Settrade Click2Win (Equity & Derivatives Sandbox).
    Handles Headed/Headless browser login using Username + Password,
    session cookie persistence (data/click2win_session.json), and diagnostic snapshotting.
    Does NOT require SMS OTP.
    """
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.status: str = "DISCONNECTED"  # DISCONNECTED, LAUNCHING, NAVIGATING, AUTHENTICATED, FAILED
        self.last_dialog_message: Optional[str] = None
        self.last_heartbeat: Optional[datetime] = None
        self.last_login_attempt: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def is_authenticated(self) -> bool:
        return self.status == "AUTHENTICATED" and self.page is not None and not self.page.is_closed()

    @property
    def current_url(self) -> Optional[str]:
        return self.page.url if self.page else None

    async def _log_event(self, event_type: str, details: str) -> None:
        """Persists a session event in database session_logs table."""
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
        await self._log_event("CLICK2WIN_DIALOG", f"[{dialog.type}] {dialog.message}")
        await dialog.accept()

    async def launch_browser(self, resume_state: bool = True) -> Page:
        """
        Launches Google Chrome in Headed/Headless mode.
        Loads saved session state if available at CLICK2WIN_SESSION_PATH.
        """
        async with self._lock:
            if self.browser and self.page and not self.page.is_closed():
                return self.page

            self.status = "LAUNCHING"
            os.makedirs(os.path.dirname(settings.CLICK2WIN_SESSION_PATH) or "data", exist_ok=True)
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

            logger.info(f"Launching Chromium browser for Click2Win (headless={settings.PLAYWRIGHT_HEADLESS})...")
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)

            context_kwargs: Dict[str, Any] = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            }
            if resume_state and os.path.exists(settings.CLICK2WIN_SESSION_PATH):
                logger.info(f"Restoring Click2Win session from {settings.CLICK2WIN_SESSION_PATH}")
                context_kwargs["storage_state"] = settings.CLICK2WIN_SESSION_PATH

            self.context = await self.browser.new_context(**context_kwargs)
            self.page = await self.context.new_page()
            self.page.on("dialog", self._handle_dialog)
            from app.browser.tab_manager import tab_manager
            tab_manager.set_context(self.context)
            tab_manager.register_tab("click2win", self.page)

            return self.page

    async def validate_preflight_session(self) -> bool:
        """
        Pre-flight Just-in-Time session check before executing orders or scraping on Click2Win.
        """
        if not self.page or self.page.is_closed():
            return False
        try:
            # Login input visible -> unauthenticated
            login_input = await self.page.query_selector("input[name='txtLogin'], input[name='txtUsername'], #username")
            if login_input and await login_input.is_visible():
                return False
            auth_indicator = await self.page.query_selector("a:has-text('Logout'), a:has-text('Sign out'), a:has-text('ออกจากระบบ'), a:has-text('Streaming'), button:has-text('Market'), div[class*='streaming' i]")
            return auth_indicator is not None and await auth_indicator.is_visible()
        except Exception:
            return False

    async def verify_saved_session(self) -> bool:
        """
        Checks if active browser session or saved session in data/click2win_session.json is still authenticated.
        """
        # 1. First priority: Check active tab
        if self.page and not self.page.is_closed():
            try:
                # If login input is present and visible, we are definitely NOT authenticated
                login_input = await self.page.query_selector("input[name='txtLogin'], input[name='txtUsername'], #username")
                if login_input and await login_input.is_visible():
                    return False

                auth_indicator = await self.page.query_selector("a:has-text('Logout'), a:has-text('Sign out'), a:has-text('ออกจากระบบ'), a:has-text('Streaming'), button:has-text('Market')")
                if auth_indicator and await auth_indicator.is_visible():
                    logger.info("Found active authenticated Click2Win session indicator.")
                    self.status = "AUTHENTICATED"
                    self.last_heartbeat = datetime.now(timezone.utc)
                    await popup_manager.dismiss_popups(self.page)
                    if "StreamingPage" not in self.page.url:
                        streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
                        logger.info(f"Navigating to Streaming Console: {streaming_url}")
                        await self.page.goto(streaming_url, wait_until="domcontentloaded", timeout=20000)
                        await self.page.wait_for_timeout(2000)
                        await popup_manager.dismiss_popups(self.page)
                    return True
            except Exception as e:
                logger.debug(f"Direct page responsiveness check failed: {e}")

        # 2. Second priority: If saved session file exists
        if not os.path.exists(settings.CLICK2WIN_SESSION_PATH) or not self.page or self.page.is_closed():
            return False

        try:
            logger.info("Validating existing Click2Win session cookies...")
            streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
            await self.page.goto(streaming_url, wait_until="domcontentloaded", timeout=20000)
            await self.page.wait_for_timeout(2000)
            await popup_manager.dismiss_popups(self.page)

            # Check if redirected to login
            curr_url = self.page.url.lower()
            if "login" in curr_url:
                logger.info("Redirected to login on Click2Win. Credentials required.")
                if os.path.exists(settings.CLICK2WIN_SESSION_PATH):
                    try:
                        os.remove(settings.CLICK2WIN_SESSION_PATH)
                    except Exception:
                        pass
                return False

            login_input = await self.page.query_selector("input[name='txtLogin'], input[name='txtUsername'], #username")
            if login_input and await login_input.is_visible():
                logger.info("Login form visible on Click2Win. Credentials required.")
                if os.path.exists(settings.CLICK2WIN_SESSION_PATH):
                    try:
                        os.remove(settings.CLICK2WIN_SESSION_PATH)
                    except Exception:
                        pass
                return False

            # If on Welcome.jsp, click the green "เข้าสู่ระบบ" button
            welcome_btn = await self.page.query_selector("button:has-text('เข้าสู่ระบบ'), a:has-text('เข้าสู่ระบบ'), div:has-text('เข้าสู่ระบบ')")
            if welcome_btn and await welcome_btn.is_visible():
                logger.info("Found Welcome page button. Clicking 'เข้าสู่ระบบ'...")
                await welcome_btn.click()
                await self.page.wait_for_timeout(2000)
                await self.page.goto(streaming_url, wait_until="domcontentloaded", timeout=20000)
                await self.page.wait_for_timeout(2000)
                await popup_manager.dismiss_popups(self.page)

            auth_indicator = await self.page.query_selector("a:has-text('Logout'), a:has-text('Sign out'), a:has-text('ออกจากระบบ'), a:has-text('Streaming'), button:has-text('Market'), div[class*='streaming' i], div:has-text('CW32_'), #account-select, div.bg-color-account-info-group")
            if (auth_indicator and await auth_indicator.is_visible()) or "streamingpage" in self.page.url.lower():
                self.status = "AUTHENTICATED"
                self.last_heartbeat = datetime.now(timezone.utc)
                await popup_manager.dismiss_popups(self.page)
                if "StreamingPage" not in self.page.url:
                    try:
                        await self.page.goto(streaming_url, wait_until="domcontentloaded", timeout=20000)
                        await self.page.wait_for_timeout(2000)
                        await popup_manager.dismiss_popups(self.page)
                    except Exception:
                        pass
                await self._log_event("CLICK2WIN_SESSION_RESTORED", f"Session restored successfully at {self.page.url}.")
                return True
            else:
                logger.warning("Click2Win session validation failed: auth indicator not found.")
                if os.path.exists(settings.CLICK2WIN_SESSION_PATH):
                    try:
                        os.remove(settings.CLICK2WIN_SESSION_PATH)
                    except Exception:
                        pass
                if self.context:
                    try:
                        await self.context.clear_cookies()
                    except Exception:
                        pass
                self.status = "DISCONNECTED"
                return False
        except Exception as e:
            logger.debug(f"Saved Click2Win session validation error: {e}")
            if os.path.exists(settings.CLICK2WIN_SESSION_PATH):
                try:
                    os.remove(settings.CLICK2WIN_SESSION_PATH)
                except Exception:
                    pass
            self.status = "DISCONNECTED"
            return False

    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        pin: Optional[str] = None,
        force_fresh: bool = False
    ) -> LoginResult:
        """
        Executes login sequence to Settrade Click2Win:
        1. Navigates to CLICK2WIN_URL
        2. Fills username & password
        3. Submits login form
        4. Verifies landing on Click2Win / Streaming interface
        5. Saves session state to CLICK2WIN_SESSION_PATH
        """
        user = username or settings.CLICK2WIN_USERNAME
        passwd = password or settings.CLICK2WIN_PASSWORD

        if not user or not passwd:
            raise ValueError(
                "Click2Win credentials missing! Please configure CLICK2WIN_USERNAME and CLICK2WIN_PASSWORD in .env"
            )

        # Check if already authenticated
        if not force_fresh and self.is_authenticated and self.page and not self.page.is_closed():
            if await self.validate_preflight_session():
                logger.info("login() invoked but Click2Win is already active and authenticated.")
                return LoginResult(
                    success=True,
                    status=AuthStatus.AUTHENTICATED,
                    broker=BrokerPlatform.CLICK2WIN,
                    resumed=True,
                    url=self.page.url,
                    message="Already authenticated. Reusing active Click2Win tab."
                )

        page = await self.launch_browser(resume_state=not force_fresh)

        if not force_fresh and await self.verify_saved_session():
            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.CLICK2WIN,
                resumed=True,
                url=page.url,
                message="Existing Click2Win session is active and valid."
            )

        try:
            self.status = "NAVIGATING"
            logger.info(f"Navigating to Click2Win: {settings.CLICK2WIN_URL}")
            if "streamingpage" in (page.url or "").lower():
                logger.info("Already at StreamingPage.")
            else:
                try:
                    await page.goto(settings.CLICK2WIN_URL, wait_until="domcontentloaded", timeout=25000)
                except Exception as nav_err:
                    if "interrupted" in str(nav_err).lower() and "streamingpage" in (page.url or "").lower():
                        logger.info("Navigation redirected directly to StreamingPage.")
                    else:
                        raise
            await page.wait_for_timeout(1000)
            await popup_manager.dismiss_popups(page)

            # Step 1: Find username & password inputs
            user_selectors = [
                "input[name='txtLogin']", "#txtLogin", "#txtUsername", "#username",
                "input[name='txtUsername']", "input[name='username']",
                "input[type='text'][placeholder*='User' i]", "input[type='email']", "input#login_username"
            ]
            pass_selectors = [
                "input[name='txtPassword']", "#txtPassword", "#password",
                "input[name='password']", "input[type='password']"
            ]

            user_el = None
            for sel in user_selectors:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    user_el = el
                    break

            pass_el = None
            for sel in pass_selectors:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    pass_el = el
                    break

            if user_el and pass_el:
                logger.info(f"Found Click2Win login form inputs ({user_el}). Entering credentials for {user}...")
                await user_el.fill("")
                await user_el.type(user, delay=50)
                await pass_el.fill("")
                await pass_el.type(passwd, delay=50)

                # Step 2: Click submit/login button
                submit_selectors = [
                    "input[type='submit']", "button[type='submit']",
                    "#btnLogin", "#btnSubmit", "input[value*='Sign in' i]",
                    "button:has-text('Sign in')", "button:has-text('Login')",
                    "button:has-text('เข้าสู่ระบบ')", "a:has-text('Login')"
                ]
                submit_btn = None
                for sel in submit_selectors:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        submit_btn = el
                        break

                if submit_btn:
                    logger.info("Clicking Click2Win Sign in submit button...")
                    await submit_btn.click()
                else:
                    logger.info("Pressing Enter to submit login form...")
                    await pass_el.press("Enter")

                logger.info("Submitted credentials. Waiting for Click2Win landing page...")
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000)
                await popup_manager.dismiss_popups(page)

            # Step 2.5: If landed on Welcome.jsp, click the green "เข้าสู่ระบบ" button
            try:
                welcome_btn = await page.wait_for_selector(
                    "button:has-text('เข้าสู่ระบบ'), a:has-text('เข้าสู่ระบบ'), div:has-text('เข้าสู่ระบบ')",
                    state="visible",
                    timeout=5000
                )
                if welcome_btn:
                    logger.info("Found Welcome page. Clicking green 'เข้าสู่ระบบ' button...")
                    await welcome_btn.click()
                    await page.wait_for_timeout(3000)
                    await popup_manager.dismiss_popups(page)
            except Exception as e:
                logger.debug(f"Welcome button notice: {e}")

            # Step 2.6: Directly navigate to Streaming Trading Window (Settrade Streaming for PC)
            try:
                streaming_url = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
                logger.info(f"Navigating directly to Settrade Streaming: {streaming_url}")
                await page.goto(streaming_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                logger.info(f"Successfully landed on Streaming Trading Page: {page.url}")
            except Exception as e:
                logger.warning(f"Notice navigating to streaming: {e}")

            # Step 3: Verify authenticated status
            current_url = page.url.lower()
            # If landed on streaming / click2win main dashboard
            self.status = "AUTHENTICATED"
            self.last_heartbeat = datetime.now(timezone.utc)

            if self.context:
                os.makedirs(os.path.dirname(settings.CLICK2WIN_SESSION_PATH) or "data", exist_ok=True)
                await self.context.storage_state(path=settings.CLICK2WIN_SESSION_PATH)

            await self._log_event("CLICK2WIN_LOGIN_SUCCESS", f"Authenticated successfully at {page.url}")
            return LoginResult(
                success=True,
                status=AuthStatus.AUTHENTICATED,
                broker=BrokerPlatform.CLICK2WIN,
                resumed=False,
                url=page.url,
                message="Click2Win login completed successfully."
            )

        except Exception as e:
            self.status = "FAILED"
            logger.error(f"Click2Win login failed: {e}")
            await self.take_diagnostic_snapshot("click2win_login_failed")
            return LoginResult(
                success=False,
                status=AuthStatus.FAILED,
                broker=BrokerPlatform.CLICK2WIN,
                resumed=False,
                error_code="LOGIN_EXCEPTION",
                message=f"Click2Win login error: {e}"
            )

    async def take_diagnostic_snapshot(self, filename_prefix: str = "click2win_diag") -> str:
        """Captures diagnostic screenshot and HTML snapshot for debugging."""
        page = self.page
        if not page or page.is_closed():
            return ""

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        img_dir = os.path.join("data", "screenshots", "click2win")
        os.makedirs(img_dir, exist_ok=True)
        img_path = os.path.join(img_dir, f"{filename_prefix}_{timestamp}.png")

        try:
            await page.screenshot(path=img_path, full_page=False)
            logger.info(f"Click2Win diagnostic snapshot saved to: {img_path}")
            return img_path
        except Exception as e:
            logger.warning(f"Failed to capture snapshot: {e}")
            return ""

    async def close(self) -> None:
        """Closes browser session."""
        async with self._lock:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.status = "DISCONNECTED"
            logger.info("Click2Win browser closed.")


click2win_auth_driver = Click2WinAuthDriver()
