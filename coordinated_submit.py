"""
v7.2: Coordinated team submission pipeline.

All participating bots check their OWN scores in parallel, then
one coordinator (Ewan) ranks globally and orchestrates submissions.

Signal protocol (via team_submit_signals table):
  - scores_ready:      "I've finished checking my own scores"
  - submit_command:     "Submit this alpha" (target_owner + alpha_id + round_num)
  - submitted:          "I submitted (or failed)" (round_num + accepted)
  - recheck:            "Re-check your scores now" (round_num)
  - recheck_done:       "I've finished re-checking" (round_num)
  - done:               "Coordinator is finished, stop waiting"
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import config


def _window_id() -> str:
    """Current submission window identifier.
    Uses 6-hour blocks aligned to 00:00 UTC so both bots always get the same ID
    even if they trigger a few minutes apart.
    """
    now = datetime.now(timezone.utc)
    block = (now.hour // 6) * 6
    return now.strftime(f"%Y-%m-%d") + f"T{block:02d}:00"


def _recent_cutoff() -> str:
    """ISO timestamp for 'recent' signals — ignore anything older than 30 min."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    return cutoff.isoformat()


class CoordinatedSubmitPipeline:
    """Runs on EVERY participating bot (Ewan + Griff)."""

    WAIT_TIMEOUT = 180   # 3 minutes max wait for other bot
    POLL_INTERVAL = 5    # seconds between polls

    def __init__(self, storage, client, config_mod):
        self.storage = storage
        self.client = client
        self.config = config_mod
        self.owner = storage.owner
        self.window_id = _window_id()
        self.is_coordinator = getattr(config_mod, "IS_COORDINATOR", False)
        self.participating_owners = getattr(config_mod, "COORDINATED_SUBMIT_OWNERS", [])

    # ── Signals ──────────────────────────────────────────────────

    def _send_signal(self, signal: str, target_owner: str = None,
                     alpha_id: str = None, round_num: int = 0, payload: dict = None):
        """Write a coordination signal to Supabase."""
        if payload is None:
            payload = {}
        payload["round_num"] = round_num
        try:
            self.storage._post("team_submit_signals", {
                "window_id": self.window_id,
                "owner": self.owner,
                "signal": signal,
                "target_owner": target_owner,
                "alpha_id": alpha_id,
                "payload": json.dumps(payload),
            })
        except Exception as exc:
            print(f"  [SIGNAL] send failed ({signal}): {exc}")

    def _wait_for_signal(self, signal: str, from_owner: str = None,
                         target_owner: str = None, round_num: int = None,
                         timeout: int = None) -> dict | None:
        """Poll for a specific signal. Returns signal row or None on timeout."""
        timeout = timeout or self.WAIT_TIMEOUT
        deadline = time.time() + timeout
        cutoff = _recent_cutoff()

        while time.time() < deadline:
            params = {
                "window_id": f"eq.{self.window_id}",
                "signal": f"eq.{signal}",
                "created_at": f"gte.{cutoff}",
                "order": "created_at.desc",
                "limit": 10,
            }
            if from_owner:
                params["owner"] = f"eq.{from_owner}"
            if target_owner:
                params["target_owner"] = f"eq.{target_owner}"
            try:
                rows = self.storage._get("team_submit_signals", params)
                if rows and round_num is not None:
                    # Filter by round_num in payload
                    for row in rows:
                        p = json.loads(row.get("payload", "{}")) if row.get("payload") else {}
                        if p.get("round_num") == round_num:
                            return row
                elif rows:
                    return rows[0]
            except Exception:
                pass
            remaining = deadline - time.time()
            if remaining > 0:
                time.sleep(min(self.POLL_INTERVAL, remaining))
        return None

    # ── Score Checking ───────────────────────────────────────────

    def _check_own_scores(self) -> list[dict]:
        """Check scores for own ready_alphas using own credentials."""
        try:
            alphas = self.storage._get("ready_alphas", {
                "owner": f"eq.{self.owner}",
                "status": "in.(ready,unverified)",
                "select": "*",
                "order": "sharpe.desc",
            }) or []
        except Exception as exc:
            print(f"  ERROR loading own alphas: {exc}")
            return []

        if not alphas:
            print(f"  No ready alphas for {self.owner}")
            return []

        print(f"  Checking {len(alphas)} own alphas...")

        for i, a in enumerate(alphas):
            alpha_id = a.get("alpha_id")
            if not alpha_id:
                a["live_score"] = None
                continue

            score = None
            for attempt in range(3):
                try:
                    perf = self.client.check_before_after_performance(
                        alpha_id, competition_id=self.config.IQC_COMPETITION_ID,
                    )
                    score = perf.get("_score_change")
                    if score is not None:
                        break
                except Exception:
                    pass
                if attempt < 2:
                    time.sleep(3)

            a["live_score"] = score

            # Write score to Supabase so coordinator can read it
            try:
                new_status = "ready" if score is not None and score >= 0 else (
                    "rejected" if score is not None and score < 0 else "unverified"
                )
                self.storage._patch("ready_alphas", {"id": a["id"]}, {
                    "score_change": score,
                    "status": new_status,
                })
            except Exception:
                pass

            direction = "+" if score and score > 0 else "" if score else "?"
            print(f"    [{i+1}/{len(alphas)}] {a.get('family','')}/{a.get('template_id','')} "
                  f"S={a.get('sharpe',0):.2f} → score: {direction}{score if score is not None else 'unknown'}")
            time.sleep(2)

        # Retry unknowns once
        unknowns = [a for a in alphas if a.get("live_score") is None and a.get("alpha_id")]
        if unknowns:
            print(f"\n  {len(unknowns)} unknown — retrying after 10s...")
            time.sleep(10)
            for a in unknowns:
                try:
                    perf = self.client.check_before_after_performance(
                        a["alpha_id"], competition_id=self.config.IQC_COMPETITION_ID,
                    )
                    score = perf.get("_score_change")
                    if score is not None:
                        a["live_score"] = score
                        self.storage._patch("ready_alphas", {"id": a["id"]}, {
                            "score_change": score,
                            "status": "ready" if score >= 0 else "rejected",
                        })
                        print(f"    ✅ {a.get('family','')} S={a.get('sharpe',0):.2f} → {score:+.0f}")
                except Exception:
                    pass
                time.sleep(2)

        return alphas

    # ── Main Entry ───────────────────────────────────────────────

    def run(self) -> dict:
        """Main entry — called by both coordinator and participants."""
        print(f"\n{'='*60}")
        print(f"  COORDINATED SUBMISSION — {self.owner}")
        print(f"  Window: {self.window_id}")
        print(f"  Role: {'COORDINATOR' if self.is_coordinator else 'PARTICIPANT'}")
        print(f"{'='*60}\n")

        # Phase 1: Check own scores
        print("  ── Phase 1: Checking own scores ──")
        alphas = self._check_own_scores()
        positive = [a for a in alphas if a.get("live_score") is not None and a["live_score"] > 0]
        print(f"\n  Own results: {len(positive)} positive out of {len(alphas)}\n")

        # Signal scores ready
        self._send_signal("scores_ready", payload={
            "count": len(alphas),
            "positive": len(positive),
        })

        if self.is_coordinator:
            return self._run_coordinator()
        else:
            return self._run_participant()

    # ── Coordinator ──────────────────────────────────────────────

    def _run_coordinator(self) -> dict:
        """Wait for all bots, rank globally, orchestrate submissions."""

        # Phase 2: Wait for other bots
        print("  ── Phase 2: Waiting for other bots ──")
        other_owners = [o for o in self.participating_owners if o != self.owner]

        for other in other_owners:
            sig = self._wait_for_signal("scores_ready", from_owner=other)
            if sig:
                payload = json.loads(sig.get("payload", "{}")) if sig.get("payload") else {}
                print(f"    ✅ {other}: {payload.get('positive', '?')} positive ready")
            else:
                print(f"    ⚠️ {other}: timed out — proceeding without")

        # Small delay to ensure DB writes have propagated
        time.sleep(3)

        # Phase 3: Greedy submission loop
        print("\n  ── Phase 3: Global ranking & submission ──")
        submitted = 0
        rejected = 0
        max_rounds = getattr(self.config, "MAX_SUBMISSIONS_PER_WINDOW", 15)

        for round_num in range(1, max_rounds + 1):
            all_positive = self._read_all_positive()

            if not all_positive:
                print(f"\n  No more positive alphas — done")
                break

            best = all_positive[0]
            best_owner = best["_owner"]
            best_score = best.get("score_change", 0)
            best_alpha_id = best.get("alpha_id", "")

            print(f"\n  🏆 Round {round_num}: BEST = {best_owner} "
                  f"score={best_score:+.0f} S={best.get('sharpe',0):.2f} "
                  f"{best.get('family','')}")

            if best_owner == self.owner:
                # Submit directly
                print(f"  Submitting own alpha...")
                success = self._submit_alpha(best)
            else:
                # Tell the other bot to submit
                print(f"  Sending submit command to {best_owner}...")
                self._send_signal("submit_command",
                                  target_owner=best_owner,
                                  alpha_id=best_alpha_id,
                                  round_num=round_num,
                                  payload={"score": best_score})

                # Wait for response (keyed by round_num — no replay bug)
                sig = self._wait_for_signal("submitted", from_owner=best_owner,
                                            round_num=round_num, timeout=120)
                if sig:
                    p = json.loads(sig.get("payload", "{}")) if sig.get("payload") else {}
                    success = p.get("accepted", False)
                    if success:
                        print(f"    ✅ {best_owner} ACCEPTED")
                    else:
                        print(f"    ❌ {best_owner} rejected: {p.get('reason', 'unknown')}")
                else:
                    print(f"    ⚠️ {best_owner} didn't respond — skipping this alpha")
                    success = False

            if success:
                submitted += 1
            else:
                rejected += 1
                try:
                    self.storage._patch("ready_alphas", {"id": best["id"]}, {"status": "rejected"})
                except Exception:
                    pass

            # Re-check scores across all bots
            print(f"  Re-checking scores after round {round_num}...")
            self._send_signal("recheck", round_num=round_num)
            self._recheck_own_positive()

            # Wait for other bots to finish rechecking
            for other in other_owners:
                self._wait_for_signal("recheck_done", from_owner=other,
                                      round_num=round_num, timeout=45)
            time.sleep(2)

        # Signal done so participants stop waiting
        self._send_signal("done")

        print(f"\n{'='*60}")
        print(f"  COORDINATED SUBMISSION COMPLETE")
        print(f"  Submitted: {submitted}  Rejected: {rejected}")
        print(f"{'='*60}\n")

        return {"submitted": submitted, "rejected": rejected}

    # ── Participant ──────────────────────────────────────────────

    def _run_participant(self) -> dict:
        """Wait for coordinator commands, submit when told."""
        print("  ── Waiting for coordinator ──")

        submitted = 0
        rejected = 0
        max_rounds = getattr(self.config, "MAX_SUBMISSIONS_PER_WINDOW", 15)

        for round_num in range(1, max_rounds + 1):
            # Poll for: submit_command for this round, recheck for this round, or done
            deadline = time.time() + 180
            got_command = None
            got_done = False

            while time.time() < deadline:
                # Check for done
                done_sig = self._wait_for_signal("done", timeout=1)
                if done_sig:
                    got_done = True
                    break

                # Check for submit command for THIS round (round_num prevents replay)
                cmd_sig = self._wait_for_signal("submit_command",
                                                 target_owner=self.owner,
                                                 round_num=round_num,
                                                 timeout=1)
                if cmd_sig:
                    got_command = cmd_sig
                    break

                # Check for recheck (coordinator submitted its own alpha)
                recheck_sig = self._wait_for_signal("recheck", round_num=round_num, timeout=1)
                if recheck_sig:
                    print(f"  Round {round_num}: coordinator submitted — re-checking scores...")
                    self._recheck_own_positive()
                    self._send_signal("recheck_done", round_num=round_num)
                    # Move to next round — coordinator will send next command with round_num+1
                    break

                time.sleep(self.POLL_INTERVAL)

            if got_done:
                print(f"  Coordinator finished — done")
                break

            if got_command:
                # Process submit command
                alpha_id = got_command.get("alpha_id")
                payload = json.loads(got_command.get("payload", "{}")) if got_command.get("payload") else {}
                print(f"\n  📩 Round {round_num}: submit alpha_id={alpha_id[:12]}... "
                      f"(score={payload.get('score', '?')})")

                # Find the alpha
                try:
                    rows = self.storage._get("ready_alphas", {
                        "owner": f"eq.{self.owner}",
                        "alpha_id": f"eq.{alpha_id}",
                    }) or []
                except Exception:
                    rows = []

                if not rows:
                    print(f"  ⚠️ Alpha not found — skipping")
                    self._send_signal("submitted", round_num=round_num,
                                      payload={"accepted": False, "reason": "not_found"})
                    rejected += 1
                else:
                    alpha = rows[0]
                    success = self._submit_alpha(alpha)

                    if success:
                        submitted += 1
                        self._send_signal("submitted", round_num=round_num,
                                          payload={"accepted": True, "alpha_id": alpha_id})
                    else:
                        rejected += 1
                        self._send_signal("submitted", round_num=round_num,
                                          payload={"accepted": False, "alpha_id": alpha_id,
                                                   "reason": "rejected"})
                        try:
                            self.storage._patch("ready_alphas", {"id": alpha["id"]}, {"status": "rejected"})
                        except Exception:
                            pass

                # Wait for recheck
                recheck_sig = self._wait_for_signal("recheck", round_num=round_num, timeout=30)
                if recheck_sig:
                    print(f"  Re-checking own scores...")
                    self._recheck_own_positive()
                    self._send_signal("recheck_done", round_num=round_num)

        print(f"\n  Participant done: submitted={submitted} rejected={rejected}")
        return {"submitted": submitted, "rejected": rejected}

    # ── Helpers ───────────────────────────────────────────────────

    def _read_all_positive(self) -> list[dict]:
        """Read all positive ready_alphas across participating owners, sorted by score."""
        all_positive = []
        for owner in self.participating_owners:
            try:
                rows = self.storage._get("ready_alphas", {
                    "owner": f"eq.{owner}",
                    "status": "eq.ready",
                    "score_change": "gt.0",
                    "order": "score_change.desc",
                }) or []
                for r in rows:
                    r["_owner"] = owner
                    all_positive.append(r)
            except Exception as exc:
                print(f"    ERROR reading {owner}: {exc}")
        all_positive.sort(key=lambda x: x.get("score_change", 0), reverse=True)
        return all_positive

    def _submit_alpha(self, alpha: dict) -> bool:
        """Submit a single alpha to WQ. Returns True if accepted."""
        alpha_id = alpha.get("alpha_id")
        if not alpha_id:
            return False

        try:
            result = self.client.submit_alpha(alpha_id)
        except Exception as exc:
            print(f"    Submit error: {exc}")
            return False

        accepted = result.get("_accepted")
        if accepted:
            try:
                self.storage._patch("ready_alphas", {"id": alpha["id"]}, {"status": "submitted"})
            except Exception:
                pass
            print(f"    ✅ ACCEPTED — score {alpha.get('score_change', '?')}")
            return True
        else:
            reason = result.get("_fail_reason", "unknown")
            corr = result.get("_self_correlation")
            print(f"    ❌ Rejected: {reason}" + (f" (corr={corr})" if corr else ""))
            return False

    def _recheck_own_positive(self):
        """Quick re-check of own positive alphas after a team submission."""
        try:
            rows = self.storage._get("ready_alphas", {
                "owner": f"eq.{self.owner}",
                "status": "eq.ready",
                "order": "score_change.desc",
            }) or []
        except Exception:
            return

        for a in rows:
            alpha_id = a.get("alpha_id")
            if not alpha_id:
                continue
            try:
                perf = self.client.check_before_after_performance(
                    alpha_id, competition_id=self.config.IQC_COMPETITION_ID,
                )
                score = perf.get("_score_change")
                if score is not None:
                    self.storage._patch("ready_alphas", {"id": a["id"]}, {
                        "score_change": score,
                        "status": "ready" if score >= 0 else "rejected",
                    })
                    direction = "+" if score > 0 else ""
                    print(f"    {a.get('family','')}/{a.get('template_id','')} "
                          f"S={a.get('sharpe',0):.2f} → {direction}{score:.0f}")
            except Exception:
                pass
            time.sleep(2)
