"""Model 19 wave-thrust & wave-forensics engine (Kinematic Wave Zones).

Source of truth (frozen snapshot, SHA-256 pinned in
``reference/model19/MANIFEST.json``):

* ``reference/model19/kinematic_wave_zones_daily.csv`` — daily wave zone:
  ``wave_context`` (``BULL_WAVE`` / ``BEAR_WAVE``), long/short breadth counts,
  ``net_delta``, ``kinematic_state``, ``zone_mode`` (``AGGRESSIVE_LONG`` /
  ``AGGRESSIVE_SHORT`` / ``TRANSITION`` / ``DEFENSIVE``), ``zone_sub_type``,
  ``fear_greed`` and ``market_sqn``.
* ``reference/model19/wave_forensics_context_daily.csv`` — wave forensics:
  ``direction`` / ``sign`` / ``wave_id`` / ``running_wave_dur`` /
  ``running_peak_delta`` / ``prev_same_peak`` / ``prev_opp_peak`` / ...
* ``reference/model19/18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py``
  — CELL 4 lines 282-290 (point-in-time wave thrust from the breadth delta
  series) and CELL 5 lines 380-388, 411-422, 443-445, 483-492 (forensics
  derived columns + squeeze shield).

What this module owns
---------------------
1. **Wave thrust** — ``days_in_wave`` (length of the current same-sign run of
   the breadth delta series) and ``delta_prog`` (``abs(delta_last -
   delta_first)`` over that run). This is the point-in-time wave engine of
   notebook lines 284-290, re-implemented with the exact pandas semantics
   (``np.sign(...).replace(0, nan).ffill().fillna(1)`` → ``cumsum`` of sign
   changes → current run slice).
2. **Kinematic zone context** — typed ``ZoneContext`` records with the
   reference defaults (``zone_mode='DEFENSIVE'``, ``wave_context='BULL_WAVE'``).
3. **Wave forensics** — typed records **including the four derived columns the
   reference computes at load time** (``above_075``, ``cross_075``,
   ``sqn_crosses_10d``, ``sqn_vel_5d``; notebook lines 384-387), reproduced
   with pandas ``rolling(10, min_periods=1).sum()`` / ``diff(5).fillna(0)``
   semantics.
4. **Short-squeeze shield detection** — the three Wave-Forensics triggers of
   notebook lines 483-492, returned as a named alert so the exit layer can
   cover shorts without re-deriving the conditions.

Blanks stay blanks
------------------
Where the reference does ``float(wf_day.get(col, 0.0) or 0.0)`` on a blank
pandas cell, the result is ``nan`` (a blank cell is ``nan``, and ``nan`` is
truthy) — never ``0.0``. :func:`forensics_day` reproduces that exactly, because
downstream threshold comparisons depend on ``nan`` comparing ``False``.

Isolation
---------
Analytical only. Standard library plus :mod:`app.services.model19` only; no
``order_service``, ``trade_dispatcher``, ``quicktrade_*``, ``broker_cdp``,
broker-driver, DB or web imports (see ``tests/test_model19_regime.py``).
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, replace
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

#: Zone modes emitted by the Kinematic Wave Zones engine (notebook lines 448-455).
ZONE_MODES: Tuple[str, ...] = (
    "AGGRESSIVE_LONG",
    "AGGRESSIVE_SHORT",
    "TRANSITION",
    "DEFENSIVE",
)

#: Wave contexts (notebook lines 445-455).
WAVE_CONTEXTS: Tuple[str, ...] = ("BULL_WAVE", "BEAR_WAVE")

#: Reference fallbacks when a date has no wave-thrust entry (notebook line 413).
DEFAULT_DAYS_IN_WAVE: int = 10
DEFAULT_DELTA_PROG: float = 200.0

#: Reference fallbacks when a date has no zone entry (notebook lines 444-445).
DEFAULT_ZONE_MODE: str = "DEFENSIVE"
DEFAULT_WAVE_CONTEXT: str = "BULL_WAVE"

#: Reference fallbacks when a date has no forensics entry (notebook lines 416-422).
DEFAULT_FORENSICS_DIRECTION: str = "LONG"
DEFAULT_RUNNING_WAVE_DUR: int = 1

#: SQN bull-line used for the forensics crossover features (notebook line 384).
FORENSICS_SQN_LINE: float = 0.75

#: Squeeze-shield thresholds (notebook lines 485-492).
SQUEEZE_OPP_PEAK_MIN: float = 500.0
SQUEEZE_RUN_PEAK_RATIO: float = 0.65
SQUEEZE_SQN_MIN: float = 0.70
SQUEEZE_TRANSITION_SQN_VEL5: float = 0.15
SQUEEZE_TRANSITION_SQN_V3: float = 0.12
SQUEEZE_TRANSITION_SQN_MIN: float = 0.80
SQUEEZE_SAME_PEAK_MIN: float = 400.0
SQUEEZE_SAME_PEAK_RATIO: float = 0.30
SQUEEZE_SAME_SQN_MIN: float = 1.10


class WaveThrustError(FileNotFoundError):
    """Raised when a frozen wave CSV cannot be located."""


def _nan() -> float:
    return float("nan")


def _to_float(value: object) -> Optional[float]:
    """``pd.to_numeric(value, errors='coerce')`` for scalars — ``None`` on blanks/junk."""
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


def _to_int(value: object) -> Optional[int]:
    parsed = _to_float(value)
    return None if parsed is None else int(parsed)


def _to_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


# ══════════════════════════════ 1. wave thrust ══════════════════════════════


@dataclass(frozen=True)
class WaveThrustPoint:
    """Point-in-time thrust of the current breadth wave (notebook line 290)."""

    date: str
    days_in_wave: int
    delta_prog: float
    sign: int
    delta: float

    def as_dict(self) -> Dict[str, object]:
        """Reference ``wave_thrust_map`` entry shape (``days_in_wave``/``delta_prog``)."""
        return {"days_in_wave": self.days_in_wave, "delta_prog": self.delta_prog}


def compute_wave_thrust(
    deltas: Sequence[Tuple[str, float]],
) -> Dict[str, WaveThrustPoint]:
    """Point-in-time wave thrust for every date of a breadth-delta series.

    Notebook CELL 4 lines 284-290, per date, in pandas terms::

        sub       = breadth[:i+1]
        sign      = np.sign(delta).replace(0, nan).ffill().fillna(1)
        wave_id   = (sign != sign.shift(1)).cumsum()
        cur       = sub[wave_id == wave_id.iloc[-1]]        # current run
        days      = len(cur)
        delta_prog= abs(cur.delta.iloc[-1] - cur.delta.iloc[0])

    A zero delta inherits the previous sign; a series that starts at zero is
    treated as ``+1``. ``deltas`` must be time-ordered; duplicates keep the last
    value (the reference indexes by date).
    """
    ordered: List[Tuple[str, float]] = []
    seen: Dict[str, int] = {}
    for date_str, value in deltas:
        key = str(date_str)
        numeric = float(value)
        if key in seen:
            ordered[seen[key]] = (key, numeric)
        else:
            seen[key] = len(ordered)
            ordered.append((key, numeric))
    if not ordered:
        return {}

    thrust: Dict[str, WaveThrustPoint] = {}
    run_start = 0
    run_sign = 0
    for index, (date_str, delta) in enumerate(ordered):
        if delta > 0:
            sign = 1
        elif delta < 0:
            sign = -1
        else:
            # .replace(0, nan).ffill().fillna(1)
            sign = run_sign if index > 0 else 1
        if index == 0 or sign != run_sign:
            run_start = index
        run_sign = sign
        first_delta = ordered[run_start][1]
        thrust[date_str] = WaveThrustPoint(
            date=date_str,
            days_in_wave=index - run_start + 1,
            delta_prog=abs(delta - first_delta),
            sign=sign,
            delta=delta,
        )
    return thrust


def wave_thrust_day(
    thrust_map: Mapping[str, WaveThrustPoint], date_str: str
) -> WaveThrustPoint:
    """Thrust for ``date_str`` with the reference fallbacks (line 413).

    A missing date yields ``days_in_wave = 10`` and ``delta_prog = 200.0`` — the
    notebook's ``.get(d_str, {})`` + ``.get(key, default)`` pair.
    """
    point = thrust_map.get(date_str)
    if point is None:
        return WaveThrustPoint(
            date=date_str,
            days_in_wave=DEFAULT_DAYS_IN_WAVE,
            delta_prog=DEFAULT_DELTA_PROG,
            sign=0,
            delta=_nan(),
        )
    return point


# ═══════════════════════ 2. kinematic wave zone context ═════════════════════


@dataclass(frozen=True)
class ZoneContext:
    """One row of ``kinematic_wave_zones_daily.csv``."""

    date: str
    wave_context: str
    long_count: Optional[float]
    short_count: Optional[float]
    net_delta: Optional[float]
    v_long: Optional[float]
    v_short: Optional[float]
    v_net: Optional[float]
    a_long: Optional[float]
    a_short: Optional[float]
    kinematic_state: str
    zone_mode: str
    zone_sub_type: str
    fear_greed: Optional[float]
    market_sqn: Optional[float]

    def as_dict(self) -> Dict[str, object]:
        """Reference-shaped dict (``kwz_map`` was built with ``to_dict('index')``)."""
        return {
            "date": self.date,
            "wave_context": self.wave_context,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "net_delta": self.net_delta,
            "v_long": self.v_long,
            "v_short": self.v_short,
            "v_net": self.v_net,
            "a_long": self.a_long,
            "a_short": self.a_short,
            "kinematic_state": self.kinematic_state,
            "zone_mode": self.zone_mode,
            "zone_sub_type": self.zone_sub_type,
            "fear_greed": self.fear_greed,
            "market_sqn": self.market_sqn,
        }


def parse_zone_row(row: Mapping[str, object]) -> ZoneContext:
    """Build a :class:`ZoneContext` from one CSV row / dict."""
    return ZoneContext(
        date=str(row.get("date") or "").strip(),
        wave_context=str(row.get("wave_context") or DEFAULT_WAVE_CONTEXT),
        long_count=_to_float(row.get("long_count")),
        short_count=_to_float(row.get("short_count")),
        net_delta=_to_float(row.get("net_delta")),
        v_long=_to_float(row.get("v_long")),
        v_short=_to_float(row.get("v_short")),
        v_net=_to_float(row.get("v_net")),
        a_long=_to_float(row.get("a_long")),
        a_short=_to_float(row.get("a_short")),
        kinematic_state=str(row.get("kinematic_state") or ""),
        zone_mode=str(row.get("zone_mode") or DEFAULT_ZONE_MODE),
        zone_sub_type=str(row.get("zone_sub_type") or ""),
        fear_greed=_to_float(row.get("fear_greed")),
        market_sqn=_to_float(row.get("market_sqn")),
    )


def load_kinematic_zones(path: str) -> Dict[str, ZoneContext]:
    """Load ``kinematic_wave_zones_daily.csv`` → ``{date: ZoneContext}``.

    The delta series is ``long_count - short_count`` (breadth net delta); the
    frozen file also carries it as ``net_delta`` and both agree row for row —
    :func:`zone_delta_series` prefers the counts so the parity harness can prove
    they are the same signal.
    """
    if not os.path.exists(path):
        raise WaveThrustError(f"[!] FATAL: kinematic wave zones CSV not found: {path}")
    zones: Dict[str, ZoneContext] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            zone = parse_zone_row(row)
            if zone.date:
                zones[zone.date] = zone
    return zones


def zone_context_day(
    zones: Mapping[str, ZoneContext], date_str: str
) -> ZoneContext:
    """Zone context for ``date_str`` with the reference fallbacks (lines 443-445)."""
    zone = zones.get(date_str)
    if zone is None:
        return ZoneContext(
            date=date_str,
            wave_context=DEFAULT_WAVE_CONTEXT,
            long_count=None,
            short_count=None,
            net_delta=None,
            v_long=None,
            v_short=None,
            v_net=None,
            a_long=None,
            a_short=None,
            kinematic_state="",
            zone_mode=DEFAULT_ZONE_MODE,
            zone_sub_type="",
            fear_greed=None,
            market_sqn=None,
        )
    return zone


def zone_delta_series(zones: Mapping[str, ZoneContext]) -> List[Tuple[str, float]]:
    """Time-ordered ``(date, delta)`` breadth series feeding the wave engine."""
    dates = sorted(zones)
    series: List[Tuple[str, float]] = []
    for date_str in dates:
        zone = zones[date_str]
        if zone.long_count is not None and zone.short_count is not None:
            series.append((date_str, zone.long_count - zone.short_count))
        elif zone.net_delta is not None:
            series.append((date_str, zone.net_delta))
    return series


# ══════════════════════════ 3. wave forensics context ═══════════════════════


@dataclass(frozen=True)
class WaveForensics:
    """One row of ``wave_forensics_context_daily.csv`` plus derived features.

    ``above_075`` / ``cross_075`` / ``sqn_crosses_10d`` / ``sqn_vel_5d`` are
    computed at load time exactly as notebook lines 384-387 do.
    """

    date: str
    long_count: Optional[float]
    short_count: Optional[float]
    net_delta: Optional[float]
    direction: str
    sign: Optional[int]
    wave_id: Optional[int]
    running_wave_dur: Optional[int]
    running_peak_delta: Optional[float]
    running_retract_pct: Optional[float]
    is_day1_crossover: Optional[bool]
    is_warmup: Optional[bool]
    prev_same_wave_id: Optional[int]
    prev_same_peak: Optional[float]
    prev_same_dur: Optional[int]
    peak_expansion_ratio: Optional[float]
    dur_ratio: Optional[float]
    prev_opp_wave_id: Optional[int]
    prev_opp_peak: Optional[float]
    prev_opp_dur: Optional[int]
    is_decay_warning: Optional[bool]
    is_absorption: Optional[bool]
    tactical_regime: str
    confidence_score: Optional[float]
    market_sqn: Optional[float]
    fear_greed_score: Optional[float]
    above_075: int = 0
    cross_075: int = 0
    sqn_crosses_10d: float = 0.0
    sqn_vel_5d: float = 0.0

    def as_dict(self) -> Dict[str, object]:
        """Reference-shaped dict (``wf_map`` came from ``to_dict('index')``)."""
        return {
            "date": self.date,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "net_delta": self.net_delta,
            "direction": self.direction,
            "sign": self.sign,
            "wave_id": self.wave_id,
            "running_wave_dur": self.running_wave_dur,
            "running_peak_delta": self.running_peak_delta,
            "running_retract_pct": self.running_retract_pct,
            "is_day1_crossover": self.is_day1_crossover,
            "is_warmup": self.is_warmup,
            "prev_same_wave_id": self.prev_same_wave_id,
            "prev_same_peak": self.prev_same_peak,
            "prev_same_dur": self.prev_same_dur,
            "peak_expansion_ratio": self.peak_expansion_ratio,
            "dur_ratio": self.dur_ratio,
            "prev_opp_wave_id": self.prev_opp_wave_id,
            "prev_opp_peak": self.prev_opp_peak,
            "prev_opp_dur": self.prev_opp_dur,
            "is_decay_warning": self.is_decay_warning,
            "is_absorption": self.is_absorption,
            "tactical_regime": self.tactical_regime,
            "confidence_score": self.confidence_score,
            "market_sqn": self.market_sqn,
            "fear_greed_score": self.fear_greed_score,
            "above_075": self.above_075,
            "cross_075": self.cross_075,
            "sqn_crosses_10d": self.sqn_crosses_10d,
            "sqn_vel_5d": self.sqn_vel_5d,
        }


def parse_forensics_row(row: Mapping[str, object]) -> WaveForensics:
    """Build a :class:`WaveForensics` from one CSV row (derived columns left at 0)."""
    return WaveForensics(
        date=str(row.get("date") or "").strip(),
        long_count=_to_float(row.get("long_count")),
        short_count=_to_float(row.get("short_count")),
        net_delta=_to_float(row.get("net_delta")),
        direction=str(row.get("direction") or DEFAULT_FORENSICS_DIRECTION),
        sign=_to_int(row.get("sign")),
        wave_id=_to_int(row.get("wave_id")),
        running_wave_dur=_to_int(row.get("running_wave_dur")),
        running_peak_delta=_to_float(row.get("running_peak_delta")),
        running_retract_pct=_to_float(row.get("running_retract_pct")),
        is_day1_crossover=_to_bool(row.get("is_day1_crossover")),
        is_warmup=_to_bool(row.get("is_warmup")),
        prev_same_wave_id=_to_int(row.get("prev_same_wave_id")),
        prev_same_peak=_to_float(row.get("prev_same_peak")),
        prev_same_dur=_to_int(row.get("prev_same_dur")),
        peak_expansion_ratio=_to_float(row.get("peak_expansion_ratio")),
        dur_ratio=_to_float(row.get("dur_ratio")),
        prev_opp_wave_id=_to_int(row.get("prev_opp_wave_id")),
        prev_opp_peak=_to_float(row.get("prev_opp_peak")),
        prev_opp_dur=_to_int(row.get("prev_opp_dur")),
        is_decay_warning=_to_bool(row.get("is_decay_warning")),
        is_absorption=_to_bool(row.get("is_absorption")),
        tactical_regime=str(row.get("tactical_regime") or ""),
        confidence_score=_to_float(row.get("confidence_score")),
        market_sqn=_to_float(row.get("market_sqn")),
        fear_greed_score=_to_float(row.get("fear_greed_score")),
    )


def load_wave_forensics(path: str) -> Dict[str, WaveForensics]:
    """Load ``wave_forensics_context_daily.csv`` with its derived features.

    Derived columns (notebook lines 384-387), in file order:

    * ``above_075 = (market_sqn >= 0.75)`` as int;
    * ``cross_075 = (above_075.diff().abs() > 0)`` as int (first row ``0``);
    * ``sqn_crosses_10d = cross_075.rolling(10, min_periods=1).sum()``;
    * ``sqn_vel_5d = market_sqn.diff(5).fillna(0.0)`` (first five rows ``0.0``).

    ``market_sqn`` is coerced like ``pd.to_numeric`` — a blank row keeps ``None``
    (pandas ``NaN``), which makes every comparison ``False`` exactly as in the
    reference.
    """
    if not os.path.exists(path):
        raise WaveThrustError(f"[!] FATAL: wave forensics CSV not found: {path}")

    rows: List[WaveForensics] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            parsed = parse_forensics_row(raw)
            if parsed.date:
                rows.append(parsed)
    rows.sort(key=lambda item: item.date)

    above = [0 if row.market_sqn is None else int(row.market_sqn >= FORENSICS_SQN_LINE) for row in rows]
    cross = [0 if index == 0 else int(above[index] != above[index - 1]) for index in range(len(rows))]

    out: Dict[str, WaveForensics] = {}
    cross_window: List[int] = []
    for index, row in enumerate(rows):
        cross_window.append(cross[index])
        if len(cross_window) > 10:
            cross_window.pop(0)
        velocity = 0.0
        if index >= 5:
            previous = rows[index - 5].market_sqn
            if row.market_sqn is not None and previous is not None:
                velocity = row.market_sqn - previous
        out[row.date] = replace(
            row,
            above_075=above[index],
            cross_075=cross[index],
            sqn_crosses_10d=float(sum(cross_window)),
            sqn_vel_5d=velocity,
        )
    return out


def forensics_day(
    forensics: Mapping[str, WaveForensics], date_str: str
) -> Dict[str, object]:
    """The exact forensics values the backtest pulls for one date (lines 415-422).

    Blank cells become ``nan`` — identical to the reference's
    ``float(wf_day.get(col, 0.0) or 0.0)`` on a pandas ``NaN`` cell.
    """
    row = forensics.get(date_str)
    if row is None:
        return {
            "direction": DEFAULT_FORENSICS_DIRECTION,
            "running_peak_delta": 0.0,
            "prev_opp_peak": 0.0,
            "prev_same_peak": 0.0,
            "running_wave_dur": DEFAULT_RUNNING_WAVE_DUR,
            "sqn_crosses_10d": 0.0,
            "sqn_vel_5d": 0.0,
        }
    return {
        "direction": row.direction,
        "running_peak_delta": _nan() if row.running_peak_delta is None else row.running_peak_delta,
        "prev_opp_peak": _nan() if row.prev_opp_peak is None else row.prev_opp_peak,
        "prev_same_peak": _nan() if row.prev_same_peak is None else row.prev_same_peak,
        "running_wave_dur": row.running_wave_dur if row.running_wave_dur is not None else DEFAULT_RUNNING_WAVE_DUR,
        "sqn_crosses_10d": row.sqn_crosses_10d,
        "sqn_vel_5d": row.sqn_vel_5d,
    }


# ══════════════════════════ 4. short-squeeze shield ═════════════════════════


@dataclass(frozen=True)
class SqueezeAlert:
    """Which of the three squeeze triggers fired on a day (lines 483-492)."""

    is_alert: bool
    triggers: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, object]:
        return {"is_alert": self.is_alert, "triggers": list(self.triggers)}


def assess_short_squeeze(
    direction: str,
    running_peak_delta: float,
    prev_opp_peak: float,
    prev_same_peak: float,
    sqn: float,
    zone_mode: str = DEFAULT_ZONE_MODE,
    sqn_vel_5d: float = 0.0,
    sqn_v3: float = 0.0,
) -> SqueezeAlert:
    """Detect short-squeeze exhaustion (notebook lines 483-492).

    Three independent triggers, evaluated against the *current* wave:

    * ``SQUEEZE_SHIELD_COVER`` — an opposite-side peak ``>= 500`` followed by a
      run peak ``< 65%`` of it with ``SQN >= 0.70``;
    * ``SQN_MOMENTUM`` — a ``TRANSITION`` zone day where SQN velocity
      (``sqn_vel_5d >= 0.15`` or 3-day ``sqn_v3 >= 0.12``) with ``SQN >= 0.80``;
    * ``DECAYED_SAME_WAVE`` — the same-side peak ``>= 400`` collapsing to
      ``< 30%`` with ``SQN >= 1.10``.

    ``nan`` inputs compare ``False``, so blank forensics cells never fire a
    trigger — same as the reference.
    """
    triggers: List[str] = []
    if direction == "SHORT" and prev_opp_peak >= SQUEEZE_OPP_PEAK_MIN:
        if abs(running_peak_delta) < SQUEEZE_RUN_PEAK_RATIO * prev_opp_peak and sqn >= SQUEEZE_SQN_MIN:
            triggers.append("SQUEEZE_SHIELD_COVER")
    if zone_mode == "TRANSITION" and sqn >= SQUEEZE_TRANSITION_SQN_MIN:
        if sqn_vel_5d >= SQUEEZE_TRANSITION_SQN_VEL5 or sqn_v3 >= SQUEEZE_TRANSITION_SQN_V3:
            triggers.append("SQN_MOMENTUM")
    if direction == "SHORT" and abs(prev_same_peak) >= SQUEEZE_SAME_PEAK_MIN:
        if (
            abs(running_peak_delta) < SQUEEZE_SAME_PEAK_RATIO * abs(prev_same_peak)
            and sqn >= SQUEEZE_SAME_SQN_MIN
        ):
            triggers.append("DECAYED_SAME_WAVE")
    return SqueezeAlert(is_alert=bool(triggers), triggers=tuple(triggers))


# ══════════════════════════════ 5. locators ═════════════════════════════════


def reference_path(filename: str, base_dir: Optional[str] = None) -> str:
    """Resolve a frozen snapshot file (``base_dir`` first, then repo default)."""
    candidates: List[str] = []
    if base_dir:
        candidates.extend(
            [
                os.path.join(base_dir, filename),
                os.path.join(base_dir, "shared_mcp", filename),
                os.path.join(base_dir, "data", "shared_mcp", filename),
            ]
        )
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    candidates.append(os.path.join(repo_root, "reference", "model19", filename))
    candidates.append(os.path.join(os.getcwd(), "reference", "model19", filename))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise WaveThrustError(
        f"[!] FATAL: {filename} not found. Looked in: " + ", ".join(candidates)
    )


def load_wave_context(
    zones_path: Optional[str] = None,
    forensics_path: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Tuple[Dict[str, ZoneContext], Dict[str, WaveForensics], Dict[str, WaveThrustPoint]]:
    """Load all three wave inputs from the frozen snapshot in one call.

    Returns ``(zones, forensics, thrust_map)`` where ``thrust_map`` is computed
    from the zone file's breadth delta series via :func:`compute_wave_thrust`.
    """
    zones = load_kinematic_zones(zones_path or reference_path("kinematic_wave_zones_daily.csv", base_dir))
    forensics = load_wave_forensics(
        forensics_path or reference_path("wave_forensics_context_daily.csv", base_dir)
    )
    thrust = compute_wave_thrust(zone_delta_series(zones))
    return zones, forensics, thrust


__all__ = [
    "DEFAULT_DELTA_PROG",
    "DEFAULT_DAYS_IN_WAVE",
    "DEFAULT_FORENSICS_DIRECTION",
    "DEFAULT_RUNNING_WAVE_DUR",
    "DEFAULT_WAVE_CONTEXT",
    "DEFAULT_ZONE_MODE",
    "FORENSICS_SQN_LINE",
    "SqueezeAlert",
    "WAVE_CONTEXTS",
    "WaveForensics",
    "WaveThrustError",
    "WaveThrustPoint",
    "ZONE_MODES",
    "ZoneContext",
    "assess_short_squeeze",
    "compute_wave_thrust",
    "forensics_day",
    "load_kinematic_zones",
    "load_wave_context",
    "load_wave_forensics",
    "parse_forensics_row",
    "parse_zone_row",
    "reference_path",
    "wave_thrust_day",
    "zone_context_day",
    "zone_delta_series",
]
