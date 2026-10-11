# Learned Workflow: SBL Borrow Inventory Inquiry & Short Audit
**Workflow Name:** `sbl_borrow_inquiry`  
**Recorded At:** 2026-10-03 04:02:23 UTC  
**Status:** `VERIFIED_LIVE` (Watch-and-Learn Co-pilot Session)  
**Broker Platform:** Krungsri TradeMan Pro (`3024959` Margin)

## Description
ขั้นตอนการเปิดหน้าต่างค้นหาหุ้นยืม SBL ตรวจสอบโควตาคงเหลือ กรองหุ้นที่ติดประกาศเครื่องหมาย XD/XR และประเมินความเสี่ยงเงินชดเชยปันผล 100%

## Verified Execution Steps (4-Tier Self-Annealing)
| Step | Action | Target Selector | Fallback Tier | Description |
| :---: | :---: | :--- | :--- | :--- |
| 1 | `NAV` | `https://trademan.in.th/SBL` | Tier 1 Semantic URL | เข้าตรงสู่แท็บหุ้นยืม SBL |
| 2 | `DISMISS` | `button:has-text('ตกลง'), .v-btn` | Tier 3 JS Event | ปิด Modal ประกาศ "มีอะไรใหม่" |
| 3 | `SCRAPE` | `table tbody tr` | Tier 3 DOM Extract | กวาดโควตา SET50 (พบ 0 รายการ) |
| 4 | `CLICK` | `button:has-text('XD, XR')` | Tier 1/2 Text Filter | สลับไปยังแท็บ Corporate Actions |
| 5 | `SCRAPE` | `table tbody tr` | Tier 3 DOM Extract | กวาดรายชื่อหุ้นใกล้ขึ้นเครื่องหมาย XD (พบ 4 ตัว) |
| 6 | `AUDIT` | `sbl_intelligence_service` | Tier 4 Decision Engine | จำแนก BORROW_ALLOWED, CAUTION_XD_RISK, OUT_OF_STOCK |

## Live Artifact Proofs
- SBL Overview Screenshot: `/home/araya-sawasdichai/.gemini/antigravity-ide/brain/d1755cee-0ec2-4505-9300-2a8d4fcb2a94/trademan_sbl_studio_overview.png`
- XD/XR Corporate Actions Tab: `/home/araya-sawasdichai/.gemini/antigravity-ide/brain/d1755cee-0ec2-4505-9300-2a8d4fcb2a94/trademan_sbl_xd_xr_tab.png`
- Verified Accounts: `3024959` (Credit Balance / Margin Exclusive)
