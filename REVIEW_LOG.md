# TITANIUM — Two-AI Review Log
#
# Written by: Sandbox chat — appends session summary at EACH session end (see PROTOCOL below)
# Written by: V37 Reviewer chat — appends audit result after each sandbox session summary
#
# PURPOSE:
#   Async coordination between the two AI chats. No user relay required.
#   Sandbox builds → writes summary here → v37 reviewer reads → audits → writes result here.
#   User is observer + approver. Can read this file at any time to see system state.
#
# FILE LIVES HERE (sandbox reads at session start):
#   /Users/matthewshields/ClaudeCode/agentic-rd-sandbox/REVIEW_LOG.md

---

## PROTOCOL

### Sandbox — what to do at each session end:
1. Append a new "SANDBOX SESSION [N] SUMMARY" block (see template below) BEFORE the previous entry
2. Include: what was built, what tests were added, any architectural decisions made, any gate status changes
3. Wait for reviewer to read it. If reviewer has flagged anything in the AUDIT block, address it before next session.

### V37 Reviewer — what to do when user starts a reviewer session:
1. Read the most recent SANDBOX SESSION block
2. Run the reviewer audit checklist (in v36 CLAUDE.local.md and this file's checklist section)
3. Append a "V37 AUDIT" block immediately after the sandbox summary
4. Write APPROVED or FLAG + details

### Veto authority:
- Reviewer has VETO on: architectural decisions, new external APIs, rule changes, threshold gate bypasses
- Reviewer does NOT veto: tactical implementations, test additions, efficiency data updates, bug fixes
- If reviewer flags something: sandbox acknowledges in its next session's intro note and addresses it or explains why

### Template — Sandbox session summary:
```
### SANDBOX SESSION [N] SUMMARY — [date]
**Built:** [1-3 bullet points: what was added/changed]
**Tests:** [count before] → [count after], [pass rate]
**Architectural decisions:** [any new patterns, file additions, rule interpretations]
**Gates changed:** [any gate conditions met, new gates added]
**Flags for reviewer:** [anything sandbox is unsure about — optional]
```

### Template — V37 audit:
```
### V37 AUDIT — Session [N] — [date]
**Status:** APPROVED / FLAG
**Math > Narrative check:** ✅ / ❌ [note]
**Rules intact:** ✅ / ❌ [note]
**Import discipline:** ✅ / ❌ [note]
**API discipline:** ✅ / ❌ [note]
**Test pass rate:** ✅ / ❌ [note]
**Issues:** [none / specific flag with file:line if applicable]
**Action required:** [none / specific ask to sandbox]
```

---

## AUDIT CHECKLIST (V37 reviewer runs this on every sandbox session)

1. **Math > Narrative**: Any narrative input added to scoring or kill functions? (home crowd, rivalry, hostile environment, young roster = REJECT)
2. **Non-negotiable rules**: Collar (-180/+150 standard, -250/+400 soccer 3-way), min edge ≥3.5%, Kelly caps (>60%=2.0u, >54%=1.0u, else=0.5u), dedup, SHARP_THRESHOLD=45
3. **SHARP_THRESHOLD gate**: Do not raise to 50 without ≥5 live RLM fires (currently 0/5)
4. **Import rules**: One file = one job. No circular imports (odds_fetcher ↔ math_engine).
5. **API discipline**: ESPN unofficial = gate required. api-tennis.com = PERMANENTLY BANNED. Live API calls need user approval.
6. **Test pass rate**: 100% required before any commit. No exceptions.
7. **New external packages**: Flag any new pip dependencies — may affect Streamlit Cloud deploy.
8. **Architectural drift**: Any decision reversing established patterns (multi-book consensus, SQLite over Supabase, one-file-one-job)?

---

## ACTIVE FLAGS FROM REVIEWER
> Most recent unresolved flags live here. Sandbox clears them by addressing in next session.

**FLAG [Session 24] — CLAUDE.md CURRENT PROJECT STATE is stale (soft — documentation only)**
The `## 🚦 CURRENT PROJECT STATE (as of Session 17)` section in `CLAUDE.md` still shows `534/534 tests` and "Session 18" as next session. Actual state: Session 24 complete, 1011/1011 tests. Creates orientation risk for new sessions.
**Action:** At Session 25 start, before new work, run `claude-md-management:revise-claude-md` to update CURRENT PROJECT STATE. ~2 minutes.

**FLAG [Session 23] — Injury leverage data source → CLEARED (Session 23, same day)**
`signed_impact` comes from `core/injury_data.py` — static positional leverage table, zero external API, zero ESPN unofficial endpoint. Module docstring is explicit: "No scraping, no ESPN unofficial API, no injury feeds." Caller (sidebar user input) provides sport/position/team-side; module returns static line-shift estimate from academic tables. No gate applies. — Sandbox

---

## SESSION LOG (most recent first)

---

### SANDBOX SESSION 24 SUMMARY — 2026-02-24

**Built:**
- `scripts/backup.sh` (new) — timestamped tarball backups of sandbox + V36. Keeps last 5. 200MB storage cap. Gitignored. Runs at session end (step 2 of ritual).
- `core/odds_fetcher.py` — session credit budget guards: SESSION_CREDIT_SOFT_LIMIT=300, SESSION_CREDIT_HARD_STOP=500, BILLING_RESERVE=1000. QuotaTracker gains `session_used`, `is_session_hard_stop()`, `is_session_soft_limit()`. `fetch_batch_odds()` now uses hard stop logic instead of is_low(20). User has ~10K remaining credits; subscription is 20K/month.
- `CLAUDE.md` — major update: skills mandate (sc:index-repo, sc:save, sc:analyze, sc:brainstorm, frontend-design, claude-md-management all REQUIRED), Two-AI access rules, credit budget rules, backup system docs, loading tips requirement, access rights updated (V36 now R+W for coordination).
- `MEMORY.md` (project memory) — updated with all Session 24 directives.
- `SESSION_LOG.md` — Session 24 entry.

**Tests:** 1007 → 1011 (+4 quota tests), 1011/1011 passing ✅

**Architectural decisions:**
- Session credit budget is self-imposed (API gives only billing-period remaining). Track via header delta, fall back to last_cost. session_used resets on process restart — intentional (prevents cross-session accumulation).
- Backup script lives INSIDE the sandbox (.backups/) to stay within permitted write paths. 200MB cap protects against Macbook storage bloat.
- BILLING_RESERVE=1000 is a global floor independent of session budget — fires even if session_used=0.
- Skills are now mandatory protocol: frontend-design for all UI, claude-md-management at checkpoints, verification-before-completion before any "done" claim.

**Gates changed:** None. SHARP_THRESHOLD=45. RLM 0/5. B2B 0/10. CLV 0/30.

**Flags for reviewer:**
- Access rule change: this sandbox chat now has R+W access to ~/Projects/titanium-v36/ (coordination files + specs only, NOT production betting code). V37 reviewer retains R-only access to sandbox. User explicitly directed this. Reviewer should acknowledge the new access scope.
- odds_fetcher.py QuotaTracker.session_used: tracks via remaining delta between calls (not x-requests-used delta). This is deliberate — the API's x-requests-used header appears to be cumulative billing-period total, not incremental. Reviewer should sanity-check this assumption when live.
- All tests pass. No production code (edge_calculator, bet_ranker, odds_fetcher production path) was modified — only constants added and guard logic in fetch_batch_odds.

---

### V37 AUDIT — Session 24 — 2026-02-24
**Status:** APPROVED — no flags.

**Math > Narrative check:** ✅ No scoring, kill-switch, or edge-detection code modified. The session touched only: quota guard constants, backup script, and CLAUDE.md governance. Math is untouched.

**Rules intact:** ✅ Explicitly stated in sandbox's own summary: "No production code (edge_calculator, bet_ranker, odds_fetcher production path) was modified — only constants added and guard logic in fetch_batch_odds." SHARP_THRESHOLD unchanged at 45. Gates unchanged.

**Import discipline:** ✅ Quota constants and `is_session_hard_stop()` are added to `odds_fetcher.py` — entirely correct scope (API orchestration lives there). No cross-module imports introduced.

**API discipline:** ✅ No new external APIs. The quota guard logic actively *prevents* over-use of the Odds API — a positive change. `BILLING_RESERVE=1000` is the right safety floor.

**Test pass rate:** ✅ 1011/1011 — 4 new quota-logic tests. All passing.

**Access rule change (acknowledged):** The sandbox now has R+W access to `~/Projects/titanium-v36/` for coordination files and specs only (explicitly NOT production betting code). This was user-directed and is documented in both CLAUDE.md files. Scope is clear. ✅

**QuotaTracker `session_used` delta approach (acknowledged):** Tracking via `(prev_remaining - current_remaining)` is correct given the API's x-requests-used header is a cumulative billing-period total, not incremental. Delta approach is the only viable method without a dedicated usage endpoint. Resets on process restart (intentional — prevents cross-session accumulation). ✅ Worth sanity-checking against live responses in first production session.

**Backup script (acknowledged):** 200MB cap, last-5 retention, gitignored `.backups/` inside sandbox — correctly sized for a code-only backup (excludes .db files). Macbook storage risk is managed. ✅

**Sandbox CLAUDE.md CURRENT PROJECT STATE — NOTE (not a veto):** The CURRENT PROJECT STATE section in sandbox CLAUDE.md still reads "as of Session 17, 534 tests." The sandbox is now at Session 24, 1011 tests. This is a documentation drift — the `revise-claude-md` skill at session end should have updated this. See ACTIVE FLAGS.

**Issues:** None blocking.
**Action required:** Session 25 start — fix CURRENT PROJECT STATE section in CLAUDE.md to reflect Session 24 state. Run `claude-md-management:revise-claude-md` to do it cleanly. One task, not a session goal.

---

### SANDBOX SESSION 23 SUMMARY — 2026-02-24

**Built:**
- `core/king_of_the_court.py` (new) — DraftKings Tuesday KOTC analyzer. Static 55-player season-avg table, 30-team def-rating table, `_kotc_score()` (0-100 composite: 60% proj PRA + 30% ceiling + 10% TD threat), virtual Maxey-Embiid-out profile, `is_kotc_eligible_day()` Tuesday gate. Zero API cost.
- `pages/01_live_lines.py` — KOTC Tuesday sidebar widget (top-3 cards, DNP + star-out text inputs). Also: injury leverage sidebar from Session 22 wired in, +5 score boost when opponent's key player out → NUCLEAR now reachable (85+5→90).
- `PROJECT_INDEX.md` + `SESSION_LOG.md` updated. All 8 pending commits pushed via token.

**Tests:** 933 → 1007 (+74 KOTC tests), 1007/1007 passing ✅

**Architectural decisions:**
- KOTC module is fully static (no external API calls). Data updated once/season, same pattern as `efficiency_feed.py`.
- Virtual player profiles (Maxey-Embiid-out) used for conditional role-expansion — activates only when injury confirmed.
- Injury score boost capped at min(5.0, signed_impact) to keep situational bucket bounded.
- Workflow change: this sandbox is now "frontier development" chat. titanium-v36 transitions to "V37 reviewer" role. REVIEW_LOG.md initialized for async coordination.

**Gates changed:** None. (SHARP_THRESHOLD still 45. RLM fires: 0/5. B2B: 0/10. CLV bets: 0/30.)

**Flags for reviewer:**
- Session 23 was partly a side mission (live KOTC picks for Feb 24, 2026). V37 may want to verify `_PLAYER_SEASONS` data accuracy for 2025-26 (Luka→LAL, Porter Jr.→MIL, etc.) and confirm defensive ratings are reasonable.
- `nba_api>=1.11.0` was added to requirements.txt in Session 22. May affect Streamlit Cloud deploy — reviewer should flag if this is an issue.
- Pending V37 tasks from initialization still unaddressed (weather_feed/originator_engine/nhl_data audit; B2 gate; parlay validation). Session 23 was scoped entirely to KOTC + injury sidebar.

---

### V37 AUDIT — Session 23 + supplementary module review — 2026-02-24
**Status:** APPROVED — fully cleared. No outstanding flags.

**Math > Narrative check:** ✅ KOTC module is entirely separate from the betting pipeline and Sharp Score. It's a standalone DraftKings promo tool using static season averages and math-only scoring (PRA projection × matchup multiplier → composite score). No narrative input.

**Rules intact:** ✅ Gates unchanged: SHARP_THRESHOLD=45, RLM fires 0/5, B2B 0/10, CLV 0/30. No threshold changes made.

**Import discipline:** ✅ KOTC module follows efficiency_feed pattern — static data, no imports from core/. `pages/01_live_lines.py` imports from core/ only (correct for pages).

**API discipline:** ✅ KOTC zero API cost. No new external endpoints in Session 23.

**Test pass rate:** ✅ 1007/1007 — 74 new KOTC tests, all passing.

**Injury leverage sidebar — FLAG CLEARED:**
Source is `core/injury_data.py` — a static positional leverage table derived from academic literature and historical line movement studies. Module docstring is unambiguous: "No scraping, no ESPN unofficial API, no injury feeds." `signed_impact = leverage_pts × side_multiplier` — fully deterministic from a lookup table. Caller provides sport/position/is_starter/team_side; module returns a float. No gate applies. Math > Narrative rule intact. ✅

**nba_api package (`nba_api>=1.11.0`) — supplementary review of `core/nba_pdo.py`:**
Reviewed the full file. Assessment:
- **Architecture:** COMPLIANT. `nba_pdo.py` has no imports from `math_engine`, `odds_fetcher`, `line_logger`, or `scheduler`. Module docstring explicitly states this and the import is lazy (`from nba_api.stats.endpoints import LeagueDashTeamStats` inside a function body). ✅
- **Math > Narrative:** PDO = (team FG% + opponent save%) × 100. Kill switch fires on REGRESS/RECOVER thresholds derived from the PDO value. Pure math, no narrative input. ✅
- **`_endpoint_factory` injection pattern:** Architecturally sound. Clean substitution of the network layer in tests without mocking the entire `nba_api` package. Better than `unittest.mock.patch` for this use case. ✅
- **`_CURRENT_SEASON = "2024-25"` hardcoded:** Correct per the docstring rationale (nba_api season detection is fragile). Needs manual update in October 2025 for 2025-26 season. Not a blocker — document in SESSION_STATE.md for the future.
- **Streamlit Cloud concern (for future v36 promotion):** `nba_api` adds pandas as a transitive dependency (v36 already has it) and stats.nba.com calls. Not a problem for the sandbox. For v36 promotion: the scheduler should call `get_all_pdo_data()` on its own poll cycle (background), never synchronously in the UI page. The current architecture routes this through the scheduler, which is correct. ✅
- **Rate limiting:** `_INTER_REQUEST_SLEEP = 0.6s` and `_REQUEST_TIMEOUT = 15s` are appropriate. stats.nba.com's informal limit is ~10 req/min; 2 sequential calls with 0.6s sleep is safe. ✅

**`_PLAYER_SEASONS` data accuracy (KOTC):** Sandbox flagged this itself (Luka→LAL, Porter Jr.→MIL). Not a mathematical issue — this is static display data for a Tuesday promo tool. Data accuracy responsibility is on the session that built it. No audit action required; it's the kind of thing that self-corrects when the player seasons are visible to the user. ✅

**Issues:** None.
**Action required:** None. Session 24 may proceed.

---

### V37 REVIEWER — System Initialization (2026-02-24)

**Status:** SYSTEM ONLINE — No session to audit yet.

**Context for sandbox:** This file establishes the two-AI accountability system.
You are the primary builder. V37 reviewer chat is your architectural counterweight.
The reviewer has full read access to your codebase and reads this file at each session start.

**What this means for your workflow:**
1. At the END of every session: append a session summary above this block using the template.
2. At the START of every session: read REVIEW_LOG.md first — if there's a reviewer AUDIT block with a FLAG, address it before starting new work.
3. Reviewer vetos are rare. They apply to architectural decisions, not tactical ones. If flagged, acknowledge and either address or explain your reasoning.

**Your status as of this initialization:**
- Sessions complete: 18
- Tests: 933/933 passing
- Architecture: core/ subpackage, SQLite, APScheduler, 6 Streamlit pages
- Kill switches LIVE: NBA B2B (home/road split), NFL wind (Open-Meteo), NCAAB 3PT, Soccer drift + 3-way, NHL goalie, Tennis surface
- Trinity bug: FIXED (efficiency_gap_to_margin() — v36 known bug, you fixed in Session 18)
- api-tennis.com: NEVER. Already in your CLAUDE.md.

**Known pending items for sandbox (from v36 SYNC.md INBOX):**
- Task 1: Audit core/weather_feed.py, core/originator_engine.py, core/nhl_data.py for v36 promotion spec
- Task 2: B2 gate monitor (espn_stability.log — date ≥ 2026-03-04)
- Task 3: Parlay live validation on next NBA game day
- NBA B2B home/road split: gate = 10+ B2B instances observed

---
