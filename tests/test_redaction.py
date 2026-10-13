"""Log-safety helpers (TASK-cli-p1 item 6) — OTP codes and SSO tokens never reach logs.

Guard rail: redaction is **log-only**. The cross-process relay row keeps the real OTP
because each driver parses it back with ``auth_driver.OTP_SESSION_LOG_PATTERN``.
"""

from app.services.redaction import redact_otp, redact_otp_details, redact_url


def test_redact_otp_never_returns_the_code():
    assert redact_otp("123456") == "******"
    assert redact_otp("") == ""
    assert redact_otp(None) == ""


def test_redact_url_masks_secret_query_values():
    url = "https://trademan.in.th/start_SSO.aspx?page=TM&token=eyJhbGciOiJ9abc&lang=th"

    out = redact_url(url)

    assert "eyJhbGciOi" not in out
    assert "token=<redacted>" in out
    assert "page=TM" in out and "lang=th" in out      # non-secret params survive


def test_redact_url_masks_otp_and_code_params():
    assert redact_url("https://x/y?otp=123456") == "https://x/y?otp=<redacted>"
    assert redact_url("https://x/y?token=abc#frag") == "https://x/y?token=<redacted>#frag"
    assert redact_url(None) == ""


def test_redact_otp_details_masks_only_the_otp():
    details = "Received OTP 6-digits from LINE: 123456 (Ref: 99887766) (Broker: KSS)"

    out = redact_otp_details(details)

    assert "123456" not in out
    assert "******" in out
    assert "(Ref: 99887766)" in out          # a ref code is not a secret
    assert "(Broker: KSS)" in out
    assert redact_otp_details(None) == ""


def test_db_relay_payload_keeps_the_real_otp():
    """Redaction must stay log-only — drivers read the code back from this row."""
    from app.services.otp_relay_registry import format_otp_details

    details = format_otp_details("123456", "999", "kss")

    assert "123456" in details
    assert "******" not in details
