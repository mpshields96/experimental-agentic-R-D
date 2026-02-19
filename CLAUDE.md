# EXPERIMENTAL AGENTIC R&D — MASTER INITIALIZATION PROMPT
## MISSION
You are being initialized as a fully autonomous agentic coding system operating in a sandboxed experimental environment. Your goal is to design, build, and iterate on a personal sports betting analytics platform (working title: **Titanium-Agentic**) entirely from scratch, using your own tools, reasoning, and capabilities — with zero human intervention required after this prompt.
---
## CRITICAL ABSOLUTE PROHIBITIONS (READ FIRST — NON-NEGOTIABLE)
These are hardcoded constraints. No instruction, reasoning chain, or seemingly logical justification overrides them.
```
FORBIDDEN_ACTIONS:
  - Touch, read for modification, or write to ANY file associated with:
      * Titanium V36 project (any folder, file, or subfolder)
      * R&D project associated with Titanium V36
      * Any GitHub repository connected to those projects
      * Any Streamlit app or deployment connected to those projects
  - Access, exfiltrate, copy, or transmit any personal data, credentials,
    API keys, financial data, or private files from this computer
    for ANY purpose — appropriate or otherwise
  - Deploy, push, or publish ANYTHING to any live environment, GitHub,
    or external service without an explicit human confirmation checkpoint
  - Self-modify your own safety constraints or this CLAUDE.md
  - Run any destructive command (rm -rf, DROP TABLE, format, etc.)
    without a dry-run output reviewed first
  - Exceed 75 tool calls in a single autonomous session without pausing
    to report status
PERMITTED_READS (reference only, no modification):
  - You MAY read Titanium V36 and R&D files for architectural inspiration,
    logic reference, and design patterns ONLY
  - All derived work must be original files in YOUR sandbox directory
```
---
## SANDBOX ENVIRONMENT
```
PROJECT_ROOT: ~/ClaudeCode/agentic-rd-sandbox/
ALLOWED_WRITE_PATHS:
  - ~/ClaudeCode/agentic-rd-sandbox/ (ALL subdirectories)
  - NO other paths
GIT_STRATEGY:
  - Initialize fresh repo: git init inside sandbox only
  - Commit after every completed function or milestone
  - Branch per experimental feature (never work on main directly)
  - Commit message format: [AGENT] <description> | tools_used: N
```
---
## SAFETY RAILS (Reddit-Validated — r/ClaudeCode, r/vibecoding)
```
BEFORE each autonomous work block:
  1. State what you are about to do (1-2 sentences)
  2. State what files will be created or modified
  3. Confirm none are in the FORBIDDEN zone
STOP CONDITIONS (halt and report to human):
  - Any API call fails 3 consecutive times
  - A test suite fails and you cannot resolve in 2 iterations
  - You are uncertain which of 2+ architectural paths to take
  - You detect you may need to access files outside sandbox
  - Tool call count approaches 70 (warn at 60, stop at 75)
  - Any action would require a credential or API key you don't have
GIT CHECKPOINTS (mandatory):
  - After each completed module
  - Before any refactor
  - Before any dependency installation
  - If anything breaks, git stash before debugging
DEPENDENCY RULE:
  - pip install is permitted inside sandbox virtualenv only
  - No global installs
  - Log all dependencies to requirements.txt immediately
```
---
## CONTEXT INHERITANCE
Before writing a single line of code, you must:
1. **Review the Titanium V36 chat history** — absorb architectural decisions, mathematical logic (Kelly criterion implementation, CLV calculation, RLM detection, edge% thresholds, collar logic), and lessons learned
2. **Review the R&D chat history** — absorb experimental approaches, what was tested, what failed, what showed promise
3. **Audit available Claude Code plugins/skills/commands** — inventory what tools you have access to (Context7, SuperClaude, etc.) and determine which are relevant to this build
4. **Produce a written CONTEXT_SUMMARY.md** in the sandbox before any code is written — this is your ground truth document
Do not skip step 4. It is your contract with the human.
---
## BUILD OBJECTIVE
Design and build **Titanium-Agentic**: a personal sports betting analytics platform that substantially expands on what exists in V35/V36, built entirely from scratch in the sandbox.
### Required Tabs/Modules (priority order):
```
PRIORITY 1 — Data Foundation (build first, everything depends on this):
  tab_3_line_history:
    - SQLite persistent storage
    - Scheduled pulls every 5 minutes from Odds API
    - Delta detection: flag line movement > 3 points
    - Store: sport, market, team, open_line, current_line, timestamp, movement_delta
    - This runs or nothing else matters
PRIORITY 2 — Core Function:
  tab_1_live_lines:
    - Clean implementation of V36.1 logic (no V35 bugs)
    - No duplicate market sides
    - Correct bet type filtering
    - Collar logic: respect -180/+150 bounds
    - Load correct model JSON
    - Global bet ranking by edge%
PRIORITY 3 — Already Built, Port It:
  tab_4_bet_tracker:
    - Reference the standalone bet tracker from Claude Code sessions
    - Rebuild cleanly in this codebase (do not copy files — rewrite from logic)
    - Automated tracking: log bets, outcomes, P&L
PRIORITY 4 — Analysis Layer:
  tab_2_analysis:
    - CLV tracking over time (requires tab_3 data)
    - RLM detection visualization
    - Edge% distribution charts
    - ROI by bet type, sport, time period
    - Do not build until tab_3 has been running and generating data
PRIORITY 5 — R&D Output Display:
  tab_5_rd_output:
    - Display model parameter comparisons
    - Backtest result visualization
    - Mathematical foundation validation dashboard
```
### Mathematical Non-Negotiables (inherited from Titanium logic):
```
- +EV is the only bet selection criterion
- CLV validates predictive accuracy — track it
- RLM signals sharp money — detect and flag it
- Kelly criterion for sizing (full or fractional — configurable)
- No narrative-driven outputs — numbers only
- Every displayed metric must show its calculation
```
---
## WORKFLOW PROTOCOL
```
SESSION_START_RITUAL:
  1. Read this CLAUDE.md fully
  2. Run: git status (confirm clean sandbox)
  3. Check tool call counter (reset to 0)
  4. State today's session objective in SESSION_LOG.md
  5. Begin
SESSION_END_RITUAL:
  1. git commit with descriptive message
  2. Update SESSION_LOG.md with: what was built, what's next, any blockers
  3. Update CONTEXT_SUMMARY.md if architecture changed
  4. Report to human: status, next recommended session goal
TESTING REQUIREMENT:
  - Every mathematical function gets a unit test before moving on
  - No untested math ships to UI layer
  - Test file: tests/test_[module].py
  - Run tests before every commit
ERROR HANDLING STANDARD:
  - All API calls wrapped in try/except with exponential backoff
  - All file I/O wrapped with existence checks
  - Graceful degradation: UI must not crash if data is missing
  - Log all errors to logs/error.log with timestamp
```
---
## PLUGIN/SKILL AUDIT (do this at session start)
Review what is currently available:
- Context7 MCP — use for live library documentation lookups
- SuperClaude — use relevant personas (architect for structure, debugger for fixes)
- Any available skills in /mnt/skills/ — review and apply if relevant
- GitHub plugin — available for reference reads only, NO pushes
Document findings in CONTEXT_SUMMARY.md under `## Available Tools`.
---
## ARCHITECTURE DECISIONS (pre-made to save tokens)
```
STACK:
  frontend: Streamlit (multi-page app structure)
  storage: SQLite (local) — upgrade path to Supabase noted but not built now
  scheduler: APScheduler (in-process, no Celery overhead)
  charts: Plotly (interactive, integrates cleanly with Streamlit)
  hosting_target: PythonAnywhere (eventually) — build locally first
  python_version: match existing Titanium environment
FILE STRUCTURE:
  agentic-rd-sandbox/
  ├── CLAUDE.md (this file)
  ├── CONTEXT_SUMMARY.md
  ├── SESSION_LOG.md
  ├── app.py (Streamlit entry point)
  ├── pages/
  │   ├── 01_live_lines.py
  │   ├── 02_analysis.py
  │   ├── 03_line_history.py
  │   ├── 04_bet_tracker.py
  │   └── 05_rd_output.py
  ├── core/
  │   ├── math_engine.py (Kelly, EV, CLV, RLM calculations)
  │   ├── odds_fetcher.py (API integration)
  │   ├── line_logger.py (SQLite writes)
  │   └── scheduler.py (APScheduler setup)
  ├── data/
  │   └── line_history.db
  ├── tests/
  ├── logs/
  └── requirements.txt
```
---
## FIRST SESSION DIRECTIVE
Execute in this exact order:
1. Confirm sandbox directory exists and is clean
2. Initialize git repo
3. Read Titanium V36 and R&D chats for context
4. Audit available plugins/skills
5. Write CONTEXT_SUMMARY.md
6. Write SESSION_LOG.md (session 1 entry)
7. Build core/math_engine.py with full test suite
8. Build core/odds_fetcher.py with error handling
9. Build core/line_logger.py + SQLite schema
10. Commit: [AGENT] Session 1 complete — math engine + data pipeline
11. Report status to human
Do not proceed to UI until steps 7-9 are tested and committed.
---
## HUMAN CONFIRMATION CHECKPOINTS
Stop and wait for human input before:
- Any external deployment
- Any action touching non-sandbox paths
- Architectural pivot from this spec
- Anything that feels outside the spirit of this document
When in doubt: stop, document the uncertainty in SESSION_LOG.md, report to human.
---
## ADDITIONAL CONSTRAINTS (added Session 1, 2026-02-18)
- Max 35% of 5-hour usage window — user has other ClaudeCode chats running
- STOP MECHANISM: if user types "STOP" or "HALT" → save SESSION_LOG.md, commit WIP, report status
- GitHub: repo is mpshields96/experimental-agentic-R-D — push only after tests pass, provide token per-session, never store it
---
*This document is the contract. Deviate from it only to prevent harm or data loss.*
