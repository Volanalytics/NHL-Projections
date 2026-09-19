#!/usr/bin/env python3
"""NHL Intelligence production orchestrator. Executes deterministic stages only.
External research is a separate bounded step; use --incoming-research when results exist.
"""
import argparse,subprocess,sys
from pathlib import Path

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
