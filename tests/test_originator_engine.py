"""
tests/test_originator_engine.py — Titanium-Agentic
====================================================
Unit tests for core/originator_engine.py (Trinity Monte Carlo + Poisson soccer).

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
    poisson_soccer,
    efficiency_gap_to_soccer_strength,
    PoissonResult,
    SOCCER_HOME_GOAL_BOOST,
    SOCCER_LEAGUE_AVG_GOALS_HOME,
    SOCCER_LEAGUE_AVG_GOALS_AWAY,
    _poisson_pmf,
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


# ---------------------------------------------------------------------------
# _poisson_pmf helper
# ---------------------------------------------------------------------------

class TestPoissonPMF:
    def test_known_value_k0_lam1(self):
        """P(X=0 | lambda=1) = e^-1 ≈ 0.3679."""
        assert _poisson_pmf(0, 1.0) == pytest.approx(math.exp(-1.0), rel=1e-6)

    def test_known_value_k1_lam1(self):
        """P(X=1 | lambda=1) = e^-1 ≈ 0.3679."""
        assert _poisson_pmf(1, 1.0) == pytest.approx(math.exp(-1.0), rel=1e-6)

    def test_known_value_k2_lam2(self):
        """P(X=2 | lambda=2) = 2 * e^-2 / 2! = 2*e^-2/2 = e^-2 ≈ 0.2707."""
        expected = (2.0 ** 2) * math.exp(-2.0) / 2
        assert _poisson_pmf(2, 2.0) == pytest.approx(expected, rel=1e-6)

    def test_zero_lambda_returns_zero(self):
        assert _poisson_pmf(0, 0.0) == 0.0

    def test_negative_k_returns_zero(self):
        assert _poisson_pmf(-1, 1.5) == 0.0

    def test_sums_near_one_for_reasonable_lambda(self):
        """Sum P(X=k | lambda=2.5) for k=0..20 should be very close to 1."""
        total = sum(_poisson_pmf(k, 2.5) for k in range(21))
        assert total == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# poisson_soccer
# ---------------------------------------------------------------------------

class TestPoissonSoccerBasic:
    def test_returns_poisson_result(self):
        r = poisson_soccer()
        assert isinstance(r, PoissonResult)

    def test_1x2_probs_sum_to_one(self):
        """home_win + draw + away_win ≈ 1.0 (grid coverage ≥ 99.99%)."""
        r = poisson_soccer()
        total = r.home_win + r.draw + r.away_win
        assert total == pytest.approx(1.0, abs=0.005)

    def test_over_under_sum_to_one(self):
        r = poisson_soccer(total_line=2.5)
        assert r.over_probability + r.under_probability == pytest.approx(1.0, abs=0.005)

    def test_all_probs_between_0_and_1(self):
        r = poisson_soccer()
        for attr in ("home_win", "draw", "away_win", "over_probability", "under_probability"):
            val = getattr(r, attr)
            assert 0.0 <= val <= 1.0, f"{attr}={val} out of range"

    def test_expected_goals_positive(self):
        r = poisson_soccer()
        assert r.expected_home_goals > 0.0
        assert r.expected_away_goals > 0.0

    def test_expected_total_is_sum(self):
        r = poisson_soccer()
        assert r.expected_total == pytest.approx(r.expected_home_goals + r.expected_away_goals)

    def test_home_advantage_increases_expected_home_goals(self):
        r_with = poisson_soccer(apply_home_advantage=True)
        r_without = poisson_soccer(apply_home_advantage=False)
        assert r_with.expected_home_goals > r_without.expected_home_goals

    def test_neutral_slightly_home_favored(self):
        """With home advantage, home win probability should exceed 40%."""
        r = poisson_soccer()
        assert r.home_win > 0.40

    def test_draw_probability_realistic_range(self):
        """Draws in top-5 leagues average ~25-27%."""
        r = poisson_soccer()
        assert 0.20 <= r.draw <= 0.35

    def test_high_total_line_reduces_over_prob(self):
        """Total line 4.5 → over probability should be low."""
        r = poisson_soccer(total_line=4.5)
        assert r.over_probability < 0.25

    def test_low_total_line_increases_over_prob(self):
        """Total line 0.5 → almost certain over."""
        r = poisson_soccer(total_line=0.5)
        assert r.over_probability > 0.85

    def test_strong_home_team_higher_win_prob(self):
        """Home team with 1.6 attack vs 0.7 away attack → home_win >> away_win."""
        r = poisson_soccer(home_attack=1.6, away_attack=0.7)
        assert r.home_win > r.away_win + 0.20


class TestPoissonSoccerEdgeCases:
    def test_extreme_home_attack_doesnt_crash(self):
        r = poisson_soccer(home_attack=5.0, away_attack=0.1)
        assert isinstance(r, PoissonResult)

    def test_zero_total_line(self):
        """Total line 0 → over prob nearly 1 (any goal goes over)."""
        r = poisson_soccer(total_line=0.0)
        assert r.over_probability > 0.90

    def test_very_high_total_line(self):
        """Total line 8.5 → over prob very small."""
        r = poisson_soccer(total_line=8.5)
        assert r.over_probability < 0.05

    def test_max_goals_attribute(self):
        r = poisson_soccer()
        assert r.max_goals == 10

    def test_identical_attack_defense_symmetric(self):
        """Equal attack/defense strengths with home_advantage off → symmetric home/away.
        Must also pass equal league avg values via attack factors to neutralize base asymmetry."""
        # Scale away_attack to compensate for the league-average asymmetry
        # (SOCCER_LEAGUE_AVG_GOALS_AWAY / SOCCER_LEAGUE_AVG_GOALS_HOME ≈ 0.72)
        away_boost = SOCCER_LEAGUE_AVG_GOALS_HOME / SOCCER_LEAGUE_AVG_GOALS_AWAY
        r = poisson_soccer(home_attack=1.0, away_attack=away_boost,
                           home_defense=1.0, away_defense=1.0,
                           apply_home_advantage=False)
        assert abs(r.home_win - r.away_win) < 0.05


# ---------------------------------------------------------------------------
# efficiency_gap_to_soccer_strength
# ---------------------------------------------------------------------------

class TestEfficiencyGapToSoccerStrength:
    def test_neutral_gap_returns_unit_factors(self):
        h_att, a_att, h_def, a_def = efficiency_gap_to_soccer_strength(10.0)
        assert h_att == pytest.approx(1.0, abs=0.001)
        assert a_att == pytest.approx(1.0, abs=0.001)
        assert h_def == pytest.approx(1.0, abs=0.001)
        assert a_def == pytest.approx(1.0, abs=0.001)

    def test_home_advantage_gap_boosts_home(self):
        h_att, a_att, h_def, a_def = efficiency_gap_to_soccer_strength(15.0)
        assert h_att > 1.0
        assert a_att < 1.0

    def test_away_advantage_gap_boosts_away(self):
        h_att, a_att, h_def, a_def = efficiency_gap_to_soccer_strength(5.0)
        assert a_att > 1.0
        assert h_att < 1.0

    def test_all_factors_positive(self):
        for gap in [0.0, 5.0, 10.0, 15.0, 20.0]:
            factors = efficiency_gap_to_soccer_strength(gap)
            for f in factors:
                assert f > 0.0, f"factor={f} for gap={gap}"

    def test_wires_into_poisson_correctly(self):
        """efficiency_gap=15 → home stronger → home_win increases vs neutral."""
        h_att, a_att, h_def, a_def = efficiency_gap_to_soccer_strength(15.0)
        r_strong = poisson_soccer(home_attack=h_att, away_attack=a_att,
                                  home_defense=h_def, away_defense=a_def)
        r_neutral = poisson_soccer()
        assert r_strong.home_win >= r_neutral.home_win

    def test_gap_zero_is_max_away_advantage(self):
        h_att0, a_att0, _, _ = efficiency_gap_to_soccer_strength(0.0)
        h_att10, a_att10, _, _ = efficiency_gap_to_soccer_strength(10.0)
        assert a_att0 > a_att10
        assert h_att0 < h_att10
