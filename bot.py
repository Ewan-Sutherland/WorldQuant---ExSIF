
from __future__ import annotations

from datetime import timedelta

import config
from brain_client import BrainAPIError, BrainClient
from evaluator import evaluate_submission, parse_metrics
from generator import AlphaGenerator
from models import Run, new_id, utc_now
from scheduler import Scheduler
from similarity import SimilarityEngine, SubmissionPortfolioSelector
from storage import Storage


class AlphaBot:
    """
    Phase-2 bot:
    - keeps Phase 1 / 1.5 orchestration
    - keeps refinement / pruning / diversity
    - adds adaptive family weighting
    - adds adaptive template weighting
    - adds structural similarity gating
    - adds bucket / cluster pressure controls
    - adds portfolio-aware submission selection
    - adds reason-aware refinement
    - adds near-miss reporting
    """

    def __init__(
        self,
        storage: Storage,
        client: BrainClient,
        generator: AlphaGenerator,
        scheduler: Scheduler,
    ):
        self.storage = storage
        self.client = client
        self.generator = generator
        self.scheduler = scheduler

        self.completed_runs = 0
        self.refinement_attempts_by_base: dict[str, int] = {}
        self.similarity = SimilarityEngine()
        self.portfolio_selector = SubmissionPortfolioSelector(self.similarity)

    # =========================================================
    # Main loop
    # =========================================================

    def tick(self) -> None:
        self.client.ensure_session()
        self._poll_running()
        self._fill_capacity()

    # =========================================================
    # Polling
    # =========================================================

    def _poll_running(self) -> None:
        for sim_id, run_id in list(self.scheduler.active_items()):
            try:
                result = self.client.poll_simulation(sim_id)
            except BrainAPIError as exc:
                print(f"[POLL_ERROR] sim_id={sim_id} run_id={run_id} error={exc}")
                continue
            except Exception as exc:
                print(f"[POLL_UNEXPECTED] sim_id={sim_id} run_id={run_id} error={exc}")
                continue

            status = result.get("status", "running")

            if status in {"submitted", "running"}:
                if status == "running":
                    self.storage.update_run(run_id, status="running")
                continue

            self.scheduler.remove(sim_id)

            if status == "completed":
                self._handle_completed(run_id, result)

            elif status == "failed":
                error_message = result.get("error_message", "Simulation failed")
                self.storage.update_run(
                    run_id,
                    status="failed",
                    completed_at=utc_now(),
                    error_message=error_message,
                    raw_result=result,
                )
                print(f"[FAILED] run_id={run_id} sim_id={sim_id} error={error_message}")

            elif status == "timed_out":
                self.storage.update_run(
                    run_id,
                    status="timed_out",
                    completed_at=utc_now(),
                    error_message=result.get("error_message", "Timed out"),
                    raw_result=result,
                )
                print(f"[TIMED_OUT] run_id={run_id} sim_id={sim_id}")

            else:
                self.storage.update_run(
                    run_id,
                    status=status,
                    completed_at=utc_now(),
                    raw_result=result,
                )
                print(f"[UNKNOWN_TERMINAL_STATUS] run_id={run_id} sim_id={sim_id} status={status}")

    # =========================================================
    # Completion / refinement / submission
    # =========================================================

    def _handle_completed(self, run_id: str, result: dict) -> None:
        alpha_id = (
            result.get("alpha_id")
            or result.get("raw", {}).get("alpha_id")
            or result.get("raw", {}).get("id")
        )

        self.storage.update_run(
            run_id,
            alpha_id=alpha_id,
            status="completed",
            completed_at=utc_now(),
            raw_result=result,
        )

        run_row = self.storage.get_run_by_id(run_id)
        if run_row is None:
            print(f"[WARN] completed run not found in DB: run_id={run_id}")
            return

        candidate_id = run_row["candidate_id"]

        metrics = parse_metrics(run_id, result)
        self.storage.insert_metrics(metrics)

        decision = evaluate_submission(candidate_id, metrics)
        self._maybe_queue_refinement(candidate_id, run_id, metrics)

        self.completed_runs += 1

        sharpe_str = "None" if metrics.sharpe is None else f"{metrics.sharpe:.3f}"
        fitness_str = "None" if metrics.fitness is None else f"{metrics.fitness:.3f}"
        turnover_str = "None" if metrics.turnover is None else f"{metrics.turnover:.3f}"

        print(
            f"[COMPLETED] run_id={run_id} "
            f"sharpe={sharpe_str} fitness={fitness_str} turnover={turnover_str} "
            f"eligible={decision.should_submit} reason={decision.reason}"
        )

        if (
            decision.should_submit
            and self._portfolio_allows_submission(candidate_id, run_id, metrics)
            and config.AUTO_SUBMIT
        ):
            self._attempt_submission(candidate_id, run_id, result)

        if self.completed_runs % config.REPORT_EVERY_N_COMPLETIONS == 0:
            self._print_progress_report()

    def _maybe_queue_refinement(self, candidate_id: str, run_id: str, metrics) -> None:
        sharpe = metrics.sharpe
        fitness = metrics.fitness
        turnover = metrics.turnover

        if sharpe is None or fitness is None:
            return

        min_refinement_sharpe = getattr(config, "MIN_REFINEMENT_SHARPE", 1.20)
        if sharpe < min_refinement_sharpe:
            return

        if sharpe >= config.NEAR_PASSER_MIN_SHARPE and fitness >= config.NEAR_PASSER_MIN_FITNESS:
            priority = float(sharpe) + float(fitness)

            fail_reason = metrics.fail_reason or "near_passer"
            if "LOW_FITNESS" in fail_reason:
                priority += getattr(config, "LOW_FITNESS_REFINEMENT_PRIORITY_BONUS", 0.0)
            elif "HIGH_TURNOVER" in fail_reason:
                priority += getattr(config, "HIGH_TURNOVER_REFINEMENT_PRIORITY_BONUS", 0.0)

            if turnover is not None:
                priority -= max(0.0, turnover - config.NEAR_PASSER_MAX_TURNOVER)

            self.storage.add_refinement_candidate(
                candidate_id=candidate_id,
                run_id=run_id,
                priority=priority,
                reason=fail_reason,
                created_at=utc_now(),
            )
            print(
                f"[QUEUED_REFINEMENT] run_id={run_id} candidate_id={candidate_id} "
                f"priority={priority:.3f} reason={fail_reason}"
            )

    def _attempt_submission(self, candidate_id: str, run_id: str, result: dict) -> None:
        alpha_id = (
            result.get("alpha_id")
            or result.get("raw", {}).get("alpha_id")
            or result.get("raw", {}).get("id")
        )

        if not alpha_id:
            print(f"[SUBMIT_SKIP] run_id={run_id} reason=no_alpha_id_found")
            return

        try:
            submission_response = self.client.submit_alpha(alpha_id)
            self.storage.insert_submission(
                submission_id=new_id("sub"),
                candidate_id=candidate_id,
                run_id=run_id,
                submitted_at=utc_now(),
                submission_status="submitted",
                message=str(submission_response),
            )
            print(f"[SUBMITTED] run_id={run_id} alpha_id={alpha_id}")
        except Exception as exc:
            self.storage.insert_submission(
                submission_id=new_id("sub"),
                candidate_id=candidate_id,
                run_id=run_id,
                submitted_at=utc_now(),
                submission_status="failed",
                message=str(exc),
            )
            print(f"[SUBMIT_FAILED] run_id={run_id} alpha_id={alpha_id} error={exc}")

    # =========================================================
    # Stats / scoring maps
    # =========================================================

    def _template_stats_map(self) -> dict[str, dict]:
        rows = self.storage.get_recent_template_stats(limit=config.TEMPLATE_SCORE_LOOKBACK_RUNS)
        out: dict[str, dict] = {}
        for row in rows:
            out[row["template_id"]] = {
                "family": row["family"],
                "n_runs": row["n_runs"] or 0,
                "avg_sharpe": row["avg_sharpe"],
                "avg_fitness": row["avg_fitness"],
                "avg_turnover": row["avg_turnover"],
            }
        return out

    def _family_stats_map(self) -> dict[str, dict]:
        rows = self.storage.get_recent_family_stats(limit=config.TEMPLATE_SCORE_LOOKBACK_RUNS)
        out: dict[str, dict] = {}
        for row in rows:
            out[row["family"]] = {
                "n_runs": row["n_runs"] or 0,
                "avg_sharpe": row["avg_sharpe"],
                "avg_fitness": row["avg_fitness"],
                "avg_turnover": row["avg_turnover"],
                "submit_rate": row["submit_rate"] if "submit_rate" in row.keys() else None,
            }
        return out

    def _score_from_stats(
        self,
        avg_sharpe,
        avg_fitness,
        avg_turnover,
        n_runs: int,
    ) -> float:
        if n_runs <= 0:
            return 1.0

        if avg_sharpe is None or avg_fitness is None:
            return 1.0

        score = 1.0
        score += 0.55 * max(-1.5, min(2.5, float(avg_sharpe)))
        score += 0.35 * max(-1.5, min(2.0, float(avg_fitness)))

        if avg_turnover is not None:
            turnover = float(avg_turnover)
            if turnover > 0.75:
                score -= 0.45
            elif turnover > 0.55:
                score -= 0.20
            elif turnover < 0.08:
                score -= 0.05

        if n_runs < 6:
            score *= 0.90

        return max(0.15, min(3.00, score))

    def _family_bias_map(self) -> dict[str, float]:
        stats = self._family_stats_map()
        bias: dict[str, float] = {}

        for family in getattr(config, "DEFAULT_FAMILY_ORDER", []):
            if family not in stats:
                bias[family] = 1.0

        for family, row in stats.items():
            score = self._score_from_stats(
                avg_sharpe=row["avg_sharpe"],
                avg_fitness=row["avg_fitness"],
                avg_turnover=row["avg_turnover"],
                n_runs=row["n_runs"],
            )

            if family == "momentum":
                score *= 0.08
            elif family == "fundamental":
                score *= 0.25
            elif family == "vol_adjusted" and row["avg_sharpe"] is not None and row["avg_sharpe"] > 0.90:
                score *= 1.10

            bias[family] = max(0.02, min(3.50, score))

        return bias

    def _template_bias_map(self) -> dict[str, float]:
        stats = self._template_stats_map()
        bias: dict[str, float] = {}

        boosts = getattr(config, "PREFERRED_TEMPLATE_BOOSTS", {})
        penalties = getattr(config, "TEMPLATE_WEIGHT_PENALTIES", {})

        for template_id, row in stats.items():
            score = self._score_from_stats(
                avg_sharpe=row["avg_sharpe"],
                avg_fitness=row["avg_fitness"],
                avg_turnover=row["avg_turnover"],
                n_runs=row["n_runs"],
            )

            score *= boosts.get(template_id, 1.0)
            score *= penalties.get(template_id, 1.0)

            if row["n_runs"] >= 8 and row["avg_sharpe"] is not None and row["avg_fitness"] is not None:
                if row["avg_sharpe"] < 0.55 and row["avg_fitness"] < 0.35:
                    score *= 0.55

            bias[template_id] = max(0.02, min(4.00, score))

        return bias

    # =========================================================
    # Quality / pruning / diversity
    # =========================================================

    def _template_quality_class(self, template_id: str) -> str:
        stats = self._template_stats_map().get(template_id)
        if stats is None:
            return "unknown"

        n_runs = stats["n_runs"] or 0
        avg_sharpe = stats["avg_sharpe"]
        avg_fitness = stats["avg_fitness"]

        if n_runs < config.MIN_TEMPLATE_OBS_FOR_PRUNE:
            return "young"

        if (
            avg_sharpe is not None
            and avg_fitness is not None
            and avg_sharpe <= config.HARD_PRUNE_MAX_AVG_SHARPE
            and avg_fitness <= config.HARD_PRUNE_MAX_AVG_FITNESS
        ):
            return "hard_prune"

        if (
            avg_sharpe is not None
            and avg_fitness is not None
            and avg_sharpe <= config.SOFT_PRUNE_MAX_AVG_SHARPE
            and avg_fitness <= config.SOFT_PRUNE_MAX_AVG_FITNESS
        ):
            return "soft_prune"

        return "healthy"

    def _candidate_allowed_by_template_quality(self, candidate, is_refinement: bool) -> bool:
        quality = self._template_quality_class(candidate.template_id)

        if quality in {"unknown", "young", "healthy"}:
            return True

        if quality == "hard_prune":
            return False

        if quality == "soft_prune":
            if is_refinement:
                return self.generator.rng.random() < config.SOFT_PRUNE_REFINEMENT_PROBABILITY
            return self.generator.rng.random() < config.TEMPLATE_EXPLORATION_PROBABILITY

        return True

    def _candidate_allowed_by_diversity(self, candidate, is_refinement: bool) -> bool:
        stats = self.storage.get_recent_template_stats(limit=config.DIVERSITY_LOOKBACK_RUNS)
        template_stats = None
        for row in stats:
            if row["template_id"] == candidate.template_id:
                template_stats = row
                break

        if template_stats is None:
            return True

        n_runs = template_stats["n_runs"] or 0
        avg_sharpe = template_stats["avg_sharpe"]
        avg_fitness = template_stats["avg_fitness"]

        if n_runs < config.RELAXED_TEMPLATE_COUNT:
            return True

        strong_template = (
            avg_sharpe is not None
            and avg_fitness is not None
            and avg_sharpe >= config.RELAXED_TEMPLATE_MIN_AVG_SHARPE
            and avg_fitness >= config.RELAXED_TEMPLATE_MIN_AVG_FITNESS
        )

        if n_runs >= config.MAX_RECENT_TEMPLATE_COUNT:
            if strong_template and is_refinement:
                return self.generator.rng.random() < 0.30
            return self.generator.rng.random() < config.DIVERSITY_EXPLORATION_PROBABILITY

        if strong_template and is_refinement:
            return True

        penalty_prob = max(0.15, 1.0 - 0.08 * (n_runs - config.RELAXED_TEMPLATE_COUNT))
        return self.generator.rng.random() < penalty_prob

    def _similarity_threshold_for_candidate(self, candidate, is_refinement: bool) -> float:
        base_threshold = (
            config.MAX_REFINEMENT_CANDIDATE_SIMILARITY
            if is_refinement
            else config.MAX_FRESH_CANDIDATE_SIMILARITY
        )

        family_map = (
            getattr(config, "FAMILY_REFINEMENT_SIMILARITY_THRESHOLDS", {})
            if is_refinement
            else getattr(config, "FAMILY_FRESH_SIMILARITY_THRESHOLDS", {})
        )
        threshold = family_map.get(candidate.family, base_threshold)

        quality = self._template_quality_class(candidate.template_id)
        if quality in {"young", "unknown"}:
            threshold += 0.005
        elif quality == "healthy" and is_refinement:
            threshold += 0.005

        return min(0.995, threshold)

    def _candidate_allowed_by_similarity(self, candidate, is_refinement: bool) -> bool:
        reference_rows = self.storage.get_similarity_reference_candidates(
            limit=config.SIMILARITY_REFERENCE_LOOKBACK,
            min_sharpe=config.SIMILARITY_MIN_REF_SHARPE,
            min_fitness=config.SIMILARITY_MIN_REF_FITNESS,
        )

        if len(reference_rows) < getattr(config, "SIMILARITY_MIN_REFERENCE_COUNT", 0):
            return True

        result = self.similarity.max_similarity_against_rows(candidate, reference_rows)
        threshold = self._similarity_threshold_for_candidate(candidate, is_refinement=is_refinement)

        if result.score < threshold:
            return True

        if result.reason == "exact_duplicate":
            print(
                f"[SIMILARITY_SKIP] template={candidate.template_id} family={candidate.family} "
                f"sim={result.score:.3f} threshold={threshold:.3f} "
                f"reason={result.reason} ref_candidate_id={result.ref_candidate_id} "
                f"ref_template={result.ref_template_id} ref_family={result.ref_family} "
                f"expr={candidate.expression}"
            )
            return False

        soft_margin = getattr(config, "SIMILARITY_SOFT_MARGIN", 0.0)
        overshoot = result.score - threshold

        if overshoot <= soft_margin:
            allow_prob = (
                getattr(config, "SIMILARITY_SOFT_ALLOW_PROB_REFINEMENT", 0.0)
                if is_refinement
                else getattr(config, "SIMILARITY_SOFT_ALLOW_PROB_FRESH", 0.0)
            )
            if result.reason == "same_bucket":
                allow_prob = max(0.0, allow_prob - getattr(config, "SIMILARITY_SAME_BUCKET_PENALTY", 0.0))

            if self.generator.rng.random() < allow_prob:
                print(
                    f"[SIMILARITY_NEARPASS] template={candidate.template_id} family={candidate.family} "
                    f"sim={result.score:.3f} threshold={threshold:.3f} "
                    f"reason={result.reason} ref_candidate_id={result.ref_candidate_id} "
                    f"ref_template={result.ref_template_id} ref_family={result.ref_family} "
                    f"expr={candidate.expression}"
                )
                return True

        print(
            f"[SIMILARITY_SKIP] template={candidate.template_id} family={candidate.family} "
            f"sim={result.score:.3f} threshold={threshold:.3f} "
            f"reason={result.reason} ref_candidate_id={result.ref_candidate_id} "
            f"ref_template={result.ref_template_id} ref_family={result.ref_family} "
            f"expr={candidate.expression}"
        )
        return False

    def _bucket_limits_for_family(self, family: str) -> tuple[int, int]:
        max_bucket = getattr(config, "FAMILY_MAX_BUCKET_OCCUPANCY", {}).get(
            family,
            config.MAX_BUCKET_OCCUPANCY,
        )
        max_strong = getattr(config, "FAMILY_MAX_STRONG_BUCKET_OCCUPANCY", {}).get(
            family,
            config.MAX_STRONG_BUCKET_OCCUPANCY,
        )
        return max_bucket, max_strong

    def _candidate_allowed_by_bucket_pressure(self, candidate, is_refinement: bool) -> bool:
        candidate_sig = self.similarity.signature_from_candidate(candidate)
        rows = self.storage.get_recent_bucket_reference_candidates(
            limit=getattr(config, "BUCKET_REFERENCE_LOOKBACK", config.SIMILARITY_REFERENCE_LOOKBACK)
        )

        bucket_count = 0
        strong_bucket_count = 0

        for row in rows:
            row_sig = self.similarity.signature_from_row(row)
            if row_sig.bucket_key != candidate_sig.bucket_key:
                continue

            bucket_count += 1

            sharpe = row["sharpe"]
            fitness = row["fitness"]
            if (
                sharpe is not None
                and fitness is not None
                and float(sharpe) >= config.STRONG_BUCKET_MIN_SHARPE
                and float(fitness) >= config.STRONG_BUCKET_MIN_FITNESS
            ):
                strong_bucket_count += 1

        max_bucket, max_strong_bucket = self._bucket_limits_for_family(candidate.family)

        if strong_bucket_count >= max_strong_bucket:
            allow_prob = (
                getattr(config, "STRONG_BUCKET_SOFT_ALLOW_PROB_REFINEMENT", 0.0)
                if is_refinement
                else getattr(config, "STRONG_BUCKET_SOFT_ALLOW_PROB_FRESH", 0.0)
            )
            if self.generator.rng.random() < allow_prob:
                print(
                    f"[CLUSTER_NEARPASS] template={candidate.template_id} family={candidate.family} "
                    f"bucket={candidate_sig.bucket_key} reason=strong_bucket_soft_allow "
                    f"strong_bucket_count={strong_bucket_count} limit={max_strong_bucket} "
                    f"expr={candidate.expression}"
                )
                return True

            print(
                f"[CLUSTER_SKIP] template={candidate.template_id} family={candidate.family} "
                f"bucket={candidate_sig.bucket_key} reason=strong_bucket_saturated "
                f"strong_bucket_count={strong_bucket_count} limit={max_strong_bucket} "
                f"expr={candidate.expression}"
            )
            return False

        if bucket_count >= max_bucket:
            allow_prob = (
                getattr(config, "BUCKET_SOFT_ALLOW_PROB_REFINEMENT", 0.0)
                if is_refinement
                else getattr(config, "BUCKET_SOFT_ALLOW_PROB_FRESH", 0.0)
            )

            if self.generator.rng.random() < allow_prob:
                print(
                    f"[CLUSTER_NEARPASS] template={candidate.template_id} family={candidate.family} "
                    f"bucket={candidate_sig.bucket_key} reason=bucket_soft_allow "
                    f"bucket_count={bucket_count} limit={max_bucket} expr={candidate.expression}"
                )
                return True

            print(
                f"[CLUSTER_SKIP] template={candidate.template_id} family={candidate.family} "
                f"bucket={candidate_sig.bucket_key} reason=bucket_saturated "
                f"bucket_count={bucket_count} limit={max_bucket} expr={candidate.expression}"
            )
            return False

        return True

    # =========================================================
    # Candidate selection
    # =========================================================

    def _should_abandon_refinement_base(self, base_candidate_id: str) -> bool:
        attempts = self.refinement_attempts_by_base.get(base_candidate_id, 0)
        return attempts >= config.MAX_REFINEMENT_ATTEMPTS_PER_BASE

    def _fresh_candidate(self):
        family_bias = self._family_bias_map()
        template_bias = self._template_bias_map()

        for _ in range(8):
            candidate = self.generator.generate_candidate(
                family_bias=family_bias,
                template_bias=template_bias,
            )

            if self.storage.candidate_exists(candidate.expression_hash):
                continue

            if not self._candidate_allowed_by_template_quality(candidate, is_refinement=False):
                print(
                    f"[TEMPLATE_PRUNE_SKIP] template={candidate.template_id} family={candidate.family} "
                    f"expr={candidate.expression}"
                )
                continue

            if not self._candidate_allowed_by_diversity(candidate, is_refinement=False):
                print(
                    f"[DIVERSITY_SKIP] template={candidate.template_id} family={candidate.family} "
                    f"expr={candidate.expression}"
                )
                continue

            if not self._candidate_allowed_by_similarity(candidate, is_refinement=False):
                continue

            if not self._candidate_allowed_by_bucket_pressure(candidate, is_refinement=False):
                continue

            return candidate

        return None

    def _load_metrics_row(self, run_id: str) -> dict:
        with self.storage.connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, sharpe, fitness, turnover, fail_reason
                FROM metrics
                WHERE run_id = ?
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            return dict(row) if row is not None else {}

    def _get_candidate_with_refinement_priority(self):
        for _ in range(6):
            refinement_row = None

            if self.generator.rng.random() < config.REFINEMENT_PROBABILITY:
                refinement_row = self.storage.get_next_refinement_candidate()

            if refinement_row is not None:
                base_candidate_id = refinement_row["candidate_id"]

                if self._should_abandon_refinement_base(base_candidate_id):
                    self.storage.mark_refinement_consumed(base_candidate_id)
                    self.refinement_attempts_by_base.pop(base_candidate_id, None)
                    print(
                        f"[REFINEMENT_EXHAUSTED] base_candidate_id={base_candidate_id} "
                        f"template={refinement_row['template_id']} family={refinement_row['family']}"
                    )
                    continue

                metrics_hint = self._load_metrics_row(refinement_row["run_id"])
                candidate = self.generator.mutate_candidate(refinement_row, metrics_hint=metrics_hint)
                self.refinement_attempts_by_base[base_candidate_id] = (
                    self.refinement_attempts_by_base.get(base_candidate_id, 0) + 1
                )

                print(
                    f"[REFINING] base_candidate_id={base_candidate_id} "
                    f"template={refinement_row['template_id']} family={refinement_row['family']} "
                    f"new_template={candidate.template_id} new_family={candidate.family} "
                    f"expr={candidate.expression}"
                )

                if self.storage.candidate_exists(candidate.expression_hash):
                    continue

                if not self._candidate_allowed_by_template_quality(candidate, is_refinement=True):
                    print(
                        f"[TEMPLATE_PRUNE_SKIP] template={candidate.template_id} family={candidate.family} "
                        f"expr={candidate.expression}"
                    )
                    continue

                if not self._candidate_allowed_by_diversity(candidate, is_refinement=True):
                    print(
                        f"[DIVERSITY_SKIP] template={candidate.template_id} family={candidate.family} "
                        f"expr={candidate.expression}"
                    )
                    continue

                if not self._candidate_allowed_by_similarity(candidate, is_refinement=True):
                    continue

                if not self._candidate_allowed_by_bucket_pressure(candidate, is_refinement=True):
                    continue

                self.storage.mark_refinement_consumed(base_candidate_id)
                self.refinement_attempts_by_base.pop(base_candidate_id, None)
                return candidate

            fresh = self._fresh_candidate()
            if fresh is not None:
                return fresh

        return None

    # =========================================================
    # Submission loop
    # =========================================================

    def _fill_capacity(self) -> None:
        attempts = 0
        max_attempts = 12

        while self.scheduler.has_capacity() and attempts < max_attempts:
            attempts += 1

            candidate = self._get_candidate_with_refinement_priority()
            if candidate is None:
                continue

            if self.storage.candidate_exists(candidate.expression_hash):
                continue

            try:
                self.storage.insert_candidate(candidate)
            except Exception as exc:
                print(f"[CANDIDATE_INSERT_ERROR] candidate_id={candidate.candidate_id} error={exc}")
                continue

            run = Run.create(candidate_id=candidate.candidate_id, status="pending")
            self.storage.insert_run(run)

            try:
                sim_id = self.client.submit_simulation(
                    candidate.expression,
                    candidate.settings.to_dict(),
                )

                now = utc_now()
                self.storage.update_run(
                    run.run_id,
                    sim_id=sim_id,
                    status="submitted",
                    submitted_at=now,
                )
                self.scheduler.add(sim_id, run.run_id)

                print(
                    f"[SUBMITTED_SIM] run_id={run.run_id} sim_id={sim_id} "
                    f"template={candidate.template_id} family={candidate.family} "
                    f"expr={candidate.expression}"
                )

            except BrainAPIError as exc:
                self.storage.update_run(
                    run.run_id,
                    status="failed",
                    completed_at=utc_now(),
                    error_message=str(exc),
                )
                print(f"[SIM_SUBMIT_ERROR] run_id={run.run_id} error={exc}")

            except Exception as exc:
                self.storage.update_run(
                    run.run_id,
                    status="failed",
                    completed_at=utc_now(),
                    error_message=str(exc),
                )
                print(f"[SIM_SUBMIT_UNEXPECTED] run_id={run.run_id} error={exc}")

    def _portfolio_allows_submission(self, candidate_id: str, run_id: str, metrics) -> bool:
        if metrics.submit_eligible is not True:
            return False

        candidate_rows = self.storage.get_submission_eligible_candidates(
            limit=config.SUBMISSION_PORTFOLIO_LOOKBACK
        )
        submitted_rows = self.storage.get_submitted_candidate_rows(
            limit=config.SUBMISSION_PORTFOLIO_LOOKBACK
        )

        target_row = None
        peer_rows = []

        for row in candidate_rows:
            if row["run_id"] == run_id:
                target_row = row
            else:
                peer_rows.append(row)

        if target_row is None:
            return True

        selected = self.portfolio_selector.select_rows(
            candidate_rows=[target_row] + peer_rows,
            already_submitted_rows=submitted_rows,
            max_selected=config.SUBMISSION_MAX_SELECTED_PER_CYCLE,
            max_pairwise_similarity=config.SUBMISSION_MAX_PAIRWISE_SIMILARITY,
        )

        allowed = any(row["run_id"] == run_id for row in selected)

        if not allowed:
            print(
                f"[PORTFOLIO_HOLD] run_id={run_id} candidate_id={candidate_id} "
                f"reason=portfolio_similarity_or_score"
            )

        return allowed

    # =========================================================
    # Recovery / timeout
    # =========================================================

    def recover_running_from_storage(self) -> None:
        rows = self.storage.get_running_runs()
        recovered = 0

        for row in rows:
            sim_id = row["sim_id"]
            run_id = row["run_id"]

            if sim_id and not self.scheduler.is_running(sim_id):
                self.scheduler.add(sim_id, run_id)
                recovered += 1

        if recovered:
            print(f"[RECOVERED] restored {recovered} running simulations from storage")

    def mark_stale_runs_timed_out(self) -> None:
        cutoff = utc_now() - timedelta(minutes=config.SIM_TIMEOUT_MINUTES)
        rows = self.storage.get_running_runs()

        stale_count = 0
        for row in rows:
            submitted_at = row["submitted_at"]
            if not submitted_at:
                continue

            try:
                submitted_dt = self.storage.parse_dt(submitted_at)
            except Exception:
                continue

            if submitted_dt < cutoff:
                run_id = row["run_id"]
                sim_id = row["sim_id"]
                self.storage.update_run(
                    run_id,
                    status="timed_out",
                    completed_at=utc_now(),
                    error_message="Marked stale by timeout sweep.",
                )
                if sim_id:
                    self.scheduler.remove(sim_id)
                stale_count += 1

        if stale_count:
            print(f"[STALE_SWEEP] marked {stale_count} runs as timed_out")

    # =========================================================
    # Reporting
    # =========================================================

    def _recent_failure_counts(self):
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    COALESCE(m.fail_reason, 'UNKNOWN') AS fail_reason,
                    COUNT(*) AS n_runs
                FROM metrics m
                JOIN runs r ON m.run_id = r.run_id
                WHERE r.run_id IN (
                    SELECT run_id
                    FROM runs
                    WHERE status = 'completed'
                    ORDER BY completed_at DESC
                    LIMIT ?
                )
                GROUP BY COALESCE(m.fail_reason, 'UNKNOWN')
                ORDER BY n_runs DESC
                """,
                (getattr(config, "REPORT_RECENT_FAILURE_LOOKBACK", 180),),
            ).fetchall()
            return rows

    def _recent_near_misses(self):
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    r.run_id,
                    c.template_id,
                    c.family,
                    c.expression,
                    m.sharpe,
                    m.fitness,
                    m.turnover,
                    m.fail_reason
                FROM metrics m
                JOIN runs r ON m.run_id = r.run_id
                JOIN candidates c ON r.candidate_id = c.candidate_id
                WHERE r.status = 'completed'
                  AND COALESCE(m.submit_eligible, 0) = 0
                  AND m.sharpe IS NOT NULL
                  AND m.fitness IS NOT NULL
                  AND (
                        m.sharpe >= ?
                     OR m.fitness >= ?
                  )
                ORDER BY (m.sharpe + m.fitness) DESC, r.completed_at DESC
                LIMIT ?
                """,
                (
                    max(config.MIN_REFINEMENT_SHARPE, config.MIN_SHARPE - 0.10),
                    max(0.70, config.NEAR_PASSER_MIN_FITNESS - 0.08),
                    getattr(config, "NEAR_MISS_REPORT_COUNT", 6),
                ),
            ).fetchall()
            return rows

    def _print_progress_report(self) -> None:
        print("\n[REPORT] recent family stats")
        family_rows = self.storage.get_recent_family_stats(limit=500)

        if not family_rows:
            print("No completed family stats yet.\n")
            return

        def fmt(x):
            return "None" if x is None else f"{x:.3f}"

        for row in family_rows:
            family = row["family"]
            n_runs = row["n_runs"]
            avg_sharpe = row["avg_sharpe"]
            avg_fitness = row["avg_fitness"]
            avg_turnover = row["avg_turnover"]
            submit_rate = row["submit_rate"]

            print(
                f"family={family:<16} "
                f"n={n_runs:<4} "
                f"avg_sharpe={fmt(avg_sharpe):<8} "
                f"avg_fitness={fmt(avg_fitness):<8} "
                f"avg_turnover={fmt(avg_turnover):<8} "
                f"submit_rate={fmt(submit_rate):<8}"
            )

        print("\n[REPORT] recent template stats")
        template_rows = self.storage.get_recent_template_stats(limit=config.TEMPLATE_SCORE_LOOKBACK_RUNS)

        shown = 0
        for row in template_rows:
            template_id = row["template_id"]
            family = row["family"]
            n_runs = row["n_runs"]
            avg_sharpe = row["avg_sharpe"]
            avg_fitness = row["avg_fitness"]
            avg_turnover = row["avg_turnover"]
            quality = self._template_quality_class(template_id)

            print(
                f"template={template_id:<8} "
                f"family={family:<14} "
                f"n={n_runs:<4} "
                f"avg_sharpe={fmt(avg_sharpe):<8} "
                f"avg_fitness={fmt(avg_fitness):<8} "
                f"avg_turnover={fmt(avg_turnover):<8} "
                f"quality={quality}"
            )

            shown += 1
            if shown >= 12:
                break

        failure_rows = self._recent_failure_counts()
        if failure_rows:
            print("\n[REPORT] recent failure reasons")
            for row in failure_rows[:8]:
                print(f"reason={row['fail_reason']:<28} n={row['n_runs']}")

        near_rows = self._recent_near_misses()
        if near_rows:
            print("\n[REPORT] recent near-misses")
            for row in near_rows:
                print(
                    f"template={row['template_id']:<8} family={row['family']:<14} "
                    f"sharpe={fmt(row['sharpe']):<8} fitness={fmt(row['fitness']):<8} "
                    f"turnover={fmt(row['turnover']):<8} fail={row['fail_reason']}"
                )

        print()
