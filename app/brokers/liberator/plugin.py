"""
Liberator Securities (WebTrade) Broker Plugin.
==============================================
Isolated adapter implementing BaseBrokerPlugin for Liberator Securities.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.brokers.base import (
    BaseBrokerPlugin, BrokerMetadata, TransportType, BrokerStatus, BrokerCapability,
    AccountSummary, PortfolioSnapshot, PositionItem, OrderRequest, OrderResult
)
from app.browser.tab_manager import tab_manager
from app.brokers.liberator.driver import liberator_driver


class LiberatorBrokerPlugin(BaseBrokerPlugin):
    metadata = BrokerMetadata(
        name="liberator",
        display_name="Liberator Securities (WebTrade)",
        transport=TransportType.PLAYWRIGHT,
        supported_markets=["SET"],
        supports_sbl=False,
        supports_direct_api=False,
        supported_accounts=["CASH_BALANCE"],
        base_url="https://www.liberator.co.th",
        capabilities=[
            BrokerCapability.AUTHENTICATION,
            BrokerCapability.EQUITY_TRADE,
            BrokerCapability.BROWSER_AUTOMATION
        ]
    )

    def is_configured(self) -> bool:
        return bool(settings.LIBERATOR_USERNAME and settings.LIBERATOR_PASSWORD)

    async def get_health(self) -> Dict[str, Any]:
        configured = self.is_configured()
        has_session = os.path.exists(settings.LIBERATOR_SESSION_PATH)
        tab = tab_manager.get_tab("liberator")
        is_active = tab is not None and not tab.is_closed()

        status = BrokerStatus.UNCONFIGURED.value
        if configured:
            status = BrokerStatus.AUTHENTICATED.value if is_active else (
                BrokerStatus.DISCONNECTED.value if not has_session else "SESSION_SAVED"
            )

        return {
            "broker_name": self.metadata.name,
            "status": status,
            "is_authenticated": is_active,
            "is_configured": configured,
            "has_saved_session": has_session,
            "tab_active": is_active,
            "last_heartbeat": datetime.now(timezone.utc).isoformat()
        }

    async def authenticate(self, force_fresh: bool = False) -> bool:
        if not self.is_configured():
            return False
        # If tab is already active and healthy
        tab = tab_manager.get_tab("liberator")
        if tab and not tab.is_closed() and not force_fresh:
            return True
        # Verify saved session if not forced fresh
        if not force_fresh and os.path.exists(settings.LIBERATOR_SESSION_PATH):
            if await liberator_driver.verify_saved_session():
                return True
        # Execute automated login
        res = await liberator_driver.login(force_fresh=force_fresh)
        return res.success

    async def get_account_summary(self, account_no: Optional[str] = None) -> AccountSummary:
        acc = account_no or settings.LIBERATOR_USERNAME or "7055938"
        raw = await liberator_driver.scrape_portfolio()
        return AccountSummary(
            broker_name=self.metadata.name,
            account_no=acc,
            account_type="CASH_BALANCE",
            line_available=float(raw.get("line_available", 0.0)),
            cash_balance=float(raw.get("cash_balance", 0.0)),
            excess_equity=float(raw.get("line_available", 0.0)),
            total_equity=float(raw.get("total_equity", 0.0)),
            unrealized_pnl=float(raw.get("total_unrealized_pnl", 0.0)),
            realized_pnl_today=0.0
        )

    async def get_portfolio(self, account_no: Optional[str] = None) -> PortfolioSnapshot:
        summary = await self.get_account_summary(account_no)
        raw = await liberator_driver.scrape_portfolio()
        positions: list[PositionItem] = []
        for p in raw.get("positions", []):
            positions.append(PositionItem(
                symbol=p["symbol"],
                volume=int(p.get("volume", p.get("in_port", 0))),
                available_volume=int(p.get("available_volume", p.get("act_vol", 0))),
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

    async def get_orders(self) -> list[Dict[str, Any]]:
        """Returns scraped orders from active/cached Liberator session."""
        raw = await liberator_driver.scrape_portfolio()
        return raw.get("orders", [])

    async def get_open_orders(self, account_no: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns currently OPEN / unmatched (queuing) orders from the active or cached
        Liberator session, normalized to the Homelab canonical order schema shared with
        Click2Win / Krungsri:

        [{broker_order_no, symbol, side, volume, matched_volume, balance, price, status, time}]

        Only live rows are kept (status not Matched/Cancelled AND balance > 0), mirroring
        the price-negotiation unmatched-order definition.
        """
        raw = await liberator_driver.scrape_portfolio()
        normalized: List[Dict[str, Any]] = []
        for o in raw.get("orders", []):
            status = str(o.get("status", "Unknown"))
            balance = int(o.get("balance", 0) or 0)
            if status in ("Matched", "Cancelled") or balance <= 0:
                continue
            normalized.append({
                "broker_order_no": str(o.get("order_no") or o.get("broker_order_no") or ""),
                "symbol": str(o.get("symbol", "")).upper(),
                "side": str(o.get("side", "")).upper(),
                "volume": int(o.get("volume", 0) or 0),
                "matched_volume": int(o.get("matched", o.get("matched_volume", 0)) or 0),
                "balance": balance,
                "price": float(o.get("price", 0.0) or 0.0),
                "status": status,
                "time": o.get("time"),
            })
        return normalized

    async def get_all_orders(self, account_no: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns ALL orders (matched + partial + open + cancelled) from the active/cached
        Liberator session, normalized to the canonical Homelab order schema used by Pillar 2
        `current_orders` / the Order Ledger view.

        Unlike `get_open_orders()` (which drops terminal rows for price negotiation), this
        preserves EVERY row so the caller can render a full Matched vs Unmatched ledger.
        """
        raw = await liberator_driver.scrape_portfolio()
        normalized: List[Dict[str, Any]] = []
        for o in raw.get("orders", []):
            normalized.append({
                "broker_order_no": str(o.get("order_no") or o.get("broker_order_no") or ""),
                "symbol": str(o.get("symbol", "")).upper(),
                "side": str(o.get("side", "")).upper(),
                "volume": int(o.get("volume", 0) or 0),
                "matched_volume": int(o.get("matched", o.get("matched_volume", 0)) or 0),
                "balance": int(o.get("balance", 0) or 0),
                "cancelled_volume": int(o.get("cancelled", 0) or 0),
                "price": float(o.get("price", 0.0) or 0.0),
                "status": str(o.get("status", "Unknown")),
                "time": o.get("time"),
            })
        return normalized

    async def switch_account_type(self, target_type: str) -> bool:
        """
        Liberator Securities WebTrade is a SINGLE-ACCOUNT (Cash Balance) broker — there is
        no MARGIN (credit/SBL) or DERIVATIVES environment to switch into. Returns True for a
        cash/equity request and False for anything else, so callers never silently assume
        MARGIN / DERIVATIVES availability.
        """
        t = (target_type or "CASH").upper().strip()
        return t in ("CASH", "CASH_BALANCE", "EQUITY")

    async def place_order(self, request: OrderRequest) -> OrderResult:
        # Pre-flight safety validations
        if not request.symbol or not request.symbol.strip():
            return OrderResult(
                success=False,
                broker_name=self.metadata.name,
                message="Order rejected: Symbol cannot be empty."
            )
        if request.volume <= 0 or request.volume % 100 != 0:
            return OrderResult(
                success=False,
                broker_name=self.metadata.name,
                message=f"Order rejected: Volume ({request.volume}) must be positive multiple of 100 on SET board lot."
            )
        if request.price <= 0:
            return OrderResult(
                success=False,
                broker_name=self.metadata.name,
                message="Order rejected: Price must be greater than 0.0."
            )

        pin = request.pin or getattr(settings, "LIBERATOR_PIN", "")
        if not pin or len(pin) != 6:
            return OrderResult(
                success=False,
                broker_name=self.metadata.name,
                message="Order rejected: Valid 6-digit PIN required for Liberator order submission."
            )

        # Market Hours Validation (SET market is open Mon-Fri 09:55-12:30, 14:25-16:35 Bangkok)
        now_bkk = datetime.now(timezone.utc).astimezone()
        if now_bkk.weekday() in (5, 6):  # Saturday or Sunday
            return OrderResult(
                success=False,
                broker_name=self.metadata.name,
                message=f"Order staged / rejected: SET Market is CLOSED on weekends ({now_bkk.strftime('%A')}). Form interaction is verified and ready for Monday Market Open (09:55 BKK)."
            )

        # Execute via Liberator autonomous driver
        res = await liberator_driver.execute_order(
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            price=request.price,
            pin=pin,
            account_no=request.account_no
        )

        return OrderResult(
            success=res.get("success", False),
            order_id=res.get("broker_order_no"),
            broker_name=self.metadata.name,
            message=res.get("message") or res.get("error", "Order processed"),
            raw_response=res
        )

    async def cancel_order(self, order_id: str) -> bool:
        res = await liberator_driver.cancel_order(order_id)
        return res.get("success", False)

    async def execute_action_exit(
        self,
        symbol: str,
        volume: Optional[int] = None,
        target_price: Optional[float] = None,
        reason: str = "Tactical Action Exit"
    ) -> Dict[str, Any]:
        """Pillar 6 Tactical Action Exit: Liquidates stock holding on Liberator."""
        return await liberator_driver.execute_action_exit(
            symbol=symbol,
            volume=volume,
            target_price=target_price,
            reason=reason
        )

    async def change_order(
        self,
        order_no: str,
        new_price: float,
        new_volume: Optional[int] = None
    ) -> Dict[str, Any]:
        """Pillar 6 Amend In Place: presses the broker's native `Change` control on a resting
        order so the price changes WITHOUT cancelling — order number + queue slot are retained."""
        return await liberator_driver.change_order(
            order_no=order_no,
            new_price=new_price,
            new_volume=new_volume
        )

    async def negotiate_price(
        self,
        order_no: Optional[str] = None,
        symbol: Optional[str] = None,
        target_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Pillar 6 Passive Queue Pegging: amends an unmatched order **in place** (native
        `Change` control) to the priority price — no cancel + re-place (order number retained)."""
        return await liberator_driver.negotiate_price(
            order_no=order_no,
            symbol=symbol,
            target_price=target_price
        )

    async def get_market_bid_offer(self, symbol: str) -> Dict[str, Any]:
        """Live Bid1 / Offer1 (/ last) from the Liberator WebTrade board — used by the
        LINE CLI ``/nego lib`` guardrails (G5 tick distance / G6 SHORT uptick).

        Fails closed: returns ``source="unavailable"`` (all numeric fields None) when
        the board cannot be read, so callers must skip rather than trade on a guess.
        """
        return await liberator_driver.get_market_bid_offer(symbol)

    async def close(self) -> None:
        await liberator_driver.close()
        tab = tab_manager.get_tab("liberator")
        if tab and not tab.is_closed():
            await tab.close()


# Singleton Plugin Instance
liberator_plugin = LiberatorBrokerPlugin()
