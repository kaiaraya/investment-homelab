# TASK-loop2-line-witness — Loop 2 LINE round-trip (T2, human witness)

> **Task ID**: `L2V-13` · **Board**: `kanban_loop2_verify.csv` (ใบปิด Loop 2 = `L2V-00`)
> **Tier**: 🔴 T2 — human at the phone · **DRY_RUN_MODE**: `true` (ห้าม `false`)
> **Gateway**: `uvicorn app.main:app --host 0.0.0.0 --port 8000` (ไม่ใช้ `--reload`)
> **Public webhook**: `https://line.a14s.dev/api/v1/webhook/line` (cloudflared → :8000)
> **Probe ที่ผ่านแล้ว**: `docs/handoff/evidence/loop2/line_probe_*.json`

## 0. สถานะก่อนเริ่ม (STEP 0a — ทำแล้ว 2026-10-22 10:47)

| stage | ผล | หลักฐาน |
|---|---|---|
| signed empty body | 200 `verify_ping` | tunnel + app ตอบ |
| bad signature | 400 `Invalid LINE signature` | signature ถูกบังคับใช้จริง |
| signed `/help` (ผ่าน public URL) | 200 ใน **0.097 s**, `CLI_QUEUED 65e261fc` | log: enqueued → push → completed 0.36 s |
| signed `/sbl` (ผ่าน public URL) | 200 ใน **0.080 s**, `CLI_QUEUED 0ca85fb3` | log: push HTTP 200, completed 0.30 s |

แปลว่า **webhook → queue → push ทำงานจริง** และไม่ต้องเดาอีกต่อไป แต่ยังไม่นับเป็น acceptance จนกว่าจะเห็นการ์ดในแอปและกดยืนยันครบทุกคำสั่ง

## 1. ลำดับที่ต้องพิมพ์ใน LINE (ทำตามลำดับ)

| # | พิมพ์ | ต้องเห็น | ถ้าไม่เห็น → เช็ค |
|---|---|---|---|
| 1 | `/help` | ข้อความ help + quick reply `/status /port /orders` | log `Enqueued job … (/help)`; ถ้าไม่มี = webhook ไม่ถึง |
| 2 | `/status` | การ์ดสถานะระบบ | `CLI_SBL_REJECTED`/error ใน log |
| 3 | `/port` | snapshot ล่าสุด หรือ "ยังไม่มี snapshot — ใช้ /port … sync" | — |
| 4 | `/sbl` | การ์ด SBL: ไม่มี lot ค้าง (หรือรายการถ้ามี) | DB `sbl_borrow_lots` ว่างหรือไม่ |
| 5 | `/sbl pool PTT` | การ์ด pool: จำนวนหุ้นให้ยืม + fee 3.5% | ต้องมี session broker; ถ้า fail = `NO_SESSION` (ยอมรับได้ในรอบ DRY_RUN แต่ต้องบันทึก) |
| 6 | `/borrow PTT 1000` | **การ์ดยืนยันการยืม** + ต้องมีคำว่า **จำลอง/DRY_RUN** | ต้องไม่มี "ยื่นขอยืมสำเร็จ" แบบจริง — นี่คือ Anti-Mock check |
| 7 | กดยืนยันบนการ์ดข้อ 6 | ข้อความยืนยัน + lot ถูกบันทึก (สถานะจำลอง) | DB: `select * from sbl_borrow_lots` → `remaining_qty=1000` |
| 8 | `/short PTT 1000 34.50` | กรณีมี lot จากข้อ 7 → การ์ดยืนยัน short · กรณีล้าง lot ก่อน → hint + quick reply `/sbl pool PTT` `/borrow PTT 1000` | ทั้งสองทางต้องมีหลักฐาน (เก็บทั้งคู่) |
| 9 | `/buy PTT 50k` | การ์ดยืนยัน buy พร้อม **จำนวนหุ้นที่ปัดลงเป็นทวีคูณ 100** + ราคาที่ใช้ | ต้องไม่ error `float(None)`; ถ้า `อ่านราคาตลาด…ไม่ได้` = ต้องระบุราคาเอง (บันทึกเป็น finding) |
| 10 | `/return PTT all` | การ์ดยืนยันการคืน + ดอกเบี้ยค้าง | ต้องคืน lot จากข้อ 7 ครบ (`FULLY_RETURNED`) |

## 2. หลักฐานที่ต้องเก็บ (ทุกข้อ)

- screenshot การ์ด → `docs/handoff/evidence/loop2/witness_<YYYYMMDD>/step-<n>.png`
- log ที่เกี่ยวข้อง → `docker`-less: `grep -aE 'AsyncCommandQueue|LINE API|CLI_' /tmp/hermes-gateway-loop2.log > …/witness_<date>/gateway.log`
- แถว DB หลังข้อ 7 และ 10 → `sqlite3 investment_homelab.db "select lot_id,symbol,remaining_qty,status from sbl_borrow_lots"`
- **ห้ามสรุป "ผ่าน" จาก screenshot เดียว** — ต้องมี (ก) การ์ดที่เห็น (ข) job id/completed ใน log (ค) แถว DB ที่เปลี่ยน

## 3. Failure playbook

| อาการ | ความหมาย | ทำอะไร |
|---|---|---|
| LINE ไม่มีอะไรขึ้น แต่ log ไม่มี event | LINE Console webhook URL ผิด/ปิดอยู่ | เปิด Console → Messaging API → Webhook `https://line.a14s.dev/api/v1/webhook/line` → Verify |
| log มี `timed out after 30.0s` | handler ค้าง (broker/browser) | เก็บ log, เปิดการ์ด T1 แยก ห้ามแก้โค้ดในใบนี้ |
| `CLI_QUEUE_FULL` | คิวเต็ม (worker ตาย?) | restart gateway, เก็บ log |
| ข้อความขึ้นว่า "สำเร็จ" แต่ไม่มี lot ใน DB | Anti-Mock fail | **ห้ามปิดใบ** — เปิด side-quest card + revert สถานะ Loop 2 |
| การ์ดขึ้นใน 1:1 แต่ไม่ขึ้นในกลุ่ม | push target = userId ไม่ใช่ groupId | ตรวจ `LINE_GROUP_ID` |

## 4. Done-When ของใบนี้

ครบ 10 ข้อในตาราง §1 โดยมีหลักฐาน 3 ชั้นตาม §2 และผู้ใช้เซ็นรับในแชต (ไม่ใช่จาก log อย่างเดียว) แล้วจึงไปปิด `L2V-00`
