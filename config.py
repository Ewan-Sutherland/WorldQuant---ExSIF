from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "bot.db"

# Storage backend: "sqlite" or "supabase"
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "sqlite")

# Supabase credentials (only needed if STORAGE_BACKEND = "supabase")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# Environment / API
BRAIN_USERNAME = os.getenv("BRAIN_USERNAME", "")
BRAIN_PASSWORD = os.getenv("BRAIN_PASSWORD", "")

# Scheduler / runtime
MAX_CONCURRENT_SIMS = 3
POLL_INTERVAL_SECONDS = 20
SESSION_REFRESH_MINUTES = 150
SIM_TIMEOUT_MINUTES = 45

# Default simulation settings
DEFAULT_REGION = "USA"
DEFAULT_DELAY = 1
DEFAULT_UNIVERSES = ["TOP3000", "TOP1000", "TOP500", "TOP200", "TOPSP500"]
DEFAULT_NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"]
DEFAULT_DECAYS = [2, 4, 6, 8, 10, 12]
DEFAULT_TRUNCATIONS = [0.03, 0.05, 0.08, 0.10]

DEFAULT_INSTRUMENT_TYPE = "EQUITY"
DEFAULT_VISUALIZATION = False

DEFAULT_PASTEURIZATION = "ON"
DEFAULT_UNIT_HANDLING = "VERIFY"
DEFAULT_NAN_HANDLING = "OFF"
DEFAULT_MAX_STOCK_WEIGHT = 0.10
DEFAULT_LANGUAGE = "FASTEXPR"

# Evaluation thresholds
MIN_SHARPE = 1.25
MIN_FITNESS = 1.00
MAX_TURNOVER = 0.70

# Near-passer / refinement settings
NEAR_PASSER_MIN_SHARPE = 1.35
NEAR_PASSER_MIN_FITNESS = 0.75
NEAR_PASSER_MAX_TURNOVER = 0.75
REFINEMENT_PROBABILITY = 0.65

MIN_REFINEMENT_SHARPE = 1.20
FRONTIER_MIN_SHARPE = 1.25
FRONTIER_MIN_FITNESS = 0.65
FRONTIER_ALT_MIN_SHARPE = 1.45
FRONTIER_ALT_MIN_FITNESS = 0.68

# Frontier templates worth exploiting more aggressively
STRONG_TEMPLATES = {"cs_02", "pvc_04", "vol_03", "cond_01", "va_02", "mr_02", "pvc_03", "fs_04", "fs_05", "fs_06", "opt_03", "opt_04"}
ELITE_TEMPLATES = {"mr_04", "vol_03", "va_02", "cond_01"}

# Diversity / anti-self-correlation
DIVERSITY_LOOKBACK_RUNS = 120
MAX_RECENT_TEMPLATE_COUNT = 20
RELAXED_TEMPLATE_COUNT = 14
RELAXED_TEMPLATE_MIN_AVG_SHARPE = 1.30
RELAXED_TEMPLATE_MIN_AVG_FITNESS = 0.70
DIVERSITY_EXPLORATION_PROBABILITY = 0.12
MAX_REFINEMENT_ATTEMPTS_PER_BASE = 7
MAX_CORE_SIGNAL_EXHAUSTIONS = 3  # After 3 exhausted refinement cycles for same core signal, stop
MAX_FAMILY_TEMPLATE_EXHAUSTIONS = 5  # After 5 exhausted cycles for same family+template combo, stop
LOCAL_REFINEMENT_HISTORY = 10
LOCAL_REFINEMENT_MAX_SIMILARITY = 0.90

# Template scoring / pruning
TEMPLATE_SCORE_LOOKBACK_RUNS = 180
MIN_TEMPLATE_OBS_FOR_PRUNE = 6

HARD_PRUNE_MAX_AVG_SHARPE = 0.20
HARD_PRUNE_MAX_AVG_FITNESS = 0.10

SOFT_PRUNE_MAX_AVG_SHARPE = 0.60
SOFT_PRUNE_MAX_AVG_FITNESS = 0.35

TEMPLATE_EXPLORATION_PROBABILITY = 0.10
SOFT_PRUNE_REFINEMENT_PROBABILITY = 0.35

