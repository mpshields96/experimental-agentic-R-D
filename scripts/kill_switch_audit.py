#!/usr/bin/env python3
"""
scripts/kill_switch_audit.py — Kill Switch Wiring Audit
========================================================
Static AST analysis of all parse_game_markets() call sites.

Detects two failure patterns that caused real bugs:

  PATTERN A — SILENT BYPASS
    Kill switch checks `condition AND context_param`, but call site passes
    context_param="" (empty / falsy). Kill switch evaluates to SAFE even when
    condition would fire. Example: tennis Session 45 gap.

  PATTERN B — NOT WIRED
    Kill switch requires a context dict that defaults to None. Call site never
    provides it, so kill switch block is skipped entirely. Example: NHL goalie
    status in auto-scan.

Usage:
    python3 scripts/kill_switch_audit.py [--strict]

    --strict: exit code 1 if any gaps found (use in CI / pre-commit hooks)

Exit codes:
    0 — all CRITICAL params wired at all call sites, or --strict not set
    1 — gaps found AND --strict flag passed
"""
import ast
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Config — which params are "critical" for kill switch wiring
# ---------------------------------------------------------------------------

# CRITICAL = silent bypass if missing (falsy default kills the condition).
# These will NEVER fire correctly if not explicitly provided when needed.
SILENT_BYPASS_PARAMS = [
    "tennis_sport_key",   # "" → Tennis surface kill switch silently bypassed
]

# IMPORTANT = kill switch gated behind `if param is not None`, so it's not
# fired but is also not silently wrong. Still a gap vs live UI.
NOT_WIRED_PARAMS = [
    "nhl_goalie_status",  # None → NHL goalie kill switch skipped entirely
]

# PARITY = params that affect scoring but don't have binary kill-switch gates.
# Missing = auto-scan bets scored differently than live UI bets (paper/live gap).
PARITY_PARAMS = [
    "efficiency_gap",     # NBA/NCAAB net rating gap — affects sharp score
    "rest_days",          # B2B / rest fatigue — affects kill switch
    "wind_mph",           # NFL weather — affects kill switch
    "nba_pdo",            # NBA PDO regression — affects kill switch
]

# Source files to audit (relative to ROOT)
TARGET_FILES = [
    "core/scheduler.py",
    "pages/01_live_lines.py",
]

FUNCTION_NAME = "parse_game_markets"


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------

def find_call_sites(source: str, filename: str) -> list[dict]:
    """Return all call sites of FUNCTION_NAME with their kwargs."""
    tree = ast.parse(source)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match direct calls: parse_game_markets(...)
        if isinstance(node.func, ast.Name) and node.func.id == FUNCTION_NAME:
            kwargs_passed = {kw.arg for kw in node.keywords if kw.arg is not None}
            sites.append({
                "file": filename,
                "line": node.lineno,
                "kwargs": kwargs_passed,
            })
        # Match attribute calls: module.parse_game_markets(...)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == FUNCTION_NAME:
            kwargs_passed = {kw.arg for kw in node.keywords if kw.arg is not None}
            sites.append({
                "file": filename,
                "line": node.lineno,
                "kwargs": kwargs_passed,
            })
    return sites


def audit_call_site(site: dict) -> dict:
    """Categorise gaps for a single call site."""
    kw = site["kwargs"]
    return {
        "file": site["file"],
        "line": site["line"],
        "kwargs": sorted(kw),
        "silent_bypass_missing": sorted(p for p in SILENT_BYPASS_PARAMS if p not in kw),
        "not_wired_missing":     sorted(p for p in NOT_WIRED_PARAMS if p not in kw),
        "parity_missing":        sorted(p for p in PARITY_PARAMS if p not in kw),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def severity_label(gap: dict) -> str:
    if gap["silent_bypass_missing"]:
        return "🔴 CRITICAL (silent bypass)"
    if gap["not_wired_missing"]:
        return "🟡 IMPORTANT (kill switch not wired)"
    if gap["parity_missing"]:
        return "🔵 PARITY (paper/live scoring gap)"
    return "✅ OK"


def run_audit(strict: bool = False) -> int:
    all_sites = []
    for rel_path in TARGET_FILES:
        fp = ROOT / rel_path
        if not fp.exists():
            print(f"⚠️  File not found: {fp}")
            continue
        source = fp.read_text()
        sites = find_call_sites(source, rel_path)
        if not sites:
            print(f"⚠️  No {FUNCTION_NAME}() call found in {rel_path}")
        all_sites.extend(sites)

    if not all_sites:
        print("❌ No call sites found — check TARGET_FILES config.")
        return 1

    gaps = [audit_call_site(s) for s in all_sites]

    # Print report
    print(f"\n{'='*70}")
    print(f"KILL SWITCH WIRING AUDIT — {FUNCTION_NAME}()")
    print(f"{'='*70}")
    print(f"Scanned {len(gaps)} call site(s) across {len(TARGET_FILES)} file(s).\n")

    any_critical = False
    any_important = False

    for g in gaps:
        label = severity_label(g)
        print(f"  {label}")
        print(f"  File: {g['file']}:{g['line']}")

        if g["silent_bypass_missing"]:
            any_critical = True
            print(f"  ❌ SILENT BYPASS — missing: {g['silent_bypass_missing']}")
            print(f"     Kill switch fires but evaluates to SAFE because param is falsy.")
            print(f"     Fix: detect when sport matches and pass correct value explicitly.")

        if g["not_wired_missing"]:
            any_important = True
            print(f"  ⚠️  NOT WIRED — missing: {g['not_wired_missing']}")
            print(f"     Kill switch block skipped (guarded by `if param is not None`).")
            print(f"     Fix: fetch/pass data when sport requires it.")

        if g["parity_missing"]:
            print(f"  ℹ️  PARITY GAP — missing: {g['parity_missing']}")
            print(f"     Paper bets scored differently than live UI. Sharp score may diverge.")

        print(f"  Kwargs passed: {g['kwargs']}")
        print()

    # Summary
    print(f"{'='*70}")
    n_critical  = sum(1 for g in gaps if g["silent_bypass_missing"])
    n_important = sum(1 for g in gaps if g["not_wired_missing"])
    n_parity    = sum(1 for g in gaps if g["parity_missing"])
    n_ok        = sum(1 for g in gaps if not any([
        g["silent_bypass_missing"], g["not_wired_missing"], g["parity_missing"]
    ]))

    print(f"SUMMARY:")
    print(f"  ✅ OK:                {n_ok}")
    print(f"  🔴 CRITICAL:          {n_critical}")
    print(f"  🟡 IMPORTANT:         {n_important}")
    print(f"  🔵 PARITY gaps:       {n_parity}")
    print(f"{'='*70}\n")

    if strict and (any_critical or any_important):
        print("❌ --strict mode: CRITICAL or IMPORTANT gaps found. Failing.")
        return 1

    if any_critical:
        print("⚠️  CRITICAL gaps present — silent bypass means kill switches ARE NOT FIRING.")
        print("   Run without --strict to report; fix before next deployment.\n")

    return 0


def main():
    strict = "--strict" in sys.argv
    sys.exit(run_audit(strict=strict))


if __name__ == "__main__":
    main()
