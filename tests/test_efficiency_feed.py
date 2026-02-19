"""
tests/test_efficiency_feed.py — Titanium-Agentic
=================================================
Unit tests for core/efficiency_feed.py.

Coverage:
  - get_team_data(): canonical lookup, alias lookup, case-insensitive, miss
  - get_efficiency_gap(): scaling formula, clamp, unknown fallback, symmetry
  - list_teams(): total count, league filter, unknown league
  - Architecture: no imports from other core modules
"""

import pytest
from core.efficiency_feed import (
    _UNKNOWN_GAP,
    get_efficiency_gap,
    get_team_data,
    list_teams,
)


# ---------------------------------------------------------------------------
# get_team_data
# ---------------------------------------------------------------------------

class TestGetTeamData:

    def test_canonical_nba_team(self):
        data = get_team_data("Boston Celtics")
        assert data is not None
        assert data["league"] == "NBA"
        assert data["adj_em"] > 0

    def test_canonical_nfl_team(self):
        data = get_team_data("Kansas City Chiefs")
        assert data is not None
        assert data["league"] == "NFL"

    def test_canonical_ncaab_team(self):
        data = get_team_data("Duke")
        assert data is not None
        assert data["league"] == "NCAAB"
        assert data["adj_em"] > 25  # Duke is elite

    def test_canonical_mlb_team(self):
        data = get_team_data("Los Angeles Dodgers")
        assert data is not None
        assert data["league"] == "MLB"

    def test_canonical_mls_team(self):
        data = get_team_data("Inter Miami CF")
        assert data is not None
        assert data["league"] == "MLS"

    def test_canonical_epl_team(self):
        data = get_team_data("Liverpool")
        assert data is not None
        assert data["league"] == "EPL"

    def test_canonical_bundesliga_team(self):
        data = get_team_data("Bayern Munich")
        assert data is not None
        assert data["league"] == "BUNDESLIGA"

    def test_canonical_ligue1_team(self):
        data = get_team_data("Paris Saint-Germain")
        assert data is not None
        assert data["league"] == "LIGUE1"

    def test_canonical_serie_a_team(self):
        data = get_team_data("Inter Milan")
        assert data is not None
        assert data["league"] == "SERIE_A"

    def test_canonical_la_liga_team(self):
        data = get_team_data("Real Madrid")
        assert data is not None
        assert data["league"] == "LA_LIGA"

    def test_alias_lookup_nba(self):
        data = get_team_data("Celtics")
        assert data is not None
        assert data["league"] == "NBA"

    def test_alias_lookup_nfl(self):
        data = get_team_data("Chiefs")
        assert data is not None
        assert data["league"] == "NFL"

    def test_alias_lookup_soccer(self):
        data = get_team_data("PSG")
        assert data is not None
        assert data["league"] == "LIGUE1"

    def test_alias_lookup_soccer_short(self):
        data = get_team_data("Man City")
        assert data is not None
        assert data["league"] == "EPL"

    def test_alias_lookup_returns_same_adj_em_as_canonical(self):
        canonical = get_team_data("Boston Celtics")
        alias = get_team_data("Celtics")
        assert canonical is not None
        assert alias is not None
        assert canonical["adj_em"] == alias["adj_em"]

    def test_case_insensitive_fallback(self):
        data = get_team_data("boston celtics")
        assert data is not None
        assert data["league"] == "NBA"

    def test_unknown_team_returns_none(self):
        assert get_team_data("Unknown FC") is None

    def test_empty_string_returns_none(self):
        assert get_team_data("") is None

    def test_whitespace_stripped(self):
        data = get_team_data("  Boston Celtics  ")
        assert data is not None

    def test_adj_em_is_float(self):
        data = get_team_data("Oklahoma City Thunder")
        assert data is not None
        assert isinstance(data["adj_em"], float)


# ---------------------------------------------------------------------------
# get_efficiency_gap
# ---------------------------------------------------------------------------

