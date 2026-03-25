"""
Migrate existing SQLite data to Supabase.

Usage:
    python migrate_to_supabase.py                    # Migrate all data
    python migrate_to_supabase.py --dry-run          # Show what would be migrated
    python migrate_to_supabase.py --submissions-only  # Only migrate submissions
"""
from __future__ import annotations
import argparse
import json
import sqlite3

import config
from storage_supabase import Storage as SupabaseStorage


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite → Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without migrating")
    parser.add_argument("--submissions-only", action="store_true", help="Only migrate submissions")
    args = parser.parse_args()

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(config.DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    # Connect to Supabase
    sb = SupabaseStorage(
        supabase_url=config.SUPABASE_URL,
        supabase_key=config.SUPABASE_ANON_KEY,
    )

    if args.dry_run:
        for table in ["candidates", "runs", "metrics", "submissions", "refinement_queue"]:
            count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")
        sqlite_conn.close()
        return

    if args.submissions_only:
        _migrate_submissions(sqlite_conn, sb)
        sqlite_conn.close()
        return

    # Full migration in dependency order
    _migrate_candidates(sqlite_conn, sb)
    _migrate_runs(sqlite_conn, sb)
    _migrate_metrics(sqlite_conn, sb)
    _migrate_submissions(sqlite_conn, sb)
    _migrate_refinement(sqlite_conn, sb)

    sqlite_conn.close()
    print("\nMigration complete!")


def _migrate_candidates(conn, sb):
    rows = conn.execute("SELECT * FROM candidates").fetchall()
    print(f"Migrating {len(rows)} candidates...")
    ok = 0
    for row in rows:
        result = sb._post("candidates", {
            "candidate_id": row["candidate_id"],
            "expression": row["expression"],
            "canonical_expression": row["canonical_expression"],
            "expression_hash": row["expression_hash"],
            "template_id": row["template_id"],
            "family": row["family"],
            "fields_json": json.loads(row["fields_json"]) if isinstance(row["fields_json"], str) else row["fields_json"],
            "params_json": json.loads(row["params_json"]) if isinstance(row["params_json"], str) else row["params_json"],
            "settings_json": json.loads(row["settings_json"]) if isinstance(row["settings_json"], str) else row["settings_json"],
            "created_at": row["created_at"],
        }, upsert=True)
        if result:
            ok += 1
    print(f"  → {ok}/{len(rows)} candidates migrated")


def _migrate_runs(conn, sb):
    rows = conn.execute("SELECT * FROM runs").fetchall()
    print(f"Migrating {len(rows)} runs...")
    ok = 0
    for row in rows:
        raw = row["raw_result_json"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                raw = None
        result = sb._post("runs", {
            "run_id": row["run_id"],
            "candidate_id": row["candidate_id"],
            "sim_id": row["sim_id"],
            "alpha_id": row["alpha_id"],
            "status": row["status"],
            "submitted_at": row["submitted_at"],
            "completed_at": row["completed_at"],
            "error_message": row["error_message"],
            "raw_result_json": raw,
        }, upsert=True)
        if result:
            ok += 1
    print(f"  → {ok}/{len(rows)} runs migrated")


def _migrate_metrics(conn, sb):
    rows = conn.execute("SELECT * FROM metrics").fetchall()
    print(f"Migrating {len(rows)} metrics...")
    ok = 0
    for row in rows:
        result = sb._post("metrics", {
            "run_id": row["run_id"],
            "sharpe": row["sharpe"],
            "fitness": row["fitness"],
            "turnover": row["turnover"],
            "returns": row["returns"],
            "margin": row["margin"],
            "drawdown": row["drawdown"],
            "checks_passed": bool(row["checks_passed"]) if row["checks_passed"] is not None else None,
            "submit_eligible": bool(row["submit_eligible"]) if row["submit_eligible"] is not None else None,
            "fail_reason": row["fail_reason"],
        }, upsert=True)
        if result:
            ok += 1
    print(f"  → {ok}/{len(rows)} metrics migrated")


def _migrate_submissions(conn, sb):
    rows = conn.execute("SELECT * FROM submissions").fetchall()
    print(f"Migrating {len(rows)} submissions...")
    ok = 0
    for row in rows:
        result = sb._post("submissions", {
            "submission_id": row["submission_id"],
            "candidate_id": row["candidate_id"],
            "run_id": row["run_id"],
            "submitted_at": row["submitted_at"],
            "submission_status": row["submission_status"],
            "message": row["message"],
        }, upsert=True)
        if result:
            ok += 1
    print(f"  → {ok}/{len(rows)} submissions migrated")


def _migrate_refinement(conn, sb):
    rows = conn.execute("SELECT * FROM refinement_queue").fetchall()
    print(f"Migrating {len(rows)} refinement queue entries...")
    ok = 0
    for row in rows:
        result = sb._post("refinement_queue", {
            "candidate_id": row["candidate_id"],
            "run_id": row["run_id"],
            "priority": row["priority"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "consumed": bool(row["consumed"]),
            "source_stage": row["source_stage"] if "source_stage" in row.keys() else "unknown",
            "base_sharpe": row["base_sharpe"] if "base_sharpe" in row.keys() else None,
            "base_fitness": row["base_fitness"] if "base_fitness" in row.keys() else None,
            "base_turnover": row["base_turnover"] if "base_turnover" in row.keys() else None,
        }, upsert=True)
        if result:
            ok += 1
    print(f"  → {ok}/{len(rows)} refinement entries migrated")


if __name__ == "__main__":
    main()
