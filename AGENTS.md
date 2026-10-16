# InvestmentHomelab — Agent Rules (shared: Antigravity + Jules + Cline)

Core rules loaded on every call. Keep this file short — details live in `docs/agent/` (read only when the task touches that area).
Full pre-slim versions (verbatim): `docs/agent/full/`.

## Project
- Python/FastAPI + Playwright broker automation (Krungsri TradeMan, Settrade Click2Win, Liberator, Settrade Open API). venv: `.venv/bin/python`
- Gateway (single entrypoint): `app.main:app` (uvicorn, no `--reload`) → `/api/v1/*`, `/api/v1/webhook/line`, `/console`, `/sse`, `/health`
  - ⚠️ Edited gateway code → **restart the process** (LINE-RCA-011). Verify: `ps -o lstart= -p <pid>` vs source mtime.
  - `python -m app.mcp.mcp_server` (playwright-homelab stdio) = **retired**, never use as entrypoint. Trading/portfolio/session go through REST `/api/v1/*` or `/sse`.
- Start: `scripts/start_homelab.py [--keep-open]` · Daily readiness: `.venv/bin/python scripts/daily_readiness.py` (0=GO, 1=NO-GO)

## Verify (mandatory per unit)
- `.venv/bin/python scripts/verify_changes.py <changed files>` (exit 0=PASS · 1=FAIL · 2=BLOCKED/UNMAPPED; `--dry-run` to preview)
- **Never run the full suite per loop** — `verify_changes.py --full` once at task close. **Never run two pytest at once** (SQLite single-writer).
- UNMAPPED → add mapping to `MODULE_TEST_MAP` in the script; do not guess tests.

## Trading safety (CRITICAL)
- Never call a tool that places/modifies/cancels an order unless the user explicitly asked in this task.
- Never change order / tick size / price-volume validation logic unless it is in the handoff scope.
- Never show or copy credentials from `.env` into files, logs, or chat.
- **Never fire SMS OTP unless `otp_relay_readiness.check().ready == true`** (Invariant 9). Background jobs must not trigger full login/2FA.
- **Anti-Mock**: never return/report fabricated accounts, balances, order ids, or empty data as success; report failures honestly.
- **Broker isolation**: never apply one broker's behaviour/selectors to another.

## Token budget (mandatory)
- **Never `read_files` on images/binaries** (`*.png *.jpg *.db *.mp4 *.har`). Use DOM text / `browser_evaluate` / a short OCR summary.
- Files > 400 lines: find the symbol first (`grep -n <symbol> docs/agent/CODEMAP.md` — **grep it, never read the whole map**), then read only that range (±60 lines). Never read a whole large file.
- `search_codebase`: specific identifiers only (function/class/constant), ≤ 3 queries per call, scope to a directory when possible. **No short/generic patterns** (`B3`, `approve`, `KILL`, `11:00`).
- Long-output commands: `pytest -q --tb=line`, pipe logs through `| tail -40`; never cat whole logs.
- STOP & ask the user when a unit exceeds **~20 tool calls**, a failure exceeds **3 attempts**, or the task exceeds **40 tool calls**.
- Context > **60K tokens** → run skill `compact`, then continue in a new session with skill `resume`.
- One task = one handoff md = one session (Jules session, Cline session, หรือ Flash room). Max **2** in `[In Progress]` พร้อมกัน.
- Hook `token_guard` (`.cline/hooks/PreToolUse`, `.agents/hooks.json`) enforces the read/search limits — if denied, follow the reason; don't retry the same call.

## Response style
- To user: Thai, concise. Agent-facing docs (Context map, Jules/Cline Report, CONTEXT snapshot): English bullets.
- Show only the diff / changed lines. No recap, no basics, no repeating tool output back.

## Ask before widening context
- Start from the handoff Context map. Before reading files outside it, state in one line which file(s) and why; > 3 extra files → ask the user first.

## Workflow (4-Agent Hybrid Loop)
- Loop every unit: DECOMPOSE → EXECUTE → VERIFY → REFLECT → REPEAT (`.agents/rules/loop_engineering.md`).
- Handoff (Argon → Flash STEP 0a Probe → Jules STEP 2a T0/T1 → Cline STEP 2b Triage → Flash STEP 3 Witness → Argon STEP 5): work only the scope in `docs/handoff/TASK-<slug>.md`; out-of-scope findings go to Open questions (routed to Cline Side-Quests). Details: `docs/agent/handoff_protocol.md`.
- Jules bridge CLI: `.venv/bin/python scripts/jules_bridge.py {check-safety|push-plan|prompt|pull-branch}` · Cloud VM bootstrap: `bash scripts/jules_setup.sh`.

## Read-when-relevant index
| Task touches | Read first |
|---|---|
| OTP relay / LINE group / push targets / multi-broker OTP | `docs/agent/otp_relay.md` |
| LINE conversation flows / state machine | `docs/agent/line_state_machine.md` |
| Daily readiness | `docs/agent/daily_readiness.md`, `.agents/skills/daily-readiness/SKILL.md` |
| Handoff / Jules & Cline Triage report format | `docs/agent/handoff_protocol.md` |
| Token workflow (4-agent model routing: Argon / Flash / Jules / Cline) | `docs/agent/token_workflow.md` |
| Workflow SOP (Argon + Flash 3.8 + Jules + Cline + loop board) | `docs/agent/workflow_playbook.md` |
| Agent loop / hybrid handoff (STEP 0–5, Pre-Coding Probe, Side-Quests) | `docs/agent/local_handoff.md` |
| Loop board (5 main columns + Side-Quest lane) | `docs/board/loop_board.md` |
| Finding code | `docs/agent/CODEMAP.md` (regenerate: `.venv/bin/python scripts/gen_codemap.py`) |
| Broker RCA / runbooks | `rca/<broker>/`, `learned_workflows/<broker>/` |
| Token usage report | `.venv/bin/python scripts/token_report.py [--session <id>]` |
