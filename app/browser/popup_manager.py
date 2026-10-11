"""
Adaptive Heuristic Popup Dismissal Engine (deterministic - no AI/Gemini).
Handles advertisement banners, promotional modals, and system alerts on TradeMan
using pure Playwright DOM selectors + keyboard fallback only.

Tiered dismissal (all offline / deterministic):
- Tier 0   : 'Connection Lost' dialog -> click 'Reconnect' (SPA websocket recovery).
- Tier 0.5 : 'Don't show again' checkbox.
- Tier 1   : Fast heuristic close/X button selectors.
- Tier 1.5 : Keyboard Escape / backdrop scrim click.
Unrecognized popups are left for the caller to escalate (HITL), never guessed.
"""

import asyncio
import logging
import os
from playwright.async_api import Page

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import SessionLog

logger = logging.getLogger(__name__)


class PopupManager:
    """
    Autonomous popup cleaner for Playwright browser sessions.
    Guarantees clean, unobstructed navigation for trading automation.
    """

    FAST_DISMISS_SELECTORS = [
        ".v-overlay .absolute.top-3.right-3 button",
        ".v-overlay .v-overlay__content button:has(svg)",
        ".v-overlay__content button:has(svg.nuxt-icon)",
        ".v-dialog button:has(svg)",
        "button:has-text('ปิด')",
        "button:has-text('รับทราบ')",
        "button:has-text('ตกลง')",
        "button:has-text('ยอมรับ')",
        "button:has-text('ไม่แสดงอีก')",
        "button:has-text('ข้าม')",
        "button:has-text('ยกเลิก')",
        "a:has-text('ปิด')",
        "a:has-text('รับทราบ')",
        "a:has-text('ยอมรับ')",
        "button[aria-label*='close' i]",
        "button[aria-label*='dismiss' i]",
        "button.v-btn--icon",
        ".v-dialog .v-btn--icon",
        ".trial-dialog button",
        "i[class*='close' i]",
        "svg[data-icon='close']",
        ".btn-close",
        ".close-button"
    ]

    # TradeMan 'Connection Lost' dialog recovery (KSS-RCA-012).
    # The 'Connection Lost' dialog has NO close/X button -- only a 'Reconnect'
    # button that re-establishes the SPA websocket. Pure-Playwright, deterministic,
    # no AI dependency. Proven runbook: learned_workflows/krungsri/trademan_session_reconnect.md
    RECONNECT_SELECTORS = [
        "button:has-text('Reconnect')",
        "button:has-text('เชื่อมต่อใหม่')",
        "button:has-text('ลองใหม่')",
        "button:has-text('ลองอีกครั้ง')",
        "button:has-text('Try again')",
        "button:has-text('Retry')",
    ]

    DONT_SHOW_AGAIN_SELECTORS = [
        "input.disable_show",
        "input[type='checkbox'].disable_show",
        "label[for='disable_show']",
        "label:has-text('ไม่ต้องแสดงอีก')",
        "span:has-text('ไม่ต้องแสดงอีก')",
        "input[type='checkbox']",
        "label:has-text('ไม่แสดงอีก')",
        "label:has-text('ไม่ต้องแสดง')",
        "label:has-text('ไม่ต้องแสดงในวันนี้')",
        "label:has-text('Do not show again')",
        "span:has-text('ไม่แสดงอีก')",
        "span:has-text('ไม่ต้องแสดงในวันนี้')",
        "span:has-text('Do not show again')",
        "div:has-text('ไม่ต้องแสดงอีก')",
        ".v-input--checkbox"
    ]

    OVERLAY_SELECTORS = [
        ".v-overlay--active",
        ".v-dialog--active",
        ".v-dialog",
        ".trial-dialog",
        "[role='dialog']",
        ".modal.show",
        ".fancybox-opened"
    ]

    async def _log_event(self, event_type: str, details: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                log_entry = SessionLog(event_type=event_type, details=details)
                db.add(log_entry)
                await db.commit()
        except Exception as e:
            logger.debug(f"PopupManager DB log failed: {e}")

    async def _is_page_open(self, page: Page) -> bool:
        if not page:
            return False
        try:
            if hasattr(page, "is_closed"):
                res = page.is_closed()
                if asyncio.iscoroutine(res):
                    res = await res
                return not bool(res)
            return True
        except Exception:
            return True

    async def is_overlay_present(self, page: Page) -> bool:
        """Checks whether an overlay or modal dialog is currently visible on screen."""
        if not await self._is_page_open(page):
            return False

        try:
            for sel in self.OVERLAY_SELECTORS:
                el = await page.query_selector(sel)
                if el:
                    is_vis = el.is_visible()
                    if asyncio.iscoroutine(is_vis):
                        is_vis = await is_vis
                    if is_vis:
                        return True
        except Exception:
            pass
        return False

    async def _check_dont_show_again(self, page: Page) -> bool:
        """
        Detects and checks 'Don't show again' / 'ไม่ต้องแสดงอีก' checkbox in active dialogs
        so that announcements/popups do not appear again.
        """
        for sel in self.DONT_SHOW_AGAIN_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el:
                    tag_name = await el.evaluate("el => el.tagName.toLowerCase()")
                    if tag_name == "input":
                        is_checked = await el.is_checked()
                        if not is_checked:
                            logger.info(f"Checking 'Don't show again' checkbox: {sel}")
                            await el.check(timeout=2000, force=True)
                            return True
                    else:
                        logger.info(f"Clicking 'Don't show again' option element: {sel}")
                        await el.click(timeout=2000, force=True)
                        return True
            except Exception:
                continue
        return False

    async def _reconnect_if_connection_lost(self, page: Page) -> bool:
        """
        Detects the TradeMan 'Connection Lost' dialog and clicks its 'Reconnect'
        button to re-establish the SPA websocket.

        Unlike a plain close/X button, 'Reconnect' is the CORRECT action for this
        dialog. This is a pure Playwright/selector recovery path (no Gemini
        Vision), so it survives Vision rate-limits (429) / outages (503).
        Ref: KSS-RCA-012, learned_workflows/krungsri/trademan_session_reconnect.md
        """
        if not await self._is_page_open(page):
            return False
        for sel in self.RECONNECT_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    logger.info(f"'Connection Lost' dialog detected. Clicking reconnect: {sel}")
                    await btn.click(timeout=5000, force=True)
                    await page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue
        return False

    async def dismiss_popups(self, page: Page, max_rounds: int = 2) -> bool:
        """
        Main entrypoint: Detects and clears any popups currently blocking the page.
        Returns True if at least one popup was dismissed.
        """
        if not await self._is_page_open(page):
            return False

        dismissed_any = False

        for round_idx in range(max_rounds):
            has_overlay = await self.is_overlay_present(page)
            if not has_overlay:
                break

            logger.info(f"Popup / Overlay detected on screen (Round {round_idx + 1}). Attempting dismissal...")

            # Tier 0: TradeMan 'Connection Lost' -> click 'Reconnect' (SPA websocket
            # recovery). Runs fully offline via selectors (no Gemini dependency) so it
            # still works when Vision is rate-limited/off. Ref: KSS-RCA-012.
            if await self._reconnect_if_connection_lost(page):
                dismissed_any = True
                await page.wait_for_timeout(1500)
                if not await self.is_overlay_present(page):
                    logger.info("TradeMan connection re-established via 'Reconnect'.")
                    await self._log_event("POPUP_DISMISSED", "Dismissed via Tier 0 Reconnect (Connection Lost)")
                    continue

            # Tier 0.5: Check 'ไม่ต้องแสดงอีก' (Don't show again) option first
            await self._check_dont_show_again(page)

            # Tier 1: Fast Heuristic Rules
            t1_success = await self._dismiss_via_fast_rules(page)
            if t1_success:
                dismissed_any = True
                await page.wait_for_timeout(800)
                if not await self.is_overlay_present(page):
                    logger.info("Popup successfully dismissed via Fast Heuristic Rules.")
                    await self._log_event("POPUP_DISMISSED", "Dismissed via Tier 1 Fast Selectors")
                    continue

            # Tier 1.5: Keyboard Escape or Backdrop Click
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            if not await self.is_overlay_present(page):
                logger.info("Popup successfully dismissed via Escape key.")
                await self._log_event("POPUP_DISMISSED", "Dismissed via Escape key")
                dismissed_any = True
                continue

            # Tier 2 (Gemini Vision) REMOVED 2026-10-07 - deterministic-only.
            # Novel popups surviving Tier 0-1.5 are left for the caller to escalate
            # via HITL (root_cause_and_escalation Invariant 4), never guessed by AI.

        if dismissed_any and page.context:
            try:
                os.makedirs(os.path.dirname(settings.SESSION_STATE_PATH) or "data", exist_ok=True)
                await page.context.storage_state(path=settings.SESSION_STATE_PATH)
            except Exception:
                pass

        return dismissed_any

    async def _dismiss_via_fast_rules(self, page: Page) -> bool:
        """Scans for known close buttons in active modals and clicks them."""
        for sel in self.FAST_DISMISS_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    logger.info(f"Found modal close button: {sel}. Clicking...")
                    await btn.click(timeout=3000, force=True)
                    return True
            except Exception:
                continue

        # Try clicking overlay backdrop (scrim)
        try:
            scrim = await page.query_selector(".v-overlay__scrim, .modal-backdrop")
            if scrim and await scrim.is_visible():
                logger.info("Clicking modal backdrop scrim...")
                await scrim.click(timeout=3000)
                return True
        except Exception:
            pass

        return False

popup_manager = PopupManager()
