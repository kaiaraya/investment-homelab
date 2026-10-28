"""Model 19 compass engine & setup scoring — unit + parity tests (Card 3.1).

Coverage
--------
1. ``test_isolation_guard_*`` — the new modules stay analytical (no broker,
   order, dispatcher or live-DB imports).
2. ``test_reference_parity_*`` — my port vs the **frozen reference
   implementation** ``reference/model19/compass_returns_engine.py``, executed
   live (its compute path is pandas-free, so it runs in the project venv).
   Comparison is exact (``==`` on dicts/lists) → zero float drift.
3. ``test_golden_*`` — the same outputs frozen into
   ``tests/fixtures/model19_compass_golden.json`` (score + campaign-mode
   snapshot covering all four modes).
4. Unit tests for the 20-day statistics, breadth gauges, Fear & Greed tier
   derivation, slot defaults, scoring rule and 10-regime classifier.

Golden provenance: the fixture was produced from the frozen reference engine
plus the notebook CELL 4 scoring/mode formulas; the reference file hashes are
embedded in the fixture and re-verified here, so a changed snapshot fails loudly
instead of silently shifting the goldens.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from app.services.model19 import compass_engine as ce
from app.services.model19 import setups as st

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "reference" / "model19"
MASTER_CSV = REFERENCE_DIR / "decision_compass_master_records.csv"
REFERENCE_ENGINE = REFERENCE_DIR / "compass_returns_engine.py"
REFERENCE_PLOT = REFERENCE_DIR / "plot_comparison_boxplot.py"
GOLDEN_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "model19_compass_golden.json"

FAMILIES = ("transition", "pure_trend", "king_trend")
FG_TIERS = ("Fear", "Greed", "Extreme Fear", "Neutral", "Extreme Greed")
Q_LABELS = ("Q1", "Q2", "Q3", "Q4")
BOXES = (st.BOX_SHORT, st.BOX_TALL)
BREADTH_BASELINE = st.BREADTH_MEDIAN_BASELINES["Old_Long"]


# ─────────────────────────────── fixtures ──────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: ``calc_stats_20d`` parity arm needs real numpy/scipy. The project venv is
#: stdlib-only by design (isolation contract), so the arm is expected to SKIP
#: here: a skip means "not verified live in this environment", never "parity ok".
_SKIP_REASON = (
    "calc_stats_20d parity arm unavailable: it must execute the frozen "
    "reference/model19/plot_comparison_boxplot.py:calc_stats_20d, which needs "
    "numpy.percentile + scipy.stats.percentileofscore, and the project venv intentionally "
    "has neither. Installing numpy+scipy arms this comparison; until then the reference-"
    "derived pinned goldens in test_golden_calc_stats_20d_cases_match_port_exactly carry "
    "the parity evidence."
)


def _detect_optional_reference_deps() -> Tuple[bool, bool]:
    try:
        import numpy  # noqa: F401
    except Exception:
        have_np = False
    else:
        have_np = True
    try:
        from scipy import stats  # noqa: F401
    except Exception:
        have_sps = False
    else:
        have_sps = True
    return have_np, have_sps


_HAVE_NUMPY, _HAVE_SCIPY = _detect_optional_reference_deps()


def _reference_calc_stats_20d(np_module, stats_module):
    """Execute ONLY ``calc_stats_20d`` from the frozen plot script.

    That script imports pandas/matplotlib/scipy at module level, so the function
    source is lifted with :mod:`ast` and given just numpy + scipy.stats.
    """
    tree = ast.parse(REFERENCE_PLOT.read_text(encoding="utf-8"))
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "calc_stats_20d"
    )
    namespace: Dict[str, Any] = {"np": np_module, "stats": stats_module}
    exec(
        compile(ast.Module(body=[fn], type_ignores=[]), str(REFERENCE_PLOT), "exec"),
        namespace,
    )
    return namespace["calc_stats_20d"]


def _single_arm_percentile(ordered: Sequence[float], q: float) -> float:
    """The round-2 (defective) single-arm interpolation, kept as a test oracle.

    Used only to prove that the decimal parity windows actually discriminate
    NumPy's two-branch ``_lerp`` — never as an implementation.
    """
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (float(q) / 100.0) * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    if frac == 0.0:
        return float(ordered[low])
    return float(ordered[low]) + frac * (float(ordered[high]) - float(ordered[low]))


def _load_reference_module():
    """Import the frozen reference engine file without invoking its pandas ctor."""
    spec = importlib.util.spec_from_file_location("_model19_reference_engine", REFERENCE_ENGINE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reference_engine():
    """Reference ``DynamicCompassEngine`` instance fed from the frozen CSV."""
    module = _load_reference_module()
    records = ce.load_master_records(str(MASTER_CSV))
    engine = object.__new__(module.DynamicCompassEngine)
    engine.recs_trans = records["transition"]
    engine.recs_pure = records["pure_trend"]
    engine.recs_king = records["king_trend"]
    return engine


@pytest.fixture(scope="module")
def reference_module():
    """The frozen reference module itself (``compute_cell_stat`` lives at module level)."""
    return _load_reference_module()


@pytest.fixture(scope="module")
def port_engine() -> ce.DynamicCompassEngine:
    return ce.DynamicCompassEngine(master_csv_path=str(MASTER_CSV))


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))


def _stats(q_label: str, box_type: str) -> Dict[str, object]:
    return {"q_label": q_label, "box_type": box_type}


def _all_slots(q_label: str, box_type: str) -> Dict[str, Dict[str, object]]:
    return {slot: _stats(q_label, box_type) for slot in st.SETUP_SLOTS}


# ──────────────────────────── 1. isolation guard ───────────────────────────

FORBIDDEN_IMPORT_ROOTS = (
    "app.services.order_service",
    "app.services.trade_dispatcher",
    "app.services.quicktrade",
    "app.services.broker_cdp",
    "app.services.action_exit",
    "app.browser",
    "app.brokers",
    "app.api",
    "app.db",
    "app.core.events",
    "sqlalchemy",
    "fastapi",
    "pandas",
    "numpy",
    "scipy",
)


def _imported_modules(path: Path) -> List[str]:
    """Every module name imported by ``path`` (``import x`` and ``from x import y``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — resolve against the package
                names.append("." * node.level + (node.module or ""))
            elif node.module:
                names.append(node.module)
    return names


@pytest.mark.parametrize(
    "module_path",
    [
        REPO_ROOT / "app/services/model19/setups.py",
        REPO_ROOT / "app/services/model19/compass_engine.py",
    ],
)
def test_isolation_guard_no_broker_order_or_db_imports(module_path: Path):
    offenders = [
        name
        for name in _imported_modules(module_path)
        if any(name == root or name.startswith(root + ".") for root in FORBIDDEN_IMPORT_ROOTS)
    ]
    assert offenders == [], f"{module_path.name} imports forbidden module(s): {offenders}"


def test_isolation_guard_only_stdlib_and_model19():
    allowed_prefixes = ("app.services.model19",)
    stdlib = set(sys.stdlib_module_names)
    for module_path in (
        REPO_ROOT / "app/services/model19/setups.py",
        REPO_ROOT / "app/services/model19/compass_engine.py",
    ):
        for name in _imported_modules(module_path):
            root = name.split(".")[0]
            assert root == "__future__" or root in stdlib or name.startswith(allowed_prefixes), (
                f"{module_path.name} imports non-stdlib module {name!r}"
            )


# ───────────────────────── 2. reference parity (live) ──────────────────────


def test_reference_snapshot_is_the_pinned_one():
    """Guard: parity below is only meaningful against the frozen snapshot."""
    manifest = json.loads((REFERENCE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    entries = manifest.get("files") or manifest.get("artifacts") or manifest
    if isinstance(entries, list):
        entries = {e["file"] if "file" in e else e.get("name"): e for e in entries}
    engine_entry = entries.get("compass_returns_engine.py") if isinstance(entries, dict) else None
    if engine_entry is not None:
        pinned = engine_entry.get("sha256") or engine_entry.get("sha_256")
        if pinned:
            assert _sha256(REFERENCE_ENGINE) == pinned


def test_port_loads_every_family_from_frozen_csv(port_engine):
    assert port_engine.record_counts == {"transition": 882, "pure_trend": 882, "king_trend": 882}
    assert str(MASTER_CSV) == os.path.abspath(port_engine.master_csv_path)
    sample = port_engine.recs_trans[0]
    assert sample["d"] == "2022-12-30"
    assert isinstance(sample["mt"], int) and isinstance(sample["li"], float)
    assert isinstance(sample["lq"], str)


def test_reference_parity_full_calibration_grid(reference_engine, port_engine):
    """81 scenarios x 2646 records: table rows + long/short returns, exact equality."""
    comparisons = 0
    for is_bull in (True, False):
        for fg_tier in FG_TIERS:
            for q_label in Q_LABELS:
                for box_type in BOXES:
                    slot = _stats(q_label, box_type)
                    kwargs = dict(
                        stats_old_l=slot,
                        stats_old_s=slot,
                        stats_new_l=slot,
                        stats_new_s=slot,
                        stats_kt_l=slot,
                        stats_kt_s=slot,
                    )
                    expected_rows, expected_long, expected_short = (
                        reference_engine.compute_all_6_setups(
                            is_bull=is_bull, fg_tier=fg_tier, **kwargs
                        )
                    )
                    rows, long_rets, short_rets = port_engine.compute_all_6_setups(
                        is_bull=is_bull, fg_tier=fg_tier, **kwargs
                    )
                    assert [row.as_dict() for row in rows] == expected_rows
                    assert long_rets == expected_long, (is_bull, fg_tier, q_label, box_type)
                    assert short_rets == expected_short, (is_bull, fg_tier, q_label, box_type)
                    comparisons += 1
    assert comparisons == 2 * len(FG_TIERS) * len(Q_LABELS) * len(BOXES) == 80


def test_reference_parity_default_slots(reference_engine, port_engine):
    """No-stats path: reference falls back to per-slot defaults (Q4/Q1 + box)."""
    rows = []
    for is_bull in (True, False):
        for fg_tier in FG_TIERS:
            expected_rows, expected_long, expected_short = reference_engine.compute_all_6_setups(
                is_bull=is_bull, fg_tier=fg_tier
            )
            rows, long_rets, short_rets = port_engine.compute_all_6_setups(
                is_bull=is_bull, fg_tier=fg_tier
            )
            assert [row.as_dict() for row in rows] == expected_rows
            assert long_rets == expected_long
            assert short_rets == expected_short
    assert [row.q_label for row in rows] == ["Q4", "Q1", "Q1", "Q4", "Q4", "Q1"]
    assert [row.box for row in rows] == ["กล่องยาว", "กล่องสั้น", "กล่องยาว", "กล่องสั้น", "กล่องสั้น", "กล่องสั้น"]


def test_reference_parity_cell_stat_spot_grid(reference_engine, reference_module, port_engine):
    """Per-cell parity (win/ret/days) across fg x q x box x side x market type."""
    records_by_family = {
        "transition": port_engine.recs_trans,
        "pure_trend": port_engine.recs_pure,
        "king_trend": port_engine.recs_king,
    }
    reference_records = {
        "transition": reference_engine.recs_trans,
        "pure_trend": reference_engine.recs_pure,
        "king_trend": reference_engine.recs_king,
    }
    for family in FAMILIES:
        for market_type in ("bull", "non_bull", "all"):
            for fg_tier in FG_TIERS:
                for q_label in Q_LABELS:
                    for is_short_box in (True, False):
                        for side in ("long", "short"):
                            expected = reference_module.compute_cell_stat(
                                reference_records[family], market_type, fg_tier, q_label,
                                is_short_box, side,
                            )
                            actual = ce.compute_cell_stat(
                                records_by_family[family], market_type, fg_tier, q_label,
                                is_short_box, side,
                            )
                            assert actual == expected, (
                                family, market_type, fg_tier, q_label, is_short_box, side
                            )


def test_calc_stats_20d_parity_against_frozen_reference(golden):
    """Live parity: port vs ``plot_comparison_boxplot.calc_stats_20d``, exact dicts.

    This arm SKIPS in the project venv (stdlib-only by design). A skip means the
    live comparison did **not** run — parity then rests on the pinned goldens in
    ``test_golden_calc_stats_20d_cases_match_port_exactly``, which were derived
    from this same reference function with numpy/scipy.
    """
    if not (_HAVE_NUMPY and _HAVE_SCIPY):
        pytest.skip(_SKIP_REASON)

    import numpy as np
    from scipy import stats as sps

    reference_calc = _reference_calc_stats_20d(np, sps)

    # 1. the pinned golden cases, re-derived live from the reference
    for case in golden["calc_stats_20d"]["cases"]:
        expected = reference_calc(case["arr"], case["cur"], case["median_baseline"])
        assert expected == case["expected"], f"golden drifted from reference: {case['name']}"
        assert st.calc_stats_20d(case["arr"], case["cur"], case["median_baseline"]) == expected

    # 2. extra windows not in the fixture: odd/even lengths, float data,
    #    duplicates, cur outside the range, baseline exactly at the IQR
    extra = [
        ([5, 5, 5, 5, 5], 5, 14.8),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], 25, 2.5),
        ([0.5, 1.25, 3.75, 9.0, 12.5, 7.25, 4.5], 4.5, 30.7),
        (list(range(20, -1, -1)), 20, 37.8),
        ([2, 2, 2, 2, 2, 2, 8, 8, 8], 8, None),
    ]
    for arr, cur, baseline in extra:
        assert st.calc_stats_20d(arr, cur, baseline) == reference_calc(arr, cur, baseline), (
            arr,
            cur,
            baseline,
        )

    # 3. non-binary-exact decimal windows. These are the windows that expose
    #    NumPy's two-branch _lerp: every "nice" window above (halves, quarters,
    #    integers) is binary-exact and lands on t values where both lerp arms
    #    agree, so it cannot see a single-arm regression.
    decimal_windows = [
        ([3.67, -2.934029, 0.3], 0.3, 1.0),
        ([-8.671256, 74.1959, 90.377244, 36.11502], 36.11502, None),
        ([76.645563, -88.635486, -61.738774, -91.560221, -80.450945, -9.564815], -9.564815, 20.0),
        (
            [-45.615908, 81.179738, -63.689722, 51.15531, 63.955454, 69.917565, 35.194728,
             89.200312, -18.810434, 7.319778, 2.956524],
            2.956524,
            None,
        ),
    ]
    for arr, cur, baseline in decimal_windows:
        assert st.calc_stats_20d(arr, cur, baseline) == reference_calc(arr, cur, baseline), (
            arr,
            cur,
            baseline,
        )

    # ... and prove those windows are not vacuous: the round-2 single-arm lerp
    # must disagree with the reference on q25 or q75, otherwise the case proves
    # nothing about the two-branch structure.
    for arr, cur, baseline in decimal_windows:
        ordered = sorted(float(v) for v in arr)
        reference_dict = reference_calc(arr, cur, baseline)
        assert (
            _single_arm_percentile(ordered, 25) != reference_dict["q25"]
            or _single_arm_percentile(ordered, 75) != reference_dict["q75"]
        ), f"decimal window does not discriminate: {arr}"

    # 4. seeded fuzz: ~200 random windows, full result dicts compared exactly.
    #    Mixes ints, decimals, duplicates, constant, negative and large-magnitude
    #    data across n in [3, 40], both baseline arms.
    rng = random.Random(20261028)
    kinds = ("int", "float", "dup", "const", "neg", "large")
    compared = 0
    for i in range(200):
        kind = kinds[i % len(kinds)]
        n = rng.randint(3, 40)
        if kind == "int":
            arr = [rng.randint(-50, 50) for _ in range(n)]
        elif kind == "float":
            arr = [rng.uniform(-100.0, 100.0) for _ in range(n)]
        elif kind == "dup":
            pool = [rng.uniform(-20, 20) for _ in range(3)]
            arr = [rng.choice(pool) for _ in range(n)]
        elif kind == "const":
            arr = [rng.uniform(-10, 10)] * n
        elif kind == "neg":
            arr = [-abs(rng.uniform(0.001, 500.0)) for _ in range(n)]
        else:
            arr = [rng.uniform(-1e6, 1e6) for _ in range(n)]
        cur = rng.uniform(-200, 200)
        baseline = rng.choice([None, abs(rng.uniform(0, 50))])
        assert st.calc_stats_20d(arr, cur, baseline) == reference_calc(arr, cur, baseline), (
            kind,
            n,
            arr,
            cur,
            baseline,
        )
        compared += 1
    assert compared == 200


# ───────────────────────────── 3. golden fixture ───────────────────────────


def test_golden_fixture_is_pinned_to_the_frozen_snapshot(golden):
    pinned = golden["generated_from"]
    assert _sha256(REFERENCE_ENGINE) == pinned["compass_returns_engine.py"]["sha256"]
    assert _sha256(MASTER_CSV) == pinned["decision_compass_master_records.csv"]["sha256"]
    assert pinned["decision_compass_master_records.csv"]["rows"] == 2646
    # calc_stats_20d goldens are pinned to the plot script they were derived from
    assert _sha256(REFERENCE_PLOT) == pinned["plot_comparison_boxplot.py"]["sha256"]
    assert "calc_stats_20d" in REFERENCE_PLOT.read_text(encoding="utf-8")


def test_golden_calc_stats_20d_cases_match_port_exactly(golden):
    """Full result dict — every key incl. ``thai_box`` — bit-exact, no approx."""
    cases = golden["calc_stats_20d"]["cases"]
    assert len(cases) >= 12
    seen_box_labels = set()
    for case in cases:
        got = st.calc_stats_20d(case["arr"], case["cur"], case["median_baseline"])
        assert got == case["expected"], case["name"]
        assert list(got) == list(case["expected"]), case["name"]
        if "thai_box" in got:
            seen_box_labels.add(got["thai_box"])
    # both reference thai labels are exercised, in their exact reference spelling
    assert seen_box_labels == {"กล่องสั้น (Squeeze)", "กล่องยาว (Dispersion)"}


def test_golden_has_non_binary_exact_decimal_cases(golden):
    """The fixture must pin NumPy's two-branch lerp, not just binary-exact windows.

    Every decimal case carries ``why_non_binary_exact`` — the single-arm value it
    excludes — so the provenance of what the case protects is auditable, and the
    excluded value is re-derived here rather than trusted.
    """
    cases = golden["calc_stats_20d"]["cases"]
    decimal_cases = [c for c in cases if c["name"].startswith("decimal_")]
    assert len(decimal_cases) >= 4, [c["name"] for c in cases]
    for case in decimal_cases:
        assert "why_non_binary_exact" in case, case["name"]
        ordered = sorted(float(v) for v in case["arr"])
        expected = case["expected"]
        assert (
            _single_arm_percentile(ordered, 25) != expected["q25"]
            or _single_arm_percentile(ordered, 75) != expected["q75"]
        ), case["name"]
        # the port reproduces the reference dict exactly, not the single-arm one
        assert st.calc_stats_20d(case["arr"], case["cur"], case["median_baseline"]) == expected
    # the review's canonical 1-ULP window is among them, pinned literally
    canonical = next(c for c in decimal_cases if c["name"] == "decimal_3d_midpoint_lerp")
    assert canonical["expected"]["q25"] == -1.3170145


def test_golden_scenarios_match_port(port_engine, golden):
    for scenario in golden["scenarios"]:
        slots = scenario["slots"]
        if slots:
            stats = {slot: _stats(slots[slot][0], slots[slot][1]) for slot in st.SETUP_SLOTS}
        else:
            stats = {slot: None for slot in st.SETUP_SLOTS}

        decision = port_engine.compute_decision(
            is_bull=scenario["is_bull"],
            fg_tier=scenario["fg_tier"],
            l_cnt=scenario["l_cnt"],
            s_cnt=scenario["s_cnt"],
            stats_old_l=stats["tl"],
            stats_old_s=stats["ts"],
            stats_new_l=stats["pb"],
            stats_new_s=stats["bear"],
            stats_kt_l=stats["kl"],
            stats_kt_s=stats["ks"],
        )
        expected = scenario["expected"]
        label = scenario["name"]

        assert [float(row.win_norm) for row in decision["table"]] == [
            row["win_norm"] for row in expected["table"]
        ], label
        assert [row.days for row in decision["table"]] == [row["days"] for row in expected["table"]], label
        assert [row.box for row in decision["table"]] == [row["box"] for row in expected["table"]], label
        assert decision["long_rets"] == expected["long_rets"], label
        assert decision["short_rets"] == expected["short_rets"], label
        assert [s.pool_key for s in decision["long_scores"]] == [
            s["pool_key"] for s in expected["long_scores"]
        ], label
        assert [s.score for s in decision["long_scores"]] == [
            s["score"] for s in expected["long_scores"]
        ], label
        assert [s.score for s in decision["short_scores"]] == [
            s["score"] for s in expected["short_scores"]
        ], label
        assert [s.pool_key for s in decision["long_qual"]] == expected["long_qual_keys"], label
        assert [s.pool_key for s in decision["short_qual"]] == expected["short_qual_keys"], label
        assert decision["mode"] == expected["mode"], label
        assert (decision["target_l"], decision["target_s"]) == (
            expected["target_l"],
            expected["target_s"],
        ), label


def test_golden_covers_all_four_campaign_modes(golden):
    assert {scenario["expected"]["mode"] for scenario in golden["scenarios"]} == set(
        st.CAMPAIGN_MODES
    )


# ──────────────────────── 4. statistics unit tests ─────────────────────────


def test_percentile_matches_numpy_linear_interpolation():
    sample = [10, 12, 14, 16, 18, 20]
    assert st.percentile(sample, 0) == 10.0
    assert st.percentile(sample, 100) == 20.0
    assert st.percentile(sample, 25) == pytest.approx(12.5)
    assert st.percentile(sample, 50) == pytest.approx(15.0)
    assert st.percentile(sample, 75) == pytest.approx(17.5)
    assert st.percentile(sample, 10) == pytest.approx(10.0 + 0.5 * 2.0)
    # unsorted input, single element, and odd-length interpolation
    assert st.percentile([5, 1, 3], 50) == 3.0
    assert st.percentile([7], 30) == 7.0
    assert st.percentile([1, 2], 25) == pytest.approx(1.25)


def test_percentile_reproduces_numpy_two_branch_lerp_exactly():
    """NumPy's ``_lerp`` is two-branch; both arms are pinned here bit-exactly.

    These are the decimal drift windows from the Card 3.1 review: the upper arm
    (``t >= 0.5`` → ``b - (b-a)*(1-t)``) yields values the single-arm form
    cannot produce. ``pytest.approx`` is deliberately **not** used — a 1-ULP
    regression must fail.
    """
    # t = 0.5 exactly: numpy 2.5.4 gives -1.3170145, the single arm -1.3170145000000002
    assert st.percentile([3.67, -2.934029, 0.3], 25) == -1.3170145
    assert st.percentile([3.67, -2.934029, 0.3], 75) == 1.9849999999999999
    # q25 of a 4-value float window (upper arm), numpy 2.5.4 == 24.918451
    assert st.percentile([-8.671256, 74.1959, 90.377244, 36.11502], 25) == 24.918451
    # q75 of a 6-value float window (upper arm), numpy 2.5.4 == -22.60830475
    assert (
        st.percentile(
            [76.645563, -88.635486, -61.738774, -91.560221, -80.450945, -9.564815], 75
        )
        == -22.60830475
    )
    # the single-arm value that must NOT be produced (guards against the regression
    # being silently reintroduced by a "simplification" of the two branches)
    assert st.percentile([-8.671256, 74.1959, 90.377244, 36.11502], 25) != 24.918451000000005


def test_median_odd_and_even():
    assert st.median([3, 1, 2]) == 2.0
    assert st.median([4, 1, 3, 2]) == pytest.approx(2.5)


def test_percentile_of_score_weak_is_cumulative_share():
    values = [10, 20, 20, 30]
    assert st.percentile_of_score_weak(values, 5) == 0.0
    assert st.percentile_of_score_weak(values, 20) == pytest.approx(75.0)
    assert st.percentile_of_score_weak(values, 30) == pytest.approx(100.0)


def test_percentile_of_score_weak_reproduces_scipy_reciprocal_order_ulp():
    """``count * (100.0 / n)``, not ``count * 100.0 / n`` — 1-ULP difference at n=11."""
    assert st.percentile_of_score_weak(list(range(1, 12)), 25) == 100.00000000000001
    assert st.percentile_of_score_weak(list(range(1, 12)), 1) == 9.090909090909092
    assert st.percentile_of_score_weak([10, 20, 20, 30], 20) == 75.0


def test_calc_stats_20d_quantile_boundaries():
    # current >= q75 -> Q4, >= median -> Q3, >= q25 -> Q2, else Q1
    sample = [10, 12, 14, 16, 18, 20]  # q25=12.5, median=15, q75=17.5
    assert st.calc_stats_20d(sample, 17.5)["q_label"] == "Q4"
    assert st.calc_stats_20d(sample, 15.0)["q_label"] == "Q3"
    assert st.calc_stats_20d(sample, 12.5)["q_label"] == "Q2"
    assert st.calc_stats_20d(sample, 12.4)["q_label"] == "Q1"
    assert st.calc_stats_20d(sample, 12.5)["zone"] == "Mid-Low / Q2"
    assert st.calc_stats_20d(sample, 20)["zone"] == "Max Zone / Q4"


def test_calc_stats_20d_iqr_and_box_classification():
    tight = st.calc_stats_20d([10, 11, 12, 13, 14, 15], 12.0, median_baseline=2.0)
    assert tight["iqr"] == pytest.approx(2.5)
    assert tight["box_type"] == st.BOX_TALL  # 2.5 > 2.0
    assert tight["thai_box"] == "กล่องยาว (Dispersion)"

    squeezed = st.calc_stats_20d([10, 11, 12, 13, 14, 15], 12.0, median_baseline=2.5)
    assert squeezed["iqr"] == pytest.approx(2.5)
    assert squeezed["box_type"] == st.BOX_SHORT  # equality counts as squeezed
    assert squeezed["thai_box"] == "กล่องสั้น (Squeeze)"

    plain = st.calc_stats_20d([1, 2, 3], 2)
    assert "box_type" not in plain and "thai_box" not in plain


def test_box_label_constants_match_the_reference_strings():
    """Pinned against ``plot_comparison_boxplot.py:116-120`` verbatim.

    Asserted as literals (not constant-vs-constant) so a wrong constant cannot
    quietly redefine the expectation.
    """
    assert st.BOX_SHORT == "Short (Squeeze)"
    assert st.BOX_TALL == "Tall (Dispersion)"
    assert st.BOX_SHORT_TH == "กล่องสั้น (Squeeze)"
    assert st.BOX_TALL_TH == "กล่องยาว (Dispersion)"
    # compass table's `box` column is a different pair by reference design
    assert st.TABLE_BOX_SHORT == "กล่องสั้น"
    assert st.TABLE_BOX_TALL == "กล่องยาว"
    assert st.TABLE_BOX_SHORT != st.BOX_SHORT_TH
    assert st.TABLE_BOX_TALL != st.BOX_TALL_TH


def test_calc_stats_20d_reports_all_fields():
    res = st.calc_stats_20d([1, 2, 3, 4], 2.5, median_baseline=BREADTH_BASELINE)
    assert set(res) == {
        "min", "q25", "median", "q75", "iqr", "max", "latest", "pct",
        "zone", "q_label", "box_type", "thai_box",
    }
    assert res["min"] == 1.0 and res["max"] == 4.0 and res["latest"] == 2.5
    assert res["pct"] == 50.0


# ───────────────────────── breadth / tier unit tests ───────────────────────


def test_breadth_baselines_match_reference():
    assert st.BREADTH_MEDIAN_BASELINES == {
        "Old_Long": 14.8,
        "Old_Short": 15.5,
        "New_Long": 14.5,
        "New_Short": 37.8,
        "King_Trend_Long": 30.7,
        "King_Trend_Short": 14.2,
    }


def test_classify_breadth_counts_notebook_rules():
    rows = [
        {"ema50": "-", "ema200": "-", "trend": "+"},  # Old_Long
        {"ema50": "-", "ema200": "+", "trend": "+"},  # Old_Long (no ema200 condition)
        {"ema50": "+", "ema200": "+", "trend": "+"},  # New_Long
        {"ema50": "+", "ema200": "-", "trend": "-"},  # Old_Short
        {"ema50": "-", "ema200": "-", "trend": "-"},  # New_Short
        {"ema50": " - ", "ema200": " - ", "trend": " - "},  # whitespace tolerated
        {"ema50": "?", "ema200": "?", "trend": "?"},  # unclassified
    ]
    counts = st.classify_breadth_counts(rows)
    assert counts == {
        "Old_Long": 2,
        "Old_Short": 1,
        "New_Long": 1,
        "New_Short": 2,
        "l_cnt": 3,
        "s_cnt": 3,
        "delta": 0,
    }


def test_classify_breadth_counts_delta_sign():
    bullish = st.classify_breadth_counts(
        [{"ema50": "+", "ema200": "+", "trend": "+"}] * 4
    )
    assert (bullish["l_cnt"], bullish["s_cnt"], bullish["delta"]) == (4, 0, 4)
    bearish = st.classify_breadth_counts(
        [{"ema50": "-", "ema200": "-", "trend": "-"}] * 3
    )
    assert bearish["delta"] == -3


@pytest.mark.parametrize(
    "score,expected",
    [
        (80.0, "Extreme Greed"),
        (75.0, "Extreme Greed"),
        (74.9, "Greed"),
        (55.0, "Greed"),
        (54.9, "Neutral"),
        (45.0, "Neutral"),
        (44.9, "Fear"),
        (25.1, "Fear"),
        (25.0, "Extreme Fear"),
        (0.0, "Extreme Fear"),
    ],
)
def test_derive_fg_tier_boundaries(score, expected):
    assert st.derive_fg_tier(score) == expected


# ───────────────────────── slot defaults & scoring ─────────────────────────


def test_slot_defaults_match_reference_fallbacks():
    assert {slot: (d.q_label, d.short_box) for slot, d in st.SETUP_SLOT_DEFAULTS.items()} == {
        "tl": ("Q4", False),
        "ts": ("Q1", True),
        "pb": ("Q1", False),
        "bear": ("Q4", True),
        "kl": ("Q4", True),
        "ks": ("Q1", True),
    }
    assert st.resolve_slot_q("tl", None) == "Q4"
    assert st.resolve_slot_box("tl", None) is False
    stats = {"q_label": "Q2", "box_type": st.BOX_SHORT}
    assert st.resolve_slot_q("pb", stats) == "Q2"
    assert st.resolve_slot_box("pb", stats) is True


def test_score_setups_uses_normal_win_for_even_slots_only():
    rows = [
        {"win_norm": 60.0, "win_inv": 40.0},
        {"win_norm": 55.0, "win_inv": 45.0},
        {"win_norm": 50.0, "win_inv": 50.0},
        {"win_norm": 70.0, "win_inv": 30.0},
        {"win_norm": 80.0, "win_inv": 20.0},
        {"win_norm": 65.0, "win_inv": 35.0},
    ]
    long_rets = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    short_rets = [-2.0, -3.0, -4.0, -5.0, -6.0, -7.0]

    long_scores, short_scores = st.score_setups(rows, long_rets, short_rets)

    # long: 2*60, 3*45, 4*50, 5*30, 6*80, 7*35  (slots 0/2/4 use win_norm)
    assert [s.score for s in long_scores] == [120.0, 135.0, 200.0, 150.0, 480.0, 245.0]
    # short: -2*40, -3*55, -4*50, -5*70, -6*20, -7*65  (complement of the used win rate)
    assert [s.score for s in short_scores] == [-80.0, -165.0, -200.0, -350.0, -120.0, -455.0]
    assert [s.pool_key for s in long_scores] == list(st.SETUP_SLOTS)
    assert [s.pool_key for s in short_scores] == list(st.SHORT_POOL_KEYS)
    assert {s.direction for s in long_scores} == {"LONG"}
    assert {s.direction for s in short_scores} == {"SHORT"}


def test_score_setups_requires_six_slots():
    with pytest.raises(ValueError):
        st.score_setups([{"win_norm": 1, "win_inv": 1}], [1.0], [1.0])


def test_score_setups_rounds_to_two_decimals():
    rows = [{"win_norm": 33.333, "win_inv": 66.667}] * 6
    long_scores, _ = st.score_setups(rows, [1.0] * 6, [-1.0] * 6)
    for score in long_scores:
        assert score.score == round(score.score, 2)


# ────────────────────────── campaign mode matrix ───────────────────────────


def _scores(long_values: Sequence[float], short_values: Sequence[float]):
    long_scores = [
        st.SetupScore(pool_key=slot, direction="LONG", score=v)
        for slot, v in zip(st.SETUP_SLOTS, long_values)
    ]
    short_scores = [
        st.SetupScore(pool_key=key, direction="SHORT", score=v)
        for key, v in zip(st.SHORT_POOL_KEYS, short_values)
    ]
    return long_scores, short_scores


@pytest.mark.parametrize(
    "long_score,short_score,is_bull,l_cnt,s_cnt,expected",
    [
        (150.0, 99.0, True, 10, 10, ("LONG", 4, 0)),
        (150.0, 99.0, False, 10, 10, ("LONG", 4, 0)),
        (99.0, 150.0, True, 10, 10, ("SHORT", 0, 4)),
        (99.0, 150.0, False, 10, 10, ("SHORT", 0, 4)),
        (150.0, 150.0, True, 10, 10, ("LONG", 4, 0)),  # bull + tie on breadth
        (150.0, 150.0, True, 9, 10, ("BI-DIRECTIONAL", 2, 2)),  # bull but breadth short
        (150.0, 150.0, False, 90, 1, ("BI-DIRECTIONAL", 2, 2)),  # not bull
        (99.0, 99.0, True, 10, 10, ("HOLD CASH", 0, 0)),
        (100.0, 100.0, True, 10, 10, ("HOLD CASH", 0, 0)),  # threshold is strict >
        (100.01, 100.0, True, 10, 10, ("LONG", 4, 0)),
    ],
)
def test_select_campaign_mode_matrix(long_score, short_score, is_bull, l_cnt, s_cnt, expected):
    long_scores, short_scores = _scores(
        [long_score] + [0.0] * 5, [short_score] + [0.0] * 5
    )
    decision = st.select_campaign_mode(long_scores, short_scores, is_bull, l_cnt, s_cnt)
    assert (decision.mode, decision.target_l, decision.target_s) == expected


def test_select_campaign_mode_reports_qualifiers():
    long_scores, short_scores = _scores([150.0, 120.0, 0.0, 0.0, 0.0, 0.0], [0.0] * 6)
    decision = st.select_campaign_mode(long_scores, short_scores, True, 5, 1)
    assert [s.pool_key for s in decision.long_qual] == ["tl", "ts"]
    assert decision.short_qual == []


# ─────────────────────────── 10-regime classifier ──────────────────────────


@pytest.mark.parametrize(
    "sqn,expected_direction",
    [
        (2.10, "Very Bullish"),
        (1.48, "Very Bullish"),
        (1.47, "Bullish"),
        (0.75, "Bullish"),
        (0.74, "Neutral"),
        (0.00, "Neutral"),
        (-0.01, "Bearish"),
        (-0.70, "Bearish"),
        (-0.71, "Very Bearish"),
    ],
)
def test_classify_regime_10_sqn_axis(sqn, expected_direction):
    assert ce.classify_regime_10(sqn, 0.50) == f"{expected_direction} Quiet"


@pytest.mark.parametrize(
    "vol,expected",
    [(0.855, "Quiet"), (0.856, "Volatile"), (0.10, "Quiet"), (2.5, "Volatile")],
)
def test_classify_regime_10_volatility_axis(vol, expected):
    assert ce.classify_regime_10(1.0, vol) == f"Bullish {expected}"


def test_classify_regime_10_defaults_to_baseline_volatility():
    assert ce.classify_regime_10(1.0) == "Bullish Quiet"
    assert ce.BASELINE_VOL_100D == 0.855


def test_regime_mapping_tables_cover_all_ten_states():
    expected_states = {
        f"{direction} {vol}"
        for direction in ("Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish")
        for vol in ("Quiet", "Volatile")
    }
    assert set(ce.MAPPING_10_REGIMES_M18_ATR) == expected_states
    assert set(ce.MAPPING_10_REGIMES_M17) == expected_states
    assert ce.MAPPING_10_REGIMES_M18_ATR["Bullish Volatile"] == ("V6_2_WaveSqueezeSpring", "FLIP_CUT")
    assert ce.MAPPING_10_REGIMES_M18_ATR["Very Bearish Volatile"] == ("12_V4_Macro", "FLIP_CUT")


def test_get_10_regime_prefers_precomputed_map():
    regime_map = {"2026-10-27": "Very Bullish Volatile"}
    assert ce.get_10_regime("2026-10-27", {"sqn": 0.1}, regime_map, {}, ce.BASELINE_VOL_100D) == (
        "Very Bullish Volatile"
    )
    assert ce.get_10_regime(
        "2026-10-28", {"sqn": 1.60}, None, {"2026-10-28": 0.90}, ce.BASELINE_VOL_100D
    ) == "Very Bullish Volatile"
    # unknown date -> baseline volatility, sqn from decision
    assert ce.get_10_regime("2026-10-29", {"sqn": -0.2}) == "Bearish Quiet"
    assert ce.get_10_regime("2026-10-29") == "Neutral Quiet"


def test_active_tactic_defaults_and_fallback():
    assert ce.active_tactic("Very Bullish Volatile") == ("V6_3_FullUnified", "FLIP_CUT")
    assert ce.active_tactic("Unknown Regime") == ("12_V4_Macro", "STANDARD")


# ─────────────────────────── engine edge cases ─────────────────────────────


def test_compute_cell_stat_neutral_when_no_records():
    assert ce.compute_cell_stat(None) == {"days": 0, "win": 50.0, "ret": 0.0}
    assert ce.compute_cell_stat([]) == {"days": 0, "win": 50.0, "ret": 0.0}


def test_compute_cell_stat_empty_box_arm_falls_back_to_quantile_cell():
    records = [
        {"mt": 1, "fg": "Greed", "lq": "Q4", "li": 40.0, "lp": 1, "la": 5.0, "sq": "Q1", "si": 10.0, "sp": 0, "sa": -2.0},
        {"mt": 1, "fg": "Greed", "lq": "Q4", "li": 50.0, "lp": 0, "la": -1.0, "sq": "Q1", "si": 20.0, "sp": 1, "sa": 3.0},
    ]
    # median li = 45.0 -> tall-box arm (li > 45) keeps one row, short-box keeps one row
    short_box = ce.compute_cell_stat(records, "bull", "Greed", "Q4", True, "long")
    tall_box = ce.compute_cell_stat(records, "bull", "Greed", "Q4", False, "long")
    assert short_box == {"days": 1, "win": 100.0, "ret": 5.0}
    assert tall_box == {"days": 1, "win": 0.0, "ret": -1.0}
    # a quantile cell with no records at all -> neutral
    assert ce.compute_cell_stat(records, "bull", "Fear", "Q4", True, "long") == {
        "days": 0,
        "win": 50.0,
        "ret": 0.0,
    }


def test_engine_raises_when_csv_missing(tmp_path):
    with pytest.raises(ce.CompassEngineError):
        ce.DynamicCompassEngine(master_csv_path=str(tmp_path / "nope.csv"))


def test_engine_default_locator_finds_frozen_snapshot():
    engine = ce.DynamicCompassEngine()
    assert Path(engine.master_csv_path).resolve() == MASTER_CSV.resolve()


def test_engine_source_reports_csv_provenance(port_engine):
    assert "decision_compass_master_records.csv" in port_engine.source
    assert port_engine.source.startswith("CSV: ")


def test_load_master_records_types_and_order():
    records = ce.load_master_records(str(MASTER_CSV))
    assert set(records) >= set(FAMILIES)
    first = records["transition"][0]
    assert first == {
        "d": "2022-12-30",
        "y": 2023,
        "sqn": 0.97,
        "mt": 1,
        "fg": "Greed",
        "sc": 56,
        "lq": "Q4",
        "li": 43.0,
        "lp": 1,
        "la": 3.91,
        "sq": "Q1",
        "si": 27.5,
        "sp": 0,
        "sa": -3.5,
        "setup_family": "transition",
    }
