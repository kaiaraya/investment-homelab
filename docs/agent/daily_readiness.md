# Daily readiness (ใช้ทุกวันก่อนทดสอบ pillar)

> ย้ายมาจาก AGENTS.md (คำต่อคำ) เมื่อ 2026-10-12 — ต้นฉบับเต็ม: `docs/agent/full/AGENTS_full.md`

- Skill: `.agents/skills/daily-readiness/SKILL.md` · Runner: `scripts/daily_readiness.py`
- คำสั่งเดียว: `.venv/bin/python scripts/daily_readiness.py` → exit `0` = GO (พร้อม), `1` = NO-GO (ต้อง HITL)
- Auto re-login ทันทีเมื่อ OTP relay live; **ห้ามยิง SMS OTP ถ้า `otp_relay_readiness.check().ready != true`** (Invariant 9)
- Tests: `.venv/bin/python -m pytest tests/test_daily_readiness.py tests/test_otp_relay_readiness.py -q`
- Handoff/RCA: `docs/handoff/TASK-daily-readiness-skill.md`, `docs/handoff/TASK-line-otp-group-relay.md`
