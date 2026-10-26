# TASK — Migration: Development Loop → Hermes-only (retire Jules / Cline / Antigravity IDE)

- **Status:** DRAFT — M.0 ✅ · M.1 ✅ · M.2 ✅ · M.3 ✅ · M.4 ✅ · M.5 ✅ · M.6 ✅ · M.7 ✅ · M.8 ✅ · M.9 (live dry-run) · รอ gate #2 = human squash `chore/hermes-only-migration` → `main`
- **Created:** 2026-10-26 by Hermes `default` (planner lane)
- **Lane / Tier:** `default` · process+docs (ไม่แตะ trading logic, ไม่แตะ `app/**` ยกเว้น M.7)
- **Branch:** `chore/hermes-only-migration` (human squash → `main` = gate #2)
- **Scope:** เอกสาร 4 ชั้น + profile/model routing + script gate · **ไม่** แตะ broker driver / LINE handler
- **Done when:** ไม่มีเอกสารหรือสคริปต์ไหนอ้าง Jules/Cline เป็น *ทางที่ต้องใช้* แล้ว; การ์ดใหม่ 1 ใบวิ่งจบ loop ผ่าน Hermes Kanban 3 เลนได้จริง (build → review → verdict) และ Colab lane สั่งงานได้

---

## 0. ข้อเท็จจริงที่ตรวจแล้ว (verified 2026-10-26, ไม่ใช่การเดา)

| เรื่อง | ผลที่วัดได้ |
|---|---|
| provider | ใช้ตัวเดียว: `antigravity-subscription-directsdk` (`agy://local`, chat_completions) · fallback `deepseek/deepseek-flash` |
| model ที่ตอบจริง | `gemini-4-argon` · `gemini-3.1-pro` · `claude-opus-5-5` · `gemini-3.8-flash` → one-shot ทั้ง 4 ผ่าน (10–14s/ครั้ง, ไม่มี 429) |
| auxiliary ปัจจุบัน | compression/skills_hub/approval/mcp/title/voice/triage_specifier/curator = `gemini-3.8-flash` · review = `gemini-4-argon` · **kanban_decomposer = `claude-opus-5-5`** |
| gateway | **ไม่รัน** (`hermes gateway status` → not running) ⇒ kanban dispatcher ไม่ tick ⇒ การ์ด `ready` ไม่ถูก spawn |
| kanban board | `investment-homelab`: done 27 · blocked 10 · todo 5 · มีการ์ด `☁️ Colab` อยู่แล้ว 4 ใบ (B.1–B.4) |
| profiles | `default` (gemini-3.8-flash, มี skills+memory ครบ) · `housekeeper` (deepseek-flash) |
| colab CLI | `/home/araya-sawasdichai/.local/bin/colab` + `~/.config/colab-cli/token.json` (auth แล้ว) · `sessions.json` = `{}` (ไม่มี session ค้าง) · รองรับ `new/exec/install/ls/download/drivemount/log/repl` |
| working tree | dirty: `app/services/line_cli/handlers.py`, `kanban_board.csv`, `scripts/setup_rich_menu.py`, 2 tests (M) + 5 ไฟล์ untracked |

> ⚠️ ผลข้อนี้ override ความจำเดิม: `claude-*` ไม่ 429 แล้ววันนี้ — แต่ยังไม่รู้ credit จริง จึงไม่ตั้งเป็น default ของเลนไหน

---

## 1. Operating model ใหม่ — 6 เลน (kanban assignee = profile)

| เลน | profile | งาน | model | gate |
|---|---|---|---|---|
| **P** planning | `default` | แตกการ์ด · spec · verdict · board owner (แทน Argon) | `gemini-4-argon` (reasoning high) | human gate #1/#2 |
| **B** build | `homelab-build` (ใหม่) | T0/T1: code + unit test + `## Worker Report` (แทน Jules 2a + Cline small-fix) | T0 `gemini-3.8-flash` · T1 `gemini-3.1-pro` (per-card `set-model`) | ไม่มี (auto) |
| **R** review | `homelab-review` (ใหม่) | `git diff main...` audit + `verify_changes.py` + `## Review Report` (แทน Cline 2b) | `gemini-3.1-pro` | ไม่มี (auto) |
| **H** human | `default` (desktop, headed) | `0a` read-only probe · 🔴T2 live witness · OTP · squash `main` | `gemini-3.8-flash` (เร็ว/ประหยัดตอนอ่าน DOM) | **คนอยู่หน้าจอ** |
| **C** colab | `homelab-colab` (ใหม่) | ☁️ งาน GPU/CPU: model 19, Monte Carlo, data pack, EOD ingest | `gemini-3.8-flash` | ไม่มี — แต่ห้าม commit เข้า repo ตรง |
| **T** triage | `default` (specifier) | idea/ไอเดียใหม่ระหว่างทาง → การ์ด `--triage` → specifier เติม body → `todo` | `gemini-3.1-pro` (aux `triage_specifier`) | ไม่ขัดงานที่กำลังรัน |

### กฎที่ยกมาจาก 4-agent contract (ต้องคงไว้)
1. `0a` ก่อน code ทุกครั้งที่แตะ DOM/XHR — การ์ดที่ยัง `Probe: PROBE_NEEDED` **ห้าม** ถูก unblock/dispatch
2. 🔴T2 (order/OTP/account switch/SBL/live login/merge main) — **นโยบายใหม่ (ผู้ใช้เลือก 2026-10-26):** worker รันเต็มได้ **ถ้า** (a) `DRY_RUN_MODE=false` เฉพาะ run นั้น (b) browser เป็น headed (`QUICKTRADE_HEADLESS=false`) (c) **คนนั่งดูจออยู่จริง** และกด "go" ในแชทก่อน unblock · ถ้าเงื่อนไขใดไม่ครบ → การ์ดต้องอยู่ `blocked` · ทุกกรณีต้องมี `## Witness Session` (วันที่/คน/การ์ด/คำสั่ง) ก่อน dispatch และห้าม worker ปิด browser เองระหว่าง run
3. `verify_changes.py` เป็นด่านบังคับก่อน `complete` (ไม่ใช่ทั้ง suite; `--full` ครั้งเดียวตอนปิดงาน)
4. Idea ใหม่ระหว่างทำงาน → **การ์ด triage ใหม่** (ไม่แทรก scope การ์ดที่กำลังรัน) — ห้ามแก้ `code` ใน witness card
5. Anti-Mock + Broker isolation + Zero-OTP + DRY_RUN guard อยู่ที่เดิม (ใน `.hermes.md`)

---

## 2. Docs: ยุบ 4 ชั้น → 3 ชั้น (แก้รากของ drift)

เป้าหมาย: **1 สัญญา + 1 SOP + 1 template** ที่เหลือเป็น redirect 2 บรรทัด

| ชั้น | ไฟล์เดิม | การกระทำ | ไฟล์ใหม่ |
|---|---|---|---|
| 1 สัญญา | `AGENTS.md` | เขียนใหม่ → pointer 15 บรรทัด (portability) | **`.hermes.md`** (Hermes โหลดจริง, walk-up ถึง git root, ชนะ AGENTS.md) |
| 1 แม่บท | `directive/master_directive_v2.md` | แก้ Target Readers + "Cline & Argon" → Hermes lanes · เพิ่ม §Triage + §Colab lane · คงกฎ Dormant/Disabled | เหมือนเดิม (in place) |
| 2 SOP | `docs/agent/workflow_playbook.md` + `local_handoff.md` + `handoff_protocol.md` + `token_workflow.md` | **รวมเป็นไฟล์เดียว** แล้วทิ้ง redirect stub 4 ไฟล์ | **`docs/agent/kanban_operating_model.md`** (§Lanes · §STEP 0–5 · §Model routing · §Guards) |
| 3 template | `docs/handoff/_TEMPLATE.md` | `## Jules Report`→`## Worker Report` · `## Cline Triage Report`→`## Review Report` · `## Argon Analysis`→`## Planner Analysis` · เพิ่ม `Lane:` `Model:` `Probe:` `New idea → triage:` | เหมือนเดิม (in place) |
| 3 board | `docs/board/loop_board.md` | downgrade เป็น **snapshot อ่านอย่างเดียว** (ความจริง = `hermes kanban`) + banner วันที่ | เหมือนเดิม |
| 3 board | `kanban_board.csv` (+ `kanban_loop2_verify.csv` untracked) | ย้ายเข้า `docs/board/legacy/` | — |
| 3 roadmap | `docs/handoff/TASK-loop2-autotrade-roadmap.md` L50 + หัวตาราง tier | แทน legend: 🟢T0=build/3.8-flash · 🟡T1=build/3.1-pro · 🔴T2=human/default · ☁️Colab=homelab-colab · 🔧=triage | เหมือนเดิม (in place) |
| 3 acceptance | `directive/loop_acceptance_and_tasks.md` | "Cline Report" → "Worker + Review Report" | เหมือนเดิม (in place) |
| 4 บังคับ | `scripts/jules_bridge.py` + `scripts/jules_setup.sh` | ย้าย → `scripts/legacy/` · ยกเฉพาะ `check-safety` (secrets-in-index) มาเป็น `scripts/preflight_card.py` | — |
| 4 บังคับ | `scripts/hooks/token_guard.py` + `.cline/hooks/PreToolUse` + `.agents/hooks.json` | ถอด wiring (Hermes มี tool_loop_guardrails + compression) · เก็บสคริปต์ไว้ถ้า `tests/test_token_guard.py` ยังอ้าง | — |
| 2 router | `.agents/skills/task-router/SKILL.md` + `.agents/skills/stepwise-approval/` | เลิกใช้ (Antigravity skill dir) → กฎ routing ย้ายเข้า **skill `investment-homelab-ops`** (Hermes โหลดจริง) | — |

---

## 3. Work breakdown

### M.0 — Preflight + snapshot (default · 10 นาที)
- `hermes gateway install` (user service) หรือ `hermes gateway run` background → dispatcher เริ่ม tick
- `hermes kanban --board investment-homelab list > docs/board/snapshot-2026-10-26.txt`
- เก็บของค้าง: `git stash` หรือแยก commit ตาม topic ก่อนเริ่ม (tree dirty อยู่)
- **verify:** `hermes gateway status` = running · `hermes kanban --board investment-homelab dispatch --dry-run` เห็น `spawned` ว่าง (ไม่มีอะไรค้าง)
- **done when:** gateway running + snapshot มี + tree สะอาดพอจะแตก branch

### M.1 — `.hermes.md` (สัญญาใหม่) · default / argon
- สร้าง `InvestmentHomelab/.hermes.md` (โครงตาม §6.1) · ตัด `AGENTS.md` เหลือ pointer
- **verify:** เปิด `hermes` ใน cwd repo แล้วถาม "which project rules loaded" → ชี้ `.hermes.md`
- **done when:** ไฟล์ใหม่โหลดจริง และไม่มีคำว่า Jules/Cline ในเนื้อ (เหลือแค่หมายเหตุ "retired")

### M.2 — สร้าง 3 profiles · default ✅ DONE 2026-10-26
```bash
hermes profile create homelab-build  --clone --description "InvestmentHomelab T0/T1 code worker: edit repo, run verify_changes.py, write ## Worker Report. Never place/modify/cancel orders, never OTP."
hermes profile create homelab-review --clone --description "InvestmentHomelab reviewer: audit git diff vs invariants, run verify_changes.py, write ## Review Report. Read-only on broker screens."
hermes profile create homelab-colab  --clone --description "InvestmentHomelab Colab lane: run GPU/CPU jobs via colab CLI, return artifacts. Never commit to repo."
```
- แล้ว pin model ต่อ profile: `hermes -p homelab-build config set model.default gemini-3.8-flash` · `hermes -p homelab-review config set model.default gemini-3.1-pro` · `hermes -p homelab-colab config set model.default gemini-3.8-flash`
- **verify:** `hermes profile list` เห็น 4 · `hermes -p homelab-review chat -q 'reply OK'` → OK
- **done when:** ทั้ง 3 profile ตอบได้ และ assignee เห็นใน `hermes kanban --board investment-homelab assignees`

### M.3 — Model routing ใน config · default
| key | ค่า |
|---|---|
| `model.default` (default) | `gemini-4-argon` |
| `auxiliary.kanban_decomposer` | `gemini-3.1-pro` (เดิม `claude-opus-5-5`) |
| `auxiliary.triage_specifier` | `gemini-3.1-pro` |
| `auxiliary.review` | `gemini-4-argon` (คง) |
| `auxiliary.compression`/`title_generation`/`curator`/`memory_query_rewrite` | `gemini-3.8-flash` (คง) |
| `delegation.model` | `gemini-3.8-flash` (child รับ token เยอะสุด) |
- **verify:** `hermes config get auxiliary.kanban_decomposer` · การ์ด 1 ใบ `--triage` → specifier เติม body ได้
- **done when:** ไม่มี aux key ไหนชี้ claude แล้ว (เว้นแต่จะยืนยัน credit)

### M.4 — `directive/master_directive_v2.md` · default / argon
- Target Readers → "Hermes `default` (Planner) + `homelab-build` / `homelab-review` / `homelab-colab`"
- แทนกฎ "สำหรับ Cline & Argon" → "สำหรับ Hermes lanes ทั้งหมด" · เพิ่ม §Triage rule, §Colab lane (ห้าม commit เข้า repo, artifact ผ่าน Drive)
- **verify:** ไม่มีคำว่า Cline/Jules ในเนื้อหากฎ (ยกเว้นหมายเหตุประวัติ)
- **done when:** อ่านจบ 90 บรรทัดแล้ววางแผน loop ได้โดยไม่ต้องเปิด SOP

### M.5 — ยุบ SOP 4 → 1 · default
- เขียน `docs/agent/kanban_operating_model.md` (ใช้เนื้อ STEP 0–5 + guardrails + model routing จาก 4 ไฟล์เดิม)
- 4 ไฟล์เดิม → stub 3 บรรทัด `> SUPERSEDED 2026-10-26 → docs/agent/kanban_operating_model.md`
- **verify:** `grep -rl "STEP 2a" docs/ | grep -v legacy` เหลือ ≤ 1 ไฟล์
- **done when:** ไม่มีคำอธิบาย loop สองชุดที่ขัดกัน

### M.6 — Template + board + roadmap legend · default
- `_TEMPLATE.md` เขียนใหม่ (fields ตาม §2) · `loop_board.md` banner snapshot · roadmap L50 legend ใหม่ · `loop_acceptance_and_tasks.md` เปลี่ยนคำ
- legacy CSV → `docs/board/legacy/`
- **verify:** `grep -rn "Jules\|Cline" docs/ directive/ .hermes.md AGENTS.md | grep -v legacy | grep -v SUPERSEDED` → ว่าง
- **done when:** grep ข้างบนคืน 0 บรรทัด

### M.7 — Scripts: ปิด gate เก่า เปิด gate ใหม่ · default
- `git mv scripts/jules_bridge.py scripts/jules_setup.sh scripts/legacy/`
- `scripts/preflight_card.py` (ยกจาก `check-safety`): block ถ้า `.env`, `*session*.json`, `*.db`, `data/screenshots/*.png` อยู่ใน index · block ถ้า body การ์ด T0/T1 ที่แตะ DOM มี `Probe: PROBE_NEEDED`
- ถอด hook wiring ของ `token_guard`; เก็บ `tests/test_token_guard.py` ถ้าสคริปต์ยังอยู่
- **verify:** `PYTHONPATH=. .venv/bin/python scripts/preflight_card.py --card docs/handoff/TASK-<slug>.md` → exit 0/1 ตามกรณี
- **done when:** ไม่มี path ไหนเรียก jules_bridge จาก docs/scripts ที่ยัง active

### M.8 — Triage lane + Colab skill · default
- กฎ "idea → `hermes kanban --board investment-homelab create "<title>" --triage --assignee default`" เข้า `.hermes.md` + operating model
- skill ใหม่ `colab-offload` (`~/.hermes/skills/`): `colab new --gpu`, `colab install`, `colab exec`, `colab drivemount`, `colab download`, `colab log`, `sessions.json` = source of session id, ห้ามรัน 2 session พร้อมกัน, artifact กลับผ่าน Drive ไม่ผ่าน git
- **verify:** สร้างการ์ด `☁️ Colab` ทดสอบ 1 ใบ (CPU-only, งานสั้น เช่น `nvidia-smi`/`df -h`) → `colab exec` คืนผล
- **done when:** การ์ด ☁️ วิ่งจบด้วย `homelab-colab` และ artifact อยู่บน Drive

### M.9 — Dry-run 1 การ์ดจริง + commit · ทั้งหมด
- เปิด loop ย่อย: การ์ด T0 จริง 1 ใบ → build (auto) → review (auto) → verdict (default)
- **verify:** `hermes kanban --board investment-homelab show <id>` มี Worker Report + Review Report + verdict · `verify_changes.py` PASS
- **done when:** 1 การ์ดวิ่งจบโดยไม่ต้องใช้ Jules/Cline/Antigravity และ commit format `TASK-hermes-only: docs(process): …`

---

## 4. การตัดสินใจแล้ว (2026-10-26) + ที่ยังเปิดอยู่

| # | เรื่อง | คำตอบผู้ใช้ | สถานะ |
|---|---|---|---|
| 1 | Live-money 🔴T2 | **ให้ worker รันเต็มได้ ถ้า `DRY_RUN_MODE=false` + headed browser + คนดูจอ** | เขียนเป็นกฎข้อ 2 แล้ว · ต้องมี `## Witness Session` ใน card + `scripts/preflight_card.py` เช็ค |
| 2 | `auxiliary.kanban_decomposer` | **DeepSeek Pro** → `provider: deepseek`, `model: deepseek-pro` (ยืนยันแล้วว่าตอบจริง 4s) | ✅ set แล้ว |
| 3 | `auxiliary.vision` | **Gemini 3.8 Flash** → set แล้ว แต่ **ใช้ไม่ได้จริง** (ดูข้อ 4.1) | ⚠️ ติด blocker |
| 4 | M.0 gateway | **เริ่มเลย (user service)** | ✅ running, linger enabled, PID 32474 |

### 4.1 Blocker: vision ยังอ่านรูปไม่ได้ (หลักฐาน ไม่ใช่การเดา)
- `auxiliary.vision` = `antigravity-subscription-directsdk` / `gemini-3.8-flash` ตั้งแล้ว แต่ `vision_analyze` ยังตอบ "no image attached"
- สาเหตุจริง: plugin ตัวนี้ **ยุบ content เป็น string** — `plugins/antigravity-subscription-directsdk/prompt.py:44` `"Normalize multimodal or structured message content into a string"` ⇒ รูปถูกทิ้งก่อนถึงโมเดล
- ทางแก้ที่ลองแล้วไม่ได้: เรียก `agy` CLI ตรง ๆ → `RESOURCE_EXHAUSTED 429` ("AI credits balance is too low") เพราะ CLI ใช้ credit คนละกองกับ DirectSDK path
- `~/.hermes/.env` **ไม่มี** `GEMINI_API_KEY`/`GOOGLE_API_KEY` ⇒ ไม่มี endpoint ที่รับรูปเลยตอนนี้
- **ต้องตัดสิน:** (a) ใส่ `GEMINI_API_KEY` (AI Studio free tier) แล้วตั้ง `auxiliary.vision.provider=gemini` + `model=gemini-2.5-flash` ← ทางเดียวที่ WORK; (b) ยอมรับว่า probe/witness ใช้ DOM text อย่างเดียว (งานปัจจุบันทำได้ครบ) — **ข้อเสนอ: (b) ไปก่อน แล้วค่อยเพิ่ม (a) เมื่อมี key**

### 4.2 ยังเปิดอยู่ (ไม่บล็อก M.1/M.4–M.9)
1. `model.default` ของ `default` — จะเปลี่ยนเป็น `gemini-4-argon` (planner tier ตาม §5) หรือคง `gemini-3.8-flash`?
2. `claude-opus-5-5` — ตอบได้วันนี้ ไม่รู้โควต้าจริง จึงไม่ตั้งเป็นค่าไหน
3. `housekeeper` profile (deepseek-flash) — เก็บไว้หรือรวมเข้า default?


---

## 4.3 Execution log (2026-10-26)

| ขั้น | ผลจริง |
|---|---|
| M.0 | gateway ติดตั้งเป็น systemd user service, linger on, PID 32474 · snapshot `docs/board/snapshot-2026-10-26.txt` |
| M.2 | `homelab-build` / `homelab-review` / `homelab-colab` สร้างแล้ว + ตอบจริง + เป็น assignee |
| M.3 | `kanban_decomposer` → deepseek/deepseek-pro · `homelab-review` → gemini-3.1-pro · vision ตั้งแล้วแต่ **ยังใช้ไม่ได้** (§4.1) |
| M.5 | 4 SOP → stub 3 บรรทัด ชี้ `docs/agent/kanban_operating_model.md` (+ `github_handoff.md` ชี้ไฟล์ใหม่) |
| M.6 | `_TEMPLATE.md` เขียนใหม่ (Worker/Review/Planner/Colab + `## Witness Session`) · `loop_board.md` = snapshot · roadmap legend ใหม่ · CSV → `docs/board/legacy/` |
| M.7 | `scripts/legacy/{jules_bridge.py,jules_setup.sh}` · `scripts/preflight_card.py` ใช้งานได้ (PASS/FAIL ตามการ์ดจริง) |
| M.8 | skill `colab-offload` สร้างแล้ว (คำสั่งจริงจาก `colab --help`) · triage card `t_cb7d4bda` เกิดจาก caveat ของ review lane (ทดสอบ flow จริง) |
| M.9 | การ์ด `t_8a0772ee` วิ่งจบเองใน 8 นาที: `homelab-build` (319s, 8 tests) → `homelab-review` (re-run + mutation-test, approve) → `done` |

### M.9 บทเรียนที่ต้องจำ
1. **Worker over-report เป็นของจริง**: worker อ้าง "8 passing" แต่ pytest จริงได้ **6 passed, 2 errors** — เพราะ `test_homelab.db` ค้างจาก schema change; `rm -f test_homelab.db` แล้วได้ 8 passed. ต้องรันเองทุกครั้ง (review lane ก็เจอ single-writer guard ตอนรันชนกัน)
2. **Scope deviation ที่ถูกต้อง**: worker เพิ่ม 1 บรรทัดใน `scripts/verify_changes.py` (`MODULE_TEST_MAP`) นอก scope การ์ด — แต่ถ้าไม่เพิ่ม การ์ดตัวเองจะ UNMAPPED exit 2 · การ์ดลักษณะนี้ควรเขียน Verify เป็น `verify_changes.py <file> --tests <testfile>` หรืออนุญาต mapping ชัด ๆ
3. **`AGENTS.md` เขียนไม่ได้** (protected file, write ถูกปฏิเสธ) — `.hermes.md` ชนะการโหลดอยู่แล้ว (first-match-wins) จึงไม่กระทบ runtime; ถ้าจะให้ AGENTS.md สะอาด ต้องแก้ด้วยมือ
4. **review lane มีค่าจริง**: mutation test จับว่ามี 2 branch ที่ยังไม่มีเทสต์ → เปิดการ์ด `t_cb7d4bda` (triage) แทนการขยาย scope การ์ดเดิม

---

## 5. Model routing — สรุปภาษาเดียว (ใช้ตอบ "เลือก Model ตามงาน")

| งาน | ที่รัน | model | เหตุผล |
|---|---|---|---|
| อ่าน directive/แตก loop/เขียน card/spec/verdict | `default` | **gemini-4-argon** | reasoning สูงสุด, จำนวน call น้อย |
| 0a DOM probe (headed, อ่าน selector/XHR) | `default` desktop | **gemini-3.8-flash** | เร็ว+ถูก, งานอ่าน DOM ซ้ำ ๆ เยอะ |
| T0 code + unit test | `homelab-build` | **gemini-3.8-flash** | ปริมาณมากสุด |
| T1 logic ที่ต้องคิด (tick size, guardrail, parser) | `homelab-build` + `set-model` | **gemini-3.1-pro** | ผิดแล้วแพง |
| diff audit + verify + review report | `homelab-review` | **gemini-3.1-pro** | ต้องจับผิด |
| Colab GPU/CPU job | `homelab-colab` | **gemini-3.8-flash** | งาน pipeline ซ้ำ ๆ |
| triage specifier / decomposer | aux | **decomposer = `deepseek-pro`** (provider `deepseek`) · specifier = `gemini-3.1-pro` | คุณภาพ spec คุมทั้ง loop, DeepSeek ถูกว่า |
| compression/title/curator/memory-rewrite | aux | **gemini-3.8-flash** | งานเบา |
| สำรองเมื่อ provider ล่ม | fallback | **deepseek-flash** | ตั้งไว้แล้ว |

---

## 6. ภาคผนวก — ร่าง system message

### 6.1 `.hermes.md` (โครง, ~60 บรรทัด)
```markdown
# InvestmentHomelab — Hermes rules (single source)

## Platform
- Everything runs in Hermes: planner = profile `default`, code = kanban cards for
  `homelab-build`, review = `homelab-review`, Colab = `homelab-colab`.
- Jules / Cline / Antigravity IDE are RETIRED. Do not route work to them.
- Board = `hermes kanban --board investment-homelab`. `docs/board/loop_board.md`
  is a snapshot, not the truth.

## Lanes & tiers
- T0 code → card, assignee `homelab-build`, model gemini-3.8-flash.
- T1 logic → same lane, `hermes kanban set-model <id> gemini-3.1-pro`.
- T2 (order · OTP · account switch · SBL · live login · live browser · merge main)
  → `initial_status=blocked`, NEVER dispatched. Human runs it in the desktop session, headed.
- Every card ends in a review: `homelab-review` runs verify_changes.py + writes ## Review Report.

## Probe gate
- A card touching broker DOM/XHR must carry `Probe: PROBE_DONE` + `## DOM / API Contract`
  from a read-only headed probe before it can leave `blocked`.

## New ideas
- Any idea or finding outside the running card's scope → create a NEW triage card
  (`hermes kanban create "<title>" --triage --assignee default`). Never widen scope,
  never edit code inside a witness card.

## Verify
- `.venv/bin/python scripts/verify_changes.py <changed files>`; `--full` once per card close.
- Never two pytest at once (SQLite single writer).

## Trading safety (unchanged)
Anti-Mock · broker isolation · zero-OTP background · DRY_RUN guard · never print credentials
· never place/modify/cancel an order unless the user asked in this task.

## Response style
Thai to the user, concise. Agent-facing reports: English bullets, diff-only.
```

### 6.2 profile description (ใช้โดย kanban orchestrator)
- `homelab-build`: "T0/T1 implementer for InvestmentHomelab. Edit repo, add unit tests, run verify_changes.py, write ## Worker Report. Never touch live orders, OTP, or main."
- `homelab-review`: "Reviewer for InvestmentHomelab. Audit the diff against invariants, re-run verify_changes.py, write ## Review Report + verdict. Read-only on broker screens."
- `homelab-colab`: "Colab runner. Provision GPU/CPU sessions via the colab CLI, run pipeline jobs, return artifacts to Drive. Never commit to the repo."
