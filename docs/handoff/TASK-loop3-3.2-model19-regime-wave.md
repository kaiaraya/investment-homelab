# TASK-loop3-3.2-model19-regime-wave: Regime & Wave Thrust Engine

- Created: 2026-10-28 by Hermes `homelab-build`
- Loop: 3 · Kanban card: `t_4e823047` · Card name: 3.2 Port Regime & Wave Thrust Engine
- Lane: `homelab-build` (T0/T1 code)
- Tier: 🟢 T0 (analytical port, zero live financial risk)
- Model: `gemini-3.1-pro`
- Broker: N/A (quantitative strategy engine)
- Status: REVIEW (round 2 — review round 1 defects fixed, see §8)

---

## 1. Scope

Port Pillar B of Model 19 (*Drawdown-Guarded 10-Regime & Wave Forensics*) into the
std lib-only `app/services/model19/` package:

| Module | Owns | Reference |
|---|---|---|
| `app/services/model19/regime_engine.py` | SQN snapshot loading (pandas-parity typing), 10-regime matrix, per-day tactic flags, transition tightening | notebook CELL 3 lines 112-125, CELL 5 lines 331-378, 424-441, 473-481 |
| `app/services/model19/wave_thrust.py` | point-in-time wave thrust, kinematic zone context, wave-forensics derived columns, short-squeeze shield | notebook CELL 4 lines 282-290, CELL 5 lines 380-388, 411-422, 443-445, 483-492 |
| `tests/test_model19_regime.py` | 106 unit + parity tests (AST isolation guard included) | — |
| `tests/fixtures/model19_regime_golden.json` | pinned goldens + source SHA-256 | — |

## 2. Frozen inputs (unchanged, verified by hash in the tests)

| File | Rows | Role |
|---|---|---|
| `mcp_historical_sqn_data.json` | 1199 | Market SQN + 100d volatility + 0.855 baseline |
| `kinematic_wave_zones_daily.csv` | 902 | `wave_context`, breadth counts, `net_delta`, `zone_mode`, `sub_type` |
| `wave_forensics_context_daily.csv` | 901 | `direction`, `wave_id`, run duration, peaks, `market_sqn` |

## 3. Design decisions

1. **No duplicated classifier.** `regime_engine` re-exports the 10-regime
   formula from `compass_engine` (Card 3.1) and a test asserts both ports agree
   on all 1199 dates, so the two cards cannot drift apart.
2. **Wave thrust is derived from breadth delta, not read from the CSV.** The
   reference engine computes `days_in_wave` / `delta_prog` from its own breadth
   series (CELL 4 lines 284-290); the port reproduces those pandas semantics
   (`np.sign(...).replace(0, nan).ffill().fillna(1)` → run segmentation) over
   the frozen zone file's `long_count - short_count`, which equals its
   `net_delta` column on every row.
3. **Blanks stay `nan`.** The reference writes
   `float(wf_day.get(col, 0.0) or 0.0)`; on a blank pandas cell that yields
   `nan`, so threshold tests silently fail. `forensics_day()` reproduces that
   exactly instead of "helpfully" substituting `0.0`.
4. **Transition tightening is gated on the tactic, like the notebook.** The
   whole block sits inside `if use_trans_tight:` (line 474), so
   `transition_tightening()` takes the day's tactic (`model=…`, or the flag via
   `use_trans_tight=…`; `transition_tightening_for_day(day, …)` binds both). It
   touches only risk knobs (`sl_mult`, `tp_mult`) and returns
   `is_trans_tight_day` plus slot-target flags; applying those flags to
   `target_l`/`target_s` stays with the entry/exit cards (3.3). See §4a.
5. **Isolation guard is AST-based** — both modules import stdlib +
   `app.services.model19` only (no `pandas`/`numpy`, no broker/order/DB/web).

## 4a. Code-map / notebook conflict resolved (read before 3.3 / 3.4)

The code map (`TASK-loop3-0a-model19-code-map.md`, Pillar B bullet) describes
transition tightening as "three rules gated on `zone_mode == 'TRANSITION'`" and
omits both the `use_trans_tight` tactic gate and the fourth rule. The frozen
notebook (lines 473-481) disagrees, and **the notebook wins** for a parity card:

