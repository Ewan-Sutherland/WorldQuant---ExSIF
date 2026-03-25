"""
Fetch and register your WQ alphas for self-correlation tracking.

Usage:
    python fetch_my_alphas.py --probe              # Find which API endpoints return your active alphas
    python fetch_my_alphas.py --list               # List all alphas from default endpoint
    python fetch_my_alphas.py --register-all       # Register all eligible alphas found via API
    python fetch_my_alphas.py --register-alpha ID   # Register one alpha by WQ ID

    # Manual registration (when API doesn't return submitted alphas):
    python fetch_my_alphas.py --manual --expression "rank(ts_mean(close, 10) - close)" \
        --universe TOPSP500 --decay 4 --neutralization SUBINDUSTRY --truncation 0.08 \
        --sharpe 1.50 --fitness 1.10 --turnover 0.35
"""
from __future__ import annotations
import argparse, json, sys
import config
from brain_client import BrainClient
from canonicalize import canonicalize_expression, hash_candidate
from models import Candidate, SimulationSettings, Run, Metrics, new_id, utc_now
from storage_factory import get_storage


def _try_endpoint(client, url):
    try:
        r = client.session.get(url, timeout=client.timeout_seconds)
        if r.status_code == 401:
            client.login()
            r = client.session.get(url, timeout=client.timeout_seconds)
        if r.status_code != 200:
            return [], r.status_code
        data = r.json()
        if isinstance(data, list): return data, 200
        if isinstance(data, dict):
            for k in ("results", "alphas", "data"):
                if isinstance(data.get(k), list): return data[k], 200
        return [], 200
    except Exception:
        return [], -1


def probe_all_endpoints(client):
    client.ensure_session()
    base = client.base_url
    urls = [
        f"{base}/users/self/alphas",
        f"{base}/users/self/alphas?limit=100",
        f"{base}/users/self/alphas?stage=OS",
        f"{base}/users/self/alphas?stage=OS&limit=100",
        f"{base}/users/self/alphas?stage=ACTIVE",
        f"{base}/users/self/alphas?status=ACTIVE",
        f"{base}/users/self/alphas?status=SUBMITTED",
        f"{base}/users/self/alphas?order=-dateSubmitted&limit=50",
        f"{base}/alphas?limit=50&stage=OS",
        f"{base}/alphas?limit=50&status=ACTIVE",
        f"{base}/alphas?limit=50",
        f"{base}/users/self/alphas?competition=IQC2026S1",
        f"{base}/competitions/IQC2026S1/alphas",
        f"{base}/users/self/submissions",
        f"{base}/users/self/submissions?limit=50",
    ]
    found = {}
    for url in urls:
        alphas, code = _try_endpoint(client, url)
        short = url.replace(base, "")
        if code == 200 and alphas:
            stages = {str(a.get("stage","?")) for a in alphas}
            statuses = {str(a.get("status","?")) for a in alphas}
            print(f"  [200] {short} -> {len(alphas)} alpha(s)  stages={stages}  statuses={statuses}")
            found[short] = alphas
        elif code == 200:
            print(f"  [200] {short} -> 0 results")
        else:
            print(f"  [{code}] {short}")
    return found


def _is_active(a):
    return (
        str(a.get("status","")).upper() in {"ACTIVE","SUBMITTED"}
        or str(a.get("stage","")).upper() in {"OS","ACTIVE","PROD"}
        or a.get("dateSubmitted") is not None
    )


def extract_info(a):
    s = a.get("settings", {})
    reg = a.get("regular", {})
    expr = reg.get("code","") if isinstance(reg, dict) else (reg if isinstance(reg, str) else "")
    isd = a.get("is", {}) or {}
    return {
        "alpha_id": a.get("id","?"), "expression": expr,
        "stage": a.get("stage","?"), "status": a.get("status","?"),
        "grade": a.get("grade","?"), "date_submitted": a.get("dateSubmitted"),
        "region": s.get("region","?"), "universe": s.get("universe","?"),
        "delay": s.get("delay","?"), "decay": s.get("decay","?"),
        "neutralization": s.get("neutralization","?"), "truncation": s.get("truncation","?"),
        "sharpe": isd.get("sharpe"), "fitness": isd.get("fitness"), "turnover": isd.get("turnover"),
        "settings_raw": s, "is_active": _is_active(a),
        "is_eligible": (
            isd.get("sharpe") is not None and isd.get("fitness") is not None
            and float(isd["sharpe"]) >= 1.25 and float(isd["fitness"]) >= 1.0
            and (isd.get("turnover") is None or float(isd["turnover"]) <= 0.70)
        ),
    }


