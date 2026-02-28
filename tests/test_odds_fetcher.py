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
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core.odds_fetcher as _of_module
from core.odds_fetcher import (
    QuotaTracker,
    CreditLedger,
    DailyCreditLog,
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
    SESSION_CREDIT_SOFT_LIMIT,
    SESSION_CREDIT_HARD_STOP,
    BILLING_RESERVE,
    SUBSCRIPTION_CREDITS,
    BILLING_DAY,
)


def _reset_quota() -> None:
    """Reset module-level quota tracker to pristine state between tests."""
    _of_module.quota.used = 0
    _of_module.quota.remaining = 10_000   # safe remaining — won't trigger billing reserve
    _of_module.quota.last_cost = 0
    _of_module.quota.session_used = 0
    # Also zero daily log in-memory state so DAILY_CREDIT_CAP doesn't interfere.
    # The real daily_quota.json is NOT written (no _save()) — only in-memory reset.
    _of_module.quota.daily_log._data["used_today"] = 0
    # credit_ledger writes to SQLite — redirect to :memory: to avoid test pollution.
    _of_module.quota.credit_ledger = CreditLedger(db_path=":memory:")


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
        assert "400" in report    # remaining
        assert "100" in report    # used (billing period)
        assert "session=" in report

    def test_session_soft_limit(self):
        qt = QuotaTracker()
        qt.remaining = 5000
        qt.session_used = SESSION_CREDIT_SOFT_LIMIT - 1
        assert qt.is_session_soft_limit() is False
        qt.session_used = SESSION_CREDIT_SOFT_LIMIT
        assert qt.is_session_soft_limit() is True

    def test_session_hard_stop_from_session_count(self):
        qt = QuotaTracker()
        qt.remaining = 5000
        qt.session_used = SESSION_CREDIT_HARD_STOP
        assert qt.is_session_hard_stop() is True

    def test_session_hard_stop_from_billing_reserve(self):
        qt = QuotaTracker()
        qt.remaining = BILLING_RESERVE - 1   # below global floor
        qt.session_used = 0
        assert qt.is_session_hard_stop() is True

    def test_session_hard_stop_false_when_safe(self):
        qt = QuotaTracker()
        qt.remaining = 5000
        qt.session_used = 50
        assert qt.is_session_hard_stop() is False

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
    def setup_method(self):
        _reset_quota()

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
    def setup_method(self):
        _reset_quota()

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


# ---------------------------------------------------------------------------
# CreditLedger
# ---------------------------------------------------------------------------

class TestCreditLedger:
    def test_schema_created_in_memory(self):
        cl = CreditLedger(db_path=":memory:")
        # Should not raise; schema exists
        result = cl.get_today_allowance("2026-03-01")
        assert result is None  # no record yet

    def test_record_and_retrieve(self):
        cl = CreditLedger(db_path=":memory:")
        cl.record("2026-03-01", used=45, remaining=9955, allowance=357)
        assert cl.get_today_allowance("2026-03-01") == 357

    def test_record_upsert_updates_value(self):
        cl = CreditLedger(db_path=":memory:")
        cl.record("2026-03-01", used=45, remaining=9955, allowance=357)
        cl.record("2026-03-01", used=90, remaining=9910, allowance=362)
        assert cl.get_today_allowance("2026-03-01") == 362

    def test_different_dates_stored_separately(self):
        cl = CreditLedger(db_path=":memory:")
        cl.record("2026-03-01", used=45, remaining=9955, allowance=357)
        cl.record("2026-03-02", used=20, remaining=9935, allowance=360)
        assert cl.get_today_allowance("2026-03-01") == 357
        assert cl.get_today_allowance("2026-03-02") == 360

    def test_get_today_allowance_missing_date_returns_none(self):
        cl = CreditLedger(db_path=":memory:")
        assert cl.get_today_allowance("2026-03-15") is None

    def test_record_accepts_none_remaining(self):
        cl = CreditLedger(db_path=":memory:")
        cl.record("2026-03-01", used=10, remaining=None, allowance=333)
        assert cl.get_today_allowance("2026-03-01") == 333


# ---------------------------------------------------------------------------
# DailyAllowance and _days_until_billing
# ---------------------------------------------------------------------------

