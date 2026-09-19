"""Build a bounded NHL intelligence research queue from the frozen model snapshot."""
import argparse, json, os, tempfile
from datetime import datetime, timezone

DOMAINS = [
    ("starting_goalies", "CRITICAL"),
    ("lines_and_scratches", "CRITICAL"),
    ("injuries_and_returns", "HIGH"),
    ("power_play", "HIGH"),
    ("penalty_kill", "MEDIUM"),
    ("expected_toi_and_role", "HIGH"),
    ("rest_travel_schedule", "MEDIUM"),
    ("coach_player_media", "MEDIUM"),
    ("market", "MEDIUM"),
    ("situational", "LOW"),
]
GATE_LIMITS = {"EARLY": 4, "GAME_DAY": 6, "T-90": 8, "T-30": 10, "PUCK_DROP": 0}

def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def load(path):
    with open(path, encoding="utf-8") as f: return json.load(f)

def atomic(path, obj):
    d=os.path.dirname(os.path.abspath(path)); os.makedirs(d, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".nhl_queue_",suffix=".json",dir=d)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(obj,f,indent=2,ensure_ascii=False); f.write("\n")
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def task(game, domain, severity):
    gid=game["game_id"]; away=game["away"]; home=game["home"]
    model_context={}
    if domain=="starting_goalies": model_context=game.get("goalies",{})
    elif domain in ("lines_and_scratches","power_play","penalty_kill","expected_toi_and_role"):
        model_context={"players":game.get("players",{})}
    elif domain=="projection_integrity":
        model_context={"warnings":game.get("integrity_warnings",[])}
    return {
        "task_id":f"{gid}:{domain}",
        "game_id":gid,"away":away,"home":home,
        "gate":game.get("gate","EARLY"),"domain":domain,"severity":severity,
        "status":"PENDING",
        "question": {
            "starting_goalies": f"Verify expected/confirmed starting goalies for {away} at {home}.",
            "lines_and_scratches": f"Verify current lines, scratches, and material lineup changes for {away} at {home}.",
            "injuries_and_returns": f"Check material injuries, returns, illness, maintenance, and availability for {away} and {home}.",
            "power_play": f"Verify PP1/PP2 personnel and material unit changes for {away} and {home}.",
            "penalty_kill": f"Verify material PK personnel/unit changes for {away} and {home}.",
            "expected_toi_and_role": f"Check material TOI or role restrictions/changes for projected players in {away} at {home}.",
            "rest_travel_schedule": f"Check rest, back-to-back, travel, and schedule context for {away} at {home}.",
            "coach_player_media": f"Find material pregame coach/player/team comments for {away} at {home}.",
            "market": f"Capture current moneyline/total context and material movement for {away} at {home}.",
            "situational": f"Check other material situational context for {away} at {home}.",
        }[domain],
        "model_context":model_context,
        "research_rules":{
            "do_not_mutate_model":True,
            "daily_faceoff_pull_allowed":False,
            "prefer_sources":["official_team","NHL","credentialed_beat","reputable_news","market_provider"],
            "explicit_unresolved_required":True
        }
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--snapshot",default="intelligence/current/nhl_model_snapshot.json")
    ap.add_argument("--out","--output",dest="out",default="intelligence/current/research_queue.json")
    ap.add_argument("--run-plan",default="intelligence/current/run_plan.json")
    ap.add_argument("--gate",choices=list(GATE_LIMITS))
    args=ap.parse_args()
    snap=load(args.snapshot); tasks=[]
    plan=load(args.run_plan) if os.path.exists(args.run_plan) else {"games":[]}
    plan_by_game={x.get("game_id"):x for x in plan.get("games",[])}
    players=snap.get("players",[])
    severity_by_domain=dict(DOMAINS)
    for g in snap.get("games",[]):
        gp=plan_by_game.get(g.get("game_id"),{})
        gate=args.gate or gp.get("gate") or g.get("gate","EARLY")
        if gate=="PUCK_DROP" or gp.get("freeze") is True: continue
        gg=dict(g); gg["gate"]=gate
        gg["players"]=[p for p in players if p.get("team") in (g.get("away"),g.get("home"))]
        # Snapshot model conflicts are deterministic local-review work and consume no external budget.
        model_conflicts=g.get("conflicts",[]) or []
        if model_conflicts:
            gg["integrity_warnings"]=model_conflicts
            t=task(gg,"projection_integrity","HIGH"); t["status"]="LOCAL_REVIEW"
            t["question"]="Resolve model/data integrity conflicts before treating intelligence as current."
            tasks.append(t)
        allowed=gp.get("domains")
        if allowed is None:
            limit=GATE_LIMITS[gate]
            allowed=[d for d,_ in DOMAINS[:limit]]
        max_items=gp.get("max_external_items",len(allowed))
        added=0
        for domain in allowed:
            if domain not in severity_by_domain or added>=max_items: continue
            tasks.append(task(gg,domain,severity_by_domain[domain])); added+=1
    payload={
        "schema_version":"1.0","generated_at":now(),"slate_date":snap.get("slate_date"),
        "snapshot_generated_at":snap.get("generated_at"),
        "policy":{
            "bounded_research":True,
            "daily_faceoff_independent_pulls":0,
            "queue_is_fact_finding_not_projection_generation":True,
            "reuse_valid_sources":True
        },
        "task_count":len(tasks),"tasks":tasks
    }
    atomic(args.out,payload)
    print(f"Wrote {args.out}: {len(tasks)} tasks")

if __name__=="__main__": main()
