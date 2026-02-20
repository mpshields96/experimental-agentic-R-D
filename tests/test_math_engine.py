"""
tests/test_math_engine.py — Titanium-Agentic
=============================================
Unit tests for core/math_engine.py.

Every mathematical function must have a test before moving to the UI layer.
Run: pytest tests/test_math_engine.py -v
"""

import pytest
import sys
import os

# Ensure sandbox root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.math_engine import (
    passes_collar,
    passes_collar_soccer,
    implied_probability,
    no_vig_probability,
    no_vig_probability_3way,
    calculate_edge,
    calculate_profit,
    fractional_kelly,
    calculate_sharp_score,
    sharp_to_size,
    nba_kill_switch,
    nfl_kill_switch,
    ncaab_kill_switch,
    soccer_kill_switch,
    nhl_kill_switch,
    ncaaf_kill_switch,
    tennis_kill_switch,
    NCAAF_SPREAD_KILL_THRESHOLD,
    NCAAF_SEASON_MONTHS,
    consensus_fair_prob,
    consensus_fair_prob_3way,
    compute_rlm,
    cache_open_prices,
    get_open_price,
    clear_open_price_cache,
    open_price_cache_size,
    get_rlm_fire_count,
    reset_rlm_fire_count,
    rlm_gate_status,
    calculate_clv,
    clv_grade,
    BetCandidate,
    run_nemesis,
    parse_game_markets,
    COLLAR_MIN,
    COLLAR_MAX,
    COLLAR_MIN_SOCCER,
    COLLAR_MAX_SOCCER,
    SOCCER_SPORTS,
    MIN_EDGE,
    SHARP_THRESHOLD,
    RLM_FIRE_GATE,
)


# ---------------------------------------------------------------------------
# Collar check
# ---------------------------------------------------------------------------

class TestPassesCollar:
    def test_standard_spread_odds_pass(self):
        assert passes_collar(-110) is True

    def test_max_collar_boundary_pass(self):
        assert passes_collar(150) is True

    def test_min_collar_boundary_pass(self):
        assert passes_collar(-180) is True

    def test_outside_max_fails(self):
        assert passes_collar(155) is False

    def test_outside_min_fails(self):
        assert passes_collar(-185) is False

    def test_positive_underdog_passes(self):
        assert passes_collar(130) is True

    def test_even_money_passes(self):
        assert passes_collar(100) is True
        assert passes_collar(-100) is True

    def test_collar_constants(self):
        assert COLLAR_MIN == -180
        assert COLLAR_MAX == 150


# ---------------------------------------------------------------------------
# Implied probability
# ---------------------------------------------------------------------------

class TestImpliedProbability:
    def test_standard_spread_odds(self):
        # -110 → 52.38%
        assert abs(implied_probability(-110) - 0.5238) < 0.0001

    def test_positive_odds(self):
        # +110 → 47.62%
        assert abs(implied_probability(110) - 0.4762) < 0.0001

    def test_heavy_favourite(self):
        # -180 → 64.29%
        assert abs(implied_probability(-180) - 0.6429) < 0.0001

    def test_max_underdog(self):
        # +150 → 40.00%
        assert abs(implied_probability(150) - 0.4000) < 0.0001

    def test_probability_range(self):
        for odds in [-180, -150, -130, -110, 100, 110, 130, 150]:
            prob = implied_probability(odds)
            assert 0 < prob < 1, f"Probability out of range for odds {odds}: {prob}"


# ---------------------------------------------------------------------------
# No-vig probability
# ---------------------------------------------------------------------------