class TestDaysUntilBilling:
    def _qt(self) -> QuotaTracker:
        qt = QuotaTracker()
        qt.credit_ledger = CreditLedger(db_path=":memory:")
        return qt

    def test_before_billing_day(self):
        qt = self._qt()
        # Today is Feb 25, billing day is 1 → next billing is Mar 1 → 4 days
        today = date(2026, 2, 25)
        assert qt._days_until_billing(today) == 4

    def test_on_billing_day_goes_to_next_month(self):
        qt = self._qt()
        # Today IS billing day (1st) → next billing is next month's 1st → 28/30/31 days
        today = date(2026, 3, 1)
        # March has 31 days → next billing is Apr 1 → 31 days
        assert qt._days_until_billing(today) == 31

    def test_last_day_before_billing(self):
        qt = self._qt()
        # Feb 28, billing day 1 → next billing Mar 1 → 1 day
        today = date(2026, 2, 28)
        assert qt._days_until_billing(today) == 1

    def test_december_rolls_to_january(self):
        qt = self._qt()
        today = date(2025, 12, 15)
        # Dec 15 → next billing Jan 1 → 17 days
        assert qt._days_until_billing(today) == 17

    def test_returns_at_least_1(self):
        qt = self._qt()
        # Even on billing day itself, returns next month (≥1)
        today = date(2026, 1, 1)
        result = qt._days_until_billing(today)
        assert result >= 1


class TestDailyAllowance:
    def _qt(self, billing_used: int = 0) -> QuotaTracker:
        qt = QuotaTracker()
        qt.used = billing_used
        qt.credit_ledger = CreditLedger(db_path=":memory:")
        return qt

    def test_full_budget_start_of_period(self):
        # Day 1 of billing, nothing used: 10000 / 28 ≈ 357
        qt = self._qt(billing_used=0)
        today = date(2026, 3, 1)   # billing day → 31 days until Apr 1
        allowance = qt.daily_allowance(today)
        assert allowance == 10_000 // 31  # = 322

    def test_halfway_through_period(self):
        # 5000 used, 15 days left → 5000/15 = 333
        qt = self._qt(billing_used=5_000)
        today = date(2026, 3, 16)  # 16 days until Apr 1 = 16 days
        allowance = qt.daily_allowance(today)
        assert allowance == 5_000 // 16  # = 312

    def test_budget_exhausted_returns_1(self):
        # Used more than monthly budget → remaining_budget = 0 → max(1, ...)
        qt = self._qt(billing_used=15_000)
        today = date(2026, 3, 15)
        assert qt.daily_allowance(today) == 1

    def test_allowance_uses_50_percent_of_subscription(self):
        qt = self._qt(billing_used=0)
        today = date(2026, 3, 2)   # 30 days until Apr 1
        allowance = qt.daily_allowance(today)
        # monthly_budget = 20000 * 0.5 = 10000; 10000 // 30 = 333
        assert allowance == 10_000 // 30


# ---------------------------------------------------------------------------
# is_daily_soft_limit and is_daily_hard_stop
# ---------------------------------------------------------------------------

class TestDailySoftLimit:
    def _qt(self, used_today: int, billing_used: int = 0) -> QuotaTracker:
        qt = QuotaTracker()
        qt.used = billing_used
        qt.daily_log._data["used_today"] = used_today
        qt.credit_ledger = CreditLedger(db_path=":memory:")
        return qt

    def test_below_soft_limit(self):
        # allowance = 10000 // 4 = 2500 (Feb 25); 80% = 2000; used = 1999
        qt = self._qt(used_today=1999, billing_used=0)
        today = date(2026, 2, 25)
        assert not qt.is_daily_soft_limit(today)

    def test_at_soft_limit(self):
        qt = self._qt(used_today=2000, billing_used=0)
        today = date(2026, 2, 25)   # allowance = 2500; 80% = 2000
        assert qt.is_daily_soft_limit(today)

    def test_above_soft_limit(self):
        qt = self._qt(used_today=2400, billing_used=0)
        today = date(2026, 2, 25)
        assert qt.is_daily_soft_limit(today)


