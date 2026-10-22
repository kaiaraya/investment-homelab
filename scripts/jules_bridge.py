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
  5. `sources`      — list GitHub repos connected to Jules (REST API).
  6. `dispatch`     — `push-plan` + create a Jules session via the REST API (replaces copy-paste).
  7. `status`       — print a session's state/outputs.
  8. `approve-plan` — approve the pending plan of a session (when --require-plan-approval).
  9. `wait`         — poll a session to completion; `--auto-pull` fetches the branch afterwards.
  10. `run`         — one-shot: dispatch → wait → auto-pull (the full agent loop).

API auth: `JULES_API_KEY` env var (from jules.google.com/settings#api), stored in `.env`.
Docs: https://jules.google/docs/api/reference/ · https://developers.google.com/jules/api
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO_SLUG = "kaiaraya/investment-homelab"

JULES_API_BASE = "https://jules.googleapis.com/v1alpha"
TERMINAL_STATES = ("COMPLETED", "FAILED")
WAITING_STATES = ("AWAITING_PLAN_APPROVAL", "AWAITING_USER_FEEDBACK")

load_dotenv(str(REPO_ROOT / ".env"))

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


# ─────────────────────────────────────────────────────────────────────────────
# Google Jules REST API (v1alpha) — programmatic dispatch (replaces copy-paste)
# Docs: https://jules.google/docs/api/reference/ · https://developers.google.com/jules/api
# ─────────────────────────────────────────────────────────────────────────────

def _jules_key() -> str:
    key = os.environ.get("JULES_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "JULES_API_KEY is not set. Generate it at https://jules.google.com/settings#api "
            "and add `JULES_API_KEY=...` to .env (gitignored)."
        )
    return key


def _jules_headers() -> Dict[str, str]:
    return {"x-goog-api-key": _jules_key(), "Content-Type": "application/json"}


def _raise_for_jules(resp: "requests.Response") -> None:
    if resp.status_code < 400:
        return
    detail = ""
    try:
        detail = resp.json().get("error", {}).get("message", resp.text[:300])
    except Exception:
        detail = resp.text[:300]
    raise RuntimeError(f"Jules API HTTP {resp.status_code}: {detail}")


def source_name_from_remote_url(url: str) -> Optional[str]:
    """Derive `sources/github/<owner>/<repo>` from a GitHub remote URL (SSH or HTTPS)."""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not match:
        return None
    return f"sources/github/{match.group(1)}/{match.group(2)}"


def resolve_source_name(remote: str = "origin", repo_root: Path = REPO_ROOT) -> str:
    proc = subprocess.run(
        ["git", "remote", "get-url", remote], cwd=str(repo_root),
        capture_output=True, text=True,
    )
    derived = source_name_from_remote_url(proc.stdout.strip())
    return derived or f"sources/github/{DEFAULT_REPO_SLUG}"


def match_task_branch(branch_names: Sequence[str], slug: str, session_id: Optional[str] = None) -> Optional[str]:
    """Pick the Jules branch for `slug` from candidate branch names (`task/<slug>…`).
    Prefers a branch whose suffix matches the session id, then the exact `task/<slug>`,
    then the first candidate (callers pass newest-first)."""
    prefix = f"task/{slug}"
    matches = [b for b in branch_names if b.startswith(prefix)]
    if not matches:
        return None
    if session_id:
        for b in matches:
            if str(session_id) in b:
                return b
    if prefix in matches:
        return prefix
    return matches[0]


def find_remote_task_branch(slug: str, session_id: Optional[str] = None, remote: str = "origin") -> Optional[str]:
    """Fetch latest refs and locate the remote branch Jules pushed for `slug`."""
    subprocess.run(["git", "fetch", "--prune", remote], cwd=str(REPO_ROOT), capture_output=True, text=True)
    proc = subprocess.run(
        ["git", "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", f"refs/remotes/{remote}"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    names: List[str] = []
    for line in proc.stdout.splitlines():
        name = line.strip()
        if name.startswith(f"{remote}/"):
            names.append(name[len(remote) + 1:])
    return match_task_branch(names, slug, session_id)


def jules_list_sources() -> List[dict]:
    resp = requests.get(f"{JULES_API_BASE}/sources", headers=_jules_headers(), timeout=30)
    _raise_for_jules(resp)
    return resp.json().get("sources", [])


def jules_create_session(
    prompt: str,
    title: str,
    source: str,
    starting_branch: str = "main",
    automation_mode: Optional[str] = None,
    require_plan_approval: bool = False,
) -> dict:
    body: Dict[str, object] = {
        "prompt": prompt,
        "title": title,
        "sourceContext": {
            "source": source,
            "githubRepoContext": {"startingBranch": starting_branch},
        },
    }
    if automation_mode:
        body["automationMode"] = automation_mode
    if require_plan_approval:
        body["requirePlanApproval"] = True
    resp = requests.post(f"{JULES_API_BASE}/sessions", headers=_jules_headers(), json=body, timeout=30)
    _raise_for_jules(resp)
    return resp.json()


def jules_get_session(session_id: str) -> dict:
    resp = requests.get(f"{JULES_API_BASE}/sessions/{session_id}", headers=_jules_headers(), timeout=30)
    _raise_for_jules(resp)
    return resp.json()


def jules_approve_plan(session_id: str) -> dict:
    resp = requests.post(f"{JULES_API_BASE}/sessions/{session_id}:approvePlan", headers=_jules_headers(), timeout=30)
    _raise_for_jules(resp)
    return resp.json()


def wait_for_terminal(session_id: str, poll_interval: int = 30, timeout: int = 1800) -> dict:
    deadline = time.time() + timeout
    while True:
        session = jules_get_session(session_id)
        state = session.get("state", "STATE_UNSPECIFIED")
        print(f"[{time.strftime('%H:%M:%S')}] session {session_id} state={state}")
        if state in TERMINAL_STATES or state in WAITING_STATES:
            return session
        if time.time() > deadline:
            raise TimeoutError(f"Session {session_id} did not reach a terminal state within {timeout}s (last state={state})")
        time.sleep(poll_interval)


def _print_session(session: dict) -> None:
    print(f"id:    {session.get('id')}")
    print(f"title: {session.get('title')}")
    print(f"state: {session.get('state')}")
    print(f"url:   {session.get('url')}")
    for out in session.get("outputs", []) or []:
        pr = out.get("pullRequest") if isinstance(out, dict) else None
        if pr:
            print(f"PR: {pr.get('url')}  ({pr.get('title')})")
        else:
            print(f"output: {out}")


def _slug_from_task_path(task_path: str) -> str:
    slug = Path(task_path).stem
    if slug.startswith("TASK-"):
        slug = slug[len("TASK-"):]
    return slug


def _pipeline_dispatch(
    task_file: str,
    automation_mode: Optional[str] = None,
    require_plan_approval: bool = False,
    source: Optional[str] = None,
    starting_branch: str = "main",
    dry_run: bool = False,
) -> Tuple[Optional[dict], str]:
    """Push the plan branch, build the prompt, and create a Jules session.
    Returns (session_dict, slug); session_dict is None when dry_run. Raises on failure."""
    rc = cmd_push_plan(task_file, dry_run=dry_run)
    if rc != 0:
        raise RuntimeError("push-plan failed (see output above)")
    abs_path = (REPO_ROOT / task_file).resolve() if not os.path.isabs(task_file) else Path(task_file).resolve()
    rel_path = os.path.relpath(abs_path, REPO_ROOT).replace(os.sep, "/")
    prompt_text = build_jules_prompt(rel_path, abs_path.read_text(encoding="utf-8"))
    slug = _slug_from_task_path(rel_path)
    resolved_source = source or resolve_source_name()
    if dry_run:
        print(f"[dry-run] source={resolved_source} startingBranch={starting_branch} "
              f"automationMode={automation_mode or 'NONE'} requirePlanApproval={require_plan_approval}")
        print("[dry-run] prompt:")
        print(prompt_text)
        return None, slug
    session = jules_create_session(prompt_text, slug, resolved_source, starting_branch, automation_mode, require_plan_approval)
    return session, slug


def cmd_sources() -> int:
    try:
        sources = jules_list_sources()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not sources:
        print("No connected sources. Install the Jules GitHub app at jules.google.com first.")
        return 0
    for s in sources:
        print(f"  {s.get('name')}   (id={s.get('id')})")
    return 0


def cmd_dispatch(
    task_file: str,
    automation_mode: Optional[str] = None,
    require_plan_approval: bool = False,
    source: Optional[str] = None,
    starting_branch: str = "main",
    dry_run: bool = False,
) -> int:
    try:
        session, slug = _pipeline_dispatch(task_file, automation_mode, require_plan_approval, source, starting_branch, dry_run)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if dry_run or session is None:
        return 0
    print(f"SESSION CREATED: id={session.get('id')}  slug={slug}")
    print(f"  url:   {session.get('url')}")
    print(f"  state: {session.get('state')}")
    print(f"  poll:  .venv/bin/python scripts/jules_bridge.py wait {session.get('id')} --slug {slug}")
    return 0


def cmd_status(session_id: str) -> int:
    try:
        _print_session(jules_get_session(session_id))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_approve_plan(session_id: str) -> int:
    try:
        jules_approve_plan(session_id)
        print(f"Plan approved for session {session_id}.")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def _resolve_waiting_state(session_id: str, state: str, slug: Optional[str], auto_approve: bool) -> Optional[int]:
    """Handle AWAITING_* states during a wait. Returns an exit code to stop, or None to keep polling."""
    if state == "AWAITING_PLAN_APPROVAL":
        if auto_approve:
            print("Plan ready — auto-approving…")
            jules_approve_plan(session_id)
            return None
        print("AWAITING_PLAN_APPROVAL — review the plan, then run:")
        print(f"  .venv/bin/python scripts/jules_bridge.py approve-plan {session_id}")
        return 2
    if state == "AWAITING_USER_FEEDBACK":
        print("AWAITING_USER_FEEDBACK — Jules needs input; respond in the web UI or via send-message.")
        return 2
    return None


def _auto_pull(slug: str, session_id: Optional[str]) -> int:
    branch = find_remote_task_branch(slug, session_id=session_id)
    if not branch:
        print(f"ERROR: no remote branch matching task/{slug} found.", file=sys.stderr)
        return 1
    print(f"Detected Jules branch: {branch}")
    return cmd_pull_branch(branch, slug=slug)


def cmd_wait(session_id: str, slug: Optional[str] = None, poll_interval: int = 30, timeout: int = 1800,
             auto_approve: bool = False, auto_pull: bool = False) -> int:
    try:
        while True:
            session = wait_for_terminal(session_id, poll_interval=poll_interval, timeout=timeout)
            state = session.get("state", "")
            stop = _resolve_waiting_state(session_id, state, slug, auto_approve)
            if stop is not None:
                return stop
            if state in TERMINAL_STATES:
                break
        _print_session(session)
        if state == "FAILED":
            print("Session FAILED.", file=sys.stderr)
            return 1
        if auto_pull:
            if not slug:
                print("ERROR: --auto-pull requires --slug.", file=sys.stderr)
                return 2
            return _auto_pull(slug, session_id)
        return 0
    except TimeoutError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_run(
    task_file: str,
    automation_mode: Optional[str] = None,
    require_plan_approval: bool = False,
    source: Optional[str] = None,
    starting_branch: str = "main",
    poll_interval: int = 30,
    timeout: int = 1800,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> int:
    """One-shot: push plan → dispatch to Jules → wait for completion → pull branch locally."""
    try:
        session, slug = _pipeline_dispatch(task_file, automation_mode, require_plan_approval, source, starting_branch, dry_run)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if dry_run or session is None:
        return 0
    session_id = str(session.get("id") or "")
    print(f"Dispatched session {session_id} (slug={slug}). Waiting for completion…")
    try:
        while True:
            session = wait_for_terminal(session_id, poll_interval=poll_interval, timeout=timeout)
            state = session.get("state", "")
            stop = _resolve_waiting_state(session_id, state, slug, auto_approve)
            if stop is not None:
                return stop
            if state in TERMINAL_STATES:
                break
        _print_session(session)
        if state == "FAILED":
            print("Session FAILED.", file=sys.stderr)
            return 1
        return _auto_pull(slug, session_id)
    except TimeoutError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


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

    sub.add_parser("sources", help="List GitHub repos connected to Jules")

    p_dispatch = sub.add_parser("dispatch", help="push-plan + create a Jules session via the REST API (no copy-paste)")
    p_dispatch.add_argument("task_file", help="Path to docs/handoff/TASK-<slug>.md")
    p_dispatch.add_argument("--pr", action="store_true", help="Set automationMode=AUTO_CREATE_PR (Jules opens a PR)")
    p_dispatch.add_argument("--require-plan-approval", action="store_true", help="Pause for plan approval before coding")
    p_dispatch.add_argument("--source", default=None, help="Override source name (default derived from git remote)")
    p_dispatch.add_argument("--branch", default="main", help="Starting branch for Jules (default main)")
    p_dispatch.add_argument("--dry-run", action="store_true")

    p_status = sub.add_parser("status", help="Print a session's state and outputs")
    p_status.add_argument("session_id")

    p_approve = sub.add_parser("approve-plan", help="Approve the pending plan of a session")
    p_approve.add_argument("session_id")

    p_wait = sub.add_parser("wait", help="Poll a session until it completes (or needs input)")
    p_wait.add_argument("session_id")
    p_wait.add_argument("--slug", default=None, help="Task slug (required with --auto-pull)")
    p_wait.add_argument("--poll-interval", type=int, default=30, help="Seconds between polls (default 30)")
    p_wait.add_argument("--timeout", type=int, default=1800, help="Max wait seconds (default 1800)")
    p_wait.add_argument("--auto-approve", action="store_true", help="Auto-approve a generated plan")
    p_wait.add_argument("--auto-pull", action="store_true", help="Pull the branch into task/<slug> after completion")

    p_run = sub.add_parser("run", help="One-shot: dispatch → wait → auto-pull (the agent's full loop)")
    p_run.add_argument("task_file", help="Path to docs/handoff/TASK-<slug>.md")
    p_run.add_argument("--pr", action="store_true", help="Set automationMode=AUTO_CREATE_PR")
    p_run.add_argument("--require-plan-approval", action="store_true", help="Pause for plan approval before coding")
    p_run.add_argument("--auto-approve", action="store_true", help="Auto-approve the plan (with --require-plan-approval)")
    p_run.add_argument("--source", default=None, help="Override source name")
    p_run.add_argument("--branch", default="main", help="Starting branch (default main)")
    p_run.add_argument("--poll-interval", type=int, default=30, help="Seconds between polls (default 30)")
    p_run.add_argument("--timeout", type=int, default=1800, help="Max wait seconds (default 1800)")
    p_run.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.subcommand == "check-safety":
        return cmd_check_safety()
    if args.subcommand == "prompt":
        return cmd_prompt(args.task_file)
    if args.subcommand == "push-plan":
        return cmd_push_plan(args.task_file, remote=args.remote, branch=args.branch, dry_run=args.dry_run)
    if args.subcommand == "pull-branch":
        return cmd_pull_branch(args.remote_branch, slug=args.slug, remote=args.remote, dry_run=args.dry_run)
    if args.subcommand == "sources":
        return cmd_sources()
    if args.subcommand == "dispatch":
        automation = "AUTO_CREATE_PR" if args.pr else None
        return cmd_dispatch(args.task_file, automation_mode=automation,
                            require_plan_approval=args.require_plan_approval,
                            source=args.source, starting_branch=args.branch, dry_run=args.dry_run)
    if args.subcommand == "status":
        return cmd_status(args.session_id)
    if args.subcommand == "approve-plan":
        return cmd_approve_plan(args.session_id)
    if args.subcommand == "wait":
        return cmd_wait(args.session_id, slug=args.slug, poll_interval=args.poll_interval,
                        timeout=args.timeout, auto_approve=args.auto_approve, auto_pull=args.auto_pull)
    if args.subcommand == "run":
        automation = "AUTO_CREATE_PR" if args.pr else None
        return cmd_run(args.task_file, automation_mode=automation,
                       require_plan_approval=args.require_plan_approval, source=args.source,
                       starting_branch=args.branch, poll_interval=args.poll_interval,
                       timeout=args.timeout, auto_approve=args.auto_approve, dry_run=args.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