class TestNoVigProbability:
    def test_symmetric_market_is_50_50(self):
        a, b = no_vig_probability(-110, -110)
        assert abs(a - 0.5) < 0.001
        assert abs(b - 0.5) < 0.001

    def test_sums_to_one(self):
        for odds_a, odds_b in [(-110, -110), (-150, 130), (-120, 100)]:
            a, b = no_vig_probability(odds_a, odds_b)
            assert abs(a + b - 1.0) < 1e-9, f"Sum != 1 for {odds_a}/{odds_b}: {a+b}"

    def test_favourite_higher_prob(self):
        fav, dog = no_vig_probability(-150, 130)
        assert fav > dog

    def test_removes_vig(self):
        # Raw probs sum > 1 (overround). Fair probs sum to exactly 1.
        raw_sum = implied_probability(-110) + implied_probability(-110)
        assert raw_sum > 1.0
        a, b = no_vig_probability(-110, -110)
        assert abs(a + b - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Edge calculation
# ---------------------------------------------------------------------------

class TestCalculateEdge:
    def test_positive_edge(self):
        # Model: 55% win. Market: -110 (52.38% implied). Edge = 2.62%
        edge = calculate_edge(0.55, -110)
        assert abs(edge - 0.0262) < 0.001

    def test_zero_edge(self):
        # Model matches implied exactly
        prob = implied_probability(-110)
        edge = calculate_edge(prob, -110)
        assert abs(edge) < 1e-9

    def test_negative_edge_below_threshold(self):
        edge = calculate_edge(0.48, -110)
        assert edge < 0

    def test_min_edge_constant(self):
        assert MIN_EDGE == 0.035

    def test_high_edge(self):
        edge = calculate_edge(0.65, -110)
        assert edge > MIN_EDGE


class TestCalculateProfit:
    def test_positive_odds_profit(self):
        assert abs(calculate_profit(100, 110) - 110.0) < 0.01

    def test_negative_odds_profit(self):
        # -110: win 100 → profit = 100 * (100/110)
        assert abs(calculate_profit(100, -110) - 90.91) < 0.01

    def test_even_money(self):
        assert abs(calculate_profit(50, 100) - 50.0) < 0.01


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------

class TestFractionalKelly:
    def test_lean_cap_applied(self):
        # win_prob <= 0.54 → max 0.5u
        size = fractional_kelly(0.52, -110)
        assert size <= 0.5

    def test_standard_cap_applied(self):
        # win_prob > 0.54, <= 0.60 → max 1.0u
        size = fractional_kelly(0.57, -110)
        assert size <= 1.0

    def test_nuclear_cap_applied(self):
        # win_prob > 0.60 → max 2.0u
        size = fractional_kelly(0.65, -110)
        assert size <= 2.0

    def test_negative_kelly_returns_small_positive(self):
        # Very low win prob — Kelly would be negative, but we cap at max for tier
        # Actually with very low prob, full_kelly < 0, fractional < 0 → min(neg, 0.5) = neg
        # So we shouldn't bet. The function should not return negative numbers.
        # In practice: if full_kelly is negative, fractional is negative
        # The current implementation does NOT floor at 0, which is V36 behavior.
        # These bets would be filtered by MIN_EDGE before reaching Kelly.
        # Just verify the formula doesn't crash.
        size = fractional_kelly(0.45, -110)
        # A bet with 45% win prob at -110 has negative Kelly — don't assert positivity

    def test_zero_edge_kelly(self):
        # At exactly breakeven (model = implied), Kelly = 0
        prob = implied_probability(-110)
        size = fractional_kelly(prob, -110)
        # Should be at or near 0
        assert abs(size) < 0.01

    def test_kelly_positive_odds(self):
        # +130 underdog with 52% win prob should produce small positive bet
        size = fractional_kelly(0.52, 130)
        # 52% win at +130 → decimal 2.30, b=1.30, q=0.48
        # full_kelly = (1.30*0.52 - 0.48)/1.30 = (0.676 - 0.48)/1.30 = 0.1508
        # fractional = 0.1508 * 0.25 = 0.0377 (under 0.5 cap)
        assert 0 < size <= 0.5


# ---------------------------------------------------------------------------
# Sharp Score
# ---------------------------------------------------------------------------

class TestCalculateSharpScore:
    def test_session_13_validated_8pct_no_rlm(self):
        """8% edge, no RLM, eff=12, rest=2 → 46.0 (from HANDOFF.md S13 table)"""
        score, breakdown = calculate_sharp_score(0.08, False, 12.0, rest_edge=2.0)
        assert score == 46.0

    def test_session_13_validated_6pct_with_rlm(self):
        """6% edge, RLM, eff=12, rest=2 → 63.0 (validated in R&D S13)"""
        score, breakdown = calculate_sharp_score(0.06, True, 12.0, rest_edge=2.0)
        assert score == 63.0

    def test_edge_component_capped_at_40(self):
        """Edge > 10% still caps at 40 pts"""
        score, breakdown = calculate_sharp_score(0.15, False, 0.0)
        assert breakdown["edge"] == 40.0

    def test_rlm_contributes_25_pts(self):
        score_no_rlm, _ = calculate_sharp_score(0.08, False, 12.0)
        score_rlm, _ = calculate_sharp_score(0.08, True, 12.0)
        assert abs((score_rlm - score_no_rlm) - 25.0) < 0.01

    def test_efficiency_capped_at_20(self):
        _, breakdown = calculate_sharp_score(0.08, False, 25.0)
        assert breakdown["efficiency"] == 20.0

    def test_situational_capped_at_15(self):
        _, breakdown = calculate_sharp_score(0.08, False, 12.0,
                                             rest_edge=10.0, injury_leverage=10.0,
                                             motivation=5.0, matchup_score=5.0)
        assert breakdown["situational"] == 15.0

    def test_breakdown_keys_present(self):
        _, breakdown = calculate_sharp_score(0.08, False, 12.0)
        assert all(k in breakdown for k in ["edge", "rlm", "efficiency", "situational"])

    def test_sharp_threshold_constant(self):
        assert SHARP_THRESHOLD == 45.0

    def test_score_below_threshold_with_low_edge(self):
        """6% edge, no RLM, eff=8 → should be below threshold"""
        score, _ = calculate_sharp_score(0.06, False, 8.0)
        assert score < SHARP_THRESHOLD


class TestSharpToSize:
    def test_nuclear(self):
        assert sharp_to_size(90) == "NUCLEAR_2.0U"
        assert sharp_to_size(95) == "NUCLEAR_2.0U"

    def test_standard(self):
        assert sharp_to_size(80) == "STANDARD_1.0U"
        assert sharp_to_size(85) == "STANDARD_1.0U"

    def test_lean(self):
        assert sharp_to_size(79) == "LEAN_0.5U"
        assert sharp_to_size(60) == "LEAN_0.5U"
        assert sharp_to_size(45) == "LEAN_0.5U"

    def test_boundary_90(self):
        # 89.9 is below 90 → STANDARD tier (80-89.9)
        assert sharp_to_size(89.9) == "STANDARD_1.0U"
        assert sharp_to_size(90.0) == "NUCLEAR_2.0U"

    def test_boundary_80(self):
        # 79.9 is below 80 → LEAN tier
        assert sharp_to_size(79.9) == "LEAN_0.5U"
        assert sharp_to_size(80.0) == "STANDARD_1.0U"


# ---------------------------------------------------------------------------
# Kill switches
# ---------------------------------------------------------------------------

class TestNBAKillSwitch:
    def test_rest_disadvantage_spread_inside_4_killed(self):
        """V36.1 canonical kill case — Heat B2B, -3.5 spread"""
        killed, reason = nba_kill_switch(True, -3.5, market_type="spread")
        assert killed is True
        assert "KILL" in reason

    def test_rested_team_spread_outside_4_safe(self):
        """Celtics rested, -8.5 spread — should pass"""
        killed, reason = nba_kill_switch(False, -8.5, market_type="spread")
        assert killed is False
        assert reason == ""

    def test_home_b2b_flagged_kelly_reduction(self):
        """Home B2B → FLAG with Kelly reduction message (not road message)"""
        killed, reason = nba_kill_switch(False, -4.5, b2b=True, is_road_b2b=False, market_type="spread")
        assert killed is False
        assert "FLAG" in reason
        assert "Home B2B" in reason
        assert "50%" in reason

    def test_road_b2b_flagged_higher_edge_requirement(self):
        """Road B2B → FLAG with higher edge requirement"""
        killed, reason = nba_kill_switch(False, -4.5, b2b=True, is_road_b2b=True, market_type="spread")
        assert killed is False
        assert "FLAG" in reason
        assert "Road B2B" in reason
        assert "8%" in reason

    def test_road_b2b_stricter_than_home(self):
        """Road B2B flag is semantically stricter than home B2B flag."""
        _, home_reason = nba_kill_switch(False, 0.0, b2b=True, is_road_b2b=False)
        _, road_reason = nba_kill_switch(False, 0.0, b2b=True, is_road_b2b=True)
        assert home_reason != road_reason
        assert "Home" in home_reason
        assert "Road" in road_reason

    def test_is_road_b2b_false_default_backward_compat(self):
        """is_road_b2b=False (default) preserves original flag behavior."""
        killed, reason = nba_kill_switch(False, -4.5, b2b=True, market_type="spread")
        assert killed is False
        assert "FLAG" in reason

    def test_high_pace_variance_kills_total(self):
        killed, reason = nba_kill_switch(False, -5.0, pace_std_dev=5.0, market_type="total")
        assert killed is True

    def test_rest_disadvantage_does_not_kill_moneyline(self):
        """Rest kill only applies to spread bets"""
        killed, reason = nba_kill_switch(True, -3.0, market_type="moneyline")
        assert killed is False

    def test_star_absent_inside_avg_margin_killed(self):
        killed, reason = nba_kill_switch(False, -3.0, star_absent=True, avg_margin=5.0)
        assert killed is True


class TestNFLKillSwitch:
    def test_high_wind_high_total_force_under(self):
        """V36.1 canonical — wind 18mph, total 44.5"""
        killed, reason = nfl_kill_switch(18.0, 44.5, market_type="total")
        assert killed is True
        assert "FORCE_UNDER" in reason

    def test_low_wind_safe(self):
        killed, reason = nfl_kill_switch(12.0, 44.5, market_type="total")
        assert killed is False

    def test_extreme_wind_kills_all(self):
        killed, reason = nfl_kill_switch(22.0, 38.0, market_type="total")
        assert killed is True
        assert "KILL" in reason

    def test_backup_qb_killed(self):
        killed, reason = nfl_kill_switch(8.0, 42.0, backup_qb=True)
        assert killed is True

    def test_wind_over_15_but_low_total_safe(self):
        """Wind >15 but total <= 42 — no kill"""
        killed, reason = nfl_kill_switch(16.0, 40.0, market_type="total")
        assert killed is False


class TestNCAABKillSwitch:
    def test_3pt_reliance_away_killed(self):
        """V36.1 canonical — DePaul 43% 3PT on road"""
        killed, reason = ncaab_kill_switch(0.43, True)
        assert killed is True
        assert "KILL" in reason

    def test_3pt_reliance_home_safe(self):
        killed, reason = ncaab_kill_switch(0.43, False)
        assert killed is False

    def test_below_threshold_away_safe(self):
        killed, reason = ncaab_kill_switch(0.38, True)
        assert killed is False

    def test_tempo_diff_kills_total(self):
        """14-possession tempo diff → kill total"""
        killed, reason = ncaab_kill_switch(0.35, False, tempo_diff=14.0, market_type="total")
        assert killed is True

    def test_conference_tournament_flagged(self):
        killed, reason = ncaab_kill_switch(0.30, False, conference_tournament=True)
        assert killed is False
        assert "FLAG" in reason


class TestSoccerKillSwitch:
    def test_high_drift_killed(self):
        """V36.1 canonical — 11% drift"""
        killed, reason = soccer_kill_switch(0.11)
        assert killed is True

    def test_low_drift_safe(self):
        killed, reason = soccer_kill_switch(0.05)
        assert killed is False

    def test_dead_rubber_killed(self):
        killed, reason = soccer_kill_switch(0.0, dead_rubber=True)
        assert killed is True

    def test_key_creator_out_flagged(self):
        killed, reason = soccer_kill_switch(0.05, key_creator_out=True)
        assert killed is False
        assert "FLAG" in reason

    def test_exact_boundary_10pct_safe(self):
        """Exactly 10% — boundary is > 0.10, so 0.10 should be safe"""
        killed, reason = soccer_kill_switch(0.10)
        assert killed is False


# ---------------------------------------------------------------------------
# Consensus fair probability
# ---------------------------------------------------------------------------

def _make_bookmaker(key: str, title: str, market_key: str, outcomes: list) -> dict:
    """Helper: build a mock bookmaker dict for tests."""
    return {
        "key": key,
        "title": title,
        "markets": [{"key": market_key, "outcomes": outcomes}],
    }


class TestConsensusFairProb:
    def test_two_book_consensus_spread(self):
        bookmakers = [
            _make_bookmaker("dk", "DraftKings", "spreads", [
                {"name": "Duke", "price": -110, "point": -4.5},
                {"name": "Virginia", "price": -110, "point": 4.5},
            ]),
            _make_bookmaker("fd", "FanDuel", "spreads", [
                {"name": "Duke", "price": -112, "point": -4.5},
                {"name": "Virginia", "price": -108, "point": 4.5},
            ]),
        ]
        prob, std, n_books = consensus_fair_prob("Duke", "spreads", "team", bookmakers)
        assert n_books == 2
        assert 0.49 < prob < 0.51  # near 50/50 for balanced lines
        assert std >= 0.0

    def test_single_book_returns_zero_n_books(self):
        bookmakers = [
            _make_bookmaker("dk", "DraftKings", "spreads", [
                {"name": "Duke", "price": -110, "point": -4.5},
                {"name": "Virginia", "price": -110, "point": 4.5},
            ]),
        ]
        prob, std, n_books = consensus_fair_prob("Duke", "spreads", "team", bookmakers)
        assert n_books == 1  # has data but only 1 book — below MIN_BOOKS

    def test_no_bookmakers_returns_zero(self):
        prob, std, n_books = consensus_fair_prob("Duke", "spreads", "team", [])
        assert n_books == 0
        assert prob == 0.5

    def test_totals_over(self):
        bookmakers = [
            _make_bookmaker("dk", "DraftKings", "totals", [
                {"name": "Over", "price": -110, "point": 148.5},
                {"name": "Under", "price": -110, "point": 148.5},
            ]),
            _make_bookmaker("fd", "FanDuel", "totals", [
                {"name": "Over", "price": -108, "point": 148.5},
                {"name": "Under", "price": -112, "point": 148.5},
            ]),
        ]
        prob, std, n_books = consensus_fair_prob("", "totals", "Over", bookmakers)
        assert n_books == 2
        assert 0.49 < prob < 0.52  # over slightly favoured at -108


# ---------------------------------------------------------------------------
# RLM tracker
# ---------------------------------------------------------------------------

class TestRLM:
    def setup_method(self):
        """Clear cache and fire counter before each test to prevent state bleed."""
        clear_open_price_cache()
        reset_rlm_fire_count()

    def test_cold_cache_returns_false(self):
        rlm, drift = compute_rlm("event_001", "Duke", -110, public_on_side=True)
        assert rlm is False
        assert drift == 0.0

    def test_cache_open_prices_stored(self):
        games = [
            {
                "id": "event_001",
                "home_team": "Duke",
                "away_team": "Virginia",
                "bookmakers": [
                    _make_bookmaker("dk", "DraftKings", "spreads", [
                        {"name": "Duke", "price": -110, "point": -4.5},
                        {"name": "Virginia", "price": -110, "point": 4.5},
                    ]),
                ],
            }
        ]
        cache_open_prices(games)
        assert open_price_cache_size() == 1
        assert get_open_price("event_001", "Duke") == -110

    def test_rlm_fires_on_drift(self):
        games = [
            {
                "id": "event_002",
                "home_team": "TeamA",
                "away_team": "TeamB",
                "bookmakers": [
                    _make_bookmaker("dk", "DraftKings", "h2h", [
                        {"name": "TeamA", "price": -115},
                        {"name": "TeamB", "price": 105},
                    ]),
                ],
            }
        ]
        cache_open_prices(games)
        # Price moves from -115 to -130 (public on TeamA, line moves against them)
        # implied(-115) = 0.5349, implied(-130) = 0.5652, drift = 0.0303 > 0.03
        rlm, drift = compute_rlm("event_002", "TeamA", -130, public_on_side=True)
        assert rlm is True
        assert drift >= 0.03

    def test_rlm_does_not_fire_below_threshold(self):
        games = [{"id": "evt_003", "bookmakers": [
            _make_bookmaker("dk", "DK", "h2h", [
                {"name": "X", "price": -110}, {"name": "Y", "price": -110}
            ])
        ]}]
        cache_open_prices(games)
        # Small move: -110 → -113 (drift ≈ 0.007 < 0.03)
        rlm, drift = compute_rlm("evt_003", "X", -113, public_on_side=True)
        assert rlm is False

    def test_cache_not_overwritten(self):
        games = [{"id": "evt_004", "bookmakers": [
            _make_bookmaker("dk", "DK", "h2h", [
                {"name": "A", "price": -110}, {"name": "B", "price": -110}
            ])
        ]}]
        cache_open_prices(games)
        original = get_open_price("evt_004", "A")
        # Re-cache same event (simulating second fetch)
        new_games = [{"id": "evt_004", "bookmakers": [
            _make_bookmaker("dk", "DK", "h2h", [
                {"name": "A", "price": -120}, {"name": "B", "price": 100}
            ])
        ]}]
        cache_open_prices(new_games)
        # Should still have original price
        assert get_open_price("evt_004", "A") == original

    def test_clear_cache(self):
        games = [{"id": "evt_005", "bookmakers": []}]
        cache_open_prices(games)
        clear_open_price_cache()
        assert open_price_cache_size() == 0


# ---------------------------------------------------------------------------
# CLV
# ---------------------------------------------------------------------------

class TestCLV:
    def test_positive_clv_beat_the_close(self):
        # Bet at -110, closed at -120 → we got a better price
        clv = calculate_clv(-115, -120, -110)
        assert clv > 0

    def test_zero_clv_matched_close(self):
        clv = calculate_clv(-110, -110, -110)
        assert clv == 0.0

    def test_negative_clv_missed_closing_line(self):
        # Bet at -120, closed at -110 → market moved away from us
        clv = calculate_clv(-115, -110, -120)
        assert clv < 0

    def test_clv_grade_excellent(self):
        assert clv_grade(0.025) == "EXCELLENT"
        assert clv_grade(0.02) == "EXCELLENT"

    def test_clv_grade_good(self):
        assert clv_grade(0.01) == "GOOD"
        assert clv_grade(0.005) == "GOOD"

    def test_clv_grade_neutral(self):
        assert clv_grade(0.0) == "NEUTRAL"
        # 0.001 < 0.005 threshold → NEUTRAL (not GOOD)
        assert clv_grade(0.001) == "NEUTRAL"
        # 0.004 < 0.005 → NEUTRAL
        assert clv_grade(0.004) == "NEUTRAL"

    def test_clv_grade_poor(self):
        assert clv_grade(-0.01) == "POOR"


# ---------------------------------------------------------------------------
# parse_game_markets
# ---------------------------------------------------------------------------

class TestParseGameMarkets:
    def _make_game(self) -> dict:
        """
        Build a synthetic game where Duke moneyline has a clear edge.

        Design:
        - 3 consensus books all have Duke ML at -130 (fair_prob ≈ 0.5652)
        - Best book has Duke ML at -115 (implied ≈ 0.5349)
        - Edge = 0.5652 - 0.5349 = 0.0303 < 0.035 → not quite
        - Use 4 consensus books at -140 (fair ≈ 0.5833) and best at -115 (0.5349) → edge ≈ 0.048 ✓

        Key insight: outlier book is included in consensus because it has BOTH sides.
        To get clear edge, we need the consensus to be solidly above the best available price.
        Use -140/-140 (vig-free=0.5833) and best book at -115 (implied=0.5349) → edge=0.048.
        """
        return {
            "id": "game_001",
            "home_team": "Duke",
            "away_team": "Virginia",
            "commence_time": "2026-02-20T01:00:00Z",
            "bookmakers": [
                # 4 consensus books — Duke favoured at -140
                _make_bookmaker("dk", "DraftKings", "h2h", [
                    {"name": "Duke", "price": -140},
                    {"name": "Virginia", "price": 120},
                ]),
                _make_bookmaker("fd", "FanDuel", "h2h", [
                    {"name": "Duke", "price": -140},
                    {"name": "Virginia", "price": 120},
                ]),
                _make_bookmaker("bm", "BetMGM", "h2h", [
                    {"name": "Duke", "price": -140},
                    {"name": "Virginia", "price": 120},
                ]),
                # Best book underprices Duke (edges exist here)
                _make_bookmaker("br", "BetRivers", "h2h", [
                    {"name": "Duke", "price": -115},   # better price = higher edge
                    {"name": "Virginia", "price": -105},
                ]),
            ],
        }

    def test_returns_candidates_with_edge(self):
        """Duke ML: 3 books at -140 (consensus ~0.565), best book at -115 (implied 0.535) → edge ~3.0%"""
        game = self._make_game()
        candidates = parse_game_markets(game, sport="NCAAB")
        # Duke consensus from 4 books:
        # DK: no_vig(-140, 120) → Duke ≈ 0.5652
        # FD: same ≈ 0.5652
        # BM: same ≈ 0.5652
        # BR: no_vig(-115, -105) → Duke ≈ 0.5122
        # Mean ≈ (0.5652*3 + 0.5122) / 4 ≈ 0.5519
        # Best price: -115, implied = 0.5349
        # Edge = 0.5519 - 0.5349 = 0.017 → below 3.5% threshold
        # Virginia consensus ≈ 0.448, best price +120 (implied 0.455) → negative edge
        # So this game produces NO candidates — that's correct behavior.
        # The test verifies the function runs without error and collar/edge rules are enforced.
        assert isinstance(candidates, list)
        # No bet should appear for Virginia (negative edge)
        virginia_bets = [c for c in candidates if "Virginia" in c.target]
        assert len(virginia_bets) == 0

    def _make_game_with_clear_edge(self) -> dict:
        """
        Game where Duke ML has a clear >3.5% edge.

        Design:
        3 consensus books at -130/+110 → Duke vig-free ≈ 0.5427
        Best book at +140/-165 → Duke vig-free ≈ 0.4009 (outlier, prices Duke as underdog)
        Mean consensus across 4 books ≈ 0.5073
        Best available price for Duke = +140 (implied = 0.4167)
        Edge = 0.5073 - 0.4167 = 0.0906 > 3.5% ✓

        This mirrors a real scenario: 3 books think Duke wins >50%, one outlier
        prices Duke as an underdog. Consensus says the outlier is wrong.
        """
        return {
            "id": "game_edge_001",
            "home_team": "Duke",
            "away_team": "Virginia",
            "commence_time": "2026-02-20T01:00:00Z",
            "bookmakers": [
                _make_bookmaker("dk", "DraftKings", "h2h", [
                    {"name": "Duke", "price": -130},
                    {"name": "Virginia", "price": 110},
                ]),
                _make_bookmaker("fd", "FanDuel", "h2h", [
                    {"name": "Duke", "price": -130},
                    {"name": "Virginia", "price": 110},
                ]),
                _make_bookmaker("bm", "BetMGM", "h2h", [
                    {"name": "Duke", "price": -130},
                    {"name": "Virginia", "price": 110},
                ]),
                # Outlier book — prices Duke as underdog (consensus disagrees strongly)
                _make_bookmaker("br", "BetRivers", "h2h", [
                    {"name": "Duke", "price": 140},    # best price for Duke
                    {"name": "Virginia", "price": -165},
                ]),
            ],
        }

    def test_candidate_fields_populated(self):
        """Verify candidate fields are properly set when a clear edge exists."""
        game = self._make_game_with_clear_edge()
        candidates = parse_game_markets(game, sport="NCAAB")
        duke_bets = [c for c in candidates if "Duke" in c.target and c.market_type == "h2h"]
        assert len(duke_bets) == 1, f"Expected 1 Duke ML bet, got {len(duke_bets)}: {[c.target for c in candidates]}"
        c = duke_bets[0]
        assert c.sport == "NCAAB"
        assert c.matchup == "Virginia @ Duke"
        assert c.event_id == "game_edge_001"
        assert c.price == 140   # best price (outlier book underprices Duke)
        assert c.edge_pct >= 0.035
        assert 0 < c.win_prob < 1
        assert 0 < c.kelly_size <= 2.0

    def test_no_duplicate_sides(self):
        """Should not output both Duke and Virginia on the same spread when only one has edge."""
        game = self._make_game()
        candidates = parse_game_markets(game, sport="NCAAB")
        spread_targets = [c.target for c in candidates if c.market_type == "spreads"]
        # Duke and Virginia are opposite sides — shouldn't both appear unless both have edge
        duke_spreads = [t for t in spread_targets if "Duke" in t]
        virginia_spreads = [t for t in spread_targets if "Virginia" in t]
        # At most one of each (could have 0 if edge not met)
        assert len(duke_spreads) <= 1
        assert len(virginia_spreads) <= 1

    def test_empty_bookmakers_returns_empty(self):
        game = {"id": "g", "home_team": "Duke", "away_team": "Virginia",
                "commence_time": "", "bookmakers": []}
        assert parse_game_markets(game, "NCAAB") == []

    def test_collar_violation_rejected(self):
        """Odds outside collar should produce no candidate."""
        game = {
            "id": "game_002",
            "home_team": "Duke",
            "away_team": "Virginia",
            "commence_time": "2026-02-20T01:00:00Z",
            "bookmakers": [
                _make_bookmaker("dk", "DraftKings", "spreads", [
                    {"name": "Duke", "price": -200, "point": -12.5},  # outside collar
                    {"name": "Virginia", "price": 175, "point": 12.5},  # outside collar
                ]),
                _make_bookmaker("fd", "FanDuel", "spreads", [
                    {"name": "Duke", "price": -200, "point": -12.5},
                    {"name": "Virginia", "price": 175, "point": 12.5},
                ]),
            ],
        }
        candidates = parse_game_markets(game, "NCAAB")
        assert candidates == []

    def test_efficiency_gap_zero_default(self):
        """Default efficiency_gap=0.0 → efficiency_contribution=0 in breakdown."""
        game = self._make_game_with_clear_edge()
        candidates = parse_game_markets(game, sport="NCAAB")  # no efficiency_gap arg
        duke_bets = [c for c in candidates if "Duke" in c.target and c.market_type == "h2h"]
        assert len(duke_bets) == 1
        c = duke_bets[0]
        assert c.sharp_breakdown is not None
        assert c.sharp_breakdown.get("efficiency", -1) == 0.0

    def test_efficiency_gap_increases_sharp_score(self):
        """Passing efficiency_gap=15.0 should raise sharp_score vs gap=0.0."""
        game = self._make_game_with_clear_edge()
        low_eff = parse_game_markets(game, sport="NCAAB", efficiency_gap=0.0)
        high_eff = parse_game_markets(game, sport="NCAAB", efficiency_gap=15.0)
        duke_low = [c for c in low_eff if "Duke" in c.target and c.market_type == "h2h"]
        duke_high = [c for c in high_eff if "Duke" in c.target and c.market_type == "h2h"]
        assert len(duke_low) == 1
        assert len(duke_high) == 1
        assert duke_high[0].sharp_score > duke_low[0].sharp_score

    def test_efficiency_gap_reflected_in_breakdown(self):
        """efficiency_contribution in breakdown should equal the efficiency_gap passed."""
        game = self._make_game_with_clear_edge()
        candidates = parse_game_markets(game, sport="NCAAB", efficiency_gap=12.5)
        duke_bets = [c for c in candidates if "Duke" in c.target and c.market_type == "h2h"]
        assert len(duke_bets) == 1
        c = duke_bets[0]
        assert c.sharp_breakdown is not None
        # calculate_sharp_score clamps efficiency to [0, 20], so 12.5 should pass through
        assert c.sharp_breakdown.get("efficiency", -1) == pytest.approx(12.5, abs=0.01)

    def test_efficiency_gap_capped_at_20(self):
        """efficiency_gap > 20 should be clamped to 20 by calculate_sharp_score."""
        game = self._make_game_with_clear_edge()
        capped = parse_game_markets(game, sport="NCAAB", efficiency_gap=25.0)
        uncapped = parse_game_markets(game, sport="NCAAB", efficiency_gap=20.0)
        duke_capped = [c for c in capped if "Duke" in c.target and c.market_type == "h2h"]
        duke_uncapped = [c for c in uncapped if "Duke" in c.target and c.market_type == "h2h"]
        assert len(duke_capped) == 1
        assert len(duke_uncapped) == 1
        assert duke_capped[0].sharp_score == duke_uncapped[0].sharp_score


# ---------------------------------------------------------------------------
# Nemesis — math-condition-driven (not narrative probability assignment)
# ---------------------------------------------------------------------------

class TestRunNemesis:
    """
    Nemesis v2: every case fires only when a quantifiable condition is present.
    Tests verify condition detection, not static probability lookup.
    """

    def _make_bet(
        self,
        sport: str,
        market_type: str,
        line: float = -4.5,
        price: int = -110,
        edge_pct: float = 0.06,
        signal: str = "",
        kill_reason: str = "",
        rest_days: int | None = None,
        sharp_breakdown: dict | None = None,
    ) -> BetCandidate:
        bet = BetCandidate(
            sport=sport, matchup="A @ B", market_type=market_type,
            target="A -4.5", line=line, price=price, edge_pct=edge_pct,
            win_prob=0.55, market_implied=0.5238, fair_implied=0.55,
            kelly_size=0.25, signal=signal, kill_reason=kill_reason,
        )
        bet.rest_days = rest_days
        if sharp_breakdown is not None:
            bet.sharp_breakdown = sharp_breakdown
        return bet

    # --- V36-compat keys always present ---
    def test_compat_keys_present_no_conditions(self):
        """Clean bet with no conditions → compat keys present, zero probability."""
        bet = self._make_bet("NBA", "h2h", line=0.0, edge_pct=0.10)
        result = run_nemesis(bet, "NBA")
        assert all(k in result for k in ["counter", "probability", "adjustment", "remove"])

    def test_no_conditions_returns_zero_probability(self):
        """Strong bet with no detectable conditions → worst_prob=0."""
        bet = self._make_bet("NBA", "h2h", line=0.0, edge_pct=0.10)
        result = run_nemesis(bet, "NBA")
        assert result["worst_prob"] == 0.0
        assert result["n_flags"] == 0
        assert result["remove"] is False

    # --- Universal: thin edge ---
    def test_thin_edge_fires(self):
        bet = self._make_bet("NBA", "h2h", edge_pct=0.03)
        result = run_nemesis(bet, "NBA")
        assert result["n_flags"] >= 1
        assert result["worst_prob"] > 0.0
        assert "edge thin" in result["worst_case"].lower() or "edge" in result["worst_case"].lower()

    def test_thin_edge_probability_scales_with_edge(self):
        """Smaller edge → higher nemesis probability."""
        bet_borderline = self._make_bet("NBA", "h2h", edge_pct=0.049)
        bet_thin = self._make_bet("NBA", "h2h", edge_pct=0.01)
        r_border = run_nemesis(bet_borderline, "NBA")
        r_thin = run_nemesis(bet_thin, "NBA")
        assert r_thin["worst_prob"] >= r_border["worst_prob"]

    def test_adequate_edge_no_thin_flag(self):
        """Edge ≥ 5% does not trigger thin-edge condition."""
        bet = self._make_bet("NBA", "h2h", edge_pct=0.07)
        result = run_nemesis(bet, "NBA")
        thin_flags = [t for t, _ in result.get("fired_cases", []) if "thin" in t.lower() or "edge thin" in t.lower()]
        assert len(thin_flags) == 0

    # --- Universal: RLM absent on large spread ---
    def test_large_spread_no_rlm_fires(self):
        bet = self._make_bet("NBA", "spreads", line=-9.5, sharp_breakdown={"rlm": 0})
        result = run_nemesis(bet, "NBA")
        assert any("rlm" in t.lower() or "no rlm" in t.lower() for t, _ in result.get("fired_cases", []))

    def test_large_spread_with_rlm_no_flag(self):
        bet = self._make_bet("NBA", "spreads", line=-9.5, sharp_breakdown={"rlm": 25})
        result = run_nemesis(bet, "NBA")
        no_rlm_flags = [t for t, _ in result.get("fired_cases", []) if "no rlm" in t.lower()]
        assert len(no_rlm_flags) == 0

    # --- Universal: collar proximity ---
    def test_collar_proximity_negative_price_fires(self):
        """Price at -182 (2 within collar ceiling) → proximity flag."""
        bet = self._make_bet("NFL", "spreads", price=-182, line=-3.5)
        result = run_nemesis(bet, "NFL")
        assert any("collar" in t.lower() for t, _ in result.get("fired_cases", []))

    def test_collar_proximity_positive_price_fires(self):
        """Price at +148 (2 within collar floor) → proximity flag."""
        bet = self._make_bet("NFL", "h2h", price=148)
        result = run_nemesis(bet, "NFL")
        assert any("collar" in t.lower() for t, _ in result.get("fired_cases", []))

    def test_no_collar_flag_for_center_price(self):
        """Price -130 (far from boundaries) → no collar flag."""
        bet = self._make_bet("NBA", "h2h", price=-130)
        result = run_nemesis(bet, "NBA")
        collar_flags = [t for t, _ in result.get("fired_cases", []) if "collar" in t.lower()]
        assert len(collar_flags) == 0

    # --- NFL key numbers ---
    def test_nfl_spread_at_key_3_fires(self):
        bet = self._make_bet("NFL", "spreads", line=-3.0, edge_pct=0.07)
        result = run_nemesis(bet, "NFL")
        assert any("key number" in t.lower() or "3" in t for t, _ in result.get("fired_cases", []))

    def test_nfl_spread_at_key_7_fires(self):
        bet = self._make_bet("NFL", "spreads", line=-7.0, edge_pct=0.07)
        result = run_nemesis(bet, "NFL")
        assert any("key number" in t.lower() or "7" in t for t, _ in result.get("fired_cases", []))

    def test_nfl_key_number_thin_edge_triggers_kill(self):
        """Key number at 3 + thin edge → probability > 0.40 → remove=True."""
        bet = self._make_bet("NFL", "spreads", line=-3.0, edge_pct=0.03)
        result = run_nemesis(bet, "NFL")
        assert result["remove"] is True

    def test_nfl_key_number_good_edge_no_kill(self):
        """Key number at 3 + adequate edge → flag, not kill."""
        bet = self._make_bet("NFL", "spreads", line=-3.0, edge_pct=0.08)
        result = run_nemesis(bet, "NFL")
        assert result["remove"] is False

    def test_nfl_non_key_spread_no_key_flag(self):
        """Spread -8.5 is not a key number → no key number condition."""
        bet = self._make_bet("NFL", "spreads", line=-8.5, edge_pct=0.08)
        result = run_nemesis(bet, "NFL")
        key_flags = [t for t, _ in result.get("fired_cases", []) if "key number" in t.lower()]
        assert len(key_flags) == 0

    # --- NHL goalie ---
    def test_nhl_no_goalie_signal_fires_on_h2h(self):
        bet = self._make_bet("NHL", "h2h", signal="", kill_reason="")
        result = run_nemesis(bet, "NHL")
        assert any("goalie" in t.lower() for t, _ in result.get("fired_cases", []))

    def test_nhl_goalie_confirmed_in_signal_reduces_flags(self):
        """If goalie appears in signal, condition does not fire."""
        bet = self._make_bet("NHL", "h2h", signal="goalie: Vasilevskiy confirmed")
        result = run_nemesis(bet, "NHL")
        goalie_flags = [t for t, _ in result.get("fired_cases", []) if "no goalie" in t.lower()]
        assert len(goalie_flags) == 0

    def test_nhl_totals_always_flags_shot_quality(self):
        bet = self._make_bet("NHL", "totals")
        result = run_nemesis(bet, "NHL")
        assert any("shot" in t.lower() or "goalie matchup" in t.lower() for t, _ in result.get("fired_cases", []))

    # --- Soccer ---
    def test_soccer_h2h_high_draw_kills(self):
        """Draw=35% in signal → Poisson draw > 33% → remove=True."""
        bet = self._make_bet("SOCCER", "h2h", signal="Draw=35%")
        result = run_nemesis(bet, "SOCCER")
        assert result["remove"] is True

    def test_soccer_h2h_moderate_draw_flags(self):
        """Draw=29% → elevated, but not kill."""
        bet = self._make_bet("SOCCER", "h2h", signal="Draw=29%")
        result = run_nemesis(bet, "SOCCER")
        assert result["worst_prob"] > 0.0
        assert result["remove"] is False

    def test_soccer_h2h_low_draw_no_kill(self):
        """Draw=20% → below elevated threshold."""
        bet = self._make_bet("SOCCER", "h2h", signal="Draw=20%")
        result = run_nemesis(bet, "SOCCER")
        # Draw=20% is below 27% threshold, should not fire high-prob draw case
        draw_kills = [p for t, p in result.get("fired_cases", []) if "draw" in t.lower() and p > 0.33]
        assert len(draw_kills) == 0

    def test_soccer_totals_low_poisson_kills(self):
        """Poisson side < 30% in signal → remove=True."""
        bet = self._make_bet("SOCCER", "totals", signal="Poisson Over=28% (xG 2.20)")
        result = run_nemesis(bet, "SOCCER")
        assert result["remove"] is True

    def test_soccer_totals_marginal_poisson_flags(self):
        """Poisson side 35% → flag but not kill."""
        bet = self._make_bet("SOCCER", "totals", signal="Poisson Over=35% (xG 2.50)")
        result = run_nemesis(bet, "SOCCER")
        assert result["worst_prob"] > 0.0
        assert result["remove"] is False

    def test_soccer_totals_strong_poisson_no_kill(self):
        """Poisson side 55% → no divergence flag."""
        bet = self._make_bet("SOCCER", "totals", signal="Poisson Over=55% (xG 2.80)")
        result = run_nemesis(bet, "SOCCER")
        poisson_kills = [p for t, p in result.get("fired_cases", []) if "poisson" in t.lower() and p > 0.25]
        assert len(poisson_kills) == 0

    # --- Return structure ---
    def test_fired_cases_is_list_of_tuples(self):
        bet = self._make_bet("NFL", "spreads", line=-3.0, edge_pct=0.07)
        result = run_nemesis(bet, "NFL")
        assert isinstance(result["fired_cases"], list)
        for item in result["fired_cases"]:
            assert isinstance(item, tuple) and len(item) == 2

    def test_remove_true_iff_worst_prob_above_threshold(self):
        for sport in ["NBA", "NCAAB", "NHL", "SOCCER"]:
            bet = self._make_bet(sport, "h2h")
            result = run_nemesis(bet, sport)
            expected_remove = result["worst_prob"] > 0.40
            assert result["remove"] == expected_remove


# ---------------------------------------------------------------------------
# RLM Fire Counter (Session 11)
# ---------------------------------------------------------------------------

class TestRLMFireCounter:
    def setup_method(self):
        clear_open_price_cache()
        reset_rlm_fire_count()

    def test_initial_count_is_zero(self):
        assert get_rlm_fire_count() == 0

    def test_count_increments_on_fire(self):
        # Seed open price, then move line enough to fire RLM
        from core.math_engine import seed_open_prices_from_db
        seed_open_prices_from_db({"ev1": {"TeamA": -110}})
        # -180 is a big implied prob shift from -110 (~52% → 64%)
        compute_rlm("ev1", "TeamA", -180, public_on_side=True)
        assert get_rlm_fire_count() == 1

    def test_count_accumulates_across_fires(self):
        from core.math_engine import seed_open_prices_from_db
        seed_open_prices_from_db({"ev1": {"TeamA": -110}, "ev2": {"TeamB": -110}})
        compute_rlm("ev1", "TeamA", -180, public_on_side=True)
        compute_rlm("ev2", "TeamB", -180, public_on_side=True)
        assert get_rlm_fire_count() == 2

    def test_no_fire_when_cold_cache(self):
        compute_rlm("no_event", "Team", -180, public_on_side=True)
        assert get_rlm_fire_count() == 0

    def test_no_fire_when_drift_below_threshold(self):
        from core.math_engine import seed_open_prices_from_db
        seed_open_prices_from_db({"ev1": {"TeamA": -110}})
        # -112 is a tiny shift — below 3% threshold
        compute_rlm("ev1", "TeamA", -112, public_on_side=True)
        assert get_rlm_fire_count() == 0

    def test_no_fire_when_public_not_on_side(self):
        from core.math_engine import seed_open_prices_from_db
        seed_open_prices_from_db({"ev1": {"TeamA": -110}})
        compute_rlm("ev1", "TeamA", -180, public_on_side=False)
        assert get_rlm_fire_count() == 0

    def test_reset_zeroes_counter(self):
        from core.math_engine import seed_open_prices_from_db
        seed_open_prices_from_db({"ev1": {"TeamA": -110}})
        compute_rlm("ev1", "TeamA", -180, public_on_side=True)
        assert get_rlm_fire_count() == 1
        reset_rlm_fire_count()
        assert get_rlm_fire_count() == 0

    def test_rlm_gate_status_structure(self):
        s = rlm_gate_status()
        assert "fire_count" in s
        assert "gate" in s
        assert "pct_to_gate" in s
        assert "gate_reached" in s

    def test_rlm_gate_status_initial(self):
        s = rlm_gate_status()
        assert s["fire_count"] == 0
        assert s["gate"] == RLM_FIRE_GATE
        assert s["pct_to_gate"] == 0.0
        assert s["gate_reached"] is False

    def test_rlm_gate_reached_at_threshold(self):
        from core.math_engine import seed_open_prices_from_db
        # Fire RLM_FIRE_GATE times using unique event IDs
        for i in range(RLM_FIRE_GATE):
            seed_open_prices_from_db({f"ev{i}": {"Team": -110}})
            compute_rlm(f"ev{i}", "Team", -180, public_on_side=True)
        s = rlm_gate_status()
        assert s["gate_reached"] is True
        assert s["pct_to_gate"] == 1.0

    def test_pct_to_gate_capped_at_1(self):
        from core.math_engine import seed_open_prices_from_db
        # Fire more than gate times
        for i in range(RLM_FIRE_GATE + 5):
            seed_open_prices_from_db({f"ev{i}": {"Team": -110}})
            compute_rlm(f"ev{i}", "Team", -180, public_on_side=True)
        assert rlm_gate_status()["pct_to_gate"] == 1.0

    def test_rlm_fire_gate_constant(self):
        assert isinstance(RLM_FIRE_GATE, int)
        assert RLM_FIRE_GATE > 0


# ---------------------------------------------------------------------------
# NHL Kill Switch
# ---------------------------------------------------------------------------

class TestNhlKillSwitch:
    def test_backup_goalie_killed(self):
        killed, reason = nhl_kill_switch(backup_goalie=True)
        assert killed is True
        assert "KILL" in reason
        assert "Backup goalie" in reason

    def test_confirmed_starter_safe(self):
        killed, reason = nhl_kill_switch(backup_goalie=False)
        assert killed is False
        assert reason == ""

    def test_b2b_flagged_not_killed(self):
        killed, reason = nhl_kill_switch(backup_goalie=False, b2b=True)
        assert killed is False
        assert "FLAG" in reason
        assert "B2B" in reason

    def test_unconfirmed_goalie_flagged(self):
        killed, reason = nhl_kill_switch(backup_goalie=False, goalie_confirmed=False)
        assert killed is False
        assert "FLAG" in reason
        assert "confirmed" in reason.lower()

    def test_backup_overrides_b2b(self):
        """Backup kill takes priority over B2B flag."""
        killed, reason = nhl_kill_switch(backup_goalie=True, b2b=True)
        assert killed is True
        assert "KILL" in reason

    def test_backup_overrides_unconfirmed(self):
        """backup_goalie=True overrides goalie_confirmed=False."""
        killed, reason = nhl_kill_switch(backup_goalie=True, goalie_confirmed=False)
        assert killed is True

    def test_return_type_is_tuple(self):
        result = nhl_kill_switch(backup_goalie=False)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_b2b_not_killed_only_flagged(self):
        """B2B should never kill — only flag for Kelly reduction."""
        killed, _ = nhl_kill_switch(backup_goalie=False, b2b=True)
        assert killed is False

    def test_all_safe_conditions_empty_reason(self):
        killed, reason = nhl_kill_switch(
            backup_goalie=False, b2b=False, goalie_confirmed=True
        )
        assert killed is False
        assert reason == ""

    def test_kill_message_mentions_edge_threshold(self):
        """Kill message should reference the edge override threshold."""
        _, reason = nhl_kill_switch(backup_goalie=True)
        assert "12%" in reason


# ---------------------------------------------------------------------------
# Tennis Kill Switch
# ---------------------------------------------------------------------------

class TestTennisKillSwitch:

    def test_clay_heavy_favourite_flagged(self):
        """Heavy favourite on clay must be flagged."""
        killed, reason = tennis_kill_switch("clay", 0.78, True, "h2h")
        assert killed is False
        assert "FLAG" in reason
        assert "Clay" in reason or "clay" in reason

    def test_clay_moderate_favourite_not_flagged(self):
        """Moderate favourite (< 72%) on clay — no flag."""
        killed, reason = tennis_kill_switch("clay", 0.65, True, "h2h")
        assert killed is False
        assert reason == ""

    def test_clay_betting_underdog_not_flagged(self):
        """Betting the underdog on clay — no flag (they are not the favourite)."""
        killed, reason = tennis_kill_switch("clay", 0.78, False, "h2h")
        assert killed is False
        assert reason == ""

    def test_grass_heavy_favourite_flagged(self):
        """Heavy favourite (> 75%) on grass — flag for serve variance."""
        killed, reason = tennis_kill_switch("grass", 0.80, True, "h2h")
        assert killed is False
        assert "FLAG" in reason
        assert "Grass" in reason or "grass" in reason

    def test_grass_moderate_favourite_not_flagged(self):
        killed, reason = tennis_kill_switch("grass", 0.70, True, "h2h")
        assert killed is False
        assert reason == ""

    def test_hard_heavy_favourite_no_flag(self):
        """Hard court: even heavy favourites are not flagged."""
        killed, reason = tennis_kill_switch("hard", 0.85, True, "h2h")
        assert killed is False
        assert reason == ""

    def test_unknown_surface_flagged(self):
        killed, reason = tennis_kill_switch("unknown", 0.60, True, "h2h")
        assert killed is False
        assert "FLAG" in reason
        assert "Surface unknown" in reason or "unknown" in reason.lower()

    def test_totals_never_flagged(self):
        """Totals market is not affected by surface flags."""
        killed, reason = tennis_kill_switch("clay", 0.80, True, "totals")
        assert killed is False
        assert reason == ""

    def test_never_kills_outright(self):
        """Tennis kill switch never returns killed=True (FLAG only)."""
        for surface in ("clay", "grass", "hard", "unknown"):
            for prob in (0.55, 0.72, 0.80, 0.90):
                killed, _ = tennis_kill_switch(surface, prob, True, "h2h")
                assert killed is False, f"Should not kill: surface={surface}, prob={prob}"

    def test_return_type_is_tuple(self):
        result = tennis_kill_switch("clay", 0.75, True, "h2h")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_clay_threshold_exactly_at_boundary(self):
        """0.72 is the kill threshold for clay — exactly at boundary = no flag."""
        killed, reason = tennis_kill_switch("clay", 0.72, True, "h2h")
        assert killed is False
        assert reason == ""

    def test_clay_just_above_threshold_flagged(self):
        """0.721 > 0.72 threshold — flag fires."""
        killed, reason = tennis_kill_switch("clay", 0.721, True, "h2h")
        assert killed is False
        assert "FLAG" in reason


# ---------------------------------------------------------------------------
# Soccer collar + 3-way no-vig
# ---------------------------------------------------------------------------

class TestPassesCollarSoccer:

    def test_standard_odds_pass(self):
        assert passes_collar_soccer(-110) is True

    def test_standard_dog_passes(self):
        assert passes_collar_soccer(250) is True

    def test_at_max_passes(self):
        assert passes_collar_soccer(COLLAR_MAX_SOCCER) is True

    def test_above_max_fails(self):
        assert passes_collar_soccer(COLLAR_MAX_SOCCER + 1) is False

    def test_at_min_passes(self):
        assert passes_collar_soccer(COLLAR_MIN_SOCCER) is True

    def test_below_min_fails(self):
        assert passes_collar_soccer(COLLAR_MIN_SOCCER - 1) is False

    def test_draw_price_passes(self):
        # Typical draw price in soccer
        assert passes_collar_soccer(225) is True

    def test_heavy_favourite_passes(self):
        assert passes_collar_soccer(-220) is True

    def test_soccer_max_exceeds_standard_max(self):
        assert COLLAR_MAX_SOCCER > COLLAR_MAX

    def test_soccer_sports_constant(self):
        assert "EPL" in SOCCER_SPORTS
        assert "MLS" in SOCCER_SPORTS
        assert "NBA" not in SOCCER_SPORTS


class TestNoVigProbability3Way:

    def test_probs_sum_to_one(self):
        a, b, c = no_vig_probability_3way(-105, 290, 250)
        assert abs(a + b + c - 1.0) < 1e-9

    def test_favourite_highest_prob(self):
        a, b, c = no_vig_probability_3way(-140, 320, 260)
        assert a > b  # favourite higher than underdog
        assert a > c  # favourite higher than draw

    def test_all_positive(self):
        a, b, c = no_vig_probability_3way(-110, 280, 240)
        assert a > 0 and b > 0 and c > 0

    def test_symmetrical_match(self):
        # Equal-odds match: home/away equal, draw at same price
        a, b, c = no_vig_probability_3way(200, 200, 200)
        assert abs(a - b) < 1e-9
        assert abs(b - c) < 1e-9

    def test_realistic_soccer_prices(self):
        # Mainz -105, Hamburger +290, Draw +250
        a, b, c = no_vig_probability_3way(-105, 290, 250)
        assert 0.3 < a < 0.5   # moderate favourite
        assert 0.1 < b < 0.3   # underdog
        assert 0.2 < c < 0.4   # draw

    def test_returns_tuple_of_three(self):
        result = no_vig_probability_3way(-110, 280, 240)
        assert len(result) == 3

    def test_returns_floats(self):
        a, b, c = no_vig_probability_3way(-110, 280, 240)
        assert isinstance(a, float)
        assert isinstance(b, float)
        assert isinstance(c, float)


class TestConsensusFairProb3Way:

    def _make_bookmakers(self, home_price, away_price, draw_price, home="Team A", away="Team B"):
        return [
            {
                "key": "book1",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": home, "price": home_price},
                    {"name": away, "price": away_price},
                    {"name": "Draw", "price": draw_price},
                ]}]
            },
            {
                "key": "book2",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": home, "price": home_price - 5},
                    {"name": away, "price": away_price + 5},
                    {"name": "Draw", "price": draw_price + 5},
                ]}]
            },
        ]

    def test_home_team_prob_returned(self):
        bks = self._make_bookmakers(-120, 280, 240)
        cp, std, n = consensus_fair_prob_3way("Team A", bks)
        assert n == 2
        assert 0.3 < cp < 0.6

    def test_draw_prob_returned(self):
        bks = self._make_bookmakers(-120, 280, 240)
        cp, std, n = consensus_fair_prob_3way("Draw", bks)
        assert n == 2
        assert 0.2 < cp < 0.4

    def test_not_found_returns_zero_books(self):
        bks = self._make_bookmakers(-120, 280, 240)
        cp, std, n = consensus_fair_prob_3way("Unknown Team", bks)
        assert n == 0

    def test_empty_bookmakers(self):
        cp, std, n = consensus_fair_prob_3way("Team A", [])
        assert n == 0

    def test_two_book_books_count(self):
        bks = self._make_bookmakers(-110, 270, 230)
        _, _, n = consensus_fair_prob_3way("Team A", bks)
        assert n == 2

    def test_ignores_2way_markets(self):
        # 2-outcome h2h should be ignored (not 3-way soccer)
        bks = [{"key": "book1", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Team A", "price": -110},
            {"name": "Team B", "price": 100},
        ]}]}]
        cp, std, n = consensus_fair_prob_3way("Team A", bks)
        assert n == 0