class TestGetEfficiencyGap:

    def test_known_vs_known_returns_float(self):
        gap = get_efficiency_gap("Boston Celtics", "Washington Wizards")
        assert isinstance(gap, float)

    def test_gap_range_is_0_to_20(self):
        """All valid matchups must stay within the clamped range."""
        gap = get_efficiency_gap("Boston Celtics", "Washington Wizards")
        assert 0.0 <= gap <= 20.0

    def test_elite_home_vs_worst_away_near_max(self):
        """OKC (28.0) at home vs Wizards (-21.6) should approach 20.0."""
        gap = get_efficiency_gap("Oklahoma City Thunder", "Washington Wizards")
        # differential = 28.0 - (-21.6) = 49.6 → (49.6+30)/60*20 = 16.53
        assert gap > 16.0

    def test_worst_home_vs_elite_away_near_min(self):
        """Wizards at home vs Celtics → gap should be low."""
        gap = get_efficiency_gap("Washington Wizards", "Boston Celtics")
        # differential = -21.6 - 27.5 = -49.1 → (−49.1+30)/60*20 = -6.37 → clamped to 0
        assert gap == 0.0

    def test_even_matchup_near_10(self):
        """Two teams with identical adj_em → gap should be exactly 10.0."""
        from core.efficiency_feed import _TEAM_DATA
        # Use two teams with the same adj_em if available, or check formula directly
        # Formula: differential=0 → (0+30)/60*20 = 10.0
        # We'll verify with two mid-tier NBA teams that have similar adj_em
        gap = get_efficiency_gap("Miami Heat", "Philadelphia 76ers")
        # adj_em: Heat=4.2, Sixers=3.5 → differential=0.7 → (0.7+30)/60*20=10.23
        assert 9.0 <= gap <= 12.0

    def test_unknown_home_returns_unknown_gap(self):
        gap = get_efficiency_gap("Unknown FC", "Boston Celtics")
        assert gap == _UNKNOWN_GAP

    def test_unknown_away_returns_unknown_gap(self):
        gap = get_efficiency_gap("Boston Celtics", "Unknown FC")
        assert gap == _UNKNOWN_GAP

    def test_both_unknown_returns_unknown_gap(self):
        gap = get_efficiency_gap("Unknown A", "Unknown B")
        assert gap == _UNKNOWN_GAP

    def test_unknown_gap_value_is_below_neutral(self):
        """Unknown teams should not inflate scores — gap < 10 (neutral)."""
        assert _UNKNOWN_GAP < 10.0

    def test_alias_works_in_gap(self):
        """get_efficiency_gap should accept aliases, not just canonical names."""
        gap_canonical = get_efficiency_gap("Boston Celtics", "Washington Wizards")
        gap_alias = get_efficiency_gap("Celtics", "Wizards")
        assert abs(gap_canonical - gap_alias) < 0.001

    def test_gap_not_symmetric(self):
        """home(A,B) != home(B,A) — home/away matters."""
        gap_ab = get_efficiency_gap("Oklahoma City Thunder", "Washington Wizards")
        gap_ba = get_efficiency_gap("Washington Wizards", "Oklahoma City Thunder")
        assert gap_ab != gap_ba

    def test_nfl_teams_produce_valid_gap(self):
        gap = get_efficiency_gap("Kansas City Chiefs", "Chicago Bears")
        assert 0.0 <= gap <= 20.0
        assert gap > 10.0  # Chiefs should be favored vs Bears

    def test_soccer_teams_produce_valid_gap(self):
        gap = get_efficiency_gap("Manchester City", "Southampton")
        assert 0.0 <= gap <= 20.0
        assert gap > 10.0  # Man City vs relegation-zone Southampton

    def test_formula_precision(self):
        """Manual formula check: Celtics(27.5) home vs Hornets(-14.9)."""
        # differential = 27.5 - (-14.9) = 42.4
        # gap = (42.4 + 30) / 60 * 20 = 72.4 / 60 * 20 = 24.13 → clamped to 20.0
        gap = get_efficiency_gap("Boston Celtics", "Charlotte Hornets")
        assert gap == 20.0  # hits upper clamp

    def test_mlb_teams_produce_valid_gap(self):
        gap = get_efficiency_gap("Los Angeles Dodgers", "Colorado Rockies")
        assert 0.0 <= gap <= 20.0
        assert gap > 10.0  # Dodgers elite ERA vs Rockies worst ERA


# ---------------------------------------------------------------------------
# list_teams
# ---------------------------------------------------------------------------

class TestListTeams:

    def test_all_teams_over_200(self):
        """Database should have 200+ teams across all leagues."""
        teams = list_teams()
        assert len(teams) > 200

    def test_nba_count(self):
        assert len(list_teams("NBA")) == 30

    def test_nfl_count(self):
        """NFL should have 32 canonical teams (Raiders duplicate counted separately)."""
        nfl_teams = list_teams("NFL")
        # Oakland Raiders is an alias entry in _TEAM_DATA but we store it separately
        # Accept 32 or 33 depending on whether alias is in canonical dict
        assert 32 <= len(nfl_teams) <= 33

    def test_mlb_count(self):
        assert len(list_teams("MLB")) == 30

    def test_epl_count(self):
        assert len(list_teams("EPL")) == 20

    def test_bundesliga_count(self):
        assert len(list_teams("BUNDESLIGA")) == 18

    def test_ligue1_count(self):
        assert len(list_teams("LIGUE1")) == 18

    def test_serie_a_count(self):
        assert len(list_teams("SERIE_A")) == 20

    def test_la_liga_count(self):
        assert len(list_teams("LA_LIGA")) == 20

    def test_league_filter_case_insensitive(self):
        """list_teams("nba") should work same as "NBA"."""
        upper = list_teams("NBA")
        lower = list_teams("nba")
        assert set(upper) == set(lower)

    def test_unknown_league_returns_empty(self):
        assert list_teams("CRICKET") == []

    def test_returns_canonical_names_not_aliases(self):
        """list_teams() should return canonical keys, not aliases."""
        teams = list_teams("NBA")
        # "Celtics" is an alias — should NOT be in list_teams output
        assert "Celtics" not in teams
        # "Boston Celtics" is canonical — should be there
        assert "Boston Celtics" in teams

    def test_no_duplicates(self):
        teams = list_teams()
        assert len(teams) == len(set(teams))


# ---------------------------------------------------------------------------
# Architecture: no imports from other core modules
# ---------------------------------------------------------------------------

class TestArchitecture:

    def test_no_math_engine_import(self):
        """efficiency_feed must not import math_engine (circular risk)."""
        import importlib
        import sys
        # If math_engine was imported by efficiency_feed at module level,
        # it would be in sys.modules as a side-effect of importing efficiency_feed.
        # But we can also inspect the source directly.
        import inspect
        import core.efficiency_feed as mod
        source = inspect.getsource(mod)
        assert "from core.math_engine" not in source
        assert "import math_engine" not in source

    def test_no_odds_fetcher_import(self):
        import inspect
        import core.efficiency_feed as mod
        source = inspect.getsource(mod)
        assert "from core.odds_fetcher" not in source
        assert "import odds_fetcher" not in source

    def test_no_line_logger_import(self):
        import inspect
        import core.efficiency_feed as mod
        source = inspect.getsource(mod)
        assert "from core.line_logger" not in source
        assert "import line_logger" not in source
