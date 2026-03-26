from __future__ import annotations

TEMPLATE_LIBRARY: dict[str, list[dict[str, str]]] = {
    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 1: Short-term mean reversion (ALREADY SUBMITTED ×6)
    # Status: SATURATED — reduce exploration weight
    # ══════════════════════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 2: Fundamental Value (earnings yield, book value)
    # Hypothesis: cheap stocks outperform expensive stocks
    # Settings: decay 0-4, SUBINDUSTRY neutral, TOP3000, trunc 0.05-0.08
    # ══════════════════════════════════════════════════════════════════
    "fundamental_value": [
        {"template_id": "fv_01", "expression": "ts_zscore({deep_field} / (cap + 0.001), {n})"},
        {"template_id": "fv_02", "expression": "rank(ts_delta({deep_field}, {n}) / ({deep_field} + 0.001))"},
        {"template_id": "fv_03", "expression": "-rank(close / ({deep_field} + 0.001))"},
        {"template_id": "fv_04", "expression": "group_rank(-ts_zscore({deep_field}, {n}), industry)"},
        {"template_id": "fv_05", "expression": "ts_rank({deep_field} / (cap + 0.001), 252)"},
        {"template_id": "fv_06", "expression": "group_rank(ts_rank({deep_field} / (cap + 0.001), 252), subindustry)"},
        {"template_id": "fv_07", "expression": "rank({deep_field} / (enterprise_value + 0.001))"},
    ],
    "size_value": [
        {"template_id": "sv_01", "expression": "rank(ts_zscore(eps / (close + 0.001), {n}))"},
        {"template_id": "sv_02", "expression": "rank(ts_delta(ebitda / (enterprise_value + 0.001), {n}))"},
        {"template_id": "sv_03", "expression": "-rank(ts_zscore(close / (bookvalue_ps + 0.001), {n}))"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 3: Financial Quality / Balance Sheet Trends
    # Hypothesis: improving balance sheets predict returns
    # Settings: decay 0-4, SUBINDUSTRY neutral, TOP3000, trunc 0.05-0.08
    # ══════════════════════════════════════════════════════════════════
    "quality_trend": [
        {"template_id": "qt_01", "expression": "rank(ts_delta(cashflow_op / (assets + 0.001), {n}))"},
        {"template_id": "qt_02", "expression": "rank(ts_delta(current_ratio, {n}))"},
        {"template_id": "qt_03", "expression": "rank(cashflow_op / (income + 0.001))"},
        {"template_id": "qt_04", "expression": "ts_rank(cashflow_op / (debt + 0.001), 252)"},
        {"template_id": "qt_05", "expression": "rank(ts_delta(equity / (assets + 0.001), {n}))"},
        {"template_id": "qt_06", "expression": "group_rank(ts_rank(cashflow_op / (debt + 0.001), 252), subindustry)"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 4: Fundamental Scores (highest fitness signal!)
    # Hypothesis: composite factor models predict returns
    # Settings: decay 4-8, SUBINDUSTRY neutral, TOP500-TOP1000, trunc 0.05
    # ══════════════════════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 5: Earnings Momentum (analyst revisions)
    # Hypothesis: upward analyst revisions predict outperformance
    # Settings: decay 2-6, NONE or INDUSTRY neutral, TOP1000-TOP3000
    # ══════════════════════════════════════════════════════════════════
    "earnings_momentum": [
        {"template_id": "em_01", "expression": "rank(snt1_d1_netearningsrevision)"},
        {"template_id": "em_02", "expression": "rank(ts_delta(snt1_d1_earningssurprise, {n}))"},
        {"template_id": "em_03", "expression": "rank(snt1_d1_dynamicfocusrank)"},
        {"template_id": "em_04", "expression": "ts_decay_linear(rank(consensus_analyst_rating), {n})"},
        {"template_id": "em_05", "expression": "rank(snt1_d1_stockrank)"},
        {"template_id": "em_06", "expression": "rank(ts_zscore(snt1_d1_netearningsrevision, {n}))"},
        {"template_id": "em_07", "expression": "group_rank(snt1_d1_earningssurprise, subindustry)"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 6: Options Sentiment (put-call, IV)
    # Hypothesis: options market predicts equity moves
    # Settings: decay 0-4, INDUSTRY neutral, trunc 0.03, TOP3000
    # ══════════════════════════════════════════════════════════════════
    "options_vol": [
        {"template_id": "opt_01", "expression": "rank(ts_backfill(implied_volatility_call_{opt_window}, 60) - ts_backfill(implied_volatility_put_{opt_window}, 60))"},
        {"template_id": "opt_02", "expression": "rank(ts_backfill(implied_volatility_call_{opt_window}, 60) / (ts_backfill(historical_volatility_{opt_window}, 60) + 0.001))"},
        {"template_id": "opt_03", "expression": "rank((ts_backfill(implied_volatility_call_{opt_window}, 60) - ts_backfill(implied_volatility_put_{opt_window}, 60)) * rank(adv20))"},
        {"template_id": "opt_04", "expression": "rank((ts_backfill(implied_volatility_call_{opt_window}, 60) / (ts_backfill(historical_volatility_{opt_window}, 60) + 0.001)) * rank(adv20))"},
        {"template_id": "opt_05", "expression": "trade_when(ts_argmax(ts_backfill(pcr_vol_{pcr_window}, 60), 7) < 1, rank(-returns), -1)"},
        {"template_id": "opt_06", "expression": "ts_decay_linear(ts_delta(ts_backfill(implied_volatility_call_{opt_window}, 60), 25) > 0, 20)"},
        {"template_id": "opt_07", "expression": "rank(-ts_backfill(pcr_oi_{pcr_window}, 60)) * rank(adv20)"},
        {"template_id": "opt_08", "expression": "rank(ts_backfill(implied_volatility_mean_skew_{opt_window}, 60)) * rank(cap)"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 7: News & Social Sentiment
    # Hypothesis: positive sentiment predicts short-term returns
    # Settings: decay 2-6, NONE neutral, TOP500-TOP1000
    # ══════════════════════════════════════════════════════════════════
    "news_sentiment": [
        {"template_id": "ns_01", "expression": "rank(ts_backfill(scl12_sentiment, 60))"},
        {"template_id": "ns_02", "expression": "rank(ts_delta(ts_backfill(scl12_buzz, 60), {n}))"},
        {"template_id": "ns_03", "expression": "rank(ts_backfill(rp_ess_earnings, 60))"},
        {"template_id": "ns_04", "expression": "ts_decay_linear(rank(ts_backfill(news_pct_1min, 60)), {n})"},
        {"template_id": "ns_05", "expression": "rank(ts_backfill(snt_buzz_bfl, 60)) * rank(adv20)"},
        {"template_id": "ns_06", "expression": "rank(ts_backfill(rp_css_earnings, 60) - ts_backfill(rp_css_credit, 60))"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # SIGNAL CLASS 8: Volatility Regime (from WQ researcher)
    # Hypothesis: mean reversion stronger in high-vol regimes
    # Settings: decay 4-8, MARKET neutral
    # ══════════════════════════════════════════════════════════════════
    "vol_regime": [
        {"template_id": "vr_01", "expression": "trade_when(ts_rank(ts_std_dev(returns, 22), 252) > 0.55, -ts_regression(returns, ts_delay(returns, 1), 252, rettype=2), -1)"},
        {"template_id": "vr_02", "expression": "trade_when(ts_rank(ts_std_dev(returns, {n}), 252) > 0.5, rank(-returns), -1)"},
        {"template_id": "vr_03", "expression": "rank(-ts_regression(returns, ts_delay(returns, 1), {n}, rettype=2))"},
        {"template_id": "vr_04", "expression": "rank(ts_regression(close, ts_step(1), {n}, rettype=2))"},
    ],

    # ══════════════════════════════════════════════════════════════════
    # LEGACY: Lower priority families
    # ══════════════════════════════════════════════════════════════════
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

# v5.7: Fundamental score derivatives — different signal from base scores
DERIVATIVE_FIELDS = [
    "cashflow_efficiency_rank_derivative",
    "composite_factor_score_derivative",
    "earnings_certainty_rank_derivative",
    "growth_potential_rank_derivative",
    "analyst_revision_rank_derivative",
    "relative_valuation_rank_derivative",
]

OPTIONS_WINDOWS = [30, 60, 90, 120, 180]

# v5.7: PCR windows for put-call ratio signals
PCR_WINDOWS = [10, 30, 60, 90, 120, 180, 270]

SAFE_PARAM_RANGES = {
    "n": [3, 5, 10, 20, 40, 60],
    "m": [5, 10, 20, 60],
}

# v5.7: Long lookback params for fundamental signals (quarterly data)
FUNDAMENTAL_PARAM_RANGES = {
    "n": [60, 120, 180, 252],
    "m": [60, 120, 252],
}
