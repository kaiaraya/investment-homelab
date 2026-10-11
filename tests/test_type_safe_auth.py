import pytest
from datetime import datetime
from pydantic import ValidationError, SecretStr
from pydantic_ai.models.test import TestModel

from app.schemas.auth import (
    BrokerPlatform,
    AuthStatus,
    OTPSource,
    OTPPayload,
    LoginCredentials,
    LoginResult,
    OTPExtractResult,
)
from app.core.events import InternalEventBus
from app.ai.otp_agent import extract_otp_from_text


def test_login_result_type_safety_and_hybrid_access():
    """Verify LoginResult provides static type safety AND backward-compatible dict access."""
    res = LoginResult(
        success=True,
        status=AuthStatus.AUTHENTICATED,
        broker=BrokerPlatform.TRADEMAN,
        resumed=True,
        url="https://trademan.in.th/portfolio",
        otp_ref="BIPE",
        message="Session active"
    )

    # 1. Dot notation
    assert res.success is True
    assert res.status == AuthStatus.AUTHENTICATED
    assert res.broker == BrokerPlatform.TRADEMAN
    assert res.url == "https://trademan.in.th/portfolio"
    assert res.otp_ref == "BIPE"

    # 2. Backward compatibility with dict access
    assert res["success"] is True
    assert res["status"] == AuthStatus.AUTHENTICATED
    assert res.get("url") == "https://trademan.in.th/portfolio"
    assert res.get("non_existent", "default_val") == "default_val"
    assert "otp_ref" in res

    # 3. Pythonic Boolean evaluation
    assert bool(res) is True
    failed_res = LoginResult(
        success=False,
        status=AuthStatus.FAILED,
        broker=BrokerPlatform.CLICK2WIN,
        message="Login rejected"
    )
    assert bool(failed_res) is False


def test_otp_payload_validation_and_masking():
    """Verify strict 6-digit regex validation and log masking."""
    # Valid OTP
    valid_payload = OTPPayload(
        otp="123456",
        ref="ABCD",
        source=OTPSource.KDE_CONNECT,
        sender="KrungsriSec"
    )
    assert valid_payload.otp == "123456"
    assert valid_payload.masked_otp == "12****"
    assert valid_payload["otp"] == "123456"

    # Invalid OTPs
    with pytest.raises(ValidationError):
        OTPPayload(otp="12345")  # only 5 digits

    with pytest.raises(ValidationError):
        OTPPayload(otp="1234567")  # 7 digits

    with pytest.raises(ValidationError):
        OTPPayload(otp="ABCDEF")  # non-numeric


def test_login_credentials_secret_masking():
    """Verify passwords and PINs are securely masked in logs and dumps."""
    creds = LoginCredentials(
        username="trader01",
        password=SecretStr("SuperSecretPass!"),
        pin=SecretStr("998877"),
        broker=BrokerPlatform.CLICK2WIN
    )

    # Must never expose secret in str or repr
    assert "SuperSecretPass!" not in str(creds)
    assert "SuperSecretPass!" not in repr(creds)
    assert "998877" not in str(creds)

    # Exposed only via explicit get_secret_value()
    assert creds.password.get_secret_value() == "SuperSecretPass!"
    assert creds.pin.get_secret_value() == "998877"


@pytest.mark.asyncio
async def test_event_bus_type_safe_otp():
    """Verify InternalEventBus validates and publishes OTPPayload."""
    bus = InternalEventBus()

    # 1. Publish typed OTPPayload
    payload = OTPPayload(otp="849201", ref="XYZW", source=OTPSource.LINE_CHAT)
    res = await bus.publish_otp(payload)
    assert res.otp == "849201"
    assert bus.otp_queue.qsize() == 1

    event = await bus.otp_queue.get()
    assert event["payload"].otp == "849201"
    assert event["data"]["otp"] == "849201"
    assert event["data"]["ref"] == "XYZW"

    # 2. Publish raw dictionary (auto-converted & validated)
    res2 = await bus.publish_otp({"otp": "654321", "ref": "BIPE", "source": "api_manual_entry"})
    assert isinstance(res2, OTPPayload)
    assert res2.otp == "654321"
    assert bus.get_latest_otp_payload().otp == "654321"

    # 3. Invalid dict raises ValidationError
    with pytest.raises(ValidationError):
        await bus.publish_otp({"otp": "bad_otp"})


@pytest.mark.asyncio
async def test_dual_engine_otp_extraction_regex():
    """Test fast regex extraction for typical SMS and chat patterns."""
    # Pattern 1: Pure 6 digits
    res1 = await extract_otp_from_text("849201")
    assert res1.otp == "849201"
    assert res1.ref is None

    # Pattern 2: Thai SMS format
    res2 = await extract_otp_from_text("Krungsri Sec: รหัส OTP ของคุณคือ 748291 รหัสอ้างอิง BIPE ใช้งานได้ภายใน 3 นาที")
    assert res2.otp == "748291"
    assert res2.ref == "BIPE"

    # Pattern 3: English SMS format
    res3 = await extract_otp_from_text("Your OTP is 112233 (Ref: ABCD). Do not share.")
    assert res3.otp == "112233"
    assert res3.ref == "ABCD"
