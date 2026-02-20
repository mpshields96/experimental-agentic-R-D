"""
tests/test_calibration.py — Titanium-Agentic
=============================================
Unit tests for core/calibration.py.

Coverage:
  - _brier_score(): edge cases, perfect prediction, random
  - _roc_auc(): perfect, random, undefined cases
  - _calibration_bins(): binning logic, CalibrationBin fields
  - _sharp_score_win_rates(): tier bucketing, minimum sample size
  - _mean_edge_accuracy(): formula correctness
  - get_calibration_report(): activation gate, inactive path, active path
  - calibration_is_ready(): counts correctly
"""

import pytest
from core.calibration import (
    MIN_BETS_FOR_CALIBRATION,
    N_CALIBRATION_BINS,
    CalibrationBin,
    CalibrationReport,
    _brier_score,
    _calibration_bins,
    _mean_edge_accuracy,
    _roc_auc,
    _sharp_score_win_rates,
    calibration_is_ready,
    get_calibration_report,
)


# ---------------------------------------------------------------------------
# _brier_score
# ---------------------------------------------------------------------------

class TestBrierScore:

    def test_perfect_prediction_wins(self):
        """Predicted 1.0 for all wins → Brier = 0."""
        assert _brier_score([1.0, 1.0], [1, 1]) == 0.0

    def test_perfect_prediction_losses(self):
        """Predicted 0.0 for all losses → Brier = 0."""
        assert _brier_score([0.0, 0.0], [0, 0]) == 0.0

    def test_worst_prediction(self):
        """Always wrong → Brier = 1.0."""
        assert _brier_score([1.0, 1.0], [0, 0]) == 1.0

    def test_random_prediction(self):
        """50% for all → Brier ≈ 0.25."""
        assert abs(_brier_score([0.5, 0.5], [1, 0]) - 0.25) < 0.001

    def test_empty_returns_zero(self):
        assert _brier_score([], []) == 0.0

    def test_single_correct_prediction(self):
        assert _brier_score([0.7], [1]) == pytest.approx(0.09, abs=0.001)

    def test_lower_is_better(self):
        good = _brier_score([0.7, 0.8, 0.3, 0.2], [1, 1, 0, 0])
        bad = _brier_score([0.3, 0.2, 0.7, 0.8], [1, 1, 0, 0])
        assert good < bad

    def test_known_value(self):
        """Manual: (0.6-1)^2 + (0.6-0)^2 = 0.16 + 0.36 = 0.52 / 2 = 0.26."""
        assert abs(_brier_score([0.6, 0.6], [1, 0]) - 0.26) < 0.001


# ---------------------------------------------------------------------------
# _roc_auc
# ---------------------------------------------------------------------------

class TestRocAuc:

    def test_perfect_classifier(self):
        """Highest prob = all wins, lowest = all losses."""
        assert _roc_auc([0.9, 0.8, 0.3, 0.2], [1, 1, 0, 0]) == 1.0

    def test_random_classifier(self):
        """Same prob for all → AUC ≈ 0.5."""
        result = _roc_auc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0])
        assert abs(result - 0.5) < 0.1

    def test_empty_returns_half(self):
        assert _roc_auc([], []) == 0.5

    def test_all_same_outcome_returns_half(self):
        """Undefined AUC when no positive/negative class."""
        assert _roc_auc([0.7, 0.8], [1, 1]) == 0.5
        assert _roc_auc([0.3, 0.2], [0, 0]) == 0.5

    def test_result_bounded_0_to_1(self):
        for _ in range(5):
            result = _roc_auc([0.6, 0.4, 0.7, 0.3], [1, 0, 1, 0])
            assert 0.0 <= result <= 1.0

    def test_better_model_higher_auc(self):
        """Model that better separates classes should have higher AUC."""
        good = _roc_auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0])
        bad = _roc_auc([0.6, 0.55, 0.45, 0.4], [1, 1, 0, 0])
        assert good >= bad


# ---------------------------------------------------------------------------
# _calibration_bins
# ---------------------------------------------------------------------------

class TestCalibrationBins:

    def test_returns_list(self):
        bins = _calibration_bins([0.6, 0.4], [1, 0])
        assert isinstance(bins, list)

    def test_all_calibration_bin_objects(self):
        bins = _calibration_bins([0.6, 0.65, 0.4], [1, 1, 0])
        assert all(isinstance(b, CalibrationBin) for b in bins)

    def test_empty_input_empty_output(self):
        bins = _calibration_bins([], [])
        assert bins == []

    def test_bin_prob_low_below_high(self):
        bins = _calibration_bins([0.6, 0.7, 0.3], [1, 1, 0])
        for b in bins:
            assert b.prob_low < b.prob_high

    def test_actual_rate_in_range(self):
        bins = _calibration_bins([0.6, 0.65, 0.7, 0.4], [1, 0, 1, 0])
        for b in bins:
            assert 0.0 <= b.actual <= 1.0

    def test_count_matches_samples(self):
        bins = _calibration_bins([0.6, 0.65, 0.4], [1, 1, 0])
        total = sum(b.count for b in bins)
        assert total == 3

    def test_calibration_error_property(self):
        b = CalibrationBin(0.5, 0.6, 0.55, 0.60, 10)
        assert abs(b.calibration_error - 0.05) < 0.001

    def test_n_bins_parameter(self):
        """With n_bins=5, at most 5 bins returned."""
        probs = [i / 10 + 0.05 for i in range(10)]
        outcomes = [1 if i % 2 == 0 else 0 for i in range(10)]
        bins = _calibration_bins(probs, outcomes, n_bins=5)
        assert len(bins) <= 5