- `is_trans_tight_day = False; if use_trans_tight:` wraps all four rules;
  `use_trans_tight = active_m in ['V6_1_TransitionTight', 'V6_3_FullUnified']`
  (line 438).
- Rule 4 — `if today_regime == 'Neutral Volatile': target_l = 0; target_s = 0;
  is_trans_tight_day = True` — has **no** zone-mode gate (but is still inside
  the tactic gate).
- Rules 2 and 3 also zero slot targets (`target_s = 0`; `target_l =
  min(target_l, 1)`), reported here as `zero_short` / `long_cap` / `zero_long`.

Measured on the frozen snapshot (901 rows shared with the zone file): 395
TRANSITION-zone days, of which only 88 carry a transition-tight tactic — so
**236 days keep `(1.0, 2.0)`** despite loud triggers (74 Neutral Quiet/12_V4_Macro,
71 Bearish Quiet/11_V3_Sniper, 47 Very Bearish Quiet/13_V4_1_Harvest, 28 Bullish
Volatile/V6_2_WaveSqueezeSpring, 14 Very Bearish Volatile/12_V4_Macro, 2 Very
Bullish Quiet/11_V3_Sniper). Rule 1 (`quiet_transition`) therefore **never fires
on the snapshot** under either regime map — all quiet regimes map to non-tight
tactics — but it is kept for parity (a future map could point one at V6_1).

Census asserted by `test_transition_tightening_snapshot_sweep`: TRANSITION rules
`{none: 344, thrust_exhaustion: 45, sqn_whipsaw: 3, neutral_volatile: 3}` (51
tightened days, 51 `is_trans_tight_day`), plus 12 `neutral_volatile` days on
non-TRANSITION zones and zero leaks on non-tight tactics.

Consumers of `is_trans_tight_day` in the notebook, for 3.3/3.4: BE trigger
`0.65` vs `1.0` (line 508), exit clamp `sm = min(sm, 0.70); tm = min(tm, 1.30)`
(517), RUNWAY 7 vs 10 days (543), entry slot merge (612).

## 4. Verification

```
.venv/bin/python scripts/verify_changes.py app/services/model19/regime_engine.py \
    app/services/model19/wave_thrust.py tests/test_model19_regime.py
→ compileall OK · targeted tests/test_model19_regime.py · PASS (106 passed in 39.52s)
.venv/bin/python -m pytest tests/test_model19_compass.py -q
→ 73 passed, 1 skipped   (package __init__ re-check, no regression)
```

Parity evidence:

| Check | Result |
|---|---|
| 10-regime label, all 1199 snapshot rows vs the notebook if-chain | 100% equal |
| Full `date|label` map SHA-256 vs pinned golden | match |
| Regime distribution (10/10 states present) | match |
| Wave thrust `date|days|delta_prog` digest, 902 rows | match |
| Forensics `above_075/cross_075/sqn_crosses_10d/sqn_vel_5d`, 901 rows | match |
| Vendor forensics `direction` + `sign`, 901 rows | 100% equal |
| Vendor `running_peak_delta` before the snapshot gap | 806/806 equal |
| Vendor `running_wave_dur` | 846/901 equal; 55 exceptions all at/after 2026-05-05 |

### Known snapshot caveat (not a port defect)

The vendor engine that produced `wave_forensics_context_daily.csv` ran on a
longer series than the frozen zone file: rows for 2026-05-01..04 (and other
multi-day gaps) were dropped from the snapshot, so the vendor's
`running_wave_dur` keeps counting through them. Its last row also carries a
revised delta (-82) versus the zone file (-115). Both facts are asserted
explicitly in
`test_vendor_csv_run_length_agrees_except_after_the_data_gap`, so the exception
set is pinned rather than hidden.

## 5. Worker Report (`homelab-build`)

- Files created: `app/services/model19/regime_engine.py`,
  `app/services/model19/wave_thrust.py`, `tests/test_model19_regime.py`,
  `tests/fixtures/model19_regime_golden.json`, this handoff.
