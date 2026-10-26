# TASK-xxx: <ชื่องาน>

- Created: YYYY-MM-DD by Hermes `default` (planner lane)
- Loop: <N> · Kanban card: `t_xxxxxxxx` (`hermes kanban --board investment-homelab show t_xxxxxxxx`)
- Lane: `default` (plan) | `homelab-build` (T0/T1 code) | `homelab-review` (verify) | `homelab-colab` (GPU/CPU)
- Tier: 🟢 T0 | 🟡 T1 | 🔴 T2   (T2 = order/OTP/account switch/SBL/live login/live browser/merge `main`)
- Model: `gemini-4-argon` (plan) · `gemini-3.8-flash` (T0) · `gemini-3.1-pro` (T1 / review) · override: `hermes kanban … set-model <id> <model>`
- Broker: <kss / lib / N/A>
- Probe: NONE | PROBE_NEEDED | PROBE_DONE   (งานที่แตะ DOM/XHR ต้อง PROBE_DONE + §DOM / API Contract ก่อนปล่อยจาก `blocked`)
- Workspace: `worktree:<path>` / `scratch` · Branch: `wt/<card-id>` หรือ `task/<slug>` · human squash → `main` = gate #2
- Status: DRAFT | PROBE_NEEDED | READY | IN_PROGRESS | TRIAGE | REVIEW | DONE  (↩ CHANGES_REQUESTED)
- Plan approved (gate #1): <YYYY-MM-DD human OK / —> · Merged to main (gate #2): <commit sha / —>
- Verify: `.venv/bin/python scripts/verify_changes.py <files>`

## Directive delta (planner เขียน — STEP 0)
- ไฟล์ directive ที่ปรับ: `directive/<file>.md` — <สรุปสิ่งที่เปลี่ยน>
- เหตุผล: <learning จาก §Planner Analysis ของ loop ก่อน / RCA / open question ที่ปิด>

## Context (planner เขียน — STEP 0)
<ปัญหา / เป้าหมาย / RCA ที่เกี่ยวข้อง>

## DOM / API Contract (0a probe — read-only, headed, human ยืนยันหน้าจอ)
> กรณี `Probe: PROBE_DONE` ให้ระบุ Selector จริง / XHR JSON Schema ที่ยืนยันจากหน้าเว็บแล้ว (ห้ามเดา)
- URL / Screen: `<URL หรือหน้าจอที่เปิด>`
- Verified Selectors / API Payload (Redacted):
  - `<selector หรือ endpoint + ตัวอย่างฟิลด์จริง>`
- Human Confirmation: `<ยืนยันว่าเปิดถูกบัญชี / ถูกหน้าจอแล้ว>`

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/...`

## Context map (ลด token: worker เริ่มจากตรงนี้ ไม่ต้อง search ทั้ง repo)
| File | Symbol / Lines | Why (read / edit) |
|------|----------------|-------------------|
| `app/services/...py` | `func_name` L120-180 | edit |
| `tests/test_...py` | `test_xxx` L10-60 | pattern to copy |
- Verify command: `.venv/bin/python scripts/verify_changes.py <files>`
- หา symbol เพิ่ม: `grep -n <symbol> docs/agent/CODEMAP.md` แล้วอ่านเฉพาะช่วงบรรทัด

## Steps / Task Decomposition (บังคับ)
แตกงานเป็น atomic steps ก่อนเริ่ม (1 action / 1 ไฟล์ / 1 assertion ต่อ step) — ทำทีละ step ห้าม batch

| # | Atomic Step (หนึ่ง action) | Expected Outcome | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------|--------------------------|--------|
| 1 | ...                        | ...              | `.venv/bin/python -m pytest tests/<...> -q` | ⬜ |

## Acceptance / Done when
- `.venv/bin/python scripts/verify_changes.py <files>` → PASS
- `.venv/bin/python -m pytest tests/<...> -q`
- <observable outcome ที่พิสูจน์ว่าทำจริง>

## Out of scope / ห้ามแตะ
- Order placement / tick size logic (เว้นแต่ระบุ)

## Witness Session (เฉพาะ 🔴T2 — ต้องมีก่อน dispatch)
- Date / time (+07): · Human at screen: <ชื่อ> · Go-ahead: <ข้อความ/เวลา>
- Exact action: <side / symbol / volume / price / account>
- `DRY_RUN_MODE=false` เฉพาะ run นี้: <confirmed by human>
- Browser: headed (`QUICKTRADE_HEADLESS=false`) · ห้าม worker ปิด browser เอง

---

## Worker Report (homelab-build เขียน — STEP 2a)
- Card branch / commit(s): `TASK-xxx: <type>(<scope>): <summary>`
- Files changed:
- Summary:
- Tests run + result:
- Open questions (นอก scope → **ห้ามแก้เอง**, ให้สร้างการ์ด `--triage` หรือ child card):

---

## Review Report (homelab-review เขียน — STEP 2b)
- Diff audited: `git diff main...<branch>` / working tree
- Invariant & scope audit: <Anti-Mock / Broker isolation / Zero-OTP / scope boundary>
- Local verify: `.venv/bin/python scripts/verify_changes.py <files>` → PASS / FAIL
- Findings + สิ่งที่แก้เพิ่ม (ถ้ามี):
- Verdict: `APPROVED` / `CHANGES_REQUESTED`
- Triage routing: idea/tech-debt ที่เจอ → การ์ด `--triage` ใหม่ (`t_xxxxxxxx`)

---

## Verification & Stepwise Approval (human + planner — STEP 3 · T2 เท่านั้น)
- [ ] **Stage A (Code audit)**: diff ตรง scope + invariants ผ่าน (Anti-Mock, Zero-OTP, Uptick, broker isolation)
- [ ] **Stage B (Verify)**: `.venv/bin/python scripts/verify_changes.py <files>` = PASS
- [ ] **Stage C (Live / HITL)**: state จริงบนหน้าจอตรวจแล้ว (DOM text / screenshot path — ห้าม base64 เข้าโมเดล)
- [ ] **Stage D (Verdict + merge)**: PASS → human squash → `main` (gate #2)
- Verdict: PASS / CHANGES_REQUESTED
- Notes:

### Live Evidence (Anti-Mock — หลักฐานจริงเท่านั้น)
| Step | Expected Outcome | หลักฐาน (DOM text / screenshot path / order no) | Human witness |
|------|------------------|--------------------------------------------------|---------------|
| ...  | ...              | `data/screenshots/<file>.png`                    | ✅ / ❌ |

### On T2 error
1. STOP ทันที → 3-point RCA (session/context · live DOM · data schema)
2. self-anneal ≤ 3 ครั้ง → ไม่ผ่าน: capture anomaly → `rca/<broker>/` + `learned_workflows/<broker>/`
3. **ห้าม commit ไป `main`** · Verdict = `CHANGES_REQUESTED` + ลิงก์ RCA
4. รากเป็น code bug → การ์ดซ่อมใหม่ (`homelab-build`) → human re-verify · รากเป็นแผน → planner re-plan
   (ห้ามแก้ code ใน witness card นี้)

---

## Colab Report (homelab-colab เขียน — เฉพาะ ☁️ Colab card)
- Session: `colab` session id · GPU/CPU type:
- Job / notebook: · Input (Drive path):
- Output artifact (Drive path): · Runtime:
- Findings / next step:

---

## Planner Analysis (planner เขียน — STEP 5)
> Input = แผน (§Context / §DOM Contract / §Scope / §Steps) + ผล (§Worker Report + §Review Report + §Verification)
> ข้อที่เป็น "สมมติฐาน" → ต้อง live-verify (broker + LINE, headed) ก่อน merge (Anti-Mock)

### 1. Direction alignment
- Verdict: ✅ ALIGNED / ⚠️ DRIFT / ❌ OFF-DIRECTION · เหตุผล + อ้างอิง `directive/master_directive_v2.md`:

### 2. Directive consistency (findings)
- [ ] <แผน/ผล ขัดกับ directive อะไรบ้าง>

### 3. Code vulnerability scan (findings)
- [ ] <ไฟล์ในรายงานที่มีช่องโหว่ / เสี่ยงเทียบ RCA pattern>

### 4. Next loop improvement
- ปัญหาที่ loop นี้เจอ:
- สิ่งที่ loop ถัดไปต้องทำ (→ ป้อนเป็น `## Context` ของการ์ดถัดไป):
- Child cards / triage: `t_xxxxxxxx` → `todo` / `blocked`
