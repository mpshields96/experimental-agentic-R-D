"""
core/analytics.py — Titanium-Agentic
======================================
Pure analytics functions for bet performance analysis.

Design principle (V37 Session 25 directive):
  All functions accept list[dict] — source-agnostic.
  Pages pass get_bets() (SQLite sandbox) or fetch_bets() (Supabase v36).
  Zero rewrites needed when promoting to V36.

Functions:
  compute_sharp_roi_correlation  — sharp score buckets vs ROI
  compute_rlm_correlation        — RLM-fired vs non-RLM win/ROI comparison
  compute_clv_beat_rate          — CLV > 0 rate + avg CLV by result
  compute_equity_curve           — cumulative P&L series
  compute_rolling_metrics        — 7/30/90-day win rate + ROI
  compute_book_breakdown         — per-book ROI and volume
  get_bet_counts                 — resolved/pending/total (used by sample guards)

Sample-size guard:
  MIN_RESOLVED = 30  — returned in every result as "min_required".
  If n_resolved < 30, status="inactive" and analytics values are omitted.
  Callers should check result["status"] before rendering charts.

Import rules: NO imports from core/ except standard library.
"""

from __future__ import annotations

from typing import Optional
import math

MIN_RESOLVED = 30  # calibration gate — matches MIN_BETS_FOR_CALIBRATION in calibration.py


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolved(bets: list[dict]) -> list[dict]:
    """Return only win/loss rows (not pending/void)."""
    return [b for b in bets if b.get("result") in ("win", "loss")]


def _pearson_r(xs: list[float], ys: list[float]) -> Optional[float]:
    """
    Pearson correlation coefficient. Returns None if < 3 pairs or zero variance.
    """
    n = len(xs)
    if n < 3:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))

    if denom_x == 0 or denom_y == 0:
        return None
    return num / (denom_x * denom_y)


def _roi(bets: list[dict]) -> float:
    """ROI% for a list of resolved bets. Returns 0.0 for empty/unstaked."""
    resolved = _resolved(bets)
    if not resolved:
        return 0.0
    total_profit = sum(b.get("profit", 0.0) for b in resolved)
    total_stake = sum(b.get("stake", 0.0) for b in resolved)
    if total_stake <= 0:
        return 0.0
    return round(total_profit / total_stake * 100, 2)


def _win_rate(bets: list[dict]) -> float:
    """Win rate% for resolved bets."""
    resolved = _resolved(bets)
    if not resolved:
        return 0.0
    wins = sum(1 for b in resolved if b.get("result") == "win")
    return round(wins / len(resolved) * 100, 1)


# ---------------------------------------------------------------------------
# Sample-size guard
# ---------------------------------------------------------------------------

def get_bet_counts(bets: list[dict]) -> dict:
    """
    Return counts by status — used by callers to render sample-size guards.

    Returns:
        {
          "total": int,
          "resolved": int,
          "pending": int,
          "wins": int,
          "losses": int,
          "min_required": int  (= MIN_RESOLVED)
        }
    """
    resolved = _resolved(bets)
    return {
        "total": len(bets),
        "resolved": len(resolved),
        "pending": sum(1 for b in bets if b.get("result") == "pending"),
        "wins": sum(1 for b in resolved if b.get("result") == "win"),
        "losses": sum(1 for b in resolved if b.get("result") == "loss"),
        "min_required": MIN_RESOLVED,
    }


# ---------------------------------------------------------------------------
# Core analytics functions
# ---------------------------------------------------------------------------

