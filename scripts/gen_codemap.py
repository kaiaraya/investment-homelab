#!/usr/bin/env python3
"""Generate docs/agent/CODEMAP.md — file → class/def → line number index for app/ and scripts/.

Agents read this map first, then open only the needed line range, instead of searching the
whole repo or reading 2,000-line files end to end.

    .venv/bin/python scripts/gen_codemap.py            # write docs/agent/CODEMAP.md
    .venv/bin/python scripts/gen_codemap.py --stdout   # print instead
"""
from __future__ import annotations

import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTS = ["app", "scripts"]
OUT = os.path.join(REPO, "docs", "agent", "CODEMAP.md")
MIN_LINES_FOR_DETAIL = 1  # list symbols for every file


def file_entries(path: str) -> tuple[int, list[str]]:
    src = open(path, encoding="utf-8").read()
    n_lines = src.count("\n") + 1
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return n_lines, [f"  - ⚠️ SyntaxError line {exc.lineno}"]
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            out.append(f"  - `class {node.name}` L{node.lineno}-{end}")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(f"    - `{sub.name}` L{sub.lineno}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            out.append(f"  - `{node.name}()` L{node.lineno}-{end}")
    return n_lines, out


def build() -> str:
    lines = [
        "# CODEMAP (generated — do not edit)",
        "",
        "Regenerate: `.venv/bin/python scripts/gen_codemap.py`. Use: find the symbol here, then read only that line range.",
        "",
    ]
    for root in ROOTS:
        base = os.path.join(REPO, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in {"__pycache__", "systemd"})
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dirpath, fn)
                n, entries = file_entries(p)
                if fn == "__init__.py" and not entries:
                    continue
                lines.append(f"- **{os.path.relpath(p, REPO)}** ({n} lines)")
                lines.extend(entries)
    return "\n".join(lines) + "\n"


def main() -> int:
    text = build()
    if "--stdout" in sys.argv:
        sys.stdout.write(text)
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {os.path.relpath(OUT, REPO)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
