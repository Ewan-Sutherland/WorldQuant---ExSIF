"""
Supabase storage backend for the Alpha Bot.
Drop-in replacement for the SQLite Storage class — same method signatures.

Requires:
    SUPABASE_URL and SUPABASE_ANON_KEY in environment or passed to constructor.
    Tables and RPC functions created via supabase_schema.sql.
"""
from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from contextlib import contextmanager

import requests

from models import Candidate, Run, Metrics

logger = logging.getLogger(__name__)


def dt_to_str(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


class Storage:
    """Supabase-backed storage with the same interface as the SQLite version."""

    def __init__(self, db_path: str | None = None, supabase_url: str | None = None, supabase_key: str | None = None):
        """
        Args:
            db_path: Ignored (kept for backward compatibility with config.DB_PATH).
            supabase_url: Supabase project URL. Falls back to SUPABASE_URL env var.
            supabase_key: Supabase anon/publishable key. Falls back to SUPABASE_ANON_KEY env var.
        """
        self.url = (supabase_url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = supabase_key or os.environ.get("SUPABASE_ANON_KEY", "")
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        self.base = f"{self.url}/rest/v1"
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    # ── HTTP helpers ──────────────────────────────────────────────────

    def _get(self, table: str, params: dict | None = None) -> list[dict]:
        r = requests.get(f"{self.base}/{table}", headers=self.headers, params=params or {})
        if r.status_code not in (200, 206):
            logger.warning(f"GET {table} failed: {r.status_code} {r.text[:300]}")
            return []
        return r.json()

    def _post(self, table: str, data: dict, upsert: bool = False) -> dict | None:
        headers = dict(self.headers)
        if upsert:
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        r = requests.post(f"{self.base}/{table}", headers=headers, json=data)
        if r.status_code not in (200, 201):
            logger.warning(f"POST {table} failed: {r.status_code} {r.text[:300]}")
            return None
        result = r.json()
        return result[0] if isinstance(result, list) and result else result

    def _patch(self, table: str, match: dict, data: dict) -> dict | None:
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = requests.patch(f"{self.base}/{table}", headers=self.headers, params=params, json=data)
        if r.status_code not in (200, 204):
            logger.warning(f"PATCH {table} failed: {r.status_code} {r.text[:300]}")
            return None
        result = r.json() if r.text else None
        return result[0] if isinstance(result, list) and result else result

    def _delete(self, table: str, match: dict) -> bool:
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = requests.delete(f"{self.base}/{table}", headers=self.headers, params=params)
        return r.status_code in (200, 204)

    def _rpc(self, function: str, params: dict | None = None) -> list[dict]:
        r = requests.post(
            f"{self.base}/rpc/{function}",
            headers=self.headers,
            json=params or {},
        )
        if r.status_code != 200:
            logger.warning(f"RPC {function} failed: {r.status_code} {r.text[:300]}")
            return []
        return r.json()

    # ── Compatibility ─────────────────────────────────────────────────

    @contextmanager
    def connect(self):
        """Compatibility shim — yields self so `with storage.connect() as conn` still works."""
        yield self

    def execute(self, sql: str, params: tuple = ()):
        """Compatibility shim for raw SQL. Only used by cleanup scripts."""
        logger.warning(f"Raw SQL not supported in Supabase mode: {sql[:100]}")
        return _EmptyResult()

    def init_db(self):
        """No-op — tables created via supabase_schema.sql."""
        pass

    def parse_dt(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    # ── Candidates ────────────────────────────────────────────────────

    def candidate_exists(self, expression_hash: str) -> bool:
        rows = self._get("candidates", {
            "expression_hash": f"eq.{expression_hash}",
            "select": "candidate_id",
        })
        return len(rows) > 0

    def insert_candidate(self, candidate: Candidate) -> None:
        self._post("candidates", {
            "candidate_id": candidate.candidate_id,
            "expression": candidate.expression,
            "canonical_expression": candidate.canonical_expression,
            "expression_hash": candidate.expression_hash,
            "template_id": candidate.template_id,
            "family": candidate.family,
            "fields_json": candidate.fields,
            "params_json": candidate.params,
            "settings_json": candidate.settings.to_dict(),
            "created_at": dt_to_str(candidate.created_at),
        })

    def get_candidate_by_id(self, candidate_id: str) -> Optional[dict]:
        rows = self._get("candidates", {
            "candidate_id": f"eq.{candidate_id}",
            "select": "*",
        })
        return rows[0] if rows else None

    def get_candidate_by_hash(self, expression_hash: str) -> Optional[dict]:
        rows = self._get("candidates", {
            "expression_hash": f"eq.{expression_hash}",
            "select": "*",
        })
        return rows[0] if rows else None

    # ── Runs ──────────────────────────────────────────────────────────

    def insert_run(self, run: Run) -> None:
        self._post("runs", {
            "run_id": run.run_id,
            "candidate_id": run.candidate_id,
            "sim_id": run.sim_id,
            "alpha_id": run.alpha_id,
            "status": run.status,
            "submitted_at": dt_to_str(run.submitted_at),
            "completed_at": dt_to_str(run.completed_at),
            "error_message": run.error_message,
            "raw_result_json": run.raw_result,
        })

    def update_run(
        self,
        run_id: str,
        status: str | None = None,
        sim_id: str | None = None,
        alpha_id: str | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
        raw_result: dict | None = None,
    ) -> None:
        data = {}
        if status is not None:
            data["status"] = status
        if sim_id is not None:
            data["sim_id"] = sim_id
        if alpha_id is not None:
            data["alpha_id"] = alpha_id
        if completed_at is not None:
            data["completed_at"] = dt_to_str(completed_at)
        if error_message is not None:
            data["error_message"] = error_message
        if raw_result is not None:
            data["raw_result_json"] = raw_result
        if data:
            self._patch("runs", {"run_id": run_id}, data)

    def get_run_by_id(self, run_id: str) -> Optional[dict]:
        rows = self._get("runs", {
            "run_id": f"eq.{run_id}",
            "select": "*",
        })
        return rows[0] if rows else None

    def get_running_runs(self) -> list[dict]:
        return self._get("runs", {
            "status": "eq.running",
            "select": "*",
        })

    # ── Metrics ───────────────────────────────────────────────────────

    def insert_metrics(self, metrics: Metrics) -> None:
        self._post("metrics", {
            "run_id": metrics.run_id,
            "sharpe": metrics.sharpe,
            "fitness": metrics.fitness,
            "turnover": metrics.turnover,
            "returns": metrics.returns,
            "margin": metrics.margin,
            "drawdown": metrics.drawdown,
            "checks_passed": metrics.checks_passed,
            "submit_eligible": metrics.submit_eligible,
            "fail_reason": metrics.fail_reason,
        })

    # ── Submissions ───────────────────────────────────────────────────

    def insert_submission(
        self,
        submission_id: str,
        candidate_id: str,
        run_id: str,
        submitted_at: datetime,
        submission_status: str,
        message: str | None = None,
    ) -> None:
        self._post("submissions", {
            "submission_id": submission_id,
            "candidate_id": candidate_id,
            "run_id": run_id,
            "submitted_at": dt_to_str(submitted_at),
            "submission_status": submission_status,
            "message": message,
        })

    # ── Refinement Queue ──────────────────────────────────────────────

    def add_refinement_candidate(
        self,
        candidate_id: str,
        run_id: str,
        priority: float,
        reason: str,
        created_at: datetime,
        source_stage: str = "unknown",
        base_sharpe: float | None = None,
        base_fitness: float | None = None,
        base_turnover: float | None = None,
    ) -> None:
        self._post("refinement_queue", {
            "candidate_id": candidate_id,
            "run_id": run_id,
            "priority": priority,
            "reason": reason,
            "created_at": dt_to_str(created_at),
            "consumed": False,
            "source_stage": source_stage,
            "base_sharpe": base_sharpe,
            "base_fitness": base_fitness,
            "base_turnover": base_turnover,
        }, upsert=True)

    def get_next_refinement_candidate(self) -> Optional[dict]:
        rows = self._get("refinement_queue", {
            "consumed": "eq.false",
            "select": "*",
            "order": "priority.desc",
            "limit": "1",
        })
        if not rows:
            return None

        row = rows[0]
        cid = row["candidate_id"]

        # Get the full candidate data
        cand = self.get_candidate_by_id(cid)
        if not cand:
            return None

        # Merge refinement queue data with candidate data
        merged = dict(cand)
        merged["reason"] = row.get("reason", "")
        merged["source_stage"] = row.get("source_stage", "unknown")
        merged["base_sharpe"] = row.get("base_sharpe")
        merged["base_fitness"] = row.get("base_fitness")
        merged["base_turnover"] = row.get("base_turnover")
        return merged

    def mark_refinement_consumed(self, candidate_id: str) -> None:
        self._patch("refinement_queue", {"candidate_id": candidate_id}, {"consumed": True})

    # ── Complex Queries (via RPC) ─────────────────────────────────────

    def get_recent_family_stats(self, limit: int = 500) -> list[dict]:
        return self._rpc("get_family_stats", {"run_limit": limit})

    def get_recent_template_stats(self, limit: int = 180) -> list[dict]:
        return self._rpc("get_template_stats", {"run_limit": limit})

    def get_submitted_candidate_rows(self, *, limit: int = 300) -> list[dict]:
        return self._rpc("get_submitted_candidates", {"row_limit": limit})

    def get_submission_eligible_candidates(self, *, limit: int = 50) -> list[dict]:
        return self._rpc("get_eligible_candidates", {"row_limit": limit})

    def get_similarity_reference_candidates(
        self, *, limit: int, min_sharpe: float, min_fitness: float,
    ) -> list[dict]:
        return self._rpc("get_reference_candidates", {
            "row_limit": limit,
            "min_s": min_sharpe,
            "min_f": min_fitness,
        })

    def get_recent_bucket_reference_candidates(self, *, limit: int) -> list[dict]:
        # Reuse reference candidates with low thresholds
        return self.get_similarity_reference_candidates(
            limit=limit, min_sharpe=0.0, min_fitness=0.0,
        )

    # ── Utility / Compatibility ───────────────────────────────────────

    def get_submitted_alphas(self, *, limit: int = 300) -> list[dict]:
        return self.get_submitted_candidate_rows(limit=limit)

    def get_refinement_report(self, limit: int = 250) -> list[dict]:
        return self._get("refinement_queue", {
            "select": "*",
            "order": "priority.desc",
            "limit": str(limit),
        })

    def register_manual_submission(self, expression_hash: str, alpha_id: str | None = None) -> bool:
        cand = self.get_candidate_by_hash(expression_hash)
        if not cand:
            return False

        cid = cand["candidate_id"]

        # Find the best completed run for this candidate
        runs = self._get("runs", {
            "candidate_id": f"eq.{cid}",
            "status": "eq.completed",
            "select": "run_id",
            "order": "completed_at.desc",
            "limit": "1",
        })
        rid = runs[0]["run_id"] if runs else "manual_run"

        from models import new_id, utc_now
        self.insert_submission(
            submission_id=new_id("sub"),
            candidate_id=cid,
            run_id=rid,
            submitted_at=utc_now(),
            submission_status="submitted",
            message="manually_registered",
        )
        return True

    def register_manual_submission_by_candidate_id(self, candidate_id: str) -> bool:
        cand = self.get_candidate_by_id(candidate_id)
        if not cand:
            return False

        runs = self._get("runs", {
            "candidate_id": f"eq.{candidate_id}",
            "status": "eq.completed",
            "select": "run_id",
            "order": "completed_at.desc",
            "limit": "1",
        })
        rid = runs[0]["run_id"] if runs else "manual_run"

        from models import new_id, utc_now
        self.insert_submission(
            submission_id=new_id("sub"),
            candidate_id=candidate_id,
            run_id=rid,
            submitted_at=utc_now(),
            submission_status="submitted",
            message="manually_registered",
        )
        return True


class _EmptyResult:
    """Stub for compatibility with raw SQL execute calls."""
    def fetchall(self):
        return []
    def fetchone(self):
        return None