def compute_sharp_roi_correlation(bets: list[dict]) -> dict:
    """
    Bin resolved bets by sharp_score and compute ROI per bin.

    Bins: [0-20), [20-40), [40-60), [60-80), [80-100]
    Only bins with ≥ 3 resolved bets are included in correlation calc.

    Args:
        bets: list[dict] from get_bets() or equivalent. Each dict must have:
              sharp_score (int), result (str), profit (float), stake (float).

    Returns:
        {
          "status": "active" | "inactive",
          "n_resolved": int,
          "min_required": int,
          "bins": [
            {"label": "0-20", "n": int, "roi_pct": float, "win_rate": float},
            ...
          ],
          "correlation_r": float | None,  # Pearson r (sharp_score vs win/loss)
          "correlation_label": str,        # "strong+", "moderate+", "weak", etc.
          "mean_score_winners": float,
          "mean_score_losers": float,
        }
    """
    resolved = _resolved(bets)
    n_resolved = len(resolved)

    base = {
        "status": "inactive",
        "n_resolved": n_resolved,
        "min_required": MIN_RESOLVED,
        "bins": [],
        "correlation_r": None,
        "correlation_label": "insufficient data",
        "mean_score_winners": 0.0,
        "mean_score_losers": 0.0,
    }

    if n_resolved < MIN_RESOLVED:
        return base

    # Define bins
    bin_edges = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
    bin_labels = ["0–20", "20–40", "40–60", "60–80", "80–100"]
    bins = []

    for (lo, hi), label in zip(bin_edges, bin_labels):
        bucket = [b for b in resolved if lo <= b.get("sharp_score", 0) < hi]
        if not bucket:
            bins.append({"label": label, "n": 0, "roi_pct": 0.0, "win_rate": 0.0})
            continue
        bins.append({
            "label": label,
            "n": len(bucket),
            "roi_pct": _roi(bucket),
            "win_rate": _win_rate(bucket),
        })

    # Pearson r: sharp_score vs binary outcome (1=win, 0=loss)
    xs = [float(b.get("sharp_score", 0)) for b in resolved]
    ys = [1.0 if b.get("result") == "win" else 0.0 for b in resolved]
    r = _pearson_r(xs, ys)

    def _label(r_val: Optional[float]) -> str:
        if r_val is None:
            return "insufficient data"
        if r_val >= 0.5:
            return "strong positive"
        if r_val >= 0.3:
            return "moderate positive"
        if r_val >= 0.1:
            return "weak positive"
        if r_val >= -0.1:
            return "no correlation"
        if r_val >= -0.3:
            return "weak negative"
        if r_val >= -0.5:
            return "moderate negative"
        return "strong negative"

    winners = [b for b in resolved if b.get("result") == "win"]
    losers = [b for b in resolved if b.get("result") == "loss"]
    mean_w = sum(b.get("sharp_score", 0) for b in winners) / len(winners) if winners else 0.0
    mean_l = sum(b.get("sharp_score", 0) for b in losers) / len(losers) if losers else 0.0

    return {
        "status": "active",
        "n_resolved": n_resolved,
        "min_required": MIN_RESOLVED,
        "bins": bins,
        "correlation_r": round(r, 4) if r is not None else None,
        "correlation_label": _label(r),
        "mean_score_winners": round(mean_w, 1),
        "mean_score_losers": round(mean_l, 1),
    }


def compute_rlm_correlation(bets: list[dict]) -> dict:
    """
    Compare RLM-confirmed bets vs standard bets: win rate, ROI, count.

    Args:
        bets: list[dict]. Each dict must have:
              rlm_fired (int: 0 or 1), result (str), profit (float), stake (float).

    Returns:
        {
          "status": "active" | "inactive",
          "n_resolved": int,
          "min_required": int,
          "rlm": {"n": int, "win_rate": float, "roi_pct": float},
          "no_rlm": {"n": int, "win_rate": float, "roi_pct": float},
          "lift_win_rate": float,  # rlm.win_rate - no_rlm.win_rate
          "lift_roi": float,       # rlm.roi_pct - no_rlm.roi_pct
        }
    """
    resolved = _resolved(bets)
    n_resolved = len(resolved)

    base = {
        "status": "inactive",
        "n_resolved": n_resolved,
        "min_required": MIN_RESOLVED,
        "rlm": {"n": 0, "win_rate": 0.0, "roi_pct": 0.0},
        "no_rlm": {"n": 0, "win_rate": 0.0, "roi_pct": 0.0},
        "lift_win_rate": 0.0,
        "lift_roi": 0.0,
    }

    if n_resolved < MIN_RESOLVED:
        return base

    rlm_bets = [b for b in resolved if b.get("rlm_fired", 0) == 1]
    no_rlm_bets = [b for b in resolved if b.get("rlm_fired", 0) != 1]

    rlm_wr = _win_rate(rlm_bets)
    no_rlm_wr = _win_rate(no_rlm_bets)
    rlm_roi = _roi(rlm_bets)
    no_rlm_roi = _roi(no_rlm_bets)

    return {
        "status": "active",
        "n_resolved": n_resolved,
        "min_required": MIN_RESOLVED,
        "rlm": {"n": len(rlm_bets), "win_rate": rlm_wr, "roi_pct": rlm_roi},
        "no_rlm": {"n": len(no_rlm_bets), "win_rate": no_rlm_wr, "roi_pct": no_rlm_roi},
        "lift_win_rate": round(rlm_wr - no_rlm_wr, 1),
        "lift_roi": round(rlm_roi - no_rlm_roi, 2),
    }


