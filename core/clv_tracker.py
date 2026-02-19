"""
core/clv_tracker.py — CLV Tracker (Session 7 — R&D EXP 1)
============================================================
Closing Line Value persistence layer.

Responsibilities:
- log_clv_snapshot(): append one CLV observation to CSV
- read_clv_log():     return recent entries as list[dict]
- clv_summary():      aggregate stats from a set of entries
- print_clv_report(): human-readable stdout report for R&D

This module does NO math. All CLV computation is in core/math_engine.py:
  calculate_clv(open_price, close_price, bet_price) -> float
  clv_grade(clv)                                    -> str

Wire-in point (bet_tracker.py):
  After update_bet_result() — call log_clv_snapshot() with
  the event_id, side, open price (from _OPEN_PRICE_CACHE),
  and the close_price the user entered when grading the bet.

CSV columns: timestamp, event_id, side, open_price, bet_price, close_price, clv_pct, grade

DO NOT add API calls or Streamlit imports to this file.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Default CSV path — relative to sandbox root.
# Overridable via CLV_LOG_PATH env var for testing.
_DEFAULT_LOG_PATH = str(Path(__file__).parent.parent / "data" / "clv_log.csv")

_CSV_HEADERS = [
    "timestamp",
    "event_id",
    "side",
    "open_price",
    "bet_price",
    "close_price",
    "clv_pct",
    "grade",
]

# Gate: minimum entries before summary is considered statistically meaningful.
CLV_GATE = 30


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_path() -> str:
    return os.environ.get("CLV_LOG_PATH", _DEFAULT_LOG_PATH)


def _ensure_csv(path: str) -> None:
    """Create CSV with headers if it doesn't exist. No-op if already exists."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        with open(p, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_HEADERS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_clv_snapshot(
    event_id: str,
    side: str,
    open_price: int,
    bet_price: int,
    close_price: int,
    log_path: Optional[str] = None,
) -> dict:
    """
    Append one CLV observation to the CSV log.

    Computes CLV inline (bet_price vs close_price) and writes a row.
    open_price is stored for reference but not used in the CLV formula
    (matching math_engine.calculate_clv behaviour).

    Args:
        event_id:    Odds API event ID string.
        side:        Team name, "Over", or "Under".
        open_price:  American odds at open (from _OPEN_PRICE_CACHE).
        bet_price:   American odds when the bet was placed.
        close_price: American odds at market close.
        log_path:    Override CSV path (defaults to data/clv_log.csv).

    Returns:
        Dict of the logged row (for confirmation / test assertions).

    >>> import os; os.environ["CLV_LOG_PATH"] = "/tmp/test_clv.csv"
    >>> row = log_clv_snapshot("ev001", "Duke", -110, -110, -120)
    >>> row["event_id"]
    'ev001'
    >>> row["grade"] in ("EXCELLENT", "GOOD", "NEUTRAL", "POOR")
    True
    """
    from core.math_engine import calculate_clv, clv_grade, implied_probability

    clv = calculate_clv(open_price, close_price, bet_price)
    grade = clv_grade(clv)

    path = log_path or _log_path()
    _ensure_csv(path)

    timestamp = datetime.now(timezone.utc).isoformat()
    row = {
        "timestamp":   timestamp,
        "event_id":    event_id,
        "side":        side,
        "open_price":  open_price,
        "bet_price":   bet_price,
        "close_price": close_price,
        "clv_pct":     round(clv * 100, 4),  # stored as %, e.g. 1.88 not 0.0188
        "grade":       grade,
    }

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
        writer.writerow(row)

    return row


