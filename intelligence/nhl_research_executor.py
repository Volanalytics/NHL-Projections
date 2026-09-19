#!/usr/bin/env python3
"""Validate/merge externally researched NHL findings without spending on its own.
The actual web/API research provider is intentionally decoupled from this file.
This keeps source provenance explicit and prevents accidental unbounded API use.
"""

import argparse,json
from datetime import datetime,timezone
from pathlib import Path

VALID_STATUS={"CONFIRMED","UNRESOLVED","CONFLICT","EXHAUSTED"}
VALID_SEVERITY={"INFO","LOW","MEDIUM","HIGH","CRITICAL"}
VALID_EFFECT={"NONE","CONFLICT","REPROJECTION_REQUIRED"}

def load(p,default=None):
    p=Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def write(p,o):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(o,indent=2)+"\n",encoding="utf-8");t.replace(p)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--queue",default="intelligence/current/research_queue.json")
    ap.add_argument("--incoming",required=True,help="Provider-produced JSON results file")
    ap.add_argument("--results",default="intelligence/current/research_results.json")
    ap.add_argument("--ledger",default="intelligence/current/source_ledger.json")
    a=ap.parse_args()
    q=load(a.queue); incoming=load(a.incoming)
    if not q: raise SystemExit("Research queue missing.")
    allowed={x["queue_id"]:x for x in q.get("items",[])}
    accepted=[]; sources={}
    for r in incoming.get("results",[]):
        qid=r.get("queue_id")
        if qid not in allowed: raise SystemExit("Result not present in bounded queue: "+str(qid))
        if r.get("status") not in VALID_STATUS: raise SystemExit("Bad status: "+str(r.get("status")))
        if r.get("severity","INFO") not in VALID_SEVERITY: raise SystemExit("Bad severity")
        if r.get("model_effect","NONE") not in VALID_EFFECT: raise SystemExit("Bad model_effect")
        if not r.get("source_ids") and r.get("status") in ("CONFIRMED","CONFLICT"):
            raise SystemExit("Confirmed/conflict finding requires source_ids: "+qid)
        r["game_id"]=allowed[qid]["game_id"];r["domain"]=allowed[qid]["domain"];accepted.append(r)
    for s in incoming.get("sources",[]):
        sid=s.get("source_id")
        if not sid or not s.get("url") or not s.get("retrieved_at"): raise SystemExit("Source requires source_id/url/retrieved_at")
        sources[sid]=s
    for r in accepted:
        for sid in r.get("source_ids",[]):
            if sid not in sources: raise SystemExit("Missing source ledger record: "+sid)
    now=datetime.now(timezone.utc).isoformat()
    write(a.results,{"schema_version":"1.0","generated_at":now,"slate_date":q.get("slate_date"),"results":accepted})
    write(a.ledger,{"schema_version":"1.0","generated_at":now,"sources":list(sources.values())})
    print(f"Accepted {len(accepted)} bounded findings and {len(sources)} sources.")

if __name__=="__main__": main()
