# alphabot v7.2.2 hotfix notes

Applied after reviewing the four restarted bot logs and the Supabase `team_submit_signals` screenshot.

## Critical fixes

1. Coordinator signal cutoff widened
   - `coordinated_submit.py`
   - Replaced per-bot `run_started_at` filtering with a shared same-window 3-hour `signal_cutoff`.
   - Fixes the likely bug where the coordinator ignored valid `scores_ready` rows from workers that finished earlier.

2. Terminal simulation status aliasing
   - `bot.py`, `brain_client.py`
   - Treats `status=fail` and `status=error` as failed terminal states.
   - Fixes `[UNKNOWN_TERMINAL_STATUS] ... status=fail`.

3. Safer metric/check handling
   - `brain_client.py`, `evaluator.py`
   - Alpha fetch failure or missing alpha id no longer sets `checks_passed=True`.
   - Missing metrics now remain non-eligible instead of potentially being promoted through a truthy default.

4. Self-correlation numeric guard
   - `brain_client.py`
   - If WQ reports `SELF_CORRELATION` as PASS but the numeric value is above its stated limit, the bot treats it as failed.
   - Addresses log cases like `SELF_CORRELATION: PASS (value=0.7144, limit=0.7)`.

5. Supabase retry wrapper
   - `storage_supabase.py`
   - Adds small retry/backoff for transient 429/5xx/network failures.
   - Logs unavailable Supabase calls more clearly so empty results are less likely to hide DB failures.

6. Dead-family softening
   - `config.py`
   - `DEAD_FAMILY_WEIGHT` moved from 0.01 to 0.03.
   - This is still a cooldown, but less likely to permanently starve useful low-correlation families.

## Log review observations

- Workers did appear to send `scores_ready`, so the failure was more likely coordinator-side filtering than worker-side missing signals.
- Multiple `UNKNOWN_TERMINAL_STATUS status=fail` events appeared in the coordinator log.
- Several eligible variants were rejected by negative portfolio score, which is expected behaviour but shows that single-alpha Sharpe/Fitness is not the current bottleneck.
- Several before-after checks were unavailable and staged as `unverified`; this is acceptable, but those alphas depend on the coordinated submission pipeline being reliable.
- Repeated `DIVERSITY_EXHAUST` and `SCORE_NEG_BLOCK` messages suggest the search policy is heavily exploiting a few cores. Keep monitoring for search collapse.
