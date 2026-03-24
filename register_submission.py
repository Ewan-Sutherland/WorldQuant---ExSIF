"""
Register a manually submitted alpha in the bot's database.

Usage:
    # By candidate ID (shown in [ELIGIBLE] log lines):
    python register_submission.py --candidate-id cand_8067bd84baee46b0b90c9a0b3e604d0d

    # By expression hash:
    python register_submission.py --hash abc123def456

    # List all eligible candidates to find the right one:
    python register_submission.py --list-eligible
"""
from __future__ import annotations

import argparse

import config
from storage import Storage


def main():
    parser = argparse.ArgumentParser(description="Register manual alpha submissions")
    parser.add_argument("--candidate-id", type=str, help="Candidate ID to register")
    parser.add_argument("--hash", type=str, help="Expression hash to register")
    parser.add_argument("--list-eligible", action="store_true", help="List all eligible candidates")
    parser.add_argument("--list-submitted", action="store_true", help="List all submitted candidates")
    args = parser.parse_args()

    storage = Storage(config.DB_PATH)

    if args.list_eligible:
        rows = storage.get_submission_eligible_candidates(limit=50)
        if not rows:
            print("No eligible candidates found.")
            return
        print(f"\n{'candidate_id':<46} {'template':<10} {'family':<16} {'sharpe':<8} {'fitness':<8} {'turnover':<8}")
        print("-" * 120)
        for row in rows:
            s = f"{row['sharpe']:.3f}" if row['sharpe'] else "?"
            f = f"{row['fitness']:.3f}" if row['fitness'] else "?"
            t = f"{row['turnover']:.3f}" if row['turnover'] else "?"
            print(f"{row['candidate_id']:<46} {row['template_id']:<10} {row['family']:<16} {s:<8} {f:<8} {t:<8}")
            print(f"  expr: {row['canonical_expression'][:100]}")
        return

    if args.list_submitted:
        rows = storage.get_submitted_candidate_rows(limit=50)
        if not rows:
            print("No submitted candidates found.")
            return
        print(f"\n{'candidate_id':<46} {'template':<10} {'family':<16} {'sharpe':<8} {'fitness':<8}")
        print("-" * 120)
        for row in rows:
            s = f"{row['sharpe']:.3f}" if row['sharpe'] else "?"
            f = f"{row['fitness']:.3f}" if row['fitness'] else "?"
            print(f"{row['candidate_id']:<46} {row['template_id']:<10} {row['family']:<16} {s:<8} {f:<8}")
            print(f"  expr: {row['canonical_expression'][:100]}")
        return

    if args.candidate_id:
        ok = storage.register_manual_submission_by_candidate_id(args.candidate_id)
        if ok:
            print(f"[OK] Registered submission for candidate_id={args.candidate_id}")
        else:
            print(f"[FAIL] Could not find completed run for candidate_id={args.candidate_id}")
        return

    if args.hash:
        ok = storage.register_manual_submission(args.hash)
        if ok:
            print(f"[OK] Registered submission for hash={args.hash}")
        else:
            print(f"[FAIL] Could not find candidate with hash={args.hash}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
