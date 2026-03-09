"""
tests/test_kill_switch_audit.py — Kill Switch Wiring Enforcement Tests

These tests enforce that ALL call sites of parse_game_markets() are wired
with the full set of kill-switch-critical context parameters.

WHY THIS EXISTS:
  Session 45 surfaced a SILENT BYPASS bug: tennis_sport_key was not passed
  to parse_game_markets() in _auto_paper_bet_scan(). The compound guard
  `sport.startswith("TENNIS") and tennis_sport_key` evaluated to False
  because tennis_sport_key defaulted to "".

  Result: every scheduler-polled tennis game bypassed the surface kill switch
  silently. No error, no log, no trace. Bets were logged that should have
  been killed.

WHAT THIS CATCHES:
  - SILENT BYPASS (Pattern A): compound guard `A and B` where B is falsy.
    Kill switch evaluates safe even when condition fires.
  - NOT WIRED (Pattern B): `if param is not None` guard, param always None.
    Kill switch block silently skipped.
  - PARITY (Pattern C): context params present in live UI but missing from
    scheduler auto-scan. Paper bets scored/killed differently than live bets.

RUN:
  python3 -m pytest tests/test_kill_switch_audit.py -v
  (also runs automatically with: python3 -m pytest)
"""
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
AUDIT_SCRIPT = ROOT / "scripts" / "kill_switch_audit.py"


def _run_audit(strict: bool = False) -> tuple[int, str]:
    """Run the audit script and return (returncode, output)."""
    cmd = [sys.executable, str(AUDIT_SCRIPT)]
    if strict:
        cmd.append("--strict")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return result.returncode, result.stdout + result.stderr


class TestKillSwitchAuditScript:
    """Verify the audit script itself exists and runs correctly."""

    def test_audit_script_exists(self):
        """scripts/kill_switch_audit.py must exist — it's the enforcement tool."""
        assert AUDIT_SCRIPT.exists(), (
            "scripts/kill_switch_audit.py is missing. "
            "This is the kill switch wiring enforcement tool — must not be deleted."
        )

    def test_audit_script_runs_without_error(self):
        """Audit script must execute without Python exceptions."""
        returncode, output = _run_audit(strict=False)
        assert "Traceback" not in output, (
            f"Audit script raised an exception:\n{output}"
        )
        assert "Error" not in output or "CRITICAL" in output or returncode == 0, (
            f"Unexpected error output:\n{output}"
        )


class TestKillSwitchWiring:
    """
    CRITICAL: All call sites of parse_game_markets() must pass every
    kill-switch-critical context parameter.

    If this test fails, a kill switch is silently bypassed in production.

    To fix a failure:
      1. Read docs/KILL_SWITCH_LESSONS.md — understand which pattern failed
      2. Add the missing parameter to the call site identified in the failure message
      3. If adding a new kill switch param to parse_game_markets(), also update:
         - scripts/kill_switch_audit.py SILENT_BYPASS_PARAMS or NOT_WIRED_PARAMS
         - docs/KILL_SWITCH_LESSONS.md SESSION HISTORY table
         - Both call sites: core/scheduler.py + pages/01_live_lines.py
    """

    def test_no_critical_gaps_strict(self):
        """
        CRITICAL — must never fail.

        A CRITICAL gap means a kill switch compound guard `A and B` has `B`
        missing at a call site. The kill switch evaluates SAFE regardless of
        game state. Bets that should be KILLED will be logged.

        Failure message includes the exact file:line and missing param.
        """
        returncode, output = _run_audit(strict=True)
        assert returncode == 0, (
            f"Kill switch audit FAILED in strict mode.\n\n"
            f"This means a kill switch is silently bypassed at a call site.\n"
            f"Read docs/KILL_SWITCH_LESSONS.md for the fix pattern.\n\n"
            f"Audit output:\n{output}"
        )

    def test_zero_critical_gaps_in_output(self):
        """Audit report must show 0 CRITICAL gaps."""
        _, output = _run_audit(strict=False)
        assert "CRITICAL:          0" in output or "🔴 CRITICAL" not in output, (
            f"CRITICAL gaps found in kill switch audit.\n"
            f"Silent bypass detected — kill switches not firing.\n\n"
            f"Output:\n{output}"
        )

    def test_zero_important_gaps_in_output(self):
        """
        Audit must show 0 IMPORTANT gaps.

        IMPORTANT = NOT WIRED (Pattern B): param is always None, kill switch
        block never executes. Not a silent bypass, but protection is missing.

        If this fails: a kill switch was added to parse_game_markets() but
        not wired at a call site. Fix: pass the required context param.
        """
        _, output = _run_audit(strict=False)
        assert "IMPORTANT:         0" in output or "🟡 IMPORTANT" not in output, (
            f"IMPORTANT gaps found in kill switch audit.\n"
            f"Kill switch block not wired at one or more call sites.\n\n"
            f"Output:\n{output}"
        )

    def test_zero_parity_gaps_in_output(self):
        """
        Audit must show 0 PARITY gaps.

        PARITY = params that drive kill switches are present in live_lines.py
        but missing from scheduler._auto_paper_bet_scan(). Paper bets would
        survive kills that live bets would not — misleading P&L tracking.

        If this fails: a context param was added to the live UI path but not
        the scheduler auto-scan path (or vice versa). Both paths must be
        identical.
        """
        _, output = _run_audit(strict=False)
        assert "PARITY gaps:       0" in output or "🔵 PARITY" not in output, (
            f"PARITY gaps found in kill switch audit.\n"
            f"Paper bets will be scored/killed differently from live bets.\n\n"
            f"Output:\n{output}"
        )

    def test_both_call_sites_are_ok(self):
        """Both core/scheduler.py and pages/01_live_lines.py must show ✅ OK."""
        _, output = _run_audit(strict=False)
        ok_count_line = [l for l in output.splitlines() if "✅ OK:" in l]
        assert ok_count_line, f"Could not find OK count in audit output:\n{output}"
        # Both sites should be OK
        ok_line = ok_count_line[0]
        # Extract the number after "✅ OK:"
        import re
        match = re.search(r"✅ OK:\s+(\d+)", ok_line)
        assert match, f"Unexpected OK line format: {ok_line}"
        ok_count = int(match.group(1))
        assert ok_count >= 2, (
            f"Expected ≥2 call sites to be ✅ OK, got {ok_count}.\n"
            f"Output:\n{output}"
        )
