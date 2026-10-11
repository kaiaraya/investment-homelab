"""
Centralized Multi-Tab Registry & Manager for Homelab Trading Engines.
====================================================================
Maintains persistent, shared browser tabs across multiple broker services:
- Krungsri Master Portal (Anchor SSO for SBL, eFin, iFund, TradeMan)
- TradeMan (Active Real-Time Trading & Portfolio)
- SBL Realtime (Securities Borrowing & Lending)
- eFin Stock Pickup (Technical Charts & Data)
- Settrade Click2Win / Streaming

Features:
- Zero-latency tab switching (bring_to_front)
- Automatic tab discovery via URL matching (scan_and_sync)
- On-demand service launcher through Master Portal SSO without re-authentication
"""

import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
from playwright.async_api import Page, BrowserContext

logger = logging.getLogger("BrowserTabManager")


class BrowserTabManager:
    def __init__(self):
        self._tabs: Dict[str, Page] = {}
        self.context: Optional[BrowserContext] = None

    def set_context(self, context: BrowserContext):
        """Attaches the Playwright BrowserContext to this manager."""
        self.context = context
        # Listen for newly spawned pages or popups
        try:
            self.context.on("page", lambda p: self._handle_new_page(p))
        except Exception as e:
            logger.debug(f"Error binding context page listener: {e}")

    def _handle_new_page(self, page: Page):
        """Auto-detects and categorizes newly opened pages/popups."""
        url = page.url.lower()
        logger.info(f"TabManager detected new page: {page.url}")
        self._classify_page(page)

    def _classify_page(self, page: Page) -> Optional[str]:
        if page.is_closed():
            return None
        url = page.url.lower()
        if "trademan.in.th" in url:
            self.register_tab("trademan", page)
            return "trademan"
        elif "krungsrisecurities.com" in url:
            if "sbl" in url:
                self.register_tab("sbl", page)
                return "sbl"
            elif "mutual-fund" in url or "ifund" in url:
                self.register_tab("ifund", page)
                return "ifund"
            elif "default.aspx" in url or "main" in url or "check_login" in url:
                self.register_tab("krungsri_portal", page)
                return "krungsri_portal"
            else:
                self.register_tab("krungsri_portal", page)
                return "krungsri_portal"
        elif "click2win" in url:
            self.register_tab("click2win", page)
            return "click2win"
        elif "liberator" in url:
            self.register_tab("liberator", page)
            return "liberator"
        return None

    def register_tab(self, name: str, page: Page):
        """Explicitly registers a page under a logical service name."""
        self._tabs[name] = page
        logger.info(f"Registered tab '{name}' -> URL: {page.url}")

    def get_tab(self, name: str) -> Optional[Page]:
        """Returns the active Page instance if open and not closed."""
        page = self._tabs.get(name)
        if page and not page.is_closed():
            return page
        elif page and page.is_closed():
            del self._tabs[name]
        return None

    def list_active_tabs(self) -> Dict[str, Dict[str, Any]]:
        """Returns an overview of all currently active tabs."""
        self.clean_closed_tabs()
        result = {}
        for name, page in list(self._tabs.items()):
            try:
                result[name] = {
                    "name": name,
                    "url": page.url,
                    "is_active": not page.is_closed(),
                    "title": ""
                }
            except Exception:
                pass
        return result

    def clean_closed_tabs(self):
        """Removes references to tabs that have been closed."""
        closed = [k for k, p in self._tabs.items() if p.is_closed()]
        for k in closed:
            del self._tabs[k]

    async def scan_and_sync(self, context: Optional[BrowserContext] = None):
        """Scans all pages in the context and synchronizes the registry."""
        ctx = context or self.context
        if not ctx:
            return

        self.clean_closed_tabs()
        for p in ctx.pages:
            if not p.is_closed():
                self._classify_page(p)

    async def switch_to_tab(self, name: str) -> Optional[Page]:
        """Brings the requested tab to the front."""
        page = self.get_tab(name)
        if page:
            try:
                await page.bring_to_front()
                logger.info(f"Switched to tab '{name}' ({page.url})")
                return page
            except Exception as e:
                logger.warning(f"Could not bring tab '{name}' to front: {e}")
        return None

    async def get_or_open_trademan(self) -> Optional[Page]:
        """
        Retrieves the TradeMan tab. If not open, attempts to launch it via
        Krungsri Master Portal SSO or direct session navigation.
        """
        page = self.get_tab("trademan")
        if page:
            await page.bring_to_front()
            return page

        # Check if Krungsri Master Portal is available to SSO
        portal = self.get_tab("krungsri_portal")
        if portal and not portal.is_closed():
            logger.info("TradeMan tab not found. Launching via Krungsri Master Portal SSO...")
            try:
                await portal.bring_to_front()
                # Trigger TradeMan popup
                await portal.evaluate("popup('../../th/efin/start_SSO.aspx?page=TM','',1200,800)")
                # Wait for new page
                for _ in range(15):
                    await portal.wait_for_timeout(1000)
                    await self.scan_and_sync()
                    tm = self.get_tab("trademan")
                    if tm:
                        await tm.bring_to_front()
                        return tm
            except Exception as e:
                logger.warning(f"Failed to launch TradeMan from portal SSO: {e}")

        # Fallback to opening a new page with existing session cookies
        if self.context:
            logger.info("Opening new TradeMan page with context cookies...")
            new_p = await self.context.new_page()
            await new_p.goto("https://trademan.in.th/Portfolio", wait_until="domcontentloaded")
            self.register_tab("trademan", new_p)
            return new_p

        return None

    async def get_or_open_sbl(self) -> Optional[Page]:
        """
        Retrieves the SBL Realtime tab. If not open, opens it via Krungsri Portal.
        """
        page = self.get_tab("sbl")
        if page:
            await page.bring_to_front()
            return page

        portal = self.get_tab("krungsri_portal")
        if portal and not portal.is_closed():
            logger.info("Opening SBL Realtime from Krungsri Portal...")
            try:
                sbl_url = "https://www.krungsrisecurities.com/th/discliaimer-sbl/Default.aspx?start=sbl"
                if self.context:
                    new_p = await self.context.new_page()
                    await new_p.goto(sbl_url, wait_until="domcontentloaded")
                    self.register_tab("sbl", new_p)
                    return new_p
            except Exception as e:
                logger.warning(f"Failed to open SBL tab: {e}")
        return None

    async def ping_keepalive(self) -> Dict[str, bool]:
        """
        Sends lightweight pings across all active registered tabs to prevent idle logout.
        """
        self.clean_closed_tabs()
        results = {}
        for name, page in self._tabs.items():
            try:
                # Evaluating document.title is non-intrusive and refreshes active interaction timestamps
                title = await page.evaluate("() => document.title")
                results[name] = True
                logger.debug(f"Keep-Alive ping successful for '{name}' (Title: '{title[:30]}')")
            except Exception as e:
                results[name] = False
                logger.debug(f"Keep-Alive ping failed for '{name}': {e}")
        return results


# Global Singleton Instance
tab_manager = BrowserTabManager()
