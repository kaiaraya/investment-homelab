#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate docs/board/loop_board.md from the live Hermes Kanban board.

`docs/board/loop_board.md` is a *mirror*, not a source of truth: the board lives in
`~/.hermes/kanban/boards/<slug>/kanban.db` and is driven by the gateway dispatcher.
This script rewrites the live sections (counts, open cards, recently closed) and keeps
the frozen Loop-1 history + Legend block that already sit in the file.

Usage:
    python scripts/board_snapshot.py                    # board investment-homelab
    python scripts/board_snapshot.py --board other --out path/to/board.md
    python scripts/board_snapshot.py --check            # exit 1 if the file is stale

Exit codes: 0 = written/current, 1 = stale (--check), 2 = board DB not found.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sqlite3
import sys

LIVE_HEADER = "# Loop Board — LIVE SNAPSHOT"
HISTORY_MARK = "## 📜 ประวัติ Loop 1"
HISTORY_START = "## 🔴 1. Backlog"
LEGEND_MARK = "## Legend"
COUNT_KEYS = ("running", "ready", "todo", "scheduled", "blocked", "triage", "review", "done", "archived")
OPEN_ORDER = ("running", "ready", "todo", "scheduled", "blocked", "triage", "review")
DEFAULT_STATUS_LINE = "- **เปิด acceptance:** Loop 1 = native in-place `change_order` ทำงานได้ทั้ง Streaming + Liberator"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def board_db(board: str) -> str:
    """Resolve the per-board SQLite file (the root ~/.hermes/kanban.db is the empty board)."""
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    return os.path.join(home, "kanban", "boards", board, "kanban.db")


def load(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        tasks = [dict(r) for r in con.execute(
            "SELECT id, title, status, assignee, created_at, completed_at FROM tasks")]
    finally:
        con.close()
    return tasks


def _fmt(ts) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"


def render(tasks, now: str, acceptance: str) -> str:
    by_status = {s: [t for t in tasks if t["status"] == s] for s in COUNT_KEYS}
    counts = " · ".join(f"{s} {len(by_status[s])}" for s in COUNT_KEYS)

    rows = []
    for status in OPEN_ORDER:
        for t in sorted(by_status[status], key=lambda x: x["created_at"]):
            rows.append(f"| `{t['id']}` | **{status}** | `{t['assignee']}` | {t['title']} |")
    open_tbl = "\n".join(rows) if rows else "| — | — | — | ไม่มีการ์ดเปิดอยู่ |"

    recent = sorted(by_status["done"], key=lambda x: x["completed_at"] or 0, reverse=True)[:10]
    done_tbl = "\n".join(
        f"| `{t['id']}` | {_fmt(t['completed_at'])} | {t['title'][:80]} |" for t in recent
    ) or "| — | — | — |"

    return f"""{LIVE_HEADER}

> ⚠️ **SNAPSHOT ONLY — regenerated {now}.** The source of truth is the Hermes Kanban board:
> `hermes kanban --board investment-homelab list`. This file is a readable mirror; if the two
> disagree, the Kanban board wins. Regenerate with `python scripts/board_snapshot.py` — never
> hand-edit the live sections.
> **Platform:** Hermes-only. Jules, Cline and the Antigravity IDE loop are **retired**
> (`docs/handoff/TASK-hermes-only-migration.md`). SOP: `docs/agent/kanban_operating_model.md`.
> Card content lives in `docs/handoff/TASK-<slug>.md`.

- **Generated:** {now}
- **Counts:** {counts}
- **Directive:** `directive/master_directive_v2.md` · **Scorecard:** `directive/loop_acceptance_and_tasks.md`
{acceptance}

## วิธีใช้
- **Kanban board** = ความจริง: status/assignee/evidence อยู่บนการ์ด และ gateway dispatch เอง
- **`default` (planner)** = เขียน/แก้การ์ด, `set-model`, verdict, squash `main`
- **`homelab-build`** = T0 (`gemini-3.8-flash`) / T1 (`gemini-3.1-pro`) เขียนโค้ด + unit test
- **`homelab-review`** (`gemini-3.1-pro`) = diff audit + `verify_changes.py` + §Review Report
- **`homelab-colab`** = งาน GPU/CPU ผ่าน `colab` CLI
- **Human** = gate #1 (อนุมัติแผน/probe) · gate #2 (squash `main`) · witness 🔴T2 ที่หน้าจอ

---

## 🟨 การ์ดที่ยังเปิดอยู่ (live)

| id | status | assignee | title |
|---|---|---|---|
{open_tbl}

## ✅ ปิดล่าสุด 10 ใบ

| id | completed | title |
|---|---|---|
{done_tbl}

---

"""


def split_history(text: str):
    """Keep the frozen Loop-1 history + Legend tail of an existing file (empty on first run).

    The trailing ``---`` separator is stripped so a regenerated file parses back to the same
    history block — otherwise each run appends one more rule and ``--check`` never settles.
    """
    history = legend = ""
    try:
        if HISTORY_START in text:
            start = text.index(HISTORY_START)
            end = text.index(LEGEND_MARK, start)
            history = re.sub(r"(?:\s*\n-{3,})+\s*$", "", text[start:end]).rstrip()
        if LEGEND_MARK in text:
            legend = text[text.index(LEGEND_MARK):]
    except ValueError:  # a partially migrated file — rebuild from scratch
        pass
    return history, legend


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="investment-homelab")
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "board", "loop_board.md"))
    ap.add_argument("--check", action="store_true", help="exit 1 when the file no longer matches the board")
    ap.add_argument("--now", default=None, help="override the timestamp (used by --check)")
    args = ap.parse_args()

    db = board_db(args.board)
    if not os.path.exists(db):
        print(f"board DB not found: {db}", file=sys.stderr)
        return 2

    tasks = load(db)
    old = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else ""
    history, legend = split_history(old)

    acceptance = DEFAULT_STATUS_LINE
    for line in old.splitlines():
        if line.startswith("- **เปิด acceptance:**"):
            acceptance = line
            break

    # A stable timestamp is what makes --check meaningful.
    now = args.now or _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = render(tasks, now, acceptance)
    if history:
        body += f"{HISTORY_MARK} (frozen 2026-10-26 — อ่านอย่างเดียว)\n\n{history}\n\n---\n\n"
    if legend:
        body += legend

    if args.check:
        cur = old
        if not cur.startswith(LIVE_HEADER):
            print("stale: file is not a generated snapshot yet")
            return 1
        strip = lambda s: "\n".join(l for l in s.splitlines() if not l.startswith(("- **Generated:**", "> ⚠️ **SNAPSHOT ONLY")))
        if strip(cur).strip() != strip(body).strip():
            print("stale: board changed — run `python scripts/board_snapshot.py`")
            return 1
        print("current")
        return 0

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"wrote {args.out} ({len(body)} chars, {len(tasks)} cards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
