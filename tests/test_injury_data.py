"""
tests/test_injury_data.py — Titanium-Agentic
=============================================
Unit tests for core/injury_data.py.

Coverage:
  - get_positional_leverage(): known positions, unknowns, aliases
  - evaluate_injury_impact(): starter vs non-starter, direction, market types
  - injury_kill_switch(): return format, thresholds
  - list_high_leverage_positions(): sorting, threshold filtering
  - get_sport_leverage_summary(): completeness, pivotals
"""

import pytest
from core.injury_data import (
    LEVERAGE_KILL_THRESHOLD,
    LEVERAGE_FLAG_THRESHOLD,
    InjuryReport,
    evaluate_injury_impact,
    get_positional_leverage,
    get_sport_leverage_summary,
    injury_kill_switch,
    list_high_leverage_positions,
)


# ---------------------------------------------------------------------------
# get_positional_leverage
# ---------------------------------------------------------------------------

class TestGetPositionalLeverage:

    def test_nba_pg(self):
        lev, piv = get_positional_leverage("NBA", "PG")
        assert lev == 3.0
        assert piv is True

    def test_nfl_qb(self):
        lev, piv = get_positional_leverage("NFL", "QB")
        assert lev == 4.5
        assert piv is True

    def test_nhl_goalie(self):
        lev, piv = get_positional_leverage("NHL", "G")
        assert lev == 3.5
        assert piv is True

    def test_mlb_sp(self):
        lev, piv = get_positional_leverage("MLB", "SP")
        assert lev == 2.0
        assert piv is True

    def test_soccer_st(self):
        lev, piv = get_positional_leverage("SOCCER", "ST")
        assert lev == 1.2
        assert piv is True

    def test_soccer_gk(self):
        lev, piv = get_positional_leverage("SOCCER", "GK")
        assert lev == 1.5
        assert piv is True

    def test_nfl_rb_not_pivotal(self):
        lev, piv = get_positional_leverage("NFL", "RB")
        assert lev == 1.5
        assert piv is False

    def test_unknown_position_returns_zero(self):
        lev, piv = get_positional_leverage("NBA", "UNKNOWN")
        assert lev == 0.0
        assert piv is False

    def test_unknown_sport_returns_zero(self):
        lev, piv = get_positional_leverage("TENNIS", "PG")
        assert lev == 0.0
        assert piv is False

    def test_sport_alias_ncaab_uses_nba(self):
        """NCAAB maps to NBA table."""
        lev, piv = get_positional_leverage("ncaab", "PG")
        assert lev == 3.0
        assert piv is True

    def test_sport_alias_ncaaf_uses_nfl(self):
        lev, piv = get_positional_leverage("ncaaf", "QB")
        assert lev == 4.5

    def test_case_insensitive_sport(self):
        lev1, _ = get_positional_leverage("nba", "PG")
        lev2, _ = get_positional_leverage("NBA", "PG")
        assert lev1 == lev2

    def test_case_insensitive_position(self):
        lev1, _ = get_positional_leverage("NFL", "qb")
        lev2, _ = get_positional_leverage("NFL", "QB")
        assert lev1 == lev2

    def test_nba_center_pivotal(self):
        lev, piv = get_positional_leverage("NBA", "C")
        assert piv is True

    def test_nfl_kicker_low_leverage(self):
        lev, _ = get_positional_leverage("NFL", "K")
        assert lev < 1.0

    def test_all_nba_leverages_positive(self):
        for pos in ["PG", "SG", "SF", "PF", "C", "G", "F"]:
            lev, _ = get_positional_leverage("NBA", pos)
            assert lev > 0

    def test_all_nfl_leverages_positive(self):
        for pos in ["QB", "RB", "WR", "TE", "CB"]:
            lev, _ = get_positional_leverage("NFL", pos)
            assert lev > 0

    def test_nfl_qb_highest_in_sport(self):
        """QB must be highest leverage in NFL."""
        qb_lev, _ = get_positional_leverage("NFL", "QB")
        for pos in ["RB", "WR", "TE", "CB", "LB"]:
            other_lev, _ = get_positional_leverage("NFL", pos)
            assert qb_lev > other_lev


# ---------------------------------------------------------------------------
# evaluate_injury_impact
# ---------------------------------------------------------------------------

