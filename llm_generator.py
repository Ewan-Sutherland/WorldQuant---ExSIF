"""
v5.6.1: LLM-guided alpha expression generator.

Uses Google Gemini 2.5 Flash (free, 250 RPD) as primary,
Groq GPT-OSS 120B (free, 1000 RPD) as fallback.

Fixes over v5.6:
- Groq model: openai/gpt-oss-120b (was llama-4-scout-17b — much weaker)
- Temperature: 0.7 (was 0.9 — too creative, too many syntax errors)
- Comprehensive operator + field reference in system prompt
- Field name validation (rejects expressions with invalid field names)
- Failed expression feedback in prompt (LLM learns from errors)
"""
from __future__ import annotations

import os
import re
import time
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Complete verified field set ─────────────────────────────────────
# Every field name the WQ API actually accepts. Used for validation.

VALID_FIELDS = {
    # Price Volume (pv1)
    "adv20", "cap", "close", "dividend", "high", "low", "open", "returns",
    "sharesout", "split", "volume", "vwap",
    # Group fields
    "industry", "subindustry", "sector", "market", "exchange",
    # Fundamental — common
    "assets", "assets_curr", "bookvalue_ps", "capex", "cash", "cash_st",
    "cashflow", "cashflow_dividends", "cashflow_fin", "cashflow_invst",
    "cashflow_op", "cogs", "current_ratio", "debt", "debt_lt", "debt_st",
    "depre_amort", "ebit", "ebitda", "employee", "enterprise_value", "eps",
    "equity", "income", "sales",
    # Fundamental Scores (model16)
    "fscore_bfl_value", "fscore_bfl_momentum", "fscore_bfl_quality",
    "fscore_bfl_growth", "fscore_bfl_profitability", "fscore_bfl_total",
    "fscore_bfl_surface", "fscore_bfl_surface_accel",
    "fscore_value", "fscore_momentum", "fscore_quality", "fscore_growth",
    "fscore_profitability", "fscore_total", "fscore_surface", "fscore_surface_accel",
    "analyst_revision_rank_derivative", "cashflow_efficiency_rank_derivative",
    "composite_factor_score_derivative", "earnings_certainty_rank_derivative",
    "growth_potential_rank_derivative", "multi_factor_acceleration_score_derivative",
    "multi_factor_static_score_derivative", "relative_valuation_rank_derivative",
    # Research Sentiment (sentiment1)
    "snt1_cored1_score", "snt1_d1_analystcoverage", "snt1_d1_buyrecpercent",
    "snt1_d1_downtargetpercent", "snt1_d1_dtstsespe", "snt1_d1_dynamicfocusrank",
    "snt1_d1_earningsrevision", "snt1_d1_earningssurprise", "snt1_d1_earningstorpedo",
    "snt1_d1_fundamentalfocusrank", "snt1_d1_longtermepsgrowthest",
    "snt1_d1_netearningsrevision", "snt1_d1_netrecpercent", "snt1_d1_nettargetpercent",
    "snt1_d1_sellrecpercent", "snt1_d1_stockrank", "snt1_d1_uptargetpercent",
    "consensus_analyst_rating",
    # SM Sentiment (socialmedia12)
    "scl12_buzz", "scl12_buzz_fast_d1", "scl12_sentiment", "scl12_sentiment_fast_d1",
    "snt_buzz", "snt_buzz_bfl", "snt_buzz_bfl_fast_d1", "snt_buzz_fast_d1",
    "snt_buzz_ret", "snt_buzz_ret_fast_d1", "snt_value", "snt_value_fast_d1",
    "snt_social_value",
    # Analyst Estimates — key fields
    "est_ptp", "est_fcf", "est_cashflow_op", "est_capex",
    # Ravenpack News — key event sentiment fields
    "rp_css_earnings", "rp_css_revenue", "rp_css_dividends", "rp_css_mna",
    "rp_css_credit", "rp_css_price", "rp_css_product", "rp_css_technical",
    "rp_ess_earnings", "rp_ess_revenue", "rp_ess_dividends", "rp_ess_mna",
    "rp_ess_credit", "rp_ess_price", "rp_ess_product", "rp_ess_technical",
    "nws18_ber", "nws18_bee", "nws18_bam", "nws18_ssc", "nws18_sse",
    # US News Data — key fields
    "news_pct_1min", "news_pct_5_min", "news_pct_10min", "news_pct_30min",
    "news_pct_60min", "news_pct_90min", "news_pct_120min",
    "news_max_up_ret", "news_max_dn_ret", "news_max_up_amt", "news_max_dn_amt",
    "news_open_gap", "news_ls",
}