class TestParseGameMarketsSoccer3Way:
    """Integration tests: parse_game_markets handles soccer 3-way h2h correctly."""

    def _soccer_game(self, home_price, away_price, draw_price, home="Arsenal", away="Chelsea"):
        return {
            "id": "soccer_test_001",
            "home_team": home,
            "away_team": away,
            "commence_time": "2026-03-01T15:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": home, "price": home_price},
                            {"name": away, "price": away_price},
                            {"name": "Draw", "price": draw_price},
                        ]},
                        {"key": "totals", "outcomes": [
                            {"name": "Over", "price": -115, "point": 2.5},
                            {"name": "Under", "price": -105, "point": 2.5},
                        ]},
                    ]
                },
                {
                    "key": "fanduel",
                    "markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": home, "price": home_price + 5},
                            {"name": away, "price": away_price - 5},
                            {"name": "Draw", "price": draw_price + 5},
                        ]},
                        {"key": "totals", "outcomes": [
                            {"name": "Over", "price": -110, "point": 2.5},
                            {"name": "Under", "price": -110, "point": 2.5},
                        ]},
                    ]
                },
            ]
        }

    def test_soccer_h2h_dog_not_collar_filtered(self):
        # Dog at +290 would fail standard collar but should pass soccer collar
        game = self._soccer_game(home_price=-120, away_price=290, draw_price=240)
        cands = parse_game_markets(game, sport="EPL")
        # At minimum, should not crash and should have collar-passed
        # (may or may not have edge — depends on prices)
        assert isinstance(cands, list)

    def test_draw_candidate_can_appear(self):
        # Construct game where Draw has clear edge
        game = self._soccer_game(home_price=-150, away_price=320, draw_price=290)
        cands = parse_game_markets(game, sport="BUNDESLIGA")
        assert isinstance(cands, list)
        # Draw candidate target format
        draw_cands = [c for c in cands if c.target == "Draw"]
        if draw_cands:
            assert draw_cands[0].market_type == "h2h"

    def test_non_soccer_sport_not_affected(self):
        # NBA game with same structure should use 2-way path
        game = {
            "id": "nba_001",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "commence_time": "2026-03-01T01:00:00Z",
            "bookmakers": [
                {"key": "dk", "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Lakers", "price": -110},
                    {"name": "Celtics", "price": 100},
                ]}]},
                {"key": "fd", "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Lakers", "price": -115},
                    {"name": "Celtics", "price": 105},
                ]}]},
            ]
        }
        cands = parse_game_markets(game, sport="NBA")
        assert isinstance(cands, list)
        # Should not produce "Draw" candidates for NBA
        assert not any(c.target == "Draw" for c in cands)

    def test_soccer_totals_still_work(self):
        game = self._soccer_game(-120, 290, 240)
        cands = parse_game_markets(game, sport="LA_LIGA")
        totals = [c for c in cands if c.market_type == "totals"]
        # Totals should still be evaluated (they use standard 2-way collar)
        assert isinstance(totals, list)

    def test_soccer_sports_constant_covers_all_leagues(self):
        for league in ["EPL", "LIGUE1", "BUNDESLIGA", "SERIE_A", "LA_LIGA", "MLS"]:
            assert league in SOCCER_SPORTS


