# AlphaBot v7.0 — Team Setup Guide

## What's new in v7.0

- **Dynamic datasets**: The bot reads all 2,646 fields from `data/wq_all_datasets.xlsx` — no more hardcoded field lists
- **Owner-isolated refinement**: Each bot only refines its OWN near-passers (no more stealing teammates' queue)
- **Team shared learning**: Bots publish their family/template performance stats and learn from each other
- **Graceful shutdown**: Ctrl+C saves state, in-flight sims resume on next start
- **Neutral weights**: All families start equal — the adaptive system learns what works on YOUR account

## Quick Start (5 minutes)

### 1. Install dependencies
```bash
pip install requests python-dotenv optuna pandas openpyxl
```

### 2. Create `.env` file
```bash
cp .env.template .env
```

### 3. Edit `.env` with YOUR credentials
- `BRAIN_USERNAME` and `BRAIN_PASSWORD` — your personal BRAIN login
- `GEMINI_API_KEYS` — get free keys from https://aistudio.google.com/apikey (get 5 for higher rate limit)
- `SUPABASE_URL` and `SUPABASE_ANON_KEY` — ask the team lead for these (shared)

### 4. Run the database migration (FIRST TIME ONLY)
The team lead needs to run `migrations/v7_multi_bot.sql` in the Supabase SQL Editor once.
This adds owner tracking, the team stats table, and bot state table.

### 5. Run
```bash
python main.py
```

You should see:
```
============================================================
  DATASET SUMMARY — 2646 total fields
============================================================
  fundamental                          886 fields
  analyst_estimates                    653 fields
  ...
============================================================

[TEAM] Team weights enabled for your_email@example.com
[START] Alpha bot is running
[START] Owner: your_email@example.com
[START] Press Ctrl+C once for graceful shutdown, twice to force quit
```

## How it works

### Each bot is independent but shares knowledge
- Your refinement queue is YOURS — no one else can consume your near-passers
- Your submissions go to YOUR Brain account only
- But ALL bots share their performance stats in `team_stats` table
- Fresh bots trust teammates' data heavily, experienced bots rely more on their own

### Adaptive learning
- Families and templates start with equal weights (1.0)
- The bot uses Thompson Sampling — automatically explores under-tested families
- Every 25 completions, it publishes stats to the team and reads teammates' data
- If 2+ teammates independently find a family dead (30+ sims, avg Sharpe < 0.2), it gets suppressed for everyone
- But never fully zeroed (floor = 0.05) — anyone can still stumble onto something

### Graceful shutdown
- Press **Ctrl+C once** → finishes current tick, saves state, publishes final stats
- Press **Ctrl+C twice** → immediate exit (in-flight sims marked interrupted)
- On next start, interrupted refinements are automatically re-queued

### Datasets
- The bot reads `data/wq_all_datasets.xlsx` at startup
- This contains all fields your team has access to across 14 data categories
- Templates dynamically sample from the full field space (not a hardcoded subset)
- If the Excel is missing, the bot falls back to a built-in minimal field set

## Important Rules

- **One bot per Brain account** — don't run multiple instances on the same login
- **Don't modify** the Supabase credentials — everyone shares the same database
- **AUTO_SUBMIT is OFF** by default — eligible alphas are staged for review
- Set `AUTO_SUBMIT = True` in config.py if you want automatic submission

## File structure
```
v7/
├── main.py              # Entry point (with graceful shutdown)
├── bot.py               # Core orchestration
├── config.py            # Settings (neutral weights for distribution)
├── datasets.py          # NEW: Dynamic field loader from Excel
├── team_weights.py      # NEW: Shared learning across bots
├── generator.py         # Alpha expression generator
├── templates.py         # Template library (uses dynamic fields)
├── llm_generator.py     # LLM-guided generation (uses dynamic fields)
├── signal_combiner.py   # Multi-signal combination engine
├── alpha_evolver.py     # Evolutionary mutation
├── settings_optimizer.py # Optuna-based settings optimization
├── brain_client.py      # WorldQuant BRAIN API client
├── storage_supabase.py  # Supabase storage (owner-scoped)
├── storage.py           # SQLite storage (local fallback)
├── storage_factory.py   # Storage backend selector
├── similarity.py        # Expression similarity engine
├── universe_sweeper.py  # Universe sweep for near-passers
├── evaluator.py         # Submission evaluation
├── models.py            # Data models
├── canonicalize.py      # Expression canonicalization
├── scheduler.py         # Concurrent sim scheduler
├── .env.template        # Environment template
├── requirements.txt     # Python dependencies
├── data/
│   └── wq_all_datasets.xlsx  # Team datasets (2,646 fields)
└── migrations/
    └── v7_multi_bot.sql      # Database migration (run once)
```
