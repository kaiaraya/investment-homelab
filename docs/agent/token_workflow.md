# Token workflow — Antigravity + Cline + Kanban (2026-10-12)

Why: baseline `docs/agent/token_baseline_2026-10-12.txt` — 15 unique sessions used ~452M input tokens; 9 sessions had
"blow-up" calls (>150K tokens/call), mostly caused by **one over-broad `search_codebase`** (e.g. queries `approve`, `KILL`,
`PANIC` → 1.1M chars) or **reading whole large files / screenshots**, which then got re-sent on every following call.

## Who does what
| Stage | Tool / model | Output |
|---|---|---|
| Plan, design, RCA, review | **Antigravity** (large model) | `docs/handoff/TASK-*.md` with **Context map** |
| Implement + targeted verify | **Cline / Kanban** — `deepseek-flash` | code + `## Cline Report` in the handoff |
| Final review / full suite | Antigravity | `verify_changes.py --full` once |

## Rules of thumb
1. **One card = one TASK = one session.** Don't continue a finished card's chat for a new task — start a new card.
2. **≤ 2 Kanban cards in parallel** (each card reloads rules + explores the repo independently).
3. **Context > 60K tokens** → skill `compact` → new session → skill `resume`.
4. **Plan outside the agent loop**: big brainstorming/architecture happens once in Antigravity; Cline receives a precise Context map.
5. **No screenshots into the model**: describe DOM text, use `browser_evaluate`, or paste a short OCR summary.
6. **Trim outputs**: `pytest -q --tb=line`, `| tail -40`, `grep -n` + ranged reads.
7. **MCP**: only enable what the current task needs (`context7` for library docs only when needed).
8. **Measure weekly**: `.venv/bin/python scripts/token_report.py --since <date>` — compare ctxMed and BLOWUP counts against the baseline.

## Targets (vs. baseline)
| Metric | Baseline | Target |
|---|---|---|
| Always-loaded rules | ~9.0K tokens/call | ≤ 3.5K |
| Median context per call (median of sessions) | ~103K | ≤ 45K |
| Sessions with blow-up calls | 9 / 15 | 0–1 |