class TestEvaluateInjuryImpact:

    def test_nba_pg_starter_home_injury_home_bet_flags(self):
        """Home PG out, betting home spread → FLAG (3.0pt leverage < 3.5 kill threshold)."""
        r = evaluate_injury_impact("NBA", "PG", True, "home", "spreads", "home")
        assert r.flag is True
        assert r.signed_impact < 0

    def test_non_starter_no_impact(self):
        """Backup player absence → zero impact."""
        r = evaluate_injury_impact("NBA", "PG", False, "home", "spreads", "home")
        assert r.leverage_pts == 0.0
        assert r.flag is False
        assert r.kill is False

    def test_nfl_qb_out_away_kills_home_bet(self):
        """Away QB out, betting home → helps (positive impact, no kill)."""
        r = evaluate_injury_impact("NFL", "QB", True, "away", "spreads", "home")
        assert r.signed_impact > 0
        assert r.kill is False  # positive impact, not a kill

    def test_nfl_qb_out_same_side_kills(self):
        """Away QB out, betting away → hurts bet → kill."""
        r = evaluate_injury_impact("NFL", "QB", True, "away", "spreads", "away")
        assert r.kill is True
        assert r.signed_impact < 0

    def test_totals_market_negative_impact(self):
        """Totals: any absence reduces expected scoring."""
        r = evaluate_injury_impact("NBA", "PG", True, "home", "totals", "home")
        assert r.signed_impact < 0

    def test_unknown_position_no_flag(self):
        r = evaluate_injury_impact("NBA", "UNKNOWNPOS", True, "home", "spreads", "home")
        assert r.flag is False
        assert r.kill is False
        assert r.leverage_pts == 0.0

    def test_returns_injury_report(self):
        r = evaluate_injury_impact("NFL", "QB", True, "home", "spreads", "home")
        assert isinstance(r, InjuryReport)

    def test_advisory_contains_sport_and_position(self):
        r = evaluate_injury_impact("NHL", "G", True, "home", "spreads", "home")
        assert "NHL" in r.advisory
        assert "G" in r.advisory

    def test_advisory_contains_severity_label(self):
        r = evaluate_injury_impact("NBA", "PG", True, "home", "spreads", "home")
        assert "KILL" in r.advisory or "FLAG" in r.advisory

    def test_pivotal_position_tagged_in_advisory(self):
        r = evaluate_injury_impact("NFL", "QB", True, "home", "spreads", "home")
        assert "PIVOTAL" in r.advisory

    def test_non_pivotal_no_pivotal_tag(self):
        r = evaluate_injury_impact("NFL", "RB", True, "home", "spreads", "home")
        assert "PIVOTAL" not in r.advisory

    def test_flag_threshold_not_triggered_for_rb(self):
        """NFL RB out (1.5pt leverage < 2.0 flag threshold) → no flag."""
        r = evaluate_injury_impact("NFL", "RB", True, "home", "spreads", "home")
        assert r.flag is False
        assert r.kill is False

    def test_low_leverage_position_no_flag(self):
        """NFL kicker out → leverage 0.5 → below flag threshold."""
        r = evaluate_injury_impact("NFL", "K", True, "home", "spreads", "home")
        assert r.flag is False
        assert r.kill is False

    def test_nhl_goalie_kill(self):
        """NHL goalie out → 3.5pt leverage → kill."""
        r = evaluate_injury_impact("NHL", "G", True, "home", "spreads", "home")
        assert r.kill is True

    def test_mlb_sp_flag(self):
        """MLB SP out → 2.0pt leverage → flag but not kill."""
        r = evaluate_injury_impact("MLB", "SP", True, "home", "spreads", "home")
        assert r.flag is True
        assert r.kill is False

    def test_soccer_striker_no_flag(self):
        """Soccer ST out → 1.2pt leverage < 2.0 flag threshold → no flag."""
        r = evaluate_injury_impact("SOCCER", "ST", True, "home", "spreads", "home")
        assert r.flag is False
        assert r.leverage_pts == 1.2

    def test_injury_helps_bet_when_opponent_missing_key_player(self):
        """Away QB out, betting home → positive signed_impact."""
        r = evaluate_injury_impact("NFL", "QB", True, "away", "spreads", "home")
        assert r.signed_impact > 0

    def test_sport_field_normalised(self):
        r = evaluate_injury_impact("nba", "PG", True, "home", "spreads", "home")
        assert r.sport == "NBA"

    def test_position_field_normalised(self):
        r = evaluate_injury_impact("NBA", "pg", True, "home", "spreads", "home")
        assert r.position == "PG"


# ---------------------------------------------------------------------------
# injury_kill_switch
# ---------------------------------------------------------------------------

