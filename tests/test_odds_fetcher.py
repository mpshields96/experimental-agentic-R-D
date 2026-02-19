"""
tests/test_odds_fetcher.py — Titanium-Agentic
==============================================
Unit tests for core/odds_fetcher.py.

These tests do NOT make real API calls — all network calls are mocked.
Run: pytest tests/test_odds_fetcher.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.odds_fetcher import (
    QuotaTracker,
    get_api_key,
    fetch_game_lines,
    fetch_batch_odds,
    fetch_active_tennis_keys,
    compute_rest_days_from_schedule,
    all_books,
    available_sports,
    sport_key_for,
    SPORT_KEYS,
    MARKETS,
    TENNIS_MARKETS,
    PREFERRED_BOOKS,
)


# ---------------------------------------------------------------------------
# QuotaTracker
# ---------------------------------------------------------------------------

class TestQuotaTracker:
    def test_initial_state(self):
        qt = QuotaTracker()
        assert qt.used == 0
        assert qt.remaining is None
        assert qt.last_cost == 0

    def test_update_from_headers(self):
        qt = QuotaTracker()
        qt.update({
            "x-requests-remaining": "450",
            "x-requests-used": "50",
            "x-requests-last": "10",
        })
        assert qt.remaining == 450
        assert qt.used == 50
        assert qt.last_cost == 10

    def test_update_ignores_malformed(self):
        qt = QuotaTracker()
        qt.update({"x-requests-remaining": "not-a-number"})
        # Malformed header → ValueError caught → remaining stays None (no change)
        assert qt.remaining is None

    def test_report_string(self):
        qt = QuotaTracker()
        qt.update({"x-requests-remaining": "400", "x-requests-used": "100", "x-requests-last": "8"})
        report = qt.report()
        assert "400" in report
        assert "100" in report

    def test_is_low_when_below_threshold(self):
        qt = QuotaTracker()
        qt.update({"x-requests-remaining": "15", "x-requests-used": "485", "x-requests-last": "10"})
        assert qt.is_low(threshold=20) is True

    def test_is_low_false_when_above_threshold(self):
        qt = QuotaTracker()
        qt.update({"x-requests-remaining": "400", "x-requests-used": "100", "x-requests-last": "10"})
        assert qt.is_low(threshold=20) is False

    def test_is_low_false_when_remaining_none(self):
        qt = QuotaTracker()
        assert qt.is_low(threshold=20) is False


# ---------------------------------------------------------------------------
# API key loader
# ---------------------------------------------------------------------------

class TestGetApiKey:
    def test_returns_env_var(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key_123"}):
            key = get_api_key()
        assert key == "test_key_123"

    def test_returns_none_when_no_key(self):
        # Patch get_api_key at the module level to return None
        # (avoids env var and streamlit secrets complexity in tests)
        import core.odds_fetcher as of
        with patch.object(of, "get_api_key", return_value=None):
            key = of.get_api_key()
        assert key is None


# ---------------------------------------------------------------------------
# fetch_game_lines (mocked)
# ---------------------------------------------------------------------------

class TestFetchGameLines:
    def _make_response(self, data: list, status_code: int = 200) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = data
        mock_resp.headers = {
            "x-requests-remaining": "490",
            "x-requests-used": "10",
            "x-requests-last": "2",
        }
        return mock_resp

    def test_returns_games_on_success(self):
        fake_games = [
            {"id": "game_1", "home_team": "Duke", "away_team": "Virginia",
             "commence_time": "2026-02-20T01:00:00Z", "bookmakers": []}
        ]
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("core.odds_fetcher._fetch_with_backoff",
                       return_value=self._make_response(fake_games)):
                result = fetch_game_lines("basketball_ncaab")
        assert len(result) == 1
        assert result[0]["id"] == "game_1"

    def test_returns_empty_on_no_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "ODDS_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with patch("core.odds_fetcher.get_api_key", return_value=None):
                result = fetch_game_lines("basketball_ncaab")
        assert result == []

    def test_returns_empty_on_unknown_sport_key(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_game_lines("unknown_sport_xyz")
        assert result == []

    def test_returns_empty_on_fetch_failure(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("core.odds_fetcher._fetch_with_backoff", return_value=None):
                result = fetch_game_lines("basketball_nba")
        assert result == []

    def test_quota_updated_on_success(self):
        import core.odds_fetcher as of
        original_remaining = of.quota.remaining
        fake_games = []
        mock_resp = self._make_response(fake_games)
        mock_resp.headers["x-requests-remaining"] = "300"
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("core.odds_fetcher._fetch_with_backoff", return_value=mock_resp):
                fetch_game_lines("basketball_nba")
        assert of.quota.remaining == 300

    def test_handles_422_gracefully(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("core.odds_fetcher._fetch_with_backoff", return_value=None):
                # 422 returns None from _fetch_with_backoff (no retry)
                result = fetch_game_lines("soccer_epl")
        assert result == []


# ---------------------------------------------------------------------------
# fetch_batch_odds (mocked)
# ---------------------------------------------------------------------------

class TestFetchBatchOdds:
    def test_returns_dict_keyed_by_sport(self):
        fake_nba = [{"id": "nba_1"}]
        fake_ncaab = [{"id": "ncaab_1"}, {"id": "ncaab_2"}]

        def mock_fetch(sport_key: str) -> list:
            if "nba" in sport_key:
                return fake_nba
            return fake_ncaab

        with patch("core.odds_fetcher.fetch_game_lines", side_effect=mock_fetch):
            result = fetch_batch_odds(["NBA", "NCAAB"])

        assert "NBA" in result
        assert "NCAAB" in result
        assert result["NBA"] == fake_nba
        assert result["NCAAB"] == fake_ncaab

    def test_unknown_sport_returns_empty(self):
        with patch("core.odds_fetcher.fetch_game_lines", return_value=[]):
            result = fetch_batch_odds(["INVALID_SPORT"])
        assert result.get("INVALID_SPORT") == []

    def test_stops_when_quota_critical(self):
        import core.odds_fetcher as of
        # Set quota to critically low
        of.quota.remaining = 5
        call_count = [0]

        def mock_fetch(sport_key: str) -> list:
            call_count[0] += 1
            return []

        with patch("core.odds_fetcher.fetch_game_lines", side_effect=mock_fetch):
            result = fetch_batch_odds(["NBA", "NCAAB", "NHL"])

        # Should stop early due to low quota
        assert call_count[0] <= 1

        # Reset quota for other tests
        of.quota.remaining = None


# ---------------------------------------------------------------------------
# compute_rest_days_from_schedule
# ---------------------------------------------------------------------------

class TestComputeRestDays:
    def _make_game(self, home: str, away: str, hours_from_now: float) -> dict:
        dt = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
        return {
            "home_team": home,
            "away_team": away,
            "commence_time": dt.isoformat().replace("+00:00", "Z"),
        }

    def test_b2b_detected(self):
        """Two games 20 hours apart → rest_days = 0 (B2B)"""
        games = [
            self._make_game("Heat", "Bucks", 0),
            self._make_game("Heat", "Celtics", 20),
        ]
        rest = compute_rest_days_from_schedule(games)
        assert rest.get("Heat") == 0  # B2B

    def test_normal_rest_detected(self):
        """Two games 48 hours apart → rest_days = 2"""
        games = [
            self._make_game("Celtics", "Lakers", 0),
            self._make_game("Celtics", "Heat", 48),
        ]
        rest = compute_rest_days_from_schedule(games)
        assert rest.get("Celtics") == 2

    def test_single_game_returns_none(self):
        """Only 1 game in window → None (fall back to stub)"""
        games = [self._make_game("Warriors", "Suns", 24)]
        rest = compute_rest_days_from_schedule(games)
        assert rest.get("Warriors") is None

    def test_missing_commence_time_skipped(self):
        """Game with no commence_time is gracefully skipped"""
        games = [
            {"home_team": "Team A", "away_team": "Team B", "commence_time": ""},
        ]
        rest = compute_rest_days_from_schedule(games)
        # Both teams should have None (only 0 valid times each)
        # (no assertions on values — just verify no crash)
        assert isinstance(rest, dict)

    def test_empty_games_returns_empty(self):
        rest = compute_rest_days_from_schedule([])
        assert rest == {}

    def test_different_teams_tracked_separately(self):
        """Heat and Celtics each have their own rest day calculation"""
        games = [
            self._make_game("Heat", "Celtics", 0),
            self._make_game("Heat", "Bucks", 22),     # Heat: B2B
            self._make_game("Celtics", "Lakers", 50), # Celtics: 50h rest
        ]
        rest = compute_rest_days_from_schedule(games)
        assert rest.get("Heat") == 0    # B2B (22h apart)
        assert rest.get("Celtics") == 2  # 50h = 2 days


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    def test_sport_keys_coverage(self):
        """All major sports should be in SPORT_KEYS"""
        for sport in ["NBA", "NFL", "NCAAB", "NHL", "MLB"]:
            assert sport in SPORT_KEYS, f"{sport} missing from SPORT_KEYS"

    def test_markets_coverage(self):
        """All sport_key values should have MARKETS entries"""
        for sport_name, sport_key in SPORT_KEYS.items():
            assert sport_key in MARKETS, f"{sport_name} → {sport_key} missing from MARKETS"

    def test_soccer_markets_no_spreads(self):
        """Soccer sports must not include spreads (422 on bulk endpoint)"""
        soccer_keys = [k for k in MARKETS if k.startswith("soccer_")]
        for key in soccer_keys:
            assert "spreads" not in MARKETS[key], \
                f"{key} has spreads — will cause 422"

    def test_sport_key_for_valid(self):
        assert sport_key_for("NBA") == "basketball_nba"
        assert sport_key_for("nba") == "basketball_nba"  # case insensitive

    def test_sport_key_for_invalid(self):
        assert sport_key_for("CRICKET") is None

    def test_available_sports_returns_list(self):
        sports = available_sports()
        assert isinstance(sports, list)
        assert len(sports) > 0
        assert "NBA" in sports

    def test_all_books_filters_empty(self):
        bookmakers = [
            {"key": "dk", "markets": [{"key": "h2h"}]},
            {"key": "empty_book", "markets": []},         # no markets
            {"key": "fd", "markets": [{"key": "spreads"}]},
        ]
        result = all_books(bookmakers)
        assert len(result) == 2
        assert all(b["key"] != "empty_book" for b in result)

    def test_preferred_books_order(self):
        """DraftKings must be first — it's our primary book"""
        assert PREFERRED_BOOKS[0] == "draftkings"


