"""
tests/test_nba_pdo.py — NBA PDO regression signal tests

All nba_api calls are injected via _endpoint_factory — no network, no patch needed.
Mock factory lambda: lambda **kwargs: MockEndpoint(df)
"""

import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pytest

import core.nba_pdo as pb
from core.nba_pdo import (
    PdoResult,
    PDO_BASELINE,
    PDO_REGRESS_THRESHOLD,
    PDO_RECOVER_THRESHOLD,
    PDO_MIN_GAMES,
    compute_pdo,
    classify_pdo,
    normalize_nba_team_name,
    _merge_shooting_data,
    _fetch_league_shooting,
    get_all_pdo_data,
    get_team_pdo,
    pdo_kill_switch,
    clear_pdo_cache,
    pdo_cache_size,
)


# ---------------------------------------------------------------------------
# Mock endpoint helpers
# ---------------------------------------------------------------------------

class MockEndpoint:
    """Minimal nba_api endpoint mock — returns a fixed dataframe."""

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_data_frames(self) -> list:
        return [self._df]


def make_base_df(rows: list[dict]) -> pd.DataFrame:
    """Build a LeagueDashTeamStats 'Base' measure dataframe."""
    default = {"TEAM_NAME": "Test Team", "GP": 40, "FG_PCT": 0.470}
    data = [{**default, **r} for r in rows]
    return pd.DataFrame(data)


def make_opponent_df(rows: list[dict]) -> pd.DataFrame:
    """Build a LeagueDashTeamStats 'Opponent' measure dataframe."""
    default = {"TEAM_NAME": "Test Team", "GP": 40, "OPP_FG_PCT": 0.450}
    data = [{**default, **r} for r in rows]
    return pd.DataFrame(data)


def make_factory(measure_type_to_df: dict):
    """
    Build a factory callable that returns different MockEndpoint per measure_type.
    Usage: factory = make_factory({"Base": base_df, "Opponent": opp_df})
    """
    def factory(**kwargs):
        mt = kwargs.get("measure_type_detailed_defense", "Base")
        df = measure_type_to_df.get(mt, pd.DataFrame())
        return MockEndpoint(df)
    return factory


# ---------------------------------------------------------------------------
# TestComputePdo
# ---------------------------------------------------------------------------

class TestComputePdo:

    def test_baseline_inputs(self):
        # When team shoots 50% and opponent shoots 50%, PDO = 100.0 exactly
        assert compute_pdo(0.500, 0.500) == 100.0

    def test_regress_boundary(self):
        # PDO exactly at regress threshold
        # (0.5 + (1.0 - 0.48)) * 100 = (0.5 + 0.52) * 100 = 102.0
        result = compute_pdo(0.500, 0.480)
        assert result == pytest.approx(102.0, abs=0.01)

    def test_above_baseline(self):
        # Good shooting, good defense → PDO > 100
        result = compute_pdo(0.490, 0.460)
        expected = (0.490 + 0.540) * 100.0
        assert result == pytest.approx(expected, abs=0.001)

    def test_recover_boundary(self):
        # PDO exactly at recover threshold
        # (0.48 + (1.0 - 0.50)) * 100 = (0.48 + 0.50) * 100 = 98.0
        result = compute_pdo(0.480, 0.500)
        assert result == pytest.approx(98.0, abs=0.01)

    def test_below_baseline(self):
        # Poor shooting, poor defense → PDO < 100
        result = compute_pdo(0.450, 0.490)
        expected = (0.450 + 0.510) * 100.0
        assert result == pytest.approx(expected, abs=0.001)

    def test_perfect_fg_zero_opp(self):
        # Extreme edge: 100% shooting, 0% opp FG → PDO = 200.0
        assert compute_pdo(1.0, 0.0) == pytest.approx(200.0, abs=0.001)

    def test_symmetric_inputs(self):
        # Symmetric around 50% should all give PDO = 100.0
        assert compute_pdo(0.470, 0.470) == pytest.approx(100.0, abs=0.001)
        assert compute_pdo(0.450, 0.450) == pytest.approx(100.0, abs=0.001)

    def test_float_precision(self):
        # Should not produce floating point noise outside 4 decimal places
        result = compute_pdo(0.473, 0.461)
        assert isinstance(result, float)
        # No more than 4 decimal places (rounded)
        assert result == round(result, 4)


# ---------------------------------------------------------------------------
# TestClassifyPdo
# ---------------------------------------------------------------------------

class TestClassifyPdo:

    def test_exactly_at_regress(self):
        assert classify_pdo(102.0) == "REGRESS"

    def test_above_regress(self):
        assert classify_pdo(104.5) == "REGRESS"

    def test_exactly_at_recover(self):
        assert classify_pdo(98.0) == "RECOVER"

    def test_below_recover(self):
        assert classify_pdo(95.3) == "RECOVER"

    def test_at_baseline_is_neutral(self):
        assert classify_pdo(100.0) == "NEUTRAL"

    def test_just_below_regress_is_neutral(self):
        assert classify_pdo(101.9) == "NEUTRAL"

    def test_just_above_recover_is_neutral(self):
        assert classify_pdo(98.1) == "NEUTRAL"


# ---------------------------------------------------------------------------
# TestNormalizeNbaTeamName
# ---------------------------------------------------------------------------

class TestNormalizeNbaTeamName:

    def test_la_clippers_maps_correctly(self):
        assert normalize_nba_team_name("LA Clippers") == "Los Angeles Clippers"

    def test_la_lakers_maps_correctly(self):
        assert normalize_nba_team_name("LA Lakers") == "Los Angeles Lakers"

    def test_canonical_pass_through(self):
        assert normalize_nba_team_name("Los Angeles Clippers") == "Los Angeles Clippers"
        assert normalize_nba_team_name("Oklahoma City Thunder") == "Oklahoma City Thunder"
        assert normalize_nba_team_name("Golden State Warriors") == "Golden State Warriors"

    def test_case_insensitive(self):
        assert normalize_nba_team_name("la clippers") == "Los Angeles Clippers"
        assert normalize_nba_team_name("BOSTON CELTICS") == "Boston Celtics"

    def test_strips_whitespace(self):
        assert normalize_nba_team_name("  Los Angeles Lakers  ") == "Los Angeles Lakers"

    def test_unknown_team_returns_none(self):
        assert normalize_nba_team_name("Las Vegas Aces") is None

    def test_empty_string_returns_none(self):
        assert normalize_nba_team_name("") is None

    def test_all_30_canonical_names_round_trip(self):
        canonical_names = [
            "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets",
            "Chicago Bulls", "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets",
            "Detroit Pistons", "Golden State Warriors", "Houston Rockets", "Indiana Pacers",
            "Los Angeles Clippers", "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat",
            "Milwaukee Bucks", "Minnesota Timberwolves", "New Orleans Pelicans",
            "New York Knicks", "Oklahoma City Thunder", "Orlando Magic",
            "Philadelphia 76ers", "Phoenix Suns", "Portland Trail Blazers",
            "Sacramento Kings", "San Antonio Spurs", "Toronto Raptors",
            "Utah Jazz", "Washington Wizards",
        ]
        for name in canonical_names:
            result = normalize_nba_team_name(name)
            assert result == name, f"Round-trip failed for: {name!r} → {result!r}"

    def test_last_word_partial_match(self):
        # "Clippers" alone should resolve
        assert normalize_nba_team_name("Clippers") == "Los Angeles Clippers"

    def test_none_input(self):
        # None-like empty string
        assert normalize_nba_team_name("") is None


# ---------------------------------------------------------------------------
# TestMergeShootingData
# ---------------------------------------------------------------------------

