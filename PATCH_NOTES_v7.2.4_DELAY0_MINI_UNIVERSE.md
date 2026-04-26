# v7.2.4 Delay-0 Mini-Universe Patch

This patch treats Delay 0 as a separate search regime rather than a random setting sweep.

## Added
- Dedicated Delay-0 template families:
  - `delay0_reversal`
  - `delay0_volume_pressure`
  - `delay0_vwap_range`
  - `delay0_event_reaction`
- Fresh Delay-0 generation budget via `DELAY0_TEMPLATE_PROBABILITY`.
- Delay-0-specific settings pool: short decays, broad universes, controlled truncation.
- Clear `[DELAY0_CANDIDATE]` logging.

## Safety / separation
- Signal combiner skips Delay-0 rows by default.
- Evolver skips Delay-0 rows by default.
- Combiner/evolver/LLM candidate creation no longer randomly flips to Delay 0.
- Existing Optuna/sweeps can still test Delay 0 where allowed, but specialist Delay-0 templates now get a separate lane.

## Why
Delay 0 is effectively a mini-universe with a lower score multiplier and different self-correlation surface. Mixing it casually with Delay 1 templates risks noisy candidates and contaminated learned populations.
