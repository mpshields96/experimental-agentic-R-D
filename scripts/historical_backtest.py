#!/usr/bin/env python3
"""
scripts/historical_backtest.py — RLM signal validator using our existing line_history data.

Since the Odds API historical endpoint requires a premium tier, this script
validates the RLM (Reverse Line Movement) signal component using the movement
data already stored in our line_history.db.

It:
  1. Queries line_history for games with significant line movement (RLM proxy)
  2. Fetches actual game outcomes via free public APIs (nba_api, NHL Stats, ESPN)
  3. Cross-references: did games with sharp movement beat the spread?

Free result sources (0 Odds API credits):
  NBA    → nba_api ScoreboardV3 (official NBA stats API, no key)
  NHL    → api-web.nhle.com/v1/score/{date} (official NHL API, no key)
  NCAAB  → site.api.espn.com (unofficial ESPN API, no key)
  NFL    → site.api.espn.com (unofficial ESPN API, no key)
  Other  → ESPN if mappable, else movement-only report

Usage:
    python3 scripts/historical_backtest.py [--sport NBA] [--min-movement 2.0]
    python3 scripts/historical_backtest.py --all-sports

SAFETY: Read-only. Does NOT write to any DB. Does NOT call Odds API.
Cost: 0 API credits.
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.path.expanduser("~/ClaudeCode/agentic-rd-sandbox/data/line_history.db")

# ESPN API sport path mapping (sport key → ESPN path segment)
ESPN_SPORT_MAP = {
    "NHL":   "hockey/nhl",
    "NFL":   "football/nfl",
    "MLB":   "baseball/mlb",
    "NCAAB": "basketball/mens-college-basketball",
    "NCAAF": "football/college-football",
    "MLS":   "soccer/usa.1",
}


# ---------------------------------------------------------------------------
# Line history queries
# ---------------------------------------------------------------------------

def get_moved_lines(sport: str, min_movement: float = 1.5) -> list[dict]:
    """
    Query line_history for spread lines that moved >= min_movement pts.
    Returns list of dicts with event/movement info.
    """
    import sqlite3
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT event_id, matchup, sport, market_type, team,
                   commence_time, open_line, current_line, movement_delta,
                   open_price, current_price, n_snapshots, first_seen
              FROM line_history
             WHERE sport = ?
               AND market_type IN ('spreads', 'spread')
               AND ABS(movement_delta) >= ?
             ORDER BY ABS(movement_delta) DESC
            """,
            (sport, min_movement),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_line_history(sport: str) -> list[dict]:
    """Return all line_history rows for a sport."""
    import sqlite3
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM line_history WHERE sport = ?", (sport,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_sports_in_db() -> list[str]:
    """Return distinct sports stored in line_history.db."""
    import sqlite3
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT sport FROM line_history ORDER BY sport"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Result lookups — one per data source
# ---------------------------------------------------------------------------

def get_nba_game_result(event_id: str, matchup: str, game_date_str: str) -> dict:
    """
    Fetch NBA result via nba_api ScoreboardV3. Most reliable for NBA.
    Returns dict with: away_team, home_team, away_pts, home_pts, winner, margin.
    """
    try:
        from nba_api.stats.endpoints import scoreboardv3
        sb = scoreboardv3.ScoreboardV3(game_date=game_date_str, league_id="00")
        raw = sb.get_dict()
        games = raw.get("scoreboard", {}).get("games", [])
        if not games:
            return {}
        parts = matchup.replace(" vs ", " @ ").split(" @ ")
        if len(parts) != 2:
            return {}
        away_name = parts[0].strip().lower()
        home_name = parts[1].strip().lower()
        for g in games:
            home = g.get("homeTeam", {})
            away = g.get("awayTeam", {})
            h_full = f"{home.get('teamCity','').lower()} {home.get('teamName','').lower()}"
            a_full = f"{away.get('teamCity','').lower()} {away.get('teamName','').lower()}"
            if (home_name in h_full or h_full in home_name) and \
               (away_name in a_full or a_full in away_name):
                h_score = home.get("score")
                a_score = away.get("score")
                if h_score is None or a_score is None or (h_score == 0 and a_score == 0):
                    return {}
                return {
                    "away_team": away.get("teamTricode", ""),
                    "home_team": home.get("teamTricode", ""),
                    "away_pts": int(a_score),
                    "home_pts": int(h_score),
                    "winner": home.get("teamTricode") if int(h_score) > int(a_score)
                              else away.get("teamTricode"),
                    "margin": int(abs(int(h_score) - int(a_score))),
                }
        return {}
    except Exception as exc:
        logger.debug("nba_api error for %s: %s", matchup, exc)
        return {}


def get_nhl_game_result(matchup: str, game_date_str: str) -> dict:
    """
    Fetch NHL result via official NHL Stats API (api-web.nhle.com). Free, no key.
    Endpoint: GET /v1/score/{YYYY-MM-DD}
    """
    try:
        url = f"https://api-web.nhle.com/v1/score/{game_date_str}"
        req = urllib.request.Request(url, headers={"User-Agent": "titanium-backtest/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)

        parts = matchup.replace(" vs ", " @ ").split(" @ ")
        if len(parts) != 2:
            return {}
        away_name = parts[0].strip().lower()
        home_name = parts[1].strip().lower()

        for g in data.get("games", []):
            if g.get("gameState") not in ("FINAL", "OFF"):
                continue
            home = g.get("homeTeam", {})
            away = g.get("awayTeam", {})
            h_abbr = home.get("abbrev", "")
            a_abbr = away.get("abbrev", "")
            # NHL API commonName is nested: {"default": "Maple Leafs"}
            h_common = home.get("commonName", {}).get("default", "").lower()
            a_common = away.get("commonName", {}).get("default", "").lower()

            h_match = home_name in h_common or h_common in home_name or \
                      home_name in h_abbr.lower()
            a_match = away_name in a_common or a_common in away_name or \
                      away_name in a_abbr.lower()

            if h_match and a_match:
                h_score = int(home.get("score", 0))
                a_score = int(away.get("score", 0))
                return {
                    "away_team": a_abbr,
                    "home_team": h_abbr,
                    "away_pts": a_score,
                    "home_pts": h_score,
                    "winner": h_abbr if h_score > a_score else a_abbr,
                    "margin": abs(h_score - a_score),
                }
        return {}
    except Exception as exc:
        logger.debug("NHL API error for %s: %s", matchup, exc)
        return {}


def get_espn_game_result(sport_espn_path: str, matchup: str, game_date_str: str) -> dict:
    """
    Fetch game result via ESPN unofficial API. Covers NFL, NCAAB, NCAAF, MLB, MLS.
    Endpoint: https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard?dates={YYYYMMDD}
    """
    try:
        date_compact = game_date_str.replace("-", "")
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{sport_espn_path}/scoreboard?dates={date_compact}&limit=100"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "titanium-backtest/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)

        parts = matchup.replace(" vs ", " @ ").split(" @ ")
        if len(parts) != 2:
            return {}
        away_name = parts[0].strip().lower()
        home_name = parts[1].strip().lower()

        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                if not comp.get("status", {}).get("type", {}).get("completed", False):
                    continue
                competitors = comp.get("competitors", [])
                home_comp = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away_comp = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home_comp or not away_comp:
                    continue
                h_name = home_comp.get("team", {}).get("displayName", "").lower()
                a_name = away_comp.get("team", {}).get("displayName", "").lower()
                h_abbr = home_comp.get("team", {}).get("abbreviation", "")
                a_abbr = away_comp.get("team", {}).get("abbreviation", "")

                h_match = home_name in h_name or h_name in home_name or \
                          home_name in h_abbr.lower()
                a_match = away_name in a_name or a_name in away_name or \
                          away_name in a_abbr.lower()

                if h_match and a_match:
                    h_score = int(home_comp.get("score", 0))
                    a_score = int(away_comp.get("score", 0))
                    return {
                        "away_team": a_abbr,
                        "home_team": h_abbr,
                        "away_pts": a_score,
                        "home_pts": h_score,
                        "winner": h_abbr if h_score > a_score else a_abbr,
                        "margin": abs(h_score - a_score),
                    }
        return {}
    except Exception as exc:
        logger.debug("ESPN API error (%s) for %s: %s", sport_espn_path, matchup, exc)
        return {}


def fetch_result(sport: str, event_id: str, matchup: str, game_date_str: str) -> dict:
    """Route result lookup to the correct free API for the given sport."""
    if not game_date_str:
        return {}
    sport_upper = sport.upper()
    if sport_upper == "NBA":
        return get_nba_game_result(event_id, matchup, game_date_str)
    if sport_upper == "NHL":
        return get_nhl_game_result(matchup, game_date_str)
    espn_path = ESPN_SPORT_MAP.get(sport_upper)
    if espn_path:
        return get_espn_game_result(espn_path, matchup, game_date_str)
    return {}


def result_source_label(sport: str) -> str:
    sport_upper = sport.upper()
    if sport_upper == "NBA":
        return "nba_api (official)"
    if sport_upper == "NHL":
        return "NHL Stats API (official)"
    if sport_upper in ESPN_SPORT_MAP:
        return "ESPN unofficial API"
    return "none (movement-only report)"


# ---------------------------------------------------------------------------
# Spread cover check — shared across sports
# ---------------------------------------------------------------------------

def check_spread_cover(result: dict, team: str, line: float) -> str:
    """
    Check if 'team' covered 'line' given the game result.
    Returns: 'cover' | 'no_cover' | 'push' | 'unknown'
    """
    if not result:
        return "unknown"
    away_pts = result.get("away_pts", 0)
    home_pts = result.get("home_pts", 0)
    away_team = result.get("away_team", "")
    home_team = result.get("home_team", "")

    team_abbr = team.split("(")[0].strip()
    is_home = any(t.lower() in home_team.lower() or home_team.lower() in t.lower()
                  for t in [team, team_abbr])
    is_away = any(t.lower() in away_team.lower() or away_team.lower() in t.lower()
                  for t in [team, team_abbr])

    if not is_home and not is_away:
        return "unknown"

    team_pts = home_pts if is_home else away_pts
    opp_pts  = away_pts if is_home else home_pts

    net = team_pts - opp_pts + line
    if net > 0:
        return "cover"
    elif net < 0:
        return "no_cover"
    else:
        return "push"


# ---------------------------------------------------------------------------
# Per-sport audit
# ---------------------------------------------------------------------------

def audit_sport(sport: str, min_movement: float, verbose: bool = True) -> dict:
    """
    Run RLM validation for a single sport.
    Returns summary dict: {sport, events, moved_lines, covers, no_covers, unknowns, cover_rate}.
    """
    sport_upper = sport.upper()

    all_rows = get_all_line_history(sport_upper)
    events_total = len({r["event_id"] for r in all_rows})
    moved = get_moved_lines(sport_upper, min_movement)

    if verbose:
        print(f"\n{'='*65}")
        print(f"  {sport_upper}  —  {result_source_label(sport_upper)}")
        print(f"{'='*65}")
        print(f"  Events tracked:   {events_total}")
        print(f"  Total rows:       {len(all_rows)}")
        if all_rows:
            dates = sorted(r["first_seen"][:10] for r in all_rows if r.get("first_seen"))
            print(f"  Date range:       {dates[0] if dates else 'N/A'} → {dates[-1] if dates else 'N/A'}")

        if not moved:
            print(f"\n  No spread lines moved >= {min_movement} pts  (data may be < 24h old)")
            return {
                "sport": sport_upper, "events": events_total,
                "moved_lines": 0, "covers": 0, "no_covers": 0,
                "unknowns": 0, "cover_rate": None,
            }

        print(f"\n  Lines moved >= {min_movement} pts: {len(moved)}\n")

    by_event: dict[str, list[dict]] = {}
    for r in moved:
        by_event.setdefault(r["event_id"], []).append(r)

    covers = no_covers = unknowns = 0
    for event_id, rows in by_event.items():
        sample = rows[0]
        matchup = sample.get("matchup", "?")
        commence = sample.get("commence_time", "")
        game_date = commence[:10] if commence else ""

        if verbose:
            print(f"  {matchup} ({game_date})")
            for r in rows:
                delta = r["movement_delta"]
                direction = "→ FAVORITE" if delta < 0 else "→ DOG"
                print(f"    {r['team']:35s} {r['open_line']:+.1f} → {r['current_line']:+.1f} "
                      f"(Δ{delta:+.1f}) {direction}")

        result = fetch_result(sport_upper, event_id, matchup, game_date)
        if result:
            if verbose:
                print(f"    Result: {result['away_team']} {result['away_pts']} @ "
                      f"{result['home_team']} {result['home_pts']}")
            for r in rows:
                cover = check_spread_cover(result, r["team"], r["current_line"])
                if verbose:
                    print(f"      {r['team'][:28]:28s} @ {r['current_line']:+.1f} → {cover.upper()}")
                if cover == "cover":
                    covers += 1
                elif cover == "no_cover":
                    no_covers += 1
                else:
                    unknowns += 1
        else:
            if verbose:
                source = result_source_label(sport_upper)
                print(f"    (No result via {source})")
            unknowns += len(rows)

        if verbose:
            print()

    total_rated = covers + no_covers
    cover_rate = covers / total_rated * 100 if total_rated > 0 else None

    if verbose:
        print(f"  {'─'*50}")
        if total_rated > 0:
            print(f"  Covers: {covers}  No covers: {no_covers}  Unknowns: {unknowns}")
            print(f"  Cover rate (rated): {cover_rate:.1f}%")
            if cover_rate >= 55:
                print("  ✅ Signal appears valid (>55% cover rate)")
            elif total_rated < 10:
                print("  ⚠️  Insufficient sample (< 10 rated) — collect more data")
            else:
                print("  ⚠️  Below 55% — signal may need calibration")
        else:
            print("  No results available (games may be in future or API unavailable)")

    return {
        "sport": sport_upper,
        "events": events_total,
        "moved_lines": len(moved),
        "covers": covers,
        "no_covers": no_covers,
        "unknowns": unknowns,
        "cover_rate": cover_rate,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RLM signal validator — uses existing line_history data, 0 Odds API credits"
    )
    parser.add_argument("--sport", default=None, help="Sport to analyze (default: NBA)")
    parser.add_argument("--all-sports", action="store_true",
                        help="Analyze all sports found in line_history.db")
    parser.add_argument("--min-movement", type=float, default=1.5,
                        help="Min spread movement (pts) to include (default: 1.5)")
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"TITANIUM — RLM SIGNAL VALIDATOR")
    print(f"Threshold: >= {args.min_movement} pts movement | Cost: 0 API credits")
    print(f"{'='*65}")

    if not os.path.exists(DB_PATH):
        print(f"\nERROR: line_history.db not found at {DB_PATH}")
        print("Run the app for at least one poll cycle to populate line history.")
        sys.exit(1)

    if args.all_sports:
        sports = get_all_sports_in_db()
        if not sports:
            print("\nNo data in line_history.db yet.")
            sys.exit(0)
        print(f"\nSports in DB: {', '.join(sports)}")
        summaries = [audit_sport(s, args.min_movement, verbose=True) for s in sports]
        # Cross-sport summary
        print(f"\n{'='*65}")
        print(f"  CROSS-SPORT SUMMARY")
        print(f"{'='*65}")
        print(f"  {'Sport':<10}  {'Events':>7}  {'Moved':>7}  {'Covers':>7}  "
              f"{'No Cov':>7}  {'Rate':>8}")
        print(f"  {'─'*60}")
        for s in summaries:
            rate_s = f"{s['cover_rate']:.1f}%" if s['cover_rate'] is not None else "N/A"
            print(f"  {s['sport']:<10}  {s['events']:>7}  {s['moved_lines']:>7}  "
                  f"{s['covers']:>7}  {s['no_covers']:>7}  {rate_s:>8}")
        print(f"\n  NOTE: Cover rate ≥ 55% on ≥ 10 rated bets = valid RLM signal")
    else:
        sport = (args.sport or "NBA").upper()
        audit_sport(sport, args.min_movement, verbose=True)
        print(f"\n  NOTE: Use --all-sports to audit every sport in line_history.db")

    print()
    print(f"  This validates the RLM line-movement component only.")
    print(f"  Full model validation requires accumulating paper bets (auto-scan).")
    print(f"  Re-run as more games resolve to increase sample size.")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
