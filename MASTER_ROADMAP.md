# MASTER_ROADMAP.md — Titanium-Agentic Sandbox
## Last updated: Session 14 (efficiency_feed.py + Sharp Score wire-in), 2026-02-19

This is the canonical task backlog for the agentic-rd-sandbox build.
It is maintained by the agent and read at the start of each session.

---

## LEGEND
- ✅ DONE — built, tested, committed
- 🔄 IN PROGRESS — partially built
- 📋 NEXT — highest priority for next session
- ⏳ DEFERRED — blocked on data/gate/live sessions
- 🌐 NEEDS WIFI — requires unblocked network to complete (revisit on good connection)
- ❌ REJECTED — decided against, reason noted

---

## SECTION 1: Core Infrastructure (all ✅)

| Module | Status | Sessions |
|---|---|---|
| core/math_engine.py | ✅ | S1, S11, S14 |
| core/odds_fetcher.py | ✅ | S1 |
| core/line_logger.py | ✅ | S1 |
| core/scheduler.py | ✅ | S2, S10, S11 |
| app.py (Streamlit entry) | ✅ | S2, S10, S11 |
| core/efficiency_feed.py | ✅ | S14 |
| pages/01_live_lines.py | ✅ | S2, S3, S14 |
| pages/02_analysis.py | ✅ | S4 |
| pages/03_line_history.py | ✅ | S2 |
| pages/04_bet_tracker.py | ✅ | S3 |
| pages/05_rd_output.py | ✅ | S5, S8, S9 |
| core/price_history_store.py | ✅ | S8 |
| core/clv_tracker.py | ✅ | S7 |
| core/probe_logger.py | ✅ | S9 |
| RLM fire gate counter | ✅ | S11 |
| Weekly purge scheduler job | ✅ | S10 |
| SYSTEM HEALTH sidebar | ✅ | S10, S11 |

**Test suite: 418/418 passing as of S14**

---

## SECTION 2: Sports Coverage

### Active and Polling
| Sport | Kill Switch | Notes |
|---|---|---|
| NBA | ✅ B2B rest + pace variance | compute_rest_days_from_schedule() |
| NFL | ✅ Wind + backup QB | 15mph/20mph validated thresholds |
| NCAAB | ✅ 3PT reliance + tempo | 40% threshold, away only |
| EPL / Ligue1 / Bundesliga / Serie A / La Liga | ✅ Market drift + dead rubber | h2h + totals only (no spreads on API) |
| MLS | ✅ Same soccer kill | |
| NHL | ✅ Goalie starter detection | nhl_kill_switch() + nhl_data.py + scheduler wired |
| MLB | ⚠️ Collar-only | Season starts Mar 27, 2026 |
| NCAAF | ⚠️ Collar-only | Kill switch deferred |

### Deferred Sports (not yet in SPORT_KEYS)
| Sport | API Key | Blocker | Priority |
|---|---|---|---|
| Tennis (ATP) | tennis_atp | Kill switch needs surface + H2H data | Medium |
| Tennis (WTA) | tennis_wta | Same as ATP | Low |
| College Baseball | baseball_ncaa | Thin line posting, sparse sharp action | Low |

---

## SECTION 3: Kill Switch Backlog

### 3A. NHL Goalie Kill Switch — ✅ COMPLETE (Session 13)
**Trigger**: Backup goalie starting (confirmed starter scratched) → KILL or FLAG

**Data source verified**: NHL Stats API (FREE, public, no key required)
- `api-web.nhle.com/v1/gamecenter/{gameId}/boxscore` — returns `"starter": true/false`
  per goalie once game state moves from FUT to live/in-progress
- `api.nhle.com/stats/rest/en/goalie/summary` — season aggregate stats (GAA, SV%)

**CRITICAL FINDING from research**: The NHL schedule endpoint does NOT have a
`startingGoalies` field for future games (gameState="FUT"). The `"starter": true`
field only populates in the **boxscore** endpoint once the game begins loading
(typically T-60 to T-30 minutes before puck drop when rosters finalize).
Pre-game strategy: poll boxscore at T-60min intervals until starter appears.

**No pre-game free API for goalie starters exists** (confirmed, community-validated):
- DailyFaceoff.com: scrapeable HTML, posts ~2-3h before puck drop (fragile)
- MySportsFeeds: ~$24/mo, cleanest pre-game starter data (paid option)
- NHL API boxscore polling: free but only available T-60min before puck drop

**Kill logic (proposed)**:
```python
def nhl_kill_switch(backup_goalie: bool, b2b: bool = False) -> tuple[bool, str]:
    if backup_goalie:
        return True, "KILL: Backup goalie confirmed — skip unless 12%+ edge"
    if b2b:
        return False, "FLAG: B2B — reduce Kelly 50%"
    return False, ""
```

