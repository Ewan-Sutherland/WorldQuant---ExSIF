"""
v6.0: Warm-started Bayesian settings optimizer using Optuna TPE.

When a near-passer alpha (high Sharpe, low fitness) is stuck, this module
uses historical sim data to intelligently suggest the next settings combo
instead of random sampling.

Usage in bot.py:
    from settings_optimizer import SettingsOptimizer
    optimizer = SettingsOptimizer(storage)
    suggested_settings = optimizer.suggest(expression, current_metrics)
"""
from __future__ import annotations

try:
    import optuna
    from optuna.samplers import TPESampler
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False


# BRAIN settings search space
UNIVERSES = ["TOP200", "TOP500", "TOP1000", "TOP3000"]
NEUTRALIZATIONS = ["NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"]
DECAYS = [0, 2, 4, 6, 8, 10, 12]
TRUNCATIONS = [0.01, 0.03, 0.05, 0.08, 0.10]




def expression_delay0_safe(expression: str) -> bool:
    """Conservative delay-0 safety check.

    Delay-0 alphas should not use same-day price/return tokens directly.
    We allow these tokens when they are inside explicit time-series wrappers
    such as ts_mean(...), ts_rank(...), ts_delta(...), ts_delay(...), etc.
    This is intentionally conservative: false negatives cost a sim; false
    positives can create useless/failed d0 sweeps.
    """
    if not expression:
        return False
    import re
    expr_l = expression.lower()
    risky = {"returns", "close", "open", "high", "low", "vwap"}

    def strip_ts_wrappers(s: str) -> str:
        prev = None
        for _ in range(12):
            if s == prev:
                break
            prev = s
            s = re.sub(r'ts_[a-z_]+\([^()]*\)', '', s)
        return s

    stripped = strip_ts_wrappers(expr_l)
    for tok in risky:
        if re.search(rf'\b{tok}\b', stripped):
            return False
    return True


def _delay_choices_for_expression(expression: str) -> list[int]:
    """Return [0, 1] for d0-safe expressions, else [1]."""
    return [0, 1] if expression_delay0_safe(expression) else [1]


