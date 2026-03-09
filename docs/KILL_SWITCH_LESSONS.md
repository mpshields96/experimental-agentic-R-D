# Kill Switch Wiring — Lessons Learned
*Last updated: Session 45 (2026-03-08)*

Every kill switch bug found in production costs real money: paper bets log for
games that a live bettor would never touch. This doc catalogs the failure patterns
with concrete examples from real sessions.

---

## FAILURE PATTERN A — SILENT BYPASS (Highest severity)

**What it is:** Kill switch has a compound guard: `if condition AND context_param`.
The condition would fire correctly, but `context_param` is falsy (empty string, 0, None)
because the call site never passed it. Kill switch evaluates to SAFE. No error, no log.

**Why it's dangerous:** The bet IS logged as a paper bet. The bettor sees a Grade A
signal and possibly acts on it — but the kill switch that should have stopped it never ran.

### Real example: Tennis surface kill switch (Session 45)

`parse_game_markets()` at line ~1745:
```python
if sport.upper().startswith("TENNIS") and tennis_sport_key:
    killed, reason = tennis_kill_switch(surface_from_sport_key(tennis_sport_key), ...)
```

`_auto_paper_bet_scan()` in scheduler.py called:
```python
bets = parse_game_markets(game, sport, ...)  # tennis_sport_key not passed → defaults to ""
```

Result: `"TENNIS_ATP_MIAMI_OPEN".startswith("TENNIS")` = True ✅, but `""` is falsy ❌.
Kill switch silently bypassed for ALL scheduler-polled tennis games.

**Fix applied:**
```python
_is_tennis = sport.lower().startswith("tennis_atp") or sport.lower().startswith("tennis_wta")
_tennis_key = sport if _is_tennis else ""
bets = parse_game_markets(..., tennis_sport_key=_tennis_key)
```

### How to spot Pattern A:
- Kill switch condition: `if A and B` where B is a context param
- Search call sites for missing B → if `B` defaults to `""` or `0` or `False`, it's a silent bypass

---

## FAILURE PATTERN B — KILL SWITCH NOT WIRED

**What it is:** Kill switch block is guarded by `if param is not None`. Call site
passes the default `None`. Kill switch block is simply skipped — not bypassed, just dormant.

**Why it matters:** Lower severity than Pattern A (no false signals), but the protection
is missing entirely. Bets that should be flagged proceed without the safeguard.

### Real example: NHL goalie kill switch (both paths as of S45)

`parse_game_markets()` line ~1702:
```python
if nhl_goalie_status is not None:
    ...
    killed, reason = nhl_kill_switch(backup_goalie=..., ...)
```

Both `scheduler.py` and `live_lines.py` don't pass `nhl_goalie_status` → defaults to `None`.
The goalie kill switch never fires.

**Fix applied (Session 45):**
- `_poll_nhl_goalies(games)` reordered to run BEFORE `_auto_paper_bet_scan()` in main poll loop.
- `get_cached_goalie_status(event_id)` called per-game in both `_auto_paper_bet_scan()` and
  `live_lines.py` — reads from shared in-process `_goalie_cache` populated by the scheduler.

---

## FAILURE PATTERN C — PAPER/LIVE PARITY GAP

**What it is:** `parse_game_markets()` accepts context params that power binary kill
switches. Scheduler auto-scan was missing several params that live_lines.py passes,
causing paper bets to survive kills that live UI would have caught.

### Params that were missing from scheduler (fixed S45):

| Param | Kill switch triggered | Impact if missing |
|-------|----------------------|-------------------|
| `rest_days` | B2B spread kill (`<= -4` spread) | Paper logs B2B games live would skip |
| `wind_mph` | NFL totals kill (>20mph) | Paper logs high-wind NFL totals |
| `nba_pdo` | PDO regression kill (NBA) | Paper logs negative-PDO NBA bets |
| `efficiency_gap` | Affects sharp_score (not binary) | Paper bets have wrong score vs live |

**Fix applied in Session 45:**
- `rest_days` = `compute_rest_days_from_schedule(games)` — zero API cost
- `wind_mph` = `get_stadium_wind(home, commence_time)` for NFL only — cached 1hr
- `nba_pdo` = `get_all_pdo_data()` for NBA — hourly cache guard in `_pdo_scan_cache`
- `efficiency_gap` = `get_efficiency_gap(home, away)` — local data, zero cost

---

## RULE: Every call site must pass ALL binary kill-switch params

When adding or modifying a kill switch in `parse_game_markets()`:

1. **If the guard is `if param and condition`** → Pattern A risk. BOTH call sites must
   explicitly detect and pass the param. Empty string / zero / False = silent bypass.

2. **If the guard is `if param is not None`** → Pattern B. Document the gap explicitly.
   Add to `kill_switch_audit.py` NOT_WIRED_PARAMS until fixed.

3. **Run `scripts/kill_switch_audit.py --strict`** before every commit that changes
   `parse_game_markets()` signature or any of its call sites.

---

## AUDIT TOOL

```bash
python3 scripts/kill_switch_audit.py          # report
python3 scripts/kill_switch_audit.py --strict # exit 1 if CRITICAL/IMPORTANT gaps
```

Update `SILENT_BYPASS_PARAMS` and `NOT_WIRED_PARAMS` in `scripts/kill_switch_audit.py`
whenever a new kill switch is added to `parse_game_markets()`.

---

## SESSION HISTORY

| Session | Bug | Pattern | Fix |
|---------|-----|---------|-----|
| S45 | Tennis kill switch never fired in auto-scan | A (silent bypass) | Detect tennis key; pass `tennis_sport_key=sport` |
| S45 | Paper bets not subject to B2B/wind/PDO kills | C (parity) | Add `rest_days`, `wind_mph`, `nba_pdo`, `efficiency_gap` to auto-scan |
| S45 | NHL goalie kill switch not wired in either path | B (not wired) | Reorder _poll_nhl_goalies before auto-scan; read _goalie_cache in both paths |
| S40 | `injury_leverage` hardcoded 0.0 in live UI | C (parity) | Compute from `compute_injury_leverage_from_event()` dynamically |
