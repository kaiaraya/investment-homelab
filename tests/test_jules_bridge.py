import pytest

from scripts.jules_bridge import (
    build_jules_prompt,
    find_forbidden_files,
    normalize_local_task_branch,
    parse_handoff_metadata,
    validate_jules_readiness,
)


def test_find_forbidden_files_blocks_secrets_and_allows_env_example():
    sample = [
        "app/main.py",
        ".env.example",
        ".env",
        "data/session_state.json",
        "data/liberator_session.json",
        "investment_homelab.db",
        "data/screenshots/live_test.png",
        "docs/handoff/TASK-loop1-1.md",
    ]
    offenders = find_forbidden_files(sample)
    assert ".env" in offenders
    assert "data/session_state.json" in offenders
    assert "data/liberator_session.json" in offenders
    assert "investment_homelab.db" in offenders
    assert "data/screenshots/live_test.png" in offenders
    assert ".env.example" not in offenders
    assert "app/main.py" not in offenders


def test_parse_handoff_metadata_routes_t0_to_flash_and_t1_to_pro():
    md_t0 = """# TASK-sample: test
- Tier: 🟢 T0
- Pre-Coding Probe: NONE
- Verify: `.venv/bin/python scripts/verify_changes.py app/main.py`
"""
    meta_t0 = parse_handoff_metadata(md_t0)
    assert meta_t0["tier"] == "T0"
    assert meta_t0["model"] == "Gemini 3.6 Flash"
    assert meta_t0["probe_state"] == "NONE"

    md_t1 = """# TASK-sample: test
- Tier: 🟡 T1
- Pre-Coding Probe: PROBE_DONE
- Verify: `.venv/bin/python scripts/verify_changes.py app/main.py`

## DOM / API Contract
- URL: `https://www.liberator.co.th/Portfolio`
- Endpoint: `POST /vb/stock/info` returns `{"n": "BCH", "bp": 11.3, "op": 11.4}`
"""
    meta_t1 = parse_handoff_metadata(md_t1)
    assert meta_t1["tier"] == "T1"
    assert meta_t1["model"] == "Gemini 3.1 Pro"
    assert meta_t1["probe_state"] == "PROBE_DONE"
    assert meta_t1["has_dom_contract"] == "true"


def test_validate_jules_readiness_blocks_when_probe_needed_or_t2():
    md_probe_needed = """# TASK-ui-fix
- Tier: 🟡 T1
- Pre-Coding Probe: PROBE_NEEDED
"""
    ok, reason, _ = validate_jules_readiness("docs/handoff/TASK-ui-fix.md", md_probe_needed)
    assert ok is False
    assert "PROBE_NEEDED" in reason

    md_t2 = """# TASK-live-round
- Tier: 🔴 T2
"""
    ok_t2, reason_t2, _ = validate_jules_readiness("docs/handoff/TASK-live-round.md", md_t2)
    assert ok_t2 is False
    assert "Tier T2" in reason_t2


def test_build_jules_prompt_includes_model_and_dom_contract_instruction():
    md = """# TASK-kss-selector-update
- Tier: 🟡 T1
- Pre-Coding Probe: PROBE_DONE
- Verify: `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py`

## DOM / API Contract
- Selector: `div.bg-darkGray span.pp-value` confirmed on Margin 3024959
"""
    prompt = build_jules_prompt("docs/handoff/TASK-kss-selector-update.md", md)
    assert "Gemini 3.1 Pro" in prompt
    assert "task/kss-selector-update" in prompt
    assert "DOM / API Contract" in prompt
    assert "scripts/verify_changes.py app/browser/trademan_driver.py" in prompt


def test_normalize_local_task_branch():
    assert normalize_local_task_branch("jules/fix-kss-nego") == "task/fix-kss-nego"
    assert normalize_local_task_branch("TASK-loop1-3-lib") == "task/loop1-3-lib"
    assert normalize_local_task_branch("task/already-prefixed") == "task/already-prefixed"
