# วิเคราะห์เวลา + Lean Process (2026-10-26)

## 1. เวลาหายไปไหน (วัดจริง ไม่ใช่ความรู้สึก)

ช่วงที่ทำ Loop-2 + CDP wave: **13:20 → 16:05 = 165 นาที**

| # | กิจกรรม | เวลาจริง | หลักฐาน |
|---|---|---|---|
| 1 | **worker รันทีละใบ (โซ่ 4 ใบ CDP-1..4)** | **108 นาที** (15+18+30+45) | `git log` 14:48/15:06/15:36/16:00 + `kanban runs` |
| 2 | **full suite 3 ครั้ง** (423s + 565s + ~570s) | **26 นาที** | `/tmp/pytest_after_3cards.log`, `pytest_after_cdp4.log`, `pytest_clean_cdp4.log` |
| 3 | gate/targeted ~8 ครั้ง (60–76s/ครั้ง) | ~9 นาที | `verify_changes.py` |
| 4 | ตามบั๊ก DB/WAL + `test_admin_console` ปนเปื้อน | ~15 นาที | 158 errors / 1014 errors / 74 errors บน HEAD สะอาด |
| 5 | พิธีบอร์ด (create 5 + link 4 + block 4 + set-model 4 + comment 5 + snapshot 3) | ~10 นาที | เครื่องมือ kanban |
| 6 | ที่ผมเขียนเอง (CDP-5, mapping, runbook) | ~15 นาที | commits |

**สรุปสาเหตุ:** ไม่ใช่เพราะ "งานยาก" แต่เพราะ **(ก) worker รันทีละใบเพราะ peلت shared tree (ข) ผมรัน full suite ในลูป (ค) gate กว้างเกิน (ง) DB hygiene พังแล้วทำให้รันซ้ำ**.

## 2. ของที่ "ไม่ควรตัด" (คุณภาพ)

| ต้องเก็บ | ทำไม | ต้นทุนจริง |
|---|---|---|
| live probe ยืนยัน session/broker (1 ครั้ง/เวฟ) | เป็นหลักฐานว่า probe ไม่ได้แค่ผ่าน unit test | ~30 วิ |
| gate เฉพาะเส้นทางเงิน (order/borrow/G3) | พลาดแล้วเสียเงินจริง | ~5 วิ (แบบ fast) |
| witness T2 + headed browser | invariant ของโปรเจกต์ | ตามรอบตลาด |
| full suite **คืนละครั้ง** (cron) | จับ regression ข้ามโมดูลที่ targeted ไม่เห็น | 0 (ไม่บล็อกงาน) |

## 3. Lean Process ใหม่ (เป้า 4x → ~25 นาที/เวฟ)

| มาตรการ | จาก → เป็น | ประหยัด |
|---|---|---|
| **P1 · 1 การ์ด 1 เวฟ** (รวม 3–5 งานย่อยที่ไฟล์ชนกันน้อย) ไม่ผูกโซ่ 4 ใบ | worker 108 นาที → **20–25 นาที** | ~85 นาที |
| **P2 · ไม่รัน full suite ในลูป** → cron 23:00 + ก่อน witness เท่านั้น | 26 นาที → **0** | ~26 นาที |
| **P3 · `verify_changes.py --fast`** = รันไฟล์เทสต์ที่แคบที่สุดของ symbol ที่แก้ (≤10s) | 9 นาที → **~1 นาที** | ~8 นาที |
| **P4 · DB hygiene**: `rm -f test_homelab.db*` (รวม `-wal`/`-shm`) ที่ SessionStart + guard ห้ามรัน concurrent | 15 นาที → **0** | ~15 นาที |
| **P5 · แก้กับดักเทสต์ 2 ตัว** (env pollution + WAL) | ตัด false alarm ทั้งหมด | ลบงานซ้ำ |
| **P6 · card body template**: "รันเฉพาะ tests/<file> · ห้าม full suite · ห้าม commit" | worker ไม่เผา 10 นาทีรัน suite เอง | ~10 นาที/เวฟ |
| **P7 · ไม่ `sleep` รอ** — ใช้ notify + ทำงานถัดไประหว่างรอ | ไม่บล็อก critical path | ~0 แต่ throughput ดีขึ้นมาก |
| **P8 · งานเล็ก non-money (≤20 บรรทัด) ผมแก้เอง** ไม่ต้องมี worker | 15 นาที → **3 นาที** | ~12 นาที |

**ผลรวมต่อเวฟ: ~101 นาที → ~25 นาที (4x)**

## 4. หลักฐานว่าปัญหาเทสต์เป็นของเดิม ไม่ใช่ของใหม่

รันบน HEAD ที่ stash การเปลี่ยนแปลงของผมออก:
```
pytest tests/test_line_cli_flow.py tests/test_admin_console.py tests/test_console_cockpit_api.py
→ 47 passed, 74 errors
```
สาเหตุ: `test_admin_console` เขียน `.env` + reload settings → DB/settings ของโมดูลถัดไปพัง
+ เศษ `test_homelab.db-wal/-shm` จากรอบที่ถูก SIGKILL ทำให้ `drop_all/create_all` ล้ม
→ ต้องแก้ 2 อันนี้ก่อน ไม่งั้น gate ใด ๆ ที่รวมหลายไฟล์จะโกหกตลอด

## 5. สิ่งที่จะทำเพื่อให้เป็นจริง (เรียงตามผลตอบแทน)

1. **P4+P5 (30 นาที)**: conftest ล้าง `-wal/-shm` ตอน session start · `test_admin_console` คืน `.env` + engine ให้ครบ · `verify_changes.py` ล้าง DB ให้เอง
2. **P3 (20 นาที)**: `--fast` mode (map symbol→ไฟล์เทสต์ ผ่าน `MODULE_TEST_MAP` + `-k` ของชื่อฟังก์ชัน)
3. **cron 23:00 full suite (5 นาที)**: แจ้งเฉพาะเมื่อผลเปลี่ยน
4. **P6 template (5 นาที)**: ใส่ในบอร์ด/สกิลเป็นค่าเริ่มต้นของ card body
5. **P1/P7/P8**: เปลี่ยนวิธีทำงานทันที (ไม่ต้องเขียนโค้ด)

## 6. ตัวอย่างเวฟแบบใหม่ (ของจริงที่เพิ่งทำ)

เดิม: แผน → 5 การ์ด → โซ่ 4 worker → full suite ×3 → gate ×8 → debug DB → 101 นาที

ใหม่: แผน 5 นาที → **1 การ์ดเดียว** (probe + /status + /login + MCP รวมกัน, ผมแก้ 2 ไฟล์ที่เหลือเอง) → worker 1 รอบ 20 นาที → live probe 30 วิ → gate fast 10 วิ → commit + snapshot 1 นาที = **~27 นาที**
