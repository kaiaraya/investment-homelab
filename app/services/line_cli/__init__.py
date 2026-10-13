"""
LINE slash-command CLI (Pillar 1–3, KSS + LIB).

Package layout:
* ``parser.py``  — pure, dependency-free command parser (no I/O)
* ``cards.py``   — LINE Flex builders for /status /port /cash /orders /nego
* ``handlers.py``— command handlers that call the existing Pillar 1/2/6 services

See ``docs/handoff/TASK-line-cli.md`` (task) and
``docs/handoff/TASK-line-cli-design.md`` (approved spec).
"""

from app.services.line_cli import parser

__all__ = ["parser"]
