# TASK-loop3-0a-model19-code-map: Model 19 Code Map & Golden Snapshot Mapping

- Created: 2026-10-28 by Hermes `homelab-build`
- Loop: 3 (STEP 0a probe / architecture code map) · Kanban card: `t_49794e8b`
- Lane: `homelab-build` (T0/T1 code & reference architecture)
- Tier: 🟢 T0 (read-only freeze & code mapping, zero live financial risk)
- Model: `gemini-3.8-flash`
- Broker: N/A (Colab & quantitative strategy engine)
- Probe: PROBE_DONE (Golden snapshot vendor complete, SHA-256 verified, notebook neutralized)
- Workspace: `worktree:investment-homelab` · Branch: `task/loop3-0a-model19-code-map`
- Status: REVIEW
- Plan approved: 2026-10-27 by human / planner
- Verify: SHA-256 match `reference/model19/MANIFEST.json` & 100% logic coverage

---

## 1. Executive Summary & Golden Snapshot Inventory

Model 19 (*Era 4 Grandmaster v6 Chandelier Booster Forwardtest*) is the flagship quantitative swing-trading engine for SET. This card formalizes the vendor snapshot in `reference/model19/`, neutralizes Colab/Drive dependencies for 100% deterministic local execution, and provides the complete architectural code map linking notebook cells to InvestmentHomelab modules in `app/`.

### Golden Snapshot Manifest (`reference/model19/`)
All 14 files have been verified with exact byte counts and SHA-256 checksums recorded in `reference/model19/MANIFEST.json`:

| # | File Name | Role | SHA-256 (12-char prefix) | Size (Bytes) | Source / Status |
|---|---|---|---|---|---|
| 0 | `18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py` | Reference Notebook (Neutralized) | `5d50f77b2253` | 64,314 | Neutralized (Pristine: `1ee891597298`, 64,969 B) |
| 1 | `thai_fear_greed_daily.csv` | Macro Sentiment Daily | `532ca580a212` | 44,717 | `~/compute/data/colab_pull/data/` |
| 2 | `kinematic_wave_zones_daily.csv` | Kinematic Wave Zones | `ae22b47fff2f` | 173,151 | `~/compute/data/colab_pull/data/` |
| 3 | `chandelier_stop_daily_cache.csv` | Chandelier Stops & Distances | `e685bdf7b0e3` | 27,699,703 | `~/compute/data/colab_pull/data/` (27 MB) |
| 4 | `decision_compass_master_records.csv` | Compass Historical Setups | `6bc306eb8c4b` | 79,848 | `~/compute/data/colab_pull/data/` |
| 5 | `wave_forensics_context_daily.csv` | Wave Context & Dynamics | `d702ad08e6d0` | 141,639 | `~/compute/data/colab_pull/data/` |
| 6 | `prices_2023_cache.csv` | Price Matrix 2023 | `d85f7370c678` | 802,341 | `~/compute/data/colab_pull/data/backtest/` |
| 7 | `prices_2024_cache.csv` | Price Matrix 2024 | `a6cd6a05370c` | 818,967 | `~/compute/data/colab_pull/data/backtest/` |
| 8 | `prices_2025_cache.csv` | Price Matrix 2025 | `6c38bfa0a9a4` | 812,283 | `~/compute/data/colab_pull/data/backtest/` |
| 9 | `prices_2026_cache.csv` | Price Matrix 2026 | `77dddbb8bda1` | 718,664 | `~/compute/data/colab_pull/data/backtest/` |
| 10 | `mcp_historical_sqn_data.json` | Market SQN & 100d Volatility | `ca22d431b75e` | 127,920 | `~/compute/data/colab_pull/data/shared_mcp/` |
| 11 | `compass_returns_engine.py` | Dynamic Compass Engine Module | `df1a376f861e` | 12,774 | `~/compute/data/colab_pull/data/shared_mcp/` |
| 12 | `plot_comparison_boxplot.py` | 20d Rolling Breadth Stats Module | `f6f8272192d6` | 4,062 | `~/compute/data/colab_pull/data/shared_mcp/` |
| 13 | `MANIFEST.json` | Hash & Provenance Manifest | `bca86e2eb704` | 3,962 | SSOT Registry |

### Neutralization Verification (Req 4)
- Colab Drive auto-mount (`from google.colab import drive`) eliminated.
- `find_file(fname)` repointed to prioritize `reference/model19/` and script directory.
- `TARGET_DIR` and `DATA_ROOT` set to `reference/model19/`.
- Verified all 6 call sites (lines 120, 132, 147, 152, 298, 399) and yearly price globs resolve locally with zero network or external Drive access.

---

