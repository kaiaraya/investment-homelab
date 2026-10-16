# TASK-loop-redesign-local-handoff: เปลี่ยน cross-app dev loop → local folder + md board (ปลด GitHub + cline-kanban)

- Created: 2026-10-16 by Argon (Complex Task Owner · Antigravity)
- Loop: 2  (board: `docs/board/loop_board.md`)
- Broker: N/A
- Tier: 🟢 T0   (docs-only + ลบ dead code/test · ไม่แตะ order/OTP/account/selectors)
- Run mode: HEADLESS-CLINE (T0)
- Git Branch: `task/loop-redesign-local-handoff`  (human squash → `main` = gate #2)
- Status: REVIEW  (↩ CHANGES_REQUESTED · state machine: `docs/agent/local_handoff.md` §7)
- Plan approved (gate #1): 2026-10-16 (human OK ใน session เดียวกัน)  ·  Merged to main (gate #2): —

## Directive delta (Argon เขียน — PHASE 0)
- ไฟล์ directive ที่ปรับ: `directive/loop_acceptance_and_tasks.md` — เปลี่ยนกลไก handoff จาก GitHub PR → local md (`Status` field) + board
- เหตุผล: Argon ย้ายมารันบน **Antigravity (local)** → ทั้ง 3 actor ใช้ folder เดียวกันได้ · `cline-kanban` ไม่เสถียร (hub-daemon / packaging bug, KB-RCA-001/002) → ปลดระวาง

## Context (Argon เขียน — PHASE 1)
Loop เดิมใช้ **GitHub + cline-kanban** เป็น medium กลาง ทำให้ 3 actor (Argon · Antigravity IDE/Flash 3.8 · Cline plugin) ต้อง push/pull
และพึ่ง hub-daemon ที่มี bug → ต้องการ medium ที่ **ไม่มี network dependency** และตรวจสอบย้อนหลังได้
- เป้าหมาย: medium = **folder เดียวกัน (filesystem)** · signal = `Status` field ใน handoff md · board = `docs/board/loop_board.md`
- ยืนยัน assumption: **Argon (Antigravity) กับ Flash 3.8 (Antigravity IDE) เป็นคนละ app/context** แม้ชื่อตระกูลเดียวกัน → มนุษย์เป็น relay
- ยืนยัน assumption: Flash 3.8 = model ของ agent **ฝั่ง IDE** → **ไม่ต้องแก้** `app/core/config.py`

## Scope — ไฟล์ที่อนุญาตให้แก้
- `docs/agent/**` · `docs/board/**` · `docs/handoff/**` · `directive/**` · `AGENTS.md` · `.agents/skills/**`
- dead artifacts ของ cline-kanban: `scripts/kanban/**` · `tests/test_install_entry_shim.py` · `rca/shared/rca_kanban_hub_daemon.md` · `scripts/systemd/cline-kanban.service`
- `scripts/verify_changes.py` (ลบ dead entries ใน `MODULE_TEST_MAP` เท่านั้น)

## Context map (Argon เขียน)
| File | Symbol / Lines | Why (read / edit) |
|------|----------------|-------------------|
| `docs/agent/local_handoff.md` | ทั้งไฟล์ (ใหม่) | SSOT ของ SOP ใหม่ (STEP 0–5 · state machine · git) |
| `docs/agent/workflow_playbook.md` | §1–§4 | บทบาท 3 actor + board + git lifecycle |
| `docs/agent/token_workflow.md` | ทั้งไฟล์ | model routing (Pro plan / Flash act / Flash 3.8 HITL) |
| `docs/agent/handoff_protocol.md` | ทั้งไฟล์ | รูปแบบไฟล์ handoff |
| `.agents/skills/task-router/SKILL.md` | ทั้งไฟล์ | routing T0/T1 → Cline · T2 → Flash |
| `.agents/skills/stepwise-approval/SKILL.md` | Stage A–D | HITL stages + human confirm |
| `scripts/verify_changes.py` | `MODULE_TEST_MAP` L158-161 | ลบ 2 entries ของ kanban |

- Verify command: `.venv/bin/python scripts/verify_changes.py <files>`

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome | Verify | Status |
|---|----------------------------|------------------|--------|--------|
| 1 | เปิด medium ใหม่: `docs/board/loop_board.md` + `docs/board/archive/.gitkeep` | board ใช้ได้แทน Kanban | `verify_changes.py` = report-only | ✅ |
| 2 | อัปเดต `docs/handoff/_TEMPLATE.md` (Status state machine + Cline Report) | template ตรง SOP ใหม่ | report-only | ✅ |
| 3 | เขียน SSOT `docs/agent/local_handoff.md` (STEP 0–5 · §7 status · §8 git) | SOP ใหม่ครบ | report-only | ✅ |
| 4 | rewrite `docs/agent/workflow_playbook.md` (3 actor + board) | ไม่มี GitHub/PR/Kanban ref | grep `github_handoff` = NONE | ✅ |
| 5 | rewrite `docs/agent/token_workflow.md` | model routing ตรงจริง | report-only | ✅ |
| 6 | patch `docs/agent/handoff_protocol.md` | format ตรง template | report-only | ✅ |
| 7 | rewrite `.agents/skills/task-router/SKILL.md` | routing T0/T1/T2 ถูก | report-only | ✅ |
| 8 | patch `.agents/skills/stepwise-approval/SKILL.md` | Stage A–D + human confirm | report-only | ✅ |
| 9 | patch `AGENTS.md` + `directive/loop_acceptance_and_tasks.md` | index ชี้ไฟล์ใหม่ | grep = NONE | ✅ |
| 10 | deprecate `docs/agent/github_handoff.md` → stub | ไม่มีใครอ่านไฟล์เก่าแล้ว | report-only | ✅ |
| 11 | ปลด git remote `origin` | repo = local-only | `git remote -v` = ว่าง | ✅ |
| 12 | ลบ dead artifacts ของ cline-kanban + `MODULE_TEST_MAP` 2 entries | ไม่เหลือ kanban artifact | `verify_changes.py scripts/verify_changes.py` = PASS | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py scripts/verify_changes.py docs/agent/local_handoff.md docs/agent/workflow_playbook.md` → exit 0
- `.venv/bin/python -m pytest tests/test_verify_changes.py -q` (รวม `test_every_mapped_target_exists_on_disk`) → PASS

## Out of scope / ห้ามแตะ
- Order placement / tick size / OTP logic — ไม่แตะเลย
- `learned_workflows/**` (มี uncommitted changes จากงาน F-11 · เจ้าของเดิมตัดสินใจเอง)
- `docs/handoff/TASK-loop1-*.md` (historical record)
- Config model id ของ app (`app/core/config.py`) — Flash 3.8 เป็น model ฝั่ง IDE

---

## Cline Report (Cline plugin เขียนเมื่อส่งงานกลับ — STEP 2 · model: DeepSeek Flash)
- Git Commit(s): `TASK-loop-redesign-local-handoff: docs(loop): local folder + md board, ปลด GitHub + cline-kanban`
- Files changed:
  - **ใหม่:** `docs/board/loop_board.md` · `docs/board/archive/.gitkeep` · `docs/agent/local_handoff.md` · `docs/handoff/TASK-loop-redesign-local-handoff.md` (ไฟล์นี้)
  - **rewrite:** `docs/agent/workflow_playbook.md` · `docs/agent/token_workflow.md` · `.agents/skills/task-router/SKILL.md`
  - **patch:** `docs/agent/handoff_protocol.md` · `.agents/skills/stepwise-approval/SKILL.md` · `AGENTS.md` · `docs/handoff/_TEMPLATE.md` · `directive/loop_acceptance_and_tasks.md`
  - **deprecate → stub:** `docs/agent/github_handoff.md`
  - **ลบ (dead code/artifacts):** `scripts/kanban/install_entry_shim.py` · `scripts/kanban/__init__.py` · `tests/test_install_entry_shim.py` · `rca/shared/rca_kanban_hub_daemon.md` · `scripts/systemd/cline-kanban.service`
  - **แก้ map:** `scripts/verify_changes.py` (ลบ 2 entries ของ kanban ใน `MODULE_TEST_MAP`)
- Summary: เปลี่ยน medium ของ cross-app dev loop จาก GitHub + cline-kanban → **local folder + md** ·
  board = `docs/board/loop_board.md` (5 คอลัมน์ · WIP ≤ 2) · handoff = `docs/handoff/TASK-<slug>.md` ไฟล์เดียวต่อยอด 3 app ·
  git = single checkout + `task/<slug>` + human squash-merge (gate #2) · repo เป็น **local-only** (ปลด `origin`)
- Tests run + result:
  - `scripts/verify_changes.py` (14 ไฟล์) → **exit 0 PASS** (report-only + `compileall: OK`)
  - `scripts/verify_changes.py scripts/verify_changes.py` → **PASS** (targeted `tests/test_verify_changes.py` · 17 passed)
  - `scripts/verify_changes.py --full` (ปิดงาน · ครั้งเดียว) → **PASS** — `679 passed, 1 warning in 211.14s` (ไม่ hang ที่ ~87%)
  - Zero-contradiction sweep: `github_handoff` / `Cline Verification` / `PHASE 0|4` → NONE (เหลือแต่ข้อความปฏิเสธที่ตั้งใจ)
  - `git remote -v` = ว่าง · `git for-each-ref refs/remotes/` = ว่าง
- Open questions:
  1. `cline-kanban.service` ที่ **ติดตั้งจริงในเครื่อง** (systemd user unit) ไม่ได้ถูกสั่งปิด — ลบแค่ไฟล์ใน repo · ถ้าต้องการปิด: `systemctl --user disable --now cline-kanban.service`
  2. `learned_workflows/click2win/click2win_order_submit.md` + `learned_workflows/shared/test_anneal_wf.md` = uncommitted จากงาน F-11 → **ไม่รวมใน commit นี้** (user: ignore)
  3. `directive/master_directive_v2.md` ยังถูกอ้างใน board header — ควรตรวจว่ามีไฟล์จริง (นอก scope)

---

## Verification & Stepwise Approval (Flash 3.8 เขียน — STEP 3 · Antigravity IDE · human witness)
- [x] **Stage A (Code Audit)**: Diffs match scope — ไม่มีไฟล์นอก scope · ไม่แตะ order/OTP/tick size · ไม่มี credential ใน diff
- [x] **Stage B (Verify)**: `.venv/bin/python scripts/verify_changes.py scripts/verify_changes.py docs/agent/local_handoff.md docs/agent/workflow_playbook.md` = **PASS** (17 passed)
- [x] **Stage C (Visual / HITL)**: ไม่มี UI/order → ไม่ใช่ T2 · หลักฐาน = output ของ verify + grep (ไม่ต้อง screenshot)
- [ ] **Stage D (Verdict + Merge)**: รอ **human** squash `task/loop-redesign-local-handoff` → `main` (gate #2)
- Verdict: **PASS** (awaiting human gate #2)
- Notes: งานนี้เป็น **bootstrap** — SOP ใหม่ไม่มีอยู่ก่อน จึงไม่มี handoff md มาก่อน (สร้างใน unit นี้) · งาน T0 ล้วน ไม่มี HITL stage

---

## Argon Analysis (Argon เขียน — PHASE 5)
> Input = แผน (§Context/§Scope/§Steps/§Acceptance) + ผล (§Cline Report) เท่านั้น
> ข้อที่เป็น "สมมติฐาน" → ต้อง live-verify ก่อน merge (Anti-Mock) — งานนี้ไม่มี live component

### 1. Direction alignment
- Verdict: ✅ ALIGNED — ลด network dependency + ปลด component ที่มี RCA (KB-RCA-001/002) · ตรงเป้าหมาย "cross-app dev loop บน local folder"

### 2. Directive consistency (findings)
- [ ] ต้องตรวจว่า `directive/master_directive_v2.md` มีอยู่จริง (ถูกอ้างใน `docs/board/loop_board.md` L10)

### 3. Code vulnerability scan (findings)
- [ ] ไม่มี — งานนี้ไม่แตะ runtime code · `scripts/verify_changes.py` แก้เฉพาะการลบ 2 map entries ที่ชี้ไฟล์ซึ่งถูกลบ

### 4. Next loop improvement
- ปัญหาที่ loop นี้เจอ: `tests/test_verify_changes.py::test_every_mapped_target_exists_on_disk` เป็นกับดักที่ดี — **ลบไฟล์ต้องลบ `MODULE_TEST_MAP` เสมอ**
- สิ่งที่ loop ถัดไปต้องทำ: ใช้ board + handoff กับงาน broker จริง (Loop 2) เพื่อพิสูจน์ว่า SOP ใช้ได้จริง
- Child cards: —

