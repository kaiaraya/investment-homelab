"""
Unit tests for the Loop-Engineering verify hook (`scripts/verify_changes.py`).

Covers `.agents/rules/loop_engineering.md` §3 (หนึ่ง unit = หนึ่งคำสั่ง verify):

  - map changed file -> targeted tests via ``MODULE_TEST_MAP`` (SSOT), never guess (Anti-Mock)
  - docs / non-code -> report-only (no test); unknown ``.py`` -> UNMAPPED (exit 2)
  - ``--dry-run`` must never execute pytest; ``--full`` is the single final gate
  - pytest single-writer guard (``test_homelab.db`` cannot take two writers -> deadlock)

No browser, no DB, no real pytest subprocess is started here.
"""

import os

import scripts.verify_changes as vc

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Path normalization
# --------------------------------------------------------------------------- #
def test_rel_normalizes_absolute_and_relative_paths():
    absolute = os.path.join(REPO_ROOT, "app", "services", "line_service.py")
    assert vc._rel(absolute) == "app/services/line_service.py"
    assert vc._rel(os.path.join(REPO_ROOT, "app", "x.py")) == "app/x.py"


def test_py_files_skips_non_python_and_missing_files():
    files = vc._py_files(["app/schemas/auth.py", "AGENTS.md", "app/does_not_exist.py"])
    assert files == ["app/schemas/auth.py"]


# --------------------------------------------------------------------------- #
# Mapping: changed file -> targeted tests
# --------------------------------------------------------------------------- #
def test_resolve_tests_maps_module_to_targeted_tests():
    tests, unmapped, report_only = vc.resolve_tests(["app/services/line_service.py"], [])
    assert "tests/test_webhook_line.py" in tests
    assert "tests/test_line_otp_group.py" in tests
    assert "tests/test_otp_multibroker_attribution.py" in tests
    assert "tests/test_line_flex_card.py" in tests
    assert unmapped == []
    assert report_only == []


def test_resolve_tests_runs_a_touched_test_file_itself():
    tests, unmapped, _ = vc.resolve_tests(["tests/test_db.py"], [])
    assert tests == ["tests/test_db.py"]
    assert unmapped == []


def test_resolve_tests_never_guesses_for_unmapped_python():
    # NOTE: ``app/core/config.py`` used to be the canonical unmapped example, but since
    # the 2026-10-10 /console redesign it IS mapped (tests/test_admin_console.py etc.).
    tests, unmapped, report_only = vc.resolve_tests(["app/ai/memory.py"], [])
    assert tests == []
    assert unmapped == ["app/ai/memory.py"]
    assert report_only == []


def test_resolve_tests_docs_are_report_only():
    tests, unmapped, report_only = vc.resolve_tests(
        ["AGENTS.md", "docs/handoff/TASK-x.md"], []
    )
    assert tests == []
    assert unmapped == []
    assert report_only == ["AGENTS.md", "docs/handoff/TASK-x.md"]


def test_resolve_tests_deduplicates_shared_targets():
    tests, _, _ = vc.resolve_tests(
        ["app/services/otp_relay_registry.py", "app/services/line_service.py"], []
    )
    assert tests.count("tests/test_otp_multibroker_attribution.py") == 1


def test_explicit_tests_override_the_mapping():
    tests, unmapped, report_only = vc.resolve_tests(["app/ai/memory.py"], ["tests/test_db.py"])
    assert (tests, unmapped, report_only) == (["tests/test_db.py"], [], [])


def test_every_mapped_target_exists_on_disk():
    """Mapping-drift guard: a stale path would silently become a pytest usage error."""
    for module, targets in vc.MODULE_TEST_MAP.items():
        assert os.path.exists(os.path.join(REPO_ROOT, module)), module
        for target in targets:
            assert target.startswith("tests/") and target.endswith(".py"), target
            assert os.path.exists(os.path.join(REPO_ROOT, target)), target


# --------------------------------------------------------------------------- #
# pytest single-writer guard
# --------------------------------------------------------------------------- #
def test_guard_blocked_is_true_when_another_pytest_is_live(monkeypatch):
    monkeypatch.setattr(vc, "_pytest_already_running", lambda: ["pid 123: pytest tests/ -q"])
    assert vc._guard_blocked() is True


def test_guard_blocked_is_false_when_alone(monkeypatch):
    monkeypatch.setattr(vc, "_pytest_already_running", lambda: [])
    assert vc._guard_blocked() is False


# --------------------------------------------------------------------------- #
# main() exit-code contract (run_pytest is stubbed — no subprocess, no DB)
# --------------------------------------------------------------------------- #
def _stub_runner(monkeypatch, calls):
    """Silences the guard and records any pytest invocation instead of running it."""

    def _record(targets, label):
        calls.append((list(targets), label))
        return 0

    monkeypatch.setattr(vc, "run_pytest", _record)
    monkeypatch.setattr(vc, "_guard_blocked", lambda: False)


def test_dry_run_never_executes_pytest(monkeypatch):
    calls = []
    _stub_runner(monkeypatch, calls)
    assert vc.main(["--dry-run", "app/schemas/auth.py"]) == 0
    assert calls == []


def test_targeted_run_uses_the_mapped_test_file(monkeypatch):
    calls = []
    _stub_runner(monkeypatch, calls)
    assert vc.main(["app/schemas/auth.py"]) == 0
    assert calls == [(["tests/test_type_safe_auth.py"], "targeted")]


def test_unmapped_file_exits_2_without_running_pytest(monkeypatch):
    calls = []
    _stub_runner(monkeypatch, calls)
    assert vc.main(["app/ai/memory.py"]) == 2
    assert calls == []


def test_docs_only_exits_0_without_running_pytest(monkeypatch):
    calls = []
    _stub_runner(monkeypatch, calls)
    assert vc.main(["AGENTS.md"]) == 0
    assert calls == []


def test_full_flag_runs_the_suite_once(monkeypatch):
    calls = []
    _stub_runner(monkeypatch, calls)
    assert vc.main(["--full"]) == 0
    assert calls == [(["tests/"], "full")]


def test_no_arguments_is_a_usage_error(monkeypatch):
    calls = []
    _stub_runner(monkeypatch, calls)
    try:
        vc.main([])
    except SystemExit as exc:  # argparse parser.error() -> exit 2
        assert exc.code == 2
    else:  # pragma: no cover - argparse must reject an empty invocation
        raise AssertionError("main([]) should have exited via parser.error()")
    assert calls == []

