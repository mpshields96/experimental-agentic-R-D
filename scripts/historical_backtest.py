#!/usr/bin/env python3
"""
scripts/historical_backtest.py — RLM signal validator using our existing line_history data.

Since the Odds API historical endpoint requires a premium tier, this script
validates the RLM (Reverse Line Movement) signal component using the movement
data already stored in our line_history.db.

It:
  1. Queries line_history for games with significant line movement (RLM proxy)
  2. Fetches actual game outcomes via nba_api (free, no key needed)
  3. Cross-references: did games with sharp movement beat the spread?

This validates the key premise: "sharp money moves lines toward the right side."

Usage:
    python3 scripts/historical_backtest.py [--sport NBA] [--min-movement 2.0]

SAFETY: Read-only. Does NOT write to any DB. Does NOT call Odds API.
Cost: 0 API credits.
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Line history query
# ---------------------------------------------------------------------------

def get_moved_lines(sport: str, min_movement: float = 1.5) -> list[dict]:
    """
    Query line_history for spread lines that moved >= min_movement pts.
    These are candidates for RLM validation.

    Returns list of dicts with: event_id, matchup, market_type, team,
    commence_time, open_line, current_line, movement_delta, n_snapshots.
    """
    import sqlite3
    db_path = os.path.expanduser("~/ClaudeCode/agentic-rd-sandbox/data/line_history.db")
    if not os.path.exists(db_path):
        print(f"ERROR: DB not found at {db_path}")
        return []

    conn = sqlite3.connect(db_path)
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
    """Return all line_history rows for a sport (for summary statistics)."""
    import sqlite3
    db_path = os.path.expanduser("~/ClaudeCode/agentic-rd-sandbox/data/line_history.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM line_history WHERE sport = ?", (sport,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# NBA result lookup
# ---------------------------------------------------------------------------

def get_nba_game_result(event_id: str, matchup: str, game_date_str: str) -> dict:
    """
    Attempt to fetch actual NBA game result via nba_api scoreboard.
    Returns dict with keys: home_team, away_team, home_pts, away_pts, winner, spread_result.
    Returns {} if game not found or not yet played.
    """
    try:
        from nba_api.stats.endpoints import scoreboardv3

        sb = scoreboardv3.ScoreboardV3(game_date=game_date_str, league_id="00")
        raw = sb.get_dict()
        games = raw.get("scoreboard", {}).get("games", [])
        if not games:
            return {}

        # Parse matchup: "{away} @ {home}"
        parts = matchup.replace(" vs ", " @ ").split(" @ ")
        if len(parts) != 2:
            return {}
        away_name, home_name = parts[0].strip().lower(), parts[1].strip().lower()

        for g in games:
            home = g.get("homeTeam", {})
            away = g.get("awayTeam", {})
            h_name = home.get("teamName", "").lower()
            a_name = away.get("teamName", "").lower()
            h_city = home.get("teamCity", "").lower()
            a_city = away.get("teamCity", "").lower()

            home_full = f"{h_city} {h_name}"
            away_full = f"{a_city} {a_name}"

            if (home_name in home_full or home_full in home_name) and \
               (away_name in away_full or away_full in away_name):
                h_score = home.get("score")
                a_score = away.get("score")
                if h_score is None or a_score is None or (h_score == 0 and a_score == 0):
                    return {}  # Not yet played
                h_abbr = home.get("teamTricode", "")
                a_abbr = away.get("teamTricode", "")
                return {
                    "away_team": a_abbr,
                    "home_team": h_abbr,
                    "away_pts": int(a_score),
                    "home_pts": int(h_score),
                    "winner": h_abbr if int(h_score) > int(a_score) else a_abbr,
                    "margin": int(abs(int(h_score) - int(a_score))),
                }
        return {}
    except Exception as exc:
        logger.debug("nba_api error for %s: %s", matchup, exc)
        return {}


# ---------------------------------------------------------------------------
# RLM spread cover check
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

    # Determine if team is home or away by abbreviation
    team_abbr = team.split("(")[0].strip()  # strip any extra info
    is_home = any(t.lower() in home_team.lower() or home_team.lower() in t.lower()
                  for t in [team, team_abbr])
    is_away = any(t.lower() in away_team.lower() or away_team.lower() in t.lower()
                  for t in [team, team_abbr])

    if not is_home and not is_away:
        return "unknown"

    if is_home:
        team_pts = home_pts
        opp_pts = away_pts
    else:
        team_pts = away_pts
        opp_pts = home_pts

    # Spread is from team's perspective (negative = team is favored)
    net = team_pts - opp_pts + line
    if net > 0:
        return "cover"
    elif net < 0:
        return "no_cover"
    else:
        return "push"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RLM signal validator — uses existing line_history data")
    parser.add_argument("--sport", default="NBA", help="Sport (default: NBA)")
    parser.add_argument("--min-movement", type=float, default=1.5,
                        help="Min line movement (pts) to flag as RLM signal (default: 1.5)")
    args = parser.parse_args()
    sport = args.sport.upper()

    print(f"\n{'='*60}")
    print(f"TITANIUM RLM SIGNAL VALIDATOR — {sport}")
    print(f"Min movement threshold: {args.min_movement} pts")
    print(f"Data source: local line_history.db (0 API credits)")
    print(f"{'='*60}\n")

    # --- Summary of all data ---
    all_rows = get_all_line_history(sport)
    if not all_rows:
        print(f"No {sport} data in line_history.db. App may not have been running yet.")
        return

    events = {}
    for r in all_rows:
        events.setdefault(r["event_id"], r)

    print(f"Line history data:")
    print(f"  Events tracked:  {len(events)}")
    print(f"  Total rows:      {len(all_rows)}")
    if all_rows:
        dates = sorted(r["first_seen"][:10] for r in all_rows if r.get("first_seen"))
        print(f"  Date range:      {dates[0] if dates else 'N/A'} → {dates[-1] if dates else 'N/A'}")
    print()

    # --- Find moved lines ---
    moved = get_moved_lines(sport, args.min_movement)
    if not moved:
        print(f"No spread lines moved >= {args.min_movement} pts in {sport} line_history.")
        print("  This is expected if the app was running for < 24 hours before games.")
        print("  RLM fires on 2nd fetch after 3% implied prob shift (separate mechanism).")
        return

    print(f"Lines moved >= {args.min_movement} pts: {len(moved)} entries")
    print()

    # Group by event
    by_event: dict[str, list[dict]] = {}
    for r in moved:
        by_event.setdefault(r["event_id"], []).append(r)

    covers = 0
    no_covers = 0
    unknowns = 0

    for event_id, rows in by_event.items():
        sample = rows[0]
        matchup = sample.get("matchup", "?")
        commence = sample.get("commence_time", "")
        game_date = commence[:10] if commence else ""

        print(f"  {matchup} ({game_date})")
        for r in rows:
            delta = r["movement_delta"]
            direction = "→ FAVORITE" if delta < 0 else "→ DOG"
            print(f"    {r['team']:35s} {r['open_line']:+.1f} → {r['current_line']:+.1f} "
                  f"(Δ{delta:+.1f}) {direction}")

        # Try to get result
        if game_date and sport == "NBA":
            result = get_nba_game_result(event_id, matchup, game_date)
            if result:
                print(f"    Result: {result['away_team']} {result['away_pts']} @ "
                      f"{result['home_team']} {result['home_pts']}")
                for r in rows:
                    cover = check_spread_cover(result, r["team"], r["current_line"])
                    print(f"      {r['team'][:25]:25s} @ {r['current_line']:+.1f} → {cover.upper()}")
                    if cover == "cover":
                        covers += 1
                    elif cover == "no_cover":
                        no_covers += 1
                    else:
                        unknowns += 1
            else:
                print("    (Result not available via nba_api — game may be in future)")
                unknowns += len(rows)
        print()

    print(f"{'='*60}")
    print(f"SIGNAL VALIDATION SUMMARY")
    print(f"{'='*60}")
    total_rated = covers + no_covers
    if total_rated > 0:
        cover_rate = covers / total_rated * 100
        print(f"Moved lines: {len(moved)}")
        print(f"  Covers:    {covers}")
        print(f"  No covers: {no_covers}")
        print(f"  Unknowns:  {unknowns}")
        print(f"  Cover rate (rated only): {cover_rate:.1f}%")
        print()
        if cover_rate >= 55:
            print("✅ RLM signal appears valid: moved lines covered at >55%")
        elif total_rated < 10:
            print("⚠️  Insufficient sample (< 10 rated bets) — collect more data")
        else:
            print("⚠️  Cover rate below 55% — signal may need calibration")
    else:
        print("No results available yet (games may be in future or nba_api unavailable).")
        print()
        print("INTERPRETATION:")
        print("  The line_history data shows how much lines moved, but game results")
        print("  are not yet available for recent games. As more games resolve,")
        print("  re-run this script to validate the RLM signal component.")
    print(f"\n  NOTE: This validates only the RLM line-movement component.")
    print(f"  Full model validation (consensus edge + sharp score) requires")
    print(f"  accumulating paper bets via the auto-scan (resets March 1 UTC).")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
