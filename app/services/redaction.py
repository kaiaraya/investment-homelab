"""Shared log-safety helpers — keep OTP codes and SSO tokens out of logs/console.

IMPORTANT (OTP relay invariant): the *authoritative* OTP value must still reach the DB
relay row (``otp_relay_registry.format_otp_details``) because each broker driver parses it
back out via ``auth_driver.OTP_SESSION_LOG_PATTERN``. Only human-readable log / console
text is redacted here — **never** the DB payload.
"""

from __future__ import annotations

import re
from typing import Any, Optional

#: Mask the value of secret-bearing query params: ``?token=eyJ...`` -> ``?token=<redacted>``.
_SECRET_QUERY_RE = re.compile(r"(?i)\b(token|otp|code|session|access_token|id_token)=([^&#\s]+)")
#: The relay details line: ``Received OTP 6-digits from LINE: 123456 (Ref: ...)``.
_OTP_DETAILS_RE = re.compile(r"(?i)(OTP[^:]*:\s*)(\d{4,8})")

REDACTED = "******"
URL_REDACTED = "<redacted>"


def redact_otp(otp: Optional[Any]) -> str:
    """Masked form of an OTP code — never the code itself."""
    return REDACTED if otp else ""


def redact_url(url: Optional[str]) -> str:
    """Mask secret query-string values (``?token=...`` -> ``?token=<redacted>``)."""
    if not url:
        return ""
    return _SECRET_QUERY_RE.sub(lambda m: f"{m.group(1)}={URL_REDACTED}", str(url))


def redact_otp_details(details: Optional[str]) -> str:
    """Mask the OTP inside an ``OTP_RECEIVED`` details/log string (DB row stays intact)."""
    if not details:
        return ""
    return _OTP_DETAILS_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", str(details))


__all__ = ["REDACTED", "URL_REDACTED", "redact_otp", "redact_otp_details", "redact_url"]
