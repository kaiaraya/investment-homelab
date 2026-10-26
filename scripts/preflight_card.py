#!/usr/bin/env python3
"""Pre-dispatch gate for an InvestmentHomelab kanban card.

Checks a card (markdown body or docs/handoff/TASK-*.md) against the gates that
used to live inside scripts/jules_bridge.py:

  1. Secrets — .env, *session*.json, *.db, data/screenshots/*.png must not be staged
     in the git index.
  2. Probe gate — a card that touches broker DOM/XHR must be `Probe: PROBE_DONE`
     with a `## DOM / API Contract` section; `PROBE_NEEDED` blocks dispatch.
  3. Witness gate — a 🔴T2 card must carry a filled `## Witness Session` block
     (date, human, exact action, DRY_RUN_MODE=false, headed browser).
  4. Contract gate — the card must state a verify command and a done-when.

Exit codes: 0 = PASS, 1 = FAIL (gate refused), 2 = BLOCKED (unreadable input).

Usage:
    .venv/bin/python scripts/preflight_card.py --card docs/handoff/TASK-<slug>.md
    .venv/bin/python scripts/preflight_card.py --card card.md --skip-git
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECRET_PATTERNS = (
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"session.*\.json$"),
    re.compile(r"\.db$"),
    re.compile(r"^data/screenshots/.*\.png$"),
)

DOM_MARKERS = ("DOM", "XHR", "selector", "streaming.settrade", "quicktrade", "liberator",
               "click2win", "brokerman", "webtrade")

PLACEHOLDER = re.compile(r"<[^>\n]{1,80}>")


def staged_files(root: Path) -> list[str]:
    """Files in the git index (staged), relative to the repo root."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def secret_violations(files: list[str]) -> list[str]:
    bad = []
    for path in files:
        if any(p.search(path) for p in SECRET_PATTERNS):
            bad.append(path)
    return bad


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"^[-*]?\s*{name}\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _section(text: str, title: str) -> str | None:
    m = re.search(rf"^##\s+{title}\s*$(.*?)(?=^##\s+|\Z)", text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else None


def touches_dom(text: str) -> bool:
    probe = (_field(text, "Probe") or "").upper()
    if "PROBE" in probe or probe in {"NONE", "—", "-"}:
        # An explicit Probe field is authoritative either way.
        return "PROBE_NEEDED" in probe or "PROBE_DONE" in probe
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in DOM_MARKERS)


def check_card(text: str) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block dispatch."""
    errors: list[str] = []
    warnings: list[str] = []

    probe = (_field(text, "Probe") or "").upper()
    if "PROBE_NEEDED" in probe:
        errors.append("Probe gate: card is PROBE_NEEDED — run the read-only 0a probe first")
    if "PROBE_DONE" in probe:
        contract = _section(text, "DOM / API Contract")
        if not contract or len(contract.strip()) < 40:
            errors.append("Probe gate: Probe: PROBE_DONE but '## DOM / API Contract' is empty")
        elif PLACEHOLDER.search(contract):
            errors.append("Probe gate: '## DOM / API Contract' still holds <placeholders>")
    elif touches_dom(text) and "NONE" not in probe:
        warnings.append("Card mentions broker DOM/XHR but declares no Probe field")

    tier = (_field(text, "Tier") or "")
    if "T2" in tier or "T2" in text.splitlines()[0:6]:
        witness = _section(text, "Witness Session")
        if not witness or len(witness.strip()) < 30:
            errors.append("T2 gate: missing '## Witness Session' (date, human, action, DRY_RUN_MODE=false, headed)")
        else:
            if PLACEHOLDER.search(witness):
                errors.append("T2 gate: '## Witness Session' still holds <placeholders>")
            if "DRY_RUN_MODE=false" not in witness.replace(" ", ""):
                warnings.append("T2 gate: witness block does not state DRY_RUN_MODE=false")
            if "headed" not in witness.lower():
                warnings.append("T2 gate: witness block does not state the browser is headed")

    if not re.search(r"verify_changes\.py|pytest", text):
        errors.append("Contract gate: no verify command (verify_changes.py / pytest) in the card")
    if not re.search(r"^##\s+(Acceptance|Done when)", text, re.MULTILINE | re.IGNORECASE):
        errors.append("Contract gate: no '## Acceptance' / '## Done when' section")
    if PLACEHOLDER.search(text):
        warnings.append("Card still contains <placeholders> — a worker may misread them")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kanban card pre-dispatch gate")
    ap.add_argument("--card", required=True, help="card markdown file (or docs/handoff/TASK-*.md)")
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--skip-git", action="store_true", help="skip the git-index secrets check")
    args = ap.parse_args(argv)

    card = Path(args.card)
    if not card.exists():
        print(f"BLOCKED: card not found: {card}")
        return 2
    text = card.read_text(encoding="utf-8", errors="replace")

    errors, warnings = check_card(text)

    if not args.skip_git:
        bad = secret_violations(staged_files(Path(args.repo)))
        if bad:
            errors.append("Secrets gate: staged in git index -> " + ", ".join(bad))

    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print("RESULT: FAIL — card is not ready to dispatch")
        return 1

    print(f"RESULT: PASS — {card} is ready to dispatch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
