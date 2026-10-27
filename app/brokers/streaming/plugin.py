"""
Settrade Streaming (Krungsri SSO) Broker Plugin.
================================================
Isolated adapter implementing BaseBrokerPlugin for the *live* Settrade Streaming
trading console (StreamingPage.jsp) reached via Krungsri SSO.

Phase 1 (TASK-loop1-8): driver + auth + plugin wiring. Line-routing and platform
switch (Phase 2/3) register this plugin into ``broker_registry`` later.
"""

import os
from typing import Any, Dict, List, Optional

from app.brokers.base import (
    BaseBrokerPlugin,
    BrokerCapability,
    BrokerMetadata,
    BrokerStatus,
    AccountSummary,
    PortfolioSnapshot,
    PositionItem,
    OrderRequest,
    OrderResult,
    TransportType,
)
from app.browser.streaming_auth_driver import streaming_auth_driver
from app.browser.streaming_driver import streaming_driver
from app.browser.tab_manager import tab_manager
from app.core.config import settings


class StreamingBrokerPlugin(BaseBrokerPlugin):
    metadata = BrokerMetadata(
        name="streaming",
        display_name="Settrade Streaming (Krungsri SSO)",
        transport=TransportType.PLAYWRIGHT,
        supported_markets=["SET"],
        supports_sbl=False,
        supports_direct_api=False,
        supported_accounts=["CASH", "MARGIN"],
        base_url="https://streaming.settrade.com",
        capabilities=[
            BrokerCapability.AUTHENTICATION,
            BrokerCapability.EQUITY_TRADE,
            BrokerCapability.BROWSER_AUTOMATION,
            BrokerCapability.ACCOUNT_SWITCHING,
        ],
    )

    def is_configured(self) -> bool:
        return bool(settings.KRUNGSRI_USERNAME and settings.KRUNGSRI_PASSWORD)

    async def get_health(self) -> Dict[str, Any]:
        configured = self.is_configured()
        has_session = os.path.exists(settings.STREAMING_SESSION_PATH)
        tab = tab_manager.get_tab("streaming")
        is_active = tab is not None and not tab.is_closed()

        status = BrokerStatus.UNCONFIGURED.value
        if configured:
            status = streaming_auth_driver.status if is_active else (
                "SESSION_SAVED" if has_session else BrokerStatus.DISCONNECTED.value
            )

        return {
            "broker_name": self.metadata.name,
            "status": status,
            "is_authenticated": streaming_auth_driver.is_authenticated,
            "is_configured": configured,
            "has_saved_session": has_session,
            "tab_active": is_active,
            "active_account_no": streaming_driver.active_account_no,
            "last_heartbeat": streaming_auth_driver.last_heartbeat.isoformat() if streaming_auth_driver.last_heartbeat else None,
        }

    async def authenticate(self, force_fresh: bool = False) -> bool:
        res = await streaming_auth_driver.login(force_fresh=force_fresh)
        return res.success

    async def get_account_summary(self, account_no: Optional[str] = None) -> AccountSummary:
        # Phase 1: honest zeros — live balance scraping is wired in a later phase
        # (Anti-Mock: never fabricate a credit line / cash balance).
        return AccountSummary(
            broker_name=self.metadata.name,
            account_no=account_no or streaming_driver.active_account_no,
            account_type="CASH",
            line_available=0.0,
            cash_balance=0.0,
        )

    async def get_portfolio(self, account_no: Optional[str] = None) -> PortfolioSnapshot:
        summary = await self.get_account_summary(account_no)
        raw_positions = await streaming_driver.scrape_portfolio()
        positions: List[PositionItem] = []
        for p in raw_positions:
            positions.append(
                PositionItem(
                    symbol=p.get("symbol", ""),
                    volume=int(p.get("volume", 0)),
                    available_volume=int(p.get("available_volume", p.get("volume", 0))),
                    avg_cost=float(p.get("avg_cost", 0.0)),
                    market_price=float(p.get("market_price", 0.0)),
                    market_value=float(p.get("market_value", 0.0)),
                    unrealized_pnl=float(p.get("unrealized_pl", 0.0)),
                    pct_unrealized_pnl=0.0,
                )
            )
        return PortfolioSnapshot(
            broker_name=self.metadata.name,
            account_no=summary.account_no,
            account_summary=summary,
            positions=positions,
        )

    async def place_order(self, request: OrderRequest) -> OrderResult:
        res = await streaming_driver.execute_order(
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            price=request.price,
            pin=request.pin or settings.KRUNGSRI_PIN,
            auto_launch=True,
        )
        return OrderResult(
            success=res.get("success", False),
            order_id=str(res.get("broker_order_no") or ""),
            broker_name=self.metadata.name,
            message=res.get("message") or res.get("error") or "Order processed",
            raw_response=res,
        )

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        res = await streaming_driver.cancel_order(order_id, symbol=symbol)
        return res.get("success", False)

    async def modify_order_price(
        self,
        order_id: str,
        new_price: float,
        symbol: Optional[str] = None,
        side: str = "BUY",
        remaining_volume: int = 0,
        pin: Optional[str] = None,
        prefer_native: bool = True,
    ) -> OrderResult:
        """Amend an open order — native in-place change first, cancel+replace as fallback.

        SQ-7 (2026-10-26 HAR): Streaming *does* have a native in-place amend —
        ``PATCH /api/dgw/v3/029/accounts/{acct}/orders/{orderNo}/change`` — so the order
        keeps its orderNo and queue position (no KSS-RCA-016 cancel+replace window).
        ``streaming_driver.change_order_native`` fires it and only reports success after
        an Anti-Mock re-read shows the new price on the same orderNo. The legacy
        cancel+replace stays as fallback for cases where nothing reached the broker.
        """
        res = await streaming_driver.modify_order_price(
            broker_order_no=order_id,
            symbol=symbol or "",
            side=side,
            new_price=new_price,
            remaining_volume=remaining_volume,
            pin=pin or settings.KRUNGSRI_PIN or None,
            prefer_native=prefer_native,
        )
        return OrderResult(
            success=res.get("success", False),
            order_id=res.get("broker_order_no") or order_id,
            broker_name=self.metadata.name,
            message=res.get("message") or res.get("error") or res.get("status", "Amend processed"),
            raw_response=res,
        )

    async def switch_account_type(self, target_type: str) -> bool:
        # Streaming exposes a single Equity account (3024952); account switching is
        # a no-op passthrough for interface parity.
        return True

    async def close(self) -> None:
        await streaming_auth_driver.close()


# Singleton Plugin Instance
streaming_plugin = StreamingBrokerPlugin()