# Dynamically add volatility/options fields with all known windows
for _prefix in ["implied_volatility_call_", "implied_volatility_put_",
                "implied_volatility_mean_", "implied_volatility_mean_skew_",
                "historical_volatility_"]:
    for _w in [10, 20, 30, 60, 90, 120, 150, 180, 270, 360, 720, 1080]:
        VALID_FIELDS.add(f"{_prefix}{_w}")

for _prefix in ["call_breakeven_", "forward_price_", "option_breakeven_",
                "pcr_oi_", "pcr_vol_"]:
    for _w in [10, 20, 30, 60, 90, 120, 150, 180, 270, 360, 720, 1080]:
        VALID_FIELDS.add(f"{_prefix}{_w}")

# v5.9: Add Parkinson volatility fields
for _w in [10, 20, 30, 60, 90, 120, 150, 180]:
    VALID_FIELDS.add(f"parkinson_volatility_{_w}")

# v5.9: model77 pre-computed anomaly fields (Analysts Factor Model)
VALID_FIELDS.update({
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
})

# v5.9: Relationship / supply chain data (pv13)
VALID_FIELDS.update({
    "rel_ret_cust", "rel_ret_comp", "rel_ret_all", "rel_ret_part",
    "rel_num_cust", "rel_num_comp", "rel_num_all", "rel_num_part",
    "pv13_ustomergraphrank_page_rank", "pv13_ustomergraphrank_hub_rank",
    "pv13_ustomergraphrank_auth_rank", "pv13_com_page_rank",
})

# v5.9: Risk Metrics (model51)
VALID_FIELDS.update({
    "beta_last_30_days_spy", "beta_last_60_days_spy",
    "beta_last_90_days_spy", "beta_last_360_days_spy",
    "correlation_last_30_days_spy", "correlation_last_60_days_spy",
    "correlation_last_90_days_spy", "correlation_last_360_days_spy",
    "systematic_risk_last_30_days", "systematic_risk_last_60_days",
    "systematic_risk_last_90_days", "systematic_risk_last_360_days",
    "unsystematic_risk_last_30_days", "unsystematic_risk_last_60_days",
    "unsystematic_risk_last_90_days", "unsystematic_risk_last_360_days",
})

# v5.9: Expanded Fundamental fields
VALID_FIELDS.update({
    "operating_income", "retained_earnings", "working_capital",
    "inventory_turnover", "rd_expense", "goodwill", "revenue",
    "return_assets", "return_equity", "sales_ps", "sales_growth",
    "sga_expense", "ppent", "pretax_income", "invested_capital",
    "operating_expense", "income_beforeextra", "income_tax",
    "interest_expense", "receivable", "liabilities", "liabilities_curr",
    "fn_liab_fair_val_l1_a", "fn_liab_fair_val_l1_q",
    "fn_liab_fair_val_a", "fn_liab_fair_val_q",
})

# v5.9: Additional analyst estimate fields
VALID_FIELDS.update({
    "est_eps", "est_epsr", "est_fcf", "est_fcf_ps", "est_ptp",
    "est_cashflow_op", "est_capex", "est_ebit", "est_ebitda",
    "est_sales", "est_netprofit", "est_dividend_ps",
})


# ── Operators ───────────────────────────────────────────────────────