# Submission behaviour
AUTO_SUBMIT = True

# Submission diversity / self-correlation avoidance
# Structural similarity threshold: if candidate > this vs any submitted alpha, flag as correlated
# This is a PROXY for PnL correlation — structural sim 0.50+ typically means PnL corr > 0.70
SUBMISSION_MAX_SIMILARITY = 0.45
# Boost factor for families NOT yet represented in submissions
UNSUBMITTED_FAMILY_BOOST = 1.60

# Logging / reporting
REPORT_EVERY_N_COMPLETIONS = 25

# Family/template weighting
DEFAULT_FAMILY_ORDER = [
    # v5.7: New signal classes — HIGH PRIORITY (different data categories)
    "fundamental_value",
    "quality_trend",
    "fundamental_scores",
    "earnings_momentum",
    "options_vol",
    "news_sentiment",
    "vol_regime",
    "size_value",
    # Existing — medium priority
    "cross_sectional",
    "liquidity_scaled",
    "conditional",
    "analyst_sentiment",
    "volume_flow",
    "price_vol_corr",
    "vol_adjusted",
    "volatility",
    "intraday",
    "fundamental",
    "mean_reversion",
    "momentum",
]

FAMILY_BASE_WEIGHTS = {
    # v5.7: SATURATED — all 6 submissions are returns mean reversion
    "mean_reversion": 0.10,
    "cross_sectional": 0.10,
    "liquidity_scaled": 0.15,
    "conditional": 0.15,
    "vol_adjusted": 0.10,
    # v5.7: HIGH PRIORITY — new signal classes, different data categories
    "fundamental_value": 1.50,
    "quality_trend": 1.50,
    "fundamental_scores": 1.80,  # fs_05 avg_fitness=1.064, closest to new submission
    "earnings_momentum": 1.60,
    "options_vol": 1.40,
    "news_sentiment": 1.40,
    "vol_regime": 1.30,
    "size_value": 1.00,
    # MEDIUM — legacy
    "volume_flow": 0.40,
    "price_vol_corr": 0.40,
    "analyst_sentiment": 0.60,
    "volatility": 0.20,
    "intraday": 0.20,
    "fundamental": 0.20,
    "momentum": 0.05,
}

TEMPLATE_BASE_WEIGHTS = {
    # v5.7: New signal class templates — high priority
    "fv_05": 1.60,      # ts_rank fundamental ratio, 252 days — from WQ seminar
    "fv_06": 1.55,      # group_rank ts_rank — WQ seminar variant
    "qt_04": 1.50,      # ts_rank cashflow/debt, 252 days
    "qt_06": 1.45,      # group_rank cashflow/debt
    "em_01": 1.50,      # net earnings revision — direct analyst signal
    "em_07": 1.45,      # group_rank earnings surprise
    "opt_05": 1.60,     # PCR timing — directly from WQ researcher
    "opt_06": 1.55,     # IV momentum — directly from WQ researcher
    "opt_07": 1.50,     # PCR OI × liquidity
    "ns_01": 1.40,      # scl12_sentiment
    "ns_03": 1.40,      # rp_ess_earnings
    "vr_01": 1.70,      # WQ researcher said "works really well!"
    "vr_03": 1.40,      # regression reversion
    "fs_07": 1.50,      # derivative fields × adv20
    "fs_08": 1.45,      # derivative fields × cap, smoothed
    # Existing good templates
    "fs_04": 1.60,
    "fs_05": 1.55,
    "fs_06": 1.50,
    "opt_03": 1.40,
    "opt_04": 1.35,
    # Legacy — reduced
    "cs_02": 0.80,      # Was 1.50 — saturated (3 submissions)
    "pvc_04": 1.00,
    "vol_03": 0.80,
    "mr_02": 0.50,
    "cond_01": 0.50,    # Was 1.10 — already submitted
    "mr_04": 0.30,      # Was 0.90 — 2 submissions already
    "pvc_03": 0.60,
    "mr_01": 0.40,
}

