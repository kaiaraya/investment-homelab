#!/usr/bin/env python3
"""
Verify Loop Hook — Investment Homelab
=====================================
คำสั่งเดียวสำหรับ "verify 1 unit" ใน Loop Engineering (ห้ามรัน full suite ต่อ loop):
  * compileall ไฟล์ .py ที่แก้ (syntax gate — เร็วมาก)
  * รันเฉพาะ **test ที่แมปกับไฟล์ที่แก้** จาก MODULE_TEST_MAP (targeted verify)
  * single-writer guard — ไม่ยอมรันถ้ามี pytest ตัวอื่นรันอยู่ (test_homelab.db ห้าม concurrent
    — พิสูจน์แล้ว 2026-10-08 ว่า 2 pytest พร้อมกัน deadlock บน SQLite ตัวเดียว)

Design:
  * Targeted > Big-Bang — ต่อ 1 unit เรียกสคริปต์นี้ครั้งเดียว จบด้วย exit code (ดู `.agents/rules/loop_engineering.md` §3)
  * Anti-Mock — ไฟล์ที่ไม่มี mapping จะ **ไม่เดา** ให้รัน (exit 2) จนกว่าจะเพิ่ม mapping หรือใช้ `--tests`
  * Full suite = ใช้ `--full` **ครั้งเดียวตอนปิดงาน** เท่านั้น (ไม่ใช่ทุก loop)

Usage:
  .venv/bin/python scripts/verify_changes.py app/services/line_service.py app/schemas/auth.py
  .venv/bin/python scripts/verify_changes.py --dry-run app/browser/auth_driver.py   # ดูแผนก่อน ไม่รัน
  .venv/bin/python scripts/verify_changes.py --tests tests/test_webhook_line.py     # override mapping
  .venv/bin/python scripts/verify_changes.py --full                                 # ปิดงาน: full suite ครั้งเดียว

Exit code: 0 = PASS, 1 = FAIL, 2 = BLOCKED / UNMAPPED / usage
"""

import argparse
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

PYTHON = os.path.join(REPO_ROOT, ".venv", "bin", "python")
if not os.path.exists(PYTHON):  # pragma: no cover - fallback for odd environments
    PYTHON = sys.executable

FULL_SUITE_TARGET = "tests/"