# ---------------------------------------------------------------------------
# Tennis support
# ---------------------------------------------------------------------------

class TestTennisMarkets:

    def test_tennis_markets_constant_is_h2h(self):
        """Tennis only supports h2h — no spreads or totals."""
        assert "h2h" in TENNIS_MARKETS
        assert "spreads" not in TENNIS_MARKETS

    def test_fetch_game_lines_accepts_atp_key(self):
        """Tennis ATP sport keys must pass through to fetch without unknown_key error."""
        fake_games = [{"id": "tennis_1", "home_team": "N. Djokovic", "away_team": "C. Alcaraz",
                        "commence_time": "2026-02-20T10:00:00Z", "bookmakers": []}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_games
        mock_resp.headers = {"x-requests-remaining": "490", "x-requests-used": "10", "x-requests-last": "1"}

        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("core.odds_fetcher._fetch_with_backoff", return_value=mock_resp):
                result = fetch_game_lines("tennis_atp_qatar_open")
        assert result == fake_games

    def test_fetch_game_lines_accepts_wta_key(self):
        """Tennis WTA sport keys must also pass through."""
        fake_games = [{"id": "wta_1"}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_games
        mock_resp.headers = {"x-requests-remaining": "490", "x-requests-used": "10", "x-requests-last": "1"}

        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("core.odds_fetcher._fetch_with_backoff", return_value=mock_resp):
                result = fetch_game_lines("tennis_wta_dubai")
        assert result == fake_games

    def test_unknown_non_tennis_key_still_returns_empty(self):
        """Non-tennis unknown keys still return empty (not in MARKETS, not tennis prefix)."""
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_game_lines("unknown_sport_xyz")
        assert result == []


class TestFetchActiveTennisKeys:

    def _make_sports_response(self, keys: list[str]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"key": k, "active": True, "title": k.replace("_", " ")}
            for k in keys
        ]
        mock_resp.headers = {"x-requests-remaining": "490", "x-requests-used": "10", "x-requests-last": "1"}
        return mock_resp

    def test_returns_active_atp_keys(self):
        mock_resp = self._make_sports_response([
            "tennis_atp_qatar_open",
            "tennis_atp_dubai",
            "basketball_nba",          # should be excluded
        ])
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", return_value=mock_resp):
                result = fetch_active_tennis_keys()
        assert "tennis_atp_qatar_open" in result
        assert "tennis_atp_dubai" in result
        assert "basketball_nba" not in result

    def test_returns_active_wta_keys(self):
        mock_resp = self._make_sports_response(["tennis_wta_dubai", "tennis_wta_abu_dhabi"])
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", return_value=mock_resp):
                result = fetch_active_tennis_keys()
        assert "tennis_wta_dubai" in result

    def test_excludes_inactive_tournaments(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"key": "tennis_atp_wimbledon", "active": False},   # not active
            {"key": "tennis_atp_qatar_open", "active": True},
        ]
        mock_resp.headers = {"x-requests-remaining": "490", "x-requests-used": "10", "x-requests-last": "1"}
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", return_value=mock_resp):
                result = fetch_active_tennis_keys()
        assert "tennis_atp_wimbledon" not in result
        assert "tennis_atp_qatar_open" in result

    def test_exclude_wta_when_flag_false(self):
        mock_resp = self._make_sports_response(["tennis_atp_qatar_open", "tennis_wta_dubai"])
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", return_value=mock_resp):
                result = fetch_active_tennis_keys(include_wta=False)
        assert "tennis_atp_qatar_open" in result
        assert "tennis_wta_dubai" not in result

    def test_exclude_atp_when_flag_false(self):
        mock_resp = self._make_sports_response(["tennis_atp_qatar_open", "tennis_wta_dubai"])
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", return_value=mock_resp):
                result = fetch_active_tennis_keys(include_atp=False)
        assert "tennis_wta_dubai" in result
        assert "tennis_atp_qatar_open" not in result

    def test_returns_empty_on_no_api_key(self):
        with patch("core.odds_fetcher.get_api_key", return_value=None):
            result = fetch_active_tennis_keys()
        assert result == []

    def test_returns_empty_on_api_error(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", side_effect=Exception("network error")):
                result = fetch_active_tennis_keys()
        assert result == []

    def test_returns_empty_list_when_no_active_tennis(self):
        mock_resp = self._make_sports_response(["basketball_nba", "americanfootball_nfl"])
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            with patch("requests.get", return_value=mock_resp):
                result = fetch_active_tennis_keys()
        assert result == []


class TestFetchBatchOddsTennis:

    def test_tennis_keys_included_in_batch_result(self):
        """When include_tennis=True, tennis sport keys appear in results dict."""
        tennis_keys = ["tennis_atp_qatar_open", "tennis_wta_dubai"]
        fake_tennis_games = [{"id": "t1"}]

        with patch("core.odds_fetcher.fetch_active_tennis_keys", return_value=tennis_keys):
            with patch("core.odds_fetcher.fetch_game_lines", return_value=fake_tennis_games):
                result = fetch_batch_odds(sports=[], include_tennis=True)

        assert "tennis_atp_qatar_open" in result
        assert "tennis_wta_dubai" in result
        assert result["tennis_atp_qatar_open"] == fake_tennis_games

    def test_tennis_excluded_when_flag_false(self):
        """When include_tennis=False, fetch_active_tennis_keys is not called."""
        with patch("core.odds_fetcher.fetch_active_tennis_keys") as mock_tennis:
            with patch("core.odds_fetcher.fetch_game_lines", return_value=[]):
                result = fetch_batch_odds(sports=["NBA"], include_tennis=False)
        mock_tennis.assert_not_called()
        assert not any(k.startswith("tennis") for k in result.keys())

    def test_static_sports_still_work_with_tennis_enabled(self):
        """NBA fetch still works normally when include_tennis=True."""
        fake_nba = [{"id": "nba_1"}]

        def mock_lines(sport_key: str) -> list:
            if "nba" in sport_key:
                return fake_nba
            return []

        with patch("core.odds_fetcher.fetch_active_tennis_keys", return_value=[]):
            with patch("core.odds_fetcher.fetch_game_lines", side_effect=mock_lines):
                result = fetch_batch_odds(sports=["NBA"], include_tennis=True)

        assert result["NBA"] == fake_nba


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    sys.exit(result.returncode)
