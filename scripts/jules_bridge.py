#!/usr/bin/env python3
"""
Jules Bridge — Local Homelab ↔ GitHub (kaiaraya/investment-homelab) ↔ Google Jules
==================================================================================
Helper CLI for the 4-Agent Hybrid Loop (Argon + Flash 3.8 + Jules + Cline):
  1. `check-safety` — verifies no secrets/sessions/DBs (.env, *session*.json, *.db) are tracked
                      or staged in git before syncing with GitHub for Jules.
  2. `push-plan`    — runs `check-safety`, validates the handoff file's Pre-Coding Probe gate,
                      and pushes the current branch to `origin` so Jules can read it.
  3. `prompt`       — generates the copy-paste ready Jules Session Prompt (with model routing:
                      T0 -> Gemini 3.6 Flash, T1 -> Gemini 3.1 Pro, and blocks if
                      `Pre-Coding Probe: PROBE_NEEDED` is not yet `PROBE_DONE`).
  4. `pull-branch`  — fetches Jules's remote branch from `origin` into local branch `task/<slug>`
                      and prints the diff summary for Cline Local Triage (STEP 2b).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO_SLUG = "kaiaraya/investment-homelab"

FORBIDDEN_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.env(\.local|\.production)?$"),
    re.compile(r"(^|/).*session.*\.json$", re.IGNORECASE),
    re.compile(r"\.(db|sqlite|sqlite3)(-wal|-shm)?$", re.IGNORECASE),
    re.compile(r"^data/screenshots/.*\.(png|jpg|jpeg|webp)$", re.IGNORECASE),
)


def find_forbidden_files(paths: Sequence[str]) -> List[str]:
    """Return any file paths matching secret/session/database patterns."""
    offenders: List[str] = []
    for raw in paths:
        norm = raw.strip().replace("\\", "/")
        if not norm or norm.endswith(".env.example"):
            continue
        if any(pat.search(norm) for pat in FORBIDDEN_PATTERNS):
            offenders.append(norm)
    return offenders


def git_tracked_and_staged_files(repo_root: Path = REPO_ROOT) -> List[str]:
    """List all tracked and staged files in the git index."""
    proc = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def parse_handoff_metadata(markdown_text: str) -> Dict[str, str]:
    """Extract header fields and check whether DOM / API Contract is populated."""
    meta: Dict[str, str] = {
        "tier": "T1",
        "model": "Gemini 3.1 Pro",
        "probe_state": "NONE",
        "verify_cmd": "",
        "has_dom_contract": "false",
    }

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Tier:"):
            if "T0" in stripped and "T1" not in stripped:
                meta["tier"] = "T0"
                meta["model"] = "Gemini 3.6 Flash"
            elif "T2" in stripped and "T0" not in stripped and "T1" not in stripped:
                meta["tier"] = "T2"
                meta["model"] = "FLASH-HITL (DO NOT RUN ON JULES)"
            else:
                meta["tier"] = "T1"
                meta["model"] = "Gemini 3.1 Pro"
        elif stripped.startswith("- Pre-Coding Probe:"):
            val = stripped.split(":", 1)[1].strip().upper()
            if "PROBE_NEEDED" in val and "PROBE_DONE" not in val:
                meta["probe_state"] = "PROBE_NEEDED"
            elif "PROBE_DONE" in val:
                meta["probe_state"] = "PROBE_DONE"
            else:
                meta["probe_state"] = "NONE"
        elif stripped.startswith("- Verify:") or stripped.startswith("- Verify command:"):
            val = stripped.split(":", 1)[1].strip().strip("`")
            meta["verify_cmd"] = val

    contract_match = re.search(
        r"^##\s+DOM\s*/\s*API\s+Contract.*?\n(.*?)(?=^##\s+|\Z)",
        markdown_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if contract_match:
        body = contract_match.group(1).strip()
        non_placeholder = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip()
            and not ln.strip().startswith(">")
            and "<" not in ln
            and "TBD" not in ln.upper()
        ]
        if non_placeholder:
            meta["has_dom_contract"] = "true"

    return meta


def validate_jules_readiness(task_path: str, markdown_text: str) -> Tuple[bool, str, Dict[str, str]]:
    """
    Validate that a handoff task is eligible to be dispatched to Google Jules:
      - Must not be pure T2 (live order/OTP/witness belongs to Flash 3.8).
      - If `Pre-Coding Probe: PROBE_NEEDED`, blocks until Flash 3.8 + Human complete the probe
        (`PROBE_DONE`) and populate `## DOM / API Contract`.
    """
    meta = parse_handoff_metadata(markdown_text)
    if meta["tier"] == "T2":
        return (
            False,
            f"BLOCKED: {task_path} is Tier T2 (live browser/OTP/order witness). Run in Antigravity IDE (Flash 3.8), not Jules.",
            meta,
        )
    if meta["probe_state"] == "PROBE_NEEDED":
        return (
            False,
            f"BLOCKED: {task_path} has `Pre-Coding Probe: PROBE_NEEDED`. "
            "Run STEP 0a (Read-Only Probe with Flash 3.8 + Human) and set `Pre-Coding Probe: PROBE_DONE` before dispatching to Jules.",
            meta,
        )
    if meta["probe_state"] == "PROBE_DONE" and meta["has_dom_contract"] != "true":
        return (
            False,
            f"BLOCKED: {task_path} is marked `PROBE_DONE` but `## DOM / API Contract` is missing or still contains placeholders.",
            meta,
        )
    return True, "READY", meta


def build_jules_prompt(task_rel_path: str, markdown_text: str) -> str:
    """Build the standardized copy-paste prompt for Google Jules (`jules.google.com`)."""
    ok, reason, meta = validate_jules_readiness(task_rel_path, markdown_text)
    if not ok:
        raise ValueError(reason)

    slug = Path(task_rel_path).stem
    if slug.startswith("TASK-"):
        slug = slug[len("TASK-") :]
    verify_cmd = meta["verify_cmd"] or ".venv/bin/python scripts/verify_changes.py <changed_files>"

    probe_note = ""
    if meta["probe_state"] == "PROBE_DONE":
        probe_note = (
            "- Follow the `## DOM / API Contract` section in the handoff file strictly — "
            "never guess or invent DOM selectors or API field names.\n"
        )

    return (
        f"[Jules Model Selection: {meta['model']} | Tier: {meta['tier']}]\n\n"
        f"Task file: `{task_rel_path}`\n"
        f"Target branch name: `task/{slug}`\n\n"
        "Instructions:\n"
        "1. If `.venv` is not set up yet, run `bash scripts/jules_setup.sh` first.\n"
        f"2. Read `AGENTS.md` and `{task_rel_path}` — start from `## Context map` and work ONLY within `## Scope`.\n"
        f"{probe_note}"
        "3. Execute `## Steps / Task Decomposition` one atomic step at a time.\n"
        f"4. After each step, run `{verify_cmd}` (never guess unmapped tests; exit code must be 0).\n"
        "5. Enforce all Non-Negotiable Invariants: Anti-Mock (never return fake/0.00 data), "
        "Strict Broker Isolation, Zero-OTP in tests, and Never Place New Orders.\n"
        f"6. Fill in `## Jules Report` inside `{task_rel_path}` (files changed, test results, and any out-of-scope findings under `Open questions`) and commit with prefix `TASK-{slug}: <type>(<scope>): <summary>`.\n"
    )


def normalize_local_task_branch(slug_or_branch: str) -> str:
    """Normalize a slug or branch name into `task/<slug>`."""
    cleaned = slug_or_branch.strip()
    for prefix in ("refs/heads/", "origin/", "task/", "jules/", "TASK-"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    return f"task/{cleaned}"


def cmd_check_safety(repo_root: Path = REPO_ROOT) -> int:
    tracked = git_tracked_and_staged_files(repo_root)
    offenders = find_forbidden_files(tracked)
    if offenders:
        print("SECURITY BLOCK — Forbidden secret/session/DB files found in git index:", file=sys.stderr)
        for item in offenders:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("SAFETY PASS — No .env, session JSON, SQLite DB, or screenshot files tracked in git.")
    return 0


def cmd_prompt(task_file: str, repo_root: Path = REPO_ROOT) -> int:
    abs_path = (repo_root / task_file).resolve() if not os.path.isabs(task_file) else Path(task_file).resolve()
    if not abs_path.exists():
        print(f"ERROR: Task file not found: {task_file}", file=sys.stderr)
        return 2
    rel_path = os.path.relpath(abs_path, repo_root).replace(os.sep, "/")
    text = abs_path.read_text(encoding="utf-8")
    try:
        prompt_text = build_jules_prompt(rel_path, text)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(prompt_text)
    return 0


def cmd_push_plan(task_file: str, remote: str = "origin", branch: str = "main", dry_run: bool = False) -> int:
    if cmd_check_safety(REPO_ROOT) != 0:
        return 1
    abs_path = (REPO_ROOT / task_file).resolve() if not os.path.isabs(task_file) else Path(task_file).resolve()
    if not abs_path.exists():
        print(f"ERROR: Task file not found: {task_file}", file=sys.stderr)
        return 2
    rel_path = os.path.relpath(abs_path, REPO_ROOT).replace(os.sep, "/")
    ok, reason, meta = validate_jules_readiness(rel_path, abs_path.read_text(encoding="utf-8"))
    if not ok:
        print(reason, file=sys.stderr)
        return 2
    cmd = ["git", "push", remote, branch]
    if dry_run:
        print(f"[dry-run] Would run: {' '.join(cmd)} (Model: {meta['model']})")
        return 0
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return proc.returncode


def cmd_pull_branch(remote_branch: str, slug: Optional[str] = None, remote: str = "origin", dry_run: bool = False) -> int:
    local_branch = normalize_local_task_branch(slug or remote_branch)
    fetch_cmd = ["git", "fetch", remote, f"{remote_branch}:{local_branch}"]
    diff_cmd = ["git", "diff", "--stat", f"main...{local_branch}"]
    if dry_run:
        print(f"[dry-run] Would run: {' '.join(fetch_cmd)}")
        print(f"[dry-run] Followed by Cline Triage diff check: {' '.join(diff_cmd)}")
        return 0
    proc = subprocess.run(fetch_cmd, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        return proc.returncode
    subprocess.run(diff_cmd, cwd=str(REPO_ROOT))
    print(f"\nReady for STEP 2b (Cline Local Triage) on branch `{local_branch}`.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Jules Bridge CLI for InvestmentHomelab 4-Agent Loop")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("check-safety", help="Verify no .env/session/DB files are tracked in git")

    p_prompt = sub.add_parser("prompt", help="Generate Jules session prompt from a handoff md file")
    p_prompt.add_argument("task_file", help="Path to docs/handoff/TASK-<slug>.md")

    p_push = sub.add_parser("push-plan", help="Check safety + probe gate and push plan branch to origin")
    p_push.add_argument("task_file", help="Path to docs/handoff/TASK-<slug>.md")
    p_push.add_argument("--remote", default="origin")
    p_push.add_argument("--branch", default="main")
    p_push.add_argument("--dry-run", action="store_true")

    p_pull = sub.add_parser("pull-branch", help="Fetch Jules remote branch into local task/<slug> for Cline Triage")
    p_pull.add_argument("remote_branch", help="Remote branch name created by Jules")
    p_pull.add_argument("--slug", default=None, help="Task slug for local branch task/<slug>")
    p_pull.add_argument("--remote", default="origin")
    p_pull.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.subcommand == "check-safety":
        return cmd_check_safety()
    if args.subcommand == "prompt":
        return cmd_prompt(args.task_file)
    if args.subcommand == "push-plan":
        return cmd_push_plan(args.task_file, remote=args.remote, branch=args.branch, dry_run=args.dry_run)
    if args.subcommand == "pull-branch":
        return cmd_pull_branch(args.remote_branch, slug=args.slug, remote=args.remote, dry_run=args.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
