"""CLI-RCA-011 (P2a) — the Account Info probe must stay shape-only and browser-free.

Importing the module here (with no playwright/browser runtime) is itself part of the
contract: ``sanitize`` is the pure half that the human-run probe shares with this suite.
"""
import inspect
import json
import re

from scripts.krungsri import probe_account_info as probe


def test_module_imports_without_playwright():
    """No playwright symbol may live in the module namespace — it is imported inside main()."""
    assert [k for k in probe.__dict__ if "playwright" in k.lower()] == []


def test_sanitize_never_leaks_money_or_account_numbers():
    raw = [
        {"label": "Line Available", "value": "250,000.00", "selector_path": "div.panel > div:nth"},
        {"label": "Trading A/C 3024959", "value": "3024959"},
        {"label": "Excess Equity", "value": "-1,234.56"},
        {"label": "%MM", "value": "45.75%"},
    ]

    out = probe.sanitize(raw)
    blob = json.dumps(out, ensure_ascii=False)

    assert not any(ch.isdigit() for ch in blob)     # zero digits: no figure, no account number
    assert "<num>" in blob                          # F2: comma-grouped numbers are hidden too
    assert "3024959" not in blob


def test_sanitize_drops_value_like_labels():
    """F2: a leaf whose text is a figure is a value — the row is dropped, not kept as a label."""
    raw = [
        {"label": "123,456.78", "value": ""},
        {"label": "-1,234.50", "value": ""},
        {"label": "12.5%", "value": ""},
        {"label": "(1,000.00)", "value": ""},
        {"label": "฿ 2,000", "value": ""},
        {"label": "2,000 THB", "value": ""},
        {"label": "Line Available", "value": "250,000.00"},
        {"label": "%MM", "value": "45.75%"},
    ]

    labels = [r["label"] for r in probe.sanitize(raw)]

    assert labels == ["Line Available", "%MM"]      # %MM is a label, never treated as a percent


def test_sanitize_dump_has_no_long_digit_run():
    """F2 regression: after stripping commas, no 4+-digit run may survive anywhere in the dump."""
    raw = [
        {"label": "Trading A/C 3024959", "value": "3024959", "selector_path": "div#panel > span.a"},
        {"label": "Line Available", "value": "250,000.00",
         "selector_path": "div.cc:nth-of-type(2)", "value_path": "div.cc:nth-of-type(3)"},
    ]

    blob = json.dumps(probe.sanitize(raw), ensure_ascii=False)

    assert not re.search(r"\d{4,}", blob.replace(",", ""))
    assert "<num>" in blob
    assert "3024959" not in blob and "250,000.00" not in blob


def test_sanitize_value_shapes():
    raw = [
        {"label": "amount", "value": "1,234.00"},
        {"label": "negative", "value": "-1,234.00"},
        {"label": "percent", "value": "12.34%"},
        {"label": "dash", "value": "-"},
        {"label": "blank", "value": "   "},
        {"label": "words", "value": "Trading A/C"},
    ]

    shapes = {r["label"]: r["value_shape"] for r in probe.sanitize(raw)}

    assert shapes == {
        "amount": "#,###.##", "negative": "-#,###.##", "percent": "#.##%",
        "dash": "empty", "blank": "empty", "words": "text",
    }


def test_sanitize_keeps_thai_and_english_labels():
    raw = [
        {"label": "เงินสดคงเหลือ", "value": "1.00"},
        {"label": "Cash Balance", "value": "1.00"},
        {"label": "Excess Equity", "value": "1.00"},
    ]

    labels = [r["label"] for r in probe.sanitize(raw)]

    assert labels == ["เงินสดคงเหลือ", "Cash Balance", "Excess Equity"]
    assert {"Cash Balance", "Excess Equity", "เงินสดคงเหลือ"}.issubset(set(probe.TARGET_LABELS))


def test_sanitize_returns_value_path():
    """F3: the sibling path travels with the row; a row with no sibling value gets ``""``."""
    raw = [{"label": "Line Available", "value": "1.00",
            "selector_path": "div.card > span.a", "value_path": "div.card > span.b"}]

    out = probe.sanitize(raw)

    assert out[0]["selector_path"] == "div.card > span.a"
    assert out[0]["value_path"] == "div.card > span.b"
    assert probe.sanitize([{"label": "No sibling", "value": "1.00"}])[0]["value_path"] == ""


def test_panel_js_computes_css_paths():
    """F3 guard: the injected JS builds a path for the label and for its value-sibling."""
    assert "const cssPath = (el) =>" in probe._PANEL_JS
    assert "selector_path: cssPath(el)" in probe._PANEL_JS
    assert "value_path: sibText ? cssPath(sib) : ''" in probe._PANEL_JS
    assert "if (node.id)" in probe._PANEL_JS                 # id short-circuit
    assert ":nth-of-type(" in probe._PANEL_JS                # position disambiguation
    assert "() => {" in probe._PANEL_JS                      # still a plain page.evaluate payload


def test_sanitize_drops_rows_without_label():
    assert probe.sanitize([{"value": "1.00"}, {"label": "", "value": "2.00"}]) == []
    assert probe.sanitize(None) == []


def test_probe_never_clicks_the_page_body():
    """F1: a bare body click could land on a button/table row — Escape closes the dropdown instead."""
    src = inspect.getsource(probe)

    assert 'click("body")' not in src
    assert 'keyboard.press("Escape")' in src


def test_dropdown_is_opened_before_counting_options():
    """F4: the options exist only while the dropdown is open, so the open must come first."""
    src = inspect.getsource(probe)

    assert src.index('click("#dropDownAccountPort")') < src.index("option.count()")


def test_probe_is_read_only_no_login_or_order_code():
    """Acceptance guard: no order/login/OTP code and no session write in the probe."""
    src = inspect.getsource(probe)

    for banned in ("place_order", "amend_order", "cancel_order",
                   "send_otp", "request_otp", "storage_state(path"):
        assert banned not in src
    assert "storage_state=settings.SESSION_STATE_PATH" in src   # read-only reuse only
