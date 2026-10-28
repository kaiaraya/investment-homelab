"""Model 19 regime engine — 10-Regime matrix over the frozen SQN snapshot.

Source of truth (frozen snapshot, SHA-256 pinned in
``reference/model19/MANIFEST.json``):

* ``reference/model19/mcp_historical_sqn_data.json`` — daily Market SQN
  (``sqn``), 100-day volatility (``volatility_100d``) and
  ``historical_avg_volatility_pct`` (the volatility baseline).
* ``reference/model19/18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py``
  — CELL 3 lines 112-125 (SQN / volatility loading, ``sqn_v3``) and CELL 5
  lines 331-378 (regime matrix + Model 17/18 tactic maps).

What this module owns
---------------------
1. **Series loading with pandas parity.** The reference builds
   ``sqn_map`` / ``sqn_v_map`` / ``vol_100d_map`` with pandas
   (``pd.to_numeric(..., errors='coerce')`` → ``fillna``). This port parses the
   JSON with :mod:`json` and reproduces the same typing and the same fill
   values (``sqn`` → ``1.0``, ``volatility_100d`` → baseline, ``sqn_v3`` →
   ``0.0`` for the first three rows).
2. **The 10-regime label.** ``SQN`` (5 direction buckets) × ``100d volatility``
   (Quiet / Volatile, strictly above the baseline) — the bivariate matrix from
   notebook lines 331-340.
3. **The Model 17 / Model 18-ATR tactic maps** and the per-day regime flags
   (``use_trans_tight`` / ``use_wave_squeeze`` / ``dir_tighten`` /
   ``mini_harvest``, notebook lines 438-441).
4. **Transition tightening** (notebook lines 473-481): the tactic-gated drawdown
   guard that compresses stops/targets on `TRANSITION` days, plus the
   `Neutral Volatile` slot-zero rule and the `is_trans_tight_day` flag that
   drives the break-even trigger / exit clamp / runway in the reference.

Isolation
---------
Analytical only. No ``order_service``, ``trade_dispatcher``, ``quicktrade_*``,
``broker_cdp``, broker-driver, DB or web imports; standard library plus
:mod:`app.services.model19` only (see ``tests/test_model19_regime.py``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Dict, List, Mapping, Optional, Tuple

from app.services.model19.compass_engine import (
    BASELINE_VOL_100D,
    MAPPING_10_REGIMES_M17,
    MAPPING_10_REGIMES_M18_ATR,
    SQN_BEARISH,
    SQN_BULLISH,
    SQN_NEUTRAL,
    SQN_VERY_BULLISH,
    active_tactic,
    classify_regime_10,
)

#: The ten bivariate states, in reference reading order.
REGIME_STATES: Tuple[str, ...] = (
    "Very Bullish Quiet",
    "Very Bullish Volatile",
    "Bullish Quiet",
    "Bullish Volatile",
    "Neutral Quiet",
    "Neutral Volatile",
    "Bearish Quiet",
    "Bearish Volatile",
    "Very Bearish Quiet",
    "Very Bearish Volatile",
)

#: Regimes where a ``TRANSITION`` wave zone forces the tight stop/target pair
#: (notebook line 475).
QUIET_TRANSITION_REGIMES: Tuple[str, ...] = (
    "Neutral Quiet",
    "Bearish Quiet",
    "Very Bearish Quiet",
)

#: Default tactic when a regime has no explicit entry (notebook line 424).
DEFAULT_REGIME_TACTIC: Tuple[str, str] = ("12_V4_Macro", "STANDARD")

#: Tactic whose days are treated as ``transition tight`` (line 438).
TRANSITION_TIGHT_MODELS: Tuple[str, ...] = ("V6_1_TransitionTight", "V6_3_FullUnified")

#: Tactic that arms the squeeze shield (line 439).
WAVE_SQUEEZE_MODELS: Tuple[str, ...] = ("V6_2_WaveSqueezeSpring", "V6_3_FullUnified")

#: Tactics that cover shorts on positive macro momentum (line 440).
DIR_TIGHTEN_MODELS: Tuple[str, ...] = (
    "12_V4_Macro",
    "13_V4_1_Harvest",
    "V6_1_TransitionTight",
    "V6_2_WaveSqueezeSpring",
    "V6_3_FullUnified",
)

#: Tactics that harvest sub-7-day waves early (line 441).
MINI_HARVEST_MODELS: Tuple[str, ...] = ("13_V4_1_Harvest",)

#: pandas ``fillna`` values for the SQN snapshot (notebook lines 119-122).
SQN_FILL_VALUE: float = 1.0
SQN_V3_FILL_VALUE: float = 0.0


class RegimeEngineError(FileNotFoundError):
    """Raised when the frozen SQN snapshot cannot be located or parsed."""


# ───────────────────────────── numeric coercion ─────────────────────────────


def _to_float(value: object) -> Optional[float]:
    """``pd.to_numeric(value, errors='coerce')`` for scalars — ``None`` on junk."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null", "na"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