def guess_family(expr):
    e = expr.replace(" ","")
    if "volume" in e and "*-returns" in e: return "vol_03","volume_flow"
    if "volume/ts_mean(volume" in e and "returns" not in e: return "vol_01","volume_flow"
    if "trade_when" in e and "volume>ts_mean(volume" in e: return "cond_01","conditional"
    if "trade_when" in e: return "cond_02","conditional"
    if "returns-ts_mean(returns" in e: return "mr_04","mean_reversion"
    if "close/ts_mean(close" in e: return "mr_03","mean_reversion"
    if "-ts_delta(close" in e: return "mr_02","mean_reversion"
    if "ts_mean(close" in e and "/ts_std_dev" in e: return "va_02","vol_adjusted"
    if "ts_delta(close" in e and "/ts_std_dev" in e: return "va_01","vol_adjusted"
    if "ts_mean(close" in e and "-close" in e: return "mr_01","mean_reversion"
    return "unknown","unknown"


def register_alpha(storage, expression, settings, alpha_id="manual", sharpe=None, fitness=None, turnover=None):
    tmpl, fam = guess_family(expression)
    canon = canonicalize_expression(expression)
    sim = SimulationSettings(
        region=settings.get("region", config.DEFAULT_REGION),
        universe=settings.get("universe", "TOP3000"),
        delay=int(settings.get("delay", config.DEFAULT_DELAY)),
        decay=int(settings.get("decay", 4)),
        neutralization=settings.get("neutralization", "SUBINDUSTRY"),
        truncation=float(settings.get("truncation", 0.08)),
        pasteurization=settings.get("pasteurization", config.DEFAULT_PASTEURIZATION),
        unit_handling=settings.get("unitHandling", settings.get("unit_handling", config.DEFAULT_UNIT_HANDLING)),
        nan_handling=settings.get("nanHandling", settings.get("nan_handling", config.DEFAULT_NAN_HANDLING)),
        language=settings.get("language", config.DEFAULT_LANGUAGE),
    )
    h = hash_candidate(canon, sim.to_dict())
    if storage.candidate_exists(h):
        row = storage.get_candidate_by_hash(h)
        if row:
            storage.register_manual_submission_by_candidate_id(row["candidate_id"])
            return row["candidate_id"]
    fields = [f for f in ["close","returns","volume","cap","assets","sales","income","cash"] if f in expression]
    cand = Candidate.create(expression=expression, canonical_expression=canon, expression_hash=h,
                            template_id=tmpl, family=fam, fields=fields, params={}, settings=sim)
    storage.insert_candidate(cand)
    run = Run.create(candidate_id=cand.candidate_id, status="completed")
    storage.insert_run(run)
    storage.update_run(run.run_id, status="completed", completed_at=utc_now(), alpha_id=alpha_id)
    m = Metrics(run_id=run.run_id, sharpe=float(sharpe) if sharpe else None,
                fitness=float(fitness) if fitness else None, turnover=float(turnover) if turnover else None,
                checks_passed=True, submit_eligible=True)
    storage.insert_metrics(m)
    storage.insert_submission(submission_id=new_id("sub"), candidate_id=cand.candidate_id,
                              run_id=run.run_id, submitted_at=utc_now(),
                              submission_status="submitted", message=f"imported:alpha_id={alpha_id}")
    return cand.candidate_id