PREFERRED_TEMPLATE_BOOSTS = {
    "mr_04": 1.35,
    "vol_03": 1.40,
    "va_02": 1.20,
    "mr_01": 1.15,
    "cond_01": 1.10,
    "fs_04": 1.50,      # v5.5: liquidity-weighted fscore — unlocks highest fitness signal
    "fs_05": 1.45,      # v5.5: adv20-weighted fscore
    "opt_03": 1.30,     # v5.5: under-tested, different data category
    "opt_04": 1.25,     # v5.5: under-tested, different data category
}

TEMPLATE_WEIGHT_PENALTIES = {
    "va_01": 0.35,
    "vol_02": 0.30,
    "cond_03": 0.40,
    # v5.5: penalize original fscore templates — consistently fail CONCENTRATED_WEIGHT
    "fs_01": 0.40,      # Unweighted fscore delta — concentrates weight
    "fs_02": 0.30,      # Unweighted fscore zscore — 34x identical failures in v5.4
    "fs_03": 0.40,      # Unweighted group_rank fscore — same issue
}

DISABLED_REFINEMENT_TEMPLATES = {"vol_02"}
SOFT_BLOCK_REFINEMENT_TEMPLATES = {"cond_03", "va_01"}
SOFT_BLOCK_REFINEMENT_PROB = 0.08

REFINEMENT_TEMPLATE_SWITCH_PROB = 0.12
REFINEMENT_ELITE_STAY_PROB = 0.90
REFINEMENT_ELITE_FITNESS_STAY_PROB = 0.96
REFINEMENT_ELITE_TURNOVER_STAY_PROB = 0.98
REFINEMENT_ELITE_SHARPE_STAY_PROB = 0.84

LIGHT_POST_PROCESS_SMOOTH_PROB = 0.34
FRESH_FORCE_SMOOTH_PROB = 0.74
FRESH_RAW_RANK_PROB = 0.02
PREFER_TS_MEAN_WINDOW = [3, 5, 10]

# v5.6: LLM generation
# Probability of trying LLM generation instead of templates for fresh candidates
LLM_GENERATION_PROBABILITY = 0.20

# ── v5.7: Signal-class settings profiles ─────────────────────────────
# Each signal class has preferred settings based on WQ researcher recommendations.
# 85% of sims use these profiles, 15% explore full setting space.
SIGNAL_CLASS_SETTINGS = {
    # Fundamental — quarterly data, long lookback, subindustry neutral
    "fundamental_value": {"universes": ["TOP3000"], "neutralizations": ["SUBINDUSTRY"], "decays": [0, 2, 4], "truncations": [0.05, 0.08]},
    "quality_trend": {"universes": ["TOP3000"], "neutralizations": ["SUBINDUSTRY"], "decays": [0, 2, 4], "truncations": [0.05, 0.08]},
    "size_value": {"universes": ["TOP3000"], "neutralizations": ["SUBINDUSTRY"], "decays": [0, 2, 4], "truncations": [0.05, 0.08]},
    # Fundamental scores — mid universe, some smoothing
    "fundamental_scores": {"universes": ["TOP1000", "TOP500"], "neutralizations": ["SUBINDUSTRY", "INDUSTRY"], "decays": [4, 6, 8], "truncations": [0.05]},
    # Earnings momentum — daily data, broad universe
    "earnings_momentum": {"universes": ["TOP3000", "TOP1000"], "neutralizations": ["NONE", "INDUSTRY"], "decays": [2, 4, 6], "truncations": [0.05, 0.08]},
    # Options — from WQ researcher: industry neutral, trunc 0.03, decay 0
    "options_vol": {"universes": ["TOP3000"], "neutralizations": ["INDUSTRY"], "decays": [0, 2, 4], "truncations": [0.03, 0.05]},
    # News/sentiment — liquid universe, minimal neutral
    "news_sentiment": {"universes": ["TOP1000", "TOP500"], "neutralizations": ["NONE", "MARKET"], "decays": [2, 4, 6], "truncations": [0.05, 0.08]},
    # Vol regime — market neutral
    "vol_regime": {"universes": ["TOP3000", "TOP1000"], "neutralizations": ["MARKET", "NONE"], "decays": [4, 6, 8], "truncations": [0.05, 0.08]},
}

# v5.7: Minimum exploration guarantee per family
# Each family MUST get at least this many sims before adaptive weighting can downweight it
MIN_EXPLORATION_PER_FAMILY = 25
