# TASK-xxx: <ชื่องาน>

- Created: YYYY-MM-DD by Antigravity
- Broker: <Krungsri / Click2Win / Liberator / N/A>
- Status: TODO | IN_PROGRESS | REVIEW | DONE

## Context (Antigravity เขียน)
<ปัญหา / เป้าหมาย / RCA ที่เกี่ยวข้อง>

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/...`

## Steps / Task Decomposition (Loop Engineering — บังคับ)
แตกงานเป็น atomic steps ก่อนเริ่มงาน (1 action / 1 ไฟล์ / 1 assertion ต่อ step)
แต่ละ step ต้องมี Expected Outcome + วิธี Verify แล้วทำทีละ step ไม่ batch

| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| 1 | ...                        | ...                                | `.venv/bin/python -m pytest tests/<...> -q` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python -m pytest tests/<...> -q`

## Out of scope / ห้ามแตะ
- Order placement / tick size logic (เว้นแต่ระบุ)

---

## Cline Report (Cline เขียน)
- Files changed:
- Summary:
- Tests run + result:
- Open questions:

---

## Antigravity Review
- Verdict: PASS / CHANGES_REQUESTED
- Notes:
