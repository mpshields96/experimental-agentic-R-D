"""
tests/test_king_of_the_court.py — King of the Court analyzer tests
==================================================================
Zero network calls. All tests use static season data.
"""

import pytest
from core.king_of_the_court import (
    KotcCandidate,
    _matchup_multiplier,
    _matchup_grade,
    _compute_ceiling_floor,
    _kotc_score,
    _PLAYER_LOOKUP,
    _TEAM_ROSTER,
    format_kotc_summary,
    get_kotc_top_pick,
    is_kotc_eligible_day,
    rank_kotc_candidates,
    KOTC_MIN_PRA_THRESHOLD,
    KOTC_TOP_N,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_kotc_min_pra_threshold_is_reasonable(self):
        assert 20 <= KOTC_MIN_PRA_THRESHOLD <= 40

    def test_kotc_top_n_is_reasonable(self):
        assert 5 <= KOTC_TOP_N <= 20


# ---------------------------------------------------------------------------
# Matchup multiplier
# ---------------------------------------------------------------------------

class TestMatchupMultiplier:
    def test_terrible_defense_gives_highest_mult(self):
        # WAS has 117.2 rating → 1.18
        assert _matchup_multiplier("WAS") == 1.18

    def test_elite_defense_gives_lowest_mult(self):
        # OKC has 108.2 rating → 0.90
        assert _matchup_multiplier("OKC") == 0.90

    def test_average_defense_gives_neutral_mult(self):
        # DEN has 112.8 → 1.06
        mult = _matchup_multiplier("DEN")
        assert 1.00 <= mult <= 1.10

    def test_unknown_team_returns_default(self):
        # Unknown team → league avg default (113.5 → 1.06)
        mult = _matchup_multiplier("XYZ")
        assert mult == 1.06

    def test_all_known_teams_return_valid_mult(self):
        from core.king_of_the_court import _TEAM_DEF_RATING
        for team in _TEAM_DEF_RATING:
            mult = _matchup_multiplier(team)
            assert 0.80 <= mult <= 1.25, f"{team} multiplier {mult} out of range"


# ---------------------------------------------------------------------------
# Matchup grade
# ---------------------------------------------------------------------------

class TestMatchupGrade:
    def test_was_is_great(self):
        assert _matchup_grade("WAS") == "GREAT"

    def test_okc_is_elite(self):
        assert _matchup_grade("OKC") == "ELITE"

    def test_cle_is_elite(self):
        assert _matchup_grade("CLE") == "ELITE"

    def test_average_team_is_neutral(self):
        grade = _matchup_grade("DEN")
        assert grade in {"NEUTRAL", "GOOD", "TOUGH"}

    def test_unknown_team_is_neutral(self):
        grade = _matchup_grade("ZZZ")
        assert grade == "NEUTRAL"

    def test_good_weak_defense(self):
        # CHA 116.1 → GOOD
        assert _matchup_grade("CHA") in {"GREAT", "GOOD"}


# ---------------------------------------------------------------------------
# Ceiling/floor computation
# ---------------------------------------------------------------------------

class TestCeilingFloor:
    def test_ceiling_above_average(self):
        ceiling, floor = _compute_ceiling_floor(42.0, 1.15)
        assert ceiling > 42.0
        assert floor < 42.0

    def test_ceiling_increases_with_role_expansion(self):
        c1, _ = _compute_ceiling_floor(42.0, 1.15, role_expansion=False)
        c2, _ = _compute_ceiling_floor(42.0, 1.15, role_expansion=True)
        assert c2 > c1

    def test_neutral_ceil_mult_gives_symmetric_range(self):
        ceiling, floor = _compute_ceiling_floor(40.0, 1.0)
        # With mult=1.0: ceiling = 40*1.0 = 40, floor = 40*(2-1) = 40
        # Symmetric around avg
        assert ceiling == floor == 40.0

    def test_values_are_rounded(self):
        ceiling, floor = _compute_ceiling_floor(42.3, 1.15)
        # Should be rounded to 1 decimal
        assert ceiling == round(ceiling, 1)
        assert floor == round(floor, 1)


# ---------------------------------------------------------------------------
# KOTC score
# ---------------------------------------------------------------------------

class TestKotcScore:
    def test_out_player_scores_zero(self):
        score = _kotc_score(48.0, 60.0, True, "GREAT", is_out=True)
        assert score == 0.0

    def test_higher_pra_gives_higher_score(self):
        score_high = _kotc_score(50.0, 62.0, True, "NEUTRAL", is_out=False)
        score_low = _kotc_score(35.0, 45.0, False, "NEUTRAL", is_out=False)
        assert score_high > score_low

    def test_triple_double_threat_boosts_score(self):
        score_td = _kotc_score(45.0, 55.0, True, "NEUTRAL", is_out=False)
        score_no_td = _kotc_score(45.0, 55.0, False, "NEUTRAL", is_out=False)
        assert score_td > score_no_td

    def test_great_matchup_boosts_score(self):
        score_great = _kotc_score(45.0, 55.0, False, "GREAT", is_out=False)
        score_elite = _kotc_score(45.0, 55.0, False, "ELITE", is_out=False)
        assert score_great > score_elite

    def test_score_clamped_to_100(self):
        # Even extreme values shouldn't exceed 100
        score = _kotc_score(100.0, 150.0, True, "GREAT", is_out=False)
        assert score <= 100.0

    def test_score_clamped_to_zero(self):
        score = _kotc_score(0.0, 0.0, False, "ELITE", is_out=False)
        assert score >= 0.0

    def test_typical_elite_player_scores_high(self):
        # Jokic-level stats: 50 PRA, 62 ceiling, TD threat, neutral matchup
        score = _kotc_score(50.0, 62.0, True, "NEUTRAL", is_out=False)
        assert score >= 75.0

    def test_typical_average_player_scores_mid(self):
        # Average all-star: 36 PRA, 43 ceiling, no TD
        score = _kotc_score(36.0, 43.0, False, "NEUTRAL", is_out=False)
        assert 30.0 <= score <= 70.0


# ---------------------------------------------------------------------------
# Player lookup table
# ---------------------------------------------------------------------------

class TestPlayerLookup:
    def test_luka_in_lookup(self):
        assert "luka doncic" in _PLAYER_LOOKUP

    def test_jokic_in_lookup(self):
        assert "nikola jokic" in _PLAYER_LOOKUP

    def test_jalen_johnson_in_lookup(self):
        assert "jalen johnson" in _PLAYER_LOOKUP

    def test_luka_on_lal(self):
        p = _PLAYER_LOOKUP["luka doncic"]
        assert p.team == "LAL"

    def test_jalen_johnson_on_atl(self):
        p = _PLAYER_LOOKUP["jalen johnson"]
        assert p.team == "ATL"

    def test_kevin_porter_jr_on_mil(self):
        p = _PLAYER_LOOKUP["kevin porter jr."]
        assert p.team == "MIL"

    def test_jokic_pra_is_high(self):
        p = _PLAYER_LOOKUP["nikola jokic"]
        pra = p.pts + p.reb + p.ast
        assert pra >= 45.0

    def test_maxey_embiid_out_virtual_profile_exists(self):
        assert "tyrese maxey-embiid-out" in _PLAYER_LOOKUP

    def test_all_profiles_have_positive_stats(self):
        from core.king_of_the_court import _PLAYER_SEASONS
        for p in _PLAYER_SEASONS:
            assert p.pts >= 0
            assert p.reb >= 0
            assert p.ast >= 0
            assert p.min_pg >= 0

    def test_all_profiles_have_valid_team(self):
        from core.king_of_the_court import _PLAYER_SEASONS, _TEAM_DEF_RATING
        known_teams = set(_TEAM_DEF_RATING.keys())
        for p in _PLAYER_SEASONS:
            # Virtual profiles (with '-') are exempt
            if "-" not in p.name:
                assert p.team in known_teams, f"{p.name} has unknown team {p.team}"


# ---------------------------------------------------------------------------
# Team roster lookup
# ---------------------------------------------------------------------------

class TestTeamRoster:
    def test_lal_has_luka(self):
        lal_players = [p.name for p in _TEAM_ROSTER.get("LAL", [])]
        assert "Luka Doncic" in lal_players

    def test_atl_has_jalen_johnson(self):
        atl_players = [p.name for p in _TEAM_ROSTER.get("ATL", [])]
        assert "Jalen Johnson" in atl_players

    def test_phi_has_embiid(self):
        phi_players = [p.name for p in _TEAM_ROSTER.get("PHI", [])]
        assert "Joel Embiid" in phi_players


# ---------------------------------------------------------------------------
# rank_kotc_candidates — core integration tests
# ---------------------------------------------------------------------------

class TestRankKotcCandidates:

    # Feb 24, 2026 slate
    _FEB24_TEAMS = [
        "PHI", "IND",    # 76ers vs Pacers
        "LAL", "ORL",    # Lakers vs Magic
        "ATL", "WAS",    # Hawks vs Wizards
        "MIL", "MIA",    # Bucks vs Heat
        "NYK", "CLE",    # Knicks vs Cavaliers
        "MIN", "POR",    # Timberwolves vs Trail Blazers
        "BOS", "PHX",    # Celtics vs Suns
        "OKC", "TOR",    # Thunder vs Raptors
        "DAL", "BKN",    # Mavericks vs Nets
        "GSW", "NOP",    # Warriors vs Pelicans
        "CHA", "CHI",    # Hornets vs Bulls
    ]

    def test_returns_list_of_candidates(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_results_sorted_by_score_descending(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        scores = [c.kotc_score for c in result]
        assert scores == sorted(scores, reverse=True)

    def test_max_n_candidates_returned(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        assert len(result) <= KOTC_TOP_N

    def test_out_players_excluded(self):
        result = rank_kotc_candidates(
            self._FEB24_TEAMS,
            injury_outs={"Jaylen Brown", "Joel Embiid"}
        )
        names = [c.player_name for c in result]
        assert "Jaylen Brown" not in names
        # Embiid is also out but Maxey virtual profile should appear
        assert "Joel Embiid" not in names

    def test_embiid_out_activates_maxey_virtual_profile(self):
        result = rank_kotc_candidates(
            self._FEB24_TEAMS,
            injury_outs={"Joel Embiid"}
        )
        maxey_entries = [c for c in result if c.player_name == "Tyrese Maxey"]
        assert len(maxey_entries) == 1
        maxey = maxey_entries[0]
        assert maxey.role_expansion is True
        # Expanded Maxey should have higher PRA than base Maxey
        assert maxey.pra_avg > 40.0  # virtual profile has 34+4.5+9.2 = 47.7

    def test_embiid_playing_uses_base_maxey(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        maxey_entries = [c for c in result if c.player_name == "Tyrese Maxey"]
        # At most one Maxey entry when Embiid plays
        assert len(maxey_entries) <= 1
        if maxey_entries:
            assert maxey_entries[0].role_expansion is False

    def test_players_not_playing_tonight_excluded(self):
        # Only give one game
        result = rank_kotc_candidates(["LAL", "ORL"])
        teams_in_results = {c.team for c in result}
        # Only LAL and ORL players should appear
        assert teams_in_results.issubset({"LAL", "ORL"})

    def test_opponent_map_is_respected(self):
        opp_map = {"LAL": "ORL", "ORL": "LAL"}
        result = rank_kotc_candidates(
            ["LAL", "ORL"],
            opponent_map=opp_map
        )
        lal_players = [c for c in result if c.team == "LAL"]
        if lal_players:
            assert lal_players[0].opponent == "ORL"

    def test_was_matchup_boosts_atl_scores(self):
        # ATL vs WAS — WAS is GREAT matchup
        result_with_was = rank_kotc_candidates(
            ["ATL", "WAS"],
            opponent_map={"ATL": "WAS", "WAS": "ATL"}
        )
        result_vs_okc = rank_kotc_candidates(
            ["ATL", "OKC"],
            opponent_map={"ATL": "OKC", "OKC": "ATL"}
        )
        # ATL players should score higher vs WAS (terrible defense) than vs OKC (elite)
        atl_was_scores = [c.kotc_score for c in result_with_was if c.team == "ATL"]
        atl_okc_scores = [c.kotc_score for c in result_vs_okc if c.team == "ATL"]
        if atl_was_scores and atl_okc_scores:
            assert max(atl_was_scores) > max(atl_okc_scores)

    def test_triple_double_threat_flag_set_correctly(self):
        result = rank_kotc_candidates(["DEN", "ORL"])
        jokic = next((c for c in result if c.player_name == "Nikola Jokic"), None)
        if jokic:
            # Jokic: 12.8 reb + 10.2 ast → both >= 10 and 7
            assert jokic.triple_double_threat is True

    def test_jalen_johnson_triple_double_threat(self):
        result = rank_kotc_candidates(["ATL", "WAS"])
        jj = next((c for c in result if c.player_name == "Jalen Johnson"), None)
        assert jj is not None
        # 10.8 reb → TD threat
        assert jj.triple_double_threat is True

    def test_empty_teams_returns_empty(self):
        result = rank_kotc_candidates([])
        assert result == []

    def test_single_team_still_works(self):
        # Edge case: odd number of teams (no opponent matchup)
        result = rank_kotc_candidates(["LAL"])
        lal_players = [c for c in result if c.team == "LAL"]
        assert len(lal_players) > 0

    def test_star_out_triggers_role_expansion(self):
        # Tatum out → teammates get expansion boost
        result_tatum_out = rank_kotc_candidates(
            ["BOS", "PHX"],
            star_outs={"Jayson Tatum": "BOS"},
        )
        result_normal = rank_kotc_candidates(["BOS", "PHX"])

        bos_out = [c for c in result_tatum_out if c.team == "BOS"]
        bos_normal = [c for c in result_normal if c.team == "BOS"]

        if bos_out and bos_normal:
            # At least one BOS player should have higher score with Tatum out
            max_out = max(c.kotc_score for c in bos_out)
            max_normal = max(c.kotc_score for c in bos_normal)
            assert max_out >= max_normal

    def test_luka_is_top_3_on_full_feb24_slate(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        top3 = [c.player_name for c in result[:3]]
        assert "Luka Doncic" in top3, f"Luka not in top 3: {top3}"

    def test_jalen_johnson_appears_in_top_candidates(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        names = [c.player_name for c in result]
        assert "Jalen Johnson" in names

    def test_all_candidates_have_valid_score(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        for c in result:
            assert 0.0 <= c.kotc_score <= 100.0
            assert c.pra_projection >= KOTC_MIN_PRA_THRESHOLD

    def test_all_candidates_have_required_fields(self):
        result = rank_kotc_candidates(self._FEB24_TEAMS)
        for c in result:
            assert c.player_name
            assert c.team
            assert c.kotc_score >= 0


# ---------------------------------------------------------------------------
# get_kotc_top_pick
# ---------------------------------------------------------------------------

class TestGetKotcTopPick:
    def test_returns_candidate_when_games_exist(self):
        pick = get_kotc_top_pick(["LAL", "ORL"])
        assert pick is not None
        assert isinstance(pick, KotcCandidate)

    def test_returns_none_on_empty_slate(self):
        pick = get_kotc_top_pick([])
        assert pick is None

    def test_top_pick_has_highest_score(self):
        all_candidates = rank_kotc_candidates(["LAL", "ORL", "ATL", "WAS"])
        top_pick = get_kotc_top_pick(["LAL", "ORL", "ATL", "WAS"])
        if all_candidates and top_pick:
            assert top_pick.kotc_score == all_candidates[0].kotc_score

    def test_out_player_not_top_pick(self):
        pick = get_kotc_top_pick(
            ["LAL", "ORL"],
            injury_outs={"Luka Doncic"}
        )
        if pick:
            assert pick.player_name != "Luka Doncic"


# ---------------------------------------------------------------------------
# format_kotc_summary
# ---------------------------------------------------------------------------

class TestFormatKotcSummary:
    def _make_candidate(self, **kwargs):
        defaults = dict(
            player_name="Luka Doncic",
            team="LAL",
            position="G",
            pts_avg=30.1,
            reb_avg=8.2,
            ast_avg=9.1,
            pra_avg=47.4,
            pra_projection=48.1,
            pra_ceiling=58.0,
            pra_floor=37.0,
            opponent="ORL",
            matchup_grade="NEUTRAL",
            triple_double_threat=True,
            kotc_score=86.5,
            reasoning="test",
            is_out=False,
            role_expansion=False,
        )
        defaults.update(kwargs)
        return KotcCandidate(**defaults)

    def test_contains_player_name(self):
        c = self._make_candidate()
        assert "Luka Doncic" in format_kotc_summary(c)

    def test_contains_team(self):
        c = self._make_candidate()
        assert "LAL" in format_kotc_summary(c)

    def test_contains_kotc_score(self):
        c = self._make_candidate(kotc_score=86.5)
        summary = format_kotc_summary(c)
        assert "87" in summary or "86" in summary  # rounded

    def test_contains_projected_pra(self):
        c = self._make_candidate(pra_projection=48.1)
        assert "48.1" in format_kotc_summary(c)

    def test_contains_opponent(self):
        c = self._make_candidate(opponent="ORL")
        assert "ORL" in format_kotc_summary(c)

    def test_td_star_shown(self):
        c = self._make_candidate(triple_double_threat=True)
        assert "TD" in format_kotc_summary(c)

    def test_no_td_star_when_not_threat(self):
        c = self._make_candidate(triple_double_threat=False)
        assert "★TD" not in format_kotc_summary(c)

    def test_expand_badge_shown(self):
        c = self._make_candidate(role_expansion=True)
        assert "EXPAND" in format_kotc_summary(c)


# ---------------------------------------------------------------------------
# is_kotc_eligible_day
# ---------------------------------------------------------------------------

class TestIsKotcEligibleDay:
    def test_tuesday_is_eligible(self):
        assert is_kotc_eligible_day(weekday=1) is True

    def test_monday_is_not_eligible(self):
        assert is_kotc_eligible_day(weekday=0) is False

    def test_wednesday_is_not_eligible(self):
        assert is_kotc_eligible_day(weekday=2) is False

    def test_sunday_is_not_eligible(self):
        assert is_kotc_eligible_day(weekday=6) is False

    def test_all_non_tuesdays_ineligible(self):
        for wd in [0, 2, 3, 4, 5, 6]:
            assert is_kotc_eligible_day(weekday=wd) is False

    def test_system_date_returns_bool(self):
        # Just ensure it doesn't crash
        result = is_kotc_eligible_day()
        assert isinstance(result, bool)