class TestMergeShootingData:

    def test_inner_join_drops_missing(self):
        base = {"Team A": {"fg_pct": 0.47, "games_played": 40}}
        opp = {"Team B": {"fg_pct": 0.46, "games_played": 40}}
        result = _merge_shooting_data(base, opp)
        assert result == {}

    def test_matching_teams_merged(self):
        base = {"Lakers": {"fg_pct": 0.48, "games_played": 42}}
        opp = {"Lakers": {"fg_pct": 0.47, "games_played": 42}}
        result = _merge_shooting_data(base, opp)
        assert "Lakers" in result
        assert result["Lakers"]["fg_pct"] == 0.48
        assert result["Lakers"]["opp_fg_pct"] == 0.47
        assert result["Lakers"]["games_played"] == 42

    def test_empty_base_returns_empty(self):
        assert _merge_shooting_data({}, {"Team A": {"fg_pct": 0.47, "games_played": 40}}) == {}

    def test_empty_opponent_returns_empty(self):
        assert _merge_shooting_data({"Team A": {"fg_pct": 0.47, "games_played": 40}}, {}) == {}

    def test_partial_overlap(self):
        base = {
            "Team A": {"fg_pct": 0.47, "games_played": 40},
            "Team B": {"fg_pct": 0.48, "games_played": 40},
        }
        opp = {
            "Team A": {"fg_pct": 0.46, "games_played": 40},
            # Team B absent from opponent
        }
        result = _merge_shooting_data(base, opp)
        assert "Team A" in result
        assert "Team B" not in result

    def test_gp_carried_from_base(self):
        base = {"X": {"fg_pct": 0.47, "games_played": 55}}
        opp = {"X": {"fg_pct": 0.45, "games_played": 55}}
        assert _merge_shooting_data(base, opp)["X"]["games_played"] == 55


# ---------------------------------------------------------------------------
# TestFetchLeagueShooting
# ---------------------------------------------------------------------------

class TestFetchLeagueShooting:

    def _make_factory(self, df: pd.DataFrame):
        return lambda **kwargs: MockEndpoint(df)

    def test_base_measure_returns_team_data(self):
        df = make_base_df([
            {"TEAM_NAME": "Boston Celtics", "GP": 45, "FG_PCT": 0.492},
        ])
        result = _fetch_league_shooting("Base", _endpoint_factory=self._make_factory(df))
        assert result is not None
        assert "Boston Celtics" in result
        assert result["Boston Celtics"]["fg_pct"] == pytest.approx(0.492)
        assert result["Boston Celtics"]["games_played"] == 45

    def test_opponent_measure_returns_team_data(self):
        df = make_opponent_df([
            {"TEAM_NAME": "Boston Celtics", "GP": 45, "OPP_FG_PCT": 0.443},
        ])
        result = _fetch_league_shooting("Opponent", _endpoint_factory=self._make_factory(df))
        assert result is not None
        assert result["Boston Celtics"]["fg_pct"] == pytest.approx(0.443)

    def test_empty_dataframe_returns_none(self):
        df = pd.DataFrame(columns=["TEAM_NAME", "GP", "FG_PCT"])
        result = _fetch_league_shooting("Base", _endpoint_factory=self._make_factory(df))
        assert result is None

    def test_factory_raises_exception_returns_none(self):
        def bad_factory(**kwargs):
            raise ConnectionError("timeout")
        result = _fetch_league_shooting("Base", _endpoint_factory=bad_factory)
        assert result is None

    def test_missing_fg_pct_column_returns_none(self):
        df = pd.DataFrame([{"TEAM_NAME": "Team A", "GP": 40}])
        result = _fetch_league_shooting("Base", _endpoint_factory=self._make_factory(df))
        assert result is None

    def test_missing_gp_column_returns_none(self):
        df = pd.DataFrame([{"TEAM_NAME": "Team A", "FG_PCT": 0.47}])
        result = _fetch_league_shooting("Base", _endpoint_factory=self._make_factory(df))
        assert result is None

    def test_multiple_teams_returned(self):
        df = make_base_df([
            {"TEAM_NAME": "Boston Celtics", "GP": 45, "FG_PCT": 0.492},
            {"TEAM_NAME": "Golden State Warriors", "GP": 44, "FG_PCT": 0.471},
        ])
        result = _fetch_league_shooting("Base", _endpoint_factory=self._make_factory(df))
        assert result is not None
        assert len(result) == 2

    def test_season_string_used(self):
        """Confirm season kwarg is passed to factory."""
        received_kwargs = {}
        def recording_factory(**kwargs):
            received_kwargs.update(kwargs)
            return MockEndpoint(make_base_df([]))
        _fetch_league_shooting("Base", _endpoint_factory=recording_factory)
        assert received_kwargs.get("season") == pb._CURRENT_SEASON

    def test_measure_type_passed_to_factory(self):
        received = {}
        def recording_factory(**kwargs):
            received.update(kwargs)
            return MockEndpoint(make_opponent_df([]))
        _fetch_league_shooting("Opponent", _endpoint_factory=recording_factory)
        assert received.get("measure_type_detailed_defense") == "Opponent"

    def test_no_frames_returned_gives_none(self):
        class EmptyFrameEndpoint:
            def get_data_frames(self):
                return []
        result = _fetch_league_shooting("Base", _endpoint_factory=lambda **kw: EmptyFrameEndpoint())
        assert result is None


# ---------------------------------------------------------------------------
# TestGetAllPdoData
# ---------------------------------------------------------------------------

class TestGetAllPdoData:

    def setup_method(self):
        clear_pdo_cache()

    def _make_full_factory(self, fg_pct=0.473, opp_fg_pct=0.461, gp=40):
        """Factory producing 30-team data for both measure types."""
        teams = [
            "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets",
            "Chicago Bulls", "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets",
            "Detroit Pistons", "Golden State Warriors", "Houston Rockets", "Indiana Pacers",
            "Los Angeles Clippers", "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat",
            "Milwaukee Bucks", "Minnesota Timberwolves", "New Orleans Pelicans",
            "New York Knicks", "Oklahoma City Thunder", "Orlando Magic",
            "Philadelphia 76ers", "Phoenix Suns", "Portland Trail Blazers",
            "Sacramento Kings", "San Antonio Spurs", "Toronto Raptors",
            "Utah Jazz", "Washington Wizards",
        ]
        base_rows = [{"TEAM_NAME": t, "GP": gp, "FG_PCT": fg_pct} for t in teams]
        opp_rows = [{"TEAM_NAME": t, "GP": gp, "OPP_FG_PCT": opp_fg_pct} for t in teams]
        base_df = pd.DataFrame(base_rows)
        opp_df = pd.DataFrame(opp_rows)

        def factory(**kwargs):
            mt = kwargs.get("measure_type_detailed_defense", "Base")
            if mt == "Base":
                return MockEndpoint(base_df)
            return MockEndpoint(opp_df)
        return factory

    def test_returns_30_teams_on_good_data(self):
        result = get_all_pdo_data(_endpoint_factory=self._make_full_factory())
        assert len(result) == 30

    def test_returns_empty_dict_on_base_error(self):
        def bad_factory(**kwargs):
            raise RuntimeError("no network")
        result = get_all_pdo_data(_endpoint_factory=bad_factory)
        assert result == {}

    def test_team_names_normalized(self):
        """LA Clippers from nba_api → Los Angeles Clippers in result."""
        # Force nba_api-style names in the dataframe
        base_df = pd.DataFrame([
            {"TEAM_NAME": "LA Clippers", "GP": 40, "FG_PCT": 0.473},
        ])
        opp_df = pd.DataFrame([
            {"TEAM_NAME": "LA Clippers", "GP": 40, "OPP_FG_PCT": 0.461},
        ])
        def factory(**kwargs):
            mt = kwargs.get("measure_type_detailed_defense", "Base")
            return MockEndpoint(base_df if mt == "Base" else opp_df)
        result = get_all_pdo_data(_endpoint_factory=factory)
        assert "Los Angeles Clippers" in result
        assert "LA Clippers" not in result

    def test_pdo_values_in_valid_range(self):
        result = get_all_pdo_data(_endpoint_factory=self._make_full_factory())
        for team, r in result.items():
            assert 90.0 <= r.pdo <= 115.0, f"{team} PDO {r.pdo} out of expected range"

    def test_teams_below_min_games_excluded(self):
        # gp=5 < PDO_MIN_GAMES=10 → all excluded
        result = get_all_pdo_data(_endpoint_factory=self._make_full_factory(gp=5))
        assert result == {}

    def test_cache_populated(self):
        get_all_pdo_data(_endpoint_factory=self._make_full_factory())
        assert pdo_cache_size() == 30


# ---------------------------------------------------------------------------
# TestGetTeamPdo
# ---------------------------------------------------------------------------

class TestGetTeamPdo:

    def setup_method(self):
        clear_pdo_cache()

    def _seed_cache(self, team_name="Boston Celtics", pdo=103.5, signal="REGRESS", gp=45):
        r = PdoResult(
            team_name=team_name,
            shoot_pct=0.492,
            opp_save_pct=0.543,
            pdo=pdo,
            signal=signal,
            games_played=gp,
            fetched_at=time.time(),
        )
        pb._pdo_cache[team_name] = r
        return r

    def test_cache_hit_returns_cached(self):
        seeded = self._seed_cache()
        call_count = {"n": 0}
        def factory(**kwargs):
            call_count["n"] += 1
            return MockEndpoint(pd.DataFrame())
        result = get_team_pdo("Boston Celtics", _endpoint_factory=factory)
        assert result is seeded
        assert call_count["n"] == 0  # no fetch needed

    def test_cache_miss_triggers_fetch(self):
        base_df = pd.DataFrame([
            {"TEAM_NAME": "Oklahoma City Thunder", "GP": 50, "FG_PCT": 0.500}
        ])
        opp_df = pd.DataFrame([
            {"TEAM_NAME": "Oklahoma City Thunder", "GP": 50, "OPP_FG_PCT": 0.440}
        ])
        def factory(**kwargs):
            mt = kwargs.get("measure_type_detailed_defense", "Base")
            return MockEndpoint(base_df if mt == "Base" else opp_df)
        result = get_team_pdo("Oklahoma City Thunder", _endpoint_factory=factory)
        assert result is not None
        assert result.team_name == "Oklahoma City Thunder"

    def test_expired_ttl_triggers_refetch(self):
        # Seed with old fetched_at
        r = PdoResult(
            team_name="Boston Celtics",
            shoot_pct=0.492, opp_save_pct=0.543, pdo=103.5,
            signal="REGRESS", games_played=45,
            fetched_at=time.time() - 7200,  # 2 hours ago — expired
        )
        pb._pdo_cache["Boston Celtics"] = r
        call_count = {"n": 0}
        base_df = pd.DataFrame([{"TEAM_NAME": "Boston Celtics", "GP": 46, "FG_PCT": 0.495}])
        opp_df = pd.DataFrame([{"TEAM_NAME": "Boston Celtics", "GP": 46, "OPP_FG_PCT": 0.442}])
        def factory(**kwargs):
            call_count["n"] += 1
            mt = kwargs.get("measure_type_detailed_defense", "Base")
            return MockEndpoint(base_df if mt == "Base" else opp_df)
        result = get_team_pdo("Boston Celtics", _endpoint_factory=factory)
        assert call_count["n"] >= 2  # both Base and Opponent calls

    def test_unknown_team_returns_none(self):
        result = get_team_pdo(
            "Las Vegas Aces",
            _endpoint_factory=lambda **kw: MockEndpoint(pd.DataFrame())
        )
        assert result is None

    def test_result_has_all_fields(self):
        base_df = pd.DataFrame([{"TEAM_NAME": "Miami Heat", "GP": 40, "FG_PCT": 0.471}])
        opp_df = pd.DataFrame([{"TEAM_NAME": "Miami Heat", "GP": 40, "OPP_FG_PCT": 0.462}])
        def factory(**kwargs):
            mt = kwargs.get("measure_type_detailed_defense", "Base")
            return MockEndpoint(base_df if mt == "Base" else opp_df)
        result = get_team_pdo("Miami Heat", _endpoint_factory=factory)
        assert result is not None
        assert result.team_name == "Miami Heat"
        assert 0.0 < result.shoot_pct < 1.0
        assert 0.0 < result.opp_save_pct < 1.0
        assert 90.0 < result.pdo < 115.0
        assert result.signal in ("REGRESS", "RECOVER", "NEUTRAL")
        assert result.games_played >= PDO_MIN_GAMES
        assert result.fetched_at > 0


# ---------------------------------------------------------------------------
# TestPdoKillSwitch
# ---------------------------------------------------------------------------

class TestPdoKillSwitch:

    def setup_method(self):
        clear_pdo_cache()

    def _seed(self, team_name: str, pdo: float, signal: str):
        r = PdoResult(
            team_name=team_name,
            shoot_pct=0.49, opp_save_pct=0.54,
            pdo=pdo, signal=signal,
            games_played=45, fetched_at=time.time(),
        )
        pb._pdo_cache[team_name] = r
        return r

    def test_regress_with_is_kill(self):
        self._seed("Boston Celtics", 103.5, "REGRESS")
        killed, reason = pdo_kill_switch("Boston Celtics", "with", "spreads")
        assert killed is True
        assert reason.startswith("KILL:")

    def test_regress_against_is_flag_not_kill(self):
        self._seed("Boston Celtics", 103.5, "REGRESS")
        killed, reason = pdo_kill_switch("Boston Celtics", "against", "spreads")
        assert killed is False
        assert reason.startswith("FLAG:")

    def test_recover_with_is_flag_not_kill(self):
        self._seed("Utah Jazz", 96.5, "RECOVER")
        killed, reason = pdo_kill_switch("Utah Jazz", "with", "h2h")
        assert killed is False
        assert reason.startswith("FLAG:")

    def test_recover_against_is_kill(self):
        self._seed("Utah Jazz", 96.5, "RECOVER")
        killed, reason = pdo_kill_switch("Utah Jazz", "against", "h2h")
        assert killed is True
        assert reason.startswith("KILL:")

    def test_neutral_returns_no_action(self):
        self._seed("Denver Nuggets", 100.5, "NEUTRAL")
        killed, reason = pdo_kill_switch("Denver Nuggets", "with", "spreads")
        assert killed is False
        assert reason == ""

    def test_totals_market_always_no_action(self):
        self._seed("Boston Celtics", 104.0, "REGRESS")
        killed, reason = pdo_kill_switch("Boston Celtics", "with", "totals")
        assert killed is False
        assert reason == ""

    def test_no_cache_returns_no_action(self):
        # Team not in cache, no fetch triggered by kill switch
        killed, reason = pdo_kill_switch("Los Angeles Lakers", "with", "spreads")
        assert killed is False
        assert reason == ""

    def test_kill_reason_contains_team_name(self):
        self._seed("Memphis Grizzlies", 103.0, "REGRESS")
        _, reason = pdo_kill_switch("Memphis Grizzlies", "with", "spreads")
        assert "Memphis Grizzlies" in reason

    def test_kill_reason_contains_pdo_value(self):
        self._seed("Memphis Grizzlies", 103.0, "REGRESS")
        _, reason = pdo_kill_switch("Memphis Grizzlies", "with", "spreads")
        assert "103.0" in reason

    def test_bet_direction_case_insensitive(self):
        self._seed("Houston Rockets", 103.5, "REGRESS")
        killed_lower, _ = pdo_kill_switch("Houston Rockets", "with", "spreads")
        clear_pdo_cache()
        self._seed("Houston Rockets", 103.5, "REGRESS")
        killed_upper, _ = pdo_kill_switch("Houston Rockets", "WITH", "spreads")
        assert killed_lower == killed_upper

    def test_normalization_fallback_in_kill_switch(self):
        # Seed with canonical name, query with nba_api variant
        self._seed("Los Angeles Clippers", 102.5, "REGRESS")
        killed, reason = pdo_kill_switch("LA Clippers", "with", "spreads")
        assert killed is True

    def test_flag_reason_starts_with_flag(self):
        self._seed("Golden State Warriors", 97.0, "RECOVER")
        _, reason = pdo_kill_switch("Golden State Warriors", "with", "spreads")
        assert reason.startswith("FLAG:")


# ---------------------------------------------------------------------------
# TestClearCache
# ---------------------------------------------------------------------------

class TestClearCache:

    def test_clear_empties_cache(self):
        pb._pdo_cache["Test Team"] = PdoResult(
            "Test Team", 0.47, 0.54, 101.0, "NEUTRAL", 40, time.time()
        )
        clear_pdo_cache()
        assert pdo_cache_size() == 0

    def test_size_zero_after_clear(self):
        pb._pdo_cache["A"] = PdoResult("A", 0.47, 0.54, 101.0, "NEUTRAL", 40, time.time())
        pb._pdo_cache["B"] = PdoResult("B", 0.47, 0.54, 101.0, "NEUTRAL", 40, time.time())
        clear_pdo_cache()
        assert pdo_cache_size() == 0