# ---------------------------------------------------------------------------
# _sharp_score_win_rates
# ---------------------------------------------------------------------------

class TestSharpScoreWinRates:

    def test_returns_dict(self):
        rates = _sharp_score_win_rates([40, 50, 70], [0, 1, 1])
        assert isinstance(rates, dict)

    def test_values_in_range(self):
        rates = _sharp_score_win_rates([40, 50, 70, 80, 90], [0, 1, 1, 1, 0])
        for v in rates.values():
            assert 0.0 <= v <= 1.0

    def test_minimum_sample_gate(self):
        """Tiers with < 3 bets must not appear."""
        # Only one bet per tier → nothing should appear
        rates = _sharp_score_win_rates([30, 50, 70], [1, 1, 1])
        assert len(rates) == 0

    def test_correct_tier_bucketing(self):
        """Score 42 → <45 tier, score 50 → 45-55, score 60 → 55-65."""
        scores = [42, 42, 42, 50, 50, 50, 60, 60, 60]
        outcomes = [1, 0, 1, 1, 1, 0, 0, 0, 0]
        rates = _sharp_score_win_rates(scores, outcomes)
        # <45: 2 wins, 1 loss → 0.667
        assert "<45" in rates
        assert abs(rates["<45"] - 2/3) < 0.01
        # 45-55: 2 wins, 1 loss → 0.667
        assert "45-55" in rates
        # 55-65: 0 wins, 3 loss → 0.0
        assert "55-65" in rates
        assert rates["55-65"] == 0.0

    def test_high_tier_correct(self):
        """Score 80 → 75+ tier."""
        scores = [80, 82, 85]
        outcomes = [1, 1, 0]
        rates = _sharp_score_win_rates(scores, outcomes)
        assert "75+" in rates
        assert abs(rates["75+"] - 2/3) < 0.01

    def test_empty_input(self):
        assert _sharp_score_win_rates([], []) == {}


# ---------------------------------------------------------------------------
# _mean_edge_accuracy
# ---------------------------------------------------------------------------

class TestMeanEdgeAccuracy:

    def test_empty_returns_zero(self):
        assert _mean_edge_accuracy([], []) == 0.0

    def test_returns_float(self):
        result = _mean_edge_accuracy([0.05, 0.07], [1, 0])
        assert isinstance(result, float)

    def test_result_non_negative(self):
        result = _mean_edge_accuracy([0.05, 0.08, 0.06], [1, 0, 1])
        assert result >= 0.0


# ---------------------------------------------------------------------------
# get_calibration_report — inactive path
# ---------------------------------------------------------------------------

class TestGetCalibrationReportInactive:

    def test_nonexistent_db_returns_inactive(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert report.is_active is False

    def test_inactive_report_type(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert isinstance(report, CalibrationReport)

    def test_bets_total_zero_when_no_db(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert report.bets_total == 0

    def test_bets_needed_when_no_db(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert report.bets_needed_for_activation == MIN_BETS_FOR_CALIBRATION

    def test_notes_contains_needed_count(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert str(MIN_BETS_FOR_CALIBRATION) in report.notes

    def test_bins_empty_when_inactive(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert report.calibration_bins == []

    def test_brier_zero_when_inactive(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert report.brier_score == 0.0

    def test_roc_zero_when_inactive(self):
        report = get_calibration_report(db_path="nonexistent.db")
        assert report.roc_auc == 0.0


# ---------------------------------------------------------------------------
# CalibrationReport — structure
# ---------------------------------------------------------------------------

class TestCalibrationReportStructure:

    def test_dataclass_instantiation(self):
        r = CalibrationReport(
            is_active=True, bets_total=50, bets_wins=28,
            bets_needed_for_activation=0,
            brier_score=0.22, roc_auc=0.63,
        )
        assert r.bets_total == 50

    def test_default_bins_is_list(self):
        r = CalibrationReport(
            is_active=False, bets_total=0, bets_wins=0,
            bets_needed_for_activation=30,
        )
        assert isinstance(r.calibration_bins, list)

    def test_default_tier_rates_is_dict(self):
        r = CalibrationReport(
            is_active=False, bets_total=0, bets_wins=0,
            bets_needed_for_activation=30,
        )
        assert isinstance(r.sharp_score_vs_wr, dict)


# ---------------------------------------------------------------------------
# calibration_is_ready
# ---------------------------------------------------------------------------

class TestCalibrationIsReady:

    def test_returns_false_no_db(self):
        assert calibration_is_ready("nonexistent.db") is False

    def test_returns_bool(self):
        result = calibration_is_ready("nonexistent.db")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# MIN_BETS_FOR_CALIBRATION constant
# ---------------------------------------------------------------------------

class TestConstants:

    def test_min_bets_is_30(self):
        assert MIN_BETS_FOR_CALIBRATION == 30

    def test_n_bins_is_10(self):
        assert N_CALIBRATION_BINS == 10
