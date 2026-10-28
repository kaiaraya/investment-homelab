# TASK-loop3-3.1-model19-compass: Port Compass Engine & Setup Scoring

- Created: 2026-10-28 by Hermes `homelab-build`
- Loop: 3 (Model 19 core) · Kanban card: `t_d326ce5f`
- Lane: `homelab-build` (T1 code & reference architecture)
- Model: `gemini-3.1-pro`
- Broker: N/A (quantitative strategy engine, no order path)
- Workspace: scratch · Repo branch: `task/loop3-0a-model19-code-map`
- Status: REVIEW
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/model19/compass_engine.py app/services/model19/setups.py tests/test_model19_compass.py` → **68 passed**

---

## 1. Scope

Port of Pillar A (Breadth Dynamics & Decision Compass) from the frozen vendor
snapshot `reference/model19/` into a Homelab service package, with 100% output
parity against the reference implementation:

| Reference source | Port target |
|---|---|
| `compass_returns_engine.py:compute_cell_stat` | `app/services/model19/compass_engine.py:compute_cell_stat` |
| `compass_returns_engine.py:DynamicCompassEngine.compute_all_6_setups` | `DynamicCompassEngine.compute_all_6_setups` |
| notebook CELL 4 scoring + mode selection (lines 312-323) | `setups.py:score_setups` / `select_campaign_mode` |
| `plot_comparison_boxplot.py:calc_stats_20d` | `setups.py:calc_stats_20d` |
| notebook CELL 3 breadth counts (lines 204-208) | `setups.py:classify_breadth_counts` |
| notebook CELL 4 `fg_tier` fallback (lines 303-304) | `setups.py:derive_fg_tier` |
| notebook CELL 5 10-regime matrix (lines 331-378) | `compass_engine.py:classify_regime_10` / `get_10_regime` / `MAPPING_10_REGIMES_M18_ATR` |

## 2. Files

1. `app/services/model19/__init__.py` (new) — package surface / isolation contract.
2. `app/services/model19/setups.py` (new) — 20-day rolling box stats, breadth
   counts, F&G tier derivation, 6-slot defaults, compass scoring, campaign mode.
3. `app/services/model19/compass_engine.py` (new) — master-record loader,
   `DynamicCompassEngine` (calibration table + daily decision), 10-regime classifier.
4. `tests/test_model19_compass.py` (new) — 68 unit + parity tests.
5. `tests/fixtures/model19_compass_golden.json` (new) — frozen goldens for 5
   scenarios covering all four campaign modes (LONG / SHORT / BI-DIRECTIONAL / HOLD CASH).
6. `scripts/verify_changes.py` (modified) — `MODULE_TEST_MAP` entries for the
   three new modules → `tests/test_model19_compass.py` (Anti-Mock: no guessing).

## 3. Isolation guard (Req 3)

Both modules import **standard library only** plus `app.services.model19.*`.
Enforced by `test_isolation_guard_no_broker_order_or_db_imports` and
`test_isolation_guard_only_stdlib_and_model19`, which AST-walk the module
sources and reject any import of `order_service`, `trade_dispatcher`,
`quicktrade_*`, `broker_cdp`, `action_exit_*`, `app.browser`, `app.brokers`,
`app.api`, `app.db`, `app.core.events`, `sqlalchemy`, `fastapi`, `pandas`,
`numpy`, `scipy`. No DB session, no network, no order path.

> Consequence: the port does not use pandas/Numpy/SciPy even though the
> reference does — the statistics (`percentile` linear-interpolation, `median`,
> `percentileofscore(kind='weak')`) are re-implemented to NumPy/SciPy semantics
> and pinned by unit tests.

## 4. Parity strategy (zero float drift)

* `test_reference_parity_full_calibration_grid` loads the **actual frozen
  reference module** (`reference/model19/compass_returns_engine.py`) via
  `importlib` and instantiates it with `object.__new__` (its own `__init__`
  needs pandas; the compute path is pure Python). It then compares, with exact
  `==` on dicts/lists:
  * 80 combinations of `is_bull (2) × fg_tier (5) × q_label (4) × box (2)`,
  * 2646 calibration records (`transition` 882 / `pure_trend` 882 / `king_trend` 882),
  * table rows (12 keys each), `long_rets`, `short_rets`.
* `test_reference_parity_default_slots` — same, for the `stats=None` fallback path.
* `test_reference_parity_cell_stat_spot_grid` — per-cell `{days, win, ret}` over
  3 families × 3 market types × 5 tiers × 4 quantiles × 2 box arms × 2 sides.
* `test_golden_scenarios_match_port` — score/mode snapshot against
  `tests/fixtures/model19_compass_golden.json`; the fixture embeds the SHA-256 of
  both reference inputs and the test re-verifies them, so a re-frozen snapshot
  fails loudly instead of drifting the goldens.
* Arithmetic order is preserved deliberately: `(sum(col) / days) * 100.0` for
  win, `sum(col) / days` for return, `round(score, 2)` last — no reformulations.
* `test_calc_stats_20d_parity_against_frozen_reference` — live parity for the
  **only** ported function that previously had no reference evidence:
  `plot_comparison_boxplot.py:calc_stats_20d`. The plot script imports
  pandas/matplotlib at module level, so the test lifts *just that function* out
  of the frozen source with `ast` and executes it with real numpy/scipy, then
  compares the **full result dict** (every key incl. `thai_box`) with `==`.
  It is `pytest.skip`-gated on numpy/scipy, and the skip reason says explicitly
  that a skip means *unverified live in this environment*, not parity.
* `test_golden_calc_stats_20d_cases_match_port_exactly` — the always-on arm:
  7 cases (even/odd windows, both IQR arms, the exact-baseline boundary, the
  no-baseline arm, tied scores) whose expected dicts were produced by running
  the extracted reference function under numpy 2.5.4 / scipy 1.18.1 — **not** by
  running the port. `plot_comparison_boxplot.py` is SHA-256-pinned in the fixture
  alongside the two original inputs.

### 4b. Three defects this round's parity work caught

1. **`thai_box` labels diverged from the reference.** `calc_stats_20d` emits
   `'กล่องสั้น (Squeeze)'` / `'กล่องยาว (Dispersion)'`; the port had
   `'กล่องสั้น'` / `'กล่องยาว'`. Fixed. The compass table's `box` column *is*
   the bare pair (from `compute_all_6_setups`), so it now has its own constants
   `TABLE_BOX_SHORT` / `TABLE_BOX_TALL` instead of sharing one pair for two
   meanings. `test_box_label_constants_match_the_reference_strings` asserts all
   six strings as literals.
2. **`percentile_of_score_weak` had a 1-ULP float drift.** scipy computes
   `count * (100.0 / n)`; the port computed `(count * 100.0) / n`. These differ
   for some `n` — for n=11, count=11 scipy returns `100.00000000000001` while
   the old port returned `100.0`. Fixed to the reciprocal-first order, pinned by
   `test_percentile_of_score_weak_reproduces_scipy_reciprocal_order_ulp`.
   This one only surfaces against the real reference; the old unit tests could
   not see it.
3. **`percentile()` was not NumPy-exact: one lerp arm instead of two.** NumPy's
   `_lerp` is two-branch (`t < 0.5 → a + (b-a)*t`, `t >= 0.5 → b - (b-a)*(1-t)`);
   the port implemented only the first form for both halves. The arms are
   algebraically identical but **not** bit-identical, so `q25`/`q75`/`iqr`
   drifted by 1 ULP on non-binary-exact windows — e.g.
   `[3.67, -2.934029, 0.3]` @ q25: port `-1.3170145000000002`, NumPy
   `-1.3170145`. Fixed by mirroring the branch structure; a 6000-window fuzz
   (ints / decimals / duplicates / constant / negative / 1e6-magnitude, n∈[3,40],
   baseline None and set, q∈{0,1,5,10,25,33.3,50,66.7,75,90,95,99,100}) then
   reported **0 percentile mismatches and 0 full-dict mismatches** against the
   frozen reference. Pinned by
   `test_percentile_reproduces_numpy_two_branch_lerp_exactly` (exact `==`, no
   `approx`) and by 5 new reference-derived decimal cases in the golden fixture.

The common thread: exactness claims are only worth what the **inputs** say. All
of 1-3 were invisible to windows made of halves, quarters and integers, because
those land on binary-exact values where both formulations agree.

## 5. Behaviour notes for downstream cards (3.2 / 3.3 / 3.4)

* `compute_cell_stat` recomputes the box median from the **active** record set
  per call (`dyn_l_med` / `dyn_s_med`), so it must not be cached across day sets.
* Qualifying threshold is **strict** (`score > 100.0`); `100.0` exactly does not qualify.
* Short scores are negative by construction (`short_rets = -long_rets`), so short
  qualification only happens on inverted/defensive cells — expected, not a bug.
* Slots 0/2/4 (`tl`, `pb`, `kl`) score with `win_norm`; slots 1/3/5 (`ts`, `bear`,
  `ks`) score with `win_inv` (inverse play). Mirrors notebook line 314-315.
* `MAPPING_10_REGIMES_M18_ATR` is the live exit-policy map (the M17 table is kept
  only for parity auditing; they differ on 4 regimes).
* `BOX_SHORT` equality counts as squeezed (`iqr <= baseline`).
* Reference HTML/Colab fallbacks were intentionally dropped: a missing CSV raises
  `CompassEngineError` instead of scraping `dual_semicircle_*.html` or Google Drive.

## 6. Verification evidence

```
$ .venv/bin/python scripts/verify_changes.py \
    app/services/model19/compass_engine.py \
    app/services/model19/setups.py tests/test_model19_compass.py
