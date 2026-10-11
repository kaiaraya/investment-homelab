from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class HybridBaseModel(BaseModel):
    """
    Pydantic V2 BaseModel with dictionary-like access (__getitem__, get, __contains__)
    for 100% backward compatibility with legacy scripts while providing full static typing.
    """
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


class BrokerPlatform(str, Enum):
    TRADEMAN = "TRADEMAN"
    CLICK2WIN = "CLICK2WIN"
    LIBERATOR = "LIBERATOR"


class AuthStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    NAVIGATING = "NAVIGATING"
    CREDENTIALS_SUBMITTED = "CREDENTIALS_SUBMITTED"
    AWAITING_OTP = "AWAITING_OTP"
    AUTHENTICATED = "AUTHENTICATED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    TIMEOUT = "TIMEOUT"
    BRIDGE_DOWN = "BRIDGE_DOWN"


class OTPSource(str, Enum):
    KDE_CONNECT = "kdeconnect_sms"
    LINE_CHAT = "line_chat"
    API_MANUAL = "api_manual_entry"
    CLI_TERMINAL = "cli_terminal"
    EVENT_BUS = "event_bus"
    BROWSER_DOM = "browser_dom_manual"


class OTPPayload(HybridBaseModel):
    otp: str = Field(..., description="6-digit numeric OTP code")
    ref: Optional[str] = Field(default=None, description="Optional broker reference code (e.g. BIPE)")
    broker: Optional[str] = Field(
        default=None,
        description="Broker tag this OTP belongs to (LINE-RCA-010 / latest-request-wins). "
                    "None = unattributed legacy path. Lets each broker's driver ignore "
                    "the other broker's OTP instead of cross-consuming it.",
    )
    source: OTPSource = Field(default=OTPSource.API_MANUAL, description="Ingestion channel")
    sender: Optional[str] = Field(default=None, description="Sender header or origin")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Ingestion timestamp")

    @field_validator("otp")
    @classmethod
    def validate_otp_digits(cls, v: str) -> str:
        clean = str(v).strip()
        if not (clean.isdigit() and len(clean) == 6):
            raise ValueError(f"OTP must be exactly 6 digits, received: '{v}'")
        return clean

    @property
    def masked_otp(self) -> str:
        if len(self.otp) == 6:
            return f"{self.otp[:2]}****"
        return "******"

    @property
    def otp_code(self) -> str:
        return self.otp


class LoginCredentials(HybridBaseModel):
    username: str = Field(..., description="Broker username or trading account ID")
    password: SecretStr = Field(..., description="Broker password (masked in logs)")
    pin: Optional[SecretStr] = Field(default=None, description="Broker 6-digit trading PIN (masked in logs)")
    broker: BrokerPlatform = Field(default=BrokerPlatform.TRADEMAN, description="Broker platform target")
    timeout_otp: Optional[int] = Field(default=None, description="Custom OTP timeout in seconds")


class LoginResult(HybridBaseModel):
    success: bool = Field(..., description="Whether the login attempt succeeded")
    status: AuthStatus = Field(..., description="Current authentication status")
    broker: BrokerPlatform = Field(default=BrokerPlatform.TRADEMAN, description="Broker platform")
    resumed: bool = Field(default=False, description="Whether an existing session was reused")
    url: Optional[str] = Field(default=None, description="Active browser URL upon completion")
    otp_ref: Optional[str] = Field(default=None, description="Broker 2FA OTP reference code if prompt was reached")
    otp_source: Optional[OTPSource] = Field(
        default=None,
        description="Honest capture channel that supplied the OTP (None when no 2FA OTP was required). "
                    "LINE-RCA-009: while the authoritative LINE channel is active this must NOT be kdeconnect_sms.",
    )
    message: Optional[str] = Field(default=None, description="Human-readable status or diagnostic description")
    error_code: Optional[str] = Field(default=None, description="Standardized error code if failed")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event timestamp")

    def __bool__(self) -> bool:
        return self.success


class OTPExtractResult(HybridBaseModel):
    otp: Optional[str] = Field(default=None, description="Extracted 6-digit OTP")
    ref: Optional[str] = Field(default=None, description="Extracted Reference code (e.g. BIPE)")
    source_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
    raw_message: Optional[str] = Field(default=None, description="Original unparsed text")
