"""Model 19 ``DynamicCompassEngine`` port + drawdown-guarded 10-regime classifier.

Source of truth (frozen snapshot, SHA-256 pinned in
``reference/model19/MANIFEST.json``):

* ``reference/model19/compass_returns_engine.py`` — ``compute_cell_stat`` and
  ``DynamicCompassEngine.compute_all_6_setups`` (win/return calibration tables
  for the 6 strategic setups: ``tl, ts, pb, bear, kl, ks``).
* ``reference/model19/18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py``
  — CELL 4 daily decision (lines 306-324) and CELL 5 10-regime matrix
  (lines 331-378).

Design notes
------------
* **Stdlib only.** The reference reads the master CSV with pandas; this port
  parses it with :mod:`csv` and reproduces pandas' column typing explicitly, so
  the record dicts handed to the calibration math are identical (``mt``/``lp``/
  ``sp`` ints, ``li``/``si``/``la``/``sa`` floats, labels as ``str``).
* **No HTML / Colab fallback.** The reference falls back to scraping the three
  ``dual_semicircle_*.html`` exports and mounting Google Drive. That path is
  dead weight for Homelab: we require the frozen CSV and fail loudly without it.
* **Isolation.** Analytical only — no ``order_service``, ``trade_dispatcher``,
  ``quicktrade_*``, ``broker_cdp``, broker driver or live-DB imports.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.services.model19.setups import (
    SETUP_SLOTS,
    TABLE_BOX_SHORT,
    TABLE_BOX_TALL,
    CampaignDecision,
    SetupScore,
    resolve_slot_box,
    resolve_slot_q,
    score_setups,
    select_campaign_mode,
)

#: Historical average 100-day volatility baseline (notebook line 121).
BASELINE_VOL_100D: float = 0.855

#: Market-SQN thresholds for the 10-regime direction axis (notebook lines 335-339).
SQN_VERY_BULLISH: float = 1.47
SQN_BULLISH: float = 0.75
SQN_NEUTRAL: float = 0.00
SQN_BEARISH: float = -0.70

#: Model 18/19 ATR regime tactic + exit policy mapping (notebook lines 367-378).
MAPPING_10_REGIMES_M18_ATR: Dict[str, Tuple[str, str]] = {
    "Very Bullish Quiet": ("11_V3_Sniper", "STANDARD"),
    "Very Bullish Volatile": ("V6_3_FullUnified", "FLIP_CUT"),
    "Bullish Quiet": ("V6_1_TransitionTight", "STANDARD"),
    "Bullish Volatile": ("V6_2_WaveSqueezeSpring", "FLIP_CUT"),
    "Neutral Quiet": ("12_V4_Macro", "STANDARD"),
    "Neutral Volatile": ("V6_1_TransitionTight", "STANDARD"),
    "Bearish Quiet": ("11_V3_Sniper", "STANDARD"),
    "Bearish Volatile": ("V6_1_TransitionTight", "STANDARD"),
    "Very Bearish Quiet": ("13_V4_1_Harvest", "STANDARD"),
    "Very Bearish Volatile": ("12_V4_Macro", "FLIP_CUT"),
}

#: Legacy Model 17 mapping kept for parity auditing (notebook lines 354-365).
MAPPING_10_REGIMES_M17: Dict[str, Tuple[str, str]] = {
    "Very Bullish Quiet": ("11_V3_Sniper", "STANDARD"),
    "Very Bullish Volatile": ("V6_2_WaveSqueezeSpring", "STANDARD"),
    "Bullish Quiet": ("V6_1_TransitionTight", "STANDARD"),
    "Bullish Volatile": ("V6_3_FullUnified", "STANDARD"),
    "Neutral Quiet": ("12_V4_Macro", "STANDARD"),
    "Neutral Volatile": ("V6_1_TransitionTight", "STANDARD"),
    "Bearish Quiet": ("11_V3_Sniper", "STANDARD"),
    "Bearish Volatile": ("V6_1_TransitionTight", "STANDARD"),
    "Very Bearish Quiet": ("13_V4_1_Harvest", "STANDARD"),
    "Very Bearish Volatile": ("13_V4_1_Harvest", "STANDARD"),
}

#: Column typing of ``decision_compass_master_records.csv`` (pandas parity).
_COLUMN_TYPES: Dict[str, type] = {
    "d": str,
    "y": int,
    "sqn": float,
    "mt": int,
    "fg": str,
    "sc": int,
    "lq": str,
    "li": float,
    "lp": int,
    "la": float,
    "sq": str,
    "si": float,
    "sp": int,
    "sa": float,
    "setup_family": str,
}

#: ``setup_family`` values → engine attribute names.
_FAMILY_ATTRS: Dict[str, str] = {
    "transition": "recs_trans",
    "pure_trend": "recs_pure",
    "king_trend": "recs_king",
}

#: Inverse-play labels used by the reference table (Thai labels preserved).
_INVERSE_LABELS: Dict[str, str] = {
    "tl": "Inverse Long (ดักย่อ/กลับหน้า)",
    "ts": "Inverse Short (ดักเด้งสวนทาง)",
    "pb": "Inverse Short",
    "bear": "Inverse Long (ดัก Short Squeeze)",
    "kl": "Inverse Short",
    "ks": "Inverse Long (ดัก Squeeze)",
}


class CompassEngineError(FileNotFoundError):
    """Raised when the frozen compass calibration records cannot be loaded."""


# ─────────────────────────────── records ───────────────────────────────────


def load_master_records(path: str) -> Dict[str, List[dict]]:
    """Load ``decision_compass_master_records.csv`` into per-family record lists.

    Returns ``{family: [record, ...]}`` preserving CSV row order — order matters
    because the reference averages with ``sum(...) / len(...)`` in file order.
    """
    if not os.path.exists(path):
        raise CompassEngineError(f"[!] FATAL: compass calibration CSV not found: {path}")

    by_family: Dict[str, List[dict]] = {family: [] for family in _FAMILY_ATTRS}
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            record: dict = {}
            for column, kind in _COLUMN_TYPES.items():
                value = raw.get(column)
                if value is None or value == "":
                    continue
                record[column] = kind(value) if kind is not str else value
            family = record.get("setup_family")
            if family in by_family:
                by_family[family].append(record)
            else:
                by_family.setdefault(str(family), []).append(record)
    return by_family


# ──────────────────────────── calibration table ────────────────────────────


@dataclass
class SetupTableRow:
    """One row of the 6-setup compass calibration table."""

    id: int
    name: str
    sub: str
    direction: str
    q_label: str
    box: str
    win_norm: float
    ret_norm: float
    inverse_name: str
    win_inv: float
    ret_inv: float
    days: int

    def as_dict(self) -> Dict[str, object]:
        """Reference-compatible dict (same keys/values as the notebook table)."""
        return {
            "id": self.id,
            "name": self.name,
            "sub": self.sub,
            "dir": self.direction,
            "q": self.q_label,
            "box": self.box,
            "win_norm": self.win_norm,
            "ret_norm": self.ret_norm,
            "inv_name": self.inverse_name,
            "win_inv": self.win_inv,
            "ret_inv": self.ret_inv,
            "days": self.days,
        }


#: Static labels for the six table rows, in reference order.
_TABLE_META: Dict[str, Tuple[str, str, str]] = {
    "tl": ("Transition Setups", "Long (L1+L2)", "Long"),
    "ts": ("Transition Setups", "Short (S1+S2)", "Short"),
    "pb": ("Pure Trend Setups", "Long (+++)", "Long (+++)"),
    "bear": ("Pure Trend Setups", "Short (---)", "Short (---)"),
    "kl": ("King Trend Hybrid", "Long Timing", "Long"),
    "ks": ("King Trend Hybrid", "Short Timing", "Short"),
}


def compute_cell_stat(
    records: Optional[Sequence[Dict[str, Any]]],
    market_type: str = "bull",
    fg: str = "Neutral",
    q: str = "Q1",
    is_short_box: bool = True,
    side: str = "long",
) -> Dict[str, object]:
    """Win rate / average return for one compass cell.

    Port of ``compass_returns_engine.py:compute_cell_stat``. The cell is
    ``market_type x fg_tier x side-quantile x box arm``:

    * box median is recomputed from the *active* record set every call
      (``dyn_l_med`` / ``dyn_s_med``) — not a frozen constant;
    * short-box arm keeps rows at or below that median, tall-box arm keeps rows
      above it;
    * when the box arm is empty, the reference falls back to the whole
      quantile cell (``days = len(match)``); an empty cell returns the neutral
      ``{days: 0, win: 50.0, ret: 0.0}``.
    """
    if not records:
        return {"days": 0, "win": 50.0, "ret": 0.0}
    active: List[Dict[str, Any]]
    if market_type == "bull":
        active = [r for r in records if r.get("mt") == 1]
    elif market_type == "non_bull":
        active = [r for r in records if r.get("mt") == 0]
    else:
        active = list(records)

    liqrs = sorted(float(r["li"]) for r in active)
    siqrs = sorted(float(r["si"]) for r in active)
    dyn_l_med = _median_or_default(liqrs)
    dyn_s_med = _median_or_default(siqrs)

    if side == "long":
        match = [r for r in active if r.get("fg") == fg and r.get("lq") == q]
        if is_short_box:
            box_match = [r for r in match if float(r["li"]) <= dyn_l_med]
        else:
            box_match = [r for r in match if float(r["li"]) > dyn_l_med]
        win_col, ret_col = "lp", "la"
    else:
        match = [r for r in active if r.get("fg") == fg and r.get("sq") == q]
        if is_short_box:
            box_match = [r for r in match if float(r["si"]) <= dyn_s_med]
        else:
            box_match = [r for r in match if float(r["si"]) > dyn_s_med]
        win_col, ret_col = "sp", "sa"

    days = len(box_match)
    if days == 0:
        if match:
            win = (sum(r[win_col] for r in match) / len(match)) * 100.0
            ret = sum(r[ret_col] for r in match) / len(match)
            return {"days": len(match), "win": win, "ret": ret}
        return {"days": 0, "win": 50.0, "ret": 0.0}

    win = (sum(r[win_col] for r in box_match) / days) * 100.0
    ret = sum(r[ret_col] for r in box_match) / days
    return {"days": days, "win": win, "ret": ret}


def _median_or_default(sorted_values: Sequence[float], default: float = 15.0) -> float:
    """Median of a pre-sorted sequence, ``default`` when empty (reference rule)."""
    if not sorted_values:
        return default
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


# ────────────────────────────── compass engine ─────────────────────────────


class DynamicCompassEngine:
    """Dynamic Compass: calibrates the 6 setups from frozen historical records.

    Usage::

        engine = DynamicCompassEngine(master_csv_path="reference/model19/"
                                      "decision_compass_master_records.csv")
        table, long_rets, short_rets = engine.compute_all_6_setups(
            is_bull=True, fg_tier="Greed", stats_old_l=stats, ...)
        decision = engine.compute_decision(...)   # mode + slot targets + qualifiers
    """

    def __init__(
        self,
        master_csv_path: Optional[str] = None,
        base_dir: Optional[str] = None,
    ) -> None:
        path = master_csv_path or _default_master_csv(base_dir)
        by_family = load_master_records(path)
        for family, attr in _FAMILY_ATTRS.items():
            setattr(self, attr, by_family.get(family, []))
        self.master_csv_path = path
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(path))
        self.source = f"CSV: {os.path.basename(path)} ({os.path.abspath(path)})"

        if not self.recs_trans:
            raise CompassEngineError(
                "[!] FATAL: DynamicCompassEngine could not find valid compass "
                f"calibration records in {self.base_dir}!"
            )

    # -- calibration -----------------------------------------------------
    @property
    def record_counts(self) -> Dict[str, int]:
        """Row count per setup family (transition / pure_trend / king_trend)."""
        return {
            "transition": len(self.recs_trans),
            "pure_trend": len(self.recs_pure),
            "king_trend": len(self.recs_king),
        }

    def _slot_stats(
        self,
        stats_old_l: Optional[Mapping[str, object]],
        stats_old_s: Optional[Mapping[str, object]],
        stats_new_l: Optional[Mapping[str, object]],
        stats_new_s: Optional[Mapping[str, object]],
        stats_kt_l: Optional[Mapping[str, object]],
        stats_kt_s: Optional[Mapping[str, object]],
    ) -> Dict[str, Tuple[str, bool]]:
        """Resolve ``(q_label, is_short_box)`` for all six slots."""
        return {
            "tl": (resolve_slot_q("tl", stats_old_l), resolve_slot_box("tl", stats_old_l)),
            "ts": (resolve_slot_q("ts", stats_old_s), resolve_slot_box("ts", stats_old_s)),
            "pb": (resolve_slot_q("pb", stats_new_l), resolve_slot_box("pb", stats_new_l)),
            "bear": (
                resolve_slot_q("bear", stats_new_s),
                resolve_slot_box("bear", stats_new_s),
            ),
            "kl": (resolve_slot_q("kl", stats_kt_l), resolve_slot_box("kl", stats_kt_l)),
            "ks": (resolve_slot_q("ks", stats_kt_s), resolve_slot_box("ks", stats_kt_s)),
        }

    def compute_all_6_setups(
        self,
        is_bull: bool = True,
        fg_tier: str = "Neutral",
        stats_old_l: Optional[Mapping[str, object]] = None,
        stats_old_s: Optional[Mapping[str, object]] = None,
        stats_new_l: Optional[Mapping[str, object]] = None,
        stats_new_s: Optional[Mapping[str, object]] = None,
        stats_kt_l: Optional[Mapping[str, object]] = None,
        stats_kt_s: Optional[Mapping[str, object]] = None,
    ) -> Tuple[List[SetupTableRow], List[float], List[float]]:
        """Calibration table + normalised long/short returns for the 6 setups.

        Returns ``(table_rows, long_rets, short_rets)`` where the long side is
        ``[tl, -ts, pb, -bear, kl, -ks]`` (transition/pure-bear/king-short legs
        are inverse plays) and the short side is its negation.
        """
        market_type = "bull" if is_bull else "non_bull"
        slots = self._slot_stats(
            stats_old_l, stats_old_s, stats_new_l, stats_new_s, stats_kt_l, stats_kt_s
        )
        cell_specs = [
            ("tl", self.recs_trans, "long"),
            ("ts", self.recs_trans, "short"),
            ("pb", self.recs_pure, "long"),
            ("bear", self.recs_pure, "short"),
            ("kl", self.recs_king, "long"),
            ("ks", self.recs_king, "short"),
        ]

        results: Dict[str, Dict[str, object]] = {}
        rows: List[SetupTableRow] = []
        for slot, records, side in cell_specs:
            q_label, is_short_box = slots[slot]
            res = compute_cell_stat(records, market_type, fg_tier, q_label, is_short_box, side)
            results[slot] = res
            name, sub, direction = _TABLE_META[slot]
            rows.append(
                SetupTableRow(
                    id=SETUP_SLOTS.index(slot) + 1,
                    name=name,
                    sub=sub,
                    direction=direction,
                    q_label=q_label,
                    box=TABLE_BOX_SHORT if is_short_box else TABLE_BOX_TALL,
                    win_norm=float(res["win"]),
                    ret_norm=float(res["ret"]),
                    inverse_name=_INVERSE_LABELS[slot],
                    win_inv=100.0 - float(res["win"]),
                    ret_inv=-float(res["ret"]),
                    days=int(res["days"]),
                )
            )

        long_rets = [
            round(float(results["tl"]["ret"]), 2),
            round(-float(results["ts"]["ret"]), 2),
            round(float(results["pb"]["ret"]), 2),
            round(-float(results["bear"]["ret"]), 2),
            round(float(results["kl"]["ret"]), 2),
            round(-float(results["ks"]["ret"]), 2),
        ]
        short_rets = [-value for value in long_rets]
        return rows, long_rets, short_rets

    # -- daily decision --------------------------------------------------
    def compute_decision(
        self,
        is_bull: bool,
        fg_tier: str,
        l_cnt: int,
        s_cnt: int,
        stats_old_l: Optional[Mapping[str, object]] = None,
        stats_old_s: Optional[Mapping[str, object]] = None,
        stats_new_l: Optional[Mapping[str, object]] = None,
        stats_new_s: Optional[Mapping[str, object]] = None,
        stats_kt_l: Optional[Mapping[str, object]] = None,
        stats_kt_s: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        """Full compass decision for one day (table + scores + campaign mode).

        Notebook CELL 4 lines 306-324: calibrate → score both sides → keep
        setups scoring above 100.0 → pick mode from qualification and breadth.
        """
        table, long_rets, short_rets = self.compute_all_6_setups(
            is_bull=is_bull,
            fg_tier=fg_tier,
            stats_old_l=stats_old_l,
            stats_old_s=stats_old_s,
            stats_new_l=stats_new_l,
            stats_new_s=stats_new_s,
            stats_kt_l=stats_kt_l,
            stats_kt_s=stats_kt_s,
        )
        long_scores, short_scores = score_setups(
            [row.as_dict() for row in table], long_rets, short_rets
        )
        decision: CampaignDecision = select_campaign_mode(
            long_scores, short_scores, is_bull, l_cnt, s_cnt
        )
        return {
            "table": table,
            "long_scores": long_scores,
            "short_scores": short_scores,
            "long_rets": long_rets,
            "short_rets": short_rets,
            "mode": decision.mode,
            "target_l": decision.target_l,
            "target_s": decision.target_s,
            "long_qual": decision.long_qual,
            "short_qual": decision.short_qual,
            "is_bull": is_bull,
            "fg_tier": fg_tier,
            "l_cnt": l_cnt,
            "s_cnt": s_cnt,
        }


def _default_master_csv(base_dir: Optional[str]) -> str:
    """Locate the frozen master CSV (repo ``reference/model19/`` first)."""
    candidates: List[str] = []
    if base_dir:
        candidates.extend(
            [
                os.path.join(base_dir, "decision_compass_master_records.csv"),
                os.path.join(base_dir, "shared_mcp", "decision_compass_master_records.csv"),
                os.path.join(base_dir, "data", "shared_mcp", "decision_compass_master_records.csv"),
            ]
        )
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    candidates.append(os.path.join(repo_root, "reference", "model19", "decision_compass_master_records.csv"))
    candidates.append(os.path.join(os.getcwd(), "reference", "model19", "decision_compass_master_records.csv"))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise CompassEngineError(
        "[!] FATAL: decision_compass_master_records.csv not found. Looked in: "
        + ", ".join(candidates)
    )


# ───────────────────────────── 10-regime matrix ────────────────────────────


def classify_regime_10(
    sqn: float,
    vol_100d: Optional[float] = None,
    baseline_vol: float = BASELINE_VOL_100D,
) -> str:
    """Bivariate regime label: ``'<direction> <Quiet|Volatile>'``.

    Notebook CELL 5 lines 331-340. Direction axis (Market SQN):
    ``> 1.47`` Very Bullish, ``>= 0.75`` Bullish, ``>= 0`` Neutral,
    ``>= -0.70`` Bearish, else Very Bearish. Volatility axis: ``Volatile`` when
    the 100-day volatility is strictly above ``baseline_vol`` (0.855), else
    ``Quiet``.
    """
    value = float(sqn)
    vol = float(baseline_vol if vol_100d is None else vol_100d)
    vol_label = "Volatile" if vol > baseline_vol else "Quiet"
    if value > SQN_VERY_BULLISH:
        direction = "Very Bullish"
    elif value >= SQN_BULLISH:
        direction = "Bullish"
    elif value >= SQN_NEUTRAL:
        direction = "Neutral"
    elif value >= SQN_BEARISH:
        direction = "Bearish"
    else:
        direction = "Very Bearish"
    return f"{direction} {vol_label}"


def get_10_regime(
    date_str: str,
    decision: Optional[Mapping[str, object]] = None,
    regime_map: Optional[Mapping[str, str]] = None,
    vol_100d_map: Optional[Mapping[str, float]] = None,
    baseline_vol: float = BASELINE_VOL_100D,
) -> str:
    """Regime for ``date_str`` — precomputed map first, else recomputed on the fly."""
    if regime_map and date_str in regime_map:
        return regime_map[date_str]
    sqn = 0.0
    if decision is not None and decision.get("sqn") is not None:
        sqn = float(decision["sqn"])  # type: ignore[arg-type]
    vol = baseline_vol
    if vol_100d_map:
        vol = float(vol_100d_map.get(date_str, baseline_vol))
    return classify_regime_10(sqn, vol, baseline_vol)


def active_tactic(
    regime: str, mapping: Optional[Mapping[str, Tuple[str, str]]] = None
) -> Tuple[str, str]:
    """``(model, exit_policy)`` for ``regime`` — defaults to the Model 18 map."""
    table = mapping if mapping is not None else MAPPING_10_REGIMES_M18_ATR
    return table.get(regime, ("12_V4_Macro", "STANDARD"))


__all__ = [
    "BASELINE_VOL_100D",
    "CompassEngineError",
    "DynamicCompassEngine",
    "MAPPING_10_REGIMES_M17",
    "MAPPING_10_REGIMES_M18_ATR",
    "SetupScore",
    "SetupTableRow",
    "active_tactic",
    "classify_regime_10",
    "compute_cell_stat",
    "get_10_regime",
    "load_master_records",
]