VALID_OPERATORS = {
    "rank", "group_rank", "ts_mean", "ts_std_dev", "ts_zscore", "ts_rank",
    "ts_delta", "ts_decay_linear", "ts_corr", "ts_sum", "ts_min", "ts_max",
    "ts_argmin", "ts_argmax", "ts_arg_max", "ts_covariance", "ts_product", "ts_backfill",
    "ts_count_nans", "ts_regression", "ts_step", "ts_delay", "ts_scale",
    "ts_quantile",
    "trade_when", "abs", "log", "sign", "max", "min", "power",
    "is_nan", "bucket", "densify", "winsorize", "normalize",
    "group_neutralize", "group_zscore", "group_scale", "group_backfill", "group_mean",
    "scale", "quantile", "zscore",
    "vec_avg", "vec_count", "vec_sum", "vec_max", "vec_min",
    "vec_stddev", "vec_range", "vec_ir",
    "signed_power", "sqrt", "inverse", "reverse", "hump",
    "last_diff_value", "days_from_last_change", "kth_element",
    "pasteurize",
}

LOCKED_OPERATORS = {"ts_skewness", "ts_kurtosis", "ts_momentum"}


# ── Comprehensive system prompt ─────────────────────────────────────

SYSTEM_PROMPT = """You are an expert quantitative researcher generating alpha expressions for WorldQuant BRAIN's IQC 2026 competition.

Your task: generate alpha expressions that predict which stocks will outperform tomorrow.
Output ONLY raw FastExpression syntax — no Python, no pseudocode.

═══════════════════════════════════════════════════
THINKING PROCESS (follow this for EVERY expression)
═══════════════════════════════════════════════════

Step 1: Pick a MARKET INEFFICIENCY to exploit. Examples:
  - Post-earnings drift (investors underreact to earnings surprises)
  - Value-momentum crash hedge (cheap stocks with improving momentum)
  - Implied vs realized volatility gap (options market mispricing)
  - Analyst herding (revision clusters predict returns)
  - Liquidity premium (less liquid stocks earn higher returns)
  - Supply chain contagion (customer returns predict supplier returns)
  - Short-term mean reversion in high-volume stocks
  - Quality flight during volatility regimes

Step 2: Choose 1-2 data fields that CAPTURE that inefficiency.
Step 3: Apply the MINIMUM operators needed — simpler = better fitness.
Step 4: Verify the expression is structurally different from the submitted list.

═══════════════════════════════════════════════════
OPERATOR REFERENCE
═══════════════════════════════════════════════════

ARITHMETIC: +, -, *, /, abs(x), log(x), sign(x), max(x,y), min(x,y), power(x,n)

RANKING (cross-sectional):
  rank(x)                         — rank stocks 0 to 1
  group_rank(x, group)            — rank within group (industry/subindustry/sector/market)

TIME SERIES (per-stock):
  ts_mean(x, n), ts_std_dev(x, n), ts_zscore(x, n), ts_rank(x, n)
  ts_delta(x, n), ts_decay_linear(x, n), ts_corr(x, y, n)
  ts_sum(x, n), ts_min(x, n), ts_max(x, n)
  ts_argmin(x, n), ts_argmax(x, n), ts_covariance(x, y, n)
  ts_backfill(x, n)               — fill NaN (REQUIRED for options/news data)
  ts_regression(y, x, n, rettype) — rettype=2 for slope
  ts_step(n)                      — sequence 1..n for trend regression
  ts_scale(x, n)                  — scale to sum to 1

CONDITIONAL:
  trade_when(cond, x, default)    — use x when cond is true, else default

LOCKED — DO NOT USE: ts_skewness, ts_kurtosis, ts_momentum

═══════════════════════════════════════════════════
DATA FIELDS
═══════════════════════════════════════════════════

PRICE & VOLUME: close, open, high, low, vwap, returns, volume, adv20, cap, sharesout

FUNDAMENTAL (quarterly, use 60-252 day lookbacks):
  assets, sales, income, cash, debt, equity, eps, ebitda, ebit, enterprise_value,
  bookvalue_ps, capex, cashflow, cashflow_op, cogs, current_ratio,
  assets_curr, debt_lt, debt_st, depre_amort, employee, retained_earnings,
  operating_income, gross_profit, inventory_turnover, rd_expense

FUNDAMENTAL SCORES (model16 — sparse coverage, use ts_backfill or multiply by rank(cap)):
  fscore_bfl_value, fscore_bfl_momentum, fscore_bfl_quality, fscore_bfl_growth,
  fscore_bfl_profitability, fscore_bfl_total, fscore_bfl_surface, fscore_bfl_surface_accel

PRE-COMPUTED ANOMALIES (model77 — ready to use):
  earnings_momentum_composite_score, earnings_momentum_analyst_score,
  five_year_eps_stability, forward_ebitda_to_enterprise_value_2,
  forward_cash_flow_to_price, cash_burn_rate, fcf_yield_times_forward_roe,
  sustainable_growth_rate, normalized_earnings_yield,
  gross_profit_to_assets_ratio, asset_growth_rate, industry_relative_return_5d,
  gross_profit_margin_ttm_2

ANALYST ESTIMATES: est_eps, est_ptp, est_fcf, est_cashflow_op, est_capex

RESEARCH SENTIMENT (daily):
  snt1_d1_earningssurprise, snt1_d1_netearningsrevision, snt1_d1_dynamicfocusrank,
  snt1_d1_buyrecpercent, snt1_d1_sellrecpercent, consensus_analyst_rating

SOCIAL MEDIA: scl12_buzz, scl12_sentiment, snt_social_value

OPTIONS (sparse — ALWAYS use ts_backfill):
  implied_volatility_call_{30,60,120,180}, implied_volatility_put_{30,60,120,180},
  implied_volatility_mean_skew_{30,60,120}, parkinson_volatility_{60,120}
  pcr_oi_{30,60,180,270}, pcr_vol_{30,60,180,270}

RAVENPACK NEWS (sparse — ALWAYS use ts_backfill):
  rp_ess_earnings, rp_ess_revenue, rp_css_earnings,
  news_pct_1min, news_max_up_ret, news_max_dn_ret

SUPPLY CHAIN: rel_ret_cust, rel_ret_comp, rel_num_cust, rel_num_comp

RISK: beta_last_60_days_spy, unsystematic_risk, systematic_risk

═══════════════════════════════════════════════════
PATTERNS THAT ACTUALLY PASS (Sharpe > 1.25, Fitness > 1.0)
═══════════════════════════════════════════════════

MULTI-FACTOR (the winning pattern — combine 2 DIFFERENT data sources):
  rank(signal_A * signal_B)          — multiplicative RAW (best — captures interaction effects)
  rank(signal_A) * rank(signal_B)    — multiplicative ranked (good)
  rank(signal_A) + rank(signal_B)    — additive (baseline, weaker than multiplicative)
  Research shows multiplicative outperforms additive in 65%+ of backtests.
  Component A: fundamental ratio, debt trend, earnings revision, options IV
  Component B: short-term price reversion, vwap deviation, volume anomaly

CONDITIONAL ENTRY:
  trade_when(vol_condition, rank(signal), -1) — only trade during vol regimes
  trade_when(volume > ts_mean(volume, 40), rank(-returns), -1)

INDUSTRY-RELATIVE:
  group_rank(signal, industry)  — outperforms rank() for fundamentals 78% of the time

CRITICAL RULES:
  1. Every expression MUST contain rank() or group_rank()
  2. Options/news/sentiment data: ALWAYS wrap in ts_backfill(field, 60) first
  3. Fundamental scores (fscore_*): ALWAYS multiply by rank(cap) or rank(adv20)
  4. Keep it simple: 1-3 nested calls. Complex = overfit = low fitness.
  5. Output ONLY the raw expression — no numbering, no explanation, no markdown
"""


