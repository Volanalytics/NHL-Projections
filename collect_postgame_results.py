#!/usr/bin/env python3
"""Populate projection_history.player_results from completed NHL games.

Uses the existing projection_history schema and collector. By default it only
checks dates that already have frozen projection_log rows but no results.
Safe to run repeatedly.
"""
import argparse,sqlite3
from projection_history import init_history,fetch_results

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",default="game_log_cache.db")
    ap.add_argument("--date",help="One YYYY-MM-DD slate date")
    ap.add_argument("--start");ap.add_argument("--end")
    ap.add_argument("--delay",type=float,default=.5)
    a=ap.parse_args()
    c=sqlite3.connect(a.db);c.row_factory=sqlite3.Row;init_history(c)
    if a.date:
        dates=[a.date]
    elif a.start or a.end:
        lo=a.start or a.end;hi=a.end or a.start;dates=None
    else:
        dates=[r[0] for r in c.execute("""SELECT DISTINCT p.slate_date
          FROM projection_log p LEFT JOIN player_results r
          ON r.game_date=p.slate_date WHERE r.game_date IS NULL
          ORDER BY p.slate_date""")]
    total=0
    if dates is None:
        total=fetch_results(c,lo,hi,delay=a.delay)
    else:
        for d in dates: total+=fetch_results(c,d,d,delay=a.delay)
    print(f"Inserted/replaced result stat rows: {total}")
    print("Result dates:",c.execute("SELECT COUNT(DISTINCT game_date) FROM player_results").fetchone()[0])

if __name__=="__main__":main()