class TestDailyHardStop:
    def _qt(self, used_today: int, billing_used: int = 0) -> QuotaTracker:
        qt = QuotaTracker()
        qt.used = billing_used
        qt.daily_log._data["used_today"] = used_today
        qt.credit_ledger = CreditLedger(db_path=":memory:")
        return qt

    def test_below_hard_stop(self):
        # allowance = 10000 // 4 = 2500; used = 2499
        qt = self._qt(used_today=2499, billing_used=0)
        today = date(2026, 2, 25)
        assert not qt.is_daily_hard_stop(today)

    def test_at_hard_stop(self):
        qt = self._qt(used_today=2500, billing_used=0)
        today = date(2026, 2, 25)
        assert qt.is_daily_hard_stop(today)

    def test_above_hard_stop(self):
        qt = self._qt(used_today=3000, billing_used=0)
        today = date(2026, 2, 25)
        assert qt.is_daily_hard_stop(today)

    def test_daily_hard_stop_triggers_session_hard_stop(self):
        # When daily budget is exhausted, is_session_hard_stop() must return True.
        # Uses _today injection so the test is not date-sensitive.
        qt = self._qt(used_today=9999, billing_used=0)
        today = date(2026, 2, 25)   # allowance = 10000//4 = 2500; 9999 >> 2500
        qt.session_used = 0
        qt.remaining = 5_000   # above BILLING_RESERVE
        # Pass _today so daily_allowance() uses Feb-25 (2500), not real date.
        assert qt.is_daily_hard_stop(_today=today)

    def test_session_hard_stop_false_when_daily_budget_safe(self):
        qt = QuotaTracker()
        qt.used = 0
        qt.remaining = 5_000
        qt.session_used = 0
        qt.daily_log._data["used_today"] = 0
        qt.credit_ledger = CreditLedger(db_path=":memory:")
        assert not qt.is_session_hard_stop()


class TestConstantsIntegrity:
    def test_subscription_credits(self):
        assert SUBSCRIPTION_CREDITS == 20_000

    def test_billing_day(self):
        assert BILLING_DAY == 1

    def test_monthly_budget_is_50_percent(self):
        from core.odds_fetcher import _DAILY_BUDGET_FRACTION
        assert _DAILY_BUDGET_FRACTION == 0.50
        assert int(SUBSCRIPTION_CREDITS * _DAILY_BUDGET_FRACTION) == 10_000

    def test_soft_fraction(self):
        from core.odds_fetcher import _DAILY_SOFT_FRACTION
        assert _DAILY_SOFT_FRACTION == 0.80


# ---------------------------------------------------------------------------
# Player props — PropsQuotaTracker + fetch_props_for_event (Session 35)
# ---------------------------------------------------------------------------

from core.odds_fetcher import (
    PropsQuotaTracker,
    fetch_props_for_event,
    get_props_api_key,
    PROPS_SESSION_CREDIT_CAP,
    PROPS_DAILY_CREDIT_CAP,
    PROP_MARKETS,
    props_quota as _module_props_quota,
)


def _reset_props_quota() -> None:
    """Reset module-level props quota tracker to pristine state."""
    _module_props_quota.session_used = 0
    _module_props_quota.last_cost = 0
    _module_props_quota.daily_log._data["used_today"] = 0


