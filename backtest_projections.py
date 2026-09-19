#!/usr/bin/env python3
"""Score frozen NHL projections and report result/matching coverage.

Read-only: never mutates projection_log or player_results.
"""
import argparse,csv,math,sqlite3
from collections import Counter

STATS=("SOG","G","A","BLK","PIM")
WINDOWS=("FS","L20","L10")
DEFAULT_BLENDS={"FS":(1,0,0),"L20":(0,1,0),"L10":(0,0,1),
"70/20/10":(.70,.20,.10),"60/25/15":(.60,.25,.15),
"50/30/20":(.50,.30,.20),"40/35/25":(.40,.35,.25)}

def date_filter(alias,start,end):
    wh=[];args=[]
    if start: wh.append(f"{alias}.slate_date>=?");args.append(start)
    if end: wh.append(f"{alias}.slate_date<=?");args.append(end)
    return ((" WHERE "+" AND ".join(wh)) if wh else ""),args

def coverage(conn,start=None,end=None):
    where,args=date_filter("l",start,end)
    projections=[dict(x) for x in conn.execute(f"""SELECT l.slate_date,l.player_id,
      l.name_key,l.player_name,l.team,l.stat,l.window FROM projection_log l
      {where} ORDER BY l.slate_date,l.player_name,l.stat,l.window""",args)]
    result_dates={r[0] for r in conn.execute("SELECT DISTINCT game_date FROM player_results")}
    player_keys={(r["slate_date"],r["player_id"]) for r in projections}
    stat_keys={(r["slate_date"],r["player_id"],r["stat"]) for r in projections if r["stat"] in STATS}
    matched=set()
    for r in conn.execute(f"""SELECT DISTINCT l.slate_date,l.player_id,l.stat
      FROM projection_log l JOIN player_results x
      ON x.game_date=l.slate_date AND x.name_key=l.name_key AND x.stat=l.stat
      {where}""",args):
        if r["stat"] in STATS: matched.add((r["slate_date"],r["player_id"],r["stat"]))
    eligible={k for k in stat_keys if k[0] in result_dates}
    missing=sorted(eligible-matched)
    return projections,player_keys,stat_keys,eligible,matched,missing,result_dates

def load_rows(conn,start=None,end=None):
    where,args=date_filter("l",start,end)
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
    es=[]
    for c in cases:
        if not all(w in c for w in WINDOWS): continue
        p=sum(weights[i]*c[w] for i,w in enumerate(WINDOWS));es.append(p-c["actual"])
    if not es:return None
    return len(es),sum(map(abs,es))/len(es),math.sqrt(sum(e*e for e in es)/len(es)),sum(es)/len(es)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--db",default="game_log_cache.db")
    ap.add_argument("--start");ap.add_argument("--end");ap.add_argument("--csv",default="")
    ap.add_argument("--missing-csv",default="",help="Write unmatched eligible player/stat keys")
    a=ap.parse_args()
    conn=sqlite3.connect(a.db);conn.row_factory=sqlite3.Row
    projections,players,stats,eligible,matched,missing,result_dates=coverage(conn,a.start,a.end)
    print("COVERAGE")
    print(f"  Frozen players:          {len(players)}")
    print(f"  Frozen player/stats:     {len(stats)}")
    print(f"  Result dates available:  {len(result_dates)}")
    print(f"  Eligible player/stats:   {len(eligible)}")
    print(f"  Matched player/stats:    {len(matched & eligible)}")
    pct=(100*len(matched & eligible)/len(eligible)) if eligible else 0
    print(f"  Match coverage:          {pct:.1f}%")
    print(f"  Unmatched player/stats:  {len(missing)}")
    if missing:
        print("  Missing by stat:         "+", ".join(f"{k}={v}" for k,v in sorted(Counter(x[2] for x in missing).items())))
        lookup={(r["slate_date"],r["player_id"],r["stat"]):r for r in projections}
        print("  First unmatched:")
        for k in missing[:10]:
            r=lookup[k];print(f"    {k[0]} | {r['player_name']} | {r['team']} | {k[2]} | {r['name_key']}")
    rows=load_rows(conn,a.start,a.end);cases=build_cases(rows)
    dates=sorted({c["slate_date"] for c in cases})
    print(f"\nGraded projection cases: {len(cases)} | slates: {len(dates)}")
    if dates: print(f"Date range: {dates[0]} to {dates[-1]}")
    print("\nstat  model         n       MAE      RMSE      bias");print("-"*57)
    output=[]
    for stat in STATS:
        sc=[c for c in cases if c["stat"]==stat]
        for name,w in DEFAULT_BLENDS.items():
            m=metric(sc,w)
            if not m: continue
            n,mae,rmse,bias=m;output.append((stat,name,n,mae,rmse,bias))
            print(f"{stat:<5} {name:<10} {n:>6} {mae:>9.4f} {rmse:>9.4f} {bias:>9.4f}")
        print()
    if a.csv:
        with open(a.csv,"w",newline="",encoding="utf-8") as f:
            z=csv.writer(f);z.writerow(["stat","model","n","mae","rmse","bias"]);z.writerows(output)
        print("Wrote",a.csv)
    if a.missing_csv and missing:
        lookup={(r["slate_date"],r["player_id"],r["stat"]):r for r in projections}
        with open(a.missing_csv,"w",newline="",encoding="utf-8") as f:
            z=csv.writer(f);z.writerow(["slate_date","player_id","player_name","team","name_key","stat"])
            for k in missing:
                r=lookup[k];z.writerow([k[0],k[1],r["player_name"],r["team"],r["name_key"],k[2]])
        print("Wrote",a.missing_csv)
    if not cases: print("No graded rows yet. Coverage above shows whether results are absent or matching failed.")

if __name__=="__main__":main()
