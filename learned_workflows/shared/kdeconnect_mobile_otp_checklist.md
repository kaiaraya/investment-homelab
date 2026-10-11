# KDE Connect Mobile OTP Checklist - Xiaomi Mi 10T Pro 5G (M2007J3SY)

> แนวป้องกันไม่ให้ **SMS OTP จากมือถือไม่ถูก relay ไปยัง Homelab (NUC)** ซ้ำอีก
> ใช้กับเครื่อง **Mi 10T Pro 5G (M2007J3SY)** บน MIUI / HyperOS
> **Last verified:** 2026-10-07

## Root Cause Summary
KDE Connect **relay "notification banner" ไม่ใช่ตัว SMS ในฐานข้อมูลโดยตรง**
ดังนั้นถ้าแอป KDE Connect ถูก MIUI/HyperOS **ปิด / หลับ / ถอนสิทธิ์** → NUC ไม่มีอะไรให้รับเลย
(อาการเดียวกับที่เคยเจอตอนใช้ **MacroDroid** - MIUI ชอบฆ่าแอปพื้นหลัง + ถอนสิทธิ์ + หน่วงด้วย Doze)

| RCA Ref | บทเรียนที่พิสูจน์แล้ว |
| :--- | :--- |
| `KDE-RCA-005` | Doze หน่วง SMS relay ถึง **~7m39s** → แก้ด้วย Battery saver = No restrictions |
| `KDE-RCA-008` | relay **notification** ไม่ใช่ SMS DB; SMS ที่ไม่เด้ง banner จะไม่ถูก relay แต่ SMS จริง relay ~1s |
| `KDE-RCA-003` | มือถือเข้าถึง NUC ได้ 2 เส้นทาง (Home Wi-Fi + Tailscale) |

## Step 0 - แยกให้ออกว่าเป็นฝั่งมือถือหรือฝั่ง NUC (10 วินาที)
บน NUC รัน:
```bash
tail -f ~/.cache/gsconnect/incoming_notifications.jsonl
```
แล้วให้ส่ง SMS / OTP เข้ามือถือ:
- PASS: มี entry ใหม่เด้งขึ้น ~1-2 วิ → relay ปกติ (ปัญหาคือ timing/Doze เท่านั้น → ทำข้อ A)
- FAIL: ไม่มี entry เลย ทั้งที่มือถือเด้งการ์ด → ทำข้อ **A-F** (มือถือ) แล้วค่อยตรวจข้อ **G** (NUC)

---

## A. ปลดล็อกให้ KDE Connect ทำงานพื้นหลัง (สำคัญสุด)
1. `Settings` → `Apps` → `Manage apps` → เลือก **KDE Connect**
2. `Battery saver` → เปลี่ยนจาก *MIUI Battery Saver* เป็น **No restrictions**
3. เปิดสวิตช์ **Autostart** ให้เป็นสีฟ้า
4. (ถ้ามี) ปิด **Restrict background activity / Pause app activity if unused**
5. เปิดแอป KDE Connect → เข้า **Recent Apps** → กดค้างที่การ์ด KDE Connect → แตะ **Lock (แม่กุญแจ)** - กัน MIUI เคลียร์ RAM แล้วปิดแอป

## B. สิทธิ์การแจ้งเตือน (Notification Access - ตัวที่ relay ใช้จริง)
1. `Settings` → `Apps` → `Special app access` → **Notification access** *(Android 11+ อาจชื่อ "Device & app notifications")*
2. ค้นหา **KDE Connect** → เปิดเป็น **Allow**
3. **HyperOS เพิ่ม:** `Settings` → `Notifications & status bar` → `App notifications` → **KDE Connect** → เปิดทุกตัว + **Pop-up notification**

## C. สิทธิ์ SMS / โทรศัพท์
- `Settings` → `Apps` → **KDE Connect** → `Permissions`: **SMS** = Allow, **Phone** = Allow

## D. ปลั๊กอินในแอป KDE Connect
เปิดแอป KDE Connect → แตะเครื่อง **home-lab** → **Plugin settings** ติ๊กให้ครบ:
- [x] **Notification sync** - ส่ง notification จากมือถือ → NUC (ตัวสำคัญสุด)
- [x] **Send notifications** - รับ critical alert จาก NUC
- [x] **SMS integration** - (ถ้ามีในเวอร์ชันที่ติดตั้ง)
- [x] **Ping**

## E. เครือข่าย (2 เส้นทาง - ขอแค่ 1 ทาง)
- อยู่บ้าน: ต่อ Wi-Fi เดิมก็พอ
- นอกบ้าน: เปิด **Tailscale** แล้ว `KDE Connect → Settings → Add devices by IP` ใส่ IP ของ NUC (`100.88.217.33`)

## F. ยืนยันผล (ทำหลังตั้งครบทุกข้อ)
1. Ping จาก NUC → มือถือต้องสั่น:
   ```bash
   kdeconnect-cli -d 9507a3fd53f848da9135ebe6253db18a --ping-msg "homelab test"
   ```
2. ส่ง SMS ทดสอบจริง → ดู `tail -f ~/.cache/gsconnect/incoming_notifications.jsonl` → ต้องมี entry ใหม่ภายใน ~2 วิ

## G. ถ้าทำ A-F ครบแล้วยังไม่ติด → ฝั่ง NUC (cross-check)
- **GSConnect ต้องยัง paired อยู่** - อย่าเพิ่งถอด/ปิด extension หรือ `gsconnect.service`
- เช็คเวอร์ชัน `kdeconnect` ฝั่ง NUC (ตอนนี้ `23.08.5`) vs แอปมือถือรุ่นใหม่ → เคยเจอ `discarding unsupported packet` (KDE-RCA-008)
- เช็ค D-Bus readiness แบบ real-time ด้วย `isReachable` (ห้ามใช้ `iconName`/`statusIconName` - คืน false-negative ได้)

---

## ข้อมูลอุปกรณ์
| รายการ | ค่า |
| :--- | :--- |
| รุ่นมือถือ | Mi 10T Pro 5G (M2007J3SY) |
| KDE Connect device id | `9507a3fd53f848da9135ebe6253db18a` (active) |
| Phone Tailscale IP | `100.119.166.62` (mobile1) |
| NUC (home-lab) Tailscale IP | `100.88.217.33` |
| พอร์ต KDE Connect | UDP/TCP 1714-1764 |

## ตรวจซ้ำประจำ (หลัง Reboot / อัปเดตแอป / อัปเดต MIUI)
MIUI/HyperOS มีนิสัย **ถอนสิทธิ์เองหลังอัปเดต หรือรีเซ็ต battery policy** → หลังทุกครั้งที่รีบูตเครื่องหรืออัปเดตระบบ ให้วนเช็คข้อ **A(2-3), B(2), F(1)** อย่างน้อยครั้งหนึ่ง
