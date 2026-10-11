"""
Pluggable Broker Architecture - Base Contracts & Data Models.
============================================================
Defines the universal interface and data schemas for all trading engines in Homelab.
Brokers can be:
- API-driven (e.g. Settrade Open API: direct REST/WebSocket, 0ms, headless)
- Browser-driven (e.g. Krungsri TradeMan, Liberator: Playwright automated SSO + OTP)
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class TransportType(str, Enum):
    DIRECT_API = "DIRECT_API"      # Direct REST/WebSocket (No browser needed)
    PLAYWRIGHT = "PLAYWRIGHT"      # Playwright Browser Automation


class BrokerStatus(str, Enum):
    UNCONFIGURED = "UNCONFIGURED"  # Missing credentials in .env
    DISCONNECTED = "DISCONNECTED"  # Configured but not logged in
    AWAITING_OTP = "AWAITING_OTP"  # Waiting for 2FA SMS/App OTP
    AUTHENTICATED = "AUTHENTICATED" # Ready for real-time portfolio & trading
    FAILED = "FAILED"              # Login failed or network error


class BrokerCapability(str, Enum):
    AUTHENTICATION = "AUTHENTICATION"        # Supports login authentication
    MULTI_FACTOR_OTP = "MULTI_FACTOR_OTP"    # Requires/supports 2FA SMS or App OTP
    EQUITY_TRADE = "EQUITY_TRADE"            # Supports SET stock trading
    DERIVATIVES_TRADE = "DERIVATIVES_TRADE"  # Supports TFEX derivatives trading
    SBL_SHORT = "SBL_SHORT"                  # Supports Stock Borrowing and Lending
    DIRECT_API = "DIRECT_API"                # Machine-to-machine direct REST/WebSocket
    BROWSER_AUTOMATION = "BROWSER_AUTOMATION" # Playwright automated browser
    REALTIME_STREAM = "REALTIME_STREAM"      # Streaming market ticks / quotes
    ACCOUNT_SWITCHING = "ACCOUNT_SWITCHING"  # Supports multi-account switching


class BrokerMetadata(BaseModel):
    name: str                      # Unique slug e.g. "krungsri", "liberator", "settrade_openapi"
    display_name: str              # Friendly UI label e.g. "Krungsri TradeMan Pro"
    transport: TransportType       # DIRECT_API or PLAYWRIGHT
    supported_markets: List[str] = ["SET", "TFEX"]
    supports_sbl: bool = False
    supports_direct_api: bool = False
    supported_accounts: List[str] = ["CASH"]
    base_url: str = ""
    capabilities: List[BrokerCapability] = []


class AccountSummary(BaseModel):
    broker_name: str
    account_no: str
    account_type: str = "CASH"     # CASH, MARGIN, EQUITY, DERIVATIVES
    line_available: float = 0.0
    cash_balance: float = 0.0
    excess_equity: float = 0.0
    total_equity: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PositionItem(BaseModel):
    symbol: str
    volume: int
    available_volume: int
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    pct_unrealized_pnl: float


class PortfolioSnapshot(BaseModel):
    broker_name: str
    account_no: str
    account_summary: AccountSummary
    positions: List[PositionItem] = []
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrderRequest(BaseModel):
    symbol: str
    side: str                      # BUY, SELL, SHORT, COVER, LONG
    volume: int
    price: float
    pin: str
    account_no: Optional[str] = None
    account_type: Optional[str] = "CASH"
    position: Optional[str] = "AUTO"  # OPEN, CLOSE, AUTO


class OrderResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    broker_name: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: Dict[str, Any] = {}


class BaseBrokerPlugin(ABC):
    """
    Tiered Capability-Driven Base Class for all pluggable broker adapters.
    Each broker implements this interface inside its own isolated folder.
    """
    metadata: BrokerMetadata
    status: BrokerStatus = BrokerStatus.DISCONNECTED

    @property
    def capabilities(self) -> List[BrokerCapability]:
        """Returns the list of capabilities supported by this broker."""
        return self.metadata.capabilities

    def has_capability(self, cap: BrokerCapability) -> bool:
        """Checks if this broker supports a specific capability."""
        return cap in self.metadata.capabilities

    # --- Core Workflows (Mandatory for all brokers) ---
    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if all required credentials exist in .env / config."""
        pass

    @abstractmethod
    async def get_health(self) -> Dict[str, Any]:
        """Returns the current connection and authentication status."""
        pass

    @abstractmethod
    async def authenticate(self, force_fresh: bool = False) -> bool:
        """Authenticates with the broker (via REST token or Playwright login)."""
        pass

    @abstractmethod
    async def get_account_summary(self, account_no: Optional[str] = None) -> AccountSummary:
        """Scrapes or requests current account financial summary."""
        pass

    @abstractmethod
    async def get_portfolio(self, account_no: Optional[str] = None) -> PortfolioSnapshot:
        """Scrapes or requests active portfolio positions."""
        pass

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Places a buy/sell order with safety guardrails."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an existing order."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Cleans up any active connections, tabs, or sessions."""
        pass

    # --- Extension Workflows (Safe Default Fallbacks - Never crash if unsupported) ---
    async def get_open_orders(self, account_no: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries currently queuing / unmatched orders."""
        return []

    async def modify_order_price(self, order_id: str, new_price: float) -> OrderResult:
        """Modifies price of an unmatched order."""
        return OrderResult(
            success=False,
            broker_name=self.metadata.name,
            message=f"Modify order price is not supported by {self.metadata.display_name}"
        )

    async def switch_account_type(self, target_type: str) -> bool:
        """Switches between account types (e.g. Cash, Margin, TFEX)."""
        return True

    async def get_sbl_inventory(self, symbols: List[str]) -> Dict[str, int]:
        """SBL: Inquires available stock borrowing inventory."""
        return {}

    async def borrow_sbl(self, symbol: str, volume: int) -> Dict[str, Any]:
        """SBL: Executes stock borrowing request."""
        return {
            "success": False,
            "error_type": "UNSUPPORTED_CAPABILITY",
            "message": f"SBL borrowing is not supported by {self.metadata.display_name}"
        }

    async def return_sbl(self, symbol: str, volume: int) -> Dict[str, Any]:
        """SBL: Executes stock returning request."""
        return {
            "success": False,
            "error_type": "UNSUPPORTED_CAPABILITY",
            "message": f"SBL returning is not supported by {self.metadata.display_name}"
        }

