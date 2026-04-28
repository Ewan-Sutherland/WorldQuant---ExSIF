"""
v7.2.7 D=0 Templates — 40 hand-picked templates for IQC 2026 USA D=0 surface.

Sourced from the D0 research brief covering:
- WQ official D=0 docs (afternoon trade, captures overnight return)
- Published USA D=0 alphas with verified Sharpe 2.0-2.58
- WQ D=0 patterns (vol-spike reversal, news-event triggers, IV/RV divergence)
- Group reversion (sector/industry mean snap-back)
- Open-price asymmetry (intraday vs overnight decomposition)

Conventions:
- All templates intended for delay=0
- {w} sweep windows handled by parameter sampler in generator.py
- {field} placeholders mostly avoided — fields are baked in for sharpness
- Pasteurization ON (default)
- Truncation 0.05-0.10 (NOT 0.01 — D0 events need wider truncation)
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════
# Family A — Open-Price Reversal (5 templates)
# Exploits intraday over-reaction that mean-reverts overnight.
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_OPEN_PRICE_REVERSAL = [
    # A1. Open-Gap Reversion (clean)
    {"template_id": "d0v7_open_01",
     "expression": "-rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001))"},
    # A2. Intraday Move + Overnight Reversal — sweep window via parameter
    {"template_id": "d0v7_open_02a",
     "expression": "-rank(ts_zscore((close - open) / (open + 0.001), 5))"},
    {"template_id": "d0v7_open_02b",
     "expression": "-rank(ts_zscore((close - open) / (open + 0.001), 10))"},
    {"template_id": "d0v7_open_02c",
     "expression": "-rank(ts_zscore((close - open) / (open + 0.001), 20))"},
    # A3. Opening-Range Pressure
    {"template_id": "d0v7_open_03",
     "expression": "-(open - (high + low) / 2) / (high - low + 0.001)"},
    # A4. Three-Day Open Reversion + Volume Filter
    {"template_id": "d0v7_open_04",
     "expression": "trade_when(volume > adv20, -ts_delta(open, 3), -1)"},
    # A5. Ranked Open-to-VWAP Pressure
    {"template_id": "d0v7_open_05",
     "expression": "-rank((open - vwap) / (open + vwap + 0.001))"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family B — Group Reversion (5 templates)
# Stocks revert to their sector/industry mean overnight.
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_GROUP_REVERSION = [
    # B1. Subindustry Mean Deviation Reversion
    {"template_id": "d0v7_grp_01",
     "expression": "-rank(close / (ts_delay(close, 5) + 0.001) - group_mean(close / (ts_delay(close, 5) + 0.001), 1, subindustry))"},
    # B2. Group-Zscore Returns Reversion
    {"template_id": "d0v7_grp_02",
     "expression": "-group_zscore(returns, industry)"},
    # B3. Geometric Mean Group Reversion
    {"template_id": "d0v7_grp_03",
     "expression": "-zscore(power(ts_product(returns + 1, 5), 0.2) / (power(ts_product(rel_ret_comp + 1, 5), 0.2) + 0.001))"},
    # B4. Sector-Relative VWAP Reversion
    {"template_id": "d0v7_grp_04",
     "expression": "-((vwap - close) / (close + 0.001) - group_mean((vwap - close) / (close + 0.001), 1, sector))"},
    # B5. Group-Rank Inverse-Volatility Reversion + Volume Gate
    {"template_id": "d0v7_grp_05",
     "expression": "trade_when(volume > adv20, -group_rank(returns / (ts_std_dev(returns, 20) + 0.001), subindustry), -1)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family C — News-Event Triggers (5 templates)
# Use news vector spikes / news volume as event triggers.
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_NEWS_TRIGGERS = [
    # C1. News-Spike Reversion (vector buzz)
    {"template_id": "d0v7_news_01",
     "expression": "trade_when(ts_arg_max(ts_backfill(vec_sum(scl12_alltype_buzzvec), 252), 5) == 0, -rank(ts_delta(close, 1)), -1)"},
    # C2. After-Hours News Drift
    {"template_id": "d0v7_news_02",
     "expression": "trade_when(ts_arg_max(ts_backfill(vec_avg(nws12_afterhsz_sl), 252), 3) == 0, rank(ts_backfill(vec_avg(nws12_afterhsz_sl), 252)), -1)"},
    # C3. News-Volume vs Price-Lag Trigger
    {"template_id": "d0v7_news_03",
     "expression": "trade_when(rank(ts_backfill(vec_sum(nws18_bam), 252)) > 0.9, -ts_zscore(close - open, 5), -1)"},
    # C4. News-Down-Spike Reversal Long
    {"template_id": "d0v7_news_04",
     "expression": "trade_when(ts_arg_max(ts_backfill(news_mins_10_pct_dn, 252), 3) == 0, -rank(ts_delta(close, 2)), -1)"},
    # C5. News-Maximum-Up-Return Fade
    {"template_id": "d0v7_news_05",
     "expression": "trade_when(ts_arg_max(ts_backfill(news_max_up_ret, 252), 5) == 0, -rank(ts_backfill(news_max_up_ret, 252)), -1)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family D — Sentiment RSI / Momentum (4 templates)
# Sentiment streams treated like price — apply RSI / reversion / momentum.
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_SENTIMENT = [
    # D1. Sentiment RSI Reversion
    {"template_id": "d0v7_snt_01",
     "expression": "-rank(ts_sum(max(ts_delta(ts_backfill(scl12_buzz, 252), 1), 0), 14) / (ts_sum(max(ts_delta(ts_backfill(scl12_buzz, 252), 1), 0), 14) + ts_sum(max(-ts_delta(ts_backfill(scl12_buzz, 252), 1), 0), 14) + 0.0001))"},
    # D2. Buzz De-mean Long-only
    {"template_id": "d0v7_snt_02",
     "expression": "ts_av_diff(ts_backfill(-vec_sum(scl12_alltype_buzzvec), 20), 60)"},
    # D3. Sentiment Trend with Volume Confirmation
    {"template_id": "d0v7_snt_03",
     "expression": "trade_when(volume > adv20, ts_zscore(ts_backfill(vec_avg(scl12_alltype_sentimentvec), 252), 20), -1)"},
    # D4. Sentiment Quantile-Bucket Momentum
    {"template_id": "d0v7_snt_04",
     "expression": "group_zscore(ts_delta(ts_backfill(scl12_buzz, 252), 5), bucket(rank(ts_backfill(scl12_buzz, 252)), range=\"0,1,0.1\"))"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family E — Volatility-Regime Triggered Reversal (4 templates)
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_VOL_REGIME = [
    # E1. Parkinson-Vol-Spike Reversal (canonical)
    {"template_id": "d0v7_vol_01",
     "expression": "trade_when(ts_arg_max(parkinson_volatility_10, 3) == 0, -rank(ts_delta(close, 2)), -1)"},
    # E2. Vol-Spike + Volume Filter Reversal
    {"template_id": "d0v7_vol_02",
     "expression": "trade_when(ts_arg_max(parkinson_volatility_10, 3) == 0, -ts_rank(volume, 5) * rank(ts_delta(close, 1)), -1)"},
    # E3. Long-Window Vol-Regime Switch (high-vol regime → reversal)
    {"template_id": "d0v7_vol_03",
     "expression": "trade_when(ts_rank(parkinson_volatility_60, 252) > 0.7, -ts_regression(returns, ts_delay(returns, 1), 60, lag=0, rettype=0), -1)"},
    # E4. Vol-Argmin Momentum Trigger (low-vol → momentum)
    {"template_id": "d0v7_vol_04",
     "expression": "trade_when(ts_arg_min(parkinson_volatility_10, 5) == 0, rank(ts_delta(close, 3)), -1)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family F — IV vs Realized-Vol Divergence (4 templates)
# Options-implied uncertainty premium reversion. Highest documented USA D0 Sharpes.
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_IV_RV = [
    # F1. IV/Parkinson Ratio (volatility arbitrage; WQ-published USA D0)
    {"template_id": "d0v7_iv_01",
     "expression": "implied_volatility_call_120 / (parkinson_volatility_120 + 0.001)"},
    # F2. Short-Tenor IV/RV Spike
    {"template_id": "d0v7_iv_02",
     "expression": "trade_when(ts_arg_max(implied_volatility_call_30, 3) == 0, -rank(implied_volatility_call_30 / (parkinson_volatility_10 + 0.001)), -1)"},
    # F3. Put-Call IV Skew
    {"template_id": "d0v7_iv_03",
     "expression": "-rank(ts_zscore(implied_volatility_put_60 / (implied_volatility_call_60 + 0.001), 20))"},
    # F4. IV Term-Structure Inversion
    {"template_id": "d0v7_iv_04",
     "expression": "ts_decay_linear(rank(implied_volatility_call_30 / (implied_volatility_call_270 + 0.001) - 1), 5)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family G — Analyst Sentiment Shock (3 templates)
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_ANALYST = [
    # G1. Analyst Sentiment + Price-Drop Trigger
    {"template_id": "d0v7_anl_01",
     "expression": "trade_when(ts_delta(close, 1) < -0.02, scale(mdl110_analyst_sentiment + mdl110_score), -1)"},
    # G2. EPS-Estimate Revision Drift
    {"template_id": "d0v7_anl_02",
     "expression": "trade_when(ts_delta(ts_backfill(est_eps, 252), 5) > 0, rank(ts_delta(ts_backfill(est_eps, 252), 20)), -1)"},
    # G3. Analyst-Sentiment Group-Adjusted Reversion
    {"template_id": "d0v7_anl_03",
     "expression": "trade_when(volume > adv20, group_zscore(mdl110_analyst_sentiment, sector) - rank(returns), -1)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family H — Volume-Spike + Reversion (3 templates)
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_VOLUME_SHOCK = [
    # H1. Volume-Spike Five-Day Reversal
    {"template_id": "d0v7_volsh_01",
     "expression": "trade_when(volume > adv20, -ts_delta(close, 5), -1)"},
    # H2. Volume Z-score Triggered VWAP Reversion
    {"template_id": "d0v7_volsh_02",
     "expression": "trade_when(ts_zscore(volume, 20) > 2, -rank((vwap - close) / (close + 0.001)), -1)"},
    # H3. Volume-Acceleration Rank with Group Reversion
    {"template_id": "d0v7_volsh_03",
     "expression": "trade_when(ts_rank(ts_delta(log(volume + 1), 1), 20) > 0.9, -group_zscore(returns, subindustry), -1)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family I — Overnight Gap Capture (4 templates)
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_OVERNIGHT_GAP = [
    # I1. Overnight Return Direct Reversion
    {"template_id": "d0v7_ong_01",
     "expression": "-ts_decay_linear(rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001)), 3)"},
    # I2. Cumulative Overnight Return Streak (3 sweep widths)
    {"template_id": "d0v7_ong_02a",
     "expression": "-ts_sum((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001), 3)"},
    {"template_id": "d0v7_ong_02b",
     "expression": "-ts_sum((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001), 5)"},
    {"template_id": "d0v7_ong_02c",
     "expression": "-ts_sum((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001), 10)"},
    # I3. Overnight vs Intraday Decomposition
    {"template_id": "d0v7_ong_03",
     "expression": "-rank((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001)) + rank((close - open) / (open + 0.001))"},
    # I4. Gap-Filtered Reversal
    {"template_id": "d0v7_ong_04",
     "expression": "trade_when(abs((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001)) > 0.02, -sign((open - ts_delay(close, 1)) / (ts_delay(close, 1) + 0.001)) * rank(volume), -1)"},
]

# ═══════════════════════════════════════════════════════════════════════════
# Family J — Fundamental-Anchored Low-Turnover D0 (3 templates)
# Verified WQ submitted alphas at Sharpe 2.0-2.58
# ═══════════════════════════════════════════════════════════════════════════
DELAY0_V727_FUNDAMENTAL = [
    # J1. EPS-Yield Rank — verified WQ submitted alpha @ Sharpe 2.03
    {"template_id": "d0v7_fnd_01",
     "expression": "rank(ts_rank(fnd6_epsfx / (close + 0.001), 40))"},
    # J2. EBIT/CapEx Quality — verified WQ submitted alpha @ Sharpe 2.02 / Fitness 2.30
    {"template_id": "d0v7_fnd_02",
     "expression": "-rank(ebit / (capex + 0.001))"},
    # J3. EV/EBITDA Reversion — verified WQ submitted alpha @ Sharpe 2.58
    {"template_id": "d0v7_fnd_03",
     "expression": "-ts_zscore(enterprise_value / (ebitda + 0.001), 63)"},
]


# Aggregate into single dict for easy import
DELAY0_V727_TEMPLATES = {
    "d0v7_open_price_reversal": DELAY0_V727_OPEN_PRICE_REVERSAL,
    "d0v7_group_reversion": DELAY0_V727_GROUP_REVERSION,
    "d0v7_news_triggers": DELAY0_V727_NEWS_TRIGGERS,
    "d0v7_sentiment": DELAY0_V727_SENTIMENT,
    "d0v7_vol_regime": DELAY0_V727_VOL_REGIME,
    "d0v7_iv_rv": DELAY0_V727_IV_RV,
    "d0v7_analyst": DELAY0_V727_ANALYST,
    "d0v7_volume_shock": DELAY0_V727_VOLUME_SHOCK,
    "d0v7_overnight_gap": DELAY0_V727_OVERNIGHT_GAP,
    "d0v7_fundamental": DELAY0_V727_FUNDAMENTAL,
}


# Settings recommendations per family (per research brief).
# These get applied via DATASET_NEUTRALIZATION + universe sweep in generator.
DELAY0_V727_NEUTRALIZATION = {
    "d0v7_open_price_reversal": ["SUBINDUSTRY", "INDUSTRY"],
    "d0v7_group_reversion": ["NONE", "MARKET"],  # Group is the neutralizer
    "d0v7_news_triggers": ["INDUSTRY", "SUBINDUSTRY"],
    "d0v7_sentiment": ["INDUSTRY", "SUBINDUSTRY"],
    "d0v7_vol_regime": ["SUBINDUSTRY", "INDUSTRY"],
    "d0v7_iv_rv": ["SUBINDUSTRY", "INDUSTRY"],
    "d0v7_analyst": ["INDUSTRY", "SECTOR"],
    "d0v7_volume_shock": ["SUBINDUSTRY", "INDUSTRY"],
    "d0v7_overnight_gap": ["SUBINDUSTRY", "INDUSTRY"],
    "d0v7_fundamental": ["SUBINDUSTRY"],
}

# Family-specific universe biases (research brief recommendation)
DELAY0_V727_UNIVERSE = {
    "d0v7_open_price_reversal": ["TOP500", "TOP1000"],
    "d0v7_group_reversion": ["TOP1000", "TOP3000"],  # B3 wants depth
    "d0v7_news_triggers": ["TOP1000", "TOP500"],
    "d0v7_sentiment": ["TOP1000", "TOP500"],
    "d0v7_vol_regime": ["TOP500", "TOP1000"],
    "d0v7_iv_rv": ["TOP1000", "TOP500"],
    "d0v7_analyst": ["TOP1000", "TOP500"],
    "d0v7_volume_shock": ["TOP500", "TOP1000"],
    "d0v7_overnight_gap": ["TOP500", "TOP1000"],
    "d0v7_fundamental": ["TOP1000", "TOP500", "TOP3000"],
}

# Family-specific decay biases
DELAY0_V727_DECAY = {
    "d0v7_open_price_reversal": [2, 4, 6],
    "d0v7_group_reversion": [3, 4, 6],
    "d0v7_news_triggers": [0, 2, 4],   # Event triggers — don't smear
    "d0v7_sentiment": [4, 5, 6],
    "d0v7_vol_regime": [0, 2, 4],
    "d0v7_iv_rv": [0, 2, 4],
    "d0v7_analyst": [0, 4, 6],
    "d0v7_volume_shock": [3, 4, 6],
    "d0v7_overnight_gap": [0, 2, 4],
    "d0v7_fundamental": [0, 9],         # Verified Sharpes were at 0 and 9
}

# Total template count check
def _count_templates() -> int:
    return sum(len(t) for t in DELAY0_V727_TEMPLATES.values())

if __name__ == "__main__":
    print(f"DELAY0_V727 — {len(DELAY0_V727_TEMPLATES)} families, "
          f"{_count_templates()} templates")
    for fam, tlist in DELAY0_V727_TEMPLATES.items():
        print(f"  {fam}: {len(tlist)} templates, "
              f"univ={DELAY0_V727_UNIVERSE.get(fam)} neut={DELAY0_V727_NEUTRALIZATION.get(fam)}")
