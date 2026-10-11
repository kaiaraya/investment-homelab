"""
Krungsri Securities (TradeMan Pro) Broker Plugin.
================================================
Isolated adapter implementing BaseBrokerPlugin for Krungsri Securities.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.core.config import settings
from app.brokers.base import (
    BaseBrokerPlugin, BrokerMetadata, TransportType, BrokerStatus, BrokerCapability,
    AccountSummary, PortfolioSnapshot, PositionItem, OrderRequest, OrderResult
)
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver

logger = logging.getLogger(__name__)


class KrungsriBrokerPlugin(BaseBrokerPlugin):
    metadata = BrokerMetadata(
        name="krungsri",
        display_name="Krungsri Securities (TradeMan Pro)",
        transport=TransportType.PLAYWRIGHT,
        supported_markets=["SET"],
        supports_sbl=True,
        supports_direct_api=False,
        supported_accounts=["CASH", "MARGIN"],
        base_url="https://trademan.in.th",
        capabilities=[
            BrokerCapability.AUTHENTICATION,
            BrokerCapability.MULTI_FACTOR_OTP,
            BrokerCapability.EQUITY_TRADE,
            BrokerCapability.SBL_SHORT,
            BrokerCapability.BROWSER_AUTOMATION,
            BrokerCapability.ACCOUNT_SWITCHING
        ]
    )

    def is_configured(self) -> bool:
        return bool(settings.KRUNGSRI_USERNAME and settings.KRUNGSRI_PASSWORD)

    async def get_health(self) -> Dict[str, Any]:
        return {
            "broker_name": self.metadata.name,
            "status": auth_driver.status,
            "is_authenticated": auth_driver.is_authenticated,
            "is_configured": self.is_configured(),
            "current_ref": auth_driver.current_ref,
            "last_heartbeat": auth_driver.last_heartbeat.isoformat() if auth_driver.last_heartbeat else None
        }

    async def authenticate(self, force_fresh: bool = False) -> bool:
        res = await auth_driver.login(force_fresh=force_fresh)
        return res.success

    async def get_account_summary(self, account_no: Optional[str] = None) -> AccountSummary:
        raw = await trademan_driver.scrape_account_summary()
        return AccountSummary(
            broker_name=self.metadata.name,
            account_no=account_no or trademan_driver.active_account_no,
            account_type=trademan_driver.active_account_type,
            line_available=raw.get("cash_balance", 0.0),
            cash_balance=raw.get("cash_balance", 0.0),
            excess_equity=raw.get("excess_equity", 0.0),
            total_equity=raw.get("total_equity", 0.0),
            realized_pnl_today=raw.get("realized_pnl_today", 0.0)
        )

    async def get_portfolio(self, account_no: Optional[str] = None) -> PortfolioSnapshot:
        summary = await self.get_account_summary(account_no)
        raw_holdings = await trademan_driver.scrape_portfolio()
        positions: list[PositionItem] = []
        for h in raw_holdings:
            positions.append(PositionItem(
                symbol=h.get("symbol", ""),
                volume=int(h.get("volume", 0)),
                available_volume=int(h.get("available_volume", h.get("volume", 0))),
                avg_cost=float(h.get("avg_cost", 0.0)),
                market_price=float(h.get("market_price", 0.0)),
                market_value=float(h.get("market_value", 0.0)),
                unrealized_pnl=float(h.get("unrealized_pnl", 0.0)),
                pct_unrealized_pnl=float(h.get("pct_unrealized_pnl", 0.0))
            ))
        return PortfolioSnapshot(
            broker_name=self.metadata.name,
            account_no=summary.account_no,
            account_summary=summary,
            positions=positions
        )

    async def place_order(self, request: OrderRequest) -> OrderResult:
        res = await trademan_driver.execute_order(
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            price=request.price,
            pin=request.pin,
            account_no=request.account_no
        )
        return OrderResult(
            success=res.get("success", False),
            order_id=res.get("order_id"),
            broker_name=self.metadata.name,
            message=res.get("message", "Order processed"),
            raw_response=res
        )

    async def cancel_order(
        self,
        order_id: str,
        symbol: Optional[str] = None,
        pin: Optional[str] = None,
        bypass_dry_run: bool = False,
    ) -> bool:
        """
        Cancels an open TradeMan order (row-scoped, PIN-confirmed).

        `symbol` is accepted for interface parity with Click2Win / the
        `/orders/{id}/cancel-broker` endpoint, but TradeMan resolves the symbol
        from the ledger row itself.
        """
        res = await trademan_driver.cancel_order(
            broker_order_no=order_id,
            symbol=symbol or "",
            pin=pin,
            bypass_dry_run=bypass_dry_run,
        )
        if not res.get("success"):
            logger.warning(
                f"Krungsri cancel_order({order_id}) failed: "
                f"{res.get('status')} - {res.get('error')}"
            )
        return res.get("success", False)

    async def modify_order_price(
        self,
        order_id: str,
        new_price: float,
        symbol: Optional[str] = None,
        side: str = "BUY",
        remaining_volume: int = 0,
        pin: Optional[str] = None,
        account_no: Optional[str] = None,
        bypass_dry_run: bool = False,
    ) -> OrderResult:
        """
        Amends an open TradeMan order's price.

        TradeMan has NO native "Change" button (verified live 2026-10-09,
        KSS-RCA-016) -> amend == cancel + re-submit, handled inside the driver.
        Header signature matches `BaseBrokerPlugin.modify_order_price`
        (`order_id`, `new_price`); the remaining kwargs mirror the driver.
        """
        res = await trademan_driver.modify_order_price(
            broker_order_no=order_id,
            symbol=symbol or "",
            side=side,
            new_price=new_price,
            remaining_volume=remaining_volume,
            pin=pin,
            account_no=account_no or trademan_driver.active_account_no,
            bypass_dry_run=bypass_dry_run,
        )
        return OrderResult(
            success=res.get("success", False),
            order_id=res.get("broker_order_no") or order_id,
            broker_name=self.metadata.name,
            message=res.get("message") or res.get("error") or res.get("status", "Amend processed"),
            raw_response=res,
        )

    async def get_sbl_inventory(self, symbols: list[str]) -> dict[str, int]:
        return await trademan_driver.scrape_sbl_inventory(symbols)

    async def borrow_sbl(self, symbol: str, volume: int) -> dict[str, Any]:
        return await trademan_driver.execute_sbl_borrow(symbol=symbol, volume=volume)

    async def return_sbl(self, symbol: str, volume: int) -> dict[str, Any]:
        return await trademan_driver.execute_sbl_return(symbol=symbol, volume=volume)

    async def switch_account_type(self, target_type: str) -> bool:
        res = await trademan_driver.switch_account(target_type)
        return res.get("success", False)

    async def close(self) -> None:
        await auth_driver.close()


# Singleton Plugin Instance
krungsri_plugin = KrungsriBrokerPlugin()
