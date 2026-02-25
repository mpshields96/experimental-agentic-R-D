"""
tests/test_analytics.py — Titanium-Agentic
============================================
Unit tests for core/analytics.py — pure analytics functions.

All tests are deterministic and network-free. Uses synthetic bet lists.
"""

import pytest
from core.analytics import (
    get_bet_counts,
    compute_sharp_roi_correlation,
    compute_rlm_correlation,
    compute_clv_beat_rate,
    compute_equity_curve,
    compute_rolling_metrics,
    compute_book_breakdown,
    MIN_RESOLVED,
    _pearson_r,
    _roi,
    _win_rate,
    _resolved,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _bet(result="win", sharp=50, rlm=0, clv=0.05, profit=1.0, stake=1.0,
         book="Pinnacle", sport="NBA", logged_at="2026-02-24T12:00:00+00:00",
         line=0.0, signal=""):
    return {
        "result": result,
        "sharp_score": sharp,
        "rlm_fired": rlm,
        "clv": clv,
        "profit": profit,
        "stake": stake,
        "book": book,
        "sport": sport,
        "logged_at": logged_at,
        "line": line,
        "signal": signal,
    }


def _make_resolved(n_win=20, n_loss=15, sharp=55, rlm=0, clv=0.05):
    """Build a list of 35 resolved bets: n_win wins + n_loss losses."""
    bets = []
    for i in range(n_win):
        bets.append(_bet(result="win", sharp=sharp, rlm=rlm, clv=clv, profit=1.0))
    for i in range(n_loss):
        bets.append(_bet(result="loss", sharp=sharp - 10, rlm=rlm, clv=-0.02, profit=-1.0))
    return bets


def _make_bets_with_gradient(n=40):
    """
    40 bets with increasing sharp score (10..100) alternating win/loss.
    Higher-score bets have better win rate.
    """
    bets = []
    for i in range(n):
        score = int(10 + (i / n) * 90)
        result = "win" if i % 3 != 0 else "loss"
        profit = 1.0 if result == "win" else -1.0
        bets.append(_bet(result=result, sharp=score, profit=profit))
    return bets


# ---------------------------------------------------------------------------
# _pearson_r
# ---------------------------------------------------------------------------

class TestPearsonR:
    def test_perfect_positive(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [1.0, 2.0, 3.0, 4.0]
        assert abs(_pearson_r(xs, ys) - 1.0) < 1e-9

    def test_perfect_negative(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [4.0, 3.0, 2.0, 1.0]
        assert abs(_pearson_r(xs, ys) - (-1.0)) < 1e-9

    def test_no_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [2.0, 2.0, 2.0, 2.0]
        assert _pearson_r(xs, ys) is None  # zero variance in y

    def test_insufficient_data(self):
        assert _pearson_r([1.0, 2.0], [1.0, 2.0]) is None

    def test_three_points_minimum(self):
        r = _pearson_r([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert r is not None
        assert abs(r - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# _roi and _win_rate helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_roi_empty(self):
        assert _roi([]) == 0.0

    def test_roi_no_stake(self):
        bets = [_bet(result="win", profit=1.0, stake=0.0)]
        assert _roi(bets) == 0.0

    def test_roi_basic(self):
        bets = [
            _bet(result="win", profit=1.0, stake=1.0),
            _bet(result="loss", profit=-1.0, stake=1.0),
        ]
        assert _roi(bets) == 0.0

    def test_roi_positive(self):
        bets = [
            _bet(result="win", profit=2.0, stake=1.0),
            _bet(result="win", profit=1.0, stake=1.0),
        ]
        assert _roi(bets) == 150.0  # 3 profit / 2 stake

    def test_win_rate_empty(self):
        assert _win_rate([]) == 0.0

    def test_win_rate_all_wins(self):
        bets = [_bet(result="win") for _ in range(4)]
        assert _win_rate(bets) == 100.0

    def test_win_rate_mixed(self):
        bets = [_bet(result="win")] * 3 + [_bet(result="loss")] * 1
        assert _win_rate(bets) == 75.0

    def test_resolved_excludes_pending(self):
        bets = [
            _bet(result="win"),
            _bet(result="pending"),
            _bet(result="loss"),
            _bet(result="void"),
        ]
        assert len(_resolved(bets)) == 2


# ---------------------------------------------------------------------------
# get_bet_counts
# ---------------------------------------------------------------------------

class TestGetBetCounts:
    def test_empty(self):
        result = get_bet_counts([])
        assert result["total"] == 0
        assert result["resolved"] == 0
        assert result["min_required"] == MIN_RESOLVED

    def test_mixed_statuses(self):
        bets = [
            _bet(result="win"),
            _bet(result="loss"),
            _bet(result="pending"),
            _bet(result="void"),
        ]
        result = get_bet_counts(bets)
        assert result["total"] == 4
        assert result["resolved"] == 2
        assert result["pending"] == 1
        assert result["wins"] == 1
        assert result["losses"] == 1

    def test_min_required_value(self):
        assert get_bet_counts([])["min_required"] == MIN_RESOLVED


# ---------------------------------------------------------------------------
# compute_sharp_roi_correlation
# ---------------------------------------------------------------------------

class TestSharpROICorrelation:
    def test_inactive_below_threshold(self):
        bets = _make_resolved(n_win=4, n_loss=4)  # only 8 resolved — below MIN_RESOLVED=10
        result = compute_sharp_roi_correlation(bets)
        assert result["status"] == "inactive"
        assert result["n_resolved"] == 8
        assert result["bins"] == []

    def test_active_above_threshold(self):
        bets = _make_resolved(n_win=20, n_loss=15)
        result = compute_sharp_roi_correlation(bets)
        assert result["status"] == "active"
        assert result["n_resolved"] == 35

    def test_bins_structure(self):
        bets = _make_resolved(n_win=20, n_loss=15)
        result = compute_sharp_roi_correlation(bets)
        assert len(result["bins"]) == 5
        labels = [b["label"] for b in result["bins"]]
        assert "40–60" in labels
        assert "80–100" in labels

    def test_bin_counts_correct(self):
        # All bets with sharp_score=55 should land in 40-60 bin
        bets = _make_resolved(n_win=20, n_loss=15, sharp=55)
        result = compute_sharp_roi_correlation(bets)
        forty_sixty = next(b for b in result["bins"] if b["label"] == "40–60")
        assert forty_sixty["n"] == 35

    def test_correlation_r_present(self):
        bets = _make_bets_with_gradient(40)
        result = compute_sharp_roi_correlation(bets)
        assert result["status"] == "active"
        # r may be None or float — just check it's there
        assert "correlation_r" in result

    def test_mean_score_winners_vs_losers(self):
        bets = (
            [_bet(result="win", sharp=70)] * 20
            + [_bet(result="loss", sharp=30)] * 15
        )
        result = compute_sharp_roi_correlation(bets)
        assert result["mean_score_winners"] == 70.0
        assert result["mean_score_losers"] == 30.0

    def test_pending_bets_excluded(self):
        bets = _make_resolved(n_win=20, n_loss=15) + [_bet(result="pending")]
        result = compute_sharp_roi_correlation(bets)
        assert result["n_resolved"] == 35  # pending not counted

    def test_correlation_label_types(self):
        bets = _make_resolved(n_win=25, n_loss=10)
        result = compute_sharp_roi_correlation(bets)
        assert isinstance(result["correlation_label"], str)
        assert len(result["correlation_label"]) > 0


# ---------------------------------------------------------------------------
# compute_rlm_correlation
# ---------------------------------------------------------------------------

class TestRLMCorrelation:
    def test_inactive_below_threshold(self):
        bets = [_bet(result="win", rlm=1)] * 4 + [_bet(result="loss", rlm=0)] * 4  # 8 < MIN_RESOLVED
        result = compute_rlm_correlation(bets)
        assert result["status"] == "inactive"

    def test_active_above_threshold(self):
        bets = (
            [_bet(result="win", rlm=1, profit=1.0, stake=1.0)] * 15
            + [_bet(result="loss", rlm=0, profit=-1.0, stake=1.0)] * 20
        )
        result = compute_rlm_correlation(bets)
        assert result["status"] == "active"
        assert result["n_resolved"] == 35

    def test_rlm_counts(self):
        bets = (
            [_bet(result="win", rlm=1)] * 10
            + [_bet(result="loss", rlm=1)] * 5
            + [_bet(result="win", rlm=0)] * 10
            + [_bet(result="loss", rlm=0)] * 10
        )
        result = compute_rlm_correlation(bets)
        assert result["rlm"]["n"] == 15
        assert result["no_rlm"]["n"] == 20

    def test_rlm_win_rate(self):
        bets = (
            [_bet(result="win", rlm=1)] * 10
            + [_bet(result="loss", rlm=1)] * 10
            + [_bet(result="win", rlm=0)] * 10
            + [_bet(result="loss", rlm=0)] * 10
        )
        result = compute_rlm_correlation(bets)
        assert result["rlm"]["win_rate"] == 50.0
        assert result["no_rlm"]["win_rate"] == 50.0
        assert result["lift_win_rate"] == 0.0

    def test_rlm_higher_win_rate(self):
        bets = (
            [_bet(result="win", rlm=1, profit=1.0, stake=1.0)] * 20
            + [_bet(result="loss", rlm=0, profit=-1.0, stake=1.0)] * 15
        )
        result = compute_rlm_correlation(bets)
        assert result["rlm"]["win_rate"] == 100.0
        assert result["no_rlm"]["win_rate"] == 0.0
        assert result["lift_win_rate"] == 100.0

    def test_lift_roi_computed(self):
        bets = (
            [_bet(result="win", rlm=1, profit=2.0, stake=1.0)] * 20
            + [_bet(result="loss", rlm=0, profit=-1.0, stake=1.0)] * 15
        )
        result = compute_rlm_correlation(bets)
        assert result["rlm"]["roi_pct"] > result["no_rlm"]["roi_pct"]


# ---------------------------------------------------------------------------
# compute_clv_beat_rate
# ---------------------------------------------------------------------------

class TestCLVBeatRate:
    def test_inactive_below_threshold(self):
        bets = [_bet(result="win", clv=0.03)] * 4 + [_bet(result="loss", clv=-0.01)] * 4  # 8 < MIN_RESOLVED
        result = compute_clv_beat_rate(bets)
        assert result["status"] == "inactive"

    def test_active_above_threshold(self):
        bets = [_bet(result="win", clv=0.05)] * 20 + [_bet(result="loss", clv=-0.02)] * 15
        result = compute_clv_beat_rate(bets)
        assert result["status"] == "active"

    def test_beat_rate_all_positive(self):
        bets = [_bet(result="win", clv=0.05)] * 20 + [_bet(result="loss", clv=0.01)] * 15
        result = compute_clv_beat_rate(bets)
        assert result["beat_rate"] == 100.0

    def test_beat_rate_mixed(self):
        bets = (
            [_bet(result="win", clv=0.05)] * 20
            + [_bet(result="loss", clv=-0.03)] * 15
        )
        result = compute_clv_beat_rate(bets)
        assert result["clv_positive"] == 20
        assert result["clv_negative"] == 15
        assert abs(result["beat_rate"] - 57.1) < 0.2

    def test_avg_clv_winners_losers(self):
        bets = (
            [_bet(result="win", clv=0.10)] * 20
            + [_bet(result="loss", clv=-0.05)] * 15
        )
        result = compute_clv_beat_rate(bets)
        assert abs(result["avg_clv_winners"] - 0.10) < 1e-6
        assert abs(result["avg_clv_losers"] - (-0.05)) < 1e-6

    def test_no_clv_data(self):
        bets = [_bet(result="win", clv=0.0)] * 20 + [_bet(result="loss", clv=0.0)] * 15
        result = compute_clv_beat_rate(bets)
        assert result["status"] == "active"
        assert result["n_with_clv"] == 0
        assert result["beat_rate"] == 0.0


# ---------------------------------------------------------------------------
# compute_equity_curve
# ---------------------------------------------------------------------------

class TestEquityCurve:
    def test_empty(self):
        result = compute_equity_curve([])
        assert result["dates"] == []
        assert result["cumulative_pnl"] == []
        assert result["n"] == 0

    def test_single_win(self):
        bets = [_bet(result="win", profit=2.0)]
        result = compute_equity_curve(bets)
        assert result["cumulative_pnl"] == [2.0]
        assert result["final_pnl"] == 2.0

    def test_cumulative_series(self):
        bets = [
            _bet(result="win", profit=1.0, logged_at="2026-01-01T00:00:00+00:00"),
            _bet(result="loss", profit=-1.0, logged_at="2026-01-02T00:00:00+00:00"),
            _bet(result="win", profit=2.0, logged_at="2026-01-03T00:00:00+00:00"),
        ]
        result = compute_equity_curve(bets)
        assert result["cumulative_pnl"] == [1.0, 0.0, 2.0]
        assert result["final_pnl"] == 2.0

    def test_max_drawdown(self):
        bets = [
            _bet(result="win", profit=3.0, logged_at="2026-01-01T00:00:00+00:00"),
            _bet(result="loss", profit=-2.0, logged_at="2026-01-02T00:00:00+00:00"),
            _bet(result="win", profit=1.0, logged_at="2026-01-03T00:00:00+00:00"),
        ]
        result = compute_equity_curve(bets)
        assert result["max_drawdown"] == 2.0

    def test_pending_excluded(self):
        bets = [
            _bet(result="win", profit=1.0),
            _bet(result="pending", profit=0.0),
        ]
        result = compute_equity_curve(bets)
        assert result["n"] == 1


# ---------------------------------------------------------------------------
# compute_rolling_metrics
# ---------------------------------------------------------------------------

class TestRollingMetrics:
    def test_returns_all_windows(self):
        bets = _make_resolved(n_win=5, n_loss=5)
        result = compute_rolling_metrics(bets)
        assert 7 in result
        assert 30 in result
        assert 90 in result

    def test_custom_windows(self):
        bets = _make_resolved(n_win=5, n_loss=5)
        result = compute_rolling_metrics(bets, windows=(14, 60))
        assert 14 in result
        assert 60 in result
        assert 7 not in result

    def test_recent_bets_counted(self):
        # All bets are very recent (logged today)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        bets = [
            _bet(result="win", logged_at=now, profit=1.0, stake=1.0),
            _bet(result="loss", logged_at=now, profit=-1.0, stake=1.0),
        ]
        result = compute_rolling_metrics(bets, windows=(7,))
        assert result[7]["n"] == 2

    def test_empty_bets(self):
        result = compute_rolling_metrics([])
        assert result[7]["n"] == 0
        assert result[30]["roi_pct"] == 0.0


# ---------------------------------------------------------------------------
# compute_book_breakdown
# ---------------------------------------------------------------------------

class TestBookBreakdown:
    def test_empty(self):
        result = compute_book_breakdown([])
        assert result == []

    def test_single_book(self):
        bets = [_bet(result="win", book="Pinnacle", profit=1.0, stake=1.0)] * 5
        bets += [_bet(result="loss", book="Pinnacle", profit=-1.0, stake=1.0)] * 5
        result = compute_book_breakdown(bets)
        assert len(result) == 1
        assert result[0]["book"] == "Pinnacle"
        assert result[0]["n"] == 10
        assert result[0]["roi_pct"] == 0.0

    def test_multiple_books(self):
        bets = (
            [_bet(result="win", book="Pinnacle", profit=2.0, stake=1.0)] * 5
            + [_bet(result="loss", book="DraftKings", profit=-1.0, stake=1.0)] * 5
        )
        result = compute_book_breakdown(bets)
        assert len(result) == 2
        # Pinnacle should be first (higher ROI)
        assert result[0]["book"] == "Pinnacle"

    def test_missing_book_label(self):
        bets = [_bet(result="win", book="", profit=1.0, stake=1.0)] * 3
        bets += [_bet(result="loss", book="", profit=-1.0, stake=1.0)] * 2
        result = compute_book_breakdown(bets)
        assert result[0]["book"] == "Unknown"

    def test_sorted_by_roi(self):
        bets = (
            [_bet(result="win", book="A", profit=3.0, stake=1.0)] * 5
            + [_bet(result="win", book="B", profit=1.0, stake=1.0)] * 5
            + [_bet(result="loss", book="C", profit=-1.0, stake=1.0)] * 5
        )
        result = compute_book_breakdown(bets)
        roi_list = [r["roi_pct"] for r in result]
        assert roi_list == sorted(roi_list, reverse=True)

    def test_pending_excluded(self):
        bets = (
            [_bet(result="win", book="Pinnacle")] * 3
            + [_bet(result="pending", book="Pinnacle")] * 5
        )
        result = compute_book_breakdown(bets)
        assert result[0]["n"] == 3  # only resolved