# ─── Module → targeted test mapping (SSOT: เพิ่มที่นี่ที่เดียวเมื่อมีการแมปใหม่) ───────────
MODULE_TEST_MAP: Dict[str, List[str]] = {
    # OTP relay / LINE (Gate C/D — LINE-RCA-010)
    "app/services/otp_relay_registry.py": ["tests/test_otp_multibroker_attribution.py"],
    "app/services/redaction.py": ["tests/test_redaction.py"],
    "app/services/otp_relay_readiness.py": [
        "tests/test_otp_relay_readiness.py",
        "tests/test_otp_channel_authoritative.py",
        "tests/test_daily_readiness.py",
    ],
    "app/services/line_service.py": [
        "tests/test_otp_multibroker_attribution.py",
        "tests/test_line_otp_group.py",
        "tests/test_webhook_line.py",
        "tests/test_line_flex_card.py",
        "tests/test_line_conversation_flow.py",
    ],
    # LINE per-user conversation state machine (2026-10-12)
    "app/services/conversation_state.py": [
        "tests/test_conversation_state.py",
        "tests/test_line_conversation_flow.py",
    ],
    # LINE slash-command CLI (TASK-line-cli, 2026-10-13)
    "app/services/line_cli/parser.py": ["tests/test_line_cli_parser.py"],
    "app/services/line_cli/cards.py": ["tests/test_line_cli_flow.py"],
    "app/services/line_cli/handlers.py": ["tests/test_line_cli_flow.py"],
    "app/services/line_cli/__init__.py": ["tests/test_line_cli_parser.py"],
    # Pillar 1 session (CLI-RCA-005: /login lib NameError — missing `import os`)
    "app/mcp/pillars/pillar1_session.py": ["tests/test_pillar1_session.py"],
    # Pillar 2 portfolio (CLI-RCA-003 Anti-Mock balances; RCA-002/RCA-006 holdings)
    "app/mcp/pillars/pillar2_portfolio.py": ["tests/test_remote_mcp.py", "tests/test_pillar2_order_ledger.py"],
    "app/services/kdeconnect_service.py": ["tests/test_kdeconnect_service.py"],
    "app/services/action_exit_dispatcher.py": ["tests/test_krungsri_pdca_guardrails.py"],
    "app/api/v1/endpoints/webhook_line.py": [
        "tests/test_webhook_line.py",
        "tests/test_line_otp_group.py",
        "tests/test_otp_multibroker_attribution.py",
    ],
    # Broker drivers (Broker Knowledge Isolation — แยกชุดต่อโบรกเกอร์)
    "app/browser/auth_driver.py": [
        "tests/test_otp_channel_authoritative.py",
        "tests/test_otp_multibroker_attribution.py",
        "tests/test_browser_auto_reconnect.py",
        "tests/test_krungsri_session_health.py",
        "tests/test_auth_session_nondestructive.py",
    ],
    "app/brokers/liberator/driver.py": [
        "tests/test_liberator_session.py",
        "tests/test_liberator_otp_channel_gate.py",
        "tests/test_otp_multibroker_attribution.py",
        "tests/test_otp_channel_authoritative.py",
        "tests/test_liberator_change_order.py",
    ],
    "app/brokers/liberator/plugin.py": [
        "tests/test_liberator_change_order.py",
        "tests/test_pillar2_portfolio_liberator.py",
    ],
    "app/brokers/liberator/cli.py": ["tests/test_liberator_change_order.py"],
    # Contracts / infra
    "app/schemas/auth.py": ["tests/test_type_safe_auth.py"],
    "app/db/session.py": ["tests/test_db.py"],
    # Config + admin console control (/console redesign 2026-10-10)
    "app/core/config.py": [
        "tests/test_admin_console.py",
        "tests/test_console_cockpit_api.py",
    ],
    "app/core/feature_matrix.py": ["tests/test_admin_console.py"],
    "app/api/v1/api.py": [
        "tests/test_admin_console.py",
        "tests/test_console_cockpit_api.py",
    ],
    "app/api/v1/endpoints/admin.py": ["tests/test_admin_console.py"],
    "app/main.py": ["tests/test_console_cockpit_api.py"],
    "app/console.py": ["tests/test_console_cockpit_api.py"],
    # Validator SSOT + Krungsri price negotiation (strict SET Uptick, KSS-RCA 2026-10-09)
    "app/services/validator.py": [
        "tests/test_validator.py",
        "tests/test_trade_negotiation.py",
    ],
    "app/services/price_negotiation_service.py": [
        "tests/test_trade_negotiation.py",
        "tests/test_tpsl_overview_negotiate_api.py",
    ],
    "app/browser/trademan_driver.py": [
        "tests/test_trademan_view_order_scraper.py",
        "tests/test_pillar2_order_ledger.py",
        "tests/test_trademan_amend_bypass_dryrun.py",
        "tests/test_sbl_account_driver.py",
        "tests/test_trademan_portfolio_scraper.py",
    ],
    "app/brokers/krungsri/plugin.py": ["tests/test_broker_registry.py"],
    # Pillar 6 — Krungsri Quick Trade passive price negotiation (2026-10-14)
    "app/brokers/krungsri/quicktrade_driver.py": ["tests/test_quicktrade_driver.py"],
    "app/services/quicktrade_negotiation_service.py": ["tests/test_quicktrade_negotiation_policy.py"],
    "app/api/v1/quicktrade.py": ["tests/test_quicktrade_negotiation_policy.py"],
    "app/core/events.py": [
        "tests/test_otp_multibroker_attribution.py",
        "tests/test_line_otp_group.py",
    ],
    # Ops scripts
    "scripts/verify_changes.py": ["tests/test_verify_changes.py"],
    "scripts/daily_readiness.py": ["tests/test_daily_readiness.py"],
    "scripts/services_status.py": ["tests/test_services_status.py"],
    "scripts/preflight_check.py": ["tests/test_preflight_check.py"],
    "scripts/start_homelab.py": [
        "tests/test_start_homelab_stages.py",
        "tests/test_start_homelab_transport.py",
        "tests/test_start_homelab_resolve_plan.py",
    ],
    "scripts/dev_resume_session.py": ["tests/test_dev_resume_session.py"],
    "scripts/hooks/token_guard.py": ["tests/test_token_guard.py"],
    "scripts/krungsri/probe_account_info.py": ["tests/test_probe_account_info.py"],
    "scripts/krungsri/probe_krungsri_products.py": ["tests/test_probe_krungsri_products.py"],
    # Shared test harness — conftest.py holds fixtures (no tests of its own). Changed fixtures
    # affect the annealing/runbook suites (F-11 write-isolation), so map it to them explicitly.
    "tests/conftest.py": [
        "tests/test_annealing_runbook_isolation.py",
        "tests/test_escalation_and_annealing.py",
        "tests/test_click2win_driver.py",
        "tests/test_mcp_and_workflow_engine.py",
    ],
}