class TestInjuryKillSwitch:

    def test_returns_tuple(self):
        result = injury_kill_switch("NBA", "PG", True, "home", "spreads", "home")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_nba_pg_starter_home_flags(self):
        """PG leverage=3.0pt < KILL threshold=3.5 → flag, not kill."""
        should_kill, reason = injury_kill_switch("NBA", "PG", True, "home", "spreads", "home")
        assert should_kill is False
        assert "FLAG" in reason

    def test_non_starter_no_kill(self):
        should_kill, reason = injury_kill_switch("NBA", "PG", False, "home", "spreads", "home")
        assert should_kill is False

    def test_low_leverage_returns_false_empty(self):
        should_kill, reason = injury_kill_switch("NFL", "K", True, "home", "spreads", "home")
        assert should_kill is False
        assert reason == ""

    def test_rb_below_flag_threshold_empty_reason(self):
        """RB 1.5pt leverage < 2.0 flag threshold → no flag, empty reason."""
        should_kill, reason = injury_kill_switch("NFL", "RB", True, "home", "spreads", "home")
        assert should_kill is False
        assert reason == ""

    def test_nhl_goalie_kills(self):
        should_kill, _ = injury_kill_switch("NHL", "G", True, "home", "spreads", "home")
        assert should_kill is True

    def test_kill_reason_has_leverage_pts(self):
        _, reason = injury_kill_switch("NBA", "PG", True, "home", "spreads", "home")
        assert "3.0pt" in reason or "3.0" in reason

    def test_unknown_position_no_kill(self):
        should_kill, reason = injury_kill_switch("NBA", "BENCH_WARMER", True, "home", "spreads", "home")
        assert should_kill is False
        assert reason == ""


# ---------------------------------------------------------------------------
# list_high_leverage_positions
# ---------------------------------------------------------------------------

class TestListHighLeveragePositions:

    def test_nfl_returns_qb_first(self):
        positions = list_high_leverage_positions("NFL", min_leverage=2.0)
        assert len(positions) > 0
        assert positions[0][0] == "QB"
        assert positions[0][1] == 4.5

    def test_sorted_descending(self):
        positions = list_high_leverage_positions("NBA", min_leverage=0.0)
        for i in range(len(positions) - 1):
            assert positions[i][1] >= positions[i + 1][1]

    def test_threshold_filters_low_leverage(self):
        """min_leverage=3.0 should exclude most positions."""
        positions = list_high_leverage_positions("NBA", min_leverage=3.0)
        for _, lev, _ in positions:
            assert lev >= 3.0

    def test_returns_tuples(self):
        positions = list_high_leverage_positions("NHL")
        for item in positions:
            assert len(item) == 3
            pos, lev, piv = item
            assert isinstance(pos, str)
            assert isinstance(lev, float)
            assert isinstance(piv, bool)

    def test_unknown_sport_returns_empty(self):
        assert list_high_leverage_positions("TENNIS") == []

    def test_nhl_goalie_in_high_leverage(self):
        positions = list_high_leverage_positions("NHL", min_leverage=3.0)
        pos_names = [p[0] for p in positions]
        assert "G" in pos_names


# ---------------------------------------------------------------------------
# get_sport_leverage_summary
# ---------------------------------------------------------------------------

class TestGetSportLeverageSummary:

    def test_nba_max_leverage(self):
        s = get_sport_leverage_summary("NBA")
        assert s["max_leverage"] == 3.0

    def test_nfl_max_leverage(self):
        s = get_sport_leverage_summary("NFL")
        assert s["max_leverage"] == 4.5

    def test_pivotal_positions_populated(self):
        s = get_sport_leverage_summary("NBA")
        assert len(s["pivotal_positions"]) > 0
        assert "PG" in s["pivotal_positions"]

    def test_total_positions_count(self):
        s = get_sport_leverage_summary("NFL")
        assert s["total_positions"] >= 10

    def test_unknown_sport_returns_zeros(self):
        s = get_sport_leverage_summary("TENNIS")
        assert s["max_leverage"] == 0.0
        assert s["total_positions"] == 0

    def test_min_leverage_below_max(self):
        s = get_sport_leverage_summary("NFL")
        assert s["min_leverage"] <= s["max_leverage"]

    def test_nhl_goalie_in_pivotal(self):
        s = get_sport_leverage_summary("NHL")
        assert "G" in s["pivotal_positions"]

    def test_mlb_sp_in_pivotal(self):
        s = get_sport_leverage_summary("MLB")
        assert "SP" in s["pivotal_positions"]
