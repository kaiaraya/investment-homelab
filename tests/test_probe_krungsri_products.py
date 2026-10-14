import pytest
from scripts.krungsri.probe_krungsri_products import (
    redact_url,
    is_blocked_request,
    json_shape,
    classify_menu_link,
)


def test_redact_url_sensitive_params():
    url = "https://www.krungsrisecurities.com/app?token=secret123&symbol=CPALL&auth_ticket=abc"
    redacted = redact_url(url)
    assert "token=%3Credacted%3E" in redacted or "token=<redacted>" in redacted
    assert "auth_ticket=%3Credacted%3E" in redacted or "auth_ticket=<redacted>" in redacted
    assert "symbol=CPALL" in redacted


def test_is_blocked_request_safety():
    # GET is always allowed
    assert is_blocked_request("GET", "https://example.com/order/list", None) is None

    # SSO form posts are allowed
    assert is_blocked_request("POST", "https://wen046.settrade.com/daytradeflex/streamingSeosMME.jsp", None) is None

    # Write paths on POST are blocked
    assert is_blocked_request("POST", "https://example.com/order/submit", None) == "WRITE_PATH"
    assert is_blocked_request("POST", "https://example.com/trade/place", None) == "WRITE_PATH"

    # Secret fields in body are blocked
    assert is_blocked_request("POST", "https://example.com/api/query", "pin=123456") == "BODY_HAS_SECRET_FIELD"
    assert is_blocked_request("POST", "https://example.com/api/query", "password=secret") == "BODY_HAS_SECRET_FIELD"

    # Read queries on POST without secret are allowed
    assert is_blocked_request("POST", "https://example.com/api/quote/inquiry", "symbol=CPALL") is None


def test_json_shape():
    data = {
        "stock": "CPALL",
        "price": 60.5,
        "bids": [{"price": 60.25, "volume": 1000}],
    }
    shape = json_shape(data)
    assert shape["stock"] == "str"
    assert shape["price"] == "float"
    assert isinstance(shape["bids"], list)


def test_classify_menu_link():
    assert classify_menu_link("Streaming") == "streaming"
    assert classify_menu_link("Quick Trade") == "quicktrade"
    assert classify_menu_link("Krungsri Securities SBL Real Time") == "sbl"
    assert classify_menu_link("TradeMan") == "trademan"
    assert classify_menu_link("Unknown Tool") is None
