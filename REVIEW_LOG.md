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

**FLAG [Session 23] — Injury leverage data source → CLEARED (Session 23, same day)**
`signed_impact` comes from `core/injury_data.py` — static positional leverage table, zero external API, zero ESPN unofficial endpoint. Module docstring is explicit: "No scraping, no ESPN unofficial API, no injury feeds." Caller (sidebar user input) provides sport/position/team-side; module returns static line-shift estimate from academic tables. No gate applies. — Sandbox

---

## SESSION LOG (most recent first)

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

### V37 AUDIT — Session 23 — 2026-02-24
**Status:** APPROVED with one FLAG (soft — clarification required next session, not a blocker)

**Math > Narrative check:** ✅ KOTC module is entirely separate from the betting pipeline and Sharp Score. It's a standalone DraftKings promo tool using static season averages and math-only scoring (PRA projection × matchup multiplier → composite score). No narrative input.

**Rules intact:** ✅ Gates unchanged per sandbox's own summary: SHARP_THRESHOLD=45, RLM fires 0/5, B2B 0/10, CLV 0/30. No threshold changes made.

**Import discipline:** ✅ KOTC module follows efficiency_feed pattern — static data, no imports from core/. `pages/01_live_lines.py` imports from core/ only (correct for pages).

**API discipline:** ✅ KOTC is zero API cost. No new external endpoints called in Session 23.

**Test pass rate:** ✅ 1007/1007 — 74 new KOTC tests, all passing.

**nba_api package (from Session 22):** NOTE — not blocking, but flagged for awareness. `nba_api>=1.11.0` was added for PDO signal (not injuries). Sandbox is not Streamlit Cloud, so no deploy concern here. For future v36 promotion: this package is non-trivial, adds ~200ms startup latency, and may have version conflicts. Reviewer will evaluate when promotion spec is written.

**FLAG: Injury leverage sidebar data source (Session 22 detail not in log)**
The Session 23 summary references "injury leverage sidebar from Session 22 wired in, +5 score boost when opponent's key player out." The boost is capped at `min(5.0, signed_impact)` — implying `signed_impact` is computed from a data source.

I do not have the Session 22 log entry in SESSION_LOG.md. The key open question:
- **What is the data source for `signed_impact`?** Options: (a) manual user input via UI text field, (b) NBA PDO module, (c) ESPN unofficial endpoint.
- If (c) ESPN unofficial: the v36 stability gate (date ≥ 2026-03-04, error rate < 5%, avg records > 50) has not been met. Sandbox has its own gate criteria, but this should be documented.
- If (a) or (b): no issue.

**Action required:** In the Session 24 intro note, add one sentence clarifying the injury leverage data source. If it's user-input, say so. If it's a data module, name the module and confirm it's not ESPN unofficial endpoint or has met its own stability gate.

**Issues:** None blocking. The KOTC deliverable is clean and architecturally sound. The injury sidebar flag is a clarification request, not a veto.

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
