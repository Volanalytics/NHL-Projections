#!/usr/bin/env python3
"""NHL Intelligence production orchestrator. Executes deterministic stages only.
External research is a separate bounded step; use --incoming-research when results exist.
"""
import argparse,json,subprocess,sys
from pathlib import Path

def ensure_slate_file(path, slate_date, root_key):
    p=Path(path)
    try:
        obj=json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        obj={}
    if obj.get("slate_date") != slate_date:
        obj={"schema_version":"1.0","slate_date":slate_date,root_key:[]}
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")

def run(cmd):
    print("+"," ".join(map(str,cmd))); subprocess.run(cmd,check=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--python",default=sys.executable)
    ap.add_argument("--incoming-research")
    ap.add_argument("--publish-stage",action="store_true")
    a=ap.parse_args();py=a.python
    snap="intelligence/current/nhl_model_snapshot.json"
    if not Path(snap).exists():raise SystemExit("Missing snapshot: "+snap)
    snapshot=json.loads(Path(snap).read_text(encoding="utf-8"))
    slate_date=snapshot.get("slate_date")
    if not slate_date: raise SystemExit("Snapshot missing slate_date")
    # Never carry research evidence from a different slate into this cycle.
    ensure_slate_file("intelligence/current/research_results.json",slate_date,"results")
    ensure_slate_file("intelligence/current/source_ledger.json",slate_date,"sources")
    run([py,"intelligence/resolve_nhl_gate.py","--snapshot",snap])
    run([py,"intelligence/build_nhl_research_queue.py","--snapshot",snap,"--output","intelligence/current/research_queue.json"])
    if a.incoming_research:
        run([py,"intelligence/nhl_research_executor.py","--queue","intelligence/current/research_queue.json",
             "--incoming",a.incoming_research,"--results","intelligence/current/research_results.json",
             "--ledger","intelligence/current/source_ledger.json"])
    run([py,"intelligence/compile_nhl_intelligence.py","--snapshot",snap,
         "--results","intelligence/current/research_results.json","--ledger","intelligence/current/source_ledger.json",
         "--output","intelligence/current/nhl_intelligence.json"])
    run([py,"intelligence/render_nhl_intelligence.py","--input","intelligence/current/nhl_intelligence.json","--output","intelligence.html"])
    if a.publish_stage: run([py,"intelligence/stage_nhl_publication.py"])
    print("NHL Intelligence deterministic cycle complete.")
if __name__=="__main__":main()
