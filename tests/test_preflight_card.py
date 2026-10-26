"""
Unit tests for scripts/preflight_card.py pre-dispatch gate.
"""

from pathlib import Path
import scripts.preflight_card as pc


GOOD_CARD = """# TASK-test-good
- Lane: homelab-build
- Tier: 🟢 T0
- Probe: PROBE_DONE
- Verify: .venv/bin/python scripts/verify_changes.py app/main.py

## DOM / API Contract
Verified selectors on broker screen: #btn-submit, #input-price, table.orders (confirmed live).

## Acceptance
- .venv/bin/python -m pytest tests/test_main.py -q
- verify_changes.py exits 0
"""


def test_check_card_good_card_passes():
    errors, warnings = pc.check_card(GOOD_CARD)
    assert errors == []


def test_check_card_probe_needed_fails():
    card = """# TASK-test-probe-needed
- Tier: 🟢 T0
- Probe: PROBE_NEEDED
- Verify: pytest tests/test_foo.py

## Acceptance
- all pass
"""
    errors, _ = pc.check_card(card)
    assert any("probe gate" in e.lower() and "probe_needed" in e.lower() for e in errors)


def test_check_card_probe_done_empty_contract_fails():
    card = """# TASK-test-empty-contract
- Tier: 🟢 T0
- Probe: PROBE_DONE
- Verify: pytest tests/test_foo.py

## DOM / API Contract

## Acceptance
- all pass
"""
    errors, _ = pc.check_card(card)
    assert any("probe gate" in e.lower() and "empty" in e.lower() for e in errors)


def test_check_card_t2_without_witness_session_fails():
    card = """# TASK-test-t2-no-witness
- Tier: 🔴 T2
- Probe: NONE
- Verify: pytest tests/test_foo.py

## Acceptance
- all pass
"""
    errors, _ = pc.check_card(card)
    assert any("t2 gate" in e.lower() and "witness session" in e.lower() for e in errors)


def test_check_card_t2_with_valid_witness_session_passes():
    card = """# TASK-test-t2-with-witness
- Tier: 🔴 T2
- Probe: NONE
- Verify: pytest tests/test_foo.py

## Witness Session
- Date: 2026-10-26
- Human: araya at screen
- Exact action: place test order
- DRY_RUN_MODE=false
- Browser: headed

## Acceptance
- all pass
"""
    errors, warnings = pc.check_card(card)
    assert not any("t2 gate" in e.lower() for e in errors)


def test_secret_violations():
    files = [
        ".env",
        "nested/.env.local",
        "data/session_state.json",
        "investment_homelab.db",
        "data/screenshots/screen_1.png",
        "app/main.py",
        "tests/test_something.py",
    ]
    bad = pc.secret_violations(files)
    assert ".env" in bad
    assert "nested/.env.local" in bad
    assert "data/session_state.json" in bad
    assert "investment_homelab.db" in bad
    assert "data/screenshots/screen_1.png" in bad
    assert "app/main.py" not in bad
    assert "tests/test_something.py" not in bad


def test_main_cli_good_card_and_bad_card(tmp_path):
    good_file = tmp_path / "good_card.md"
    good_file.write_text(GOOD_CARD, encoding="utf-8")

    bad_file = tmp_path / "bad_card.md"
    bad_file.write_text("# BAD CARD\nProbe: PROBE_NEEDED\n", encoding="utf-8")

    assert pc.main(["--card", str(good_file), "--skip-git"]) == 0
    assert pc.main(["--card", str(bad_file), "--skip-git"]) == 1
    assert pc.main(["--card", str(tmp_path / "missing.md"), "--skip-git"]) == 2


def test_touches_dom():
    assert pc.touches_dom("Probe: PROBE_DONE") is True
    assert pc.touches_dom("Probe: PROBE_NEEDED") is True
    assert pc.touches_dom("Probe: NONE\nSome text") is False
    assert pc.touches_dom("Touch streaming.settrade portal") is True
    assert pc.touches_dom("Pure docs update with no markers") is False


def test_check_card_contract_gate_missing_verify_command_fails():
    card = """# TASK-test-missing-verify
- Tier: 🟢 T0
- Probe: NONE

## Acceptance
- all pass
"""
    errors, _ = pc.check_card(card)
    assert any("contract gate" in e.lower() and "verify command" in e.lower() for e in errors)


def test_check_card_contract_gate_missing_acceptance_section_fails():
    card = """# TASK-test-missing-acceptance
- Tier: 🟢 T0
- Probe: NONE
- Verify: pytest tests/test_foo.py

## Other Section
- notes
"""
    errors, _ = pc.check_card(card)
    assert any("contract gate" in e.lower() and ("acceptance" in e.lower() or "done when" in e.lower()) for e in errors)


def test_check_card_contract_gate_done_when_satisfies_acceptance():
    card = """# TASK-test-done-when
- Tier: 🟢 T0
- Probe: NONE
- Verify: pytest tests/test_foo.py

## Done when
- all pass
"""
    errors, _ = pc.check_card(card)
    assert not any("contract gate" in e.lower() for e in errors)
