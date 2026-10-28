# Loop 3 · 3.0a — Verified Freeze Source List (pre-checked by @homelab-review)

ตรวจเมื่อ 2026-10-27 บนเครื่องจริง · ทุกไฟล์มีสำเนาซ้ำที่ `data/` และ `data/shared_mcp/` (prices: `data/` และ `data/backtest/`)
**ทั้งสองชุด byte-identical (sha256 ตรงกัน)** → หยิบจาก `data/` ได้เลย ไม่ต้องกังวลเรื่อง "เลือกผิดชุด"
(แต่ยังต้องบันทึก sha ลง `reference/model19/MANIFEST.json` ตาม spec)

## Base path
`/home/araya-sawasdichai/compute/data/colab_pull/data/`

| # | filename | sha256 (12) | note |
|---|---|---|---|
| 1 | `thai_fear_greed_daily.csv` | `532ca580a212` | find_file() |
| 2 | `kinematic_wave_zones_daily.csv` | `ae22b47fff2f` | find_file() |
| 3 | `chandelier_stop_daily_cache.csv` | `e685bdf7b0e3` | find_file() · 27 MB ใหญ่สุด |
| 4 | `decision_compass_master_records.csv` | `6bc306eb8c4b` | find_file() |
| 5 | `wave_forensics_context_daily.csv` | `d702ad08e6d0` | find_file() |
| 6 | `prices_2026_cache.csv` | `77dddbb8bda1` | glob `prices_202*.csv` |
| 7 | `prices_2025_cache.csv` | `6c38bfa0a9a4` | glob |
| 8 | `prices_2024_cache.csv` | `a6cd6a05370c` | glob |
| 9 | `prices_2023_cache.csv` | `d85f7370c678` | glob |
| 10 | `mcp_historical_sqn_data.json` | `ca22d431b75e` | ⚠️ **ตกหล่นจาก spec 6 ไฟล์** — notebook บรรทัด 132 ต้องใช้ |
| 11 | `compass_returns_engine.py` | `df1a376f861e` | ⚠️ **module ที่ notebook import** (บรรทัด 295) ไม่ใช่แค่ data |
| 12 | `plot_comparison_boxplot.py` | `f6f8272192d6` | ⚠️ **module ที่ notebook import** (บรรทัด 296) |

Notebook: `~/Downloads/18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py` · sha256 (12) `1ee891597298` · 64,969 B

## ต้องตัดสินตอนทำ code map
- glob `prices_202*.csv` **แมตช์เกิน**: มี `prices_2026_h1_cache.csv` / `prices_2026_h2_cache.csv` อยู่ในโฟลเดอร์เดียวกัน
  → freeze เฉพาะ 4 ไฟล์ปี (2023–2026) และบันทึกเหตุผลไว้ ไม่งั้น pandas concat จะนับวันซ้ำและ parity เพี้ยนโดยไม่มี error
- `position*.csv` (บรรทัด 197–200) เป็น optional input — ยืนยันว่าไม่จำเป็นต่อ parity ก่อนตัดออกจาก fixture
- `find_file()` มี fallback ไป Drive (`google.colab.drive`) — ตอน vendor ต้อง neutralize ให้อ่านจาก `reference/model19/` เท่านั้น (ถ้าไม่ neutralize แล้วเครื่องไม่มี Drive จะ exception)
