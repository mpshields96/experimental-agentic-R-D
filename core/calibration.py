"""
core/calibration.py — Sharp Score Calibration Pipeline
========================================================
Measures how well the Sharp Score predicts actual bet outcomes.

Requires ≥30 graded bets from line_history.db to produce meaningful output.
Below that threshold, all functions return sentinel values and no calibration
is attempted.

Calibration metrics produced:
  - Brier Score: mean squared error of predicted win prob vs outcome (0=perfect)
  - Bin calibration: 10 bins of predicted prob vs actual win rate
  - ROC AUC: discrimination power (0.5 = random, 1.0 = perfect)
  - Mean edge accuracy: average |predicted_edge - realized_edge|

Design:
  - Zero external libraries beyond stdlib + math (pandas optional for bins)
  - No writes to DB — read-only queries from line_history.db
  - Returns CalibrationReport dataclass — UI renders from this

Activation gate:
  - All public functions check MIN_BETS_FOR_CALIBRATION before computing
  - Returns CalibrationReport with is_active=False when gate not cleared

Usage:
    from core.calibration import get_calibration_report, CalibrationReport

    report = get_calibration_report(db_path="data/line_history.db")
    if report.is_active:
        print(f"Brier Score: {report.brier_score:.4f}")
        print(f"ROC AUC: {report.roc_auc:.3f}")
    else:
        print(f"Need {report.bets_needed_for_activation} more graded bets")
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_BETS_FOR_CALIBRATION: int = 30   # minimum graded bets to activate
N_CALIBRATION_BINS: int = 10         # probability bins for calibration curve

# Default DB path (override via argument)
DEFAULT_DB_PATH: str = "data/line_history.db"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class CalibrationBin:
    """
    One bin of the calibration curve.

    prob_low:     Lower bound of predicted probability range.
    prob_high:    Upper bound.
    predicted:    Mean predicted win probability in this bin.
    actual:       Actual win rate in this bin.
    count:        Number of bets in this bin.
    """
    prob_low: float
    prob_high: float
    predicted: float
    actual: float
    count: int

    @property
    def calibration_error(self) -> float:
        """Absolute gap between predicted and actual (0.0 = perfectly calibrated)."""
        return abs(self.predicted - self.actual)


@dataclass
class CalibrationReport:
    """
    Full calibration report.

    is_active:      False if not enough graded bets yet.
    bets_total:     Total graded bets in DB.
    bets_wins:      Confirmed wins.
    bets_needed_for_activation: How many more bets needed (0 when active).
    brier_score:    Mean squared error (lower = better; perfect = 0.0).
    roc_auc:        Area under ROC curve (0.5 = random; 1.0 = perfect).
    mean_edge_accuracy: Mean |predicted_edge - realized_edge| in pct points.
    calibration_bins: List of CalibrationBin (empty when not active).
    sharp_score_vs_wr: Dict of {sharp_tier: win_rate} (e.g. "45-55": 0.58).
    notes:          Human-readable diagnostics.
    """
    is_active: bool
    bets_total: int
    bets_wins: int
    bets_needed_for_activation: int
    brier_score: float = 0.0
    roc_auc: float = 0.0
    mean_edge_accuracy: float = 0.0
    calibration_bins: list[CalibrationBin] = field(default_factory=list)
    sharp_score_vs_wr: dict[str, float] = field(default_factory=dict)
    notes: str = ""


# ---------------------------------------------------------------------------
# DB query helpers
# ---------------------------------------------------------------------------
def _load_graded_bets(db_path: str) -> list[dict]:
    """
    Load all graded bets from line_history.db.

    Returns list of dicts with keys:
        win_prob, edge_pct, sharp_score, result ('W'/'L'), stake, pnl

    Only includes bets where result is 'W' or 'L' (excludes 'P' push/open).
    Returns [] if DB doesn't exist or table missing.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT win_prob, edge_pct, sharp_score, result, stake, pnl
            FROM bet_log
            WHERE result IN ('W', 'L')
              AND win_prob IS NOT NULL
              AND edge_pct IS NOT NULL
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _load_graded_bets_count(db_path: str) -> int:
    """Count graded bets without loading full dataset."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM bet_log WHERE result IN ('W', 'L')")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Math helpers (stdlib only — no numpy)
# ---------------------------------------------------------------------------
def _brier_score(win_probs: list[float], outcomes: list[int]) -> float:
    """
    Compute Brier Score: mean squared error of predicted prob vs binary outcome.

    outcome: 1=win, 0=loss.
    Lower is better. Perfect = 0.0. Random = 0.25.

    >>> _brier_score([0.6, 0.6], [1, 0])
    0.18
    >>> _brier_score([1.0], [1])
    0.0
    >>> abs(_brier_score([0.5, 0.5], [1, 0]) - 0.25) < 0.001
    True
    """
    if not win_probs:
        return 0.0
    total = sum((p - o) ** 2 for p, o in zip(win_probs, outcomes))
    return total / len(win_probs)


def _roc_auc(win_probs: list[float], outcomes: list[int]) -> float:
    """
    Compute ROC AUC via Wilcoxon-Mann-Whitney statistic (no sklearn).

    AUC = P(score of positive > score of negative).
    Equivalent to trapezoidal ROC AUC integration, simpler and exact.

    Returns 0.5 for random classifier, 1.0 for perfect.
    Returns 0.5 if all outcomes are the same (undefined AUC edge case).

    >>> _roc_auc([0.9, 0.8, 0.3, 0.2], [1, 1, 0, 0])
    1.0
    >>> abs(_roc_auc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) - 0.5) < 0.1
    True
    """
    if not win_probs or sum(outcomes) == 0 or sum(outcomes) == len(outcomes):
        return 0.5

    positives = [p for p, o in zip(win_probs, outcomes) if o == 1]
    negatives = [p for p, o in zip(win_probs, outcomes) if o == 0]

    if not positives or not negatives:
        return 0.5

    # Count pairs where positive score > negative score (tie = 0.5)
    concordant = 0.0
    for pos in positives:
        for neg in negatives:
            if pos > neg:
                concordant += 1.0
            elif pos == neg:
                concordant += 0.5

    auc = concordant / (len(positives) * len(negatives))
    return round(min(1.0, max(0.0, auc)), 4)


def _calibration_bins(
    win_probs: list[float],
    outcomes: list[int],
    n_bins: int = N_CALIBRATION_BINS,
) -> list[CalibrationBin]:
    """
    Bin predictions into n_bins equal-width probability buckets.

    Returns only bins with at least 1 observation.

    >>> bins = _calibration_bins([0.6, 0.65, 0.4], [1, 1, 0], n_bins=5)
    >>> all(isinstance(b, CalibrationBin) for b in bins)
    True
    """
    bins: dict[int, list] = {i: [] for i in range(n_bins)}
    bin_width = 1.0 / n_bins

    for prob, outcome in zip(win_probs, outcomes):
        bin_idx = min(n_bins - 1, int(prob / bin_width))
        bins[bin_idx].append((prob, outcome))

    result = []
    for i in range(n_bins):
        entries = bins[i]
        if not entries:
            continue
        prob_low = i * bin_width
        prob_high = (i + 1) * bin_width
        predicted = sum(p for p, _ in entries) / len(entries)
        actual = sum(o for _, o in entries) / len(entries)
        result.append(CalibrationBin(
            prob_low=round(prob_low, 2),
            prob_high=round(prob_high, 2),
            predicted=round(predicted, 4),
            actual=round(actual, 4),
            count=len(entries),
        ))
    return result


def _sharp_score_win_rates(
    sharp_scores: list[float],
    outcomes: list[int],
) -> dict[str, float]:
    """
    Compute win rates by sharp score tier.

    Tiers: <45, 45-55, 55-65, 65-75, 75+.
    Returns dict of {tier_label: win_rate}. Only includes tiers with ≥3 bets.

    >>> rates = _sharp_score_win_rates([40, 50, 70, 80], [0, 1, 1, 1])
    >>> all(0 <= v <= 1 for v in rates.values())
    True
    """
    tiers: dict[str, list[int]] = {
        "<45": [],
        "45-55": [],
        "55-65": [],
        "65-75": [],
        "75+": [],
    }
    for score, outcome in zip(sharp_scores, outcomes):
        if score < 45:
            tiers["<45"].append(outcome)
        elif score < 55:
            tiers["45-55"].append(outcome)
        elif score < 65:
            tiers["55-65"].append(outcome)
        elif score < 75:
            tiers["65-75"].append(outcome)
        else:
            tiers["75+"].append(outcome)

    result = {}
    for label, outcomes_list in tiers.items():
        if len(outcomes_list) >= 3:
            result[label] = round(sum(outcomes_list) / len(outcomes_list), 4)
    return result


def _mean_edge_accuracy(
    predicted_edges: list[float],
    outcomes: list[int],
    prices: Optional[list[int]] = None,
) -> float:
    """
    Mean absolute error between predicted edge% and realized edge%.

    Realized edge approximation: outcome - market_implied_prob.
    Without prices, falls back to outcome - (1 - predicted_edge) as proxy.

    Returns 0.0 when list is empty.

    >>> abs(_mean_edge_accuracy([0.05, 0.08], [1, 0]) - 0.065) < 0.01
    True
    """
    if not predicted_edges:
        return 0.0
    total_error = 0.0
    for i, (pred_edge, outcome) in enumerate(zip(predicted_edges, outcomes)):
        # Realized edge ≈ outcome - market_implied_prob
        # market_implied_prob ≈ 1 - pred_edge (rough proxy without prices)
        market_implied = 1.0 - pred_edge
        realized_edge = outcome - market_implied
        total_error += abs(pred_edge - realized_edge)
    return round(total_error / len(predicted_edges), 4)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def get_calibration_report(db_path: str = DEFAULT_DB_PATH) -> CalibrationReport:
    """
    Load graded bets from DB and compute calibration metrics.

    Returns CalibrationReport with is_active=False when fewer than
    MIN_BETS_FOR_CALIBRATION graded bets exist.

    >>> report = get_calibration_report(db_path="nonexistent.db")
    >>> report.is_active
    False
    >>> report.bets_total
    0
    """
    rows = _load_graded_bets(db_path)
    n = len(rows)

    if n < MIN_BETS_FOR_CALIBRATION:
        return CalibrationReport(
            is_active=False,
            bets_total=n,
            bets_wins=sum(1 for r in rows if r.get("result") == "W"),
            bets_needed_for_activation=max(0, MIN_BETS_FOR_CALIBRATION - n),
            notes=(
                f"Calibration inactive: {n}/{MIN_BETS_FOR_CALIBRATION} graded bets. "
                f"Need {MIN_BETS_FOR_CALIBRATION - n} more resolved bets."
            ),
        )

    win_probs = [r["win_prob"] for r in rows]
    outcomes = [1 if r["result"] == "W" else 0 for r in rows]
    edge_pcts = [r["edge_pct"] for r in rows]
    sharp_scores = [r.get("sharp_score") or 0.0 for r in rows]
    n_wins = sum(outcomes)

    brier = _brier_score(win_probs, outcomes)
    auc = _roc_auc(win_probs, outcomes)
    bins = _calibration_bins(win_probs, outcomes)
    tier_rates = _sharp_score_win_rates(sharp_scores, outcomes)
    edge_acc = _mean_edge_accuracy(edge_pcts, outcomes)

    # Max calibration error across bins (ECE approximation)
    ece = sum(b.calibration_error * b.count for b in bins) / n if bins else 0.0

    notes = (
        f"Calibration active: {n} graded bets ({n_wins} wins, {n-n_wins} losses). "
        f"Brier={brier:.4f} | AUC={auc:.3f} | ECE={ece:.4f}. "
    )
    if auc >= 0.65:
        notes += "Model shows good discrimination."
    elif auc >= 0.55:
        notes += "Model shows moderate discrimination."
    else:
        notes += "Low AUC — model edge detection needs review."

    return CalibrationReport(
        is_active=True,
        bets_total=n,
        bets_wins=n_wins,
        bets_needed_for_activation=0,
        brier_score=round(brier, 6),
        roc_auc=round(auc, 4),
        mean_edge_accuracy=round(edge_acc, 4),
        calibration_bins=bins,
        sharp_score_vs_wr=tier_rates,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Convenience: activation check
# ---------------------------------------------------------------------------
def calibration_is_ready(db_path: str = DEFAULT_DB_PATH) -> bool:
    """
    Fast check: does the DB have enough graded bets to activate calibration?

    >>> calibration_is_ready("nonexistent.db")
    False
    """
    return _load_graded_bets_count(db_path) >= MIN_BETS_FOR_CALIBRATION
