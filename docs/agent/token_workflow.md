# Token workflow — Argon + Antigravity IDE (Flash 3.8) + Cline (2026-10-16)

Why: baseline `docs/agent/token_baseline_2026-10-12.txt` — 15 unique sessions used ~452M input tokens; 9 sessions had
"blow-up" calls (>150K tokens/call), mostly caused by **one over-broad `search_codebase`** (e.g. queries `approve`, `KILL`,
`PANIC` → 1.1M chars) or **reading whole large files / screenshots**, which then got re-sent on every following call.

## Who does what (model routing)
| Stage | Tool / model | Output |
|---|---|---|
| Plan, design, RCA, review, board | **Argon** (Antigravity · local) | `docs/handoff/TASK-*.md` with **Context map** + `docs/board/loop_board.md` |
| Implement + targeted test (T0/T1) | **Cline plugin** — Plan = `DeepSeek Pro` · Act = `DeepSeek Flash` | code + `## Cline Report` |
| Live verify + HITL + RCA (T2) | **Antigravity IDE — Flash 3.8** (multimodal · human witness) | `## Verification & Stepwise Approval` + `### Live Evidence` |
| Final review / full suite | Cline (once per task at close) | `verify_changes.py --full` once |

**Escalation:** Flash (act) fails the same unit **twice** → re-plan ใน Cline **Plan mode** (DeepSeek Pro) ก่อน retry · งาน **T2** → ย้ายไป Antigravity IDE (Flash 3.8) ทันที (ห้ามทำต่อใน Cline plugin)

## Rules of thumb
1. **One card = one TASK = one session.** ห้ามใช้แชทเดิมทำงานใหม่ — เปิด session ใหม่จากไฟล์ handoff
2. **≤ 2 การ์ดใน `[In Progress]` พร้อมกัน** (แต่ละอันโหลด rules + explore repo แยกกัน)
3. **Context > 60K tokens** → skill `compact` → new session → skill `resume`
4. **Plan outside the agent loop**: brainstorming/architecture ทำครั้งเดียวใน **Argon**; implementer ได้ Context map ที่แม่น
5. **No screenshots/base64 into the model** — Flash 3.8 อ่านภาพผ่าน vision tool → ข้อความ แล้วเทียบ UI landmark; หรือใช้ DOM text / `browser_evaluate`
6. **Trim outputs**: `pytest -q --tb=line`, `| tail -40`, `grep -n` + ranged reads
7. **MCP**: เปิดเฉพาะที่งานต้องใช้ (`context7` สำหรับ library docs เมื่อจำเป็น)
8. **Measure weekly**: `.venv/bin/python scripts/token_report.py --since <date>` — เทียบ ctxMed + BLOWUP กับ baseline

## Round 2 — enforcement, board policy, cache
### Hook `token_guard` (hard block, fail-open)
- Cline: `.cline/hooks/PreToolUse` · Antigravity: `.agents/hooks.json` → `scripts/hooks/token_guard.py`
- Blocks: binary reads · images (Cline only) · text file > 400 lines without range / range > 400 · Cline search with > 3 queries or short/generic patterns
- Denials logged to `data/logs/token_guard.log` → `token_report.py --guard`. Temporarily disable: Antigravity `"enabled": false` ใน `.agents/hooks.json`; Cline: `chmod -x .cline/hooks/PreToolUse`

### Board policy & Workflow (see `docs/agent/workflow_playbook.md`)
- 5 board columns: `[Backlog (Argon)]` → `[Ready/Planning (Argon)]` → `[In Progress (Cline T0/T1 · Flash T2), WIP ≤ 2]` → `[Review/Approval (Flash verify + human)]` → `[Done (human merge + Argon)]`
- Board = `docs/board/loop_board.md` (md ธรรมดา) — **ไม่มี Kanban/daemon/CLI**
- Branch = single checkout + `task/<slug>` · commit `TASK-xxx: <type>(<scope>): <summary>` · human squash → `main`
- **Implement (T0/T1)** = Cline plugin (Plan=DeepSeek Pro · Act=DeepSeek Flash) · **Verify (Stage A–D)** = Flash 3.8 (คนละ actor กับ implement)
- **Never continue a session whose context passed 150K** (resume re-sends whole history). Context > 60K → `compact` → new session จาก CONTEXT snapshot
- Child cards: เจอ out-of-scope issues → `Open questions` + Argon spawn child card → Backlog (ห้าม scope-creep)
- New session prompt template:
  ```
  Task: docs/handoff/TASK-<name>.md — start from its "Context map"; work only its scope.
  Run mode: <HEADLESS-CLINE | HITL-FLASH>. Verify: scripts/verify_changes.py <files>.
  Finish with the "Cline Report" (or "Verification") section.
  ```

### Prompt caching (keep the prefix stable)
- DeepSeek caches identical prompt prefixes (system + rules). Baseline cache-hit ≈ 96% → keep it there
- No dynamic content (dates, status, "today") in AGENTS.md / `.agents/rules/`. Batch rule edits into one commit
- Check `cache%` column in `token_report.py`

## Targets (vs. baseline)
| Metric | Baseline | Target |
|---|---|---|
| Always-loaded rules | ~9.0K tokens/call | ≤ 3.5K |
| Median context per call (median of sessions) | ~103K | ≤ 45K |
| Sessions with blow-up calls | 9 / 15 | 0–1 |