- Files updated: `app/services/model19/__init__.py` (docstring + submodule
  exports), `scripts/verify_changes.py` (MODULE_TEST_MAP entries for the two
  new modules).
- No commits; no changes to `DRY_RUN_MODE` / `TRADING_MODE`; no broker, order or
  DB module touched.
- Careful during verification: another `pytest` process on the shared repo made
  `test_homelab.db` read-only mid-run (the documented single-writer hazard).
  Re-ran after it exited → PASS.

## 6. Next cards

- 3.3 Flip-cut / breakeven lock / weedout exit wiring consumes
  `RegimeDay.dir_tighten`, `SqueezeAlert`, `forensics_day()` and now
  `transition_tightening_for_day(day, zones[date].zone_mode, sqn_crosses_10d,
  running_peak_delta).is_trans_tight_day` (BE trigger + exit clamp); it must also
  apply `zero_long` / `long_cap` / `zero_short` to its slot targets.
- 3.4 parity harness should call `RegimeEngine` + `load_wave_context()` instead
  of re-parsing the CSVs, and must reproduce the `use_trans_tight` gate (see §4a)
  or its backtest will diverge on 236 historical days.

## 7. Review hand-off

Ready for `@homelab-review` audit.

## 8. Round-2 rework (`homelab-build`, after review round 1)

Review round 1 requested one defect class — `transition_tightening()` was not a
faithful port of lines 473-481. Fixed as follows, with nothing else touched
(label / thrust / forensics code unchanged):

1. **Tactic gate.** `transition_tightening(..., model=..., use_trans_tight=...)`
   now resolves `use_trans_tight` (explicit flag wins, else `model in
   TRANSITION_TIGHT_MODELS`) and returns the reference default `(1.0, 2.0)`,
   `rule='none'`, `is_trans_tight_day=False` when it is false. Rules 1-3 keep
   their `zone_mode == 'TRANSITION'` gate; rule 4 has none, as in the notebook.
   `transition_tightening_for_day(day, zone_mode, ...)` is the intended call site
   and binds `RegimeDay.model` / `RegimeDay.use_trans_tight`.
2. **Fourth rule + flag.** `TransitionTightening` gained `is_trans_tight_day`,
   `zero_short`, `zero_long`, `long_cap` (+ `as_dict()`); the `Neutral Volatile`
   rule is ported verbatim (zeroes both slot targets, leaves the sl/tp pair from
   an earlier rule in place, sets the flag).
3. **Tests.** `test_transition_tightening_quiet_regimes`,
   `test_transition_tightening_sqn_whipsaw_threshold` and
   `test_transition_tightening_thrust_exhaustion_is_the_last_rule` were rewritten
   around a transition-tight tactic; added
   `test_transition_tightening_cannot_fire_on_a_non_trans_tight_tactic`
   (parametrized over every non-tight tactic),
   `test_transition_tightening_explicit_flag_beats_the_model`,
   `test_transition_tightening_neutral_volatile_rule_has_no_zone_gate`,
   `test_transition_tightening_quiet_transition_rule_never_fires_on_the_snapshot`,
   `test_transition_tightening_for_day_uses_the_assessed_flags` and the
   whole-snapshot `test_transition_tightening_snapshot_sweep`
   (395 TRANSITION days, `{none: 344, thrust_exhaustion: 45, sqn_whipsaw: 3,
   neutral_volatile: 3}`, zero leaks on non-tight tactics).
4. **Code-map conflict documented** in §4a so 3.3 / 3.4 do not re-inherit it.

Verification after the rework (real output):

```
.venv/bin/python scripts/verify_changes.py app/services/model19/regime_engine.py \
    app/services/model19/wave_thrust.py tests/test_model19_regime.py
→ compileall OK · targeted tests/test_model19_regime.py · PASS (106 passed in 39.52s)
.venv/bin/python -m pytest tests/test_model19_compass.py -q
→ 73 passed, 1 skipped
```

Test count 97 → 106 (9 new gate/rule cases, 3 rewritten). No commits.