**Implementation plan**:
1. Add `core/nhl_data.py` — polls `api-web.nhle.com/v1/gamecenter/{id}/boxscore`
   - Map Odds API team names → NHL game IDs via schedule endpoint + team name match
   - Return starter name + confirmed bool; return `None` if not yet populated (FUT state)
   - Poll strategy: scheduler calls this function only when game_start - now < 90 min
2. Add `nhl_kill_switch()` to math_engine.py
3. Wire into scheduler._poll_all_sports() NHL branch — check starter 90min before game
4. Tests: test_nhl_kill_switch + test_nhl_data.py (mock requests, both FUT and LIVE states)

**Quota cost**: ZERO — NHL API is completely free, no key, no quota

**Confirmed working boxscore response structure**:
```json
"goalies": [
  {"playerId": 8481519, "name": {"default": "S. Knight"}, "starter": true, "toi": "59:04"},
  {"playerId": 8482821, "name": {"default": "A. Soderblom"}, "starter": false, "toi": "00:00"}
]
```
Path: `response["playerByGameStats"]["awayTeam"]["goalies"]` and `["homeTeam"]["goalies"]`

---

### 3B. MLB Starting Pitcher Kill/Flag — ⏳ DEFERRED until Apr 1 2026

**Trigger**: Starting pitcher on short rest (< 4 days) or high recent pitch count → FLAG/KILL on run line

**Data source VERIFIED**: MLB Stats API (FREE, public, no key, no rate limits)

**CONFIRMED WORKING endpoints** (directly tested by research agent):

Probable pitcher per game (available days in advance):
```
GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,team
```
Response field: `games[].teams.home.probablePitcher.fullName` and `.id`
Also: `games[].teams.home.probablePitcher` is null when TBD — treat TBD as FLAG condition.

Pitch count + days rest from game log:
```
GET https://statsapi.mlb.com/api/v1/people/{playerId}?hydrate=stats(group=pitching,type=gameLog,season=YYYY)
```
Response: `people[0].stats[0].splits[]` — each start has `stat.numberOfPitches` and `date`
Days rest = today - max(date of starts where gamesStarted==1)

**CONFIRMED field names** (live data verified for multiple pitchers):
- `numberOfPitches` — pitch count per start (range: 62-107 observed)
- `gamesStarted` — 1 for starts, 0 for relief appearances
- `date` — "YYYY-MM-DD" format

**Kill logic (proposed)**:
```python
def mlb_kill_switch(
    pitcher_days_rest: Optional[int],  # None = TBD pitcher
    last_pitch_count: int = 0,
    wind_mph: float = 0.0,
    wind_direction: str = "",          # "out" / "in" / "crosswind"
    market_type: str = "runline"
) -> tuple[bool, str]:
    if pitcher_days_rest is None:
        return False, "FLAG: TBD pitcher — reduce size, require 8%+ edge"
    if pitcher_days_rest <= 1 and market_type == "runline":
        return True, f"KILL: SP on short rest ({pitcher_days_rest}d) — skip run line"
    if last_pitch_count >= 100 and pitcher_days_rest <= 4 and market_type == "runline":
        return False, f"FLAG: High pitch count ({last_pitch_count}) on {pitcher_days_rest}d rest"
    if wind_mph > 15 and wind_direction == "out" and market_type == "total":
        return False, f"FLAG: Wind {wind_mph}mph out — lean over"
    return False, ""
```

**Deferred reason**: Season starts Mar 27 2026. Thresholds need live validation — short
rest and pitch count flags are well-documented (< 3 days rest = significantly worse ERA)
but the 100-pitch threshold should be verified against 2+ weeks of real 2026 game data
before going live. Revisit Apr 1 2026.

**TEAM NAME MATCHING NOTE**: MLB Stats API uses full team names ("Boston Red Sox").
The Odds API uses shortened names ("Red Sox"). Must build a normalization lookup table.
This is the main friction point — both directions needed (MLB→Odds, Odds→MLB).

---

### 3C. Tennis Kill Switch — ⏳ DEFERRED (surface data = $40/mo, decision needed)

**Trigger**: Surface mismatch (player favoured on hard courts playing on clay) → KILL/FLAG

**The Odds API coverage**: tennis_atp and tennis_wta — likely require paid "All Sports" tier.
Covers Grand Slams, ATP 1000, WTA 1000. No surface type in payload (confirmed gap).

**Surface + H2H data source VERIFIED**: api-tennis.com
- `GET /get_players` → per-player seasonal surface stats: `clay_won`, `clay_lost`,
  `hard_won`, `hard_lost`, `grass_won`, `grass_lost` (confirmed from their API schema)
- `GET /get_H2H` → full head-to-head record between any two players
- `GET /get_fixtures` → upcoming matches with player keys + tournament

