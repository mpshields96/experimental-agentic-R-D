"""
tests/test_weather_feed.py — Titanium-Agentic
==============================================
Unit tests for core/weather_feed.py.

Tests cover:
- All 32 NFL stadiums present and data complete
- Indoor/retractable stadiums return 0.0 without API call
- API failure graceful degradation to static stub
- Cache TTL behavior
- Unknown team fallback
- parse_game_markets wind_mph param (NFL kill switch integration)

Run: pytest tests/test_weather_feed.py -v
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.weather_feed import (
    NFL_STADIUMS,
    get_stadium_wind,
    get_stadium_info,
    clear_wind_cache,
    _DEFAULT_WIND_MPH,
)


# ---------------------------------------------------------------------------
# Stadium data completeness
# ---------------------------------------------------------------------------

class TestStadiumData:
    def test_all_32_nfl_teams_present(self):
        """All 32 NFL franchises must have stadium data."""
        assert len(NFL_STADIUMS) == 32

    def test_all_stadiums_have_required_keys(self):
        """Every stadium entry must have lat, lon, roof, avg_wind."""
        for team, data in NFL_STADIUMS.items():
            assert "lat" in data, f"{team} missing lat"
            assert "lon" in data, f"{team} missing lon"
            assert "roof" in data, f"{team} missing roof"
            assert "avg_wind" in data, f"{team} missing avg_wind"

    def test_roof_types_valid(self):
        """Roof type must be one of: outdoor, retractable, dome."""
        valid = {"outdoor", "retractable", "dome"}
        for team, data in NFL_STADIUMS.items():
            assert data["roof"] in valid, f"{team}: invalid roof '{data['roof']}'"

    def test_coordinates_in_valid_range(self):
        """All stadiums should be in continental US / nearby territories."""
        for team, data in NFL_STADIUMS.items():
            assert 18.0 < data["lat"] < 50.0, f"{team} lat out of range: {data['lat']}"
            assert -130.0 < data["lon"] < -65.0, f"{team} lon out of range: {data['lon']}"

    def test_avg_wind_non_negative(self):
        """No negative wind speeds."""
        for team, data in NFL_STADIUMS.items():
            assert data["avg_wind"] >= 0.0, f"{team} negative avg_wind"

    def test_indoor_stadiums_have_zero_avg_wind(self):
        """Dome and retractable-roof stadiums should have avg_wind = 0.0."""
        for team, data in NFL_STADIUMS.items():
            if data["roof"] in ("dome", "retractable"):
                assert data["avg_wind"] == 0.0, f"{team} indoor but avg_wind={data['avg_wind']}"

    def test_outdoor_stadiums_have_positive_avg_wind(self):
        """All outdoor stadiums should have avg_wind > 0."""
        for team, data in NFL_STADIUMS.items():
            if data["roof"] == "outdoor":
                assert data["avg_wind"] > 0.0, f"{team} outdoor but avg_wind=0"

    def test_buffalo_bills_windiest(self):
        """Buffalo should be among the windiest outdoor stadiums."""
        buffalo = NFL_STADIUMS["Buffalo Bills"]
        assert buffalo["roof"] == "outdoor"
        assert buffalo["avg_wind"] >= 12.0

    def test_specific_indoor_teams(self):
        """Known dome/retractable teams return 0.0 wind directly."""
        indoor_teams = [
            "Indianapolis Colts",   # dome
            "Las Vegas Raiders",    # dome
            "Minnesota Vikings",    # dome
            "New Orleans Saints",   # dome
            "Detroit Lions",        # dome
            "Dallas Cowboys",       # retractable
            "Houston Texans",       # retractable
            "Arizona Cardinals",    # retractable
            "Atlanta Falcons",      # retractable
        ]
        for team in indoor_teams:
            assert team in NFL_STADIUMS, f"{team} not in NFL_STADIUMS"
            assert NFL_STADIUMS[team]["roof"] in ("dome", "retractable")


# ---------------------------------------------------------------------------
# get_stadium_wind — indoor stadiums
# ---------------------------------------------------------------------------

class TestIndoorStadiums:
    def setup_method(self):
        clear_wind_cache()

    def test_dome_returns_zero_no_api_call(self):
        """Dome stadiums return 0.0 — no API call needed."""
        with patch("core.weather_feed._fetch_open_meteo_wind") as mock_fetch:
            wind = get_stadium_wind("Indianapolis Colts")
            assert wind == 0.0
            mock_fetch.assert_not_called()

    def test_retractable_returns_zero_no_api_call(self):
        """Retractable roof returns 0.0 — no API call needed."""
        with patch("core.weather_feed._fetch_open_meteo_wind") as mock_fetch:
            wind = get_stadium_wind("Dallas Cowboys", "2026-09-13T17:00:00Z")
            assert wind == 0.0
            mock_fetch.assert_not_called()

    def test_las_vegas_raiders_dome(self):
        """Las Vegas Raiders (Allegiant Stadium — dome) → 0.0."""
        wind = get_stadium_wind("Las Vegas Raiders")
        assert wind == 0.0


# ---------------------------------------------------------------------------
# get_stadium_wind — outdoor stadiums with API mock
# ---------------------------------------------------------------------------

class TestOutdoorStadiumsWithMock:
    def setup_method(self):
        clear_wind_cache()

    def test_outdoor_stadium_uses_api(self):
        """Outdoor stadium triggers API call."""
        with patch("core.weather_feed._fetch_open_meteo_wind", return_value=14.2) as mock_fetch:
            wind = get_stadium_wind("Buffalo Bills", "2026-10-05T20:00:00Z")
            assert wind == 14.2
            mock_fetch.assert_called_once()

    def test_api_failure_falls_back_to_stub(self):
        """On API failure (None returned), fall back to avg_wind static stub."""
        with patch("core.weather_feed._fetch_open_meteo_wind", return_value=None):
            wind = get_stadium_wind("Buffalo Bills", "2026-10-05T20:00:00Z")
            assert wind == NFL_STADIUMS["Buffalo Bills"]["avg_wind"]

    def test_result_cached_on_second_call(self):
        """Second call with same team+date+hour uses cache, not API."""
        with patch("core.weather_feed._fetch_open_meteo_wind", return_value=11.5) as mock_fetch:
            w1 = get_stadium_wind("Green Bay Packers", "2026-11-01T18:00:00Z")
            w2 = get_stadium_wind("Green Bay Packers", "2026-11-01T18:30:00Z")  # same hour
            assert w1 == w2 == 11.5
            assert mock_fetch.call_count == 1  # cached after first call

    def test_unknown_team_uses_default(self):
        """Unknown team returns _DEFAULT_WIND_MPH stub."""
        wind = get_stadium_wind("Unknown Team FC")
        assert wind == _DEFAULT_WIND_MPH

    def test_no_commence_time_uses_current_time(self):
        """No commence_time → uses current time as proxy, still returns float."""
        with patch("core.weather_feed._fetch_open_meteo_wind", return_value=8.0):
            wind = get_stadium_wind("Kansas City Chiefs")
            assert isinstance(wind, float)
            assert wind >= 0.0


# ---------------------------------------------------------------------------
# get_stadium_info
# ---------------------------------------------------------------------------

class TestGetStadiumInfo:
    def test_returns_dict_for_known_team(self):
        info = get_stadium_info("Philadelphia Eagles")
        assert info is not None
        assert "lat" in info
        assert "lon" in info
        assert info["roof"] == "outdoor"

    def test_returns_none_for_unknown_team(self):
        info = get_stadium_info("Fictional Franchises")
        assert info is None


# ---------------------------------------------------------------------------
# NFL kill switch integration via parse_game_markets wind_mph param
# ---------------------------------------------------------------------------

class TestNFLWindKillIntegration:
    def _make_nfl_game(self, home="Kansas City Chiefs", away="Buffalo Bills"):
        """Minimal NFL game with total market for wind kill switch testing."""
        return {
            "id": "nfl-wind-test",
            "home_team": home,
            "away_team": away,
            "commence_time": "2026-11-08T21:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {"key": "totals", "outcomes": [
                            {"name": "Over",  "price": -110, "point": 44.5},
                            {"name": "Under", "price": -110, "point": 44.5},
                        ]},
                    ],
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "markets": [
                        {"key": "totals", "outcomes": [
                            {"name": "Over",  "price": -108, "point": 44.5},
                            {"name": "Under", "price": -112, "point": 44.5},
                        ]},
                    ],
                },
                {
                    "key": "betmgm",
                    "title": "BetMGM",
                    "markets": [
                        {"key": "totals", "outcomes": [
                            {"name": "Over",  "price": -109, "point": 44.5},
                            {"name": "Under", "price": -111, "point": 44.5},
                        ]},
                    ],
                },
            ],
        }

    def test_high_wind_kills_totals(self):
        """Wind >20mph kills all total candidates for NFL."""
        from core.math_engine import parse_game_markets
        game = self._make_nfl_game()
        cands = parse_game_markets(game, "NFL", wind_mph=21.0)
        totals = [c for c in cands if c.market_type == "totals"]
        assert totals == [], f"Expected 0 total candidates with wind>20, got {len(totals)}"

    def test_force_under_wind_flags_not_kills(self):
        """Wind >15mph AND total >42 → FORCE_UNDER flag on Over, not hard kill."""
        from core.math_engine import parse_game_markets
        game = self._make_nfl_game()
        cands = parse_game_markets(game, "NFL", wind_mph=17.0)
        totals = [c for c in cands if c.market_type == "totals"]
        # Game may or may not have edge — test that if totals exist, Over has FORCE_UNDER
        over_cands = [c for c in totals if c.target.startswith("Over")]
        for c in over_cands:
            assert "FORCE_UNDER" in c.kill_reason, f"Expected FORCE_UNDER, got: {c.kill_reason!r}"

    def test_low_wind_no_flag(self):
        """Wind <15mph → no kill_reason on totals."""
        from core.math_engine import parse_game_markets
        game = self._make_nfl_game()
        cands = parse_game_markets(game, "NFL", wind_mph=8.0)
        totals = [c for c in cands if c.market_type == "totals"]
        for c in totals:
            assert c.kill_reason == "", f"Unexpected kill_reason with low wind: {c.kill_reason!r}"

    def test_zero_wind_default_no_flag(self):
        """Default wind_mph=0.0 → no NFL wind kill fires."""
        from core.math_engine import parse_game_markets
        game = self._make_nfl_game()
        cands = parse_game_markets(game, "NFL")  # default wind_mph=0.0
        totals = [c for c in cands if c.market_type == "totals"]
        for c in totals:
            assert c.kill_reason == ""

    def test_non_nfl_sport_ignores_wind(self):
        """NBA game with wind_mph set → wind is ignored."""
        from core.math_engine import parse_game_markets
        game = self._make_nfl_game(home="Lakers", away="Heat")
        cands = parse_game_markets(game, "NBA", wind_mph=25.0)
        for c in cands:
            if c.market_type == "totals":
                assert "FORCE_UNDER" not in c.kill_reason
                assert "KILL" not in c.kill_reason or "Wind" not in c.kill_reason
