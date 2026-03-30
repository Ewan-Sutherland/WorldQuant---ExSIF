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
                multivariate=True,
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
        settings = self._trial_to_settings(trial)

        # Check if this exact combo was already tried
        tried_combos = set()
        for t in study.trials:
            if t.state == optuna.trial.TrialState.COMPLETE:
                combo = (
                    t.params.get("universe"),
                    t.params.get("neutralization"),
                    t.params.get("decay"),
                    t.params.get("truncation"),
                )
                tried_combos.add(combo)

        suggested_combo = (
            settings["universe"],
            settings["neutralization"],
            settings["decay"],
            settings["truncation"],
        )

        if suggested_combo in tried_combos:
            # Already tried this exact combo — try a second suggestion
            study.tell(trial, 0.0)  # Report dummy value
            trial2 = study.ask()
            settings = self._trial_to_settings(trial2)

        print(
            f"[OPTUNA] Suggested settings (warm={n_warm}): "
            f"univ={settings['universe']} neut={settings['neutralization']} "
            f"decay={settings['decay']} trunc={settings['truncation']}"
        )
        return settings

    def _trial_to_settings(self, trial) -> dict:
        """Convert an Optuna trial to BRAIN settings dict."""
        return {
            "universe": trial.suggest_categorical("universe", UNIVERSES),
            "neutralization": trial.suggest_categorical("neutralization", NEUTRALIZATIONS),
            "decay": trial.suggest_int("decay", 0, 12, step=2),
            "truncation": trial.suggest_categorical("truncation", TRUNCATIONS),
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
