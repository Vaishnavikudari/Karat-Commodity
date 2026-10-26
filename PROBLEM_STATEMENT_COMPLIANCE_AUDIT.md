# Hack in Hills '26 Commodity Derivatives Intelligence — Official Compliance & Audit Report

**System Name:** KARAT  
**Audit Standard:** Hack in Hills '26 — Problem Statement 03: Commodity Derivatives Intelligence  
**Test Suite Status:** 130 passing tests (100% pass rate in `backend/tests/`)  
**Data Scope:** MCX India Bhavcopy Official Gold Futures Series (GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL)  
**Audit Status Legend:**
* **`FULFILLED`**: Verified complete implementation in code with rigorous regression tests and no unresolved financial invariants.
* **`PARTIAL`**: Core calculation implemented, but edge cases or user toggles remain incomplete.
* **`NOT IMPLEMENTED`**: Required functionality is missing.
* **`UNVERIFIED`**: Insufficient test or empirical evidence to verify compliance.

---

## 1. Compliance Matrix by Requirement Area

### 1.1 Cross-Contract Relative Value
| Problem Requirement | Status | Production Implementation | Verification & Test Evidence | Limitations & Financial Caveats |
| :--- | :---: | :--- | :--- | :--- |
| **Normalize contract size, quotation base, and purity** | `FULFILLED` | [`backend/analytics/normaliser.py:28`](file:///backend/analytics/normaliser.py#L28) (`normalise_price`, `normalise_dataframe`)<br>[`backend/data/builder_clean.py:90`](file:///backend/data/builder_clean.py#L90) | `test_official_worked_example`, `test_guinea_and_petal_normalisation` in [`test_analytics.py`](file:///backend/tests/test_analytics.py); `test_6_normalization_formula_accuracy` in [`test_dataset_validation.py`](file:///backend/tests/test_dataset_validation.py). | Prices are standardized to ₹/gram and ₹/10g of 0.999 fine gold benchmark. Formulas mathematically adjust for 995 fineness (`* 999 / 995`). |
| **Identify when one contract appears unusually cheap or expensive relative to another** | `FULFILLED` | [`backend/analytics/spread.py:37`](file:///backend/analytics/spread.py#L37) (`compute_spread_series`)<br>[`backend/analytics/signals.py:40`](file:///backend/analytics/signals.py#L40) (`evaluate_pair_signal`) | `test_pair_spread_all_combinations` in [`test_analytics.py`](file:///backend/tests/test_analytics.py); `test_opportunity_card_four_conditions_validation` in [`test_audit_critical_fixes.py`](file:///backend/tests/test_audit_critical_fixes.py). | Identifies rich/cheap legs using rolling statistical Z-scores ($\|Z\| \ge 2.0$) and requires expected mean-reversion to clear 4-leg transaction friction. |

---

### 1.2 Term Structure & Carry Analytics
| Problem Requirement | Status | Production Implementation | Verification & Test Evidence | Limitations & Financial Caveats |
| :--- | :---: | :--- | :--- | :--- |
| **Analyze the futures curve** | `FULFILLED` | [`backend/analytics/term_structure.py:20`](file:///backend/analytics/term_structure.py#L20) (`get_term_structure`) | `test_term_structure_generation` in [`test_analytics.py`](file:///backend/tests/test_analytics.py); `test_get_curve` in [`test_api.py`](file:///backend/tests/test_api.py). | Builds term structure curves across all maturities, computing annualized roll yield / carry rate `%`. |
| **Separate mechanical roll-down from genuine curve changes** | `FULFILLED` | [`backend/analytics/spread.py:84`](file:///backend/analytics/spread.py#L84) (`carry_adjusted_spread_bps`, `carry_adjusted_z_score`) | `test_carry_adjusted_spread_and_zscore_zero_lookahead` in [`test_audit_compliance_phase2.py`](file:///backend/tests/test_audit_compliance_phase2.py); `test_7_goldm_goldten_comparison_carry_rule` in [`test_dataset_validation.py`](file:///backend/tests/test_dataset_validation.py). | Deducts linear financing roll-down at 6% p.a. standard repo rate based on expiry day differentials ($\Delta \text{Days}$). Computes rolling carry-adjusted Z-score with strict `.shift(1)` zero lookahead. |
| **Historical curve-regime tracking** | `FULFILLED` | [`backend/analytics/term_structure.py:112`](file:///backend/analytics/term_structure.py#L112) (`compute_historical_curve_regimes`)<br>[`backend/api/main.py:401`](file:///backend/api/main.py#L401) (`/api/curve/regimes`) | `test_historical_curve_regimes_tracking`, `test_api_curve_regimes_endpoint` in [`test_audit_compliance_phase2.py`](file:///backend/tests/test_audit_compliance_phase2.py). | Evaluates multi-maturity forward spreads across each trading session; classifies market regimes into Contango, Backwardation, or Flat/Parity. |

---

### 1.3 Contract Lifecycle Planning
| Problem Requirement | Status | Production Implementation | Verification & Test Evidence | Limitations & Financial Caveats |
| :--- | :---: | :--- | :--- | :--- |
| **Track listing dates, liquidity development, tender periods, and expiry** | `FULFILLED` | [`backend/calendar/lifecycle.py:22`](file:///backend/calendar/lifecycle.py#L22) (`get_contract_calendar`, `get_upcoming_expiries_and_roll_windows`) | `test_calendar_lifecycle_fields_present`, `test_upcoming_expiries_calculations` in [`test_calendar.py`](file:///backend/tests/test_calendar.py). | Tracks MCX contract lifecycle milestones: 7 calendar day compulsory delivery tender window, roll windows, and listing boundaries (GOLDTEN post-2025). |
| **Place every intended entry and exit inside the relevant contract calendar** | `FULFILLED` | [`backend/calendar/lifecycle.py:98`](file:///backend/calendar/lifecycle.py#L98) (`validate_trade_calendar`)<br>[`backend/backtest/engine.py:214`](file:///backend/backtest/engine.py#L214) (`_run_strategy`) | `test_trade_rejected_if_entry_in_tender_period`, `test_trade_rejected_if_exit_after_last_trade_date` in [`test_calendar.py`](file:///backend/tests/test_calendar.py); `test_no_entry_inside_tender_window_or_near_expiry` in [`test_audit_compliance_phase2.py`](file:///backend/tests/test_audit_compliance_phase2.py). | Blocks simulation entries inside the tender window or $\le 3$ days from expiry. Validates entry and exit dates against legal contract lifetime. |
| **Mandatory tender-period exit & staggered-expiry unwinding** | `FULFILLED` | [`backend/backtest/engine.py:260`](file:///backend/backtest/engine.py#L260) (`_run_strategy`) | `test_tender_period_mandatory_exit_in_simulation`, `test_staggered_expiry_prevents_unhedged_leg` in [`test_audit_compliance_phase2.py`](file:///backend/tests/test_audit_compliance_phase2.py). | When a position reaches the earlier contract's tender start date, it is forcibly closed (`exit_reason = "tender_period_liquidation"`). Staggered expiries are simultaneously unwound on or before the front leg's expiry (`exit_reason = "staggered_expiry_unwind"`), preventing unhedged naked delta. |

---

### 1.4 Walk-Forward Backtesting
| Problem Requirement | Status | Production Implementation | Verification & Test Evidence | Limitations & Financial Caveats |
| :--- | :---: | :--- | :--- | :--- |
| **Replay historical contracts day-by-day without look-ahead bias** | `FULFILLED` | [`backend/analytics/spread.py:125`](file:///backend/analytics/spread.py#L125)<br>[`backend/backtest/engine.py:101`](file:///backend/backtest/engine.py#L101) (`run_backtest`) | `test_spread_lab_zero_lookahead_regression`, `test_invariant_zero_lookahead_perturbation_and_truncation` in [`test_audit_critical_fixes.py`](file:///backend/tests/test_audit_critical_fixes.py); `test_no_lookahead_rolling` in [`test_karat_real_data.py`](file:///backend/tests/test_karat_real_data.py). | Rolling mean and standard deviation at date $t$ are computed strictly using `.shift(1)` on prior observations $[t-W \dots t-1]$. Zero contemporaneous or future data enters day $t$'s Z-score. In-sample tuning is separated from out-of-sample unseen periods. |
| **Account for transaction costs and thin-day liquidity** | `FULFILLED` | [`backend/backtest/engine.py:228`](file:///backend/backtest/engine.py#L228) (`_run_strategy`, `_compute_metrics`) | `test_backtest_rupee_pnl_both_legs_and_multipliers` in [`test_audit_critical_fixes.py`](file:///backend/tests/test_audit_critical_fixes.py); `test_higher_cost_never_raises_net_pnl` in [`test_backtest.py`](file:///backend/tests/test_backtest.py). | Deducts statutory Indian commodity derivatives friction: Brokerage, STT/CTT, Exchange Turnover Fee, SEBI turnover fees, GST, and Stamp Duty across all 4 legs. Thin days ($\text{Volume} < 50$ or $\text{OI} < 100$) trigger `THIN_LIQUIDITY_SLIPPAGE_MULT = 2.0`, doubling transaction costs. |
| **Rupee P&L with exact lot multipliers** | `FULFILLED` | [`backend/backtest/engine.py:209`](file:///backend/backtest/engine.py#L209) (`_run_strategy`) | `test_invariant_pnl_conservation_across_all_pairs_and_trades` in [`test_audit_critical_fixes.py`](file:///backend/tests/test_audit_critical_fixes.py). | Rupee Gross and Net P&L are computed on both legs using actual physical contract lot sizes ($100\text{g}, 10\text{g}, 8\text{g}, 1\text{g}$) and quotation bases, proving whether gross spread edge survives execution friction. |

---

### 1.5 Trader-Facing Intelligence & Strategy Attribution
| Problem Requirement | Status | Production Implementation | Verification & Test Evidence | Limitations & Financial Caveats |
| :--- | :---: | :--- | :--- | :--- |
| **Build dashboards and alerts highlighting meaningful opportunities** | `FULFILLED` | [`index.html:380`](file:///index.html#L380)<br>[`app.js:1173`](file:///app.js#L1173) | Verified in browser UI; `test_api_explain_panel_endpoint` in [`test_calculations_step1.py`](file:///backend/tests/test_calculations_step1.py). | Surfaces live Daily Briefing, Opportunity Card, and Spread Lab charts with dynamic observation badges and graph explanations. |
| **Keep alerts quiet when there is no meaningful signal** | `FULFILLED` | [`backend/analytics/signals.py:116`](file:///backend/analytics/signals.py#L116) (`evaluate_pair_signal`) | `test_invariant_signal_conjunction_across_all_pairs` in [`test_audit_critical_fixes.py`](file:///backend/tests/test_audit_critical_fixes.py). | **4-Condition Gate**: Defaults to `NO_TRADE` ("Quiet / No Edge") unless: (1) $\|Z\| \ge 2.0$, (2) expected reversion clears 4-leg transaction costs, (3) contracts are liquid, and (4) expiry is $> 3$ days away. |
| **Attribute performance to strategy rather than simply to gold-price movement** | `FULFILLED` | [`backend/backtest/engine.py:475`](file:///backend/backtest/engine.py#L475) (`_compute_attribution`) | `test_attribution_components` in [`test_backtest.py`](file:///backend/tests/test_backtest.py); `test_market_attribution_exposure_indicators_and_caveats` in [`test_audit_compliance_phase2.py`](file:///backend/tests/test_audit_compliance_phase2.py). | Separates `strategy_pnl_bps` from underlying `gold_move_bps`. Measures Pearson correlation between daily spread deltas and daily bullion returns. Explicitly frames correlation as an empirical indicator of market exposure rather than proof of structural market neutrality. |

---

### 1.6 Data Integrity & MCX Specifics
| Problem Requirement | Status | Production Implementation | Verification & Test Evidence | Limitations & Financial Caveats |
| :--- | :---: | :--- | :--- | :--- |
| **Validate returned Date against requested Date (holiday rollover quirk)** | `FULFILLED` | [`backend/data/builder_clean.py:100`](file:///backend/data/builder_clean.py#L100) (`DateMismatchError`) | `test_fetch_one_day_raises_on_date_mismatch`, `test_date_mismatch_rejection_in_clean_file` in [`test_data_pipeline.py`](file:///backend/tests/test_data_pipeline.py). | Rejects Bhavcopy files where the returned payload date rolls back to a prior trading session due to exchange holiday queries. |
| **Date formats (`DD/MM/YYYY`, `MM/DD/YYYY`, compact `04SEP2026`) & space-padded symbols** | `FULFILLED` | [`backend/data/parser.py:48`](file:///backend/data/parser.py#L48)<br>[`backend/data/builder_clean.py:60`](file:///backend/data/builder_clean.py#L60) | `test_standard_mcx_format`, `test_all_months`, `test_space_padded_symbol_cleaned` in [`test_data_pipeline.py`](file:///backend/tests/test_data_pipeline.py). | Dual-format regex parser cleans space padding (e.g., `"GOLDM   "`) and standardizes both compact and ISO date formats. |
| **Track contracts by `expiry_date` (no continuous near-month series)** | `FULFILLED` | [`backend/data/builder_clean.py:188`](file:///backend/data/builder_clean.py#L188) | `test_multiple_expiries_not_double_counting_trading_days` in [`test_dataset_validation.py`](file:///backend/tests/test_dataset_validation.py). | Preserves distinct discrete contracts keyed by `(symbol, expiry_date)`, eliminating artificial roll jumps found in stitched continuous series. |
| **Settlement marks $\neq$ executable fills; Volume $\neq$ market depth** | `FULFILLED` | [`backend/backtest/engine.py:149`](file:///backend/backtest/engine.py#L149)<br>[`index.html:568`](file:///index.html#L568)<br>[`app.js:1314`](file:///app.js#L1314) | Documented across all UI panels, API headers, and backtester slippage multipliers. | Explicitly states that exchange Bhavcopy reflects official closing marks and total lots, not Level 2 order book liquidity. |
| **GOLDTEN listing from 2025 onwards (shorter history)** | `FULFILLED` | [`backend/calendar/lifecycle.py:18`](file:///backend/calendar/lifecycle.py#L18)<br>[`backend/analytics/position_matcher.py:270`](file:///backend/analytics/position_matcher.py#L270) | `test_goldten_entry_before_2025_listing_rejected` in [`test_calendar.py`](file:///backend/tests/test_calendar.py); `test_goldten_before_april_2025_not_required_for_completeness` in [`test_data_pipeline.py`](file:///backend/tests/test_data_pipeline.py). | Enforces 2025 listing start boundary; dynamically sizes rolling windows when GOLDTEN history is shorter. |

---

## 2. Reconciled Audit Discrepancies

| Prior Audit Item | Earlier Reported Status | Reconciled Finding | Corrective Action Implemented |
| :--- | :---: | :--- | :--- |
| **Tender Period Liquidation in Simulation** | `PARTIAL` | `_run_strategy` previously only exited on statistical mean reversion or max holding period. Open trades could theoretically hold through tender notice into physical delivery. | Added mandatory tender period liquidation rule (`curr_d >= earlier_tender_start`) with `exit_reason = "tender_period_liquidation"`. Also blocked entries inside tender window or $\le 3$ days to expiry. Status upgraded to **`FULFILLED`**. |
| **Staggered-Expiry Unhedged Leg Risk** | `PARTIAL` | When pairing legs with different expiry dates, if the earlier contract matured, the other leg was not guaranteed to exit simultaneously in simulation. | Added simultaneous unwinding rule (`curr_d >= earlier_expiry`) with `exit_reason = "staggered_expiry_unwind"`, ensuring neither leg is ever held unhedged. Status upgraded to **`FULFILLED`**. |
| **Carry-Adjusted Z-Scores** | `PARTIAL` | `carry_adjusted_spread_bps` existed in the DataFrame, but Z-scores were computed only on raw spread bps, carrying baseline drift for cross-maturity pairs. | Added `carry_adjusted_z_score` computed with strict zero-lookahead, and added `use_carry_adj` parameter toggle to `compute_spread_series` and `run_backtest`. Status upgraded to **`FULFILLED`**. |
| **Historical Curve Regime Tracking** | `PARTIAL` | System only computed forward curve snapshots on single dates, without tracking historical slope evolution over time. | Implemented `compute_historical_curve_regimes` in `term_structure.py` and exposed `/curve/regimes` and `/api/curve/regimes` endpoints. Status upgraded to **`FULFILLED`**. |
| **Market Neutrality Attribution Claim** | `PARTIAL` | Wording previously described Pearson correlation $< 0.25$ as "market neutrality", which could be interpreted as structural immunity. | Updated to explicitly describe correlation as an empirical indicator of directional market exposure, adding prominent analytical caveats. Status upgraded to **`FULFILLED`**. |
| **UI Methodology Formula Alignment** | `PARTIAL` | Methodology card in `index.html` displayed `Mean[t-19...t]`, conflicting with the zero-lookahead production implementation (`.shift(1)` using prior observations strictly before day $t$). | Corrected formula in `index.html` to `Mean[t-W...t-1] / StdDev[t-W...t-1]` with updated explanatory text. Status upgraded to **`FULFILLED`**. |

---

## 3. Test Suite Progression Summary

* **Before Phase 1 Critical Fixes:** 117 passing tests.
* **After Phase 1 Critical Fixes:** 122 passing tests.
* **After Phase 2 Compliance Fixes:** **130 passing tests (0 failures, 0 regressions in 20.79s)**.
  - Added 8 dedicated regression tests in [`backend/tests/test_audit_compliance_phase2.py`](file:///backend/tests/test_audit_compliance_phase2.py) covering mandatory tender liquidation, staggered-expiry risk management, carry-adjusted Z-scores, historical curve regimes, and market exposure caveats.

---

## 4. Remaining Market Risks & Recommended Enhancements

1. **Intraday Tick Execution (Level 2 Order Book):**  
   Exchange Bhavcopy only provides end-of-day settlement marks. For live automated market making, integration with an intraday tick feed (Level 2 order book) is recommended to measure real-time top-of-book bid-ask spreads.
2. **Dynamic Volatility-Scaled Stop Losses:**  
   Currently, the maximum holding period uses a fixed calendar-day time stop (`TIME_STOP_DAYS = 10`). Implementing an ATR- or realized-volatility-scaled stop loss would enhance drawdown mitigation during macroeconomic shocks.
