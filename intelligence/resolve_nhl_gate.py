#!/usr/bin/env python3
"""Resolve NHL Intelligence gates from puck-drop times and build a bounded run plan."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo=None

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def parse_dt(v,tz):
    if not v:return None
    s=str(v).strip().replace("Z","+00:00")
    try:d=datetime.fromisoformat(s)
    except ValueError:return None
    if d.tzinfo is None:d=d.replace(tzinfo=tz)
    return d.astimezone(timezone.utc)

def gate(minutes):
    if minutes<=0:return "PUCK_DROP"
    if minutes<=30:return "T-30"
    if minutes<=90:return "T-90"
    if minutes<=12*60:return "GAME_DAY"
    return "EARLY"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--snapshot",default="intelligence/current/nhl_model_snapshot.json")
    ap.add_argument("--policy",default="intelligence/research_policy_v1.0.json")
    ap.add_argument("--output",default="intelligence/current/run_plan.json")
    ap.add_argument("--timezone",default="America/Chicago")
    a=ap.parse_args();snap=load(a.snapshot);pol=load(a.policy)
    tz=ZoneInfo(a.timezone) if ZoneInfo else timezone.utc;now=datetime.now(timezone.utc);games=[]
    for g in snap.get("games",[]):
        pd=parse_dt(g.get("puck_drop"),tz)
        mins=(pd-now).total_seconds()/60 if pd else None
        gt=gate(mins) if mins is not None else "GAME_DAY"
        cfg=pol["gates"][gt]
        games.append({"game_id":g.get("game_id"),"puck_drop":g.get("puck_drop"),
          "minutes_to_puck_drop":None if mins is None else round(mins,1),"gate":gt,
          "freeze":gt=="PUCK_DROP","domains":cfg["domains"],
          "max_external_items":cfg["max_external_items"],"reuse_hours":cfg["reuse_hours"]})
    rank={"T-30":4,"T-90":3,"GAME_DAY":2,"EARLY":1,"PUCK_DROP":0}
    active=[x for x in games if not x["freeze"]]
    highest=max(active,key=lambda x:rank[x["gate"]])["gate"] if active else "PUCK_DROP"
    out={"schema_version":"1.0","generated_at":now.isoformat(),"slate_date":snap.get("slate_date"),
      "highest_active_gate":highest,"games":games}
    p=Path(a.output);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(".tmp");t.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8");t.replace(p)
    print("Highest active gate:",highest);print("Run plan:",p)
if __name__=="__main__":main()
