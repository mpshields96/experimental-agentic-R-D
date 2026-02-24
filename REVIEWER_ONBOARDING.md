# REVIEWER SYSTEM — ONBOARDING NOTE FOR SANDBOX CHAT
# Created: 2026-02-24
# Written by: V37 reviewer chat (Claude Code in titanium-v36/ directory)
# Action required: Read this, acknowledge in your next session, update your CLAUDE.md session ritual.

---

## WHAT CHANGED

A two-AI accountability system is now active.

You (the agentic sandbox) are the primary builder. A second Claude Code chat — the V37 reviewer —
now has READ-ONLY access to your codebase and reviews your session output.

**Why this exists:**
- Your CLAUDE.md is self-referential. You can't catch architectural drift you don't know happened.
- The reviewer provides an external check from a chat with a different context window and explicit audit instructions.
- The user is the observer and final approver. Both AIs operate more autonomously. Less user relay needed.

---

## THE COORDINATION FILE

`/Users/matthewshields/ClaudeCode/agentic-rd-sandbox/REVIEW_LOG.md`

This is the async communication channel between you and the reviewer. The user does not need to relay messages.

**Your responsibility:**
At the END of every session, append a session summary to REVIEW_LOG.md using this format:

```
### SANDBOX SESSION [N] SUMMARY — [date]
**Built:** [1-3 bullet points]
**Tests:** [count before] → [count after], [pass rate]
**Architectural decisions:** [any new patterns, file additions, rule changes]
**Gates changed:** [any gate conditions met or added]
**Flags for reviewer:** [anything you're unsure about — optional]
```

At the START of every session, read REVIEW_LOG.md first.
If there's a reviewer AUDIT block with a FLAG, address it before starting new work.

---

## REVIEWER AUTHORITY

**Reviewer DOES veto:**
- Architectural decisions (new file structures, database changes, pattern reversals)
- New external APIs (esp. unofficial ones — ESPN requires gate, api-tennis.com is permanently banned)
- Rule changes (collar, min edge, Kelly caps, SHARP_THRESHOLD gate)
- Quota-burning behavior

**Reviewer does NOT veto:**
- Tactical implementations (feature additions, bug fixes)
- Test additions
- Efficiency data updates
- Performance improvements

If the reviewer flags something: acknowledge it in your next session intro note. You can address it OR explain your reasoning. The reviewer is an auditor, not a blocker.

---

## WHAT YOU DON'T NEED TO CHANGE

Your CLAUDE.md math rules, architecture rules, and non-negotiables are unchanged and already aligned with what the reviewer enforces. The reviewer validated your codebase (933 tests, 18 sessions) as architecturally sound.

The only workflow change is: write a session summary to REVIEW_LOG.md at session end.

---

## REVIEWER'S CURRENT ASSESSMENT OF YOUR CODEBASE

Reviewed 2026-02-24 against v36 baseline:
- Math > Narrative: COMPLIANT
- Collar / edge / Kelly rules: COMPLIANT
- Import discipline: COMPLIANT
- Test coverage: 933/933 — EXCEEDS v36 (163 tests)
- Kill switch coverage: EXCEEDS v36 (12 live vs 1 live)
- api-tennis.com: BANNED in your CLAUDE.md — COMPLIANT
- Trinity bug fix: CONFIRMED — efficiency_gap_to_margin() is the correct fix
- SQLite over Supabase: APPROVED architectural decision (free, no external dep)

Status: **APPROVED — no current flags. Clear to proceed.**

---

## PENDING TASKS (from v36 SYNC.md INBOX — 2026-02-24)

1. **Sandbox audit for v36 promotion** — read core/weather_feed.py, core/originator_engine.py, core/nhl_data.py and write a v36 promotion spec (import path fixes, new packages, schema diffs, test count). Design only, no code.
2. **B2 gate monitor** — check titanium-experimental/results/espn_stability.log at session start. Gate: date ≥ 2026-03-04, error rate < 5%, avg NBA records > 50.
3. **Parlay live validation** — on next NBA game day, run build_parlay_combos([vars(b) for b in ranked_bets]) and report to REVIEW_LOG.md.

---
