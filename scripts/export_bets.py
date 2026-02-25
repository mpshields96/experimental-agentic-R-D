#!/usr/bin/env python3
"""
scripts/export_bets.py — Titanium-Agentic
==========================================
Official bet tracker export. Reads from SQLite bet_log and writes a
comprehensive CSV to data/bet_tracker_log.csv.

Run anytime to refresh the tracking file:
    python scripts/export_bets.py

Columns exported:
    id, logged_at, sport, matchup, market_type, target, price,
    implied_prob_pct, edge_pct, edge_tier, kelly_size, stake,
    result, profit, roi_pct, close_price, clv, clv_beat,
    sharp_score, rlm_fired, tags, book, days_to_game, line,
    signal, notes

CLV column (post-game only):
    Positive CLV = we beat closing line → edge was real
    Negative CLV = closing line moved against us → execution miss or noise
    0.0 / blank = pending (game not yet played)

Usage:
    python scripts/export_bets.py              # export all bets
    python scripts/export_bets.py --sport NBA  # filter by sport
    python scripts/export_bets.py --pending    # pending bets only

DO NOT add API calls or Streamlit calls to this file.
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

# Resolve repo root so this script works from any working directory
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _REPO_ROOT)

from core.line_logger import get_bets, get_pnl_summary  # noqa: E402

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------

OUTPUT_CSV = os.path.join(_REPO_ROOT, "data", "bet_tracker_log.csv")

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "id",
    "logged_at",
    "sport",
    "matchup",
    "market_type",
    "target",
    "price",
    "implied_prob_pct",
    "edge_pct",
    "edge_tier",
    "kelly_size",
    "stake",
    "result",
    "profit",
    "roi_pct",
    "close_price",
    "clv",
    "clv_beat",
    "sharp_score",
    "rlm_fired",
    "tags",
    "book",
    "days_to_game",
    "line",
    "signal",
    "notes",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def american_to_implied_prob(american: int) -> float:
    """Convert American odds to implied probability (0–100 scale)."""
    if american is None or american == 0:
        return 0.0
    if american > 0:
        return round(100.0 / (american + 100.0) * 100, 2)
    else:
        abs_odds = abs(american)
        return round(abs_odds / (abs_odds + 100.0) * 100, 2)


def edge_tier(edge_pct: float) -> str:
    """
    Classify edge into human-readable tier.

    LEAN    3.5% – 6.9%  — minimum qualifying edge
    STRONG  7.0% – 11.9% — solid edge
    GREAT  12.0% – 16.9% — strong conviction
    ELITE  17.0%+         — maximum edge signal
    """
    if edge_pct is None:
        return ""
    if edge_pct >= 17.0:
        return "ELITE"
    if edge_pct >= 12.0:
        return "GREAT"
    if edge_pct >= 7.0:
        return "STRONG"
    if edge_pct >= 3.5:
        return "LEAN"
    return "BELOW_MIN"


def clv_beat_label(row: dict) -> str:
    """
    Classify CLV outcome.

    PENDING  — game not yet played
    BEAT     — closed with positive CLV (edge was real)
    MISSED   — closing line moved against us (CLV negative)
    FLAT     — CLV at or very near zero
    """
    result = row.get("result", "pending")
    clv = row.get("clv", 0.0) or 0.0
    close_price = row.get("close_price", 0) or 0

    if result == "pending" or close_price == 0:
        return "PENDING"
    if clv > 0.005:
        return "BEAT"
    if clv < -0.005:
        return "MISSED"
    return "FLAT"


def row_roi_pct(row: dict) -> str:
    """Per-bet ROI% — only meaningful once a bet is graded."""
    stake = row.get("stake", 0.0) or 0.0
    profit = row.get("profit", 0.0) or 0.0
    result = row.get("result", "pending")
    if result == "pending" or stake == 0.0:
        return ""
    return f"{round(profit / stake * 100, 1)}"


def enrich(row: dict) -> dict:
    """Add computed columns to a raw bet_log row.

    Note: edge_pct and clv are stored as decimals in SQLite (0.172 = 17.2%).
    We convert to percentage scale here for display clarity.
    kelly_size is also stored as decimal (0.043 = 4.3% of bankroll).
    """
    price = row.get("price") or 0
    edge_raw = row.get("edge_pct") or 0.0
    clv_raw = row.get("clv") or 0.0
    kelly_raw = row.get("kelly_size") or 0.0
    rlm = row.get("rlm_fired", 0)

    # Convert decimals to human-readable percentages
    edge_pct_display = round(edge_raw * 100, 2) if edge_raw <= 1.0 else round(edge_raw, 2)
    clv_display = round(clv_raw * 100, 4) if (clv_raw != 0.0 and abs(clv_raw) <= 1.0) else round(clv_raw, 4)
    kelly_display = round(kelly_raw * 100, 3) if kelly_raw <= 1.0 else round(kelly_raw, 3)

    enriched = {
        **row,
        "edge_pct": edge_pct_display,       # now in % (17.2 not 0.172)
        "clv": clv_display,                  # now in % (3.1 not 0.031)
        "kelly_size": kelly_display,         # now in % of bankroll
        "implied_prob_pct": american_to_implied_prob(price),
        "edge_tier": edge_tier(edge_pct_display),
        "roi_pct": row_roi_pct(row),
        "clv_beat": clv_beat_label(row),
        "rlm_fired": "YES" if rlm else "NO",
    }
    return enriched


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_csv(sport_filter: str = None, pending_only: bool = False) -> str:
    """
    Export bet_log to data/bet_tracker_log.csv.

    Args:
        sport_filter:  Filter by sport (e.g. "NBA"). None = all sports.
        pending_only:  If True, only export pending bets.

    Returns:
        Path to the generated CSV file.
    """
    result_filter = "pending" if pending_only else None
    bets = get_bets(result_filter=result_filter, sport_filter=sport_filter, limit=5000)

    if not bets:
        print("[export_bets] No bets found matching filters.")
        return OUTPUT_CSV

    enriched = [enrich(b) for b in bets]

    # Sort: pending first (needs attention), then by logged_at descending
    enriched.sort(key=lambda r: (r["result"] != "pending", r["logged_at"]), reverse=False)
    enriched.sort(key=lambda r: r["result"] != "pending")

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)

    return OUTPUT_CSV


def print_summary(sport_filter: str = None, pending_only: bool = False) -> None:
    """Print a human-readable summary to stdout."""
    summary = get_pnl_summary()
    bets = get_bets(result_filter=None, sport_filter=sport_filter, limit=5000)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print()
    print("=" * 60)
    print("  TITANIUM BET TRACKER — OFFICIAL LOG")
    print(f"  Generated: {now}")
    print("=" * 60)
    print(f"  Total bets logged : {summary['total_bets']}")
    print(f"  Pending           : {summary['pending']}")
    print(f"  Wins              : {summary['wins']}")
    print(f"  Losses            : {summary['losses']}")
    print(f"  Win rate          : {summary['win_rate']}%")
    print(f"  Total profit      : {summary['total_profit']:+.2f} units")
    print(f"  ROI               : {summary['roi_pct']:+.2f}%")
    print(f"  Avg CLV           : {summary['avg_clv']:+.4f}")
    print("-" * 60)

    # Per-sport breakdown
    sports = sorted({b["sport"] for b in bets})
    for sport in sports:
        sport_bets = [b for b in bets if b["sport"] == sport]
        wins = sum(1 for b in sport_bets if b["result"] == "win")
        losses = sum(1 for b in sport_bets if b["result"] == "loss")
        pending = sum(1 for b in sport_bets if b["result"] == "pending")
        profit = sum(b.get("profit", 0.0) or 0.0 for b in sport_bets)
        print(
            f"  {sport:<8}  bets={len(sport_bets)}  "
            f"W={wins} L={losses} P={pending}  "
            f"profit={profit:+.2f}"
        )

    print("-" * 60)

    # Pending bets detail
    pending_bets = [b for b in bets if b["result"] == "pending"]
    if pending_bets:
        print(f"\n  PENDING BETS ({len(pending_bets)}):")
        print(f"  {'ID':<4}  {'Sport':<6}  {'Target':<30}  {'Price':<8}  {'Edge%':<7}  {'Sharp':<6}  {'Stake'}")
        print(f"  {'-'*4}  {'-'*6}  {'-'*30}  {'-'*8}  {'-'*7}  {'-'*6}  {'-'*5}")
        for b in pending_bets:
            edge_raw = b.get('edge_pct', 0) or 0.0
            edge_disp = edge_raw * 100 if edge_raw <= 1.0 else edge_raw
            print(
                f"  {b['id']:<4}  {b['sport']:<6}  {b['target']:<30}  "
                f"{b['price']:<8}  {edge_disp:<7.1f}  "
                f"{b.get('sharp_score', 0):<6}  {b.get('stake', 0):.2f}"
            )

    print()
    print(f"  CSV saved to: {OUTPUT_CSV}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export bet_log to CSV and print summary."
    )
    parser.add_argument("--sport", type=str, default=None, help="Filter by sport (e.g. NBA)")
    parser.add_argument("--pending", action="store_true", help="Export pending bets only")
    args = parser.parse_args()

    csv_path = export_csv(sport_filter=args.sport, pending_only=args.pending)
    print_summary(sport_filter=args.sport, pending_only=args.pending)


if __name__ == "__main__":
    main()