....................................................................... [100%]
73 passed, 1 skipped in 18.48s
Unit verify — 3 changed file(s)
  · compileall: OK
▶ targeted: tests/test_model19_compass.py
PASS (targeted) in 23.7s
```

The single skip is the numpy/scipy-gated `calc_stats_20d` live-parity arm. It
was **not** left unverified: the same test file was run in a throwaway venv
carrying numpy 2.5.4 + scipy 1.18.1 (scratch, not a project dependency), against
the same frozen reference tree:

```
$ ~/.hermes/profiles/homelab-build/cache/scratch/refenv/bin/python -m pytest \
    tests/test_model19_compass.py -q      # scratch copy, repo app/ + reference/ symlinked
........................................................................ [100%]
74 passed in 1.45s        # zero skips, both arms live
```

Mutation check on an isolated copy of the tree (base = 74 passed), to prove the
new assertions bite:

| mutation | result |
| --- | --- |
| `percentile()` reverted to the single arm | 4 failed (unit pin, live parity arm, golden exact-dict arm, decimal-golden arm) |
| `frac < 0.5` → `frac <= 0.5` (lower arm at exactly t=0.5) | 4 failed (same four) |
| round-2 tree (before the two-branch fix) | 4 failed |

Ad-hoc fuzz used for the fix itself (not committed, scratch probe): 6000 random
windows → `percentile_mismatches=0 dict_mismatches=0`.

```
$ .venv/bin/python scripts/verify_changes.py scripts/verify_changes.py
17 passed in 4.36s ... PASS (targeted)
```

Full suite deliberately not run (Loop rule: one unit = one verify; `--full` only at close).

## 7. Known gaps / follow-ups (not in this card)

* The 10-regime **tactic/exit-policy consumption** (stops, FLIP_CUT, wave
  overrides) belongs to cards 3.2/3.3 — this card only exposes the classifier.
* No wiring into `daily_scenario_runner.py` / pillar-6 yet; card 3.4 (parity
  harness over 2023-2026) is the natural first consumer.
* No commit was made (builder never commits).

## 8. Review hand-off

Round 3 closes the round-2 item: `percentile()` now mirrors NumPy's two-branch
`_lerp` (both arms, `frac >= 0.5` → `b - (b-a)*(1-t)`), so `q25`/`q75`/`iqr` are
bit-identical to `numpy.percentile` for non-binary-exact windows. Parity
evidence was extended so this class of defect cannot hide again:

* the live arm gained 4 decimal drift windows plus a seeded 200-window full-dict
  fuzz (`random.Random(20261028)`, ints / decimals / duplicates / constant /
  negative / 1e6-magnitude, n∈[3,40], both baseline arms), each compared with
  `==` against the ast-extracted frozen reference function;
* the live arm also asserts each decimal window is **non-vacuous** — the round-2
  single-arm oracle must disagree with the reference on `q25` or `q75`;
* the golden fixture gained 5 reference-derived decimal cases (numpy 2.5.4 /
  scipy 1.18.1, never from the port), each carrying `why_non_binary_exact` with
  the 1-ULP value it excludes, plus a new always-on
  `test_golden_has_non_binary_exact_decimal_cases`;
* `test_percentile_reproduces_numpy_two_branch_lerp_exactly` pins the arms by
  exact `==` in the stdlib-only venv (no numpy needed).

Focus areas for re-review: (a) the two arms and the `t >= 0.5` boundary match
NumPy's `_lerp`; (b) the new decimal/fuzz cases genuinely fail against the
round-2 implementation and pass against this one (mutation table in §6);
(c) nothing else moved — the 80-combo × 2646-record compass parity and the 5
scenario goldens are unchanged.

Round 2 closed both items from the round-1 review: `thai_box` now carries the
reference strings (with the table's `box` column split into its own constants),
and `calc_stats_20d` now has real parity evidence — a live arm against the
frozen `plot_comparison_boxplot.py` function plus reference-derived pinned
goldens that run in the stdlib-only venv. That parity work also caught a
1-ULP drift in `percentile_of_score_weak` (see 4b), now fixed and pinned.

