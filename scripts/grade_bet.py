#!/usr/bin/env python3
"""
scripts/grade_bet.py — Titanium-Agentic
========================================
CLI tool to grade a bet after game completion.

Updates the bet_log with:
  - result       : "win" / "loss" / "void"
  - stake        : actual units wagered (if not already set)
  - close_price  : closing market price (American odds)
  - profit       : auto-computed from result + stake + price
  - clv          : closing line value (auto-computed from close_price)

After grading, automatically re-generates data/bet_tracker_log.csv.

Usage:
    # Grade bet #1 as a WIN, $50 stake, closed at -108
    python scripts/grade_bet.py --id 1 --result win --stake 50 --close -108

    # Grade bet #2 as a LOSS (stake already set in DB, no close price)
    python scripts/grade_bet.py --id 2 --result loss

    # Grade as void (line moved, no action)
    python scripts/grade_bet.py --id 3 --result void

    # Review pending bets before grading
    python scripts/grade_bet.py --list

DO NOT add API calls or Streamlit calls to this file.
"""

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _REPO_ROOT)

from core.line_logger import get_bets, update_bet_result  # noqa: E402


def list_pending() -> None:
    """Print all pending bets in a grading-ready format."""
    bets = get_bets(result_filter="pending", limit=200)
    if not bets:
        print("[grade_bet] No pending bets found.")
        return

    print()
    print(f"  {'ID':<4}  {'Sport':<6}  {'Target':<30}  {'Price':<8}  {'Edge%':<7}  {'Stake':<7}  {'Tags'}")
    print(f"  {'-'*4}  {'-'*6}  {'-'*30}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*20}")
    for b in bets:
        print(
            f"  {b['id']:<4}  {b['sport']:<6}  {b['target']:<30}  "
            f"{b['price']:<8}  {b.get('edge_pct', 0):<7.1f}  "
            f"{b.get('stake', 0):<7.2f}  {b.get('tags', '')}"
        )
    print()


def grade(bet_id: int, result: str, stake: float, close_price: int) -> None:
    """Grade a single bet."""
    # Validate result
    valid = {"win", "loss", "void"}
    if result not in valid:
        print(f"[grade_bet] ERROR: result must be one of {valid}, got '{result}'")
        sys.exit(1)

    # Check the bet exists
    all_bets = get_bets(limit=5000)
    target_bet = next((b for b in all_bets if b["id"] == bet_id), None)

    if target_bet is None:
        print(f"[grade_bet] ERROR: bet ID {bet_id} not found.")
        sys.exit(1)

    if target_bet["result"] != "pending":
        print(
            f"[grade_bet] WARNING: bet {bet_id} already graded as '{target_bet['result']}'. "
            "Overwriting..."
        )

    # If stake not provided, use the value already in DB
    if stake <= 0.0:
        stake = target_bet.get("stake") or 0.0
        if stake <= 0.0 and result != "void":
            print(f"[grade_bet] ERROR: stake is 0 for bet {bet_id}. Provide --stake <units>.")
            sys.exit(1)

    print(f"\n[grade_bet] Grading bet #{bet_id}:")
    print(f"  Target     : {target_bet['target']}")
    print(f"  Sport      : {target_bet['sport']}")
    print(f"  Matchup    : {target_bet['matchup']}")
    print(f"  Bet price  : {target_bet['price']}")
    print(f"  Stake      : {stake} units")
    print(f"  Result     : {result.upper()}")
    if close_price:
        print(f"  Close price: {close_price}")
    print()

    update_bet_result(
        bet_id=bet_id,
        result=result,
        stake=stake,
        close_price=close_price if close_price else None,
    )
    print(f"[grade_bet] ✓ Bet #{bet_id} graded as {result.upper()}")

    # Regenerate the tracking CSV
    try:
        from scripts.export_bets import export_csv, print_summary
        csv_path = export_csv()
        print_summary()
        print(f"[grade_bet] ✓ Tracking CSV updated: {csv_path}")
    except Exception as exc:
        print(f"[grade_bet] WARNING: Could not regenerate CSV: {exc}")
        print("[grade_bet]   Run: python scripts/export_bets.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grade a bet with result and closing price."
    )
    parser.add_argument("--id", type=int, help="Bet ID to grade")
    parser.add_argument(
        "--result", type=str, choices=["win", "loss", "void"],
        help="Bet outcome"
    )
    parser.add_argument(
        "--stake", type=float, default=0.0,
        help="Units wagered (uses DB value if not provided)"
    )
    parser.add_argument(
        "--close", type=int, default=0,
        help="Closing American odds (e.g. -108 or +115)"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all pending bets (no grading)"
    )

    args = parser.parse_args()

    if args.list:
        list_pending()
        return

    if not args.id or not args.result:
        parser.print_help()
        sys.exit(1)

    grade(
        bet_id=args.id,
        result=args.result,
        stake=args.stake,
        close_price=args.close,
    )


if __name__ == "__main__":
    main()
