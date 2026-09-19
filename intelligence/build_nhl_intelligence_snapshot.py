"""
build_nhl_intelligence_snapshot.py

Read-only bridge from the Google Sheets NHL projection model into the
canonical NHL Intelligence workflow.

It deliberately does NOT scrape Daily Faceoff, Natural Stat Trick, or
change any model cell. It reads computed VALUES from the existing Sheets
output tabs through sheet_source.py and writes a frozen JSON snapshot.

Usage:
    python build_nhl_intelligence_snapshot.py
    python build_nhl_intelligence_snapshot.py --out intelligence/current/nhl_model_snapshot.json

Prerequisites:
    config.json contains google_sheet_id and service_account_json_path.
"""

import argparse
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

from config import load_config
from sheets_client import SheetsClient
import sheet_source as ss

TABS = ["Projections", "Game_Summary", "Matchup", "Lineups"]
WINDOWS = ("FS", "L20", "L10")


def txt(v):
    return "" if v is None else str(v).strip()


def rows_as_dicts(rows):
    rows = ss._pad(rows)
    if len(rows) < 2:
        return []
    hdr = [txt(x) for x in rows[0]]
    return [{hdr[i]: r[i] for i in range(min(len(hdr), len(r)))}
            for r in rows[1:] if any(txt(x) for x in r)]


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".nhl_snapshot_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def lineup_integrity(lineup_rows):
    by_team = defaultdict(lambda: {
        "rows": 0, "skaters": 0, "goalies": 0, "no_id": 0,
        "pp1": 0, "pp2": 0, "pk1": 0, "pk2": 0,
        "starting_goalie_flags": []
    })
    ids = defaultdict(list)

    for r in lineup_rows:
        team = txt(r.get("Team")).upper()
        name = txt(r.get("Player_Name"))
        if not team or not name:
            continue
        d = by_team[team]
        d["rows"] += 1
        pos = txt(r.get("Position")).upper()
        if pos == "G":
            d["goalies"] += 1
        else:
            d["skaters"] += 1

        pid = txt(r.get("NST_PlayerID")).split(".")[0]
        if not pid:
            d["no_id"] += 1
        else:
            ids[pid].append({"name": name, "team": team})

        pp = txt(r.get("PP_Unit"))
        pk = txt(r.get("PK_Unit"))
        if pp == "1": d["pp1"] += 1
        if pp == "2": d["pp2"] += 1
        if pk == "1": d["pk1"] += 1
        if pk == "2": d["pk2"] += 1

        if pos == "G" and txt(r.get("Starting_Goalie_Flag")).upper() == "Y":
            d["starting_goalie_flags"].append(name)

    dupes = {pid: vals for pid, vals in ids.items() if len(vals) > 1}
    warnings = []
    for team, d in sorted(by_team.items()):
        if d["skaters"] < 18:
            warnings.append(f"{team}: only {d['skaters']} skaters in Lineups")
        if d["no_id"]:
            warnings.append(f"{team}: {d['no_id']} lineup rows missing NST_PlayerID")
        if len(set(d["starting_goalie_flags"])) != 1:
            warnings.append(
                f"{team}: starting goalie unresolved "
                f"({len(set(d['starting_goalie_flags']))} distinct flagged goalies)"
            )
    if dupes:
        warnings.append(f"{len(dupes)} NST_PlayerID values appear more than once in Lineups")

    return dict(by_team), dupes, warnings


def projection_integrity(players):
    ids = Counter(p["player_id"] for p in players if p.get("player_id"))
    dupes = {pid: n for pid, n in ids.items() if n > 1}
    zero_rows = []
    for p in players:
        vals = [p["proj"][w][s] for w in WINDOWS for s in ss.STATS]
        if vals and all(v == 0 for v in vals):
            zero_rows.append({"player_id": p["player_id"], "name": p["name"], "team": p["team"]})
    return dupes, zero_rows


def game_id(date, away, home):
    safe_date = (date or "unknown").replace("/", "-").replace(" ", "_")
    return f"{safe_date}_{away}_{home}"


