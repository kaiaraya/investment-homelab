"""
Settrade Click2Win (Web Sandbox) Broker Plugin.
==============================================
Isolated adapter implementing BaseBrokerPlugin for Settrade Click2Win.
Features:
- Multi-Asset Auto-Routing (Equity vs TFEX Derivatives)
- Automatic Streaming GUI Interaction (StreamingPage.jsp)
- Real-time Position & Order Submission Sandbox
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.core.config import settings
from app.brokers.base import (
    BaseBrokerPlugin, BrokerMetadata, TransportType, BrokerStatus, BrokerCapability,
    AccountSummary, PortfolioSnapshot, PositionItem, OrderRequest, OrderResult
)
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.browser.click2win_driver import click2win_driver
from app.browser.tab_manager import tab_manager


class Click2WinBrokerPlugin(BaseBrokerPlugin):
    metadata = BrokerMetadata(
        name="click2win",
        display_name="Settrade Click2Win (Web Sandbox)",
        transport=TransportType.PLAYWRIGHT,
        supported_markets=["SET", "TFEX"],
        supports_sbl=False,
        supports_direct_api=False,
        supported_accounts=["EQUITY", "DERIVATIVES"],
        base_url="https://click2win.settrade.com",
        capabilities=[
            BrokerCapability.AUTHENTICATION,
            BrokerCapability.EQUITY_TRADE,
            BrokerCapability.DERIVATIVES_TRADE,
            BrokerCapability.BROWSER_AUTOMATION,
            BrokerCapability.ACCOUNT_SWITCHING
        ]
    )

    def is_configured(self) -> bool:
        return bool(settings.CLICK2WIN_USERNAME and settings.CLICK2WIN_PASSWORD)

    async def get_health(self) -> Dict[str, Any]:
        configured = self.is_configured()
        has_session = os.path.exists(settings.CLICK2WIN_SESSION_PATH)
        tab = tab_manager.get_tab("click2win")
        is_active = tab is not None and not tab.is_closed()

        status = BrokerStatus.UNCONFIGURED.value
        if configured:
            status = click2win_auth_driver.status if is_active else (
                "SESSION_SAVED" if has_session else BrokerStatus.DISCONNECTED.value
            )

        return {
            "broker_name": self.metadata.name,
            "status": status,
            "is_authenticated": click2win_auth_driver.is_authenticated,
            "is_configured": configured,
            "has_saved_session": has_session,
            "tab_active": is_active,
            "active_account_type": click2win_driver.active_account_type,
            "last_heartbeat": click2win_auth_driver.last_heartbeat.isoformat() if click2win_auth_driver.last_heartbeat else None
        }

    async def authenticate(self, force_fresh: bool = False) -> bool:
        res = await click2win_auth_driver.login(force_fresh=force_fresh)
        return res.get("success", False)

    async def get_account_summary(self, account_no: Optional[str] = None) -> AccountSummary:
        raw = await click2win_driver.scrape_accounts_summary()
        accounts = raw.get("accounts", [])
        
        # Default or matching account
        target_acc = None
        for acc in accounts:
            if account_no and acc.get("account_no") == account_no:
                target_acc = acc
                break
        if not target_acc and accounts:
            target_acc = accounts[0]

        line_avail = float(target_acc.get("line_available", 0.0)) if target_acc else 0.0
        cash = float(target_acc.get("cash_balance", line_avail)) if target_acc else 0.0
        acc_no = target_acc.get("account_no", account_no or "CW32-EQUITY") if target_acc else "CW32-EQUITY"
        acc_type = target_acc.get("account_type", click2win_driver.active_account_type) if target_acc else click2win_driver.active_account_type

        return AccountSummary(
            broker_name=self.metadata.name,
            account_no=acc_no,
            account_type=acc_type,
            line_available=line_avail,
            cash_balance=cash,
            total_equity=line_avail
        )

    async def get_portfolio(self, account_no: Optional[str] = None) -> PortfolioSnapshot:
        summary = await self.get_account_summary(account_no)
        raw_positions = await click2win_driver.scrape_portfolio()
        positions: List[PositionItem] = []
        for p in raw_positions:
            positions.append(PositionItem(
                symbol=p.get("symbol", ""),
                volume=int(p.get("volume", 0)),
                available_volume=int(p.get("available_volume", p.get("volume", 0))),
                avg_cost=float(p.get("avg_cost", 0.0)),
                market_price=float(p.get("market_price", 0.0)),
                market_value=float(p.get("market_value", 0.0)),
                unrealized_pnl=float(p.get("unrealized_pnl", 0.0)),
                pct_unrealized_pnl=float(p.get("pct_unrealized_pnl", 0.0))
            ))

        return PortfolioSnapshot(
            broker_name=self.metadata.name,
            account_no=summary.account_no,
            account_summary=summary,
            positions=positions
        )

    async def place_order(self, request: OrderRequest) -> OrderResult:
        # Automatic Asset-Based Routing (Equity vs TFEX)
        asset_type = click2win_driver.detect_account_type_for_symbol(request.symbol)
        if asset_type != click2win_driver.active_account_type:
            await click2win_driver.switch_account_type(asset_type)

        res = await click2win_driver.execute_order(
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            price=request.price,
            position=request.position or "AUTO",
            pin=request.pin or settings.CLICK2WIN_PIN,
            auto_launch=True
        )

        return OrderResult(
            success=res.get("success", False),
            order_id=str(res.get("broker_order_no") or res.get("order_id") or ""),
            broker_name=self.metadata.name,
            message=res.get("message", "Order processed"),
            raw_response=res
        )

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        res = await click2win_driver.cancel_order(order_id, symbol=symbol)
        return res.get("success", False)

    async def switch_account_type(self, target_type: str) -> bool:
        return await click2win_driver.switch_account_type(target_type)

    async def close(self) -> None:
        await click2win_auth_driver.close()


# Singleton Plugin Instance
click2win_plugin = Click2WinBrokerPlugin()