DOC_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".env")


def _rel(path: str) -> str:
    """Normalize an absolute or relative path to a repo-relative POSIX path."""
    abs_path = os.path.abspath(path if os.path.isabs(path) else os.path.join(os.getcwd(), path))
    try:
        return os.path.relpath(abs_path, REPO_ROOT).replace(os.sep, "/")
    except ValueError:  # pragma: no cover - different drive on Windows
        return path.replace(os.sep, "/")


def _pytest_already_running() -> List[str]:
    """Single-writer guard: list other live pytest processes (SQLite DB is not concurrent-safe)."""
    found: List[str] = []
    me = os.getpid()
    try:
        pids = [n for n in os.listdir("/proc") if n.isdigit()]
    except OSError:  # pragma: no cover - non-Linux
        return found
    for name in pids:
        pid = int(name)
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().decode(errors="replace").replace("\x00", " ").strip()
        except OSError:
            continue
        if "pytest" in cmd and "verify_changes.py" not in cmd:
            found.append(f"pid {pid}: {cmd[:120]}")
    return found


def _py_files(changed: Sequence[str]) -> List[str]:
    """Repo-relative .py files among the changed paths that actually exist."""
    return [
        f for f in (_rel(c) for c in changed)
        if f.endswith(".py") and os.path.exists(os.path.join(REPO_ROOT, f))
    ]


def _guard_blocked() -> bool:
    """True (and prints the offenders) when another pytest is live — SQLite test DB is single-writer."""
    running = _pytest_already_running()
    if not running:
        return False
    print(f"{YELLOW}{BOLD}BLOCKED{RESET} — pytest อื่นกำลังรันอยู่ (test_homelab.db ห้าม concurrent):")
    for line in running:
        print(f"  {line}")
    return True



def resolve_tests(changed: Sequence[str], explicit: Sequence[str]) -> Tuple[List[str], List[str], List[str]]:
    """Map changed files → targeted tests. Returns (tests, unmapped, report_only)."""
    if explicit:
        return list(explicit), [], []

    tests: List[str] = []
    unmapped: List[str] = []
    report_only: List[str] = []

    def add(target: str) -> None:
        if target not in tests:
            tests.append(target)

    for raw in changed:
        rel = _rel(raw)
        if rel.startswith(FULL_SUITE_TARGET) and rel.endswith(".py") and not rel.endswith("conftest.py"):
            add(rel)  # editing a test → run that test (conftest.py holds fixtures → MODULE_TEST_MAP)
        elif rel in MODULE_TEST_MAP:
            for target in MODULE_TEST_MAP[rel]:
                add(target)
        elif rel.endswith(DOC_SUFFIXES):
            report_only.append(rel)  # docs: Zero-Contradiction review only (no test)
        elif rel.endswith(".py"):
            unmapped.append(rel)  # NEVER guess — Anti-Mock
        else:
            report_only.append(rel)

    return tests, unmapped, report_only


