#!/usr/bin/env python3
"""
bet_summary.py — CLI snapshot of paper bet performance and gate progress.

Usage:
    python3 scripts/bet_summary.py
    python3 scripts/bet_summary.py --db path/to/line_history.db
    python3 scripts/bet_summary.py --all    # include pending bets in table
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

GATE_TARGET = 10
DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "data", "line_history.db")

GRADE_ORDER = ["A", "B", "C", "NEAR_MISS", ""]
RESULT_EMOJI = {"win": "✅", "loss": "❌", "pending": "⏳"}


def connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"[ERROR] DB not found: {db_path}")
        sys.exit(1)
    return sqlite3.connect(db_path)


def load_bets(conn: sqlite3.Connection, include_pending: bool = False):
    where = "" if include_pending else "WHERE result != 'pending'"
    rows = conn.execute(f"""
        SELECT id, logged_at, matchup, market_type, target, price,
               edge_pct, grade, result, profit, stake, close_price, notes
        FROM bet_log
        {where}
        ORDER BY id DESC
    """).fetchall()
    return rows


def load_all(conn: sqlite3.Connection):
    return conn.execute("""
        SELECT result, COUNT(*), SUM(profit), SUM(stake), AVG(edge_pct), grade
        FROM bet_log
        WHERE result IN ('win','loss')
        GROUP BY result
    """).fetchall()


def fmt_pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def fmt_price(p: int) -> str:
    return f"+{p}" if p > 0 else str(p)


def bar(filled: int, total: int, width: int = 20) -> str:
    n = int(width * filled / total) if total else 0
    return f"[{'█' * n}{'░' * (width - n)}] {filled}/{total}"


def main():
    parser = argparse.ArgumentParser(description="Titanium paper bet summary")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to line_history.db")
    parser.add_argument("--all", action="store_true", help="Include pending bets in table")
    args = parser.parse_args()

    conn = connect(args.db)

    # ── Aggregate stats ──────────────────────────────────────────────────────
    resolved = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result IN ('win','loss')"
    ).fetchone()[0]
    pending  = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result = 'pending'"
    ).fetchone()[0]
    total    = resolved + pending

    wins     = conn.execute("SELECT COUNT(*) FROM bet_log WHERE result='win'").fetchone()[0]
    losses   = conn.execute("SELECT COUNT(*) FROM bet_log WHERE result='loss'").fetchone()[0]

    profit_row = conn.execute(
        "SELECT SUM(profit), SUM(stake) FROM bet_log WHERE result IN ('win','loss')"
    ).fetchone()
    total_profit = profit_row[0] or 0.0
    total_staked = profit_row[1] or 0.0
    roi = (total_profit / total_staked * 100) if total_staked else 0.0

    avg_edge = conn.execute(
        "SELECT AVG(edge_pct) FROM bet_log WHERE result IN ('win','loss')"
    ).fetchone()[0] or 0.0

    grade_counts = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT grade, COUNT(*) FROM bet_log WHERE result IN ('win','loss') GROUP BY grade"
        ).fetchall()
    }

    # CLV: only count bets that have event_id (post-Session 41 schema).
    # Pre-schema bets (event_id='') have no commence_time and can never capture CLV.
    clv_eligible = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE event_id != '' AND event_id IS NOT NULL"
    ).fetchone()[0]
    clv_captured = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE close_price != 0 AND close_price IS NOT NULL"
        " AND event_id != '' AND event_id IS NOT NULL"
    ).fetchone()[0]
    pre_schema = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE (event_id = '' OR event_id IS NULL)"
    ).fetchone()[0]

    # ── Header ───────────────────────────────────────────────────────────────
    print()
    print("━" * 58)
    print("  TITANIUM — PAPER BET SUMMARY")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("━" * 58)

    # ── Gate progress ────────────────────────────────────────────────────────
    gate_pct = resolved / GATE_TARGET * 100
    gate_status = "🔒 LOCKED" if resolved < GATE_TARGET else "🔓 UNLOCKED"
    print()
    print(f"  ANALYTICS GATE  {gate_status}")
    print(f"  {bar(resolved, GATE_TARGET)}  ({gate_pct:.0f}%)")
    print(f"  {pending} bet(s) pending resolution")
    print()

    # ── Performance ──────────────────────────────────────────────────────────
    win_rate = (wins / resolved * 100) if resolved else 0.0
    print(f"  RECORD          {wins}W – {losses}L  ({win_rate:.0f}% win rate)")
    print(f"  ROI             {roi:+.1f}%  (${total_profit:+.2f} on ${total_staked:.0f} staked)")
    print(f"  AVG EDGE        {avg_edge * 100:.1f}%")
    clv_label = f"{clv_captured}/{clv_eligible} eligible bets"
    if pre_schema:
        clv_label += f"  ({pre_schema} pre-schema, no event_id)"
    print(f"  CLV CAPTURED    {clv_label}")
    print()

    # ── Grade breakdown ───────────────────────────────────────────────────────
    print("  GRADE BREAKDOWN (resolved only)")
    for g in ["A", "B", "C", "NEAR_MISS"]:
        cnt = grade_counts.get(g, 0)
        if cnt or g in ("A", "B"):
            bar_w = int(cnt / max(resolved, 1) * 15)
            label = g if g != "NEAR_MISS" else "NM"
            print(f"    {label:8s}  {'█' * bar_w}{'░' * (15 - bar_w)}  {cnt}")
    print()

    # ── Recent bets table ────────────────────────────────────────────────────
    bets = load_bets(conn, include_pending=args.all)
    label = "ALL BETS" if args.all else "RESOLVED BETS"
    print(f"  {label} (most recent first)")
    print(f"  {'#':>3}  {'Result':7}  {'Grade':6}  {'Edge':>6}  {'Price':>6}  Matchup / Target")
    print("  " + "─" * 70)
    for row in bets[:15]:
        bid, logged_at, matchup, mkt, target, price, edge, grade, result, profit, stake, clv, notes = row
        emoji  = RESULT_EMOJI.get(result, "?")
        grade  = grade or "—"
        edge_s = f"{edge * 100:.1f}%" if edge else "—"
        price_s = fmt_price(price)
        matchup_short = matchup[:28] if len(matchup) > 28 else matchup
        target_short  = target[:20] if len(target) > 20 else target
        profit_s = f"${profit:+.2f}" if result != "pending" else ""
        print(f"  {bid:>3}  {emoji} {result:5}  {grade:6}  {edge_s:>6}  {price_s:>6}  {matchup_short} — {target_short}  {profit_s}")
    print()
    print("━" * 58)
    conn.close()


if __name__ == "__main__":
    main()
