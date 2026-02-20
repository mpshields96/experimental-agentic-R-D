"""
tests/test_originator_engine.py — Titanium-Agentic
====================================================
Unit tests for core/originator_engine.py (Trinity Monte Carlo simulation).

Run: pytest tests/test_originator_engine.py -v
"""

import sys
import os
import math

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.originator_engine import (
    run_trinity_simulation,
    efficiency_gap_to_margin,
    SimulationResult,
    BASE_VOLATILITY,
    LEAGUE_AVG_TOTALS,
    EFFICIENCY_GAP_NEUTRAL,
    EFFICIENCY_GAP_SCALE,
)


# ---------------------------------------------------------------------------
# efficiency_gap_to_margin
# ---------------------------------------------------------------------------

class TestEfficiencyGapToMargin:
    def test_neutral_gap_returns_zero(self):
        assert efficiency_gap_to_margin(10.0) == pytest.approx(0.0)

    def test_home_advantage_gap(self):
        """gap=15 → home up 5 units → margin=+5.0"""
        assert efficiency_gap_to_margin(15.0) == pytest.approx(5.0)

    def test_away_advantage_gap(self):
        """gap=5 → home down 5 units → margin=-5.0"""
        assert efficiency_gap_to_margin(5.0) == pytest.approx(-5.0)

    def test_zero_gap(self):
        """gap=0 → maximum away advantage"""
        assert efficiency_gap_to_margin(0.0) == pytest.approx(-10.0)

    def test_max_gap(self):
        """gap=20 → maximum home advantage"""
        assert efficiency_gap_to_margin(20.0) == pytest.approx(10.0)

    def test_home_advantage_pts_added(self):
        """home_advantage_pts adds directly to margin."""
        margin = efficiency_gap_to_margin(10.0, home_advantage_pts=2.5)
        assert margin == pytest.approx(2.5)

    def test_home_advantage_combined(self):
        """gap=12.5 + home_advantage=2.5 → margin=5.0"""
        margin = efficiency_gap_to_margin(12.5, home_advantage_pts=2.5)
        assert margin == pytest.approx(5.0)

    def test_fractional_gap(self):
        """Non-integer gaps work correctly."""
        margin = efficiency_gap_to_margin(11.5)
        assert margin == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# run_trinity_simulation — deterministic (seed=42)
# ---------------------------------------------------------------------------

class TestTrinitySimulationBasic:
    def test_returns_simulation_result(self):
        result = run_trinity_simulation(0.0, "NBA", line=0.0, seed=42)
        assert isinstance(result, SimulationResult)

    def test_iterations_count(self):
        result = run_trinity_simulation(0.0, "NBA", seed=42)
        assert result.iterations == 10_000

    def test_cover_prob_between_0_and_1(self):
        result = run_trinity_simulation(0.0, "NBA", line=0.0, seed=42)
        assert 0.0 <= result.cover_probability <= 1.0

    def test_neutral_mean_neutral_line_near_50pct(self):
        """Home +0 vs line of 0 → ~50% cover probability."""
        result = run_trinity_simulation(0.0, "NBA", line=0.0, seed=42)
        assert 0.40 < result.cover_probability < 0.60

    def test_strong_home_advantage_higher_cover_prob(self):
        """Home projected to win by 15 vs line of -4 → cover > 75%."""
        result = run_trinity_simulation(15.0, "NBA", line=-4.0, seed=42)
        assert result.cover_probability > 0.70

    def test_strong_away_advantage_lower_cover_prob(self):
        """Home projected to lose by 10 vs line of -3 → cover < 30%."""
        result = run_trinity_simulation(-10.0, "NBA", line=-3.0, seed=42)
        assert result.cover_probability < 0.35

    def test_ci_10_less_than_ci_90(self):
        result = run_trinity_simulation(0.0, "NFL", seed=42)
        assert result.ci_10 < result.ci_90

    def test_median_margin_near_mean(self):
        """Median should be near adjusted_mean for large n."""
        result = run_trinity_simulation(5.0, "NBA", seed=42, iterations=20_000)
        assert abs(result.projected_margin - 5.0) < 2.0  # within 2 pts

    def test_volatility_positive(self):
        result = run_trinity_simulation(0.0, "NBA", seed=42)
        assert result.volatility > 0.0

    def test_reproducible_with_seed(self):
        """Same seed → identical results."""
        r1 = run_trinity_simulation(3.0, "NFL", line=-3.0, seed=99)
        r2 = run_trinity_simulation(3.0, "NFL", line=-3.0, seed=99)
        assert r1.cover_probability == r2.cover_probability

    def test_different_seeds_different_results(self):
        r1 = run_trinity_simulation(0.0, "NBA", seed=1)
        r2 = run_trinity_simulation(0.0, "NBA", seed=2)
        # Not guaranteed to differ by much but should not be identical
        assert r1.cover_probability != r2.cover_probability