def build_games(paired, players):
    players_by_game_team = defaultdict(list)
    for p in players:
        key = (p.get("team", ""), p.get("opp", ""))
        players_by_game_team[key].append(p)

    games = []
    for g in paired:
        home = g.get("home")
        away = g.get("away")
        if not home or not away:
            # An incomplete pair is an integrity condition, not a game we can
            # safely invent a home/away side for.
            continue

        home_team, away_team = home["team"], away["team"]
        date = home.get("date") or away.get("date") or ""
        hp = players_by_game_team[(home_team, away_team)]
        ap = players_by_game_team[(away_team, home_team)]

        # Game_Summary is opponent-centric for goalie context:
        # home row's opp_goalie = away goalie; away row's opp_goalie = home goalie.
        home_goalie = away.get("opp_goalie", "")
        away_goalie = home.get("opp_goalie", "")

        model = {}
        for w in WINDOWS:
            model[w] = {
                "home_goals": home["proj"][w]["G"],
                "away_goals": away["proj"][w]["G"],
                "total": home["proj"][w]["G"] + away["proj"][w]["G"],
                "home_sog": home["proj"][w]["SOG"],
                "away_sog": away["proj"][w]["SOG"],
            }

        game_warnings = []
        if not home_goalie:
            game_warnings.append(f"{home_team}: model starting goalie unresolved")
        if not away_goalie:
            game_warnings.append(f"{away_team}: model starting goalie unresolved")
        if not hp:
            game_warnings.append(f"{home_team}: no projected players found")
        if not ap:
            game_warnings.append(f"{away_team}: no projected players found")

        games.append({
            "game_id": game_id(date, away_team, home_team),
            "date": date,
            "away": away_team,
            "home": home_team,
            "gate": "EARLY",
            "state": "UNRESOLVED" if game_warnings else "BASELINE",
            "model": model,
            "goalies": {
                "away": {"model_name": away_goalie, "status": "PROJECTED" if away_goalie else "UNKNOWN"},
                "home": {"model_name": home_goalie, "status": "PROJECTED" if home_goalie else "UNKNOWN"},
            },
            "matchup": {
                "away": {
                    "opp_ca60": away.get("opp_ca60"),
                    "opp_hdca60": away.get("opp_hdca60"),
                    "opp_goalie_sv_fs": away.get("opp_sv"),
                    "opp_goalie_hdsv_fs": away.get("opp_hdsv"),
                    "shot_adj": away.get("shot_adj"),
                    "goalie_adj": away.get("goalie_adj"),
                },
                "home": {
                    "opp_ca60": home.get("opp_ca60"),
                    "opp_hdca60": home.get("opp_hdca60"),
                    "opp_goalie_sv_fs": home.get("opp_sv"),
                    "opp_goalie_hdsv_fs": home.get("opp_hdsv"),
                    "shot_adj": home.get("shot_adj"),
                    "goalie_adj": home.get("goalie_adj"),
                },
            },
            "players": {"away": ap, "home": hp},
            "lineup_status": "UNRESOLVED" if game_warnings else "CURRENT",
            "special_teams_status": "CURRENT",
            "findings": [],
            "conflicts": [],
            "reprojection_required": False,
            "integrity_warnings": game_warnings,
            "sources": [],
        })
    return games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("intelligence", "current", "nhl_model_snapshot.json"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    sheets = SheetsClient(cfg["google_sheet_id"], cfg["service_account_json_path"])

    if not args.quiet:
        print("Reading Google Sheets model outputs (computed values, not formulas)...")
    tabs = ss.batch_read(sheets, TABS)

    players = ss.load_projections(tabs.get("Projections", []), verbose=not args.quiet)
    team_rows = ss.load_game_summary(tabs.get("Game_Summary", []), verbose=not args.quiet)
    paired = ss.pair_games(team_rows)
    lineup_rows = rows_as_dicts(tabs.get("Lineups", []))

    lineup_by_team, lineup_dupes, lineup_warnings = lineup_integrity(lineup_rows)
    projection_dupes, zero_projection_rows = projection_integrity(players)
    games = build_games(paired, players)

    warnings = list(lineup_warnings)
    if projection_dupes:
        warnings.append(f"{len(projection_dupes)} duplicate NST_PlayerID values in Projections")
    if zero_projection_rows:
        warnings.append(f"{len(zero_projection_rows)} projected player rows are zero across all windows")
    incomplete_pairs = sum(1 for g in paired if not g.get("home") or not g.get("away"))
    if incomplete_pairs:
        warnings.append(f"{incomplete_pairs} Game_Summary entries could not be paired into complete games")

    slate_dates = sorted({g["date"] for g in games if g.get("date")})
    snapshot = {
        "schema_version": "1.0",
        "generated_at": iso_now(),
        "slate_date": slate_dates[0] if len(slate_dates) == 1 else (slate_dates or [""])[0],
        "projection_source": {
            "system": "Google Sheets",
            "spreadsheet_id": cfg.get("google_sheet_id"),
            "snapshot_at": iso_now(),
            "immutable": True,
            "tabs": TABS,
        },
        "pipeline": {
            "dfo": {"status": "WARNING" if lineup_warnings else "OK",
                    "detail": f"{len(lineup_rows)} Lineups rows read; snapshot performs no DFO request"},
            "nst_full_season": {"status": "OK", "detail": "Consumed indirectly through computed model outputs"},
            "rolling_l20_l10": {"status": "OK", "detail": "Consumed indirectly through computed model outputs"},
            "player_matching": {
                "status": "WARNING" if (lineup_dupes or projection_dupes or any(d["no_id"] for d in lineup_by_team.values())) else "OK",
                "detail": f"{len(lineup_dupes)} duplicate lineup IDs; {len(projection_dupes)} duplicate projection IDs",
            },
            "goalie_data": {
                "status": "WARNING" if any("goalie unresolved" in x.lower() for x in warnings) else "OK",
                "detail": "Model goalie names frozen from Game_Summary opponent-goalie context",
            },
            "matchup": {"status": "OK" if team_rows else "ERROR",
                        "detail": f"{len(team_rows)} team-game rows read"},
            "projections": {"status": "WARNING" if (projection_dupes or zero_projection_rows) else "OK",
                            "detail": f"{len(players)} player projection rows read"},
        },
        "integrity": {
            "status": "WARNING" if warnings else "OK",
            "warnings": warnings,
            "lineup_by_team": lineup_by_team,
            "duplicate_lineup_ids": lineup_dupes,
            "duplicate_projection_ids": projection_dupes,
            "zero_projection_rows": zero_projection_rows,
        },
        "games": games,
    }

    atomic_json(args.out, snapshot)
    if not args.quiet:
        print(f"Wrote {args.out}")
        print(f"  games: {len(games)}")
        print(f"  projected players: {len(players)}")
        print(f"  integrity: {snapshot['integrity']['status']} ({len(warnings)} warning(s))")
        print("  External intelligence may compare against this snapshot; it must not mutate it.")


if __name__ == "__main__":
    main()
