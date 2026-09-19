"""Compile NHL research results against an immutable model snapshot."""
import argparse, copy, json, os, tempfile
from datetime import datetime, timezone

MATERIAL = {
 "starting_goalie_change":"REPROJECTION_REQUIRED",
 "projected_player_scratched":"REPROJECTION_REQUIRED",
 "material_line_change":"CONFLICT",
 "material_pp_unit_change":"CONFLICT",
 "material_pk_unit_change":"CONFLICT",
 "player_identity_collision":"REPROJECTION_REQUIRED",
 "missing_player_id_for_projected_player":"CONFLICT",
 "stale_projection_after_material_input_change":"REPROJECTION_REQUIRED",
}
SEV={"INFO":0,"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(p):
    with open(p,encoding="utf-8") as f:return json.load(f)
def maybe(p,default):
    return load(p) if p and os.path.exists(p) else default
def atomic(p,o):
    d=os.path.dirname(os.path.abspath(p));os.makedirs(d,exist_ok=True)
    fd,t=tempfile.mkstemp(prefix=".nhl_intel_",suffix=".json",dir=d)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(o,f,indent=2,ensure_ascii=False);f.write("\n")
        os.replace(t,p)
    except Exception:
        try:os.unlink(t)
        except OSError:pass
        raise

def finding(r):
    return {
      "domain":r["domain"],"status":r.get("status","UNRESOLVED"),
      "severity":r.get("severity","INFO"),"summary":r.get("summary",""),
      "model_value":r.get("model_value"),"observed_value":r.get("observed_value"),
      "source_ids":r.get("source_ids",[])
    }

def derive_state(game):
    if game.get("reprojection_required"): return "REPROJECTION_REQUIRED"
    if game.get("conflicts"): return "CONFLICT"
    fs=game.get("findings",[])
    if not fs:return "UNRESOLVED"
    if any(x["status"] in ("UNRESOLVED","EXHAUSTED","NOT_RESEARCHED") and SEV.get(x["severity"],0)>=2 for x in fs):
        return "UNRESOLVED"
    return "CURRENT"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--snapshot",default="intelligence/current/nhl_model_snapshot.json")
    ap.add_argument("--queue",default="intelligence/current/research_queue.json")
    ap.add_argument("--results",default="intelligence/current/research_results.json")
    ap.add_argument("--ledger",default="intelligence/current/source_ledger.json")
    ap.add_argument("--out","--output",dest="out",default="intelligence/current/nhl_intelligence.json")
    args=ap.parse_args()
    snap=load(args.snapshot);queue=maybe(args.queue,{"tasks":[]});results=maybe(args.results,{"results":[]})
    ledger=maybe(args.ledger,{"sources":[]})
    by_game={}
    for r in results.get("results",[]):
        by_game.setdefault(r.get("game_id"),[]).append(r)
    games=[]
    for src in snap.get("games",[]):
        g=copy.deepcopy(src);g["findings"]=[];g["sources"]=[]
        # Preserve deterministic model/data conflicts from the frozen snapshot.
        g["conflicts"]=copy.deepcopy(src.get("conflicts",[]) or [])
        g["reprojection_required"]=any(bool(x.get("reprojection_required")) or x.get("severity")=="CRITICAL" for x in g["conflicts"])
        for r in by_game.get(g["game_id"],[]):
            f=finding(r);g["findings"].append(f);g["sources"].extend(f["source_ids"])
            ctype=r.get("conflict_type")
            if ctype:
                c=copy.deepcopy(f);c["conflict_type"]=ctype
                c["required_action"]=MATERIAL.get(ctype,"CONFLICT");c["status"]="CONFLICT"
                g["conflicts"].append(c)
                if c["required_action"]=="REPROJECTION_REQUIRED":g["reprojection_required"]=True
            if r.get("domain")=="starting_goalies" and r.get("observed"):
                side=r.get("side")
                if side in ("away","home"):
                    goalie=g["goalies"][side];goalie["observed_name"]=r["observed"]
                    goalie["status"]="CHANGED" if r.get("conflict_type")=="starting_goalie_change" else r.get("goalie_status","CONFIRMED")
        g["sources"]=sorted(set(g["sources"]))
        if any(x["domain"]=="lines_and_scratches" and x["status"]=="CONFLICT" for x in g["findings"]):
            g["lineup_status"]="CONFLICT"
        if any(x["domain"] in ("power_play","penalty_kill") and x["status"]=="CONFLICT" for x in g["findings"]):
            g["special_teams_status"]="CONFLICT"
        g["state"]=derive_state(g);games.append(g)
    completed={r.get("task_id") for r in results.get("results",[]) if r.get("task_id")}
    package={
      "schema_version":"1.0","generated_at":now(),"slate_date":snap.get("slate_date"),
      "projection_source":snap.get("projection_source",{}),"pipeline":snap.get("pipeline",{}),
      "research":{
        "queue_generated_at":queue.get("generated_at"),"tasks":len(queue.get("tasks",[])),
        "completed":len(completed),"pending":max(0,len(queue.get("tasks",[]))-len(completed)),
        "source_count":len(ledger.get("sources",[]))
      },
      "games":games
    }
    atomic(args.out,package)
    print(f"Wrote {args.out}: {len(games)} games")
    print("States:", {s:sum(g["state"]==s for g in games) for s in sorted(set(g["state"] for g in games))})

if __name__=="__main__":main()