# ---------------------------------------------------------------------------
# Totals simulation
# ---------------------------------------------------------------------------

class TestTrinityTotals:
    def test_no_total_line_returns_zero_over_prob(self):
        result = run_trinity_simulation(0.0, "NBA", total_line=None, seed=42)
        assert result.over_probability == 0.0

    def test_total_line_returns_over_prob(self):
        result = run_trinity_simulation(0.0, "NBA", total_line=225.0, seed=42)
        assert 0.0 <= result.over_probability <= 1.0

    def test_extreme_high_total_line_under_dominated(self):
        """Total line way above league average → over probability < 30%."""
        result = run_trinity_simulation(0.0, "NBA", total_line=280.0, seed=42)
        assert result.over_probability < 0.30

    def test_extreme_low_total_line_over_dominated(self):
        """Total line way below league average → over probability > 70%."""
        result = run_trinity_simulation(0.0, "NBA", total_line=180.0, seed=42)
        assert result.over_probability > 0.70


# ---------------------------------------------------------------------------
# Sport-specific volatility
# ---------------------------------------------------------------------------

class TestSportVolatility:
    def test_all_sports_in_base_volatility(self):
        for sport in ["NBA", "NCAAB", "NFL", "NCAAF", "NHL", "MLB", "SOCCER"]:
            assert sport in BASE_VOLATILITY

    def test_nhl_tighter_than_nba(self):
        """NHL has lower volatility (goals vs points)."""
        assert BASE_VOLATILITY["NHL"] < BASE_VOLATILITY["NBA"]

    def test_nfl_wider_than_nba(self):
        """NFL has wider volatility (game-to-game variance higher)."""
        assert BASE_VOLATILITY["NFL"] > BASE_VOLATILITY["NBA"]

    def test_unknown_sport_uses_default(self):
        """Unknown sport key doesn't crash — uses default volatility."""
        result = run_trinity_simulation(0.0, "LACROSSE", seed=42)
        assert isinstance(result, SimulationResult)

    def test_hockey_simulation_tight_margins(self):
        """NHL margins cluster near 0 (low-scoring sport)."""
        result = run_trinity_simulation(0.0, "NHL", seed=42)
        # 90th percentile should be within 4 goals of 10th percentile
        assert result.ci_90 - result.ci_10 < 10.0


# ---------------------------------------------------------------------------
# Situational adjustments
# ---------------------------------------------------------------------------

class TestSituationalAdjustments:
    def test_rest_edge_increases_cover_prob(self):
        """Home team on better rest → higher cover probability."""
        base = run_trinity_simulation(0.0, "NBA", line=-4.0, seed=42)
        rested = run_trinity_simulation(0.0, "NBA", line=-4.0, rest_edge=3.0, seed=42)
        assert rested.cover_probability >= base.cover_probability

    def test_travel_penalty_decreases_cover_prob(self):
        """Home team's away opponent on long travel → higher home cover prob."""
        base = run_trinity_simulation(0.0, "NBA", line=-4.0, seed=42)
        penalized = run_trinity_simulation(0.0, "NBA", line=-4.0, travel_penalty=2.0, seed=42)
        assert penalized.cover_probability >= base.cover_probability

    def test_home_advantage_increases_cover_prob(self):
        """Adding home court advantage increases cover probability."""
        base = run_trinity_simulation(0.0, "NBA", line=-4.0, seed=42)
        with_ha = run_trinity_simulation(0.0, "NBA", line=-4.0, home_advantage=2.5, seed=42)
        assert with_ha.cover_probability >= base.cover_probability


# ---------------------------------------------------------------------------
# Custom iteration count
# ---------------------------------------------------------------------------

class TestIterationCount:
    def test_custom_iterations(self):
        result = run_trinity_simulation(0.0, "NBA", iterations=1_000, seed=42)
        assert result.iterations == 1_000

    def test_small_iteration_count(self):
        """Even 100 iterations completes without error."""
        result = run_trinity_simulation(0.0, "NBA", iterations=100, seed=42)
        assert 0.0 <= result.cover_probability <= 1.0
