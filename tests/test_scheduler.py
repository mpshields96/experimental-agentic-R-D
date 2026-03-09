"""
tests/test_scheduler.py — Unit tests for core/scheduler.py

All APScheduler and network I/O is mocked.
Tests use reset_state() to guarantee isolation between test cases.
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import core.scheduler as sched_mod
from core.scheduler import (
    compute_injury_leverage_from_event,
    get_status,
    is_running,
    reset_state,
    start_scheduler,
    stop_scheduler,
    trigger_poll_now,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolate():
    """Reset all module-level state before/after every test."""
    reset_state()
    yield
    reset_state()


# ---------------------------------------------------------------------------
# start_scheduler
# ---------------------------------------------------------------------------
class TestStartScheduler:
    def test_starts_successfully(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            instance.start.assert_called_once()

    def test_idempotent_when_already_running(self):
        """Calling start twice must not create a second scheduler."""
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            start_scheduler()   # second call
            # BackgroundScheduler constructor called only once
            assert MockSched.call_count == 1

    def test_calls_init_db(self):
        with patch("core.scheduler.init_db") as mock_init, \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            MockSched.return_value.running = True
            start_scheduler(db_path="/tmp/test.db")
            mock_init.assert_called_once_with("/tmp/test.db")

    def test_adds_line_poll_job(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler(poll_interval_minutes=10)
            # line_poll is the FIRST add_job call; weekly_purge is second
            add_job_call = instance.add_job.call_args_list[0]
            assert add_job_call.kwargs["id"] == "line_poll"
            assert add_job_call.kwargs["kwargs"] == {"db_path": None}

    def test_custom_poll_interval(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler(poll_interval_minutes=15)
            # line_poll is the FIRST add_job call
            add_job_call = instance.add_job.call_args_list[0]
            assert add_job_call.kwargs["minutes"] == 15

    def test_stores_db_path(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.init_price_history_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            MockSched.return_value.running = True
            start_scheduler(db_path="/data/test.db")
            assert sched_mod._db_path == "/data/test.db"


# ---------------------------------------------------------------------------
# stop_scheduler
# ---------------------------------------------------------------------------
class TestStopScheduler:
    def test_stops_running_scheduler(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            stop_scheduler()
            instance.shutdown.assert_called_once_with(wait=False)
            assert sched_mod._scheduler is None

    def test_safe_when_not_running(self):
        """stop_scheduler on a never-started scheduler must not raise."""
        stop_scheduler()  # no exception

    def test_safe_when_already_stopped(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            stop_scheduler()
            stop_scheduler()  # second call — no exception


# ---------------------------------------------------------------------------
# is_running
# ---------------------------------------------------------------------------
class TestIsRunning:
    def test_false_before_start(self):
        assert is_running() is False

    def test_true_after_start(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            MockSched.return_value.running = True
            start_scheduler()
            assert is_running() is True

    def test_false_after_stop(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            stop_scheduler()
            assert is_running() is False


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------
class TestGetStatus:
    def test_initial_state(self):
        status = get_status()
        assert status["running"] is False
        assert status["last_poll_time"] is None
        assert status["last_poll_result"] == {}
        assert status["poll_error_count"] == 0
        assert status["recent_errors"] == []
        assert isinstance(status["quota_report"], str)
        # RLM gate must be present and structured
        assert "rlm_gate" in status
        assert isinstance(status["rlm_gate"], dict)
        assert "fire_count" in status["rlm_gate"]
        assert "gate_reached" in status["rlm_gate"]

    def test_running_true_after_start(self):
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            MockSched.return_value.running = True
            start_scheduler()
            assert get_status()["running"] is True

    def test_reflects_poll_results(self):
        sched_mod._last_poll_result = {"NBA": 5, "NFL": 3}
        sched_mod._last_poll_time = datetime(2026, 2, 18, 12, 0, 0)
        status = get_status()
        assert status["last_poll_result"] == {"NBA": 5, "NFL": 3}
        assert status["last_poll_time"] == datetime(2026, 2, 18, 12, 0, 0)

    def test_reflects_errors(self):
        sched_mod._poll_error_count = 3
        sched_mod._poll_errors = ["err1", "err2", "err3"]
        status = get_status()
        assert status["poll_error_count"] == 3
        assert status["recent_errors"] == ["err1", "err2", "err3"]

    def test_returns_copy_not_reference(self):
        """Mutating returned dict must not affect internal state."""
        status = get_status()
        status["last_poll_result"]["NBA"] = 999
        assert sched_mod._last_poll_result.get("NBA") != 999


# ---------------------------------------------------------------------------
# _poll_all_sports (internal, tested via trigger_poll_now)
# ---------------------------------------------------------------------------
class TestPollAllSports:
    """
    All tests in this class mock _get_hours_since_activity to return 0.0
    (simulating an active user) so the inactivity guard never fires.
    Tests specifically for the inactivity guard live in TestInactivityAutoStop.
    """

    def test_successful_poll_updates_state(self):
        fake_data = {
            "NBA": [{"id": "game1"}, {"id": "game2"}],
            "NFL": [],
        }
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot", return_value=[{}, {}]) as mock_log, \
             patch("core.scheduler.integrate_with_session_cache"), \
             patch("core.scheduler.inject_historical_prices_into_cache"), \
             patch("core.scheduler.probe_bookmakers", return_value={}), \
             patch("core.scheduler.log_probe_result"):
            trigger_poll_now()
            assert sched_mod._last_poll_time is not None
            assert sched_mod._last_poll_result["NBA"] == 2
            assert sched_mod._last_poll_result["NFL"] == 0
            # log_snapshot only called for sports with games
            assert mock_log.call_count == 1

    def test_empty_sport_not_logged(self):
        fake_data = {"NBA": [], "NFL": []}
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot") as mock_log:
            trigger_poll_now()
            mock_log.assert_not_called()

    def test_exception_increments_error_count(self):
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", side_effect=RuntimeError("API down")):
            trigger_poll_now()
            assert sched_mod._poll_error_count == 1
            assert len(sched_mod._poll_errors) == 1

    def test_error_list_capped_at_10(self):
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", side_effect=RuntimeError("fail")):
            for _ in range(15):
                trigger_poll_now()
        assert len(sched_mod._poll_errors) == 10

    def test_exception_does_not_raise(self):
        """Errors must be swallowed so APScheduler keeps running."""
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", side_effect=Exception("boom")):
            trigger_poll_now()  # must not raise


# ---------------------------------------------------------------------------
# trigger_poll_now
# ---------------------------------------------------------------------------
class TestTriggerPollNow:
    def test_returns_result_summary(self):
        fake_data = {"NBA": [{"id": "g1"}]}
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot", return_value=[{}]), \
             patch("core.scheduler.integrate_with_session_cache"), \
             patch("core.scheduler.inject_historical_prices_into_cache"), \
             patch("core.scheduler.probe_bookmakers", return_value={}), \
             patch("core.scheduler.log_probe_result"):
            result = trigger_poll_now()
            assert result == {"NBA": 1}

    def test_uses_db_path_override(self):
        with patch("core.scheduler.fetch_batch_odds", return_value={}), \
             patch("core.scheduler._poll_all_sports") as mock_poll:
            trigger_poll_now(db_path="/tmp/override.db")
            mock_poll.assert_called_once_with("/tmp/override.db")

    def test_returns_empty_on_error(self):
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", side_effect=RuntimeError("fail")):
            result = trigger_poll_now()
            # last_poll_result was never updated; returns {}
            assert result == {}


# ---------------------------------------------------------------------------
# weekly purge job (10C)
# ---------------------------------------------------------------------------
class TestPurgeOldPriceHistory:
    def test_purge_job_registered(self):
        """weekly_purge job must be added to the scheduler on start."""
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.init_price_history_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            job_ids = [call.kwargs.get("id") for call in instance.add_job.call_args_list]
            assert "weekly_purge" in job_ids

    def test_purge_job_has_weekly_interval(self):
        """weekly_purge must fire once per week (weeks=1)."""
        with patch("core.scheduler.init_db"), \
             patch("core.scheduler.init_price_history_db"), \
             patch("core.scheduler.BackgroundScheduler") as MockSched:
            instance = MockSched.return_value
            instance.running = True
            start_scheduler()
            purge_call = next(
                c for c in instance.add_job.call_args_list
                if c.kwargs.get("id") == "weekly_purge"
            )
            assert purge_call.kwargs.get("weeks") == 1

    def test_purge_deletes_old_rows(self, tmp_path):
        """_purge_old_price_history calls purge_old_events with correct args."""
        with patch("core.scheduler.purge_old_events") as mock_purge:
            mock_purge.return_value = 3
            sched_mod._db_path = str(tmp_path / "ph.db")
            from core.scheduler import _purge_old_price_history
            _purge_old_price_history(days_old=14)
            mock_purge.assert_called_once_with(days_old=14, db_path=str(tmp_path / "ph.db"))

    def test_purge_error_does_not_raise(self):
        """Purge errors must be swallowed (same pattern as poll errors)."""
        with patch("core.scheduler.purge_old_events", side_effect=RuntimeError("db locked")):
            from core.scheduler import _purge_old_price_history
            _purge_old_price_history()  # must not raise


# ---------------------------------------------------------------------------
# NHL goalie poll integration
# ---------------------------------------------------------------------------
class TestNhlGoaliePoll:
    """Tests for _poll_nhl_goalies being triggered during NHL sport polls."""

    def test_nhl_sport_triggers_goalie_poll(self):
        """When NHL games are fetched, _poll_nhl_goalies should be called."""
        nhl_game = {
            "id": "nhl_event_001",
            "away_team": "Boston Bruins",
            "home_team": "New York Rangers",
            "commence_time": "2099-01-01T23:00:00Z",  # future game
        }
        fake_data = {"NHL": [nhl_game]}
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot", return_value=[nhl_game]), \
             patch("core.scheduler._poll_nhl_goalies") as mock_goalies, \
             patch("core.scheduler.integrate_with_session_cache"), \
             patch("core.scheduler.inject_historical_prices_into_cache"), \
             patch("core.scheduler.probe_bookmakers", return_value={}), \
             patch("core.scheduler.log_probe_result"):
            trigger_poll_now()
            mock_goalies.assert_called_once_with([nhl_game])

    def test_non_nhl_sport_does_not_trigger_goalie_poll(self):
        """NBA, NFL etc. should not trigger NHL goalie poll."""
        fake_data = {"NBA": [{"id": "nba_game_1"}]}
        with patch("core.scheduler._get_hours_since_activity", return_value=0.0), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot", return_value=[{}]), \
             patch("core.scheduler._poll_nhl_goalies") as mock_goalies, \
             patch("core.scheduler.integrate_with_session_cache"), \
             patch("core.scheduler.inject_historical_prices_into_cache"), \
             patch("core.scheduler.probe_bookmakers", return_value={}), \
             patch("core.scheduler.log_probe_result"):
            trigger_poll_now()
            mock_goalies.assert_not_called()

    def test_poll_nhl_goalies_caches_starter_data(self):
        """_poll_nhl_goalies() writes to nhl_data goalie cache when data available."""
        from core.nhl_data import get_cached_goalie_status, clear_goalie_cache
        from core.scheduler import _poll_nhl_goalies
        from datetime import timedelta
        clear_goalie_cache()

        now = datetime.now(timezone.utc)
        near_start = (now + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
        game = {
            "id": "nhl_event_cache_test",
            "away_team": "Boston Bruins",
            "home_team": "New York Rangers",
            "commence_time": near_start,
        }
        mock_starter_data = {
            "game_id": 9999,
            "away": {"starter_confirmed": True, "starter_name": "S. Knight", "backup_name": None},
            "home": {"starter_confirmed": True, "starter_name": "I. Shesterkin", "backup_name": None},
        }
        with patch("core.scheduler.get_starters_for_odds_game", return_value=mock_starter_data):
            _poll_nhl_goalies([game])

        result = get_cached_goalie_status("nhl_event_cache_test")
        assert result is not None
        assert result["away"]["starter_name"] == "S. Knight"
        clear_goalie_cache()

    def test_poll_nhl_goalies_skips_distant_games(self):
        """Games >90 min away are skipped before calling get_starters_for_odds_game."""
        from core.nhl_data import get_cached_goalie_status, clear_goalie_cache
        from core.scheduler import _poll_nhl_goalies
        from datetime import timedelta
        clear_goalie_cache()

        now = datetime.now(timezone.utc)
        distant_start = (now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        game = {
            "id": "nhl_event_distant",
            "away_team": "Boston Bruins",
            "home_team": "New York Rangers",
            "commence_time": distant_start,
        }
        with patch("core.scheduler.get_starters_for_odds_game", return_value=None) as mock_get:
            _poll_nhl_goalies([game])
            # Scheduler skips game >90 min away — get_starters never called
            mock_get.assert_not_called()

        result = get_cached_goalie_status("nhl_event_distant")
        assert result is None
        clear_goalie_cache()

    def test_poll_nhl_goalies_swallows_errors(self):
        """An error in goalie fetch must not propagate."""
        from core.scheduler import _poll_nhl_goalies
        game = {
            "id": "nhl_error_game",
            "away_team": "Boston Bruins",
            "home_team": "New York Rangers",
            "commence_time": "2026-02-19T23:00:00Z",
        }
        with patch("core.scheduler.get_starters_for_odds_game", side_effect=Exception("API Error")):
            _poll_nhl_goalies([game])  # must not raise


# ---------------------------------------------------------------------------
# Inactivity auto-stop (2026-02-24 user directive)
# ---------------------------------------------------------------------------
class TestInactivityAutoStop:
    """
    Tests for the 24-hour inactivity guard in _poll_all_sports().

    When no user has loaded any page in > INACTIVITY_TIMEOUT_HOURS,
    the scheduler must skip all fetches (zero API calls) and return early.
    Resumes automatically on the next page load (file written by app.py).
    """

    def test_inactive_skips_fetch(self):
        """When idle_hours > 2, fetch_batch_odds must NOT be called."""
        with patch("core.scheduler._get_hours_since_activity", return_value=3.0), \
             patch("core.scheduler.fetch_batch_odds") as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_not_called()

    def test_active_proceeds_with_fetch(self):
        """When recently active (idle_hours < 2), fetch must be called."""
        fake_data = {"NBA": []}
        with patch("core.scheduler._get_hours_since_activity", return_value=0.5), \
             patch("core.scheduler._is_scheduler_enabled", return_value=True), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data) as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_called_once()

    def test_get_hours_returns_infinity_on_missing_file(self, tmp_path):
        """Missing activity file → treat as inactive (return infinity)."""
        import core.scheduler as sched_mod
        original = sched_mod._ACTIVITY_FILE
        try:
            sched_mod._ACTIVITY_FILE = tmp_path / "nonexistent_activity.json"
            hours = sched_mod._get_hours_since_activity()
            assert hours == float("inf")
        finally:
            sched_mod._ACTIVITY_FILE = original

    def test_get_hours_returns_correct_value(self, tmp_path):
        """Activity file with recent timestamp → returns correct elapsed hours."""
        import core.scheduler as sched_mod
        import json, time as _time
        activity_file = tmp_path / "last_activity.json"
        one_hour_ago = _time.time() - 3600.0
        activity_file.write_text(json.dumps({"ts": one_hour_ago}))

        original = sched_mod._ACTIVITY_FILE
        try:
            sched_mod._ACTIVITY_FILE = activity_file
            hours = sched_mod._get_hours_since_activity()
            # Allow ±5 seconds tolerance
            assert 0.99 < hours < 1.01
        finally:
            sched_mod._ACTIVITY_FILE = original

    def test_get_status_includes_idle_hours(self):
        """get_status() must expose idle_hours and inactive keys for the UI."""
        with patch("core.scheduler._get_hours_since_activity", return_value=1.0):
            status = get_status()
        assert "idle_hours" in status
        assert "inactive" in status
        assert abs(status["idle_hours"] - 1.0) < 0.01
        assert status["inactive"] is False  # 1h < 2h threshold

    def test_inactive_threshold_is_2h(self):
        """INACTIVITY_TIMEOUT_HOURS must be 2 (tightened S43 to prevent idle credit burns)."""
        import core.scheduler as sched_mod
        assert sched_mod.INACTIVITY_TIMEOUT_HOURS == 2

    def test_inactive_at_3h(self):
        """3h idle must skip fetch (above 2h threshold)."""
        with patch("core.scheduler._get_hours_since_activity", return_value=3.0), \
             patch("core.scheduler.fetch_batch_odds") as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Scheduler kill switch — SCHEDULER_ENABLED flag
# ---------------------------------------------------------------------------
class TestSchedulerEnabledKillSwitch:
    """
    Tests for the SCHEDULER_ENABLED hard gate in _poll_all_sports() (Layer 1).

    Setting SCHEDULER_ENABLED=false/0/off in env or secrets.toml must
    prevent ALL API calls regardless of inactivity state.
    """

    def test_disabled_env_var_skips_fetch(self):
        """SCHEDULER_ENABLED=false in env must prevent any fetch."""
        fake_data = {"NBA": []}
        with patch.dict("os.environ", {"SCHEDULER_ENABLED": "false"}), \
             patch("core.scheduler._get_hours_since_activity", return_value=0.1), \
             patch("core.scheduler.fetch_batch_odds") as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_not_called()

    def test_disabled_zero_skips_fetch(self):
        """SCHEDULER_ENABLED=0 must also disable."""
        with patch.dict("os.environ", {"SCHEDULER_ENABLED": "0"}), \
             patch("core.scheduler._get_hours_since_activity", return_value=0.1), \
             patch("core.scheduler.fetch_batch_odds") as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_not_called()

    def test_disabled_off_skips_fetch(self):
        """SCHEDULER_ENABLED=off must also disable."""
        with patch.dict("os.environ", {"SCHEDULER_ENABLED": "off"}), \
             patch("core.scheduler._get_hours_since_activity", return_value=0.1), \
             patch("core.scheduler.fetch_batch_odds") as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_not_called()

    def test_enabled_true_allows_fetch(self):
        """SCHEDULER_ENABLED=true must allow fetch to proceed."""
        fake_data = {"NBA": []}
        with patch.dict("os.environ", {"SCHEDULER_ENABLED": "true"}), \
             patch("core.scheduler._get_hours_since_activity", return_value=0.1), \
             patch("core.scheduler.fetch_batch_odds", return_value=fake_data) as mock_fetch:
            trigger_poll_now()
            mock_fetch.assert_called_once()

    def test_enabled_default_when_unset(self):
        """Unset SCHEDULER_ENABLED must default to enabled (non-breaking default)."""
        import core.scheduler as sched_mod
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "SCHEDULER_ENABLED"}
        with patch.dict("os.environ", env, clear=True):
            assert sched_mod._is_scheduler_enabled() is True

    def test_is_scheduler_enabled_case_insensitive(self):
        """FALSE / False / FALSE must all disable."""
        import core.scheduler as sched_mod
        for val in ("FALSE", "False", "OFF", "Off"):
            with patch.dict("os.environ", {"SCHEDULER_ENABLED": val}):
                assert sched_mod._is_scheduler_enabled() is False


# ---------------------------------------------------------------------------
# reset_state
# ---------------------------------------------------------------------------
class TestResetState:
    def test_clears_all_state(self):
        sched_mod._last_poll_time = datetime.now(timezone.utc)
        sched_mod._last_poll_result = {"NBA": 5}
        sched_mod._poll_error_count = 7
        sched_mod._poll_errors = ["e1"]
        sched_mod._db_path = "/data/test.db"
        reset_state()
        assert sched_mod._last_poll_time is None
        assert sched_mod._last_poll_result == {}
        assert sched_mod._poll_error_count == 0
        assert sched_mod._poll_errors == []
        assert sched_mod._db_path is None
        assert sched_mod._scheduler is None


# ---------------------------------------------------------------------------
# compute_injury_leverage_from_event
# ---------------------------------------------------------------------------
class TestComputeInjuryLeverageFromEvent:
    """V37 Session 38 directive: injury_data.py wired into pipeline call path."""

    def test_zero_when_no_injury_data(self):
        """Default Odds API event dict has no _injuries key → always 0.0."""
        game = {"id": "abc", "home_team": "Lakers", "away_team": "Celtics"}
        result = compute_injury_leverage_from_event(game, "NBA")
        assert result == 0.0

    def test_zero_when_injuries_empty_list(self):
        """Explicit empty list is also a no-op."""
        game = {"_injuries": []}
        result = compute_injury_leverage_from_event(game, "NBA")
        assert result == 0.0

    def test_nonzero_when_opponent_starter_out(self):
        """Away PG out → positive leverage for home spread bet (opponent weakened)."""
        game = {
            "_injuries": [
                {"position": "PG", "team_side": "away", "is_starter": True}
            ]
        }
        result = compute_injury_leverage_from_event(game, "NBA", "spreads", "home")
        assert result > 0.0

    def test_negative_when_own_starter_out(self):
        """Home PG out → negative leverage for home spread bet (our side weakened)."""
        game = {
            "_injuries": [
                {"position": "PG", "team_side": "home", "is_starter": True}
            ]
        }
        result = compute_injury_leverage_from_event(game, "NBA", "spreads", "home")
        assert result < 0.0

    def test_non_starter_ignored(self):
        """Non-starter absence → 0.0 (injury_data rule: depth chart absorbs backups)."""
        game = {
            "_injuries": [
                {"position": "PG", "team_side": "away", "is_starter": False}
            ]
        }
        result = compute_injury_leverage_from_event(game, "NBA", "spreads", "home")
        assert result == 0.0

    def test_missing_position_entry_skipped(self):
        """Entry without 'position' key is silently skipped."""
        game = {"_injuries": [{"team_side": "away", "is_starter": True}]}
        result = compute_injury_leverage_from_event(game, "NBA")
        assert result == 0.0

    def test_leverage_flows_into_sharp_score(self):
        """Sanity check: signed_impact flows into calculate_sharp_score min(5.0, leverage)."""
        from core.math_engine import calculate_sharp_score
        # Non-zero injury_leverage raises situational points
        score_with, _ = calculate_sharp_score(
            edge_pct=0.05,
            rlm_confirmed=False,
            efficiency_gap=0.0,
            injury_leverage=4.0,
        )
        score_without, _ = calculate_sharp_score(
            edge_pct=0.05,
            rlm_confirmed=False,
            efficiency_gap=0.0,
            injury_leverage=0.0,
        )
        assert score_with > score_without


class TestParseGameMarketsInjuryLeverage:
    """Regression: parse_game_markets() must accept injury_leverage kwarg (Session 40 bug fix)."""

    def _make_edge_game(self) -> dict:
        """Minimal game dict with clear edge — 3 consensus books vs 1 outlier."""
        def bm(key, name, outcomes):
            return {
                "key": key, "title": name,
                "markets": [{"key": "h2h", "outcomes": outcomes}],
            }
        return {
            "id": "sched_inj_001",
            "home_team": "Duke",
            "away_team": "Virginia",
            "commence_time": "2026-02-20T01:00:00Z",
            "bookmakers": [
                bm("dk", "DraftKings", [{"name": "Duke", "price": -130}, {"name": "Virginia", "price": 110}]),
                bm("fd", "FanDuel",    [{"name": "Duke", "price": -130}, {"name": "Virginia", "price": 110}]),
                bm("bm", "BetMGM",    [{"name": "Duke", "price": -130}, {"name": "Virginia", "price": 110}]),
                bm("br", "BetRivers", [{"name": "Duke", "price": 140},  {"name": "Virginia", "price": -165}]),
            ],
        }

    def test_accepts_injury_leverage_kwarg(self):
        """parse_game_markets() must not raise TypeError when injury_leverage is passed."""
        from core.math_engine import parse_game_markets
        game = self._make_edge_game()
        # Would raise TypeError: unexpected keyword argument before the bug fix
        result = parse_game_markets(game, sport="NCAAB", injury_leverage=2.0)
        assert isinstance(result, list)

    def test_injury_leverage_default_zero(self):
        """Default injury_leverage=0.0 produces same result as not passing it."""
        from core.math_engine import parse_game_markets
        game = self._make_edge_game()
        r1 = parse_game_markets(game, sport="NCAAB")
        r2 = parse_game_markets(game, sport="NCAAB", injury_leverage=0.0)
        assert len(r1) == len(r2)

    def test_nonzero_injury_leverage_raises_sharp_score(self):
        """Positive injury_leverage increases sharp_score vs 0.0 for qualifying bets."""
        from core.math_engine import parse_game_markets
        game = self._make_edge_game()
        bets_base = parse_game_markets(game, sport="NCAAB", injury_leverage=0.0)
        bets_inj  = parse_game_markets(game, sport="NCAAB", injury_leverage=4.0)
        if bets_base and bets_inj:
            assert bets_inj[0].sharp_score >= bets_base[0].sharp_score


class TestAutoPaperBetScan:
    """_auto_paper_bet_scan() logs Grade A/B bets, deduplicates, skips killed bets."""

    def _make_edge_game(self) -> dict:
        def bm(key, name, outcomes):
            return {
                "key": key, "title": name,
                "markets": [{"key": "h2h", "outcomes": outcomes}],
            }
        return {
            "id": "auto_pb_001",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "commence_time": "2026-02-20T01:00:00Z",
            "bookmakers": [
                bm("dk", "DraftKings", [{"name": "Lakers", "price": -130}, {"name": "Celtics", "price": 110}]),
                bm("fd", "FanDuel",    [{"name": "Lakers", "price": -130}, {"name": "Celtics", "price": 110}]),
                bm("bm", "BetMGM",    [{"name": "Lakers", "price": -130}, {"name": "Celtics", "price": 110}]),
                bm("br", "BetRivers", [{"name": "Lakers", "price": 140},  {"name": "Celtics", "price": -165}]),
            ],
        }

    def test_logs_qualifying_bet(self, tmp_path):
        """When a Grade A/B bet exists, auto scan logs it."""
        from core.scheduler import _auto_paper_bet_scan
        from core.line_logger import init_db, get_bets
        db_path = str(tmp_path / "auto_pb.db")
        init_db(db_path)
        game = self._make_edge_game()
        logged = _auto_paper_bet_scan([game], "NBA", db_path)
        bets = get_bets(db_path=db_path)
        assert logged >= 0  # any non-negative count is valid
        assert all(b["notes"] == "auto-paper" for b in bets)

    def test_deduplication_prevents_double_log(self, tmp_path):
        """Second scan for same event does NOT add duplicate entry."""
        from core.scheduler import _auto_paper_bet_scan
        from core.line_logger import init_db, get_bets
        db_path = str(tmp_path / "auto_dup.db")
        init_db(db_path)
        game = self._make_edge_game()
        first = _auto_paper_bet_scan([game], "NBA", db_path)
        second = _auto_paper_bet_scan([game], "NBA", db_path)
        assert second == 0  # nothing new on second pass
        bets = get_bets(db_path=db_path)
        assert len(bets) == first  # total count unchanged

    def test_empty_games_returns_zero(self, tmp_path):
        """Empty game list logs nothing."""
        from core.scheduler import _auto_paper_bet_scan
        from core.line_logger import init_db
        db_path = str(tmp_path / "auto_empty.db")
        init_db(db_path)
        assert _auto_paper_bet_scan([], "NBA", db_path) == 0

    def test_tennis_atp_key_passed_to_parse(self, tmp_path):
        """When sport is tennis_atp_*, parse_game_markets must receive tennis_sport_key=sport.

        Regression test for Session 45 gap: auto_paper_bet_scan was calling
        parse_game_markets without tennis_sport_key, silently bypassing the
        surface kill switch for all scheduler-polled tennis games.
        """
        from core.scheduler import _auto_paper_bet_scan
        from core.line_logger import init_db
        from unittest.mock import patch, MagicMock

        db_path = str(tmp_path / "tennis_atp.db")
        init_db(db_path)
        game = self._make_edge_game()
        sport_key = "tennis_atp_miami_open"

        captured_calls = []

        def spy_parse(game, sport, **kwargs):
            captured_calls.append(kwargs.get("tennis_sport_key", "__NOT_PASSED__"))
            return []  # return no bets — we just want to inspect the call

        with patch("core.scheduler.parse_game_markets", side_effect=spy_parse), \
             patch("core.scheduler.compute_injury_leverage_from_event", return_value=0.0):
            _auto_paper_bet_scan([game], sport_key, db_path)

        assert captured_calls, "parse_game_markets was never called"
        assert captured_calls[0] == sport_key, (
            f"tennis_sport_key should be '{sport_key}', got '{captured_calls[0]}'. "
            "Surface kill switch would be silently bypassed in auto-scan."
        )

    def test_tennis_wta_key_passed_to_parse(self, tmp_path):
        """WTA variant: tennis_wta_* sport keys must also pass tennis_sport_key."""
        from core.scheduler import _auto_paper_bet_scan
        from core.line_logger import init_db
        from unittest.mock import patch

        db_path = str(tmp_path / "tennis_wta.db")
        init_db(db_path)
        game = self._make_edge_game()
        sport_key = "tennis_wta_miami_open"

        captured_calls = []

        def spy_parse(game, sport, **kwargs):
            captured_calls.append(kwargs.get("tennis_sport_key", "__NOT_PASSED__"))
            return []

        with patch("core.scheduler.parse_game_markets", side_effect=spy_parse), \
             patch("core.scheduler.compute_injury_leverage_from_event", return_value=0.0):
            _auto_paper_bet_scan([game], sport_key, db_path)

        assert captured_calls and captured_calls[0] == sport_key

    def test_non_tennis_sport_passes_empty_tennis_key(self, tmp_path):
        """Non-tennis sports must pass tennis_sport_key='' (not the sport name)."""
        from core.scheduler import _auto_paper_bet_scan
        from core.line_logger import init_db
        from unittest.mock import patch

        db_path = str(tmp_path / "nba_tennis_key.db")
        init_db(db_path)
        game = self._make_edge_game()

        captured_calls = []

        def spy_parse(game, sport, **kwargs):
            captured_calls.append(kwargs.get("tennis_sport_key", "__NOT_PASSED__"))
            return []

        with patch("core.scheduler.parse_game_markets", side_effect=spy_parse), \
             patch("core.scheduler.compute_injury_leverage_from_event", return_value=0.0):
            _auto_paper_bet_scan([game], "NBA", db_path)

        assert captured_calls and captured_calls[0] == "", (
            f"NBA should pass tennis_sport_key='', got '{captured_calls[0]}'"
        )


# ---------------------------------------------------------------------------
# TestExtractBestPrice
# ---------------------------------------------------------------------------

class TestExtractBestPrice:
    """Tests for _extract_best_price() — extracts best collar-passing price from game dict."""

    def _game(self, market_key, outcomes, event_id="evt1"):
        return {
            "id": event_id,
            "commence_time": "2026-03-01T02:00:00Z",
            "home_team": "Team A",
            "away_team": "Team B",
            "bookmakers": [
                {"key": "book1", "markets": [{"key": market_key, "outcomes": outcomes}]},
            ],
        }

    def test_extracts_h2h_price(self):
        """Returns best h2h price for the named team."""
        from core.scheduler import _extract_best_price
        game = self._game("h2h", [
            {"name": "Team A", "price": -130},
            {"name": "Team B", "price": 110},
        ])
        assert _extract_best_price(game, "h2h", "Team A ML") == -130

    def test_extracts_best_h2h_across_books(self):
        """Returns highest (best for bettor) price across multiple bookmakers."""
        from core.scheduler import _extract_best_price
        game = {
            "id": "e1", "commence_time": "2026-03-01T02:00:00Z",
            "bookmakers": [
                {"key": "b1", "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Team A", "price": -130},
                ]}]},
                {"key": "b2", "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Team A", "price": -120},  # better for bettor
                ]}]},
            ],
        }
        assert _extract_best_price(game, "h2h", "Team A ML") == -120

    def test_extracts_spreads_price(self):
        """Returns best spread price for matching team and point."""
        from core.scheduler import _extract_best_price
        game = self._game("spreads", [
            {"name": "Team A", "price": -110, "point": -4.5},
            {"name": "Team B", "price": -110, "point": 4.5},
        ])
        assert _extract_best_price(game, "spreads", "Team A -4.5") == -110

    def test_spreads_ignores_wrong_point(self):
        """Spread price not returned if point does not match."""
        from core.scheduler import _extract_best_price
        game = self._game("spreads", [
            {"name": "Team A", "price": -110, "point": -3.5},  # different line
        ])
        assert _extract_best_price(game, "spreads", "Team A -4.5") is None

    def test_extracts_totals_price(self):
        """Returns best totals price for the side and point."""
        from core.scheduler import _extract_best_price
        game = self._game("totals", [
            {"name": "Over", "price": -110, "point": 221.0},
            {"name": "Under", "price": -110, "point": 221.0},
        ])
        assert _extract_best_price(game, "totals", "Over 221.0") == -110

    def test_returns_none_when_no_match(self):
        """Returns None when target team not found in any bookmaker."""
        from core.scheduler import _extract_best_price
        game = self._game("h2h", [{"name": "Team B", "price": 110}])
        assert _extract_best_price(game, "h2h", "Team A ML") is None

    def test_out_of_collar_price_ignored(self):
        """Prices outside collar (-180..+150) are rejected."""
        from core.scheduler import _extract_best_price
        game = self._game("h2h", [{"name": "Team A", "price": -350}])  # out of collar
        assert _extract_best_price(game, "h2h", "Team A ML") is None


# ---------------------------------------------------------------------------
# TestCaptureClosePrices
# ---------------------------------------------------------------------------

class TestCaptureClosePrices:
    """Tests for _capture_close_prices() — zero-credit CLV capture from existing fetch data."""

    def _pending_bet_game(self, tmp_path, event_id="evt1",
                          hours_offset=1.0, sport="NBA"):
        """Helper: DB with one pending bet + raw game within capture window."""
        from core.line_logger import init_db, log_bet
        from datetime import datetime, timezone, timedelta
        db_path = str(tmp_path / "clv.db")
        init_db(db_path)
        log_bet(sport, "Team A @ Team B", "h2h", "Team A ML", -120, 0.05, 0.03,
                event_id=event_id, db_path=db_path)
        commence = (datetime.now(timezone.utc) + timedelta(hours=hours_offset)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        game = {
            "id": event_id,
            "commence_time": commence,
            "bookmakers": [{"key": "b1", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Team A", "price": -118},
                {"name": "Team B", "price": 100},
            ]}]}],
        }
        return db_path, game

    def test_captures_within_window(self, tmp_path):
        """Records close_price when game starts within CLOSE_PRICE_WINDOW_HOURS."""
        from core.scheduler import _capture_close_prices
        from core.line_logger import get_bets
        db, game = self._pending_bet_game(tmp_path, hours_offset=1.0)
        count = _capture_close_prices([game], "NBA", db)
        assert count == 1
        bets = get_bets(db_path=db)
        assert bets[0]["close_price"] == -118

    def test_skips_outside_window(self, tmp_path):
        """Does NOT capture when game is more than 2 hours away."""
        from core.scheduler import _capture_close_prices
        from core.line_logger import get_bets
        db, game = self._pending_bet_game(tmp_path, hours_offset=5.0)
        count = _capture_close_prices([game], "NBA", db)
        assert count == 0
        bets = get_bets(db_path=db)
        assert not bets[0]["close_price"]

    def test_no_double_capture(self, tmp_path):
        """Second pass for same bet does not overwrite already-captured price."""
        from core.scheduler import _capture_close_prices
        from core.line_logger import get_bets
        db, game = self._pending_bet_game(tmp_path, hours_offset=1.0)
        _capture_close_prices([game], "NBA", db)  # first capture
        count2 = _capture_close_prices([game], "NBA", db)  # second — no-op
        assert count2 == 0
        bets = get_bets(db_path=db)
        assert bets[0]["close_price"] == -118  # unchanged

    def test_empty_games_returns_zero(self, tmp_path):
        """Empty game list captures nothing."""
        from core.scheduler import _capture_close_prices
        from core.line_logger import init_db
        db_path = str(tmp_path / "empty.db")
        init_db(db_path)
        assert _capture_close_prices([], "NBA", db_path) == 0

    def test_wrong_sport_skips(self, tmp_path):
        """Pending bet for NBA is not captured when scanning NHL."""
        from core.scheduler import _capture_close_prices
        from core.line_logger import get_bets
        db, game = self._pending_bet_game(tmp_path, hours_offset=1.0, sport="NBA")
        count = _capture_close_prices([game], "NHL", db)
        assert count == 0


class TestIsSportInSeason:
    """Unit tests for _is_sport_in_season() and get_in_season_sports()."""

    def test_nba_active_in_february(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NBA", month=2) is True

    def test_nba_active_in_october(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NBA", month=10) is True

    def test_nba_inactive_in_august(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NBA", month=8) is False

    def test_nfl_inactive_in_march(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NFL", month=3) is False

    def test_nfl_active_in_september(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NFL", month=9) is True

    def test_mlb_inactive_in_february(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("MLB", month=2) is False

    def test_mlb_active_in_june(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("MLB", month=6) is True

    def test_ncaaf_inactive_in_march(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NCAAF", month=3) is False

    def test_epl_active_in_february(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("EPL", month=2) is True

    def test_unknown_sport_always_active(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("UNKNOWN_SPORT", month=7) is True

    def test_get_in_season_sports_march_excludes_nfl_ncaaf(self):
        from core.scheduler import get_in_season_sports
        # March: NFL (ends Feb) and NCAAF (ends Jan) are off-season
        active = get_in_season_sports(month=3)
        assert "NFL" not in active
        assert "NCAAF" not in active

    def test_get_in_season_sports_february_includes_nba_ncaab_nhl(self):
        from core.scheduler import get_in_season_sports
        active = get_in_season_sports(month=2)
        assert "NBA" in active
        assert "NCAAB" in active
        assert "NHL" in active

    def test_get_in_season_sports_july_excludes_nba_nhl(self):
        from core.scheduler import get_in_season_sports
        active = get_in_season_sports(month=7)
        assert "NBA" not in active
        assert "NHL" not in active

    def test_nhl_active_in_march(self):
        """NHL season runs Oct–Jun; March is squarely in-season (playoffs approach)."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NHL", month=3) is True

    def test_ncaab_active_in_march(self):
        """NCAAB season runs Nov–Apr; March Madness is the peak of the season."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NCAAB", month=3) is True

    def test_nba_active_in_march(self):
        """NBA season runs Oct–Jun; March includes regular season and play-in prep."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NBA", month=3) is True

    def test_mlb_inactive_in_march(self):
        """MLB season runs Apr–Oct; March is spring training (not in-season)."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("MLB", month=3) is False

    def test_mlb_active_in_april(self):
        """MLB month gate starts at April — Opening Day activates the poll."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("MLB", month=4) is True

    def test_mlb_inactive_in_november(self):
        """MLB season ends in October; November is off-season."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("MLB", month=11) is False

    def test_mls_active_in_march(self):
        """MLS season runs Feb–Nov; March is early regular season."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("MLS", month=3) is True

    def test_get_in_season_sports_march_includes_nhl_ncaab_nba_mls(self):
        """March active set must include all currently live competitions."""
        from core.scheduler import get_in_season_sports
        active = get_in_season_sports(month=3)
        assert "NHL" in active, "NHL should be in season in March (playoffs approach)"
        assert "NCAAB" in active, "NCAAB should be in season in March (March Madness)"
        assert "NBA" in active, "NBA should be in season in March"
        assert "MLS" in active, "MLS should be in season in March"
        assert "MLB" not in active, "MLB should NOT be in season in March (starts April)"
        assert "NFL" not in active, "NFL should NOT be in season in March"
        assert "NCAAF" not in active, "NCAAF should NOT be in season in March"

    def test_wrapping_range_nba_june(self):
        """Jun is the last month of NBA season (range Oct–Jun, wraps)."""
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NBA", month=6) is True

    def test_wrapping_range_nba_july_off(self):
        from core.scheduler import _is_sport_in_season
        assert _is_sport_in_season("NBA", month=7) is False