# ──────────────────────────────── the series ────────────────────────────────


@dataclass(frozen=True)
class RegimeSeries:
    """Daily Market SQN / 100-day volatility series plus its regime labels.

    Built by :func:`load_regime_series` from the frozen
    ``mcp_historical_sqn_data.json``. Dicts are keyed by ``YYYY-MM-DD`` exactly
    as the reference keys its pandas maps (``strftime('%Y-%m-%d')``).
    """

    dates: Tuple[str, ...]
    sqn: Mapping[str, float]
    sqn_v3: Mapping[str, float]
    vol_100d: Mapping[str, float]
    baseline_vol: float = BASELINE_VOL_100D
    source_path: str = ""

    # -- per-day accessors (reference fallbacks) ---------------------------
    def label(self, date_str: str) -> str:
        """Regime label for ``date_str``.

        Notebook line 344: a missing date contributes ``sqn = 0.0`` and the
        baseline volatility → ``'Neutral Quiet'``.
        """
        return classify_regime_10(
            self.sqn.get(date_str, 0.0),
            self.vol_100d.get(date_str, self.baseline_vol),
            self.baseline_vol,
        )

    def regime_map(self) -> Dict[str, str]:
        """``{date: label}`` for every date in the series (notebook lines 331-340)."""
        return {date: self.label(date) for date in self.dates}

    def sqn_at(self, date_str: str, default: float = 0.0) -> float:
        """Market SQN for ``date_str`` (reference default ``0.0``)."""
        return float(self.sqn.get(date_str, default))

    def sqn_v3_at(self, date_str: str) -> float:
        """3-day SQN velocity for ``date_str`` (reference default ``0.0``)."""
        return float(self.sqn_v3.get(date_str, SQN_V3_FILL_VALUE))

    def vol_at(self, date_str: str) -> float:
        """100-day volatility for ``date_str`` (baseline when missing)."""
        return float(self.vol_100d.get(date_str, self.baseline_vol))


def _default_sqn_json(base_dir: Optional[str] = None) -> str:
    """Locate the frozen SQN snapshot — repo ``reference/model19/`` first."""
    candidates: List[str] = []
    if base_dir:
        candidates.extend(
            [
                os.path.join(base_dir, "mcp_historical_sqn_data.json"),
                os.path.join(base_dir, "shared_mcp", "mcp_historical_sqn_data.json"),
                os.path.join(base_dir, "data", "shared_mcp", "mcp_historical_sqn_data.json"),
            ]
        )
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    candidates.append(os.path.join(repo_root, "reference", "model19", "mcp_historical_sqn_data.json"))
    candidates.append(os.path.join(os.getcwd(), "reference", "model19", "mcp_historical_sqn_data.json"))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise RegimeEngineError(
        "[!] FATAL: mcp_historical_sqn_data.json not found. Looked in: " + ", ".join(candidates)
    )


