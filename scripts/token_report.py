#!/usr/bin/env python3
"""Token usage report for Cline sessions (~/.cline/data/sessions).

Usage:
    .venv/bin/python scripts/token_report.py                     # all sessions
    .venv/bin/python scripts/token_report.py --since 2026-10-01  # filter by start date
    .venv/bin/python scripts/token_report.py --session <id>      # one session, with tool breakdown
    .venv/bin/python scripts/token_report.py --context           # size of always-loaded rule files

Notes:
- Cline stores usage *per LLM call*; inputTokens = full context sent on that call (history included),
  so the session total is the sum. A call above BLOWUP_THRESHOLD means one huge tool result
  (e.g. an over-broad search_codebase) is being re-sent on every following call.
- Token estimate for text files: Thai chars / 1.5 + other chars / 3.5 (rough, tokenizer-agnostic).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys

SESS_DIR = os.path.expanduser("~/.cline/data/sessions")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_FILES = ["AGENTS.md", ".agents/rules/*.md"]
BLOWUP_THRESHOLD = 150_000  # tokens in a single call


def est_tokens(text: str) -> int:
    thai = len(re.findall(r"[\u0e00-\u0e7f]", text))
    return int(thai / 1.5 + (len(text) - thai) / 3.5)


def load_session(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def usage_rows(raw: str) -> list[dict]:
    """Extract per-call usage dicts that contain inputTokens."""
    rows = []
    for m in re.finditer(r"\{[^{}]*\"inputTokens\"\s*:\s*\d+[^{}]*\}", raw):
        try:
            rows.append(json.loads(m.group(0)))
        except Exception:
            pass
    return rows


def session_meta(sdir: str) -> dict:
    for f in glob.glob(os.path.join(sdir, "*.json")):
        if f.endswith(".messages.json"):
            continue
        d = load_session(f) or {}
        return d
    return {}


def analyse(sdir: str, with_tools: bool = False) -> dict | None:
    msgs_files = glob.glob(os.path.join(sdir, "*.messages.json"))
    if not msgs_files:
        return None
    raw = open(msgs_files[0], encoding="utf-8").read()
    rows = [r for r in usage_rows(raw) if "cost" not in r]  # trailing {"...","cost"} row repeats last call
    ins = [int(r.get("inputTokens", 0)) for r in rows]
    outs = [int(r.get("outputTokens", 0)) for r in rows]
    cache = [int(r.get("cacheReadTokens", 0)) for r in rows]
    meta = session_meta(sdir)
    res = {
        "id": os.path.basename(sdir),
        "started": meta.get("started_at", ""),
        "model": meta.get("model", "?"),
        "title": (meta.get("metadata") or {}).get("title", "")[:60],
        "calls": len(ins),
        "input": sum(ins),
        "output": sum(outs),
        "cache_read": sum(cache),
        "ctx_first": ins[0] if ins else None,
        "ctx_median": int(statistics.median(ins)) if ins else None,
        "ctx_max": max(ins) if ins else None,
        "blowup_calls": sum(1 for x in ins if x > BLOWUP_THRESHOLD),
    }
    if with_tools:
        d = json.loads(raw)
        names, size, cnt, big = {}, collections.Counter(), collections.Counter(), []
        for m in d.get("messages", []):
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if c.get("type") == "tool_use":
                    names[c.get("id")] = (c.get("name"), json.dumps(c.get("input"), ensure_ascii=False)[:100])
                elif c.get("type") == "tool_result":
                    n, inp = names.get(c.get("tool_use_id"), ("?", ""))
                    s = len(json.dumps(c.get("content"), ensure_ascii=False))
                    size[n] += s
                    cnt[n] += 1
                    big.append((s, n, inp))
        res["tools"] = [(n, cnt[n], s) for n, s in size.most_common(12)]
        res["biggest"] = sorted(big, reverse=True)[:5]
    return res


def fmt(n) -> str:
    if n is None:
        return "-"
    return f"{n/1e6:.1f}M" if n >= 1e6 else (f"{n/1e3:.0f}K" if n >= 1e3 else str(n))


def report_context() -> None:
    total = 0
    print("Always-loaded context (AGENTS.md + .agents/rules):")
    for pat in CONTEXT_FILES:
        for f in sorted(glob.glob(os.path.join(REPO, pat))):
            t = est_tokens(open(f, encoding="utf-8").read())
            total += t
            print(f"  {os.path.relpath(f, REPO):45s} ~{t:6d} tokens")
    print(f"  {'TOTAL':45s} ~{total:6d} tokens / call")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="YYYY-MM-DD (filter by session start)")
    ap.add_argument("--session", help="session id (directory name) for tool breakdown")
    ap.add_argument("--context", action="store_true", help="report always-loaded rule size only")
    ap.add_argument("--guard", action="store_true", help="also summarise token_guard hook denials")
    a = ap.parse_args()

    if a.context:
        report_context()
        return 0
    if not os.path.isdir(SESS_DIR):
        print(f"no Cline sessions dir: {SESS_DIR}", file=sys.stderr)
        return 2

    if a.session:
        r = analyse(os.path.join(SESS_DIR, a.session), with_tools=True)
        if not r:
            print("session not found", file=sys.stderr)
            return 2
        print(json.dumps({k: v for k, v in r.items() if k not in ("tools", "biggest")}, ensure_ascii=False, indent=2))
        print("\nTool results (chars, stays in history until compaction):")
        for n, c, s in r["tools"]:
            print(f"  {n:45s} calls={c:5d} chars={s:10d} avg={s // max(1, c)}")
        print("\nBiggest single results:")
        for s, n, inp in r["biggest"]:
            print(f"  {s:8d}  {n}  {inp}")
        return 0

    since = dt.datetime.fromisoformat(a.since).replace(tzinfo=dt.timezone.utc) if a.since else None
    rows = []
    for sdir in glob.glob(os.path.join(SESS_DIR, "*")):
        r = analyse(sdir)
        if not r:
            continue
        if since:
            try:
                started = (dt.datetime.fromisoformat(r["started"].replace("Z", "+00:00")) if r["started"]
                           else dt.datetime.fromtimestamp(os.path.getmtime(sdir), tz=dt.timezone.utc))
                if started < since:
                    continue
            except (ValueError, OSError):
                pass
        rows.append(r)
    # Kanban re-runs/resumes of the same card write new session files that replay the previous
    # history (calls 48 -> 49 -> 50 ...). Keep only the largest snapshot per (worktree, title).
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["id"].split("-")[0], r["title"]) if "-" in r["id"] else (r["id"], "")
        r_prev = best.get(key)
        best[key] = r if (r_prev is None or r["calls"] > r_prev["calls"]) else r_prev
        best[key]["snapshots"] = (r_prev or {}).get("snapshots", 1) + (1 if r_prev else 0)
    rows = sorted(best.values(), key=lambda r: r["input"], reverse=True)

    print(f"{'session':32s} {'model':14s} {'calls':>6s} {'input':>7s} {'output':>7s} {'out/c':>6s} {'cache%':>6s} "
          f"{'ctx1st':>7s} {'ctxMed':>7s} {'ctxMax':>7s}  title")
    for r in rows:
        cache_pct = f"{100 * r['cache_read'] / r['input']:.0f}%" if r["input"] else "-"
        out_call = fmt(r["output"] // r["calls"]) if r["calls"] else "-"
        print(f"{r['id'][:32]:32s} {r['model'][:14]:14s} {r['calls']:6d} {fmt(r['input']):>7s} {fmt(r['output']):>7s} "
              f"{out_call:>6s} {cache_pct:>6s} "
              f"{fmt(r['ctx_first']):>7s} {fmt(r['ctx_median']):>7s} {fmt(r['ctx_max']):>7s}  {r['title']}"
              + (f"  [BLOWUP x{r['blowup_calls']}]" if r["blowup_calls"] else ""))
    meds = [r["ctx_median"] for r in rows if r["ctx_median"]]
    tot_in = sum(r["input"] for r in rows)
    print(f"\nSessions: {len(rows)} · total input {fmt(tot_in)} · "
          f"total output {fmt(sum(r['output'] for r in rows))} · "
          f"cache-hit {100 * sum(r['cache_read'] for r in rows) / tot_in:.0f}% · " if tot_in else "\nSessions: 0 · ",
          end="")
    print(f"median-of-median ctx {fmt(int(statistics.median(meds))) if meds else '-'} · "
          f"sessions with blow-up (>{fmt(BLOWUP_THRESHOLD)}/call) {sum(1 for r in rows if r['blowup_calls'])}")
    report_context()
    if a.guard:
        report_guard(since)
    return 0


def report_guard(since: dt.datetime | None) -> None:
    """Summarise token_guard denials (data/logs/token_guard.log in the repo and in Kanban worktrees)."""
    logs = [os.path.join(REPO, "data", "logs", "token_guard.log")]
    logs += glob.glob(os.path.expanduser("~/.cline/worktrees/*/*/data/logs/token_guard.log"))
    counts: collections.Counter = collections.Counter()
    total = 0
    for p in logs:
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) < 3:
                continue
            try:
                ts = dt.datetime.fromisoformat(parts[0]).astimezone(dt.timezone.utc)
            except ValueError:
                continue
            if since and ts < since:
                continue
            total += 1
            kind = re.sub(r"'[^']*'|\d+", "…", parts[2])[:90]
            counts[(parts[1], kind)] += 1
    print(f"\ntoken_guard denials: {total}")
    for (agent, kind), n in counts.most_common(10):
        print(f"  {n:4d}  {agent:12s} {kind}")


if __name__ == "__main__":
    sys.exit(main())
