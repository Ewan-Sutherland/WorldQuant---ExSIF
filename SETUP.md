# AlphaBot v6.1 — Team Setup Guide

## Quick Start (5 minutes)

### 1. Install dependencies
```bash
pip install requests python-dotenv optuna
```

### 2. Create `.env` file in the project folder
Copy `.env.template` and fill in your credentials:
```bash
cp .env.template .env
```

### 3. Edit `.env` with YOUR credentials
- `BRAIN_USERNAME` and `BRAIN_PASSWORD` — your personal BRAIN login
- `GEMINI_API_KEY` — get free from https://aistudio.google.com/apikey
- Supabase credentials are pre-filled (shared team database)

### 4. Run
```bash
python main.py
```

You should see:
```
[OPTUNA] Settings optimizer available
[LLM] LLM generator available
[COMBINER] Loaded XX near-passers across X categories
[WARM_START] Loaded XX passed cores from submitted alphas
[WARM_START] Loaded XX CW-blacklisted expressions
[WARM_START] Loaded XX self-corr rejected cores
[START] Alpha bot is running
```

## Important Notes

- **Everyone shares the same Supabase** — this means the bot learns from ALL team members' sims
- **Warm-start** loads shared knowledge on startup (submitted alphas, rejected cores, CW blacklist)
- **AUTO_SUBMIT is ON** — eligible alphas are submitted automatically to your BRAIN account
- **Don't run multiple instances** on the same BRAIN account — use one bot per person
- Each person's submissions are tagged to their BRAIN account individually

## What the bot does
- Generates alpha expressions using templates (55%), LLM (25%), signal combiner (10%), evolutionary mutation (10%)
- Simulates them on BRAIN API
- Near-passers get refined with Optuna (Bayesian settings optimization)
- Eligible alphas are auto-submitted
- Self-correlation rejections are tracked to avoid wasting future API calls
- All results stored in shared Supabase for team-wide learning