def read_clv_log(last_n: Optional[int] = None, log_path: Optional[str] = None) -> list[dict]:
    """
    Read entries from the CLV CSV log.

    Args:
        last_n:   Return only the most recent N entries. None = return all.
        log_path: Override CSV path.

    Returns:
        List of dicts. Each dict has the 8 CSV columns.
        clv_pct is returned as float (e.g. 1.88 for 1.88%).
        Returns empty list if file doesn't exist.

    >>> import os; os.environ["CLV_LOG_PATH"] = "/tmp/test_clv_read.csv"
    >>> _ = log_clv_snapshot("ev001", "Duke", -110, -110, -115, "/tmp/test_clv_read.csv")
    >>> entries = read_clv_log(log_path="/tmp/test_clv_read.csv")
    >>> len(entries) >= 1
    True
    >>> isinstance(entries[0]["clv_pct"], float)
    True
    """
    path = log_path or _log_path()
    p = Path(path)
    if not p.exists():
        return []

    entries = []
    with open(p, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["clv_pct"]     = float(row["clv_pct"])
                row["open_price"]  = int(row["open_price"])
                row["bet_price"]   = int(row["bet_price"])
                row["close_price"] = int(row["close_price"])
            except (ValueError, KeyError):
                pass
            entries.append(row)

    if last_n is not None:
        entries = entries[-last_n:]

    return entries


def clv_summary(entries: list[dict]) -> dict:
    """
    Aggregate CLV statistics from a list of log entries.

    Gate: if len(entries) < CLV_GATE (30), returns below_gate=True.
    At least 30 observations needed for the summary to be statistically
    meaningful (matching titanium-experimental design).

    Args:
        entries: List of dicts from read_clv_log().

    Returns:
        {
            "n":              int,
            "avg_clv_pct":    float,   # mean CLV in percentage points
            "positive_rate":  float,   # fraction with clv_pct > 0
            "max_clv_pct":    float,
            "min_clv_pct":    float,
            "below_gate":     bool,    # True if n < CLV_GATE
            "verdict":        str,     # "STRONG EDGE CAPTURE" / "MARGINAL" / "NO EDGE" / "INSUFFICIENT DATA"
        }

    >>> clv_summary([])["verdict"]
    'INSUFFICIENT DATA'
    >>> entries = [{"clv_pct": 2.0, "grade": "EXCELLENT"}, {"clv_pct": -0.5, "grade": "POOR"}]
    >>> s = clv_summary(entries)
    >>> s["n"]
    2
    >>> s["below_gate"]
    True
    """
    if not entries:
        return {
            "n":             0,
            "avg_clv_pct":   0.0,
            "positive_rate": 0.0,
            "max_clv_pct":   0.0,
            "min_clv_pct":   0.0,
            "below_gate":    True,
            "verdict":       "INSUFFICIENT DATA",
        }

    clv_values = [float(e.get("clv_pct", 0)) for e in entries]
    n = len(clv_values)
    avg = sum(clv_values) / n
    positive_rate = sum(1 for v in clv_values if v > 0) / n
    max_clv = max(clv_values)
    min_clv = min(clv_values)
    below_gate = n < CLV_GATE

    if below_gate:
        verdict = "INSUFFICIENT DATA"
    elif avg >= 1.5 and positive_rate >= 0.60:
        verdict = "STRONG EDGE CAPTURE"
    elif avg >= 0.5 and positive_rate >= 0.50:
        verdict = "MARGINAL"
    else:
        verdict = "NO EDGE"

    return {
        "n":             n,
        "avg_clv_pct":   round(avg, 4),
        "positive_rate": round(positive_rate, 4),
        "max_clv_pct":   round(max_clv, 4),
        "min_clv_pct":   round(min_clv, 4),
        "below_gate":    below_gate,
        "verdict":       verdict,
    }


def print_clv_report(log_path: Optional[str] = None) -> None:
    """
    Print a human-readable CLV summary to stdout.

    Reads all entries from the log, computes summary, prints.
    Intended for R&D CLI runs and HANDOFF.md reporting.

    Args:
        log_path: Override CSV path.
    """
    entries = read_clv_log(log_path=log_path)
    summary = clv_summary(entries)
    path = log_path or _log_path()

    print(f"\n{'='*60}")
    print(f"  CLV TRACKER REPORT — {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")
    print(f"  Log file         : {path}")
    print(f"  Total entries    : {summary['n']}")
    print(f"  Avg CLV          : {summary['avg_clv_pct']:+.2f}%")
    print(f"  Positive rate    : {summary['positive_rate']:.1%}")
    print(f"  Max CLV          : {summary['max_clv_pct']:+.2f}%")
    print(f"  Min CLV          : {summary['min_clv_pct']:+.2f}%")
    print(f"  Gate ({CLV_GATE} entries) : {'BELOW — need more data' if summary['below_gate'] else 'PASSED'}")
    print(f"  Verdict          : {summary['verdict']}")

    if entries:
        # Grade distribution
        grades = {}
        for e in entries:
            g = e.get("grade", "UNKNOWN")
            grades[g] = grades.get(g, 0) + 1
        print()
        print("  Grade breakdown:")
        for grade, count in sorted(grades.items()):
            bar = "█" * min(count, 30)
            print(f"    {grade:<12} {count:>3}  {bar}")

    print(f"{'='*60}\n")
