# MASTER_ROADMAP.md — Titanium-Agentic Sandbox
## Last updated: Session 12, 2026-02-19

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
| core/math_engine.py | ✅ | S1, S11 |
| core/odds_fetcher.py | ✅ | S1 |
| core/line_logger.py | ✅ | S1 |
| core/scheduler.py | ✅ | S2, S10, S11 |
| app.py (Streamlit entry) | ✅ | S2, S10, S11 |
| pages/01_live_lines.py | ✅ | S2, S3 |
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

**Test suite: 314/314 passing as of S12**

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
| NHL | ⚠️ Collar-only | Kill switch deferred pending goalie data |
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

### 3A. NHL Goalie Kill Switch — 📋 NEXT (high value)
**Trigger**: Confirmed starting goalie scratch (backup starting) → KILL or FLAG

**Data source found**: NHL Stats API (FREE, public, no key required)
- Base: `https://api.nhle.com/stats/rest/en/`
- Schedule: `https://api-web.nhle.com/v1/schedule/now` → returns today's games with starting goalies
- Goalie stats: `https://api.nhle.com/stats/rest/en/goalie/summary`
- The schedule endpoint returns `startingGoalies` per game when available (announced ~1-2h pregame)

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
1. Add `core/nhl_data.py` — thin wrapper for NHL API schedule fetch
2. Add `nhl_kill_switch()` to math_engine.py
3. Wire into scheduler._poll_all_sports() for NHL sport — call before log_snapshot
4. Add tests: test_nhl_kill_switch + test_nhl_data.py (mock requests)

**🌐 NEEDS WIFI**: Verify `api-web.nhle.com/v1/schedule/now` returns `startingGoalies`
field structure before writing the parser. Hospital wifi may block nhle.com.
- Verify endpoint: `https://api-web.nhle.com/v1/schedule/now`
- Confirm field path to starting goalie name
- Note: Schedule announces goalies ~60-90min pregame, not always available

**Quota cost**: ZERO — NHL API is completely free, no key, no quota

---

### 3B. MLB Starting Pitcher Kill/Flag — ⏳ DEFERRED until Apr 1 2026

**Trigger**: Starting pitcher on short rest (< 4 days) → FLAG or KILL on run line

**Data source found**: MLB Stats API (FREE, public, no key required)
- Endpoint: `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD`
- Returns: `games[].gameData.teams.home.pitchers` / `.away.pitchers` (probable pitcher)
- Also: `https://statsapi.mlb.com/api/v1/people/{id}/stats?stats=pitching` for days rest

**Kill logic (proposed)**:
```python
def mlb_kill_switch(
    pitcher_days_rest: int,       # 0-1 = short rest; 4+ = normal
    wind_mph: float = 0.0,        # Wind out = favours over
    wind_direction: str = "",     # "out" / "in" / "crosswind"
    market_type: str = "runline"
) -> tuple[bool, str]:
    if pitcher_days_rest <= 1 and market_type == "runline":
        return True, f"KILL: SP on short rest ({pitcher_days_rest}d) — skip run line"
    if wind_mph > 15 and wind_direction == "out" and market_type == "total":
        return False, f"FLAG: Wind {wind_mph}mph out — lean over"
    return False, ""
```

**Deferred reason**: Season doesn't start until Mar 27 2026. No live pitcher data to
validate thresholds against. Revisit April 1 with 1 week of real games.

**🌐 NEEDS WIFI**: Verify MLB API endpoint is accessible and pitcher field structure.

---

### 3C. Tennis Kill Switch — ⏳ DEFERRED (needs surface data source)

**Trigger**: Surface mismatch (player with poor clay record playing on clay) → FLAG

**The Odds API coverage**: tennis_atp and tennis_wta are supported on ALL tiers.
Grand Slams + ATP/WTA 1000 events covered.

**Gap**: The Odds API does NOT provide surface type per match.
Options found:
1. Tennis Abstract (public data, no API): tennisabstract.com — surface stats per player
2. RapidAPI tennis endpoints: some provide surface + H2H but paid ($10-50/mo)
3. ATP/WTA official sites: surface listed in tournament schedule but no structured API

**Kill logic (proposed when data available)**:
```python
def tennis_kill_switch(
    player_surface_winrate: float,  # career win% on current surface
    career_winrate: float,          # overall career win%
    is_favourite: bool,
) -> tuple[bool, str]:
    surface_gap = career_winrate - player_surface_winrate
    if surface_gap > 0.15 and is_favourite:  # 15% worse on surface = fade favourite
        return True, f"KILL: Surface handicap {surface_gap:.0%} — fade favourite"
    return False, ""
```

**Action needed**:
- Confirm tennis_atp is in our API tier (add to SPORT_KEYS + MARKETS when ready)
- Find a free/cheap surface data source — Tennis Abstract scrape or RapidAPI
- Add 2 sports to ACTIVE_SPORTS only after kill switch is built

**🌐 NEEDS WIFI**: Check The Odds API sports list for tennis tier requirement.
Check RapidAPI tennis endpoints for pricing.

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
| College Baseball | ⏳ DEFERRED | Thin line posting, sparse sharp action, low ROI |
| Tennis WTA | ⏳ DEFERRED | Surface data gap, lower sharp action than ATP |
| Auto-raise SHARP_THRESHOLD | ❌ REJECTED | Math > automation — must be human decision |
| Pinnacle origination | ⏳ DEFERRED | Pinnacle not present on current API tier |
| Player props | ❌ REJECTED | 422 on bulk endpoint confirmed Feb 2026 |

---

## SECTION 7: WIFI-BLOCKED TASKS (revisit on good network)

These tasks require unblocked network access. Hospital/restricted wifi may block
sports APIs or Reddit. Complete these on next unrestricted session.

| # | Task | What to do |
|---|---|---|
| W1 | NHL API goalie endpoint | GET `https://api-web.nhle.com/v1/schedule/now` — confirm `startingGoalies` field structure |
| W2 | MLB Stats API pitcher | GET `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-04-01` — confirm `probablePitcher` field |
| W3 | Tennis API tier | GET `https://the-odds-api.com/liveapi/fixes/v4/sports/` with API key — confirm tennis_atp is in response |
| W4 | Reddit r/algobetting | Search for "NHL goalie API", "MLB pitcher feed", "Odds API tennis" discussions for community validation |
| W5 | Build core/nhl_data.py | After W1 confirms endpoint — write NHL schedule fetcher + nhl_kill_switch() in math_engine.py |

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

---

## SECTION 9: Next Session Checklist (Session 13)

Priority order when on good wifi:
1. **W1**: Verify NHL API `startingGoalies` field structure
2. **W2**: Verify MLB Stats API `probablePitcher` field
3. **W3**: Confirm tennis_atp in Odds API tier
4. **W5**: Build core/nhl_data.py + nhl_kill_switch() if W1 confirmed
5. Check bet tracker — if ≥10 graded bets, build CLV vs edge% scatter (4A)
6. Check RLM gate sidebar — if RAISE READY, manually raise SHARP_THRESHOLD to 50

---
*Generated by agent. Update this file at the end of each session.*
