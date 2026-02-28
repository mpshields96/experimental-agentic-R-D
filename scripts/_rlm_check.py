#!/usr/bin/env python3
"""Quick RLM check — runs inline, no args needed."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nba_api.stats.endpoints import scoreboardv3
import sqlite3

db_path = os.path.expanduser("~/ClaudeCode/agentic-rd-sandbox/data/line_history.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT DISTINCT event_id, matchup, commence_time,
           MAX(ABS(movement_delta)) as max_move
      FROM line_history
     WHERE sport='NBA' AND market_type='spread'
     GROUP BY event_id
     HAVING max_move >= 3.0
     ORDER BY max_move DESC
     LIMIT 20
""").fetchall()

# Also get the spread rows for each event
spread_rows = {}
for r in rows:
    s = conn.execute(
        "SELECT team, open_line, current_line, movement_delta FROM line_history "
        "WHERE event_id=? AND market_type='spread' ORDER BY ABS(movement_delta) DESC",
        (r['event_id'],)
    ).fetchall()
    spread_rows[r['event_id']] = [dict(sr) for sr in s]

conn.close()

print(f"\nGames with spread movement >= 3pts: {len(rows)}\n")
covers, no_covers, unknowns = 0, 0, 0

for r in rows:
    matchup = r['matchup']
    date = r['commence_time'][:10]
    max_move = r['max_move']

    try:
        sb = scoreboardv3.ScoreboardV3(game_date=date, league_id='00')
        raw = sb.get_dict()
        games = raw.get('scoreboard', {}).get('games', [])
    except Exception as e:
        games = []

    parts = matchup.split(' @ ')
    if len(parts) != 2:
        unknowns += 1
        continue
    away_name, home_name = parts[0].lower(), parts[1].lower()

    found_result = None
    for g in games:
        home = g.get('homeTeam', {})
        away_t = g.get('awayTeam', {})
        h_full = f"{home.get('teamCity','')} {home.get('teamName','')}".lower()
        a_full = f"{away_t.get('teamCity','')} {away_t.get('teamName','')}".lower()
        if (away_name in a_full or a_full in away_name) and (home_name in h_full or h_full in home_name):
            h_score = int(home.get('score') or 0)
            a_score = int(away_t.get('score') or 0)
            if h_score or a_score:
                found_result = {
                    'home': home.get('teamTricode'), 'away': away_t.get('teamTricode'),
                    'h_pts': h_score, 'a_pts': a_score
                }
            break

    print(f"  {matchup} [{date}] max_move={max_move:.1f}pts")
    for sr in spread_rows.get(r['event_id'], []):
        direction = "FAV-move" if sr['movement_delta'] < 0 else "DOG-move"
        print(f"    {sr['team'][:30]:30s} {sr['open_line']:+.1f}→{sr['current_line']:+.1f} "
              f"(Δ{sr['movement_delta']:+.1f}) {direction}")

    if found_result:
        fr = found_result
        print(f"    RESULT: {fr['away']} {fr['a_pts']} @ {fr['home']} {fr['h_pts']}")
        # Check: did the line move toward the correct winner?
        margin = fr['h_pts'] - fr['a_pts']
        for sr in spread_rows.get(r['event_id'], []):
            covered = (sr['movement_delta'] < 0 and margin > abs(sr['current_line'])) or \
                      (sr['movement_delta'] > 0 and -margin > abs(sr['current_line']))
            # Simpler: just check if favored team (negative line after move) won ATS
            line = sr['current_line']
            # This team covers if: their score + line > opponent's score
            # But we need to know if team is home/away
            # Skip detailed ATS for now, just show
        covers += 1
    else:
        print("    (Result not yet available)")
        unknowns += 1
    print()

print(f"Results found: {covers} | Unknown: {unknowns}")
