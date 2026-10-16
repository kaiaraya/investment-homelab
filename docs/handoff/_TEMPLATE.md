# TASK-xxx: <ชื่องาน>

- Created: YYYY-MM-DD by Argon (Complex Task Owner · Antigravity)
- Loop: <N>  (board: `docs/board/loop_board.md`)
- Broker: <Krungsri / Click2Win / Liberator / N/A>
- Tier: 🟢 T0 | 🟡 T1 | 🔴 T2   (T2 = order/OTP/account/SBL/live login/live browser/merge `main`)
- Implementer: JULES (`Gemini 3.6 Flash` สำหรับ T0 | `Gemini 3.1 Pro` สำหรับ T1) | CLINE-SIDEQUEST | FLASH-HITL (T2)
- Pre-Coding Probe: NONE | PROBE_NEEDED | PROBE_DONE  (งานที่แตะ DOM/XHR ต้องผ่าน STEP 0a ก่อนส่งให้ Jules)
- Git Branch: `task/<slug>`  (หรือ `chore/<slug>` สำหรับ Side-Quest · human squash → `main` = gate #2)
- Status: DRAFT | PROBE_NEEDED | READY | IN_PROGRESS | TRIAGE | REVIEW | DONE  (↩ CHANGES_REQUESTED)
- Plan approved (gate #1): <YYYY-MM-DD human OK / —>  ·  Merged to main (gate #2): <commit sha / —>
- Verify: `.venv/bin/python scripts/verify_changes.py <files>`

## Directive delta (Argon เขียน — STEP 0)
> Argon อัปเดต directive จาก learning ของ loop ที่แล้ว ก่อนร่างแผนเอง
- ไฟล์ directive ที่ปรับ: `directive/<file>.md` — <สรุปสิ่งที่เปลี่ยน>
- เหตุผล: <learning จาก §Argon Analysis ของ loop ก่อน / RCA / Open question ที่ปิด>

## Context (Argon เขียน — STEP 0)
<ปัญหา / เป้าหมาย / RCA ที่เกี่ยวข้อง>

## DOM / API Contract (Flash 3.8 + Human เขียน — STEP 0a ก่อนส่งให้ Jules)
> กรณี `Pre-Coding Probe: PROBE_DONE` ให้ระบุ Selector จริง / XHR JSON Schema ที่ยืนยันจากหน้าเว็บแล้วที่นี่ (Read-only 100% · ห้ามเดา)
- URL / Screen: `<URL หรือหน้าจอที่เปิด>`
- Verified Selectors / API Payload (Redacted):
  - `<selector หรือ endpoint + ตัวอย่างฟิลด์จริง>`
- Human Confirmation: `<ยืนยันว่าเปิดถูกบัญชี / ถูกหน้าจอแล้ว>`

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/...`

## Context map (Argon เขียน — ลด token: Jules/Cline เริ่มจากตรงนี้ ไม่ต้อง search ทั้ง repo)
| File | Symbol / Lines | Why (read / edit) |
|------|----------------|-------------------|
| `app/services/...py` | `func_name` L120-180 | edit |
| `tests/test_...py` | `test_xxx` L10-60 | pattern to copy |
- Verify command: `.venv/bin/python scripts/verify_changes.py <files>`
- หา symbol เพิ่ม: `grep -n <symbol> docs/agent/CODEMAP.md` แล้วอ่านเฉพาะช่วงบรรทัด

## Steps / Task Decomposition (Loop Engineering — บังคับ)
แตกงานเป็น atomic steps ก่อนเริ่มงาน (1 action / 1 ไฟล์ / 1 assertion ต่อ step)
แต่ละ step ต้องมี Expected Outcome + วิธี Verify แล้วทำทีละ step ไม่ batch

| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| 1 | ...                        | ...                                | `.venv/bin/python -m pytest tests/<...> -q` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py <files>`
- `.venv/bin/python -m pytest tests/<...> -q`

## Out of scope / ห้ามแตะ
- Order placement / tick size logic (เว้นแต่ระบุ)

---

## Jules Report (Jules เขียนบน Cloud VM — STEP 2a · Gemini 3.6 Flash / 3.1 Pro)
- Git Commit(s): `TASK-xxx: <type>(<scope>): <summary>`
- Files changed:
- Summary:
- Tests run + result (Cloud VM):
- Open questions (สิ่งที่ไม่แน่ใจ / ปัญหานอก Scope ที่พบ -> ห้ามแก้เอง ให้จดเพื่อส่งเข้า Cline Side-Quest หรือ Child Card):

---

## Cline Triage Report (Cline plugin เขียนในเครื่อง — STEP 2b กรองก่อนส่ง Argon / หรือรายงานงาน Side-Quest)
- Local Branch Checked: `task/<slug>` (ดึงผ่าน `.venv/bin/python scripts/jules_bridge.py pull-branch <branch>`)
- Invariant & Scope Audit: <ตรวจว่าไม่หลุด Scope, ไม่ฝ่าฝืน Anti-Mock / Broker Isolation / Zero-OTP>
- Local Verify Result: `.venv/bin/python scripts/verify_changes.py <files>` → PASS / FAIL
- Triage Verdict & Summary for Argon: <สรุปสั้นกระชับให้ Argon หรือระบุสิ่งที่แก้เพิ่มในเครื่อง>
- Side-Quest / Open Questions Triage: <แยกประเด็น Low-Priority ไปลงเลน `🔧 6. Side-Quests` บน `loop_board.md`>

---

## Verification & Stepwise Approval (Flash 3.8 เขียน — STEP 3 · Antigravity IDE · human witness)
- [ ] **Stage A (Code Audit)**: Diffs match scope, Invariants verified (Anti-Mock, Zero-OTP, Uptick)
- [ ] **Stage B (Verify)**: `.venv/bin/python scripts/verify_changes.py <changed files>` = PASS
- [ ] **Stage C (Visual / HITL)**: Observable state checked (screenshot path → vision/tool → text) via `ask_question`
- [ ] **Stage D (Verdict + Merge)**: PASS → ผู้ใช้ squash `task/<slug>` → `main` (gate #2)
- Spawned Child Cards / Side-Quests:
  - `TASK-xxx_1-...` -> ย้ายลง `[Backlog]` หรือ `[Side-Quests]`
- Verdict: PASS / CHANGES_REQUESTED
- Notes:

### Live Evidence (T2/HITL เท่านั้น · Anti-Mock — ห้าม base64 เข้าโมเดล)
| Step | Expected Outcome | หลักฐาน (screenshot path / DOM text) | Human witness |
|------|------------------|--------------------------------------|---------------|
| ...  | ...              | `data/screenshots/<file>.png`        | ✅ / ❌ |

### On T2/HITL error (ถ้าพบ error ตอน live)
1. STOP ทันที (ไม่ทำ step ถัดไป) → 3-point RCA (session/context · live DOM · data schema)
2. self-anneal ≤ 3 ครั้ง → ถ้าไม่ผ่าน: capture anomaly → บันทึก `rca/<broker>/` ใหม่ + อัปเดต `learned_workflows/<broker>/`
3. **ห้าม commit ไป `main`** — โค้ดค้างบน `task/<slug>` · Verdict = `CHANGES_REQUESTED` + ลิงก์ RCA
4. รากเป็น code bug → Cline/Jules แก้บน `task/<slug>` → Flash re-verify · รากเป็นแผน/directive → Argon re-plan

---

## Argon Analysis (Argon เขียน — STEP 5 · เขียนแผนเอง + เห็นผล)
> Input = แผน (§Context / §DOM Contract / §Scope / §Steps) + ผล (§Jules Report + §Cline Triage + §Verification)
> ข้อ 2–3 ที่ Argon พบเป็น "สมมติฐาน" → ต้อง live-verify (broker + LINE, headed) ก่อน merge (Anti-Mock)

### 1. Direction alignment
- Verdict: ✅ ALIGNED / ⚠️ DRIFT / ❌ OFF-DIRECTION
- เหตุผล + อ้างอิง `directive/master_directive_v2.md`:

### 2. Directive consistency (findings)
- [ ] <แผน/ผล ขัดกับ `directive/*.md` อะไรบ้าง>

### 3. Code vulnerability scan (findings)
- [ ] <ไฟล์ในรายงานที่มีช่องโหว่ / เสี่ยงเทียบ RCA pattern>

### 4. Next loop improvement
- ปัญหาที่ loop นี้เจอ:
- สิ่งที่ loop ถัดไปต้องทำ (→ ป้อนเป็น `## Context` ของการ์ดถัดไป):
- Child cards / Side-Quests: `TASK-xxx_n-...` → `[Backlog]` หรือ `[Side-Quests (Cline)]`