def load_regime_series(
    path: Optional[str] = None, base_dir: Optional[str] = None
) -> RegimeSeries:
    """Load the frozen SQN snapshot into a :class:`RegimeSeries`.

    Pandas parity notes (notebook lines 116-125):

    * rows are sorted by ``date`` before ``shift(3)``, so ``sqn_v3`` is the
      three-trading-day arithmetic mean of the SQN change;
    * ``sqn`` coerces junk/blank to ``1.0``; ``volatility_100d`` coerces junk or
      blank to ``historical_avg_volatility_pct`` (0.855 in the snapshot);
    * a duplicate date keeps the **last** row, matching ``dict(zip(...))``.
    """
    resolved = path or _default_sqn_json(base_dir)
    if not os.path.exists(resolved):
        raise RegimeEngineError(f"[!] FATAL: SQN snapshot not found: {resolved}")

    with open(resolved, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    baseline = _to_float(raw.get("historical_avg_volatility_pct"))
    if baseline is None:
        baseline = BASELINE_VOL_100D

    records: List[Tuple[str, Optional[float], Optional[float]]] = []
    for record in raw.get("records") or []:
        if not isinstance(record, Mapping):
            continue
        date_str = str(record.get("date") or "").strip()
        if not date_str:
            continue
        records.append((date_str, _to_float(record.get("sqn")), _to_float(record.get("volatility_100d"))))
    if not records:
        raise RegimeEngineError(f"[!] FATAL: SQN snapshot has no records: {resolved}")

    records.sort(key=lambda item: item[0])

    dates: List[str] = []
    sqn: Dict[str, float] = {}
    sqn_v3: Dict[str, float] = {}
    vol: Dict[str, float] = {}
    for index, (date_str, sqn_raw, vol_raw) in enumerate(records):
        # dupes keep the last value, like dict(zip(dates, values))
        if date_str not in sqn:
            dates.append(date_str)
        sqn[date_str] = SQN_FILL_VALUE if sqn_raw is None else sqn_raw
        vol[date_str] = baseline if vol_raw is None else vol_raw

    # sqn_v3 = (sqn - sqn.shift(3)) / 3.0, NaN → 0.0  (lines 120, 124)
    for index, date_str in enumerate(dates):
        if index < 3:
            sqn_v3[date_str] = SQN_V3_FILL_VALUE
        else:
            sqn_v3[date_str] = (sqn[date_str] - sqn[dates[index - 3]]) / 3.0

    return RegimeSeries(
        dates=tuple(dates),
        sqn=sqn,
        sqn_v3=sqn_v3,
        vol_100d=vol,
        baseline_vol=baseline,
        source_path=os.path.abspath(resolved),
    )


# ─────────────────────────────── per-day flags ──────────────────────────────


@dataclass(frozen=True)
class RegimeDay:
    """Regime + active tactic + the boolean knobs the backtest branches on."""

    date: str
    regime: str
    model: str
    exit_policy: str
    use_trans_tight: bool
    use_wave_squeeze: bool
    dir_tighten: bool
    mini_harvest: bool
    sqn: float
    sqn_v3: float
    vol_100d: float

    def as_dict(self) -> Dict[str, object]:
        """Reference-shaped dict (``active_tuple`` + flag names from lines 424-441)."""
        return {
            "date": self.date,
            "regime": self.regime,
            "model": self.model,
            "exit_policy": self.exit_policy,
            "use_trans_tight": self.use_trans_tight,
            "use_wave_squeeze": self.use_wave_squeeze,
            "dir_tighten": self.dir_tighten,
            "mini_harvest": self.mini_harvest,
            "sqn": self.sqn,
            "sqn_v3": self.sqn_v3,
            "vol_100d": self.vol_100d,
        }


def assess_regime_day(
    date_str: str,
    regime: str,
    mapping: Optional[Mapping[str, Tuple[str, str]]] = None,
    sqn: float = 0.0,
    sqn_v3: float = 0.0,
    vol_100d: float = BASELINE_VOL_100D,
) -> RegimeDay:
    """Resolve the day's tactic and the derived flags (notebook lines 424-441)."""
    model, exit_policy = active_tactic(regime, mapping or MAPPING_10_REGIMES_M18_ATR)
    return RegimeDay(
        date=date_str,
        regime=regime,
        model=model,
        exit_policy=exit_policy,
        use_trans_tight=model in TRANSITION_TIGHT_MODELS,
        use_wave_squeeze=model in WAVE_SQUEEZE_MODELS,
        dir_tighten=model in DIR_TIGHTEN_MODELS,
        mini_harvest=model in MINI_HARVEST_MODELS,
        sqn=float(sqn),
        sqn_v3=float(sqn_v3),
        vol_100d=float(vol_100d),
    )


class RegimeEngine:
    """Ten-regime classifier bound to one frozen SQN snapshot.

    Usage::

        engine = RegimeEngine()                       # frozen reference/model19/
        day = engine.day("2026-10-08")
        day.regime            # 'Bullish Quiet'
        day.model             # 'V6_1_TransitionTight'
        engine.regime_map()   # full historical label map
    """

    def __init__(
        self,
        series: Optional[RegimeSeries] = None,
        json_path: Optional[str] = None,
        base_dir: Optional[str] = None,
        mapping: Optional[Mapping[str, Tuple[str, str]]] = None,
    ) -> None:
        self.series = series or load_regime_series(json_path, base_dir)
        self.mapping = mapping or MAPPING_10_REGIMES_M18_ATR
        self._regime_map: Optional[Dict[str, str]] = None

    # -- lookups ----------------------------------------------------------
    def regime_map(self) -> Dict[str, str]:
        """``{date: regime}`` — the precomputed ``regime10_map`` (lines 331-340)."""
        if self._regime_map is None:
            self._regime_map = self.series.regime_map()
        return dict(self._regime_map)

    def label(self, date_str: str) -> str:
        """Regime for one date (precomputed first, then recomputed — line 342)."""
        cached = self._regime_map.get(date_str) if self._regime_map is not None else None
        if cached is not None:
            return cached
        return self.series.label(date_str)

    def day(self, date_str: str) -> RegimeDay:
        """Full per-day regime assessment (label + tactic + flags)."""
        return assess_regime_day(
            date_str,
            self.label(date_str),
            mapping=self.mapping,
            sqn=self.series.sqn_at(date_str),
            sqn_v3=self.series.sqn_v3_at(date_str),
            vol_100d=self.series.vol_at(date_str),
        )

    def regime_counts(self) -> Dict[str, int]:
        """``{regime: day count}`` over the whole series."""
        counts: Dict[str, int] = {state: 0 for state in REGIME_STATES}
        for label in self.regime_map().values():
            counts[label] = counts.get(label, 0) + 1
        return counts

    def dates(self) -> Tuple[str, ...]:
        """Every date in the snapshot, ascending."""
        return self.series.dates


# ────────────────────────── transition tightening ───────────────────────────


@dataclass(frozen=True)
class TransitionTightening:
    """Stop/target compression applied on a ``TRANSITION`` wave day.

    Notebook lines 473-481. The reference opens the whole block with
    ``if use_trans_tight:`` (line 474, ``use_trans_tight = active_m in
    ['V6_1_TransitionTight', 'V6_3_FullUnified']``, line 438), so **none** of the
    four rules can fire on a day whose tactic is not transition-tight; that
    outer gate is part of the port, not an optimisation.

    Inside the gate the four rules are evaluated in reference order and the
    **last** matching rule wins for ``sl_mult``/``tp_mult`` (the reference
    overwrites them in place):

    1. ``regime in QUIET_TRANSITION_REGIMES`` *and* ``zone_mode == 'TRANSITION'``
       → ``(0.70, 1.30)``, rule ``quiet_transition``;
    2. ``sqn_crosses_10d >= 2`` *and* ``zone_mode == 'TRANSITION'`` →
       ``(0.70, 1.25)``, rule ``sqn_whipsaw``, ``target_s = 0``;
    3. ``abs(running_peak_delta) >= 500`` *and* ``zone_mode == 'TRANSITION'`` →
       ``(0.65, 1.25)``, rule ``thrust_exhaustion``, ``target_s = 0``,
       ``target_l = min(target_l, 1)``;
    4. ``regime == 'Neutral Volatile'`` (**no** zone-mode gate) →
       rule ``neutral_volatile``, ``target_l = target_s = 0``.

    ``is_trans_tight_day`` is the load-bearing output of this block (reference
    line 474 sets it to ``False`` before the gate and each rule flips it): the
    notebook consumes it for the break-even trigger (``0.65`` vs ``1.0``, line
    508), the exit clamp ``sm = min(sm, 0.70); tm = min(tm, 1.30)`` (line 517),
    RUNWAY 7 vs 10 days (line 543) and the entry slot merge (line 612).
    Note that rule 4 sets the flag **without** changing ``sl_mult``/``tp_mult``
    — which is why ``apply`` (the risk-knob flag) and ``is_trans_tight_day`` are
    separate fields.

    The slot-target side effects are reported as flags (:attr:`zero_short`,
    :attr:`zero_long`, :attr:`long_cap`) and **not** applied here: mutating the
    day's ``target_l``/``target_s`` belongs to the entry/exit sizing cards
    (Card 3.3). Downstream sizing code must apply them, in this order:
    ``if r.zero_long: target_l = 0``; ``if r.long_cap is not None: target_l =
    min(target_l, r.long_cap)``; ``if r.zero_short: target_s = 0``.
    """

    apply: bool
    sl_mult: float
    tp_mult: float
    rule: str
    #: The reference's ``is_trans_tight_day`` — true even for the rule that only
    #: zeroes slot targets (``Neutral Volatile``).
    is_trans_tight_day: bool = False
    #: ``target_s = 0`` was forced by the matched rule (rules 2, 3 and 4).
    zero_short: bool = False
    #: ``target_l = 0`` was forced (rule 4 only).
    zero_long: bool = False
    #: ``target_l = min(target_l, N)`` — ``None`` unless rule 3 matched (N=1).
    long_cap: Optional[int] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "apply": self.apply,
            "sl_mult": self.sl_mult,
            "tp_mult": self.tp_mult,
            "rule": self.rule,
            "is_trans_tight_day": self.is_trans_tight_day,
            "zero_short": self.zero_short,
            "zero_long": self.zero_long,
            "long_cap": self.long_cap,
        }