**Pricing (confirmed from their site)**:
| Plan | Price | Requests/Day |
|---|---|---|
| Trial | FREE | 14 days, all features |
| Starter | $40/month | 8,000 req/day |
| Premium | $60/month | 80,000 req/day |

No permanently free tier. Starter at $40/mo is the minimum for production use.

**Surface inference**: api-tennis.com does not have a "surface" field on fixtures.
You derive it from tournament name: Roland Garros = clay, Wimbledon = grass,
US Open / Australian Open / most Masters = hard. Build a `TOURNAMENT_SURFACE` lookup
dict at deploy time. Maintain manually when new tournaments added.

**Player name matching friction**: The Odds API returns e.g. "N. Djokovic" (abbreviated).
api-tennis.com uses full names. Need a normalization function: last name exact match +
first initial check. Edge case: same last name (e.g. two players named "Williams").

**Kill logic (proposed when funded)**:
```python
def tennis_kill_switch(
    player_surface_winrate: float,  # e.g. 0.42 (clay win%)
    career_winrate: float,          # e.g. 0.65 (overall win%)
    is_favourite: bool,
) -> tuple[bool, str]:
    surface_gap = career_winrate - player_surface_winrate
    if surface_gap > 0.15 and is_favourite:  # favourite is 15%+ worse on this surface
        return True, f"KILL: Surface handicap {surface_gap:.0%} — fade favourite"
    if surface_gap > 0.08 and is_favourite:
        return False, f"FLAG: Surface concern {surface_gap:.0%} — reduce size"
    return False, ""
```

**Decision gate**: Tennis is viable IF:
1. User confirms they want tennis on their API plan (Odds API tier upgrade if needed)
2. User approves api-tennis.com $40/mo Starter OR 14-day trial for evaluation
3. Kill switch + player matching code built before adding to ACTIVE_SPORTS

**DO NOT add tennis_atp/tennis_wta to SPORT_KEYS until both gates are cleared.**

---

### 3D. NBA Home/Road B2B Differentiation — ⏳ DEFERRED

**Gap identified**: Current NBA kill fires on B2B rest disadvantage regardless of
home/road. Research shows road B2B is measurably worse (57% ATS loss vs ~52% home B2B).

**Proposed**: Add `is_home_b2b: bool` parameter to `nba_kill_switch()`. Kill spread
bets on road B2B, FLAG only on home B2B (Kelly -50%).

**Blocked on**: Enough live home/road B2B data to validate threshold. Deferred until
10+ B2B instances logged in line_history.db across live sessions.

---

### 3E. NCAAB Conference Strength Filter — ⏳ DEFERRED

**Gap**: Current 3PT kill has no conference vs non-conference differentiation.
High-3PT team on the road in a conference game vs non-con blowout are very different.

**Deferred**: No validated threshold. Low priority vs other kills.

---

## SECTION 4: UI / Analysis Backlog

### 4A. CLV vs Edge% Scatter — ⏳ DEFERRED (gate: 10+ graded bets)
- Analysis page Panel ③
- Needs: both `edge_pct` and `clv_pct` populated in graded bets
- Build when: Check bet tracker — if ≥10 graded bets, build the scatter

### 4B. NBA Home/Road B2B Badge in Live Lines — ⏳ DEFERRED
- Surface home vs road B2B label in bet card UI
- Depends on 3D above

### 4C. MLB Pitcher Display in Live Lines — ⏳ DEFERRED
- Show starting pitcher name + days rest in bet card
- Depends on 3B above and season start

---

## SECTION 5: System Integrity Gates

### 5A. SHARP_THRESHOLD Raise (45 → 50)
- **Gate**: RLM fire count ≥ 20 (sidebar shows RAISE READY)
- **Action**: Manual — change `SHARP_THRESHOLD = 45` to `50` in math_engine.py
- **Current**: 0 confirmed fires (in-memory counter, resets on restart)
- **DO NOT automate** — Math > automation

### 5B. Origination Method (Pinnacle anchor)
- **Gate**: probe_log.json shows `pinnacle_present: True` in 3+ consecutive sessions
- **Current**: pinnacle_present = False consistently
- **Action when gate met**: Add Pinnacle to PREFERRED_BOOKS, weight consensus higher
- **DO NOT implement** until Pinnacle confirmed present

### 5C. CLV Verdict Gate
- **Gate**: ≥ 30 graded bets in clv_log.csv (CLV_GATE constant)
- **Current**: 0 entries (no graded bets yet)
- **Action when gate met**: Review verdict — STRONG / MARGINAL / NO EDGE

---

## SECTION 6: Deferred / Rejected

