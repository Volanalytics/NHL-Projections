#!/usr/bin/env python3
"""Publish validated NHL Intelligence stage into a local Git checkout.

This script intentionally performs no GitHub API calls. It copies only a previously
validated publish_stage into repository publication paths, verifies hashes first,
and leaves git add/commit/push to the repository's normal authenticated publisher.
"""
import argparse, hashlib, json, shutil
from pathlib import Path

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def atomic_copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_name(dst.name+".tmp")
    shutil.copy2(src,tmp); tmp.replace(dst)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage",default="intelligence/publish_stage")
    ap.add_argument("--repo-root",default=".")
    a=ap.parse_args(); stage=Path(a.stage); root=Path(a.repo_root)
    mf=stage/"publication_manifest.json"
    if not mf.exists(): raise SystemExit("No validated publication_manifest.json.")
    m=json.loads(mf.read_text(encoding="utf-8")); expected=m.get("files",{})
    for name,want in expected.items():
        p=stage/name
        if not p.exists() or digest(p)!=want: raise SystemExit("Hash validation failed: "+name)
    slate=m.get("slate_date")
    if not slate: raise SystemExit("Missing slate_date.")
    # Live page + canonical current artifacts.
    atomic_copy(stage/"intelligence.html",root/"intelligence.html")
    for name in ["nhl_model_snapshot.json","research_queue.json","nhl_intelligence.json","source_ledger.json"]:
        atomic_copy(stage/name,root/"intelligence/current"/name)
    # Immutable archive package.
    archive=root/"intelligence/archive"/slate; archive.mkdir(parents=True,exist_ok=True)
    for p in stage.iterdir():
        if p.is_file(): atomic_copy(p,archive/p.name)
    print("Validated NHL Intelligence package copied into repository publication paths.")
    print("Next: use the repository's authenticated git publisher to add/commit/push changed files.")

if __name__=="__main__": main()
