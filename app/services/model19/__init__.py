"""Model 19 package — quantitative strategy engine ports (Loop 3).

Modules
-------
* :mod:`app.services.model19.setups` — pure-stdlib primitives: 20-day rolling
  breadth statistics, breadth classification, the 6 setup definitions and the
  compass scoring / campaign-mode selection rules.
* :mod:`app.services.model19.compass_engine` — ``DynamicCompassEngine`` port
  (master-record loading, 6-setup expected win/return tables, daily decision)
  plus the drawdown-guarded 10-regime classifier.
* :mod:`app.services.model19.regime_engine` — frozen SQN snapshot → 10-regime
  series/map, per-day tactic flags and the transition-tightening guard.
* :mod:`app.services.model19.wave_thrust` — kinematic wave zones & forensics:
  point-in-time wave thrust, zone context, derived crossover features and the
  short-squeeze shield.

Isolation contract (Loop 3 guard)
--------------------------------
This package is analytical only. It MUST NOT import ``order_service``,
``trade_dispatcher``, ``quicktrade_*``, ``broker_cdp``, broker drivers, or any
live database/session module. It depends on the standard library alone, so it
can run inside the Colab-free parity harness and in-process scanners alike.
"""
from app.services.model19.setups import (
    BREADTH_MEDIAN_BASELINES,
    BOX_SHORT,
    BOX_TALL,
    CAMPAIGN_MODES,
    SCORE_THRESHOLD,
    SETUP_SLOT_DEFAULTS,
    SETUP_SLOTS,
    SetupScore,
    calc_stats_20d,
    classify_breadth_counts,
    derive_fg_tier,
    median,
    percentile,
    percentile_of_score_weak,
    resolve_slot_box,
    resolve_slot_q,
    score_setups,
    select_campaign_mode,
)
from app.services.model19.compass_engine import (
    BASELINE_VOL_100D,
    MAPPING_10_REGIMES_M17,
    MAPPING_10_REGIMES_M18_ATR,
    CompassEngineError,
    DynamicCompassEngine,
    SetupTableRow,
    active_tactic,
    classify_regime_10,
    compute_cell_stat,
    get_10_regime,
    load_master_records,
)
from app.services.model19 import regime_engine, wave_thrust

__all__ = [
    "regime_engine",
    "wave_thrust",
    "BREADTH_MEDIAN_BASELINES",
    "BOX_SHORT",
    "BOX_TALL",
    "CAMPAIGN_MODES",
    "SCORE_THRESHOLD",
    "SETUP_SLOT_DEFAULTS",
    "SETUP_SLOTS",
    "SetupScore",
    "calc_stats_20d",
    "classify_breadth_counts",
    "derive_fg_tier",
    "median",
    "percentile",
    "percentile_of_score_weak",
    "resolve_slot_box",
    "resolve_slot_q",
    "score_setups",
    "select_campaign_mode",
    "BASELINE_VOL_100D",
    "MAPPING_10_REGIMES_M17",
    "MAPPING_10_REGIMES_M18_ATR",
    "CompassEngineError",
    "DynamicCompassEngine",
    "SetupTableRow",
    "active_tactic",
    "classify_regime_10",
    "compute_cell_stat",
    "get_10_regime",
    "load_master_records",
]