def compute_clv_beat_rate(bets: list[dict]) -> dict:
    """
    CLV beat rate: % of resolved bets with positive CLV.
    Also breaks down avg CLV by result (win/loss).

    Args:
        bets: list[dict]. Each dict must have:
              clv (float), result (str).

    Returns:
        {
          "status": "active" | "inactive",
          "n_resolved": int,
          "n_with_clv": int,       # rows where clv != 0.0
          "min_required": int,
          "beat_rate": float,      # % with clv > 0
          "avg_clv": float,
          "avg_clv_winners": float,
          "avg_clv_losers": float,
          "clv_positive": int,
          "clv_negative": int,
          "clv_zero": int,
        }
    """
    resolved = _resolved(bets)
    n_resolved = len(resolved)

    base = {
        "status": "inactive",
        "n_resolved": n_resolved,
        "n_with_clv": 0,
        "min_required": MIN_RESOLVED,
        "beat_rate": 0.0,
        "avg_clv": 0.0,
        "avg_clv_winners": 0.0,
        "avg_clv_losers": 0.0,
        "clv_positive": 0,
        "clv_negative": 0,
        "clv_zero": 0,
    }

    if n_resolved < MIN_RESOLVED:
        return base

    clv_bets = [b for b in resolved if b.get("clv", 0.0) != 0.0]
    n_with_clv = len(clv_bets)

    if n_with_clv == 0:
        return {**base, "status": "active", "n_resolved": n_resolved}

    clv_vals = [b["clv"] for b in clv_bets]
    positive = sum(1 for v in clv_vals if v > 0)
    negative = sum(1 for v in clv_vals if v < 0)
    zero = n_resolved - len(clv_bets)

    winners = [b for b in clv_bets if b.get("result") == "win"]
    losers = [b for b in clv_bets if b.get("result") == "loss"]

    avg_w = sum(b["clv"] for b in winners) / len(winners) if winners else 0.0
    avg_l = sum(b["clv"] for b in losers) / len(losers) if losers else 0.0

    return {
        "status": "active",
        "n_resolved": n_resolved,
        "n_with_clv": n_with_clv,
        "min_required": MIN_RESOLVED,
        "beat_rate": round(positive / n_with_clv * 100, 1),
        "avg_clv": round(sum(clv_vals) / n_with_clv, 4),
        "avg_clv_winners": round(avg_w, 4),
        "avg_clv_losers": round(avg_l, 4),
        "clv_positive": positive,
        "clv_negative": negative,
        "clv_zero": zero,
    }


def compute_equity_curve(bets: list[dict]) -> dict:
    """
    Cumulative P&L series, sorted by logged_at.

    Args:
        bets: list[dict]. Each dict must have:
              logged_at (str), result (str), profit (float), stake (float).

    Returns:
        {
          "dates": list[str],        # ISO8601 timestamps (resolved bets only)
          "cumulative_pnl": list[float],
          "max_drawdown": float,     # max peak-to-trough drawdown in units
          "final_pnl": float,
          "n": int,
        }
    """
    resolved = sorted(_resolved(bets), key=lambda b: b.get("logged_at", ""))
    if not resolved:
        return {"dates": [], "cumulative_pnl": [], "max_drawdown": 0.0, "final_pnl": 0.0, "n": 0}

    cumulative = []
    running = 0.0
    peak = 0.0
    max_dd = 0.0

    for b in resolved:
        running += b.get("profit", 0.0)
        cumulative.append(round(running, 3))
        if running > peak:
            peak = running
        drawdown = peak - running
        if drawdown > max_dd:
            max_dd = drawdown

    return {
        "dates": [b.get("logged_at", "") for b in resolved],
        "cumulative_pnl": cumulative,
        "max_drawdown": round(max_dd, 3),
        "final_pnl": round(running, 3),
        "n": len(resolved),
    }


def compute_rolling_metrics(bets: list[dict], windows: tuple[int, ...] = (7, 30, 90)) -> dict:
    """
    Rolling win rate and ROI for given day windows.

    Args:
        bets:    list[dict] with logged_at, result, profit, stake.
        windows: tuple of day counts. Default (7, 30, 90).

    Returns:
        Dict keyed by window size:
        {
          7:  {"n": int, "win_rate": float, "roi_pct": float},
          30: {...},
          90: {...},
        }
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    result = {}

    for days in windows:
        cutoff = (now - timedelta(days=days)).isoformat()
        window_bets = [
            b for b in bets
            if b.get("logged_at", "") >= cutoff
        ]
        result[days] = {
            "n": len(_resolved(window_bets)),
            "win_rate": _win_rate(window_bets),
            "roi_pct": _roi(window_bets),
        }

    return result


def compute_book_breakdown(bets: list[dict]) -> list[dict]:
    """
    Per-book ROI, volume, and win rate for resolved bets with a book set.

    Args:
        bets: list[dict] with book (str), result, profit, stake.

    Returns:
        List of dicts sorted by roi_pct descending:
        [{"book": str, "n": int, "win_rate": float, "roi_pct": float}, ...]
    """
    resolved = _resolved(bets)
    books: dict[str, list] = {}

    for b in resolved:
        book = b.get("book", "").strip()
        if not book:
            book = "Unknown"
        books.setdefault(book, []).append(b)

    rows = []
    for book, book_bets in books.items():
        rows.append({
            "book": book,
            "n": len(book_bets),
            "win_rate": _win_rate(book_bets),
            "roi_pct": _roi(book_bets),
        })

    rows.sort(key=lambda r: r["roi_pct"], reverse=True)
    return rows
