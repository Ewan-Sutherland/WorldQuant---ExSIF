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


# ── Operators ───────────────────────────────────────────────────────

VALID_OPERATORS = {
    "rank", "group_rank", "ts_mean", "ts_std_dev", "ts_zscore", "ts_rank",
    "ts_delta", "ts_decay_linear", "ts_corr", "ts_sum", "ts_min", "ts_max",
    "ts_argmin", "ts_argmax", "ts_covariance", "ts_product", "ts_backfill",
    "ts_count_nans", "ts_regression", "ts_step",
    "trade_when", "abs", "log", "sign", "max", "min", "power",
    "is_nan", "bucket", "densify",
    "vec_avg", "vec_count", "vec_sum", "vec_max", "vec_min",
    "vec_stddev", "vec_range", "vec_ir",
}

LOCKED_OPERATORS = {"ts_skewness", "ts_kurtosis", "ts_momentum"}


# ── Comprehensive system prompt ─────────────────────────────────────

SYSTEM_PROMPT = """You are an expert quantitative researcher generating alpha expressions for WorldQuant BRAIN's IQC 2026 competition.

An alpha expression is a mathematical formula that ranks stocks to predict which will outperform or underperform over the next day. Output ONLY raw FastExpression syntax — no Python, no pseudocode, no explanations.

═══════════════════════════════════════════════════
COMPLETE OPERATOR REFERENCE
═══════════════════════════════════════════════════

ARITHMETIC: +, -, *, /, abs(x), log(x), sign(x), max(x,y), min(x,y), power(x,n)

RANKING (cross-sectional, applied across all stocks each day):
  rank(x)                         — rank stocks 0 to 1
  group_rank(x, group)            — rank within group (industry/subindustry/sector/market)

TIME SERIES (applied per-stock across time):
  ts_mean(x, n)                   — rolling mean over n days
  ts_std_dev(x, n)                — rolling standard deviation
  ts_zscore(x, n)                 — (x - ts_mean(x,n)) / ts_std_dev(x,n)
  ts_rank(x, n)                   — percentile rank within window
  ts_delta(x, n)                  — x - x[n days ago]
  ts_decay_linear(x, n)           — linearly weighted mean (recent days weighted more)
  ts_corr(x, y, n)                — rolling correlation between x and y
  ts_sum(x, n)                    — rolling sum
  ts_min(x, n)                    — rolling minimum
  ts_max(x, n)                    — rolling maximum
  ts_argmin(x, n)                 — days since min in window
  ts_argmax(x, n)                 — days since max in window
  ts_covariance(x, y, n)          — rolling covariance
  ts_product(x, n)                — rolling product
  ts_backfill(x, n)               — fill NaN gaps using last valid value (REQUIRED for options/news data)
  ts_count_nans(x, n)             — count NaN values in window
  ts_regression(y, x, n, rettype) — rolling regression (rettype=2 for slope)
  ts_step(n)                      — generates 1,2,3,...,n sequence (use as x in ts_regression for trend)

CONDITIONAL:
  trade_when(cond, x, default)    — use x when cond is true, else default (usually -1)

VECTOR → MATRIX (for news/event vector data):
  vec_avg(x), vec_count(x), vec_sum(x), vec_max(x), vec_min(x), vec_stddev(x)

GROUPING:
  bucket(x, range='start, end, step')  — create custom groups
  densify(group)                        — remove empty groups (use before group_rank)

LOCKED — DO NOT USE: ts_skewness, ts_kurtosis, ts_momentum

═══════════════════════════════════════════════════
COMPLETE DATA FIELD REFERENCE
═══════════════════════════════════════════════════

PRICE & VOLUME (updated daily, reliable, no NaN):
  close, open, high, low, vwap, returns, volume, adv20, cap, sharesout, split, dividend

FUNDAMENTAL DATA (updated quarterly — use lookback windows 60-252):
  Core: assets, sales, income, cash, debt, equity, eps, ebitda, ebit, enterprise_value
  Balance Sheet: bookvalue_ps, capex, cashflow, cashflow_op, cogs, cash_st, current_ratio
  Extended: assets_curr, debt_lt, debt_st, depre_amort, employee, cashflow_dividends,
            cashflow_fin, cashflow_invst

FUNDAMENTAL SCORES (model16 dataset — covers ~1500 stocks, USE ts_backfill OR multiply by rank(cap)):
  BFL scores: fscore_bfl_value, fscore_bfl_momentum, fscore_bfl_quality,
              fscore_bfl_growth, fscore_bfl_profitability, fscore_bfl_total,
              fscore_bfl_surface, fscore_bfl_surface_accel
  Base scores: fscore_value, fscore_momentum, fscore_quality, fscore_growth,
               fscore_profitability, fscore_total, fscore_surface, fscore_surface_accel
  Derivatives: analyst_revision_rank_derivative, cashflow_efficiency_rank_derivative,
               composite_factor_score_derivative, earnings_certainty_rank_derivative,
               growth_potential_rank_derivative, relative_valuation_rank_derivative

RESEARCH SENTIMENT (sentiment1 — updated daily):
  snt1_d1_earningssurprise, snt1_d1_netearningsrevision, snt1_d1_earningsrevision,
  snt1_d1_dynamicfocusrank, snt1_d1_stockrank, snt1_d1_fundamentalfocusrank,
  snt1_d1_buyrecpercent, snt1_d1_sellrecpercent, snt1_d1_netrecpercent,
  snt1_d1_longtermepsgrowthest, snt1_d1_analystcoverage,
  consensus_analyst_rating, snt1_cored1_score

SOCIAL MEDIA SENTIMENT (socialmedia12):
  scl12_buzz, scl12_sentiment, scl12_buzz_fast_d1, scl12_sentiment_fast_d1,
  snt_buzz, snt_buzz_bfl, snt_value, snt_social_value

VOLATILITY DATA (option8 — has NaN, use ts_backfill):
  implied_volatility_call_{10,20,30,60,90,120,150,180,270,360,720,1080}
  implied_volatility_put_{10,20,30,60,90,120,150,180,270,360,720,1080}
  implied_volatility_mean_{10,20,30,60,90,120,150,180,270,360,720,1080}
  implied_volatility_mean_skew_{10,20,30,60,90,120,150,180,270,360,720,1080}
  historical_volatility_{10,20,30,60,90,120,150,180}

OPTIONS ANALYTICS (option9 — has NaN, use ts_backfill):
  pcr_oi_{10,20,30,60,90,120,150,180,270,360,720,1080}   — put-call ratio (open interest)
  pcr_vol_{10,20,30,60,90,120,150,180,270,360,720,1080}  — put-call ratio (volume)
  call_breakeven_{10,20,30,60,90,120,180,270,360,720,1080}
  forward_price_{10,20,30,60,90,120,180,270,360,720,1080}

RAVENPACK NEWS (event sentiment — has NaN, use ts_backfill):
  rp_css_earnings, rp_css_revenue, rp_css_dividends, rp_css_mna, rp_css_credit,
  rp_css_price, rp_css_product, rp_css_technical
  rp_ess_earnings, rp_ess_revenue, rp_ess_dividends, rp_ess_mna, rp_ess_credit,
  rp_ess_price, rp_ess_product, rp_ess_technical

US NEWS DATA (news events — has NaN, use ts_backfill):
  news_pct_1min, news_pct_5_min, news_pct_10min, news_pct_30min, news_pct_60min
  news_max_up_ret, news_max_dn_ret, news_open_gap, news_ls

ANALYST ESTIMATES:
  est_ptp, est_fcf, est_cashflow_op, est_capex

═══════════════════════════════════════════════════
RULES AND PATTERNS
═══════════════════════════════════════════════════

STRUCTURAL PATTERNS THAT WORK (from real passing alphas, Sharpe > 1.5):
  ts_decay_linear(rank(-rank(ts_zscore(returns, N))), M)     — cross-sectional mean reversion
  rank(-(returns - ts_mean(returns, N)) * rank(adv20))        — liquidity-weighted reversion
  trade_when(volume > ts_mean(volume, N), rank(-returns), -1) — conditional reversion
  rank(ts_zscore(fscore_bfl_total, N)) * rank(adv20)          — fundamental score × liquidity
  group_rank(-ts_zscore(field, N), subindustry)               — within-group relative value

WHAT DOES NOT WORK:
  Pure momentum (rank(ts_delta(close, N))) — consistently negative Sharpe
  Simple volatility (rank(1/ts_std_dev(returns,N))) — Sharpe < 1.0
  Raw fundamental ratios without ranking/smoothing — too noisy
  Unweighted fscore signals — fail CONCENTRATED_WEIGHT (must multiply by rank(cap) or rank(adv20))

CRITICAL RULES:
  1. Every expression MUST contain rank() or group_rank()
  2. For options/news/sentiment data: ALWAYS wrap in ts_backfill(field, 60) first
  3. For fundamental scores (fscore_*): ALWAYS multiply by rank(cap) or rank(adv20)
  4. Keep expressions simple: 1-3 nested function calls. Complex = overfit.
  5. Use ts_decay_linear() or ts_mean() for smoothing — improves fitness
  6. NEVER use ts_skewness, ts_kurtosis, ts_momentum — they are LOCKED
  7. Output ONLY the raw expression — no numbering, no explanation, no markdown
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
    """Build the user prompt with context about the current portfolio."""

    submitted_section = ""
    if submitted_exprs:
        submitted_section = "ALREADY SUBMITTED (do NOT generate similar):\n"
        for expr in submitted_exprs:
            submitted_section += f"  - {expr}\n"

    near_passer_section = ""
    if best_near_passers:
        near_passer_section = "\nBEST NEAR-PASSERS (learn from these — they almost passed):\n"
        for np in best_near_passers[:8]:
            near_passer_section += (
                f"  Sharpe={np.get('sharpe', 0):.2f} Fitness={np.get('fitness', 0):.2f} "
                f"Fail={np.get('reason', '?')} → {np.get('expression', '?')}\n"
            )

    failure_section = ""
    if recent_failures:
        failure_section = "\nRECENT FAILURES (avoid these patterns):\n"
        for f in recent_failures[:6]:
            failure_section += (
                f"  ERROR={f.get('error', '?')} → {f.get('expression', '?')[:80]}\n"
            )

    underexplored_section = ""
    if underexplored_categories:
        underexplored_section = (
            "\nUNDEREXPLORED DATA CATEGORIES (prioritize these for uncorrelated alphas):\n"
            f"  {', '.join(underexplored_categories)}\n"
            "\nHigh-value underexplored fields to try:\n"
            "  - Put-call ratios: ts_backfill(pcr_oi_270, 60), ts_backfill(pcr_vol_10, 60)\n"
            "  - IV skew: ts_backfill(implied_volatility_mean_skew_30, 60)\n"
            "  - Earnings surprise: snt1_d1_earningssurprise, snt1_d1_netearningsrevision\n"
            "  - News reaction: ts_backfill(news_pct_1min, 60), ts_backfill(rp_ess_earnings, 60)\n"
            "  - Fundamental derivatives: cashflow_efficiency_rank_derivative, growth_potential_rank_derivative\n"
            "  - Trend extraction: ts_regression(close, ts_step(1), 20, rettype=2)\n"
        )

    return f"""Generate {num_expressions} novel alpha expressions for the WorldQuant BRAIN simulator.

{submitted_section}
{near_passer_section}
{failure_section}
{underexplored_section}

Requirements:
- Each expression must use DIFFERENT primary data fields from each other
- At least 2 expressions should use data from underexplored categories
- Favor simple, robust expressions (1-3 function calls)
- Include rank() in every expression
- For options/news/sentiment data, ALWAYS use ts_backfill(field, 60)
- For fscore_* fields, ALWAYS multiply by rank(cap) or rank(adv20)
- Total submitted alphas: {recent_eligible_count} — we need MORE from DIVERSE data sources

Output EXACTLY {num_expressions} expressions, one per line.
Raw expression text only — no numbering, no explanation, no markdown."""


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
    if not raw_text:
        return []

    lines = raw_text.strip().split("\n")
    expressions = []

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

    return expressions


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

        expressions = parse_expressions(raw)
        self._total_generated += len(expressions)
        self._total_valid += len(expressions)

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
