# AlphaBot v6.2 → v6.2.1: Strategic Improvements
# Focus: Finding alphas that IMPROVE portfolio score, not just pass individual checks

## THE CORE PROBLEM

Your overnight run found ~15 alphas that passed all individual checks (Sharpe, Fitness,
Turnover, Self-Correlation). But only 4 had POSITIVE score changes. The other 11 would
have HURT your score.

This means the portfolio is SATURATED in certain signal types. Individual alpha quality
doesn't matter if it's correlated with what you already have at the PORTFOLIO level.

## WHAT MAKES ALPHAS PORTFOLIO-POSITIVE

All 4 winning alphas (+48, +37, +10, +2) share ONE key component:
  implied_volatility_call_120 / parkinson_volatility_120

This is an OPTIONS VOLATILITY signal. Your existing portfolio is dominated by:
  - Price returns / mean reversion (9+ submissions)
  - Fundamental ratios / model77 combos
  - Analyst estimates (est_eps/close variants)

The options vol component is genuinely DIFFERENT data → low portfolio correlation → positive score.

## CONCRETE CHANGES

### 1. REWEIGHT FAMILIES (config.py)

Current weights are based on individual Sharpe, not portfolio-additive potential.
model77_combo has weight 4.00 despite 82 sims at 0% submit rate recently.

Proposed changes:
  model77_combo:        4.00 → 0.80   # Saturated - every alpha hurts portfolio score
  model77_anomaly:      0.10 → 0.10   # Keep dead
  options_vol:          1.00 → 3.50   # PROVEN portfolio-additive (all 4 winners use it)
  news_sentiment:       1.00 → 2.50   # Unexplored, likely uncorrelated
  analyst_sentiment:    0.30 → 2.00   # Works in combos (snt1_d1 signals)
  earnings_momentum:    1.20 → 1.80   # Some signal, underexplored standalone
  intraday:             0.15 → 1.50   # open/close patterns = different data
  relationship:         0.60 → 1.20   # Increase — supply chain is genuinely novel
  combo_factor:         2.00 → 1.50   # Reduce — many are model77 variants underneath
  expanded_fundamental: 0.80 → 0.40   # Weak results, saturated data category
  fundamental_scores:   1.00 → 0.50   # CW problems, saturated
  fundamental_value:    1.00 → 0.50   # Saturated with fundamentals
  risk_beta:            0.10 → 0.60   # Increase — beta is different data, just needs better templates

### 2. NEW TEMPLATES (templates.py)

Add templates targeting PROVEN portfolio-additive signal patterns:

A) Options vol crossed with other signals (the winning formula):
  - rank(ts_backfill(IV_call_120, 60) / (ts_backfill(parkinson_120, 60) + 0.001) * snt1_d1_netearningsrevision)
  - rank(ts_backfill(IV_call_120, 60) / (ts_backfill(parkinson_120, 60) + 0.001) * forward_ebitda_to_enterprise_value_2)
  - group_rank(ts_backfill(IV_call_120, 60) / (ts_backfill(parkinson_120, 60) + 0.001), industry)

B) Options term structure (call_120 vs call_30 spread):
  - rank(ts_backfill(IV_call_120, 60) - ts_backfill(IV_call_30, 60))
  - rank((ts_backfill(IV_call_120, 60) - ts_backfill(IV_call_30, 60)) * rank(adv20))

C) News × reversion (untapped category):  
  - rank(ts_backfill(news_max_up_ret, 60) * -returns)
  - rank(ts_backfill(rp_ess_earnings, 60) * -ts_mean(returns, 5))

D) Intraday patterns (genuinely different data):
  - rank((open - close) / (high - low + 0.001))  # candle body ratio
  - rank(ts_mean(high/low - 1, 5))  # average range

E) Risk-adjusted combos (beta × fundamentals):
  - rank(-beta_last_60_days_spy * forward_ebitda_to_enterprise_value_2)
  - rank(-beta_last_60_days_spy) + rank(est_eps / close)

### 3. COMBINER BIAS (signal_combiner.py)

The combiner currently picks categories randomly. It should PREFER to include
options_vol or news as one component, since those are proven portfolio-additive:

  PORTFOLIO_ADDITIVE_CATEGORIES = {"options_vol", "news", "sentiment", "risk"}
  
  When generating combos, ensure at least one component is from PORTFOLIO_ADDITIVE_CATEGORIES.
  This increases the probability that the resulting combo adds value to the portfolio.

### 4. LLM PROMPT SHIFT (llm_generator.py)

The LLM keeps generating fundamentals and model77 variants. Update the prompt:
  - Add explicit instruction: "OPTIONS and NEWS data are the highest priority targets"
  - Add the winning pattern as an example of what works
  - Reduce near-passer examples that are fundamentals-heavy

### 5. SETTINGS INSIGHT

The +37 alpha used TOP3000/MARKET/d10/t0.08 — higher decay reduces turnover and 
stabilizes the signal. For options-based alphas specifically, suggest:
  options_vol settings: decay=[6,8,10], universe=TOP3000, neut=MARKET
  
  This is different from the current options_vol profile which uses decay=[0,2,4].

### 6. SUBMIT STAGED ALPHAS

You have 4 alphas staged with +48, +37, +10, +2 score changes.
SUBMIT THEM before running more sims. Each submission changes the self-correlation
landscape and may unblock other candidates.