def _build_generation_prompt(
    *,
    submitted_exprs: list[str],
    best_near_passers: list[dict],
    underexplored_categories: list[str],
    recent_failures: list[dict],
    recent_eligible_count: int,
    num_expressions: int = 5,
) -> str:
    """Build hypothesis-first user prompt with portfolio context."""

    submitted_section = ""
    if submitted_exprs:
        submitted_section = "ALREADY SUBMITTED — do NOT generate variants of these:\n"
        for expr in submitted_exprs[:20]:
            submitted_section += f"  {expr}\n"

    near_passer_section = ""
    if best_near_passers:
        near_passer_section = "\nNEAR-PASSERS — these almost worked, learn from them:\n"
        for np in best_near_passers[:6]:
            near_passer_section += (
                f"  S={np.get('sharpe', 0):.2f} F={np.get('fitness', 0):.2f} "
                f"Fail={np.get('reason', '?')} → {np.get('expression', '?')}\n"
            )

    failure_section = ""
    if recent_failures:
        failure_section = "\nSYNTAX ERRORS — avoid these mistakes:\n"
        for f in recent_failures[:4]:
            failure_section += (
                f"  {f.get('error', '?')} → {f.get('expression', '?')[:60]}\n"
            )

    underexplored_section = ""
    if underexplored_categories:
        underexplored_section = (
            f"\nUNDEREXPLORED CATEGORIES — prioritize these: {', '.join(underexplored_categories)}\n"
        )

    return f"""Generate {num_expressions} alpha expressions. Each must target a DIFFERENT market anomaly.

{submitted_section}
{near_passer_section}
{failure_section}
{underexplored_section}

OVERUSED FIELDS — do NOT use these, they've been tried hundreds of times:
  cashflow_efficiency_rank_derivative, growth_potential_rank_derivative, operating_income

Rules:
- Each expression uses DIFFERENT primary data fields from every other expression
- Each expression uses DIFFERENT data from the already-submitted list above
- Prefer multiplicative combos: rank(A * B) or rank(A) * rank(B)
- Keep it simple: 1-3 function calls max
- Total portfolio: {recent_eligible_count} alphas. We need DIVERSE data sources.

CRITICAL: Output EXACTLY {num_expressions} raw expressions, one per line.
NO explanations, NO numbering, NO bullet points, NO markdown.
Just {num_expressions} lines of pure FastExpression code."""


