---
name: token-lean
description: Token-saving work mode. Use when the user invokes /token-lean, when context nears ~60K tokens,
  or when a Kanban card / long task starts drifting into broad reads, searches, or long answers.
---

# /token-lean — work in token-saving mode

Apply until the task ends (or the user says stop):

1. **Read only what the task needs** — start from the handoff Context map; grep `docs/agent/CODEMAP.md` for symbols; read line ranges (±60), never whole large files.
2. **Need more context? Name the file + reason first** (one line). More than 3 extra files → ask the user.
3. **No long summaries** — no recap of what is already in the conversation; never paste tool output back.
4. **Answer only what the task asks** — no side refactors, no basics, no alternatives unless asked.
5. **Show only the diff / changed lines** — not whole files.
6. **End of task: ≤ 5-line summary** — files changed · verify result · next step / open question.

Also:
- Searches: specific identifiers, ≤ 3 per call (hook `token_guard` blocks short/generic patterns).
- Commands: `pytest -q --tb=line`, `| tail -40`.
- Context > 60K → skill `compact`, continue in a new session/card with `resume`.
- Agent-facing notes in English bullets; chat with the user in concise Thai.
