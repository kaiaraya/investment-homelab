# Token workflow — Argon + Cline (2026-10-12)

Why: baseline `docs/agent/token_baseline_2026-10-12.txt` — 15 unique sessions used ~452M input tokens; 9 sessions had
"blow-up" calls (>150K tokens/call), mostly caused by **one over-broad `search_codebase`** (e.g. queries `approve`, `KILL`,
`PANIC` → 1.1M chars) or **reading whole large files / screenshots**, which then got re-sent on every following call.

## Who does what
| Stage | Tool / model | Output |
|---|---|---|
| Plan, design, RCA, review | **Argon** (Gemini web · monthly) | `docs/handoff/TASK-*.md` with **Context map** |
| Implement + targeted test | **Cline** — `deepseek-flash` (→ `deepseek-v4-pro` on escalation) | code + `## Cline Report` in the handoff |
| Verify (Stage A–D, stepwise) | **Cline** — `deepseek-v4-pro` **เสมอ** | `## Cline Verification` verdict |
| Final review / full suite | **Cline** (once per task at close) | `verify_changes.py --full` once |

## Rules of thumb
1. **One card = one TASK = one session.** Don't continue a finished card's chat for a new task — start a new card.
2. **≤ 2 Kanban cards in parallel** (each card reloads rules + explores the repo independently).
3. **Context > 60K tokens** → skill `compact` → new session → skill `resume`.
4. **Plan outside the agent loop**: big brainstorming/architecture happens once in **Argon**; Cline receives a precise Context map.
5. **No screenshots/base64 into the model**: read images via the **vision tool** (Gemini vision → text) and compare UI landmarks; or use DOM text / `browser_evaluate`.
6. **Trim outputs**: `pytest -q --tb=line`, `| tail -40`, `grep -n` + ranged reads.
7. **MCP**: only enable what the current task needs (`context7` for library docs only when needed).
8. **Measure weekly**: `.venv/bin/python scripts/token_report.py --since <date>` — compare ctxMed and BLOWUP counts against the baseline.

## Round 2 (2026-10-13) — enforcement, Kanban policy, cache
### Hook `token_guard` (hard block, fail-open)
- Cline/Kanban: `.cline/hooks/PreToolUse` · Antigravity: `.agents/hooks.json` → `scripts/hooks/token_guard.py`
- Blocks: binary reads · images (Cline only) · text file > 400 lines without range / range > 400 · Cline search with > 3 queries or short/generic patterns.
- Denials logged to `data/logs/token_guard.log` → `token_report.py --guard`. Temporarily disable: Antigravity `"enabled": false` in `.agents/hooks.json`; Cline: `chmod -x .cline/hooks/PreToolUse`.

### Kanban policy & Workflow (see docs/agent/workflow_playbook.md)
- 5 Board Columns: `[Backlog (Argon)]` -> `[Ready / Planning (Argon)]` -> `[In Progress (Cline, WIP ≤ 2)]` -> `[Review / Approval (Cline verify + User)]` -> `[Done (Argon + User)]`.
- Worktree Isolation: Cline operates in `~/.cline/worktrees/<task-slug>` and commits with `TASK-xxx: <type>(<scope>): <summary>`.
- **Implement** = `deepseek-flash`. Use `deepseek-v4-pro` after flash failed the same unit **twice** — and in a **new card** created from the handoff (not by switching models mid-card). **Verify (Stage A–D) = `deepseek-v4-pro` เสมอ** (คนละเทิร์นกับ implement).
- **Never resume a card whose context passed 150K** (each resume re-sends the whole history; card 468c9 was resumed 7× at ~900K). Context > 60K → skill `compact` → new card with the CONTEXT snapshot.
- Card Branching: If out-of-scope issues/bugs appear, record in `Open questions` and spawn a new child card into Backlog (never scope-creep).
- New card prompt template:
  ```
  Task: docs/handoff/TASK-<name>.md — start from its "Context map"; work only its scope.
  Mode: /token-lean. Verify: scripts/verify_changes.py <files>. Finish with the "Cline Report" section.
  ```

### Prompt caching (keep the prefix stable)
- DeepSeek caches identical prompt prefixes (system + rules). Baseline cache-hit ≈ 96% → keep it there.
- No dynamic content (dates, status, "today") in AGENTS.md / `.agents/rules/`. Batch rule edits into one commit — every change invalidates the cache for all cards.
- Check `cache%` column in `token_report.py`.

## Targets (vs. baseline)
| Metric | Baseline | Target |
|---|---|---|
| Always-loaded rules | ~9.0K tokens/call | ≤ 3.5K |
| Median context per call (median of sessions) | ~103K | ≤ 45K |
| Sessions with blow-up calls | 9 / 15 | 0–1 |
