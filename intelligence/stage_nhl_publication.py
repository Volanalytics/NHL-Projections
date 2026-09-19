#!/usr/bin/env python3
"""Stage/archive NHL Intelligence artifacts for atomic GitHub publication.
Git operations remain in the existing repository publisher; this script only prepares
a validated publication directory and never destroys last-known-good output.
"""
import argparse, hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path

REQUIRED=["nhl_model_snapshot.json","research_queue.json","nhl_intelligence.json","source_ledger.json"]

def sha256(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--current",default="intelligence/current")
    ap.add_argument("--html",default="intelligence.html")
    ap.add_argument("--archive-root",default="intelligence/archive")
    ap.add_argument("--stage",default="intelligence/publish_stage")
    a=ap.parse_args()
    cur=Path(a.current); hp=Path(a.html)
    missing=[x for x in REQUIRED if not (cur/x).exists()]
    if not hp.exists(): missing.append(a.html)
    if missing: raise SystemExit("Publication blocked; missing: "+", ".join(missing))
    intel=json.loads((cur/"nhl_intelligence.json").read_text(encoding="utf-8"))
    if intel.get("compiler",{}).get("projection_values_mutated") is not False:
        raise SystemExit("Publication blocked: projection immutability assertion missing/failed.")
    slate=intel.get("slate_date")
    if not slate: raise SystemExit("Publication blocked: slate_date missing.")
    stage=Path(a.stage); tmp=stage.with_name(stage.name+"_tmp")
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    files={}
    for name in REQUIRED:
        src=cur/name; shutil.copy2(src,tmp/name); files[name]=sha256(src)
    shutil.copy2(hp,tmp/"intelligence.html"); files["intelligence.html"]=sha256(hp)
    manifest={"schema_version":"1.0","slate_date":slate,"staged_at":datetime.now(timezone.utc).isoformat(),
              "projection_values_immutable":True,"files":files}
    (tmp/"publication_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    if stage.exists(): shutil.rmtree(stage)
    tmp.replace(stage)
    archive=Path(a.archive_root)/slate
    archive.mkdir(parents=True,exist_ok=True)
    for p in stage.iterdir(): shutil.copy2(p,archive/p.name)
    print(f"Validated/staged {len(files)} artifacts; archived -> {archive}")

if __name__=="__main__": main()
