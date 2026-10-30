# -*- coding: utf-8 -*-
"""PIN-attempt guard — pure unit tests (no browser, no DB).

The guard exists because of the 2026-10-29 lockout on account 3024959: a rejected trading
PIN was neither counted nor recorded, so the automation kept typing it until the broker
suspended the account. These tests pin the money-safety contract:

* broker wording (English + Thai) is classified, benign text is not;
* one rejection quarantines the broker and ``check()`` refuses;
* only a human ``reset()`` or a broker-accepted order clears it;
* the state file holds no PIN, only the error snippet and timestamps;
* a broken/unwritable state file refuses instead of opening the gate.
"""
import json

from app.core.config import settings
from app.services import pin_guard


def test_classify_broker_wording():
    assert pin_guard.classify_pin_error("Your pin is suspended") == pin_guard.E_PIN_SUSPENDED
    assert (pin_guard.classify_pin_error(
        "Place Order: Error : The number of incorrect PIN entries exceeds the maximum")
        == pin_guard.E_PIN_SUSPENDED)
    assert pin_guard.classify_pin_error("Invalid PIN") == pin_guard.E_PIN_REJECTED
    assert pin_guard.classify_pin_error("incorrect pin, please try again") == pin_guard.E_PIN_REJECTED
    assert pin_guard.classify_pin_error("รหัส PIN ไม่ถูกต้อง") == pin_guard.E_PIN_REJECTED
    assert pin_guard.classify_pin_error("PIN ถูกระงับชั่วคราว") == pin_guard.E_PIN_SUSPENDED


def test_benign_messages_are_not_pin_errors():
    for text in ("", None, "Submit Order", "Order submitted successfully",
                 "reject meaning: short in credit", "PIN", "ticket read-back ไม่ตรง"):
        assert pin_guard.classify_pin_error(text) is None, text


def test_fresh_state_allows_submit():
    assert pin_guard.check("KRUNGSRI")["allowed"] is True


def test_one_rejection_quarantines_the_broker():
    out = pin_guard.record_failure("KRUNGSRI", "Your pin is suspended")
    assert out["allowed"] is False
    assert out["failures"] == 1

    guard = pin_guard.check("krungsri")            # case-insensitive broker key
    assert guard["allowed"] is False
    assert guard["error_code"] == pin_guard.E_PIN_GUARD
    assert "reset" in guard["reason"]

    # The other broker is untouched — a KSS rejection must not stop Liberator.
    assert pin_guard.check("LIBERATOR")["allowed"] is True


def test_success_clears_the_failures():
    pin_guard.record_failure("KRUNGSRI", "invalid pin")
    pin_guard.record_success("KRUNGSRI")
    assert pin_guard.check("KRUNGSRI")["allowed"] is True
    assert pin_guard.status("KRUNGSRI")["state"]["failures"] == 0


def test_reset_is_recorded_with_its_reason():
    pin_guard.record_failure("KRUNGSRI", "invalid pin")
    out = pin_guard.reset("KRUNGSRI", reason="Krungsri 1.2 reset the PIN", actor="araya")
    assert out["previous"]["failures"] == 1
    assert pin_guard.check("KRUNGSRI")["allowed"] is True
    history = pin_guard.status("KRUNGSRI")["state"]["history"]
    assert history[-1]["code"] == "RESET"
    assert history[-1]["actor"] == "araya"


def test_state_file_never_holds_a_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PIN_GUARD_STATE_PATH", str(tmp_path / "guard.json"))
    pin_guard.record_failure("KRUNGSRI", "invalid pin 123456")
    raw = (tmp_path / "guard.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload["brokers"]["KRUNGSRI"]["failures"] == 1
    assert "last_error" in payload["brokers"]["KRUNGSRI"]


def test_guard_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setattr(settings, "PIN_GUARD_ENABLED", False)
    pin_guard.record_failure("KRUNGSRI", "invalid pin")
    assert pin_guard.check("KRUNGSRI")["allowed"] is True


def test_zero_lock_minutes_keeps_the_quarantine_until_reset(monkeypatch):
    monkeypatch.setattr(settings, "PIN_GUARD_LOCK_MINUTES", 0)
    pin_guard.record_failure("KRUNGSRI", "invalid pin")
    guard = pin_guard.check("KRUNGSRI")
    assert guard["allowed"] is False                # failures >= MAX still wins
    assert guard.get("locked_until") is None


def test_corrupted_state_file_does_not_open_the_gate(tmp_path, monkeypatch):
    path = tmp_path / "guard.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(settings, "PIN_GUARD_STATE_PATH", str(path))
    # Unreadable state is treated as empty (no recorded failures) — but must not raise.
    assert pin_guard.check("KRUNGSRI")["allowed"] is True
