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

*(none — system just initialized, 2026-02-24)*

---

## SESSION LOG (most recent first)

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