# ── API clients ──────────────────────────────────────────────────────

class LLMClient:
    """Handles API calls to Gemini and Groq with automatic fallback."""

    def __init__(self):
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.groq_key = os.environ.get("GROQ_API_KEY", "")
        self._gemini_calls_today = 0
        self._groq_calls_today = 0
        self._last_reset_day = 0

    def _reset_daily_counters(self):
        today = int(time.time() // 86400)
        if today != self._last_reset_day:
            self._gemini_calls_today = 0
            self._groq_calls_today = 0
            self._last_reset_day = today

    def generate(self, system_prompt: str, user_prompt: str) -> str | None:
        """Try Gemini first, fall back to Groq. Returns raw text or None."""
        self._reset_daily_counters()

        # Try Gemini (250 RPD limit — keep 10 buffer)
        if self.gemini_key and self._gemini_calls_today < 240:
            result = self._call_gemini(system_prompt, user_prompt)
            if result is not None:
                self._gemini_calls_today += 1
                return result

        # Fallback to Groq GPT-OSS 120B (1000 RPD limit)
        if self.groq_key and self._groq_calls_today < 950:
            result = self._call_groq(system_prompt, user_prompt)
            if result is not None:
                self._groq_calls_today += 1
                return result

        return None

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str | None:
        """Call Google Gemini 2.5 Flash via REST API."""
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={self.gemini_key}"
            )
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1500,
                },
            }
            resp = requests.post(url, json=payload, timeout=30)

            if resp.status_code == 429:
                print("[LLM] Gemini rate limited")
                return None
            if resp.status_code != 200:
                print(f"[LLM] Gemini error {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return text.strip() if text else None

        except Exception as exc:
            print(f"[LLM] Gemini exception: {exc}")
            return None

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str | None:
        """Call Groq GPT-OSS 120B (OpenAI-compatible). Prompt caching is automatic."""
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 1500,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code == 429:
                print("[LLM] Groq rate limited")
                return None
            if resp.status_code != 200:
                print(f"[LLM] Groq error {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return None

            text = choices[0].get("message", {}).get("content", "")
            return text.strip() if text else None

        except Exception as exc:
            print(f"[LLM] Groq exception: {exc}")
            return None

    @property
    def available(self) -> bool:
        return bool(self.gemini_key or self.groq_key)


# ── Expression validation ────────────────────────────────────────────

def validate_expression(expr: str) -> tuple[bool, str]:
    """
    Validate that an LLM-generated expression is syntactically plausible
    AND uses real WQ data fields.
    Returns (is_valid, reason).
    """
    expr = expr.strip()

    if not expr:
        return False, "empty"

    if len(expr) > 500:
        return False, "too_long"

    if len(expr) < 8:
        return False, "too_short"

    # Must not contain Python/code artifacts
    for bad in ["import ", "def ", "print(", "return ", "lambda ", "class ", "#", "//", "```", "\"", "'"]:
        if bad in expr:
            return False, f"contains_code: {bad}"

    # Must not start with a number (likely a list item)
    if re.match(r"^\d+[\.\):]", expr):
        return False, "starts_with_number"

    # Check balanced parentheses
    depth = 0
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            return False, "unbalanced_parens"
    if depth != 0:
        return False, "unbalanced_parens"

    # Must contain at least one function call
    if "(" not in expr:
        return False, "no_function_calls"

    # Check for locked operators
    expr_lower = expr.lower()
    for locked in LOCKED_OPERATORS:
        if locked in expr_lower:
            return False, f"locked_operator: {locked}"

    # Must contain rank() somewhere
    if "rank" not in expr_lower and "group_rank" not in expr_lower:
        return False, "no_rank"

    # Field validation: extract all potential field names and check at least one is valid
    # Extract words that could be field names (not operators, not numbers, not keywords)
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr)
    non_operator_tokens = [
        t for t in tokens
        if t not in VALID_OPERATORS
        and t not in LOCKED_OPERATORS
        and t not in {"rettype", "range", "true", "false", "True", "False"}
        and not t.startswith("ts_")
        and not t.startswith("vec_")
    ]

    if non_operator_tokens:
        # At least one non-operator token must be a valid field
        valid_count = sum(1 for t in non_operator_tokens if t in VALID_FIELDS)
        if valid_count == 0:
            bad_fields = list(set(non_operator_tokens))[:3]
            return False, f"no_valid_fields: {bad_fields}"

    return True, "ok"


def parse_expressions(raw_text: str) -> list[str]:
    """
    Parse LLM output into individual expressions.
    Handles numbered lists, bullet points, and raw lines.
    """
    valid, _ = parse_expressions_with_errors(raw_text)
    return valid


def parse_expressions_with_errors(raw_text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Parse LLM output, returning (valid_expressions, [(failed_expr, reason), ...]).
    Used for self-correcting retry.
    """
    if not raw_text:
        return [], []

    lines = raw_text.strip().split("\n")
    expressions = []
    failures = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Strip common prefixes: "1. ", "- ", "* ", "1) ", etc.
        line = re.sub(r"^[\d]+[\.\):\-]\s*", "", line)
        line = re.sub(r"^[-*•]\s*", "", line)
        line = line.strip()

        # Strip markdown code backticks
        line = line.strip("`")
        line = line.strip()

        if not line:
            continue

        # Skip lines that look like explanations
        lower = line.lower()
        if any(w in lower for w in [
            "this ", "the ", "here ", "note:", "explanation",
            "because", "where ", "uses ", "combines ", "measures ",
            "//", "/*", "output:", "expression", "alpha",
        ]):
            continue

        valid, reason = validate_expression(line)
        if valid:
            expressions.append(line)
        else:
            failures.append((line, reason))

    return expressions, failures


# ── Main generator class ─────────────────────────────────────────────

class LLMAlphaGenerator:
    """
    Generates alpha expressions using LLM APIs.
    Integrated into the bot's candidate generation flow.
    """

    def __init__(self):
        self.client = LLMClient()
        self._cache: list[str] = []
        self._total_generated = 0
        self._total_valid = 0
        self._total_api_calls = 0
        self._total_failed_calls = 0
        self._recent_failures: list[dict] = []  # Track failed expressions for feedback
        self._last_api_call_time: float = 0.0  # v5.9: Rate limit cooldown

    @property
    def available(self) -> bool:
        return self.client.available

    def record_failure(self, expression: str, error: str):
        """Record a failed expression so the LLM can learn from it."""
        self._recent_failures.append({
            "expression": expression,
            "error": error,
        })
        # Keep only last 10 failures
        if len(self._recent_failures) > 10:
            self._recent_failures = self._recent_failures[-10:]

    def get_expression(
        self,
        *,
        submitted_exprs: list[str] | None = None,
        best_near_passers: list[dict] | None = None,
        underexplored_categories: list[str] | None = None,
        recent_eligible_count: int = 0,
    ) -> str | None:
        """
        Get a single novel expression. Uses cached buffer when available,
        refills from LLM when empty.
        """
        if self._cache:
            return self._cache.pop(0)

        self._refill_cache(
            submitted_exprs=submitted_exprs or [],
            best_near_passers=best_near_passers or [],
            underexplored_categories=underexplored_categories or [],
            recent_eligible_count=recent_eligible_count,
        )

        if self._cache:
            return self._cache.pop(0)

        return None

    def _refill_cache(
        self,
        submitted_exprs: list[str],
        best_near_passers: list[dict],
        underexplored_categories: list[str],
        recent_eligible_count: int,
    ) -> None:
        """Call LLM to generate a batch of expressions."""
        # v5.9: Rate limit cooldown — prevent Gemini 429 errors
        import config as _cfg
        cooldown = getattr(_cfg, "LLM_COOLDOWN_SECONDS", 30)
        now = time.time()
        elapsed = now - self._last_api_call_time
        if elapsed < cooldown:
            wait = cooldown - elapsed
            print(f"[LLM] Cooldown: waiting {wait:.0f}s before next API call")
            time.sleep(wait)

        self._last_api_call_time = time.time()
        self._total_api_calls += 1

        user_prompt = _build_generation_prompt(
            submitted_exprs=submitted_exprs,
            best_near_passers=best_near_passers,
            underexplored_categories=underexplored_categories,
            recent_failures=self._recent_failures,
            recent_eligible_count=recent_eligible_count,
            num_expressions=6,
        )

        raw = self.client.generate(SYSTEM_PROMPT, user_prompt)
        if raw is None:
            self._total_failed_calls += 1
            print("[LLM_GEN] API call failed — no expressions generated")
            return

        expressions, failures = parse_expressions_with_errors(raw)
        self._total_generated += len(expressions)
        self._total_valid += len(expressions)

        # v6.1: Self-correcting retry — feed errors back to LLM for fixing
        max_retries = getattr(_cfg, "LLM_AST_RETRY_MAX", 1)
        if failures and len(expressions) < 3 and max_retries > 0:
            retry_prompt = "These expressions had syntax errors. Fix each one and output ONLY the corrected expressions, one per line:\n\n"
            for failed_expr, reason in failures[:4]:
                retry_prompt += f"  ERROR: {reason}\n  EXPRESSION: {failed_expr}\n\n"
            retry_prompt += "Output ONLY corrected expressions — no explanation, no numbering."

            # Respect cooldown
            time.sleep(max(2, cooldown - (time.time() - self._last_api_call_time)))
            self._last_api_call_time = time.time()
            self._total_api_calls += 1

            retry_raw = self.client.generate(SYSTEM_PROMPT, retry_prompt)
            if retry_raw:
                fixed = parse_expressions(retry_raw)
                if fixed:
                    expressions.extend(fixed)
                    self._total_generated += len(fixed)
                    self._total_valid += len(fixed)
                    print(f"[LLM_AST_RETRY] Fixed {len(fixed)}/{len(failures)} failed expressions")

        if expressions:
            self._cache.extend(expressions)
            print(
                f"[LLM_GEN] Generated {len(expressions)} valid expressions "
                f"(api_calls={self._total_api_calls} total_valid={self._total_valid} "
                f"failed_calls={self._total_failed_calls})"
            )
            for i, expr in enumerate(expressions):
                print(f"  [LLM_EXPR_{i}] {expr}")
        else:
            self._total_failed_calls += 1
            print(f"[LLM_GEN] No valid expressions from LLM output. Raw: {raw[:300]}")

    def stats(self) -> dict[str, int]:
        return {
            "total_generated": self._total_generated,
            "total_valid": self._total_valid,
            "total_api_calls": self._total_api_calls,
            "total_failed_calls": self._total_failed_calls,
            "cache_size": len(self._cache),
            "tracked_failures": len(self._recent_failures),
        }