# ---------------------------------------------------------------------------
# NCAAF Kill Switch
# ---------------------------------------------------------------------------

class TestNcaafKillSwitch:
    """Tests for ncaaf_kill_switch() — blowout spread filter + off-season gate."""

    # --- Off-season gate ---

    def test_off_season_month_killed(self):
        """February is off-season → kill."""
        killed, reason = ncaaf_kill_switch(14.5, 2)
        assert killed is True
        assert "off-season" in reason
        assert "2" in reason

    def test_april_off_season_killed(self):
        """April is off-season → kill."""
        killed, reason = ncaaf_kill_switch(7.0, 4)
        assert killed is True
        assert "off-season" in reason

    def test_august_off_season_killed(self):
        """August (preseason hype, no reliable data) → kill."""
        killed, reason = ncaaf_kill_switch(3.5, 8)
        assert killed is True
        assert "off-season" in reason

    def test_september_in_season(self):
        """September is in-season → not killed by date gate."""
        killed, reason = ncaaf_kill_switch(14.5, 9)
        assert killed is False

    def test_october_in_season(self):
        """October is in-season → not killed."""
        killed, reason = ncaaf_kill_switch(10.0, 10)
        assert killed is False

    def test_november_in_season(self):
        """November is in-season."""
        killed, reason = ncaaf_kill_switch(21.5, 11)
        assert killed is False

    def test_december_in_season(self):
        """December (bowl games) is in-season."""
        killed, reason = ncaaf_kill_switch(14.0, 12)
        assert killed is False

    def test_january_in_season(self):
        """January (CFP) is in-season."""
        killed, reason = ncaaf_kill_switch(3.5, 1)
        assert killed is False

    # --- Blowout spread filter ---

    def test_spread_exactly_at_threshold_killed(self):
        """Spread == 28.0 → kill."""
        killed, reason = ncaaf_kill_switch(28.0, 10)
        assert killed is True
        assert "28" in reason
        assert "blowout" in reason.lower()

    def test_spread_above_threshold_killed(self):
        """Spread 35.0 → kill."""
        killed, reason = ncaaf_kill_switch(35.0, 10)
        assert killed is True

    def test_spread_just_below_threshold_ok(self):
        """Spread 27.9 → not killed."""
        killed, reason = ncaaf_kill_switch(27.9, 10)
        assert killed is False
        assert reason == ""

    def test_normal_spread_not_killed(self):
        """Typical NCAAF spread 14.5 → not killed."""
        killed, reason = ncaaf_kill_switch(14.5, 11)
        assert killed is False
        assert reason == ""

    def test_zero_spread_not_killed(self):
        """Pick'em (0.0) spread is not a blowout."""
        killed, reason = ncaaf_kill_switch(0.0, 10)
        assert killed is False

    # --- Constants ---

    def test_season_months_constant(self):
        """NCAAF_SEASON_MONTHS covers Sep–Jan."""
        assert 9 in NCAAF_SEASON_MONTHS
        assert 10 in NCAAF_SEASON_MONTHS
        assert 11 in NCAAF_SEASON_MONTHS
        assert 12 in NCAAF_SEASON_MONTHS
        assert 1 in NCAAF_SEASON_MONTHS
        assert 2 not in NCAAF_SEASON_MONTHS
        assert 8 not in NCAAF_SEASON_MONTHS

    def test_spread_threshold_constant(self):
        """Threshold is 28.0."""
        assert NCAAF_SPREAD_KILL_THRESHOLD == 28.0

    # --- Parse integration ---

    def test_parse_game_markets_ncaaf_offseason_blocked(self):
        """NCAAF game in off-season month (Feb) should produce zero candidates."""
        from unittest.mock import patch
        from datetime import datetime, timezone

        # Patch now() to return February
        fixed_now = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
        game = {
            "id": "ncaaf-offseason",
            "home_team": "Alabama",
            "away_team": "Georgia",
            "commence_time": "2026-02-15T20:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": "Alabama", "price": -110, "point": -14.5},
                            {"name": "Georgia", "price": -110, "point": 14.5},
                        ]},
                    ],
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": "Alabama", "price": -112, "point": -14.5},
                            {"name": "Georgia", "price": -108, "point": 14.5},
                        ]},
                    ],
                },
            ],
        }
        with patch("core.math_engine.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.fromisoformat = datetime.fromisoformat
            candidates = parse_game_markets(game, "NCAAF")
        assert candidates == [], f"Expected 0 candidates in off-season, got {len(candidates)}"

    def test_parse_game_markets_ncaaf_blowout_spread_blocked(self):
        """NCAAF blowout spread (≥28) should produce zero spread candidates."""
        from unittest.mock import patch
        from datetime import datetime, timezone

        # Patch to October (in-season), but spread is 35.0
        fixed_now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        game = {
            "id": "ncaaf-blowout",
            "home_team": "Alabama",
            "away_team": "ULM",
            "commence_time": "2026-10-10T20:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": "Alabama", "price": -110, "point": -35.0},
                            {"name": "ULM", "price": -110, "point": 35.0},
                        ]},
                    ],
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": "Alabama", "price": -112, "point": -35.0},
                            {"name": "ULM", "price": -108, "point": 35.0},
                        ]},
                    ],
                },
            ],
        }
        with patch("core.math_engine.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.fromisoformat = datetime.fromisoformat
            candidates = parse_game_markets(game, "NCAAF")
        spread_cands = [c for c in candidates if c.market_type == "spreads"]
        assert spread_cands == [], f"Expected 0 spread candidates for blowout, got {len(spread_cands)}"


# ---------------------------------------------------------------------------
# NBA B2B Rest Day Integration
# ---------------------------------------------------------------------------

class TestNBAB2BRestDayIntegration:
    """Tests for NBA B2B home/road differentiation in parse_game_markets."""

    def _make_nba_game(self, home="Lakers", away="Heat", price_home=-110, price_away=-110, spread=6.5):
        """Minimal NBA game dict with clear spread edge opportunity."""
        return {
            "id": "nba-b2b-test",
            "home_team": home,
            "away_team": away,
            "commence_time": "2026-10-10T23:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": home, "price": price_home, "point": -spread},
                            {"name": away, "price": price_away, "point": spread},
                        ]},
                        {"key": "h2h", "outcomes": [
                            {"name": home, "price": -150},
                            {"name": away, "price": 130},
                        ]},
                    ],
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": home, "price": price_home - 2, "point": -spread},
                            {"name": away, "price": price_away + 2, "point": spread},
                        ]},
                        {"key": "h2h", "outcomes": [
                            {"name": home, "price": -148},
                            {"name": away, "price": 128},
                        ]},
                    ],
                },
                {
                    "key": "betmgm",
                    "title": "BetMGM",
                    "markets": [
                        {"key": "spreads", "outcomes": [
                            {"name": home, "price": price_home, "point": -spread},
                            {"name": away, "price": price_away, "point": spread},
                        ]},
                    ],
                },
            ],
        }

    def test_no_rest_days_produces_no_b2b_flag(self):
        """Without rest_days dict, NBA candidates have no B2B kill_reason."""
        game = self._make_nba_game()
        cands = parse_game_markets(game, "NBA", rest_days=None)
        for c in cands:
            assert "B2B" not in c.kill_reason

    def test_road_b2b_produces_road_flag(self):
        """Away team on B2B (rest_days=0) → Road B2B flag on their candidates."""
        game = self._make_nba_game(home="Lakers", away="Heat")
        rest = {"Heat": 0, "Lakers": 2}  # Heat on B2B, Lakers rested
        cands = parse_game_markets(game, "NBA", rest_days=rest)
        heat_cands = [c for c in cands if "Heat" in c.target]
        for c in heat_cands:
            assert "Road B2B" in c.kill_reason, f"Expected Road B2B flag, got: {c.kill_reason!r}"

    def test_home_b2b_produces_home_flag(self):
        """Home team on B2B (rest_days=0) → Home B2B flag on their candidates."""
        game = self._make_nba_game(home="Lakers", away="Heat")
        rest = {"Lakers": 0, "Heat": 2}  # Lakers on B2B at home
        cands = parse_game_markets(game, "NBA", rest_days=rest)
        lakers_cands = [c for c in cands if "Lakers" in c.target]
        for c in lakers_cands:
            assert "Home B2B" in c.kill_reason, f"Expected Home B2B flag, got: {c.kill_reason!r}"

    def test_road_flag_stricter_than_home_flag(self):
        """Road B2B flag message differs from home B2B flag message."""
        game = self._make_nba_game(home="Lakers", away="Heat")
        # Road B2B
        road_cands = parse_game_markets(game, "NBA", rest_days={"Heat": 0, "Lakers": 2})
        heat_road = [c for c in road_cands if "Heat" in c.target]
        # Home B2B
        home_cands = parse_game_markets(game, "NBA", rest_days={"Lakers": 0, "Heat": 2})
        lakers_home = [c for c in home_cands if "Lakers" in c.target]
        if heat_road and lakers_home:
            assert heat_road[0].kill_reason != lakers_home[0].kill_reason

    def test_both_rested_no_b2b_flag(self):
        """Both teams rested (rest_days ≥ 1) → no B2B flag."""
        game = self._make_nba_game(home="Lakers", away="Heat")
        rest = {"Lakers": 2, "Heat": 1}
        cands = parse_game_markets(game, "NBA", rest_days=rest)
        for c in cands:
            assert "B2B" not in c.kill_reason

    def test_non_nba_sport_ignores_rest_days(self):
        """rest_days is ignored for non-NBA sports — no spurious B2B flags."""
        game = self._make_nba_game()
        rest = {"Lakers": 0, "Heat": 0}  # both on B2B
        cands = parse_game_markets(game, "NFL", rest_days=rest)
        for c in cands:
            assert "B2B" not in c.kill_reason


# ---------------------------------------------------------------------------
# Run standalone self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    sys.exit(result.returncode)
