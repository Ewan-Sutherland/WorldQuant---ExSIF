from __future__ import annotations

TEMPLATE_LIBRARY: dict[str, list[dict[str, str]]] = {
    "mean_reversion": [
        {"template_id": "mr_01", "expression": "rank(ts_mean(close, {n}) - close)"},
        {"template_id": "mr_02", "expression": "rank(-ts_delta(close, {n}))"},
        {"template_id": "mr_03", "expression": "rank(-(close / ts_mean(close, {n}) - 1))"},
        {"template_id": "mr_04", "expression": "rank(-(returns - ts_mean(returns, {n})))"},
    ],
    "cross_sectional": [
        {"template_id": "cs_01", "expression": "-rank(ts_zscore(close, {n}))"},
        {"template_id": "cs_02", "expression": "-rank(ts_zscore(returns, {n}))"},
        {"template_id": "cs_03", "expression": "rank(ts_mean(returns, {m}) - ts_mean(returns, {n}))"},
        {"template_id": "cs_04", "expression": "group_rank(-ts_zscore(close, {n}), subindustry)"},
    ],
    "liquidity_scaled": [
        {"template_id": "liq_01", "expression": "rank(-(returns - ts_mean(returns, {n})) * rank(adv20))"},
        {"template_id": "liq_02", "expression": "rank(-ts_zscore(returns, {n}) * rank(cap))"},
        {"template_id": "liq_03", "expression": "rank((ts_mean(close, {n}) - close) * rank(adv20) / (ts_std_dev(returns, {m}) + 0.001))"},
    ],
    "conditional": [
        {"template_id": "cond_01", "expression": "trade_when(volume > ts_mean(volume, {n}), rank(-returns), -1)"},
        {"template_id": "cond_02", "expression": "trade_when(abs(returns) > ts_std_dev(returns, {n}), rank(-returns), -1)"},
        {"template_id": "cond_03", "expression": "trade_when(volume > ts_mean(volume, {n}), rank(ts_delta(close, {m})), -1)"},
    ],
    "vol_adjusted": [
        {"template_id": "va_01", "expression": "rank(ts_delta(close, {n}) / ts_std_dev(returns, {m}))"},
        {"template_id": "va_02", "expression": "rank((ts_mean(close, {n}) - close) / ts_std_dev(returns, {m}))"},
    ],
    "fundamental_value": [
        {"template_id": "fv_01", "expression": "ts_zscore({deep_field} / cap, {n})"},
        {"template_id": "fv_02", "expression": "rank(ts_delta({deep_field}, {n}) / ({deep_field} + 0.001))"},
        {"template_id": "fv_03", "expression": "-rank(close / ({deep_field} + 0.001))"},
        {"template_id": "fv_04", "expression": "group_rank(-ts_zscore({deep_field}, {n}), industry)"},
        {"template_id": "fv_05", "expression": "ts_rank({deep_field} / cap, 252)"},
        {"template_id": "fv_06", "expression": "group_rank(ts_rank({deep_field} / cap, 252), subindustry)"},
        {"template_id": "fv_07", "expression": "rank({deep_field} / enterprise_value)"},
    ],
    "size_value": [
        {"template_id": "sv_01", "expression": "rank(ts_zscore(eps / close, {n}))"},
        {"template_id": "sv_02", "expression": "rank(ts_delta(ebitda / enterprise_value, {n}))"},
        {"template_id": "sv_03", "expression": "-rank(ts_zscore(close / (bookvalue_ps + 0.001), {n}))"},
    ],
    "quality_trend": [
        {"template_id": "qt_01", "expression": "rank(ts_delta(cashflow_op / assets, {n}))"},
        {"template_id": "qt_02", "expression": "rank(ts_delta(current_ratio, {n}))"},
        {"template_id": "qt_03", "expression": "rank(cashflow_op / (income + 0.001))"},
        {"template_id": "qt_04", "expression": "ts_rank(cashflow_op / debt, 252)"},
        {"template_id": "qt_05", "expression": "rank(ts_delta(equity / assets, {n}))"},
        {"template_id": "qt_06", "expression": "group_rank(ts_rank(cashflow_op / debt, 252), subindustry)"},
    ],
    "fundamental_scores": [
        {"template_id": "fs_01", "expression": "rank(ts_delta({fscore_field}, {n}))"},
        {"template_id": "fs_02", "expression": "rank(ts_zscore({fscore_field}, {n}))"},
        {"template_id": "fs_03", "expression": "group_rank(-ts_zscore({fscore_field}, {n}), industry)"},
        {"template_id": "fs_04", "expression": "rank(ts_zscore({fscore_field}, {n})) * rank(cap)"},
        {"template_id": "fs_05", "expression": "rank(ts_zscore({fscore_field}, {n})) * rank(adv20)"},
        {"template_id": "fs_06", "expression": "rank(ts_zscore({fscore_field}, {n}) * rank(cap))"},
        {"template_id": "fs_07", "expression": "rank({derivative_field}) * rank(adv20)"},
        {"template_id": "fs_08", "expression": "ts_decay_linear(rank({derivative_field}) * rank(cap), {n})"},
    ],
    "earnings_momentum": [
        {"template_id": "em_01", "expression": "rank(snt1_d1_netearningsrevision)"},
        {"template_id": "em_02", "expression": "rank(ts_delta(snt1_d1_earningssurprise, {n}))"},
        {"template_id": "em_03", "expression": "rank(snt1_d1_dynamicfocusrank)"},
        {"template_id": "em_04", "expression": "ts_decay_linear(rank(consensus_analyst_rating), {n})"},
        {"template_id": "em_05", "expression": "rank(snt1_d1_stockrank)"},
        {"template_id": "em_06", "expression": "rank(ts_zscore(snt1_d1_netearningsrevision, {n}))"},
        {"template_id": "em_07", "expression": "group_rank(snt1_d1_earningssurprise, subindustry)"},
        {"template_id": "em_08", "expression": "rank(ts_decay_linear(snt1_d1_earningssurprise, 60))"},
        {"template_id": "em_09", "expression": "rank(ts_decay_linear(snt1_d1_earningssurprise, 60)) + rank(ts_decay_linear(snt1_d1_netearningsrevision, 40))"},
    ],
    "options_vol": [
        {"template_id": "opt_01", "expression": "rank(ts_backfill(implied_volatility_call_{opt_window}, 60) - ts_backfill(implied_volatility_put_{opt_window}, 60))"},
        {"template_id": "opt_02", "expression": "rank(ts_backfill(implied_volatility_call_{opt_window}, 60) / (ts_backfill(historical_volatility_{opt_window}, 60) + 0.001))"},
        {"template_id": "opt_03", "expression": "rank((ts_backfill(implied_volatility_call_{opt_window}, 60) - ts_backfill(implied_volatility_put_{opt_window}, 60)) * rank(adv20))"},
        {"template_id": "opt_04", "expression": "rank((ts_backfill(implied_volatility_call_{opt_window}, 60) / (ts_backfill(historical_volatility_{opt_window}, 60) + 0.001)) * rank(adv20))"},
        {"template_id": "opt_05", "expression": "trade_when(ts_arg_max(ts_backfill(pcr_vol_{pcr_window}, 60), 7) < 1, rank(-returns), -1)"},
        {"template_id": "opt_06", "expression": "ts_decay_linear(ts_delta(ts_backfill(implied_volatility_call_{opt_window}, 60), 25) > 0, 20)"},
        {"template_id": "opt_07", "expression": "rank(-ts_backfill(pcr_oi_{pcr_window}, 60)) * rank(adv20)"},
        {"template_id": "opt_08", "expression": "rank(ts_backfill(implied_volatility_mean_skew_{opt_window}, 60)) * rank(cap)"},
        {"template_id": "opt_09", "expression": "trade_when(ts_backfill(pcr_oi_270, 60) < 1, ts_backfill(implied_volatility_call_270, 60) - ts_backfill(implied_volatility_put_270, 60), -1)"},
    ],
    "news_sentiment": [
        {"template_id": "ns_01", "expression": "rank(ts_backfill(scl12_sentiment, 60))"},
        {"template_id": "ns_02", "expression": "rank(ts_delta(ts_backfill(scl12_buzz, 60), {n}))"},
        {"template_id": "ns_03", "expression": "rank(ts_backfill(rp_ess_earnings, 60))"},
        {"template_id": "ns_04", "expression": "ts_decay_linear(rank(ts_backfill(news_pct_1min, 60)), {n})"},
        {"template_id": "ns_05", "expression": "rank(ts_backfill(snt_buzz_bfl, 60)) * rank(adv20)"},
        {"template_id": "ns_06", "expression": "rank(ts_backfill(rp_css_earnings, 60) - ts_backfill(rp_css_credit, 60))"},
        {"template_id": "ns_07", "expression": "-ts_std_dev(ts_backfill(scl12_buzz, 60), {n})"},
        {"template_id": "ns_08", "expression": "-rank(ts_backfill(scl12_buzz, 60) / (ts_mean(ts_backfill(scl12_buzz, 60), {n}) + 0.001))"},
    ],
    "vol_regime": [
        {"template_id": "vr_01", "expression": "trade_when(ts_rank(ts_std_dev(returns, 22), 252) > 0.55, -ts_regression(returns, ts_delay(returns, 1), 252, rettype=2), -1)"},
        {"template_id": "vr_02", "expression": "trade_when(ts_rank(ts_std_dev(returns, {n}), 252) > 0.5, rank(-returns), -1)"},
        {"template_id": "vr_03", "expression": "rank(-ts_regression(returns, ts_delay(returns, 1), {n}, rettype=2))"},
        {"template_id": "vr_04", "expression": "rank(ts_regression(close, ts_step(1), {n}, rettype=2))"},
    ],
    "combo_factor": [
        {"template_id": "cf_01", "expression": "-rank(close / {deep_field}) + -rank(ts_mean(returns, {n}))"},
        {"template_id": "cf_02", "expression": "-rank(ts_zscore({deep_field}, {n})) + -rank(ts_mean((close - vwap) / vwap, {m}))"},
        {"template_id": "cf_03", "expression": "rank({deep_field} / assets) + -rank(ts_mean((close - vwap) / vwap, {n}))"},
        {"template_id": "cf_04", "expression": "rank({deep_field} / cap) + -rank(ts_mean(returns, {n}))"},
        {"template_id": "cf_05", "expression": "rank({deep_field} / cap) + rank(trade_when(ts_rank(ts_std_dev(returns, 22), 252) > 0.5, rank(-returns), -1))"},
        {"template_id": "cf_06", "expression": "rank(snt1_d1_netearningsrevision) + -rank(ts_mean(returns, {n}))"},
        {"template_id": "cf_07", "expression": "rank(snt1_d1_dynamicfocusrank) + -rank(ts_mean((close - vwap) / vwap, {n}))"},
        {"template_id": "cf_08", "expression": "rank(ts_backfill(implied_volatility_call_{opt_window}, 60) / (ts_backfill(historical_volatility_{opt_window}, 60) + 0.001)) + -rank(ts_mean(returns, {n}))"},
        {"template_id": "cf_09", "expression": "rank(ts_zscore({fscore_field}, {n})) * rank(adv20) + -rank(ts_mean(returns, {m}))"},
        {"template_id": "cf_10", "expression": "rank(ts_backfill(scl12_sentiment, 60)) + rank({deep_field} / cap)"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # v5.9 NEW FAMILIES
    # ══════════════════════════════════════════════════════════════════
    "model77_anomaly": [
        {"template_id": "m77_01", "expression": "rank({model77_field})"},
        {"template_id": "m77_02", "expression": "-rank({model77_field})"},
        {"template_id": "m77_03", "expression": "rank(ts_zscore({model77_field}, {n}))"},
        {"template_id": "m77_04", "expression": "rank(ts_delta({model77_field}, {n}))"},
        {"template_id": "m77_05", "expression": "ts_decay_linear(rank({model77_field}), {n})"},
        {"template_id": "m77_06", "expression": "group_rank({model77_field}, industry)"},
        {"template_id": "m77_07", "expression": "group_rank({model77_field}, subindustry)"},
        {"template_id": "m77_08", "expression": "rank({model77_field}) * rank(adv20)"},
        {"template_id": "m77_09", "expression": "rank({model77_field}) * rank(cap)"},
    ],
    "model77_combo": [
        # Additive (original)
        {"template_id": "m7c_01", "expression": "rank({model77_field}) + -rank(ts_mean(returns, {m}))"},
        {"template_id": "m7c_02", "expression": "-rank({model77_field}) + -rank(ts_mean(returns, {m}))"},
        {"template_id": "m7c_03", "expression": "rank({model77_field}) + rank(trade_when(ts_rank(ts_std_dev(returns, 22), 252) > 0.5, rank(-returns), -1))"},
        {"template_id": "m7c_04", "expression": "group_rank({model77_field}, industry) + -rank(ts_mean((close - vwap) / vwap, {m}))"},
        # v5.9.1: MULTIPLICATIVE combos (research: outperform additive)
        {"template_id": "m7c_05", "expression": "rank({model77_field}) * rank(-ts_mean(returns, {m}))"},
        {"template_id": "m7c_06", "expression": "rank({model77_field}) * rank(trade_when(ts_rank(ts_std_dev(returns, 22), 252) > 0.5, rank(-returns), -1))"},
        {"template_id": "m7c_07", "expression": "rank(group_zscore({model77_field}, industry) * group_zscore(-returns, industry))"},
        {"template_id": "m7c_08", "expression": "rank(group_zscore({model77_field}, subindustry) * group_zscore(-ts_mean(returns, {m}), subindustry))"},
        # v5.9.1: Q-theory composite (Hou, Xue & Zhang — strongest academic signal)
        {"template_id": "m7c_09", "expression": "rank(gross_profit_to_assets_ratio) - rank(asset_growth_rate)"},
        {"template_id": "m7c_10", "expression": "rank(gross_profit_to_assets_ratio) - rank(asset_growth_rate) + rank(-ts_mean(returns, {m}))"},
        {"template_id": "m7c_11", "expression": "group_rank(gross_profit_to_assets_ratio, subindustry) - group_rank(asset_growth_rate, subindustry)"},
        # v5.9.1: Earnings quality × value (multiplicative model77 × model77)
        {"template_id": "m7c_12", "expression": "rank(five_year_eps_stability * forward_ebitda_to_enterprise_value_2)"},
        {"template_id": "m7c_13", "expression": "rank(five_year_eps_stability * forward_ebitda_to_enterprise_value_2) * rank(-ts_mean(returns, {m}))"},
        # v5.9.1: 3-signal composites (weak signals → strong combined)
        {"template_id": "m7c_14", "expression": "rank({model77_field}) + rank(gross_profit_to_assets_ratio) + rank(-ts_mean(returns, {m}))"},
        {"template_id": "m7c_15", "expression": "rank({model77_field}) + rank(-asset_growth_rate) + rank(-ts_mean(returns, {m}))"},
    ],
    "relationship": [
        {"template_id": "rel_01", "expression": "rank(rel_ret_cust)"},
        {"template_id": "rel_02", "expression": "-rank(rel_ret_comp)"},
        {"template_id": "rel_03", "expression": "rank(ts_delta(rel_ret_cust, {n}))"},
        {"template_id": "rel_04", "expression": "rank(ts_zscore(rel_ret_cust, {n}))"},
        {"template_id": "rel_05", "expression": "rank(rel_ret_cust) * rank(rel_num_cust)"},
        {"template_id": "rel_06", "expression": "rank(pv13_ustomergraphrank_page_rank) * rank(adv20)"},
        {"template_id": "rel_07", "expression": "rank(rel_ret_cust) + -rank(ts_mean(returns, {m}))"},
        {"template_id": "rel_08", "expression": "-rank(rel_ret_comp) + -rank(ts_mean(returns, {m}))"},
        # v5.9.1: Decayed customer momentum (Cohen & Frazzini 2008 — 150bp monthly)
        {"template_id": "rel_09", "expression": "ts_decay_linear(ts_mean(rel_ret_cust, 5), 10)"},
        {"template_id": "rel_10", "expression": "ts_decay_linear(rank(rel_ret_cust) - rank(rel_ret_comp), 10)"},
        # v5.9.1: Multiplicative customer momentum × profitability
        {"template_id": "rel_11", "expression": "rank(ts_decay_linear(rel_ret_cust, 10) * group_zscore(operating_income / (sales + 0.001), sector))"},
    ],
    "risk_beta": [
        {"template_id": "rb_01", "expression": "-rank(beta_last_60_days_spy)"},
        {"template_id": "rb_02", "expression": "-rank(beta_last_360_days_spy)"},
        {"template_id": "rb_03", "expression": "rank(unsystematic_risk_last_60_days)"},
        {"template_id": "rb_04", "expression": "-rank(ts_zscore(beta_last_60_days_spy, {n}))"},
        {"template_id": "rb_05", "expression": "-rank(correlation_last_60_days_spy) * rank(adv20)"},
        {"template_id": "rb_06", "expression": "-rank(beta_last_60_days_spy) + rank({deep_field} / cap)"},
        {"template_id": "rb_07", "expression": "-rank(beta_last_60_days_spy) + -rank(ts_mean(returns, {m}))"},
    ],
    "expanded_fundamental": [
        {"template_id": "ef_01", "expression": "rank(cashflow_op / assets) - rank(income / assets)"},
        {"template_id": "ef_02", "expression": "-group_rank(ts_delta(assets, 252) / (ts_delay(assets, 252) + 0.001), subindustry)"},
        {"template_id": "ef_03", "expression": "-rank(ts_delta(sharesout, 252) / (ts_delay(sharesout, 252) + 0.001))"},
        {"template_id": "ef_04", "expression": "rank((sales - cogs) / assets)"},
        {"template_id": "ef_05", "expression": "group_rank((sales - cogs) / assets, subindustry)"},
        {"template_id": "ef_06", "expression": "-ts_rank(retained_earnings, 500)"},
        {"template_id": "ef_07", "expression": "rank(rd_expense / cap)"},
        {"template_id": "ef_08", "expression": "rank(ts_delta(working_capital / assets, {n}))"},
        {"template_id": "ef_09", "expression": "rank(ts_delta(inventory_turnover, {n}))"},
        {"template_id": "ef_10", "expression": "group_rank((sales - ebitda) / assets, subindustry)"},
        {"template_id": "ef_11", "expression": "-ts_zscore(enterprise_value / (ebitda + 0.001), 63)"},
        {"template_id": "ef_12", "expression": "-rank(ebit / (capex + 0.001))"},
        {"template_id": "ef_13", "expression": "rank(cashflow_op / enterprise_value)"},
        {"template_id": "ef_14", "expression": "rank(sales / assets) + rank(bookvalue_ps / close)"},
        # v5.9.1: R&D intensity (Lev & Sougiannis — 1.52% monthly FF5 alpha)
        {"template_id": "ef_15", "expression": "group_rank(rd_expense / (sales + 0.001), industry)"},
        {"template_id": "ef_16", "expression": "rank(rd_expense / (sales + 0.001)) * rank(1 / (tobins_q_ratio + 0.001))"},
        # v5.9.1: Piotroski-style 3-factor quality composite
        {"template_id": "ef_17", "expression": "rank(group_zscore(cashflow_op / assets, subindustry) + group_zscore(operating_income / (sales + 0.001), subindustry) - group_zscore(debt / assets, subindustry))"},
        # v5.9.1: Altman Z-Score composite
        {"template_id": "ef_18", "expression": "rank(1.2 * working_capital / (assets + 0.001) + 1.4 * retained_earnings / (assets + 0.001) + 3.3 * ebit / (assets + 0.001))"},
    ],
    "analyst_estimates": [
        {"template_id": "ae_01", "expression": "group_rank(ts_rank(est_eps / close, 60), industry)"},
        {"template_id": "ae_02", "expression": "ts_decay_linear(ts_scale(est_cashflow_op, 252), 22) - ts_decay_linear(ts_scale(est_capex, 252), 22)"},
        {"template_id": "ae_03", "expression": "-ts_corr(est_ptp, est_fcf, 252)"},
        {"template_id": "ae_04", "expression": "rank(ts_zscore(est_fcf / cap, {n}))"},
        {"template_id": "ae_05", "expression": "rank(est_eps / close) + rank(snt1_d1_netearningsrevision)"},
    ],
    "wq_proven": [
        {"template_id": "wp_01", "expression": "group_rank(-ts_zscore(enterprise_value / cashflow, 63), industry)"},
        {"template_id": "wp_02", "expression": "ts_backfill(implied_volatility_call_120, 60) / (ts_backfill(parkinson_volatility_120, 60) + 0.001)"},
        {"template_id": "wp_03", "expression": "ts_regression(ts_sum(ts_backfill(operating_income, 60), 252), ts_step(1), 756, rettype=2)"},
        {"template_id": "wp_04", "expression": "winsorize(-ts_backfill(news_max_up_ret, 60) * abs(ts_regression(ts_backfill(news_pct_1min, 60), ts_step(1), 5, rettype=2)), std=4)"},
        {"template_id": "wp_05", "expression": "ts_rank(operating_income / cap, 252)"},
        {"template_id": "wp_06", "expression": "-ts_rank(fn_liab_fair_val_l1_a, 252)"},
    ],
    "momentum": [
        {"template_id": "mom_01", "expression": "rank(ts_delta(close, {n}))"},
        {"template_id": "mom_02", "expression": "rank(ts_rank(close, {n}))"},
        {"template_id": "mom_03", "expression": "rank(ts_mean(returns, {n}))"},
    ],
    "volume_flow": [
        {"template_id": "vol_01", "expression": "rank(volume / ts_mean(volume, {n}))"},
        {"template_id": "vol_02", "expression": "rank(ts_delta(volume, {n}) * returns)"},
        {"template_id": "vol_03", "expression": "rank((volume / ts_mean(volume, {n})) * -returns)"},
    ],
    "price_vol_corr": [
        {"template_id": "pvc_01", "expression": "-rank(ts_corr(rank(close), rank(volume), {n}))"},
        {"template_id": "pvc_02", "expression": "rank(ts_corr(ts_delta(close, {m}), volume, {n}))"},
        {"template_id": "pvc_03", "expression": "-rank(ts_corr(vwap, volume, {n}))"},
        {"template_id": "pvc_04", "expression": "-rank((close - vwap) / (vwap + 0.001) * log(volume + 1))"},
    ],
    "volatility": [
        {"template_id": "vlty_01", "expression": "rank(1 / (ts_std_dev(returns, {n}) + 0.001))"},
        {"template_id": "vlty_04", "expression": "rank(ts_mean(returns, {m}) / (ts_std_dev(returns, {n}) + 0.001))"},
    ],
    "intraday": [
        {"template_id": "iday_01", "expression": "rank(-(high - low) / (close + 0.001))"},
        {"template_id": "iday_02", "expression": "rank((close - low) / (high - low + 0.001))"},
        {"template_id": "iday_03", "expression": "-rank(ts_mean(high - low, {n}) / (close + 0.001))"},
        {"template_id": "iday_04", "expression": "rank(open / close - 1)"},
        {"template_id": "iday_05", "expression": "-rank(ts_mean(open / close - 1, {n}))"},
    ],
    "fundamental": [
        {"template_id": "fund_01", "expression": "rank({field})"},
        {"template_id": "fund_02", "expression": "rank(ts_delta({field}, {n}))"},
        {"template_id": "fund_03", "expression": "rank(({field} - ts_mean({field}, {n})))"},
    ],
    "analyst_sentiment": [
        {"template_id": "ans_01", "expression": "rank(ts_delta({analyst_field}, {n}))"},
        {"template_id": "ans_02", "expression": "-rank({sentiment_field} / (ts_mean({sentiment_field}, {n}) + 0.001))"},
        {"template_id": "ans_03", "expression": "rank(ts_zscore({analyst_field}, {n}))"},
    ],
}

# ── Field lists ───────────────────────────────────────────────────────

FUNDAMENTAL_FIELDS = ["cap", "assets", "sales", "income", "cash"]

DEEP_FUNDAMENTAL_FIELDS = [
    "cashflow_op", "ebit", "ebitda", "enterprise_value",
    "bookvalue_ps", "debt", "equity", "current_ratio",
    "eps", "capex", "cashflow", "cogs", "cash_st",
]

ANALYST_FIELDS = [
    "snt1_d1_earningssurprise", "snt1_d1_netearningsrevision",
    "snt1_d1_dynamicfocusrank", "consensus_analyst_rating",
    "snt1_d1_earningsrevision", "snt1_d1_stockrank",
]

SENTIMENT_FIELDS = ["scl12_buzz", "scl12_sentiment", "snt_social_value"]

FSCORE_FIELDS = [
    "fscore_bfl_value", "fscore_bfl_momentum", "fscore_bfl_quality",
    "fscore_bfl_growth", "fscore_bfl_profitability", "fscore_bfl_total",
]

DERIVATIVE_FIELDS = [
    "cashflow_efficiency_rank_derivative",
    "composite_factor_score_derivative",
    "earnings_certainty_rank_derivative",
    "growth_potential_rank_derivative",
    "analyst_revision_rank_derivative",
    "relative_valuation_rank_derivative",
]

OPTIONS_WINDOWS = [30, 60, 90, 120, 180]
PCR_WINDOWS = [10, 30, 60, 90, 120, 180, 270]

# v5.9: model77 pre-computed anomaly fields — Tier 1 (highest expected impact)
MODEL77_TIER1_FIELDS = [
    "standardized_unexpected_earnings", "standardized_unexpected_earnings_2",
    "earnings_momentum_composite_score", "earnings_momentum_analyst_score",
    "earnings_revision_magnitude", "sales_surprise_score",
    "change_in_eps_surprise", "net_fy1_analyst_revisions",
    "three_month_fy1_eps_revision", "six_month_avg_fy1_eps_revision",
    "forward_median_earnings_yield", "normalized_earnings_yield",
    "forward_cash_flow_to_price", "forward_ebitda_to_enterprise_value_2",
    "tobins_q_ratio", "financial_statement_value_score",
    "equity_value_score", "income_statement_value_score",
    "gross_profit_to_assets_ratio", "gross_profit_margin_ttm_2",
    "cash_flow_return_on_invested_capital", "cash_earnings_return_on_equity",
    "return_on_invested_capital_4", "fcf_yield_times_forward_roe",
    "asset_growth_rate", "one_year_change_total_assets",
    "sustainable_growth_rate", "reinvestment_rate",
    "distress_risk_measure", "credit_risk_premium_indicator",
    "twelve_month_short_interest_change",
    "value_momentum_analyst_score", "momentum_analyst_composite_score",
    "price_momentum_module_score", "fundamental_growth_module_score",
]

MODEL77_TIER2_FIELDS = [
    "trailing_twelve_month_accruals",
    "standardized_unexpected_cash_flow", "standardized_unexpected_cashflow",
    "book_leverage_ratio_3", "interest_coverage_ratio_5",
    "yearly_change_leverage", "twelve_month_total_debt_change_2",
    "five_year_eps_stability", "one_year_eps_growth_rate",
    "forward_two_year_eps_growth", "one_year_ahead_eps_growth",
    "one_quarter_ahead_eps_growth", "long_term_growth_estimate",
    "capex_to_total_assets", "capex_to_depreciation_linkage",
    "ttm_operating_cash_flow_to_price", "ttm_operating_income_to_ev",
    "ttm_sales_to_enterprise_value",
    "implied_minus_realized_volatility_2", "implied_option_volatility",
    "out_of_money_put_call_ratio",
    "industry_relative_return_4w", "industry_relative_return_5d",
    "industry_relative_book_to_market", "industry_relative_fcf_to_price",
    "cash_burn_rate", "inventory_change_avg_assets",
    "rd_expense_to_sales_2", "visibility_ratio", "treynor_ratio",
]

MODEL77_ALL_FIELDS = MODEL77_TIER1_FIELDS + MODEL77_TIER2_FIELDS

# Direction: fields where HIGHER value = LOWER expected returns (need -rank)
MODEL77_NEGATIVE_DIRECTION = {
    "asset_growth_rate", "one_year_change_total_assets",
    "trailing_twelve_month_accruals", "twelve_month_total_debt_change_2",
    "yearly_change_leverage", "distress_risk_measure",
    "credit_risk_premium_indicator", "twelve_month_short_interest_change",
    "cash_burn_rate", "book_leverage_ratio_3",
    "implied_minus_realized_volatility_2",
}

SAFE_PARAM_RANGES = {
    "n": [3, 5, 10, 20, 40, 60],
    "m": [5, 10, 20, 60],
}

FUNDAMENTAL_PARAM_RANGES = {
    "n": [60, 120, 180, 252],
    "m": [60, 120, 252],
}

# v5.9: Dataset-aware neutralization (from official Neutralisation.csv)
DATASET_NEUTRALIZATION = {
    "fundamental_value": ["INDUSTRY", "SUBINDUSTRY"],
    "quality_trend": ["INDUSTRY", "SUBINDUSTRY"],
    "size_value": ["INDUSTRY", "SUBINDUSTRY"],
    "expanded_fundamental": ["INDUSTRY", "SUBINDUSTRY"],
    "fundamental": ["INDUSTRY", "SUBINDUSTRY"],
    "earnings_momentum": ["INDUSTRY", "NONE"],
    "analyst_sentiment": ["INDUSTRY", "SUBINDUSTRY"],
    "analyst_estimates": ["INDUSTRY", "SUBINDUSTRY"],
    "fundamental_scores": ["SUBINDUSTRY", "INDUSTRY", "MARKET", "SECTOR"],
    "model77_anomaly": ["INDUSTRY", "SUBINDUSTRY", "MARKET", "SECTOR"],
    "model77_combo": ["INDUSTRY", "SUBINDUSTRY", "MARKET"],
    "news_sentiment": ["SUBINDUSTRY", "INDUSTRY"],
    "options_vol": ["MARKET", "SECTOR"],
    "mean_reversion": ["MARKET", "SECTOR", "NONE"],
    "cross_sectional": ["SUBINDUSTRY", "MARKET"],
    "liquidity_scaled": ["MARKET", "SECTOR"],
    "conditional": ["MARKET", "SECTOR"],
    "vol_adjusted": ["MARKET", "SECTOR"],
    "momentum": ["MARKET", "SECTOR"],
    "volume_flow": ["MARKET", "SECTOR"],
    "price_vol_corr": ["MARKET", "SECTOR"],
    "volatility": ["MARKET", "SECTOR"],
    "intraday": ["MARKET", "SECTOR"],
    "vol_regime": ["MARKET", "NONE"],
    "relationship": ["SUBINDUSTRY", "INDUSTRY"],
    "risk_beta": ["MARKET", "INDUSTRY"],
    "combo_factor": ["MARKET", "INDUSTRY", "SUBINDUSTRY"],
    "wq_proven": ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"],
}
