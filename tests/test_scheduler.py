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
    def test_successful_poll_updates_state(self):
        fake_data = {
            "NBA": [{"id": "game1"}, {"id": "game2"}],
            "NFL": [],
        }
        with patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot", return_value=[{}, {}]) as mock_log:
            trigger_poll_now()
            assert sched_mod._last_poll_time is not None
            assert sched_mod._last_poll_result["NBA"] == 2
            assert sched_mod._last_poll_result["NFL"] == 0
            # log_snapshot only called for sports with games
            assert mock_log.call_count == 1

    def test_empty_sport_not_logged(self):
        fake_data = {"NBA": [], "NFL": []}
        with patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot") as mock_log:
            trigger_poll_now()
            mock_log.assert_not_called()

    def test_exception_increments_error_count(self):
        with patch("core.scheduler.fetch_batch_odds", side_effect=RuntimeError("API down")):
            trigger_poll_now()
            assert sched_mod._poll_error_count == 1
            assert len(sched_mod._poll_errors) == 1

    def test_error_list_capped_at_10(self):
        with patch("core.scheduler.fetch_batch_odds", side_effect=RuntimeError("fail")):
            for _ in range(15):
                trigger_poll_now()
        assert len(sched_mod._poll_errors) == 10

    def test_exception_does_not_raise(self):
        """Errors must be swallowed so APScheduler keeps running."""
        with patch("core.scheduler.fetch_batch_odds", side_effect=Exception("boom")):
            trigger_poll_now()  # must not raise


# ---------------------------------------------------------------------------
# trigger_poll_now
# ---------------------------------------------------------------------------
class TestTriggerPollNow:
    def test_returns_result_summary(self):
        fake_data = {"NBA": [{"id": "g1"}]}
        with patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
             patch("core.scheduler.log_snapshot", return_value=[{}]):
            result = trigger_poll_now()
            assert result == {"NBA": 1}

    def test_uses_db_path_override(self):
        with patch("core.scheduler.fetch_batch_odds", return_value={}), \
             patch("core.scheduler._poll_all_sports") as mock_poll:
            trigger_poll_now(db_path="/tmp/override.db")
            mock_poll.assert_called_once_with("/tmp/override.db")

    def test_returns_empty_on_error(self):
        with patch("core.scheduler.fetch_batch_odds", side_effect=RuntimeError("fail")):
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
        with patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
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
        with patch("core.scheduler.fetch_batch_odds", return_value=fake_data), \
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
