"""
TypeSafe Multi-Account Schema & Capability Guardrail Engine for Investment Homelab.
Enforces strict Account Capability policies across 3 broker environments:
1. Settrade Click2Win: EQUITY (5M Sandbox) vs DERIVATIVES (2M TFEX Sandbox)
2. Krungsri Securities: CASH (Cash Balance A/C) vs MARGIN (Credit Balance / SBL A/C)
3. Settrade Open API: EQUITY (SETTRADE_ACCOUNT_NO_EQUITY) vs DERIVATIVES (SETTRADE_ACCOUNT_NO_DERIVATIVES)
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.schemas.auth import HybridBaseModel, BrokerPlatform
from app.core.config import settings


class AccountType(str, Enum):
    EQUITY = "EQUITY"              # Click2Win / Settrade Sandbox Stocks
    DERIVATIVES = "DERIVATIVES"    # Click2Win / Settrade Sandbox TFEX Futures/Options
    CASH = "CASH"                  # Krungsri Cash Balance Account
    MARGIN = "MARGIN"              # Krungsri Credit Balance / Margin Account (SBL exclusive)


class AccountCapability(str, Enum):
    EQUITY_TRADE = "EQUITY_TRADE"          # Buying / Selling SET Stocks
    TFEX_TRADE = "TFEX_TRADE"              # Long / Short TFEX Futures/Options
    SBL_BORROW = "SBL_BORROW"              # Borrowing shares from SBL inventory
    SBL_RETURN = "SBL_RETURN"              # Returning borrowed SBL shares
    PORTFOLIO_READ = "PORTFOLIO_READ"      # Reading balances and holdings
    PRICE_NEGOTIATE = "PRICE_NEGOTIATE"    # Adjusting queuing order prices


# Matrix defining allowed capabilities per broker platform and account type
ACCOUNT_CAPABILITY_MATRIX: Dict[Tuple[str, str], List[AccountCapability]] = {
    # Settrade Click2Win
    ("CLICK2WIN", AccountType.EQUITY.value): [
        AccountCapability.EQUITY_TRADE,
        AccountCapability.PORTFOLIO_READ,
        AccountCapability.PRICE_NEGOTIATE
    ],
    ("CLICK2WIN", AccountType.DERIVATIVES.value): [
        AccountCapability.TFEX_TRADE,
        AccountCapability.PORTFOLIO_READ,
        AccountCapability.PRICE_NEGOTIATE
    ],

    # Krungsri TradeMan (Live)
    ("KRUNGSRI", AccountType.CASH.value): [
        AccountCapability.EQUITY_TRADE,
        AccountCapability.PORTFOLIO_READ
    ],
    ("KRUNGSRI", AccountType.MARGIN.value): [
        AccountCapability.EQUITY_TRADE,
        AccountCapability.PORTFOLIO_READ,
        AccountCapability.SBL_BORROW,
        AccountCapability.SBL_RETURN
    ],

    # Settrade Open API (Sandbox)
    ("SETTRADE_OPENAPI", AccountType.EQUITY.value): [
        AccountCapability.EQUITY_TRADE,
        AccountCapability.PORTFOLIO_READ
    ],
    ("SETTRADE_OPENAPI", AccountType.DERIVATIVES.value): [
        AccountCapability.TFEX_TRADE,
        AccountCapability.PORTFOLIO_READ
    ],

    # Liberator Securities (Live)
    ("LIBERATOR", AccountType.CASH.value): [
        AccountCapability.EQUITY_TRADE,
        AccountCapability.PORTFOLIO_READ
    ],
}


class AccountEnvironment(str, Enum):
    LIVE = "LIVE"                  # เงินจริง
    SIMULATION = "SIMULATION"      # เงินเสมือน
    SANDBOX = "SANDBOX"            # เงินเสมือน (Sandbox)


class AccountInfo(HybridBaseModel):
    account_no: str = Field(..., description="Unique trading account number")
    broker_name: str = Field(..., description="Human-readable broker/institution name")
    account_type: AccountType = Field(..., description="Account category (EQUITY, DERIVATIVES, CASH, MARGIN)")
    platform: str = Field(..., description="Broker platform identifier (CLICK2WIN, KRUNGSRI, SETTRADE_OPENAPI, LIBERATOR)")
    environment: AccountEnvironment = Field(..., description="Account trading mode (LIVE or SIMULATION/SANDBOX)")
    environment_label: str = Field(..., description="Display label in Thai (เช่น 'เงินจริง' หรือ 'เงินเสมือน')")
    description: str = Field(..., description="Human-readable account label")
    capabilities: List[AccountCapability] = Field(default_factory=list, description="Permitted operations on this account")
    is_active: bool = Field(default=False, description="Whether this account is currently active for operations")
    switch_command: str = Field(..., description="Example MCP command to switch into this account")
    line_available: float = Field(default=0.0, description="Available purchasing power / Line available")
    cash_balance: float = Field(default=0.0, description="Cash balance")


class AccountContext(HybridBaseModel):
    """
    State manager tracking currently active working accounts across platforms.
    """
    click2win_active: AccountType = Field(default=AccountType.EQUITY)
    krungsri_active: AccountType = Field(default=AccountType.CASH)
    settrade_active: AccountType = Field(default=AccountType.EQUITY)
    liberator_active: AccountType = Field(default=AccountType.CASH)
    last_switched: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_active(self, platform: str) -> AccountType:
        plat = platform.upper().strip()
        if plat in ["KRUNGSRI", "TRADEMAN"]:
            return self.krungsri_active
        elif plat in ["SETTRADE_OPENAPI", "SETTRADE"]:
            return self.settrade_active
        elif plat in ["LIBERATOR"]:
            return self.liberator_active
        return self.click2win_active

    def set_active(self, platform: str, account_type: AccountType) -> None:
        plat = platform.upper().strip()
        if plat in ["KRUNGSRI", "TRADEMAN"]:
            self.krungsri_active = account_type
        elif plat in ["SETTRADE_OPENAPI", "SETTRADE"]:
            self.settrade_active = account_type
        elif plat in ["LIBERATOR"]:
            self.liberator_active = account_type
        else:
            self.click2win_active = account_type
        self.last_switched = datetime.now(timezone.utc)


# Global Account Context Singleton
account_context = AccountContext()


class AccountCapabilityGuardrail:
    """
    Strict TypeSafe Capability Guardrail Engine.
    Validates whether an account is authorized for a specific operation.
    """
    @staticmethod
    def normalize_account_type(platform: str, acc_type: Optional[str]) -> AccountType:
        plat = platform.upper().strip()
        if not acc_type:
            return account_context.get_active(plat)

        t = acc_type.upper().strip()
        if plat in ["KRUNGSRI", "TRADEMAN"]:
            if t in ["MARGIN", "CREDIT_BALANCE", "CREDIT", "SBL"]:
                return AccountType.MARGIN
            return AccountType.CASH
        elif plat in ["LIBERATOR"]:
            # Liberator Securities WebTrade is a single-account (Cash) broker.
            # No MARGIN (SBL) or DERIVATIVES environments exist.
            return AccountType.CASH
        else:
            if t in ["DERIVATIVES", "TFEX", "FUTURES"]:
                return AccountType.DERIVATIVES
            return AccountType.EQUITY

    @classmethod
    def validate_capability(
        cls,
        platform: str,
        account_type: Optional[str],
        required_capability: AccountCapability
    ) -> Tuple[bool, Optional[str], AccountType]:
        """
        Validates if target platform and account have the required capability.
        Returns (is_allowed, error_message, resolved_account_type).
        """
        p = platform.upper().strip()
        if p in ["KRUNGSRI", "TRADEMAN"]:
            plat = "KRUNGSRI"
        elif p in ["SETTRADE_OPENAPI", "SETTRADE"]:
            plat = "SETTRADE_OPENAPI"
        elif p in ["LIBERATOR"]:
            plat = "LIBERATOR"
        else:
            plat = "CLICK2WIN"
        resolved_type = cls.normalize_account_type(plat, account_type)

        key = (plat, resolved_type.value)
        allowed_caps = ACCOUNT_CAPABILITY_MATRIX.get(key, [])

        if required_capability in allowed_caps:
            return True, None, resolved_type

        # Generate targeted strict rejection message
        if required_capability in [AccountCapability.SBL_BORROW, AccountCapability.SBL_RETURN]:
            err = (
                f"Strict Guardrail Rejection: SBL operation '{required_capability.value}' is strictly restricted "
                f"to Krungsri 'MARGIN' (Credit Balance) accounts. Current target is {plat} '{resolved_type.value}'. "
                f"Please switch account using switch_account(platform='KRUNGSRI', account_type='MARGIN') first."
            )
        elif required_capability == AccountCapability.TFEX_TRADE:
            err = (
                f"Strict Guardrail Rejection: TFEX trading is restricted to 'DERIVATIVES' accounts. "
                f"Current target is {plat} '{resolved_type.value}'. "
                f"Please switch account using switch_account(platform='{plat}', account_type='DERIVATIVES') first."
            )
        elif required_capability == AccountCapability.EQUITY_TRADE:
            err = (
                f"Strict Guardrail Rejection: Stock trading is restricted to 'EQUITY' or 'CASH' accounts. "
                f"Current target is {plat} '{resolved_type.value}'. "
                f"Please switch account using switch_account(platform='{plat}', account_type='EQUITY') first."
            )
        else:
            err = (
                f"Strict Guardrail Rejection: Operation '{required_capability.value}' is not permitted "
                f"on {plat} account type '{resolved_type.value}'."
            )

        return False, err, resolved_type


account_guardrail = AccountCapabilityGuardrail()
