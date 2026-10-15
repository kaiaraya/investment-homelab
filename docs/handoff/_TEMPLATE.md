# TASK-xxx: <ชื่องาน>

- Created: YYYY-MM-DD by Argon (Complex Task Owner)
- Broker: <Krungsri / Click2Win / Liberator / N/A>
- Plan Branch (Argon): `plan/<slug>`
- Git Branch (Cline): `task/<task-slug>`
- Worktree: `~/.cline/worktrees/<task-slug>`
- Status: DRAFT | READY | IN_PROGRESS | REVIEW | DONE  (state machine: `docs/agent/github_handoff.md` §7)
- Plan PR: <GitHub PR url> · Issue: #<n>   (Argon เปิดตอน PHASE 1 — human merge = gate #1)
- Result PR: <GitHub PR url>                (Cline เปิดตอน PHASE 4b — human merge = gate #2)

## Directive delta (Argon เขียน — PHASE 0)
> Argon อัปเดต directive จาก learning ของ loop ที่แล้ว ก่อนร่างแผนเอง
- ไฟล์ directive ที่ปรับ: `directive/<file>.md` — <สรุปสิ่งที่เปลี่ยน>
- เหตุผล: <learning จาก §Argon Analysis ของ loop ก่อน / RCA / Open question ที่ปิด>

## Context (Argon เขียน — PHASE 1)
<ปัญหา / เป้าหมาย / RCA ที่เกี่ยวข้อง>

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/...`

## Context map (Argon เขียน — ลด token: Cline เริ่มจากตรงนี้ ไม่ต้อง search ทั้ง repo)
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

## Cline Report (Cline เขียนเมื่อส่งงานกลับ [Review / Approval] — PHASE 4)
- Git Commit(s): `TASK-xxx: <type>(<scope>): <summary>`
- Files changed:
- Summary:
- Tests run + result:
- Open questions (สิ่งที่ไม่แน่ใจ / ปัญหานอก Scope ที่พบ -> ห้ามแก้เอง ให้จดเพื่อแตกเป็น Child Card):

---

## Cline Verification & Stepwise Approval (Cline เขียน — PHASE 4b · model: DeepSeek Pro)
- [ ] **Stage A (Code Audit)**: Diffs match scope, Invariants verified (Anti-Mock, Zero-OTP, Uptick)
- [ ] **Stage B (Verify)**: `.venv/bin/python scripts/verify_changes.py <changed files>` = PASS
- [ ] **Stage C (Visual / HITL)**: Observable state checked (screenshot → vision tool → text) via `ask_question`
- [ ] **Stage D (Verdict + Merge)**: PASS → เปิด PR ผล → ผู้ใช้ merge `main` (gate #2) → clean worktree
- Spawned Child Cards (ถ้ามีประเด็นแตกย่อย):
  - `TASK-xxx_1-...` -> ย้ายลง `[Backlog]`
- Verdict: PASS / CHANGES_REQUESTED
- Notes:

---

## Argon Analysis (Argon เขียน — PHASE 5 · เขียนแผนเอง + เห็นผล)
> Input = แผน (§Context / §Scope / §Steps / §Acceptance) + ผล (§Cline Report + §Cline Verification) เท่านั้น
> ข้อ 2–3 ที่ Argon พบเป็น "สมมติฐาน" → ต้อง live-verify (broker + LINE, headed) ก่อน merge (Anti-Mock)

### 1. Direction alignment
- Verdict: ✅ ALIGNED / ⚠️ DRIFT / ❌ OFF-DIRECTION
- เหตุผล + อ้างอิง `directive/idea.md` / roadmap:

### 2. Directive consistency (findings)
- [ ] <แผน/ผล ขัดกับ `directive/*.md` อะไรบ้าง>

### 3. Code vulnerability scan (findings)
- [ ] <ไฟล์ใน §Cline Report ที่มีช่องโหว่ / เสี่ยงเทียบ RCA pattern>

### 4. Next loop improvement
- ปัญหาที่ loop นี้เจอ:
- สิ่งที่ loop ถัดไปต้องทำ (→ ป้อนเป็น `## Context` ของการ์ดถัดไป):
- Child cards: `TASK-xxx_n-...` → `[Backlog]`

- Direction verdict: ...
- Next loop focus: ...


