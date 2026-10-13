#!/usr/bin/env python3
"""token_guard — PreToolUse hook that blocks token-expensive tool calls.

Shared by Antigravity (`.agents/hooks.json`) and Cline CLI / Kanban (`.cline/hooks/PreToolUse`).
Reads the hook payload (JSON) on stdin, writes the decision (JSON) on stdout.

Blocks (see docs/agent/token_workflow.md):
  * reading binary files (*.db, *.mp4, ...) — both agents
  * reading images — Cline only (DeepSeek receives them as huge base64 text; Antigravity is multimodal)
  * reading a text file > MAX_LINES lines without a line range, or a range wider than MAX_LINES
  * Cline search_codebase with > MAX_QUERIES queries, or any short/generic pattern

Fail-open: any error or unknown payload → allow, so the agent is never wedged by the guard.

    echo '<payload>' | python3 scripts/hooks/token_guard.py --agent cline|antigravity
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

MAX_LINES = 400
MAX_QUERIES = 3
MIN_QUERY_CHARS = 5
BINARY_EXT = {".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".db-journal", ".mp4", ".webm", ".mov",
              ".har", ".zip", ".gz", ".tar", ".pyc", ".so", ".bin", ".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
GENERIC = {"approve", "approved", "reject", "cancel", "confirm", "kill", "panic", "stop", "start", "error",
           "errors", "test", "tests", "order", "orders", "mode", "live", "login", "logout", "session", "debug",
           "todo", "fixme", "print", "import", "return", "class", "async", "await", "self", "none", "true",
           "false", "status", "result", "config", "data", "value", "user", "token", "price", "volume"}
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("TOKEN_GUARD_LOG") or os.path.join(REPO, "data", "logs", "token_guard.log")


# ---------------------------------------------------------------- helpers
def _as_obj(v):
    """Cline may pass parameters as JSON strings (Record<string,string>)."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return v
    return v


def _ext(path: str) -> str:
    p = path.lower()
    for e in (".db-wal", ".db-shm", ".db-journal"):
        if p.endswith(e):
            return e
    return os.path.splitext(p)[1]


def _line_count(path: str) -> int | None:
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > 50_000_000:
            return None
        with open(path, "rb") as fh:
            data = fh.read()
        return data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)
    except OSError:
        return None


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def check_read(path: str, start, end, images_blocked: bool) -> str | None:
    """Return a deny reason, or None to allow."""
    if not path:
        return None
    ext = _ext(path)
    name = os.path.basename(path)
    if ext in BINARY_EXT:
        return f"token_guard: '{name}' is binary ({ext}). Query it with a script/sqlite3 and print a short summary instead."
    if ext in IMAGE_EXT:
        if images_blocked:
            return (f"token_guard: images are sent to the model as huge base64 text ('{name}'). "
                    "Use DOM text / browser_evaluate / a short OCR summary instead.")
        return None
    s, e = _int(start), _int(end)
    if s is not None and e is not None and e - s > MAX_LINES:
        return f"token_guard: range {s}-{e} is wider than {MAX_LINES} lines. Read the specific symbol range only."
    if s is None:
        n = _line_count(path)
        if n is not None and n > MAX_LINES:
            return (f"token_guard: '{name}' has {n} lines. Find the symbol first "
                    f"(`grep -n <symbol> docs/agent/CODEMAP.md` or `grep -n <symbol> {name}`), "
                    f"then read only that range (start_line/end_line, ±60 lines).")
    return None


def check_search(queries) -> str | None:
    queries = _as_obj(queries)
    if isinstance(queries, str):
        queries = [queries]
    if not isinstance(queries, list):
        return None
    if len(queries) > MAX_QUERIES:
        return (f"token_guard: {len(queries)} queries in one search (max {MAX_QUERIES}). "
                "Search specific identifiers, a few at a time.")
    for q in queries:
        q = str(q)
        for part in q.split("|"):
            core = re.sub(r"[\\^$.*+?()\[\]{}]|\\[bBdDsSwW]", "", part).strip()
            if len(core) < MIN_QUERY_CHARS or core.lower() in GENERIC:
                return (f"token_guard: search pattern '{part.strip()}' is too short/generic (matches the whole repo). "
                        "Use a function/class/constant name, e.g. '_handle_text_message'.")
    return None


# ---------------------------------------------------------------- adapters
def decide_cline(payload: dict) -> str | None:
    name, params = None, None
    pre = payload.get("preToolUse")
    if isinstance(pre, dict):
        name, params = pre.get("toolName"), pre.get("parameters")
    tc = payload.get("tool_call")
    if (not name) and isinstance(tc, dict):
        name, params = tc.get("name"), tc.get("input")
    params = _as_obj(params) or {}
    if not isinstance(params, dict):
        return None
    if name == "read_files":
        files = _as_obj(params.get("files")) or []
        if isinstance(files, dict):
            files = [files]
        for f in files if isinstance(files, list) else []:
            if isinstance(f, str):
                f = {"path": f}
            if isinstance(f, dict):
                r = check_read(str(f.get("path", "")), f.get("start_line"), f.get("end_line"), images_blocked=True)
                if r:
                    return r
    elif name == "search_codebase":
        return check_search(params.get("queries"))
    return None


def decide_antigravity(payload: dict) -> str | None:
    tc = payload.get("toolCall") or {}
    if tc.get("name") != "view_file":
        return None
    a = tc.get("args") or {}
    return check_read(str(a.get("AbsolutePath", "")), a.get("StartLine"), a.get("EndLine"), images_blocked=False)


def _log(agent: str, reason: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{agent}\t{reason}\n")
    except OSError:
        pass


def main(argv: list[str]) -> int:
    agent = "cline"
    if "--agent" in argv:
        i = argv.index("--agent")
        if i + 1 < len(argv):
            agent = argv[i + 1]
    reason = None
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if isinstance(payload, dict):
            reason = decide_antigravity(payload) if agent == "antigravity" else decide_cline(payload)
    except Exception:  # fail-open
        reason = None
    if reason:
        _log(agent, reason)
    if agent == "antigravity":
        out = {"decision": "deny", "reason": reason} if reason else {"decision": "allow"}
    else:
        out = {"cancel": True, "errorMessage": reason, "contextModification": reason} if reason else {"cancel": False}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