def main():
    p = argparse.ArgumentParser(description="Fetch and register WQ alphas")
    p.add_argument("--probe", action="store_true", help="Try all API endpoints")
    p.add_argument("--list", action="store_true")
    p.add_argument("--register-all", action="store_true")
    p.add_argument("--register-alpha", type=str)
    p.add_argument("--raw", action="store_true")
    p.add_argument("--manual", action="store_true", help="Register manually")
    p.add_argument("--expression", type=str)
    p.add_argument("--universe", type=str, default="TOP3000")
    p.add_argument("--decay", type=int, default=4)
    p.add_argument("--neutralization", type=str, default="SUBINDUSTRY")
    p.add_argument("--truncation", type=float, default=0.08)
    p.add_argument("--sharpe", type=float, default=None)
    p.add_argument("--fitness", type=float, default=None)
    p.add_argument("--turnover", type=float, default=None)
    p.add_argument("--alpha-id", type=str, default="manual")
    args = p.parse_args()

    client = BrainClient(username=config.BRAIN_USERNAME, password=config.BRAIN_PASSWORD,
                         base_url="https://api.worldquantbrain.com")
    storage = get_storage()

    if args.manual:
        if not args.expression:
            print("[ERROR] --manual requires --expression"); return
        settings = {"region":"USA","universe":args.universe,"delay":1,"decay":args.decay,
                    "neutralization":args.neutralization,"truncation":args.truncation,
                    "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"OFF","language":"FASTEXPR"}
        cid = register_alpha(storage, args.expression, settings, args.alpha_id,
                             args.sharpe, args.fitness, args.turnover)
        tmpl, fam = guess_family(args.expression)
        print(f"[OK] Registered -> {cid}  family={fam}  template={tmpl}")
        print(f"     expr: {args.expression}")
        print(f"     universe={args.universe} decay={args.decay} neut={args.neutralization}")
        print(f"\nVerify: python register_submission.py --list-submitted")
        return

    if args.probe:
        print("[*] Probing WQ API endpoints...\n")
        found = probe_all_endpoints(client)
        if not found:
            print("\n[!] No data from any endpoint. Use --manual instead.")
            return
        active = []
        for endpoint, alphas in found.items():
            for a in alphas:
                if _is_active(a):
                    info = extract_info(a)
                    info["_src"] = endpoint
                    active.append(info)
        if active:
            print(f"\n[*] Found {len(active)} active/submitted alpha(s):")
            for info in active:
                print(f"\n  {info['alpha_id']}  stage={info['stage']}  status={info['status']}")
                print(f"  expr: {info['expression'][:100]}")
                print(f"  sharpe={info['sharpe']}  fitness={info['fitness']}  universe={info['universe']}")
        else:
            print("\n[!] No ACTIVE alphas found via API. Use --manual to register them.")
            print("    Copy expression + settings from WQ website and run:")
            print('    python fetch_my_alphas.py --manual --expression "..." --universe ... --decay ... etc')
        return

    print("[*] Fetching alphas...")
    alphas = fetch_my_alphas(client)
    if not alphas: print("[!] No alphas returned."); return
    if args.raw: print(json.dumps(alphas, indent=2, default=str)); return
    infos = [extract_info(a) for a in alphas]

    if args.list or (not args.register_all and not args.register_alpha):
        for i, info in enumerate(infos):
            tags = []
            if info["is_active"]: tags.append("ACTIVE")
            if info["is_eligible"]: tags.append("ELIGIBLE")
            print(f"  [{i}] {info['alpha_id']}  {' '.join(tags)}")
            print(f"      expr: {info['expression'][:100]}")
            print(f"      stage={info['stage']} status={info['status']} universe={info['universe']} decay={info['decay']}")
            print(f"      sharpe={info['sharpe']} fitness={info['fitness']} turnover={info['turnover']}")
            tmpl, fam = guess_family(info["expression"])
            print(f"      -> family={fam} template={tmpl}\n")
        return

    if args.register_all:
        n = 0
        for info in infos:
            if not info["is_eligible"] and not info["is_active"]: continue
            if not info["expression"]: continue
            cid = register_alpha(storage, info["expression"], info["settings_raw"],
                                 str(info["alpha_id"]), info["sharpe"], info["fitness"], info["turnover"])
            tmpl, fam = guess_family(info["expression"])
            print(f"  [OK] {info['alpha_id']} -> {cid}  {fam}  sharpe={info['sharpe']}")
            n += 1
        print(f"\n[DONE] Registered {n} alpha(s)")
        return

    if args.register_alpha:
        info = next((i for i in infos if str(i["alpha_id"]) == args.register_alpha), None)
        if not info: print(f"[ERROR] Not found: {args.register_alpha}"); return
        cid = register_alpha(storage, info["expression"], info["settings_raw"],
                             str(info["alpha_id"]), info["sharpe"], info["fitness"], info["turnover"])
        print(f"[OK] {info['alpha_id']} -> {cid}")


if __name__ == "__main__":
    main()
