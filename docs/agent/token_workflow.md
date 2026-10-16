# Token workflow — Argon + Flash 3.8 + Jules (Cloud) + Cline (Local Triage & Side-Quests)

Why: baseline `docs/agent/token_baseline_2026-10-12.txt` — 15 unique sessions used ~452M input tokens; 9 sessions had
"blow-up" calls (>150K tokens/call), mostly caused by **one over-broad `search_codebase`** or **reading whole large files / screenshots**.
By shifting main-loop T0/T1 coding to **Google Jules** (100 sessions/day included in Google AI Pro, marginal cost = 0) and keeping **Cline** focused on **Local Triage** (`git diff` review + local `verify_changes.py`) and **Side-Quests**, per-token DeepSeek spend drops dramatically.

## Who does what (4-Agent model routing)
| Stage | Tool / model | Output |
|---|---|---|
| **STEP 0**: Plan, design, review, board | **Argon** (Antigravity · local) | `docs/handoff/TASK-*.md` with **Context map** + `docs/board/loop_board.md` |
| **STEP 0a**: Pre-Coding DOM/API Probe (read-only) | **Antigravity IDE — Flash 3.8** + **Human** | `## DOM / API Contract` in `TASK-*.md` (blocks Jules until `PROBE_DONE`) |
| **STEP 2a**: Main Loop Implement + Unit Test (T0/T1) | **Google Jules (Cloud VM)** — T0 = `Gemini 3.6 Flash` · T1 = `Gemini 3.1 Pro` | code + `## Jules Report` (pushed to branch via GitHub transport) |
| **STEP 2b**: Pre-Argon Local Triage | **Cline plugin** — `DeepSeek Flash` | Pull branch (`jules_bridge.py pull-branch`) → audit diff → local `verify_changes.py` → `## Cline Triage Report` |
| **🔧 Side-Quests**: Low-priority `Open questions` | **Cline plugin** — Plan = `DeepSeek Pro` · Act = `DeepSeek Flash` | Fixes on `chore/<slug>` (non-blocking lane on `loop_board.md`) |
| **STEP 3**: Live verify + HITL + RCA (T2) | **Antigravity IDE — Flash 3.8** (multimodal · human witness) | `## Verification & Stepwise Approval` + `### Live Evidence` |

## Rules of thumb
1. **One card = one TASK = one session.** ห้ามใช้แชทเดิมทำงานใหม่ — เปิด session ใหม่จากไฟล์ handoff
2. **Pre-Coding Probe before Jules (`STEP 0a`)**: งานแตะ DOM/XHR ต้องให้ Flash 3.8 + คนช่วยอ่าน Selector/JSON จริงมาใส่ `## DOM / API Contract` ก่อนส่งให้ Jules เสมอ (ห้ามให้ Jules เดา Selector บน Cloud VM)
3. **Cline as Pre-Argon Filter (`STEP 2b`)**: Cline ไม่ต้องอ่านทั้งโปรเจกต์ใหม่ ตอนกรองงานจาก Jules ให้ดูเฉพาะ `git diff main...task/<slug>` + รัน `verify_changes.py` แล้วสรุปให้ Argon
4. **Context > 60K tokens** → skill `compact` → new session → skill `resume`
5. **No screenshots/base64 into the model** — Flash 3.8 อ่านภาพผ่าน vision tool → ข้อความ แล้วเทียบ UI landmark; หรือใช้ DOM text / `browser_evaluate`
6. **Trim outputs**: `pytest -q --tb=line`, `| tail -40`, `grep -n` + ranged reads
7. **Measure weekly**: `.venv/bin/python scripts/token_report.py --since <date>`

## Enforcement & Guardrails
### Hook `token_guard` (hard block, fail-open)
- Cline: `.cline/hooks/PreToolUse` · Antigravity: `.agents/hooks.json` → `scripts/hooks/token_guard.py`
- Blocks: binary reads · images (Cline only) · text file > 400 lines without range / range > 400 · Cline search with > 3 queries or short/generic patterns

### Jules Bridge Gate (`scripts/jules_bridge.py`)
- Blocks `push-plan` if `.env`, `*session*.json`, `*.db`, or `data/screenshots/*` are in the git index (`check-safety`)
- Blocks `prompt` / `push-plan` if `Pre-Coding Probe: PROBE_NEEDED` is not yet `PROBE_DONE` or if Tier is `T2`

## Targets (vs. baseline)
| Metric | Baseline | Target |
|---|---|---|
| Always-loaded rules | ~9.0K tokens/call | ≤ 3.5K |
| Median context per call (median of sessions) | ~103K | ≤ 45K |
| Sessions with blow-up calls | 9 / 15 | 0–1 |