#: Reference defaults for a non-tight day (notebook line 447).
DEFAULT_SL_MULT: float = 1.0
DEFAULT_TP_MULT: float = 2.0


def transition_tightening(
    regime: str,
    zone_mode: str,
    sqn_crosses_10d: float = 0.0,
    running_peak_delta: float = 0.0,
    sl_mult: float = DEFAULT_SL_MULT,
    tp_mult: float = DEFAULT_TP_MULT,
    model: str = "",
    use_trans_tight: Optional[bool] = None,
) -> TransitionTightening:
    """Tighten stops/targets on a transition-tight day (notebook lines 473-481).

    ``use_trans_tight`` is the reference's outer gate (line 474). Pass either the
    day's tactic as ``model`` (``RegimeDay.model``; membership of
    :data:`TRANSITION_TIGHT_MODELS` decides) or the precomputed flag as
    ``use_trans_tight`` — the explicit flag wins when both are given. The
    ``model`` default (``""``) is *not* transition-tight, so a caller that
    forgets the tactic gets the reference's non-tight behaviour
    (``(1.0, 2.0)``, ``rule='none'``, ``is_trans_tight_day=False``) rather than
    an accidental tightening.

    Inside that gate the four rules are evaluated in reference order with the
    last match winning — see :class:`TransitionTightening` for the table and for
    the slot-target flags (``zero_short`` / ``zero_long`` / ``long_cap``) that
    Card 3.3 applies to ``target_l``/``target_s``.
    """
    if use_trans_tight is None:
        use_trans_tight = model in TRANSITION_TIGHT_MODELS
    if not use_trans_tight:
        return TransitionTightening(False, sl_mult, tp_mult, "none")

    result = TransitionTightening(False, sl_mult, tp_mult, "none")
    if regime in QUIET_TRANSITION_REGIMES and zone_mode == "TRANSITION":
        result = replace(result, apply=True, sl_mult=0.70, tp_mult=1.30, rule="quiet_transition", is_trans_tight_day=True)
    if float(sqn_crosses_10d) >= 2.0 and zone_mode == "TRANSITION":
        result = replace(result, apply=True, sl_mult=0.70, tp_mult=1.25, rule="sqn_whipsaw", is_trans_tight_day=True, zero_short=True)
    if abs(float(running_peak_delta)) >= 500.0 and zone_mode == "TRANSITION":
        result = replace(result, apply=True, sl_mult=0.65, tp_mult=1.25, rule="thrust_exhaustion", is_trans_tight_day=True, zero_short=True, long_cap=1)
    # Line 481: the only rule without a zone-mode gate (still inside the tactic
    # gate); it zeroes both slot targets but leaves the sl/tp pair untouched.
    if regime == "Neutral Volatile":
        result = replace(result, rule="neutral_volatile", is_trans_tight_day=True, zero_short=True, zero_long=True)
    return result


