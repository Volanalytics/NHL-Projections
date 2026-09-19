#!/usr/bin/env python3
"""Score frozen NHL player projections against stored NHL box-score results.

Read-only: this never mutates projection_log or player_results.
Designed for honest out-of-sample calibration of FS/L20/L10 and simple blends.
"""
import argparse,csv,math,sqlite3
from collections import defaultdict

STATS=("SOG","G","A","BLK","PIM")
DEFAULT_BLENDS={"FS":(1,0,0),"L20":(0,1,0),"L10":(0,0,1),
"70/20/10":(.70,.20,.10),"60/25/15":(.60,.25,.15),
"50/30/20":(.50,.30,.20),"40/35/25":(.40,.35,.25)}

def load_rows(conn,start=None,end=None):
    wh=[];args=[]
    if start: wh.append("l.slate_date>=?");args.append(start)
    if end: wh.append("l.slate_date<=?");args.append(end)
    where=("WHERE "+" AND ".join(wh)) if wh else ""
    q=f"""SELECT l.slate_date,l.player_id,l.name_key,l.player_name,l.team,l.opponent,
      l.home_away,l.window,l.stat,l.projected,r.actual
      FROM projection_log l JOIN player_results r
      ON r.game_date=l.slate_date AND r.name_key=l.name_key AND r.stat=l.stat
      {where} ORDER BY l.slate_date,l.player_id,l.stat,l.window"""
    return [dict(x) for x in conn.execute(q,args)]

def build_cases(rows):
    d={}
    for r in rows:
        if r["stat"] not in STATS: continue
        k=(r["slate_date"],r["player_id"],r["stat"])
        c=d.setdefault(k,{x:r[x] for x in ("slate_date","player_id","name_key","player_name","team","opponent","home_away","stat")})
        c["actual"]=float(r["actual"]);c[r["window"]]=float(r["projected"])
    return list(d.values())

def metric(cases,weights):
    errs=[];ses=[];bias=[];n=0
    for c in cases:
        if not all(w in c for w in ("FS","L20","L10")): continue
        p=sum(weights[i]*c[w] for i,w in enumerate(("FS","L20","L10")))
        e=p-c["actual"];errs.append(abs(e));ses.append(e*e);bias.append(e);n+=1
    if not n:return None
    return n,sum(errs)/n,math.sqrt(sum(ses)/n),sum(bias)/n

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",default="game_log_cache.db")
    ap.add_argument("--start");ap.add_argument("--end")
    ap.add_argument("--csv",default="")
    a=ap.parse_args()
    conn=sqlite3.connect(a.db);conn.row_factory=sqlite3.Row
    rows=load_rows(conn,a.start,a.end);cases=build_cases(rows)
    dates=sorted({c["slate_date"] for c in cases})
    print(f"Graded projection cases: {len(cases)} | slates: {len(dates)}")
    if dates: print(f"Date range: {dates[0]} to {dates[-1]}")
    print("\nstat  model         n       MAE      RMSE      bias")
    print("-"*57)
    output=[]
    for stat in STATS:
        sc=[c for c in cases if c["stat"]==stat]
        for name,w in DEFAULT_BLENDS.items():
            m=metric(sc,w)
            if not m: continue
            n,mae,rmse,bias=m
            output.append((stat,name,n,mae,rmse,bias))
            print(f"{stat:<5} {name:<10} {n:>6} {mae:>9.4f} {rmse:>9.4f} {bias:>9.4f}")
        print()
    if a.csv:
        with open(a.csv,"w",newline="",encoding="utf-8") as f:
            z=csv.writer(f);z.writerow(["stat","model","n","mae","rmse","bias"]);z.writerows(output)
        print("Wrote",a.csv)
    if not cases:
        print("No graded rows. Confirm projection_log contains pre-puck snapshots and player_results contains completed-game box scores.")

if __name__=="__main__":main()
