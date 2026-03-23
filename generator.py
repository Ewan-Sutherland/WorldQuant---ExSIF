from __future__ import annotations

import json
import random
from typing import Any

import config
from canonicalize import canonicalize_expression, hash_candidate
from models import Candidate, SimulationSettings
from templates import FUNDAMENTAL_FIELDS, SAFE_PARAM_RANGES, TEMPLATE_LIBRARY


BASE_FAMILY_WEIGHTS = {
    "mean_reversion": 4.8,
    "momentum": 0.01,
    "volume_flow": 1.8,
    "vol_adjusted": 0.6,
    "fundamental": 0.01,
    "conditional": 1.9,
}


class AlphaGenerator:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    # ============================
    # PUBLIC
    # ============================

    def generate_candidate(self, family_bias=None, template_bias=None):
        family = self._sample_family(family_bias)
        template = self._sample_template(family, template_bias)

        params = self._sample_params(template["expression"])
        expr, fields = self._render(template["expression"], params)
        expr = self._post_process(expr, light=False, force_smoothing=False)

        settings = self._sample_settings(family)
        canon = canonicalize_expression(expr)
        h = hash_candidate(canon, settings.to_dict())

        return Candidate.create(
            expression=expr,
            canonical_expression=canon,
            expression_hash=h,
            template_id=template["template_id"],
            family=family,
            fields=fields,
            params=params,
            settings=settings,
        )

    def mutate_candidate(self, row, metrics_hint: dict[str, Any] | None = None):
        family = row["family"]
        template_id = row["template_id"]
        reason = str(row["reason"]) if "reason" in row.keys() else ""

        template = next(
            (t for t in TEMPLATE_LIBRARY[family] if t["template_id"] == template_id),
            None,
        )
        if template is None:
            return self.generate_candidate()

        params = json.loads(row["params_json"])
        settings = json.loads(row["settings_json"])

        mode = self._refinement_mode(reason=reason, metrics_hint=metrics_hint)
        chosen_template = self._choose_refinement_template(family, template_id, mode)

        params = self._mutate_params_for_mode(params, chosen_template["expression"], mode)
        settings = self._mutate_settings_for_mode(settings, family=family, mode=mode)

        expr, fields = self._render(chosen_template["expression"], params)
        expr = self._apply_refinement_variants(
            expr=expr,
            family=family,
            template_id=chosen_template["template_id"],
            params=params,
            mode=mode,
        )
        expr = self._post_process(
            expr,
            light=True,
            force_smoothing=(mode in {"fitness", "turnover"}),
        )

        sim = SimulationSettings(**settings)
        canon = canonicalize_expression(expr)
        h = hash_candidate(canon, sim.to_dict())

        return Candidate.create(
            expression=expr,
            canonical_expression=canon,
            expression_hash=h,
            template_id=chosen_template["template_id"],
            family=family,
            fields=self._extract_fields(expr, params, fields),
            params=params,
            settings=sim,
        )

    # ============================
    # SAMPLING
    # ============================

    def _sample_family(self, bias):
        fams = list(TEMPLATE_LIBRARY.keys())
        weights = []

        for fam in fams:
            w = BASE_FAMILY_WEIGHTS.get(fam, 1.0)
            if bias:
                w *= bias.get(fam, 1.0)
            weights.append(max(w, 0.001))

        return self.rng.choices(fams, weights=weights, k=1)[0]

    def _sample_template(self, family, bias):
        templates = TEMPLATE_LIBRARY[family]
        filtered = []
        weights = []

        for t in templates:
            tid = t["template_id"]
            base = 1.0 if not bias else max(bias.get(tid, 1.0), 0.001)
            base *= config.PREFERRED_TEMPLATE_BOOSTS.get(tid, 1.0)
            base *= config.TEMPLATE_WEIGHT_PENALTIES.get(tid, 1.0)

            if tid in getattr(config, "TINY_EXPLORATION_TEMPLATES", set()):
                if self.rng.random() > getattr(config, "TINY_EXPLORATION_PROB", 0.03):
                    continue

            if base <= 0.0:
                continue

            filtered.append(t)
            weights.append(max(base, 0.001))

        if not filtered:
            return self.rng.choice(templates)

        return self.rng.choices(filtered, weights=weights, k=1)[0]

    # ============================
    # REFINEMENT MODES / TEMPLATE SWITCHING
    # ============================

    def _refinement_mode(self, reason: str, metrics_hint: dict[str, Any] | None = None) -> str:
        txt = (reason or "").upper()
        if metrics_hint:
            turnover = metrics_hint.get("turnover")
            fitness = metrics_hint.get("fitness")
            sharpe = metrics_hint.get("sharpe")
            try:
                if turnover is not None and float(turnover) >= getattr(config, "MAX_TURNOVER", 0.70):
                    return "turnover"
            except Exception:
                pass
            try:
                if fitness is not None and float(fitness) < getattr(config, "MIN_FITNESS", 1.00):
                    return "fitness"
            except Exception:
                pass
            try:
                if sharpe is not None and float(sharpe) < getattr(config, "MIN_SHARPE", 1.25):
                    return "sharpe"
            except Exception:
                pass
        if "LOW_FITNESS" in txt:
            return "fitness"
        if "HIGH_TURNOVER" in txt:
            return "turnover"
        if "LOW_SHARPE" in txt:
            return "sharpe"
        return "general"

    def _choose_refinement_template(self, family: str, template_id: str, mode: str) -> dict[str, str]:
        templates = TEMPLATE_LIBRARY[family]
        current = next((t for t in templates if t["template_id"] == template_id), templates[0])

        stay_prob = 0.55
        if mode == "fitness":
            stay_prob = getattr(config, "LOW_FITNESS_STAY_IN_TEMPLATE_PROB", 0.80)
        elif mode == "turnover":
            stay_prob = getattr(config, "HIGH_TURNOVER_STAY_IN_TEMPLATE_PROB", 0.90)

        if self.rng.random() < stay_prob:
            return current

        switch_prob = getattr(config, "REFINEMENT_TEMPLATE_SWITCH_PROB", 0.20)
        if mode == "sharpe":
            switch_prob += 0.05
        if self.rng.random() >= switch_prob:
            return current

        sisters = [t for t in templates if t["template_id"] != template_id]
        if not sisters:
            return current

        filtered = []
        weights = []
        disabled = getattr(config, "DISABLED_REFINEMENT_TEMPLATES", set())

        for t in sisters:
            tid = t["template_id"]
            if tid in disabled:
                continue

            w = 1.0
            if tid in getattr(config, "TINY_EXPLORATION_TEMPLATES", set()):
                w *= 0.05

            if family == "mean_reversion":
                if mode in {"fitness", "turnover"} and tid in {"mr_04", "mr_01"}:
                    w *= 1.30
                elif mode == "sharpe" and tid in {"mr_02", "mr_04"}:
                    w *= 1.20
                elif tid == "mr_03":
                    w *= 0.90
            elif family == "volume_flow":
                if tid == "vol_03":
                    w *= 1.25
                elif tid == "vol_01":
                    w *= 0.85
                elif tid == "vol_02":
                    w = 0.0
            elif family == "vol_adjusted":
                if tid == "va_02":
                    w *= 1.40
                elif tid == "va_01":
                    w *= 0.35
            elif family == "conditional":
                if tid == "cond_01":
                    w *= 1.20
                elif tid == "cond_02":
                    w *= 0.75
                elif tid == "cond_03":
                    w *= 0.05

            if w <= 0.0:
                continue
            filtered.append(t)
            weights.append(max(w, 0.001))

        if not filtered:
            return current

        return self.rng.choices(filtered, weights=weights, k=1)[0]

    # ============================
    # POST PROCESSING
    # ============================

    def _post_process(self, expr: str, light: bool = False, force_smoothing: bool = False) -> str:
        if light:
            smooth_prob = 0.25
            raw_rank_prob = getattr(config, "REFINEMENT_RAW_RANK_PROB", 0.03)
        else:
            smooth_prob = getattr(config, "FRESH_FORCE_SMOOTH_PROB", 0.55)
            raw_rank_prob = getattr(config, "FRESH_RAW_RANK_PROB", 0.06)

        if force_smoothing:
            smooth_prob = max(smooth_prob, getattr(config, "REFINEMENT_FORCE_SMOOTH_PROB", 0.80))

        if self.rng.random() < smooth_prob and not expr.startswith("ts_mean"):
            w = self.rng.choice(getattr(config, "REFINEMENT_SMOOTHING_WINDOWS", [3, 5, 10]))
            if self.rng.random() < 0.65:
                expr = f"ts_mean(rank({expr}), {w})"
            else:
                expr = f"rank(ts_mean({expr}, {w}))"

        if self.rng.random() < raw_rank_prob:
            if not expr.startswith("rank("):
                expr = f"rank({expr})"

        return expr

    # ============================
    # PARAMS
    # ============================

    def _grid(self, key: str):
        desired = [3, 5, 10, 20, 40, 60]
        allowed = SAFE_PARAM_RANGES.get(key, desired)
        return [x for x in desired if x in allowed] or list(allowed)

    def _sample_params(self, template: str):
        p: dict[str, Any] = {}
        if "{n}" in template:
            p["n"] = self.rng.choice(self._grid("n"))
        if "{m}" in template:
            p["m"] = self.rng.choice(self._grid("m"))
        if "{field}" in template:
            p["field"] = self.rng.choice(FUNDAMENTAL_FIELDS)
        return p

    def _mutate_params_for_mode(self, params: dict[str, Any], template: str, mode: str) -> dict[str, Any]:
        out = dict(params)
        grid = self._grid("n")

        if "n" in out:
            if mode == "turnover":
                out["n"] = self._push_param_wider(out["n"], grid)
            elif mode == "fitness":
                if self.rng.random() < 0.70:
                    out["n"] = self._push_param_wider(out["n"], grid)
                else:
                    out["n"] = self._mutate_neighbor(out["n"], grid)
            elif mode == "sharpe":
                out["n"] = self._mutate_neighbor(out["n"], grid)
            else:
                out["n"] = self._mutate_neighbor(out["n"], grid)

        if "m" in out:
            m_grid = self._grid("m")
            if mode in {"fitness", "turnover"}:
                out["m"] = self._push_param_wider(out["m"], m_grid)
            else:
                out["m"] = self._mutate_neighbor(out["m"], m_grid)

        if "field" in out and self.rng.random() < 0.10:
            out["field"] = self.rng.choice(FUNDAMENTAL_FIELDS)

        return out

    def _mutate_neighbor(self, val, grid):
        if val not in grid:
            return self.rng.choice(grid)
        if self.rng.random() < 0.35:
            return val
        idx = grid.index(val)
        choices = [val]
        if idx > 0:
            choices.append(grid[idx - 1])
        if idx < len(grid) - 1:
            choices.append(grid[idx + 1])
        return self.rng.choice(choices)

    def _push_param_wider(self, val, grid=None):
        grid = grid or self._grid("n")
        if val not in grid:
            return self.rng.choice(grid)
        idx = grid.index(val)
        choices = [val]
        if idx < len(grid) - 1:
            choices.append(grid[idx + 1])
        if idx < len(grid) - 2:
            choices.append(grid[idx + 2])
        return self.rng.choice(choices)

    # ============================
    # SETTINGS
    # ============================

    def _sample_settings(self, family: str):
        return SimulationSettings(
            region=config.DEFAULT_REGION,
            universe=self.rng.choice(config.DEFAULT_UNIVERSES),
            delay=self.rng.choice(getattr(config, "DEFAULT_DELAYS", [config.DEFAULT_DELAY])),
            decay=self.rng.choice(config.DEFAULT_DECAYS),
            neutralization=self.rng.choice(config.DEFAULT_NEUTRALIZATIONS),
            truncation=self.rng.choice(config.DEFAULT_TRUNCATIONS),
            pasteurization=config.DEFAULT_PASTEURIZATION,
            unit_handling=config.DEFAULT_UNIT_HANDLING,
            nan_handling=config.DEFAULT_NAN_HANDLING,
            max_stock_weight=config.DEFAULT_MAX_STOCK_WEIGHT,
            language=config.DEFAULT_LANGUAGE,
        )

    def _mutate_settings_for_mode(self, settings: dict[str, Any], family: str, mode: str) -> dict[str, Any]:
        out = dict(settings)

        decays = getattr(config, "REFINEMENT_DECAYS", config.DEFAULT_DECAYS)
        universes = getattr(config, "REFINEMENT_UNIVERSES", config.DEFAULT_UNIVERSES)
        delays = getattr(config, "DEFAULT_DELAYS", [config.DEFAULT_DELAY])
        truncs = getattr(config, "REFINEMENT_TRUNCATIONS", config.DEFAULT_TRUNCATIONS)

        if "decay" in out:
            current_decay = int(out["decay"])
            if mode == "turnover":
                out["decay"] = self._bump_setting_up(current_decay, decays)
            elif mode == "fitness":
                if self.rng.random() < 0.80:
                    out["decay"] = self._bump_setting_up(current_decay, decays)
                else:
                    out["decay"] = self._mutate_setting_neighbor(current_decay, decays)
            elif mode == "sharpe":
                out["decay"] = self._mutate_setting_neighbor(current_decay, decays)
            else:
                out["decay"] = self._mutate_setting_neighbor(current_decay, decays)

        if "universe" in out and len(universes) > 1:
            if mode in {"fitness", "turnover"}:
                if self.rng.random() < getattr(config, "REFINEMENT_UNIVERSE_SWITCH_PROB", 0.28):
                    out["universe"] = self._more_liquid_universe(out["universe"], universes)
            elif mode == "sharpe" and self.rng.random() < 0.15:
                out["universe"] = self._mutate_universe_neighbor(out["universe"], universes)

        if "delay" in out and len(delays) > 1:
            if mode == "sharpe" and self.rng.random() < getattr(config, "REFINEMENT_DELAY_SWITCH_PROB", 0.0):
                out["delay"] = self._mutate_setting_neighbor(int(out["delay"]), delays)

        if "neutralization" in out and self.rng.random() < 0.22:
            choices = list(config.DEFAULT_NEUTRALIZATIONS)
            if mode in {"fitness", "turnover"}:
                out["neutralization"] = self._prefer_stabilizing_neutralization(out["neutralization"], choices)
            else:
                out["neutralization"] = self.rng.choice(choices)

        if "truncation" in out and truncs:
            current_trunc = float(out["truncation"])
            if mode in {"fitness", "turnover"}:
                if self.rng.random() < 0.50:
                    out["truncation"] = self._tighter_truncation(current_trunc, truncs)
            elif mode == "sharpe" and self.rng.random() < 0.15:
                out["truncation"] = self._mutate_setting_neighbor(current_trunc, truncs)

        if family in {"fundamental", "conditional"} and self.rng.random() < getattr(config, "REFINEMENT_NAN_EXPERIMENT_PROB", 0.02):
            out["nan_handling"] = "ON" if str(out.get("nan_handling", "OFF")).upper() == "OFF" else "OFF"
        if self.rng.random() < getattr(config, "REFINEMENT_PASTEURIZATION_EXPERIMENT_PROB", 0.01):
            out["pasteurization"] = "OFF" if str(out.get("pasteurization", "ON")).upper() == "ON" else "ON"

        return out

    def _mutate_setting_neighbor(self, value, grid):
        ordered = list(grid)
        if value not in ordered:
            return self.rng.choice(ordered)
        idx = ordered.index(value)
        choices = [value]
        if idx > 0:
            choices.append(ordered[idx - 1])
        if idx < len(ordered) - 1:
            choices.append(ordered[idx + 1])
        return self.rng.choice(choices)

    def _bump_setting_up(self, value, grid):
        ordered = list(grid)
        if value not in ordered:
            return self.rng.choice(ordered)
        idx = ordered.index(value)
        choices = [value]
        if idx < len(ordered) - 1:
            choices.append(ordered[idx + 1])
        if idx < len(ordered) - 2:
            choices.append(ordered[idx + 2])
        return self.rng.choice(choices)

    def _more_liquid_universe(self, current: str, universes: list[str]) -> str:
        ordered = list(universes)
        if current not in ordered:
            return ordered[0]
        idx = ordered.index(current)
        choices = [current]
        if idx > 0:
            choices.append(ordered[idx - 1])
        if idx > 1:
            choices.append(ordered[idx - 2])
        return self.rng.choice(choices)

    def _mutate_universe_neighbor(self, current: str, universes: list[str]) -> str:
        ordered = list(universes)
        if current not in ordered:
            return self.rng.choice(ordered)
        idx = ordered.index(current)
        choices = [current]
        if idx > 0:
            choices.append(ordered[idx - 1])
        if idx < len(ordered) - 1:
            choices.append(ordered[idx + 1])
        return self.rng.choice(choices)

    def _prefer_stabilizing_neutralization(self, current: str, choices: list[str]) -> str:
        if "SUBINDUSTRY" in choices and self.rng.random() < 0.65:
            return "SUBINDUSTRY"
        if "INDUSTRY" in choices and self.rng.random() < 0.20:
            return "INDUSTRY"
        return self.rng.choice(choices)

    def _tighter_truncation(self, current: float, truncs: list[float]) -> float:
        ordered = sorted(float(x) for x in truncs)
        if current not in ordered:
            return ordered[0]
        idx = ordered.index(current)
        choices = [current]
        if idx > 0:
            choices.append(ordered[idx - 1])
        return self.rng.choice(choices)

    # ============================
    # REFINEMENT VARIANTS
    # ============================

    def _apply_refinement_variants(
        self,
        *,
        expr: str,
        family: str,
        template_id: str,
        params: dict[str, Any],
        mode: str,
    ) -> str:
        candidates = [expr]
        n = params.get("n", 10)
        m = params.get("m", 10)

        if family == "mean_reversion":
            if mode == "fitness":
                bigger_n = self._push_param_wider(n)
                candidates.extend([
                    f"ts_mean(rank(rank(-(returns - ts_mean(returns, {bigger_n})))), 5)",
                    f"ts_mean(rank(rank(ts_mean(close, {bigger_n}) - close)), 5)",
                    f"rank(ts_mean(rank(rank(-(close / ts_mean(close, {n}) - 1))), 3))",
                ])
            elif mode == "turnover":
                bigger_n = self._push_param_wider(n)
                candidates.extend([
                    f"ts_mean(rank(rank(-(returns - ts_mean(returns, {bigger_n})))), 10)",
                    f"ts_mean(rank(rank(-(close / ts_mean(close, {bigger_n}) - 1))), 5)",
                ])
            elif mode == "sharpe":
                if self.rng.random() < getattr(config, "LOW_SHARPE_EXTRA_SIGNAL_PROB", 0.50):
                    candidates.extend([
                        f"ts_mean(rank(rank(-ts_delta(close, {n}))), 3)",
                        f"ts_mean(rank(rank(ts_mean(close, {n}) - close)), 3)",
                        f"ts_mean(rank(rank(-(returns - ts_mean(returns, {n})))), 3)",
                    ])
                else:
                    candidates.extend([
                        f"rank(-ts_delta(close, {n}))",
                        f"rank(ts_mean(close, {n}) - close)",
                        f"rank(-(returns - ts_mean(returns, {n})))",
                    ])

        elif family == "conditional":
            cond_volume = f"volume > ts_mean(volume, {n})"
            cond_tight = f"volume > ts_mean(volume, {n}) * 1.1"
            cond_abs = f"abs(returns) > ts_std_dev(returns, {n})"
            base_sig = "rank(-returns)"
            if mode == "fitness":
                candidates.extend([
                    f"trade_when({cond_tight}, {base_sig}, -1)",
                    f"ts_mean(rank(trade_when({cond_tight}, {base_sig}, -1)), 5)",
                    f"trade_when({cond_abs}, {base_sig}, -1)",
                ])
            elif mode == "turnover":
                bigger_n = self._push_param_wider(n)
                cond_wider = f"volume > ts_mean(volume, {bigger_n}) * 1.1"
                candidates.extend([
                    f"trade_when({cond_wider}, {base_sig}, -1)",
                    f"ts_mean(rank(trade_when({cond_wider}, {base_sig}, -1)), 10)",
                ])
            elif mode == "sharpe":
                candidates.extend([
                    f"ts_mean(rank(trade_when({cond_volume}, {base_sig}, -1)), 3)",
                    f"trade_when({cond_volume}, rank(-ts_delta(close, {n})), -1)",
                    f"trade_when({cond_abs}, {base_sig}, -1)",
                ])

        elif family == "volume_flow":
            if mode == "fitness":
                candidates.extend([
                    f"ts_mean(rank(rank((volume / ts_mean(volume, {n})) * -returns)), 10)",
                    f"rank((volume / ts_mean(volume, {n})) * -returns)",
                    f"ts_mean(rank(rank((volume / ts_mean(volume, {self._push_param_wider(n)})) * -returns)), 10)",
                ])
            elif mode == "turnover":
                wider_n = self._push_param_wider(n)
                candidates.extend([
                    f"ts_mean(rank(rank((volume / ts_mean(volume, {wider_n})) * -returns)), 10)",
                    f"trade_when(abs(returns) > ts_std_dev(returns, {wider_n}), rank((volume / ts_mean(volume, {wider_n})) * -returns), -1)",
                ])
            elif mode == "sharpe":
                candidates.extend([
                    f"ts_mean(rank(rank((volume / ts_mean(volume, {n})) * -returns)), 3)",
                    f"rank((volume / ts_mean(volume, {n})) * -returns)",
                ])

        elif family == "vol_adjusted":
            if mode == "fitness":
                wider_n = self._push_param_wider(n)
                wider_m = self._push_param_wider(m, self._grid("m"))
                candidates.extend([
                    f"ts_mean(rank(rank((ts_mean(close, {wider_n}) - close) / ts_std_dev(returns, {wider_m}))), 5)",
                    f"rank((ts_mean(close, {wider_n}) - close) / ts_std_dev(returns, {wider_m}))",
                ])
            elif mode == "turnover":
                wider_n = self._push_param_wider(n)
                wider_m = self._push_param_wider(m, self._grid("m"))
                candidates.extend([
                    f"ts_mean(rank(rank((ts_mean(close, {wider_n}) - close) / ts_std_dev(returns, {wider_m}))), 10)",
                ])
            elif mode == "sharpe":
                candidates.extend([
                    f"ts_mean(rank(rank((ts_mean(close, {n}) - close) / ts_std_dev(returns, {m}))), 3)",
                    f"rank(ts_delta(close, {n}) / ts_std_dev(returns, {m}))",
                ])

        elif family == "fundamental":
            field = params.get("field", "sales")
            candidates.extend([
                f"rank({field})",
                f"rank(ts_delta({field}, {n}))",
                f"rank(({field} - ts_mean({field}, {n})))",
            ])

        return self.rng.choice(candidates)

    # ============================
    # RENDER / FIELDS / HELPERS
    # ============================

    def _render(self, template: str, params: dict[str, Any]):
        expr = template.format(**params)
        fields = []

        for key in ["field"]:
            if key in params:
                fields.append(params[key])

        for f in ["close", "returns", "volume", "cap", "assets", "sales", "income", "cash"]:
            if f in expr and f not in fields:
                fields.append(f)

        return expr, fields

    def _extract_fields(self, expr: str, params: dict[str, Any], fallback_fields: list[str]):
        _, fields = self._render(expr, params) if "{" in expr else (expr, [])
        if fields:
            return fields
        out = list(fallback_fields)
        for f in ["close", "returns", "volume", "cap", "assets", "sales", "income", "cash"]:
            if f in expr and f not in out:
                out.append(f)
        if "field" in params and params["field"] not in out:
            out.append(params["field"])
        return out