| Item | Decision | Reason |
|---|---|---|
| College Baseball | ❌ REJECTED | Confirmed: `probablePitcher` not populated for sportId=22. Thin bookmaker coverage (2-3 max). No sharp action. Do not add. |
| Tennis WTA | ⏳ DEFERRED | Surface data gap, lower sharp action than ATP |
| Auto-raise SHARP_THRESHOLD | ❌ REJECTED | Math > automation — must be human decision |
| Pinnacle origination | ⏳ DEFERRED | Pinnacle not present on current API tier |
| Player props | ❌ REJECTED | 422 on bulk endpoint confirmed Feb 2026 |

---

## SECTION 7: WIFI-BLOCKED TASKS (revisit on good network)

These tasks require unblocked network access. Hospital/restricted wifi may block
sports APIs or Reddit. Complete these on next unrestricted session.

**Research status (completed 2026-02-19)**: Background agent directly tested all
major endpoints. Key corrections to prior assumptions documented below.

| # | Task | Status | What to do |
|---|---|---|---|
| W1 | NHL API goalie field | ✅ RESOLVED | `startingGoalies` does NOT exist in schedule endpoint for future games. Use boxscore polling at T-60min. Field confirmed: `playerByGameStats.awayTeam.goalies[n].starter` |
| W2 | MLB Stats API pitcher | ✅ RESOLVED | `probablePitcher` confirmed. Endpoint: `schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,team`. Field path: `games[].teams.home.probablePitcher.fullName`. Days rest via `people/{id}?hydrate=stats(group=pitching,type=gameLog)` → `stat.numberOfPitches` + `date` |
| W3 | Tennis API tier | ✅ RESOLVED | Called `/v4/sports/` with live key (S14). 83 sports returned. `tennis_atp_qatar_open` (active=True) and `tennis_wta_dubai` (active=True) confirmed. Tennis IS on current tier. |
| W4 | Reddit r/algobetting | ✅ PARTIAL | CAPTCHA-blocked for full browse. Community consensus confirmed via search previews: no free pre-game goalie API exists, DailyFaceoff scraping is the common workaround |
| W5 | Build core/nhl_data.py | 📋 READY TO BUILD | Endpoint structure confirmed. Implement: boxscore polling, team name normalization, starter detection. See Section 3A for full spec. |
| W6 | Tennis tier confirmation | ✅ RESOLVED | S14: tennis_atp + tennis_wta both active on current API tier. No upgrade needed. |

---

## SECTION 8: Session Summary

| Session | Key Deliverable | Tests |
|---|---|---|
| S1 | math_engine, odds_fetcher, line_logger | 154 |
| S2 | scheduler, app.py, live_lines, line_history | 180 |
| S3 | bet_tracker, Log Bet button | 180 |
| S4 | analysis page (6 panels) | 180 |
| S5 | rd_output page (7 panels) | 180 |
| S6 | Context sync + push (Sessions 1-5) | 180 |
| S7 | CLV tracker, Pinnacle probe | 226 |
| S8 | price_history_store (RLM 2.0) | 262 |
| S9 | probe_logger, scheduler probe wire-in | 298 |
| S10 | Sidebar health dashboard, weekly purge | 302 |
| S11 | RLM fire gate counter, DB path fix | 314 |
| S12 | Sports coverage audit, research gaps | 314 |
| S13 | NHL kill switch: nhl_data.py + nhl_kill_switch() + scheduler wire-in | 363 |
| S14 | efficiency_feed.py (250+ teams, 10 leagues) + Sharp Score wire-in + W6 resolved | 418 |

---

## SECTION 9: Next Session Checklist (Session 15)

**efficiency_feed.py complete. 418/418 tests passing. W6 resolved (tennis on current tier).**

Priority order:
1. **SYSTEM GATES CHECK** (always first):
   - RLM gate sidebar: if fire_count ≥ 20, manually raise SHARP_THRESHOLD 45→50
   - Bet tracker: if ≥10 graded bets, build CLV vs edge% scatter (Analysis ③, item 4A)
2. **Tennis kill switch** (Section 3C):
   - W6 RESOLVED: tennis_atp/tennis_wta are on current API tier. No upgrade needed.
   - Gate remaining: user decision on api-tennis.com $40/mo Starter plan for surface data.
   - If user approves: build surface lookup dict, player name normalizer, `tennis_kill_switch()`,
     add `tennis_atp`/`tennis_wta` to SPORT_KEYS in odds_fetcher.
   - If user declines: continue monitoring, defer to future session.
3. **3D. NBA Home/Road B2B Differentiation** — gate: 10+ B2B instances in DB.
   - If gate met: add `is_home_b2b` param to `nba_kill_switch()`.
4. **MLB kill switch** — HOLD until Apr 1 gate. No live 2026 data yet.

**Do NOT add tennis to SPORT_KEYS until kill switch is built AND user approves api-tennis.com.**
**Do NOT build NBA B2B diff without 10+ confirmed B2B instances in DB.**

---
*Generated by agent. Update this file at the end of each session.*
