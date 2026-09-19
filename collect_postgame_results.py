#!/usr/bin/env python3
"""Populate player_results from completed NHL games, safely across partial slates.

Unlike projection_history.fetch_results(), this wrapper tracks completion at the
NHL game-id level. Re-running after later games become final will ingest those
games instead of skipping the whole date merely because earlier games were saved.
"""
import argparse
import sqlite3
import time
from datetime import datetime, timedelta

from projection_history import (
    fetch_box_score_rows, fetch_game_ids, init_history,
)


def stored_game_ids(conn, game_date):
    return {str(r[0]) for r in conn.execute(
        """SELECT DISTINCT nhl_game_id FROM player_results
           WHERE game_date=? AND nhl_game_id IS NOT NULL""",
        (game_date,),
    ).fetchall()}


def collect_date(conn, game_date, delay=0.5, verbose=True):
    final_ids = set(fetch_game_ids(game_date))
    if not final_ids:
        if verbose:
            print(f"  results {game_date}: no completed games found")
        return 0, 0, 0

    stored = stored_game_ids(conn, game_date)
    missing = sorted(final_ids - stored)
    if not missing:
        if verbose:
            print(f"  results {game_date}: {len(final_ids)} completed games already stored")
        return 0, len(final_ids), len(stored)

    rows = []
    successful_games = 0
    for gid in missing:
        try:
            game_rows = fetch_box_score_rows(gid)
            if not game_rows:
                if verbose:
                    print(f"  results {game_date}: game {gid} returned no skater rows")
                continue
            rows.extend(
                (game_date, nk, team, nm, gid, stat, val)
                for nk, team, nm, stat, val in game_rows
            )
            successful_games += 1
        except Exception as ex:
            if verbose:
                print(f"  results {game_date}: game {gid} failed ({ex})")
        time.sleep(delay)

    if rows:
        conn.executemany(
            """INSERT OR REPLACE INTO player_results
               (game_date, name_key, team, player_name, nhl_game_id, stat, actual)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()

    if verbose:
        now_stored = len(stored_game_ids(conn, game_date))
        print(
            f"  results {game_date}: final={len(final_ids)}, "
            f"previously_stored={len(stored)}, fetched={successful_games}, "
            f"stored_now={now_stored}, stat_rows={len(rows)}"
        )
    return len(rows), len(final_ids), len(stored_game_ids(conn, game_date))


def projection_dates(conn):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT slate_date FROM projection_log ORDER BY slate_date"
    ).fetchall()]


def date_range(start, end):
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    d = d0
    while d <= d1:
        yield d.isoformat()
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="game_log_cache.db")
    ap.add_argument("--date", help="One YYYY-MM-DD slate date")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    init_history(conn)

    if args.date:
        dates = [args.date]
    elif args.start or args.end:
        lo = args.start or args.end
        hi = args.end or args.start
        dates = list(date_range(lo, hi))
    else:
        # Recheck every frozen projection date. Game-level filtering below makes
        # this cheap and ensures a partially completed slate is revisited.
        dates = projection_dates(conn)

    total = 0
    for d in dates:
        n, _, _ = collect_date(conn, d, delay=args.delay)
        total += n

    print(f"Inserted/replaced result stat rows: {total}")
    print(
        "Result dates:",
        conn.execute(
            "SELECT COUNT(DISTINCT game_date) FROM player_results"
        ).fetchone()[0],
    )


if __name__ == "__main__":
    main()
