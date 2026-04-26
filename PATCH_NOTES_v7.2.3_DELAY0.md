# v7.2.3 Delay-0 patch

Changes:
- Delay is now included in Optuna in-memory de-duplication.
- Optimisation variant logs show both decay and delay explicitly.
- settings_override now preserves `delay` instead of forcing delay=1.
- Delay-0 safety check is stricter and checks raw returns/close/open/high/low/vwap outside ts_* wrappers.
- Fresh generation now has a small controlled delay-0 exploration budget for safe expressions.
- Universe sweeper still tests delay-0, but with the stricter safety gate.

Rationale:
Delay 0 should be treated as a separate mini-universe. It is useful for self-correlation diversification, but many delay-1 expressions use raw same-day price/return terms and are poor/unsafe candidates for delay 0.