def transition_tightening_for_day(
    day: RegimeDay,
    zone_mode: str,
    sqn_crosses_10d: float = 0.0,
    running_peak_delta: float = 0.0,
    sl_mult: float = DEFAULT_SL_MULT,
    tp_mult: float = DEFAULT_TP_MULT,
) -> TransitionTightening:
    """``transition_tightening`` bound to an assessed :class:`RegimeDay`."""
    return transition_tightening(
        day.regime,
        zone_mode,
        sqn_crosses_10d,
        running_peak_delta,
        sl_mult,
        tp_mult,
        use_trans_tight=day.use_trans_tight,
        model=day.model,
    )


def is_bull_from_sqn(sqn: float, threshold: float = SQN_BULLISH) -> bool:
    """``is_bull`` flag used all over CELL 5 (notebook line 300)."""
    return float(sqn) >= threshold


__all__ = [
    "BASELINE_VOL_100D",
    "DEFAULT_REGIME_TACTIC",
    "DEFAULT_SL_MULT",
    "DEFAULT_TP_MULT",
    "DIR_TIGHTEN_MODELS",
    "MAPPING_10_REGIMES_M17",
    "MAPPING_10_REGIMES_M18_ATR",
    "MINI_HARVEST_MODELS",
    "QUIET_TRANSITION_REGIMES",
    "REGIME_STATES",
    "SQN_BEARISH",
    "SQN_BULLISH",
    "SQN_FILL_VALUE",
    "SQN_NEUTRAL",
    "SQN_V3_FILL_VALUE",
    "SQN_VERY_BULLISH",
    "TRANSITION_TIGHT_MODELS",
    "TransitionTightening",
    "WAVE_SQUEEZE_MODELS",
    "RegimeDay",
    "RegimeEngine",
    "RegimeEngineError",
    "RegimeSeries",
    "active_tactic",
    "assess_regime_day",
    "classify_regime_10",
    "is_bull_from_sqn",
    "load_regime_series",
    "transition_tightening",
    "transition_tightening_for_day",
]