def compile_changed(changed: Sequence[str]) -> Tuple[bool, str]:
    """Syntax gate on the .py files touched in this unit (fast, deterministic)."""
    files = _py_files(changed)
    if not files:
        return True, "compileall: no .py files to check"
    proc = subprocess.run(
        [PYTHON, "-m", "compileall", "-q", *files],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    ok = proc.returncode == 0
    detail = "compileall: OK" if ok else "compileall: FAILED\n" + proc.stdout + proc.stderr
    return ok, detail


def run_pytest(targets: Sequence[str], label: str) -> int:
    print(f"{BLUE}▶{RESET} {label}: {' '.join(targets)}")
    started = time.time()
    proc = subprocess.run([PYTHON, "-m", "pytest", *targets, "-q"], cwd=REPO_ROOT)
    elapsed = time.time() - started
    if proc.returncode == 0:
        print(f"{GREEN}{BOLD}PASS{RESET} ({label}) in {elapsed:.1f}s")
    else:
        print(f"{RED}{BOLD}FAIL{RESET} ({label}, exit {proc.returncode}) in {elapsed:.1f}s")
    return proc.returncode


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Targeted verify hook for one Loop-Engineering unit (compileall + mapped tests)."
    )
    parser.add_argument("paths", nargs="*", help="ไฟล์ที่แก้ใน unit นี้ (repo-relative หรือ absolute)")
    parser.add_argument("--tests", nargs="+", default=[], help="ระบุ test target เอง (ข้าม mapping)")
    parser.add_argument("--full", action="store_true", help="full suite — ใช้ครั้งเดียวตอนปิดงาน")
    parser.add_argument("--dry-run", action="store_true", help="แสดงแผนแล้วจบ (ไม่รัน test)")
    args = parser.parse_args(argv)

    if not args.paths and not args.tests and not args.full:
        parser.error("ต้องระบุไฟล์ที่แก้อย่างน้อย 1 ไฟล์ หรือใช้ --tests/--full")

    if args.full:
        if args.dry_run:
            print(f"[dry-run] full suite → {FULL_SUITE_TARGET}")
            return 0
        if _guard_blocked():
            return 2
        print(f"{BOLD}Full suite (final gate){RESET} — {FULL_SUITE_TARGET}")
        return run_pytest([FULL_SUITE_TARGET], "full")

    tests, unmapped, report_only = resolve_tests(args.paths, args.tests)

    print(f"{BOLD}Unit verify{RESET} — {len(args.paths)} changed file(s)")
    for rel in report_only:
        print(f"  {BLUE}·{RESET} {rel}  →  report-only (Zero-Contradiction review, ไม่มี test)")
    for rel in unmapped:
        print(f"  {RED}✗{RESET} {rel}  →  {RED}UNMAPPED{RESET} (เพิ่มใน MODULE_TEST_MAP หรือใช้ --tests)")

    if args.dry_run:
        for target in tests or ["(none)"]:
            print(f"  {BLUE}→{RESET} would run: {target}")
        print(f"  {BLUE}·{RESET} compileall: {' '.join(sorted(_py_files(args.paths))) or '(none)'}")
        return 2 if unmapped else 0

    ok, detail = compile_changed(args.paths)
    print(f"  {BLUE}·{RESET} {detail}")
    if not ok:
        return 1
    if unmapped:
        print(f"{RED}{BOLD}UNMAPPED{RESET} — ไม่รัน test (Anti-Mock: ห้ามเดา)")
        return 2
    if not tests:
        print(f"{YELLOW}{BOLD}NO TESTS{RESET} — docs/อย่างเดียว → compileall ผ่าน = จบ unit")
        return 0

    if _guard_blocked():
        return 2

    return run_pytest(tests, "targeted")


if __name__ == "__main__":
    sys.exit(main())