## 2. Model 19 Code Map & Logic Decomposition

The reference implementation consists of 9 logical cells. Below is the 100% exhaustive mapping of each algorithmic pillar into existing and target Homelab modules.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MODEL 19 ARCHITECTURE                            │
├───────────────────┬─────────────────────────────────┬───────────────────┤
│   PILLAR 1        │          PILLAR 2               │    PILLAR 3       │
│  Dual-Synergy     │   Drawdown-Guarded 10-Regime    │ Asymmetric Exits  │
│  Booster Engine   │        & Wave Forensics         │ & House-Money     │
│ (Dip x Chandelier)│  (SQN x Volatility x Breadth)   │ (Flip-Cut & Weed) │
└─────────┬─────────┴────────────────┬────────────────┴─────────┬─────────┘
          │                          │                          │
          ▼                          ▼                          ▼
┌───────────────────┐      ┌───────────────────┐      ┌───────────────────┐
│ app/services/     │      │ app/services/     │      │ app/services/     │
│ trade_center_     │      │ market_monitor_   │      │ action_exit_      │
│ service.py        │      │ service.py        │      │ service.py        │
└───────────────────┘      └───────────────────┘      └───────────────────┘
```

---

### Pillar A: Breadth Dynamics & Decision Compass Engine (CELL 3 & 4)

#### 1. Notebook Implementation
- **Breadth Classification** (Lines 220–227):
  Evaluates daily candidate pool trend flags (`ema50`, `ema200`, `trend`) to compute market participation counts:
  - `Old_Long` ($L_1$): `ema50 == '-'` & `trend == '+'` (Dip/Pullback in uptrend)
  - `New_Long` ($L_2$): `ema50 == '+'` & `ema200 == '+'` & `trend == '+'` (Pure Bull Momentum)
  - `Old_Short` ($S_1$): `ema50 == '+'` & `trend == '-'` (Dead-cat bounce in downtrend)
  - `New_Short` ($S_2$): `ema50 == '-'` & `ema200 == '-'` & `trend == '-'` (Pure Bear Momentum)
  - Net Delta: $\Delta = (L_1 + L_2) - (S_1 + S_2)$
- **20-Day Rolling Breadth Statistics** (Lines 311–317):
  Uses `plot_comparison_boxplot.py:calc_stats_20d` against historical median baselines:
  - `Old_Long`: baseline 14.8
  - `Old_Short`: baseline 15.5
  - `New_Long`: baseline 14.5
  - `New_Short`: baseline 37.8
  - `King_Trend_Long`: baseline 30.7
  - `King_Trend_Short`: baseline 14.2
- **Dynamic Compass Returns Engine** (Lines 325–343, `compass_returns_engine.py`):
  Computes expected win rates and returns for 6 strategic setups (`tl`, `ts`, `pb`, `bear`, `kl`, `ks`):
  $$\text{Score}_{\text{Long}} = \text{Return}_{\text{Long}} \times \text{WinRate}_{\text{Norm}}$$
  $$\text{Score}_{\text{Short}} = \text{Return}_{\text{Short}} \times (100 - \text{WinRate}_{\text{Norm}})$$
  - Qualifying threshold: $\text{Score} > 100.0$
  - Mode selection:
    * Long only qualified $\rightarrow$ `mode = LONG` (Target: 4 Long, 0 Short)
    * Short only qualified $\rightarrow$ `mode = SHORT` (Target: 0 Long, 4 Short)
    * Both qualified: Bullish & $L_{cnt} \ge S_{cnt} \rightarrow$ `mode = LONG` (4/0); else `BI-DIRECTIONAL` (2/2)
    * Neither qualified $\rightarrow$ `mode = HOLD CASH` (0/0)

#### 2. Homelab Target Mapping
- **Target Module**: `app/services/strategy_compass_service.py` (New service cleanly adapting `DynamicCompassEngine`)
- **Caller**: `app/services/daily_scenario_runner.py` and `app/mcp/pillars/pillar6_strategy.py`
- **Data Feed**: Daily EOD breadth scan output from candidate scanner.

---

### Pillar B: Drawdown-Guarded 10-Regime & Wave Forensics (CELL 3 & 5)

#### 1. Notebook Implementation
- **10-Regime State Matrix** (Lines 350–397):
  Bivariate classification combining Market SQN (Van Tharp System Quality Number) and 100-day Market Volatility:
  - Volatility dimension: `Volatile` if $\sigma_{100d} > 0.855\%$ baseline; else `Quiet`.
  - Direction dimension:
    * $\text{SQN} > 1.47 \rightarrow$ **Very Bullish**
    * $0.75 \le \text{SQN} \le 1.47 \rightarrow$ **Bullish**
    * $0.00 \le \text{SQN} < 0.75 \rightarrow$ **Neutral**
    * $-0.70 \le \text{SQN} < 0.00 \rightarrow$ **Bearish**
    * $\text{SQN} < -0.70 \rightarrow$ **Very Bearish**
- **Model 18/19 ATR Regime Strategy Mapping** (Lines 386–397):
  | Regime | Active Model / Tactic | Exit Policy |
  |---|---|---|
  | Very Bullish Quiet | `11_V3_Sniper` | `STANDARD` |
  | Very Bullish Volatile | `V6_3_FullUnified` | `FLIP_CUT` |
  | Bullish Quiet | `V6_1_TransitionTight` | `STANDARD` |
  | Bullish Volatile | `V6_2_WaveSqueezeSpring` | `FLIP_CUT` |
  | Neutral Quiet | `12_V4_Macro` | `STANDARD` |
  | Neutral Volatile | `V6_1_TransitionTight` | `STANDARD` |
  | Bearish Quiet | `11_V3_Sniper` | `STANDARD` |
  | Bearish Volatile | `V6_1_TransitionTight` | `STANDARD` |
  | Very Bearish Quiet | `13_V4_1_Harvest` | `STANDARD` |
  | Very Bearish Volatile | `12_V4_Macro` | `FLIP_CUT` |
- **Kinematic Wave Zones & Forensics Overrides** (Lines 462–512):
  - Zone modes: `AGGRESSIVE_LONG`, `AGGRESSIVE_SHORT`, `TRANSITION`, `DEFENSIVE`.
  - Transition Tightening: When regime in `['Neutral Quiet', 'Bearish Quiet', 'Very Bearish Quiet']` and zone is `TRANSITION`, tightens stops ($SL_{mult} = 0.70, TP_{mult} = 1.30$).
  - Squeeze Shield Alert: Detects exhaustion of short thrust ($prev\_opp\_peak \ge 500, run\_pk < 0.65 \times prev$, $SQN \ge 0.70$), immediately zeroes target short and covers existing shorts.
  - Fear & Greed Adjustments: $FG \le 25$ blocks shorts; $FG \ge 70$ constrains leverage to $1.1\times$.

#### 2. Homelab Target Mapping
- **Target Module**: `app/services/market_monitor_service.py` & `app/schemas/intelligence.py`
- **Integration**: Extends market sentiment reporting to classify current 10-regime state during morning pre-market pipeline (09:00–09:30).

---

### Pillar C: Dual-Synergy Chandelier Booster Engine (CELL 3 & 5)

#### 1. Notebook Implementation
- **Chandelier Stop Distance & ATR Normalization** (Lines 169–193):
  - Calculates normalized distance in ATR units: $Dist_{ATR} = \frac{|CS_{dist\%} / 100 \times Price|}{ATR}$
  - Directional Chandelier Step Weights ($w_{cs\_atr}$):
    * $Dist_{ATR} \le 1.0 \rightarrow 5.0$ (Tight to stop / high conviction)
    * $1.0 < Dist_{ATR} \le 1.75 \rightarrow 3.0$
    * $1.75 < Dist_{ATR} \le 2.50 \rightarrow 1.5$
    * $Dist_{ATR} > 2.50 \rightarrow 0.5$ (Extended from stop)
    * Counter-trend side: pinned to $0.05$
- **Dual-Synergy Calculation** (Lines 232–264):
  - Long Synergy: $W_{syn\_long} = W_{dip} \times W_{cs\_atr\_long}$
    where $W_{dip} \in [0.1, 3.0]$ based on Dip Z-Score $Z \le -1.0 \rightarrow 3.0, Z > 0.5 \rightarrow 0.1$.
  - Short Synergy: $W_{syn\_short} = W_{sb\_sniper} \times W_{cs\_atr\_short}$
    where $W_{sb\_sniper} = 5.0$ for pullbacks $2.0\% \le \Delta \le 4.0\%$.
- **Booster Scoring & Candidate Selection** (Lines 600–664):
  - Candidate weight: $bw = W_{syn} \times \max(10.0, SetupScore)$
  - Filter: ATR regime filter (HIGH ATR $\ge 2.0\%$, LOW ATR $< 2.0\%$).
  - Probabilistic Selection: Top $3 \times$ candidate pool, drawn via `np.random.choice(p = bw / sum(bw))` without replacement.
- **Sizing & Point-in-Time House Money** (Lines 588–593, 667):
  - Total slots: 7 concurrent positions.
  - Position allocation: $Cost = \frac{\text{Portfolio Equity} \times Leverage \times SlotMult}{7}$
  - House-Money Trigger: If open portfolio return $> +2.0\%$ and $\ge 2$ positions have breakeven locked $\rightarrow SlotMult \times= 1.25$.

#### 2. Homelab Target Mapping
- **Target Module**: `app/services/trade_center_service.py` & `app/services/order_service.py`
- **Integration**: Feeds scored order candidates into the daily HITL approval pipeline.

---

### Pillar D: Asymmetric Exits, Flip-Cut & Weedouts (CELL 5)

#### 1. Notebook Implementation
- **Breakeven Stop Lock** (Lines 527–529):
  When $Return \ge BE_{trig} \times ATR_{\%}$ (where $BE_{trig} = 0.65$ in Transition Tight, $1.0$ standard), lock stop loss at $0.0\%$ ($BE\_locked = True$).
- **Exit Hierarchy** (Lines 540–568):
  1. `SQUEEZE_SHIELD_COVER`: Emergency short cover on short-squeeze warning.
  2. `MACRO_TIGHT_COVER`: Cover short on positive macro momentum ($FG_w \ge 5$ or $SQN_v \ge 0.10$).
  3. `MINI_WAVE_HARVEST` / `MINI_WAVE_CUT`: Wave days $\le 7$ and low thrust.
  4. `CS_FLIP_CUT` / `CS_LOSER_FLIP_CUT`: Chandelier Stop direction flip ($cs\_dir$ flips opposite to position after $\ge 1$ holding day). Loser-only variant cuts only positions with $Return < 0$.
  5. `TP`: Take profit hit at $TP_{mult} \times ATR_{\%}$ (Default $2.0\times$).
  6. `SL`: Hard stop loss at $-SL_{mult} \times ATR_{\%}$ (Default $1.0\times$).
  7. `BE_SL`: Exit at breakeven if $Return \le 0.0$ after lock.
  8. `RUNWAY`: Time-based decay exit after 10 holding days (7 days in transition tight).
- **Daily Weedout Logic** (Lines 571–586):
  - `WEEDOUT_EXT_GREED`: If Thai Fear & Greed $\ge 75.0$, cut any position with negative return $Return < -0.5\%$.
  - `WEEDOUT_7SLOTS`: If portfolio is at maximum 7 slots, cut the single worst loser ($Return < -1.0\%$) to recycle buying power.

#### 2. Homelab Target Mapping
- **Target Module**: `app/services/action_exit_service.py` & `app/services/action_exit_dispatcher.py`
- **Integration**: Direct match for `ActionExitItem` parsing, evaluation, and queued execution.

---

## 3. Homelab Implementation Roadmap (Loop 3 Pipeline)

Based on this code map, implementation will proceed through the following cards:

| Phase | Task ID | Name | Focus |
|---|---|---|---|
| **3.0a** | `t_49794e8b` | Probe: Model 19 Code Map & Golden Snapshot | Vendor snapshot, neutralize, write code map (THIS CARD) |
| **3.1** | `t_m19_compass` | Core: Compass & 10-Regime Engine | Port `compass_returns_engine` & 10-regime state classifier into `app/services/` |
| **3.2** | `t_m19_booster` | Core: Dual-Synergy Booster & Sizing | Implement Chandelier ATR step weighting & candidate ranking |
| **3.3** | `t_m19_exits` | Core: Flip-Cut & Weedout Action Center | Wire Flip-Cut, Breakeven lock, and Weedout rules into `action_exit_service.py` |
| **3.4** | `t_m19_parity` | Verification: Parity Harness (2023–2026) | Run golden backtest against reference snapshot and verify 100% output parity |

---

## 4. Worker Report (`homelab-build`)

- **Card branch**: `task/loop3-0a-model19-code-map`
- **Files modified/created**:
  1. `reference/model19/18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py` (Neutralized `find_file` & Drive mount)
  2. `reference/model19/MANIFEST.json` (Updated SHA-256 with pristine audit trail)
  3. `docs/handoff/TASK-loop3-0a-model19-code-map.md` (Complete code map documentation)
- **Verification**:
  - All 14 files in `reference/model19/` verified and checksums recorded in `MANIFEST.json`.
  - `18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py` sha256 `5d50f77b2253acf9930fd48fc849d26dc865f60b5543b813b85f62451b6bc028`, bytes 64,314.
  - Pristine sha256 `1ee8915972981852190a7515d8845ea07207834fa6d70ce980c0efce45a6080f` preserved in manifest.
  - 100% logic coverage documented across Compass, 10-Regimes, Dual-Synergy Booster, and Asymmetric Exits.

---

## 5. Review Hand-off
- Ready for `@homelab-review` audit and verification.