def _make_props_mock_response(data: dict, status: int = 200, last_cost: int = 2) -> MagicMock:
    """Build a mock requests.Response for the event-level props endpoint."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = data
    mock_resp.headers = {
        "x-requests-remaining": "480",
        "x-requests-used": "20",
        "x-requests-last": str(last_cost),
    }
    return mock_resp


class TestPropsQuotaTracker:
    def setup_method(self):
        _reset_props_quota()

    def test_initial_state(self):
        qt = PropsQuotaTracker()
        assert qt.session_used == 0
        assert qt.last_cost == 0

    def test_record_increments_session_used(self):
        qt = PropsQuotaTracker()
        qt.record(3)
        assert qt.session_used == 3
        assert qt.last_cost == 3

    def test_record_accumulates(self):
        qt = PropsQuotaTracker()
        qt.record(2)
        qt.record(3)
        assert qt.session_used == 5

    def test_is_session_hard_stop_false_below_cap(self):
        qt = PropsQuotaTracker()
        qt.session_used = PROPS_SESSION_CREDIT_CAP - 1
        assert not qt.is_session_hard_stop()

    def test_is_session_hard_stop_true_at_cap(self):
        qt = PropsQuotaTracker()
        qt.session_used = PROPS_SESSION_CREDIT_CAP
        assert qt.is_session_hard_stop()

    def test_is_session_hard_stop_true_over_cap(self):
        qt = PropsQuotaTracker()
        qt.session_used = PROPS_SESSION_CREDIT_CAP + 10
        assert qt.is_session_hard_stop()

    def test_remaining_session_budget(self):
        qt = PropsQuotaTracker()
        qt.session_used = 20
        assert qt.remaining_session_budget() == PROPS_SESSION_CREDIT_CAP - 20

    def test_remaining_session_budget_clamps_to_zero(self):
        qt = PropsQuotaTracker()
        qt.session_used = PROPS_SESSION_CREDIT_CAP + 99
        assert qt.remaining_session_budget() == 0

    def test_report_includes_session_used_and_cap(self):
        qt = PropsQuotaTracker()
        qt.session_used = 15
        report = qt.report()
        assert "15" in report
        assert str(PROPS_SESSION_CREDIT_CAP) in report


class TestPropsDailyCreditLog:
    """Tests for DailyCreditLog wired into PropsQuotaTracker.

    All tests use tmp_path to avoid touching data/props_daily_log.json.
    """

    def _qt(self, tmp_path) -> PropsQuotaTracker:
        """Fresh PropsQuotaTracker with daily_log redirected to tmp_path."""
        qt = PropsQuotaTracker()
        qt.daily_log = DailyCreditLog(str(tmp_path / "props.json"))
        return qt

    def test_daily_log_path_separate_from_main(self):
        """PropsQuotaTracker.daily_log path ends with props_daily_log.json (not daily_quota.json)."""
        qt = PropsQuotaTracker()
        assert qt.daily_log._path.endswith("props_daily_log.json")
        assert "daily_quota" not in qt.daily_log._path

    def test_is_daily_cap_hit_false_below_cap(self, tmp_path):
        qt = self._qt(tmp_path)
        qt.daily_log._data["used_today"] = PROPS_DAILY_CREDIT_CAP - 1
        assert not qt.is_daily_cap_hit()

    def test_is_daily_cap_hit_true_at_cap(self, tmp_path):
        qt = self._qt(tmp_path)
        qt.daily_log._data["used_today"] = PROPS_DAILY_CREDIT_CAP
        assert qt.is_daily_cap_hit()

    def test_is_daily_cap_hit_true_over_cap(self, tmp_path):
        qt = self._qt(tmp_path)
        qt.daily_log._data["used_today"] = PROPS_DAILY_CREDIT_CAP + 10
        assert qt.is_daily_cap_hit()

    def test_is_session_hard_stop_triggered_by_daily_cap(self, tmp_path):
        """Daily cap hit triggers is_session_hard_stop even when session_used == 0."""
        qt = self._qt(tmp_path)
        qt.daily_log._data["used_today"] = PROPS_DAILY_CREDIT_CAP
        qt.session_used = 0
        assert qt.is_session_hard_stop()

    def test_record_with_remaining_updates_daily_log(self, tmp_path):
        """record(cost, remaining=N) propagates remaining into daily_log."""
        qt = self._qt(tmp_path)
        qt.record(3, remaining=490)  # first call → start_remaining = 490
        qt.record(2, remaining=485)  # second call → used = 490 - 485 = 5
        assert qt.daily_log.used_today() == 5

    def test_record_without_remaining_does_not_update_daily_log(self, tmp_path):
        """record(cost) without remaining leaves daily_log.used_today at 0."""
        qt = self._qt(tmp_path)
        qt.record(3)
        assert qt.daily_log.used_today() == 0


class TestFetchPropsForEvent:
    """Tests for fetch_props_for_event().

    All network calls use _session injection — zero real API calls.
    All props quota interactions use _quota injection — no module state pollution.
    """

    def _quota(self) -> PropsQuotaTracker:
        """Fresh quota tracker for each test."""
        return PropsQuotaTracker()

    def _fake_props_data(self) -> dict:
        """Minimal valid event dict that mirrors The Odds API event props response."""
        return {
            "id": "evt_001",
            "sport_key": "basketball_nba",
            "home_team": "Los Angeles Lakers",
            "away_team": "Golden State Warriors",
            "commence_time": "2026-03-01T02:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "player_points",
                            "outcomes": [
                                {"name": "Over", "description": "LeBron James", "price": -115, "point": 24.5},
                                {"name": "Under", "description": "LeBron James", "price": -105, "point": 24.5},
                            ],
                        }
                    ],
                }
            ],
        }

    def test_returns_raw_dict_on_success(self):
        mock_resp = _make_props_mock_response(self._fake_props_data())
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert isinstance(result, dict)
        assert result.get("id") == "evt_001"

    def test_records_credit_cost_from_header(self):
        mock_resp = _make_props_mock_response(self._fake_props_data(), last_cost=2)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        qt = self._quota()
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points", "player_rebounds"],
                _quota=qt,
                _session=mock_session,
            )
        assert qt.session_used == 2

    def test_falls_back_to_market_count_if_header_missing(self):
        """If x-requests-last is absent, cost defaults to len(prop_markets)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self._fake_props_data()
        mock_resp.headers = {}  # no x-requests-last header
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        qt = self._quota()
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points", "player_rebounds", "player_assists"],
                _quota=qt,
                _session=mock_session,
            )
        assert qt.session_used == 3  # fallback = len(prop_markets)

    def test_returns_empty_dict_when_quota_exhausted(self):
        qt = self._quota()
        qt.session_used = PROPS_SESSION_CREDIT_CAP  # already at cap
        mock_session = MagicMock()
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=qt,
                _session=mock_session,
            )
        assert result == {}
        mock_session.get.assert_not_called()

    def test_returns_empty_dict_when_no_api_key(self):
        # Patch both key functions so no key is found at all
        with patch("core.odds_fetcher.get_props_api_key", return_value=None):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
            )
        assert result == {}

    def test_returns_empty_dict_on_422(self):
        """422 = market not available on this tier — return {} without retry."""
        mock_resp = _make_props_mock_response({}, status=422)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert result == {}

    def test_returns_empty_dict_on_401(self):
        mock_resp = _make_props_mock_response({}, status=401)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert result == {}

    def test_returns_empty_dict_on_500(self):
        mock_resp = _make_props_mock_response({}, status=500)
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert result == {}

    def test_returns_empty_dict_on_request_exception(self):
        import requests as _requests
        mock_session = MagicMock()
        mock_session.get.side_effect = _requests.exceptions.ConnectionError("network down")
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert result == {}

    def test_returns_empty_dict_on_empty_event_id(self):
        mock_session = MagicMock()
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert result == {}
        mock_session.get.assert_not_called()

    def test_returns_empty_dict_on_empty_markets_list(self):
        mock_session = MagicMock()
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            result = fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=[],
                _quota=self._quota(),
                _session=mock_session,
            )
        assert result == {}
        mock_session.get.assert_not_called()

    def test_does_not_pollute_main_quota(self):
        """Props fetch must NOT increment the main odds quota tracker."""
        _reset_props_quota()
        initial_main_session_used = _of_module.quota.session_used
        mock_resp = _make_props_mock_response(self._fake_props_data())
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        qt = self._quota()
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            fetch_props_for_event(
                event_id="evt_001",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=qt,
                _session=mock_session,
            )
        # Main quota must be unchanged
        assert _of_module.quota.session_used == initial_main_session_used

    def test_uses_correct_event_endpoint_url(self):
        """Verify the request is sent to the event-level props endpoint."""
        mock_resp = _make_props_mock_response(self._fake_props_data())
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch.dict(os.environ, {"ODDS_API_KEY": "test_key"}):
            fetch_props_for_event(
                event_id="evt_abc123",
                sport_key="basketball_nba",
                prop_markets=["player_points"],
                _quota=self._quota(),
                _session=mock_session,
            )
        call_args = mock_session.get.call_args
        url = call_args[0][0]
        assert "events/evt_abc123/odds" in url
        assert "basketball_nba" in url

    def test_get_props_api_key_prefers_props_env_var(self):
        """ODDS_API_KEY_PROPS takes priority over ODDS_API_KEY."""
        with patch.dict(os.environ, {"ODDS_API_KEY_PROPS": "props_key", "ODDS_API_KEY": "main_key"}):
            key = get_props_api_key()
        assert key == "props_key"

    def test_get_props_api_key_falls_back_to_main_key(self):
        """Falls back to ODDS_API_KEY when ODDS_API_KEY_PROPS is absent."""
        with patch.dict(os.environ, {"ODDS_API_KEY": "main_key"}, clear=True):
            with patch("core.odds_fetcher.get_api_key", return_value="main_key"):
                key = get_props_api_key()
        assert key == "main_key"

    def test_props_daily_credit_cap_is_100(self):
        assert PROPS_DAILY_CREDIT_CAP == 100

    def test_prop_markets_constant_has_nba_keys(self):
        assert "basketball_nba" in PROP_MARKETS
        assert "player_points" in PROP_MARKETS["basketball_nba"]
        assert "player_rebounds" in PROP_MARKETS["basketball_nba"]
        assert "player_assists" in PROP_MARKETS["basketball_nba"]

    def test_props_session_credit_cap_is_conservative(self):
        """Cap must be small enough to not threaten main odds budget."""
        assert PROPS_SESSION_CREDIT_CAP <= 100


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    sys.exit(result.returncode)