class SettingsOptimizer:
    """
    Bayesian optimizer for BRAIN simulation settings.
    Warm-starts from historical sim data to find optimal settings in 3-5 trials.
    """

    def __init__(self, storage=None):
        self.storage = storage

    def suggest(
        self,
        expression: str,
        core_signal: str = "",
        family: str = "",
        target_metric: str = "fitness",
    ) -> dict | None:
        """
        Suggest next settings to try for a given expression.
        Returns a settings dict or None if no suggestion available.
        """
        if not OPTUNA_AVAILABLE:
            return None

        # Create study with TPE sampler, warm-started
        study = optuna.create_study(
            direction="maximize",
            sampler=TPESampler(
                multivariate=False,
                warn_independent_sampling=False,
                n_startup_trials=0,  # Skip random phase — we have warm-start data
                n_ei_candidates=32,
            ),
        )

        # Warm-start from historical data
        n_warm = self._inject_historical_trials(study, expression, core_signal, family, target_metric)

        if n_warm < 3:
            # Not enough history to guide optimization — fall back to None
            return None

        # Ask Optuna for next suggestion
        trial = study.ask()
        settings = self._trial_to_settings(trial, expression)

        # v6.2: Robust dedup — collect all historical combos, retry up to 10 times
        # v7.2.1: include delay in the dedup key so d0 and d1 of same combo are distinct
        tried_combos = set()
        for t in study.trials:
            if t.state == optuna.trial.TrialState.COMPLETE:
                combo = (
                    t.params.get("universe"),
                    t.params.get("neutralization"),
                    t.params.get("decay"),
                    t.params.get("truncation"),
                    t.params.get("delay", 1),
                )
                tried_combos.add(combo)

        suggested_combo = (
            settings["universe"],
            settings["neutralization"],
            settings["decay"],
            settings["truncation"],
            settings.get("delay", 1),
        )

        # If duplicate, keep asking (up to 10 retries) before giving up
        max_dedup_retries = 10
        retries = 0
        while suggested_combo in tried_combos and retries < max_dedup_retries:
            study.tell(trial, 0.0)  # Report dummy value
            trial = study.ask()
            settings = self._trial_to_settings(trial, expression)
            suggested_combo = (
                settings["universe"],
                settings["neutralization"],
                settings["decay"],
                settings["truncation"],
                settings.get("delay", 1),
            )
            retries += 1

        if suggested_combo in tried_combos:
            # Exhausted search space — no novel suggestions left
            return None

        print(
            f"[OPTUNA] Suggested settings (warm={n_warm}): "
            f"univ={settings['universe']} neut={settings['neutralization']} "
            f"decay={settings['decay']} delay={settings.get('delay', 1)} "
            f"trunc={settings['truncation']}"
        )
        return settings

    def _trial_to_settings(self, trial, expression: str = "") -> dict:
        """Convert an Optuna trial to BRAIN settings dict.

        v7.2.1: delay is now part of the search space. Explicitly chooses [0, 1]
        for expressions that are safe at delay=0 (no raw returns/close at top
        level) — d0 alphas score 1/3 the points but live in a separate self-corr
        space, valuable when portfolio is saturated. For unsafe expressions,
        delay is locked at 1.
        """
        delay_choices = _delay_choices_for_expression(expression)
        return {
            "universe": trial.suggest_categorical("universe", UNIVERSES),
            "neutralization": trial.suggest_categorical("neutralization", NEUTRALIZATIONS),
            "decay": trial.suggest_int("decay", 0, 12, step=2),
            "truncation": trial.suggest_categorical("truncation", TRUNCATIONS),
            "delay": trial.suggest_categorical("delay", delay_choices),
        }

    def _inject_historical_trials(
        self,
        study,  # optuna.Study — type hint removed for conditional import
        expression: str,
        core_signal: str,
        family: str,
        target_metric: str,
    ) -> int:
        """
        Inject historical sim results as completed trials.
        Searches for runs with same expression, same core signal, or same family.
        Returns number of trials injected.
        """
        if self.storage is None:
            return 0

        historical_runs = []

        # Strategy 1: Exact expression matches (different settings)
        try:
            exact = self._get_runs_for_expression(expression)
            historical_runs.extend(exact)
        except Exception:
            pass

        # Strategy 2: Same core signal (variants of same underlying idea)
        if core_signal and len(historical_runs) < 30:
            try:
                core_runs = self._get_runs_for_core(core_signal)
                seen_ids = {r["run_id"] for r in historical_runs}
                for r in core_runs:
                    if r["run_id"] not in seen_ids:
                        historical_runs.append(r)
            except Exception:
                pass

        # Strategy 3: Same family (structural similarity)
        if family and len(historical_runs) < 30:
            try:
                family_runs = self._get_runs_for_family(family)
                seen_ids = {r["run_id"] for r in historical_runs}
                for r in family_runs:
                    if r["run_id"] not in seen_ids and len(historical_runs) < 50:
                        historical_runs.append(r)
            except Exception:
                pass

        # Inject as completed trials
        injected = 0
        for run in historical_runs:
            settings = run.get("settings_json") or run.get("settings") or {}
            universe = settings.get("universe")
            neutralization = settings.get("neutralization")
            decay = settings.get("decay")
            truncation = settings.get("truncation")

            # Skip if missing required settings
            if not all([universe, neutralization, decay is not None, truncation]):
                continue

            # Normalize types
            if isinstance(decay, str):
                try:
                    decay = int(decay)
                except ValueError:
                    continue
            if isinstance(truncation, str):
                try:
                    truncation = float(truncation)
                except ValueError:
                    continue

            # Skip if settings outside our search space
            if universe not in UNIVERSES:
                continue
            if neutralization not in NEUTRALIZATIONS:
                continue
            if decay not in DECAYS:
                # Round to nearest valid decay
                decay = min(DECAYS, key=lambda d: abs(d - decay))
            if truncation not in TRUNCATIONS:
                truncation = min(TRUNCATIONS, key=lambda t: abs(t - truncation))

            # Get target metric value
            if target_metric == "fitness":
                value = float(run.get("fitness") or run.get("sharpe", 0) or 0)
            else:
                value = float(run.get("sharpe", 0) or 0)

            # Skip sims with no useful data
            if value == 0:
                continue

            try:
                dist = {
                    "universe": optuna.distributions.CategoricalDistribution(UNIVERSES),
                    "neutralization": optuna.distributions.CategoricalDistribution(NEUTRALIZATIONS),
                    "decay": optuna.distributions.IntDistribution(0, 12, step=2),
                    "truncation": optuna.distributions.CategoricalDistribution(TRUNCATIONS),
                }
                trial = optuna.trial.create_trial(
                    params={
                        "universe": universe,
                        "neutralization": neutralization,
                        "decay": decay,
                        "truncation": truncation,
                    },
                    distributions=dist,
                    values=[value],
                )
                study.add_trial(trial)
                injected += 1
            except Exception:
                continue

        return injected

    def _get_runs_for_expression(self, expression: str) -> list[dict]:
        """Get all completed runs for a specific expression."""
        try:
            return self.storage.get_runs_for_expression(expression)
        except Exception:
            return []

    def _get_runs_for_core(self, core_signal: str) -> list[dict]:
        """Get runs with similar core signals."""
        try:
            return self.storage.get_runs_for_core_signal(core_signal)
        except Exception:
            return []

    def _get_runs_for_family(self, family: str) -> list[dict]:
        """Get top runs from the same family for cross-pollination."""
        try:
            return self.storage.get_runs_for_family(family)
        except Exception:
            return []
