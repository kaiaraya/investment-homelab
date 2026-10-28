"""Model 19 setup scoring primitives — pure stdlib port.

Source of truth (frozen snapshot, SHA-256 pinned in
``reference/model19/MANIFEST.json``):

* ``reference/model19/plot_comparison_boxplot.py:calc_stats_20d``  → :func:`calc_stats_20d`
* ``reference/model19/18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py``
  - CELL 3 ``Breadth Classification``  (lines 204-208) → :func:`classify_breadth_counts`
  - CELL 4 ``l_setups`` / ``s_setups`` scoring (lines 312-316) → :func:`score_setups`
  - CELL 4 ``mode`` selection (lines 318-323)          → :func:`select_campaign_mode`
  - lines 303-304 ``fg_tier`` derivation               → :func:`derive_fg_tier`
* ``reference/model19/compass_returns_engine.py:compute_all_6_setups`` slot
  defaults → :data:`SETUP_SLOT_DEFAULTS`

Parity rules honoured here (no float drift):
* percentile = NumPy default ``linear`` interpolation over the *sorted* sample;
* median = mean of the two central order statistics for even-length samples;
* ``percentileofscore(kind='weak')`` = ``count(x <= score) * (100.0 / n)`` — the
  reciprocal-first order, which is what makes it ULP-identical to scipy;
* per-cell win/return = ``sum(col) / days`` in CSV record order, win scaled by
  ``* 100.0`` exactly as the reference (*not* ``100.0 * x / n``).

The module deliberately imports nothing beyond the standard library — see the
isolation contract in :mod:`app.services.model19`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

# ─────────────────────────────── constants ────────────────────────────────

#: ``median_baseline`` per breadth gauge (notebook CELL 4 lines 293-298).
BREADTH_MEDIAN_BASELINES: Dict[str, float] = {
    "Old_Long": 14.8,
    "Old_Short": 15.5,
    "New_Long": 14.5,
    "New_Short": 37.8,
    "King_Trend_Long": 30.7,
    "King_Trend_Short": 14.2,
}

#: IQR classification labels (``calc_stats_20d`` / ``plot_comparison_boxplot``).
BOX_SHORT: str = "Short (Squeeze)"
BOX_TALL: str = "Tall (Dispersion)"
#: Thai ``thai_box`` labels emitted by ``calc_stats_20d`` — byte-for-byte the
#: reference strings (``plot_comparison_boxplot.py:119-120``). Do NOT reuse these
#: for the compass table's ``box`` column: that one is a *different* string pair
#: coming from ``compute_all_6_setups`` (see :data:`TABLE_BOX_SHORT`).
BOX_SHORT_TH: str = "กล่องสั้น (Squeeze)"
BOX_TALL_TH: str = "กล่องยาว (Dispersion)"

#: Compass-table ``box`` column values (``compass_returns_engine.compute_all_6_setups``).
#: Distinct from the ``thai_box`` labels above by design — the reference emits the
#: bare Thai words here and the suffixed words in :func:`calc_stats_20d`.
TABLE_BOX_SHORT: str = "กล่องสั้น"
TABLE_BOX_TALL: str = "กล่องยาว"

#: Quantile labels produced by :func:`calc_stats_20d`.
Q_LABELS: Tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4")

#: Campaign modes emitted by :func:`select_campaign_mode`.
CAMPAIGN_MODES: Tuple[str, ...] = ("LONG", "SHORT", "BI-DIRECTIONAL", "HOLD CASH")

#: Qualifying threshold — a setup only trades when ``score > 100.0``.
SCORE_THRESHOLD: float = 100.0

#: The six compass slots, in reference table order.
SETUP_SLOTS: Tuple[str, ...] = ("tl", "ts", "pb", "bear", "kl", "ks")

#: Short-pool analogue of each long slot (notebook CELL 4 line 313).
SHORT_POOL_KEYS: Tuple[str, ...] = (
    "tb",
    "ts_short",
    "pb_breakdown",
    "bear_short",
    "kl_breakdown",
    "ks_short",
)


@dataclass(frozen=True)
class SetupSlotDefault:
    """Fallback quantile / box used when the caller has no 20d stats.

    Mirrors ``compute_all_6_setups``' ``... if stats_x else '<default>'`` arms.
    """

    q_label: str
    short_box: bool


#: Slot → default when the corresponding ``stats_*`` argument is ``None``.
SETUP_SLOT_DEFAULTS: Dict[str, SetupSlotDefault] = {
    "tl": SetupSlotDefault("Q4", False),
    "ts": SetupSlotDefault("Q1", True),
    "pb": SetupSlotDefault("Q1", False),
    "bear": SetupSlotDefault("Q4", True),
    "kl": SetupSlotDefault("Q4", True),
    "ks": SetupSlotDefault("Q1", True),
}

#: Long slots whose qualifying score uses the *normal* win rate (indices 0/2/4).
NORMAL_WIN_SLOT_INDEXES: Tuple[int, ...] = (0, 2, 4)


# ─────────────────────────────── statistics ───────────────────────────────


def percentile(values: Sequence[float], q: float) -> float:
    """NumPy-exact percentile (``method='linear'``) for a small sample.

    Reproduces NumPy's ``_lerp`` **branch structure**, not just its formula.
    NumPy interpolates with two arms chosen by the fractional index
    ``t`` (``numpy/lib/_function_base_impl.py::_lerp``)::

        t <  0.5  ->  a + (b - a) * t
        t >= 0.5  ->  b - (b - a) * (1 - t)

    The two arms are algebraically identical but **not** bit-identical in IEEE
    754: e.g. ``a=-2.934029, b=0.3, t=0.25`` gives ``-1.3170145000000002`` from
    the first arm and ``-1.3170145`` from a naive ``a + (b-a)*t`` refactor of the
    second. Using a single arm therefore drifts ``q25``/``q75``/``iqr`` by 1 ULP
    against ``numpy.percentile`` for non-binary-exact windows, which is what the
    frozen reference computes.

    The index is ``pos = (q / 100) * (n - 1)`` — the same order of operations as
    NumPy, which also computes ``(q/100)`` first.
    """
    if not values:
        raise ValueError("percentile() of empty sequence")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (float(q) / 100.0) * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    if frac == 0.0:
        return ordered[low]
    a = ordered[low]
    b = ordered[high]
    if frac < 0.5:
        return a + (b - a) * frac
    return b - (b - a) * (1.0 - frac)


def median(values: Sequence[float]) -> float:
    """Median of ``values`` (mean of the two central values when even-length)."""
    if not values:
        raise ValueError("median() of empty sequence")
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile_of_score_weak(values: Sequence[float], score: float) -> float:
    """``scipy.stats.percentileofscore(kind='weak')`` — share of ``x <= score``.

    Bit-exact with scipy, which computes ``count * (100.0 / n)``: multiplying by
    the reciprocal first is **not** ULP-identical to ``count * 100.0 / n``
    (e.g. n=11, count=11 → ``100.00000000000001`` vs ``100.0``).
    """
    if not values:
        raise ValueError("percentile_of_score_weak() of empty sequence")
    count = sum(1 for v in values if float(v) <= float(score))
    return count * (100.0 / len(values))


def calc_stats_20d(
    arr: Sequence[float],
    cur: float,
    median_baseline: Optional[float] = None,
) -> Dict[str, object]:
    """20-day rolling box statistics + quantile zone label.

    Byte-for-byte port of ``plot_comparison_boxplot.py:calc_stats_20d``.

    Returns a dict with ``min, q25, median, q75, iqr, max, latest, pct, zone,
    q_label`` and — when ``median_baseline`` is given — ``box_type`` and
    ``thai_box``. ``box_type == BOX_SHORT`` means a squeezed box (IQR at or
    below the historical baseline), which selects the "short box" arm of the
    compass cell.
    """
    if not arr:
        raise ValueError("calc_stats_20d() of empty window")
    q25 = percentile(arr, 25)
    med = median(arr)
    q75 = percentile(arr, 75)
    iqr = q75 - q25
    min_v = float(min(arr))
    max_v = float(max(arr))
    pct = percentile_of_score_weak(arr, cur)

    if cur >= q75:
        zone = "Max Zone / Q4"
        q_label = "Q4"
    elif cur >= med:
        zone = "Mid-High / Q3"
        q_label = "Q3"
    elif cur >= q25:
        zone = "Mid-Low / Q2"
        q_label = "Q2"
    else:
        zone = "Low Zone / Q1"
        q_label = "Q1"

    res: Dict[str, object] = {
        "min": min_v,
        "q25": q25,
        "median": med,
        "q75": q75,
        "iqr": iqr,
        "max": max_v,
        "latest": float(cur),
        "pct": pct,
        "zone": zone,
        "q_label": q_label,
    }
    if median_baseline is not None:
        squeezed = iqr <= float(median_baseline)
        res["box_type"] = BOX_SHORT if squeezed else BOX_TALL
        res["thai_box"] = BOX_SHORT_TH if squeezed else BOX_TALL_TH
    return res


# ────────────────────────────── breadth gauges ─────────────────────────────


def classify_breadth_counts(rows: Iterable[Mapping[str, str]]) -> Dict[str, int]:
    """Breadth participation counts for one day of the candidate pool.

    ``rows`` are candidate rows carrying the momentum flags ``ema50``,
    ``ema200`` and ``trend`` (values ``'+'`` / ``'-'``, whitespace tolerated).

    Notebook CELL 3 (lines 204-208):
      * ``Old_Long``  = ema50 '-' & trend '+'
      * ``New_Long``  = ema50 '+' & ema200 '+' & trend '+'
      * ``Old_Short`` = ema50 '+' & trend '-'
      * ``New_Short`` = ema50 '-' & ema200 '-' & trend '-'
      * ``l_cnt`` = Old_Long + New_Long, ``s_cnt`` = Old_Short + New_Short
      * ``delta`` = l_cnt - s_cnt
    """
    old_long = new_long = old_short = new_short = 0
    for row in rows:
        ema50 = str(row.get("ema50", "")).strip()
        ema200 = str(row.get("ema200", "")).strip()
        trend = str(row.get("trend", "")).strip()
        if ema50 == "-" and trend == "+":
            old_long += 1
        if ema50 == "+" and ema200 == "+" and trend == "+":
            new_long += 1
        if ema50 == "+" and trend == "-":
            old_short += 1
        if ema50 == "-" and ema200 == "-" and trend == "-":
            new_short += 1
    l_cnt = old_long + new_long
    s_cnt = old_short + new_short
    return {
        "Old_Long": old_long,
        "Old_Short": old_short,
        "New_Long": new_long,
        "New_Short": new_short,
        "l_cnt": l_cnt,
        "s_cnt": s_cnt,
        "delta": l_cnt - s_cnt,
    }


def derive_fg_tier(fg_score: float) -> str:
    """Fallback Fear & Greed tier when the daily CSV has no tier string.

    Notebook CELL 4 lines 303-304: ``>= 75 Extreme Greed``, ``>= 55 Greed``,
    ``>= 45 Neutral``, ``<= 25 Extreme Fear``, everything else ``Fear``.
    """
    score = float(fg_score)
    if score >= 75:
        return "Extreme Greed"
    if score >= 55:
        return "Greed"
    if score >= 45:
        return "Neutral"
    if score <= 25:
        return "Extreme Fear"
    return "Fear"


# ──────────────────────────── slot resolution ──────────────────────────────


def resolve_slot_q(slot: str, stats: Optional[Mapping[str, object]]) -> str:
    """Quantile label for ``slot`` — stats value, else the reference default."""
    if stats:
        return str(stats["q_label"])
    return SETUP_SLOT_DEFAULTS[slot].q_label


def resolve_slot_box(slot: str, stats: Optional[Mapping[str, object]]) -> bool:
    """True when ``slot`` sits in the "short (squeeze)" box of its gauge."""
    if stats:
        return stats.get("box_type") == BOX_SHORT
    return SETUP_SLOT_DEFAULTS[slot].short_box


# ──────────────────────────── scoring & modes ──────────────────────────────


@dataclass(frozen=True)
class SetupScore:
    """One scored setup row from the compass (long or short side)."""

    pool_key: str
    direction: str  # 'LONG' | 'SHORT'
    score: float


@dataclass
class CampaignDecision:
    """Daily campaign decision produced by the compass engine."""

    mode: str
    target_l: int
    target_s: int
    long_qual: List[SetupScore] = field(default_factory=list)
    short_qual: List[SetupScore] = field(default_factory=list)


def _slot_win_rate(index: int, row: Mapping[str, object]) -> float:
    """Win rate used for slot ``index``: normal for 0/2/4, inverse otherwise."""
    if index in NORMAL_WIN_SLOT_INDEXES:
        return float(cast(float, row["win_norm"]))
    return float(cast(float, row["win_inv"]))


def score_setups(
    table_rows: Sequence[Mapping[str, object]],
    long_rets: Sequence[float],
    short_rets: Sequence[float],
) -> Tuple[List[SetupScore], List[SetupScore]]:
    """Score all six long and six short setups.

    Notebook CELL 4 lines 314-315::

        l.score = round(long_ret[i] * win_rate(i), 2)
        s.score = round(short_ret[i] * (100.0 - win_rate(i)), 2)

    ``win_rate(i)`` is ``win_norm`` for slots 0/2/4 and ``win_inv`` (the
    inverse-play probability) for slots 1/3/5.
    """
    if not (len(table_rows) == len(long_rets) == len(short_rets) == len(SETUP_SLOTS)):
        raise ValueError("score_setups() expects 6 rows / 6 long_rets / 6 short_rets")

    long_scores: List[SetupScore] = []
    short_scores: List[SetupScore] = []
    for i, slot in enumerate(SETUP_SLOTS):
        win = _slot_win_rate(i, table_rows[i])
        long_scores.append(
            SetupScore(
                pool_key=slot,
                direction="LONG",
                score=round(float(long_rets[i]) * win, 2),
            )
        )
        short_scores.append(
            SetupScore(
                pool_key=SHORT_POOL_KEYS[i],
                direction="SHORT",
                score=round(float(short_rets[i]) * (100.0 - win), 2),
            )
        )
    return long_scores, short_scores


def select_campaign_mode(
    long_scores: Sequence[SetupScore],
    short_scores: Sequence[SetupScore],
    is_bull: bool,
    l_cnt: int,
    s_cnt: int,
) -> CampaignDecision:
    """Qualifying → campaign mode / slot targets (notebook CELL 4 lines 316-323)."""
    l_qual = [s for s in long_scores if s.score > SCORE_THRESHOLD]
    s_qual = [s for s in short_scores if s.score > SCORE_THRESHOLD]

    if l_qual and not s_qual:
        mode, target_l, target_s = "LONG", 4, 0
    elif not l_qual and s_qual:
        mode, target_l, target_s = "SHORT", 0, 4
    elif l_qual and s_qual:
        if is_bull and (l_cnt >= s_cnt):
            mode, target_l, target_s = "LONG", 4, 0
        else:
            mode, target_l, target_s = "BI-DIRECTIONAL", 2, 2
    else:
        mode, target_l, target_s = "HOLD CASH", 0, 0

    return CampaignDecision(
        mode=mode,
        target_l=target_l,
        target_s=target_s,
        long_qual=l_qual,
        short_qual=s_qual,
    )
