"""
tests/test_nhl_data.py — Unit tests for core/nhl_data.py

All external HTTP calls are mocked — no real API hits.
Tests cover: team name normalization, schedule fetch, boxscore parsing,
FUT state (returns None), confirmed starters, timing gate, get_starters_for_odds_game.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.nhl_data import (
    normalize_team_name,
    get_nhl_game_ids_for_date,
    get_nhl_starters_for_game,
    get_starters_for_odds_game,
    _TEAM_NAME_MAP,
    _ABBREV_TO_FULL,
)


# ---------------------------------------------------------------------------
# Helper: build mock response
# ---------------------------------------------------------------------------

def make_response(data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


def make_boxscore_response(
    away_starters: list[dict],
    home_starters: list[dict],
    game_id: int = 12345,
) -> dict:
    """Build a minimal boxscore response with goalie data."""
    return {
        "id": game_id,
        "playerByGameStats": {
            "awayTeam": {
                "goalies": away_starters,
            },
            "homeTeam": {
                "goalies": home_starters,
            },
        },
    }


def make_schedule_response(
    date_str: str,
    games: list[dict],
) -> dict:
    return {
        "gameWeek": [
            {
                "date": date_str,
                "games": games,
            }
        ]
    }


def make_schedule_game(
    game_id: int,
    away: str,
    home: str,
    start_utc: str = "2026-02-19T23:00:00Z",
    state: str = "FUT",
) -> dict:
    return {
        "id": game_id,
        "awayTeam": {"abbrev": away},
        "homeTeam": {"abbrev": home},
        "startTimeUTC": start_utc,
        "gameState": state,
    }


# ---------------------------------------------------------------------------
# TestNormalizeTeamName
# ---------------------------------------------------------------------------

class TestNormalizeTeamName:
    def test_full_name(self):
        assert normalize_team_name("Boston Bruins") == "BOS"

    def test_full_name_case_insensitive(self):
        assert normalize_team_name("boston bruins") == "BOS"

    def test_abbrev_passthrough(self):
        assert normalize_team_name("BOS") == "BOS"

    def test_abbrev_lowercase(self):
        assert normalize_team_name("bos") == "BOS"

    def test_last_word_match(self):
        assert normalize_team_name("Bruins") == "BOS"

    def test_last_word_case_insensitive(self):
        assert normalize_team_name("bruins") == "BOS"

    def test_rangers(self):
        assert normalize_team_name("New York Rangers") == "NYR"

    def test_rangers_short(self):
        assert normalize_team_name("Rangers") == "NYR"

    def test_maple_leafs(self):
        assert normalize_team_name("Toronto Maple Leafs") == "TOR"

    def test_golden_knights(self):
        assert normalize_team_name("Vegas Golden Knights") == "VGK"

    def test_utah(self):
        assert normalize_team_name("Utah Hockey Club") == "UTA"

    def test_none_input(self):
        assert normalize_team_name("") is None

    def test_unknown_team(self):
        assert normalize_team_name("Fictional FC") is None

    def test_all_teams_in_map(self):
        """Every team in _TEAM_NAME_MAP should resolve correctly."""
        for full_name, abbrev in _TEAM_NAME_MAP.items():
            assert normalize_team_name(full_name) == abbrev

    def test_all_abbrevs_passthrough(self):
        for abbrev in _ABBREV_TO_FULL:
            assert normalize_team_name(abbrev) == abbrev

    def test_partial_substring(self):
        # "Lightning" should match Tampa Bay Lightning
        result = normalize_team_name("Lightning")
        assert result == "TBL"


# ---------------------------------------------------------------------------
# TestGetNhlGameIdsForDate
# ---------------------------------------------------------------------------

class TestGetNhlGameIdsForDate:
    def test_returns_games_list(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_schedule_response(
                "2026-02-19",
                [
                    make_schedule_game(1001, "BOS", "NYR"),
                    make_schedule_game(1002, "TOR", "MTL"),
                ]
            )
        )
        result = get_nhl_game_ids_for_date("2026-02-19", session=mock_sess)
        assert len(result) == 2
        assert result[0]["game_id"] == 1001
        assert result[0]["away_team"] == "BOS"
        assert result[0]["home_team"] == "NYR"
        assert result[0]["game_state"] == "FUT"

    def test_start_utc_parsed(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_schedule_response(
                "2026-02-19",
                [make_schedule_game(1001, "BOS", "NYR", start_utc="2026-02-19T23:00:00Z")]
            )
        )
        result = get_nhl_game_ids_for_date("2026-02-19", session=mock_sess)
        assert result[0]["game_start_utc"] is not None
        assert result[0]["game_start_utc"].tzinfo is not None

    def test_date_mismatch_returns_empty(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_schedule_response(
                "2026-02-20",  # different date than requested
                [make_schedule_game(1001, "BOS", "NYR")]
            )
        )
        result = get_nhl_game_ids_for_date("2026-02-19", session=mock_sess)
        assert result == []

    def test_api_error_returns_empty(self):
        mock_sess = MagicMock()
        mock_sess.get.side_effect = Exception("Connection error")
        result = get_nhl_game_ids_for_date("2026-02-19", session=mock_sess)
        assert result == []

    def test_empty_schedule_returns_empty(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response({"gameWeek": []})
        result = get_nhl_game_ids_for_date("2026-02-19", session=mock_sess)
        assert result == []

    def test_invalid_start_time_handled(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_schedule_response(
                "2026-02-19",
                [{
                    "id": 1001,
                    "awayTeam": {"abbrev": "BOS"},
                    "homeTeam": {"abbrev": "NYR"},
                    "startTimeUTC": "not-a-date",
                    "gameState": "FUT",
                }]
            )
        )
        result = get_nhl_game_ids_for_date("2026-02-19", session=mock_sess)
        assert result[0]["game_start_utc"] is None


# ---------------------------------------------------------------------------
# TestGetNhlStartersForGame
# ---------------------------------------------------------------------------

class TestGetNhlStartersForGame:
    def test_confirmed_starters_returned(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_boxscore_response(
                away_starters=[
                    {"name": {"default": "S. Knight"}, "starter": True},
                    {"name": {"default": "J. Backup"}, "starter": False},
                ],
                home_starters=[
                    {"name": {"default": "A. Soderblom"}, "starter": True},
                    {"name": {"default": "B. Reserve"}, "starter": False},
                ],
            )
        )
        result = get_nhl_starters_for_game(12345, session=mock_sess)
        assert result is not None
        assert result["game_id"] == 12345
        assert result["away"]["starter_confirmed"] is True
        assert result["away"]["starter_name"] == "S. Knight"
        assert result["away"]["backup_name"] == "J. Backup"
        assert result["home"]["starter_confirmed"] is True
        assert result["home"]["starter_name"] == "A. Soderblom"

    def test_fut_state_returns_none(self):
        """No playerByGameStats = FUT state = return None."""
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            {"id": 12345}  # no playerByGameStats
        )
        result = get_nhl_starters_for_game(12345, session=mock_sess)
        assert result is None

    def test_empty_goalies_returns_none(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response({
            "playerByGameStats": {
                "awayTeam": {"goalies": []},
                "homeTeam": {"goalies": [{"name": {"default": "G. Keeper"}, "starter": True}]},
            }
        })
        result = get_nhl_starters_for_game(12345, session=mock_sess)
        assert result is None

    def test_api_error_returns_none(self):
        mock_sess = MagicMock()
        mock_sess.get.side_effect = Exception("Timeout")
        result = get_nhl_starters_for_game(12345, session=mock_sess)
        assert result is None

    def test_no_starter_true_in_goalies(self):
        """If no goalie has starter=True, starter_confirmed=False."""
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_boxscore_response(
                away_starters=[
                    {"name": {"default": "G. One"}, "starter": False},
                    {"name": {"default": "G. Two"}, "starter": False},
                ],
                home_starters=[
                    {"name": {"default": "H. One"}, "starter": True},
                ],
            )
        )
        result = get_nhl_starters_for_game(12345, session=mock_sess)
        assert result is not None
        assert result["away"]["starter_confirmed"] is False
        assert result["away"]["starter_name"] is None
        assert result["home"]["starter_confirmed"] is True

    def test_backup_name_is_first_non_starter(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            make_boxscore_response(
                away_starters=[
                    {"name": {"default": "Starter G"}, "starter": True},
                    {"name": {"default": "Backup B"}, "starter": False},
                    {"name": {"default": "Third String"}, "starter": False},
                ],
                home_starters=[
                    {"name": {"default": "Home Starter"}, "starter": True},
                ],
            )
        )
        result = get_nhl_starters_for_game(12345, session=mock_sess)
        assert result["away"]["backup_name"] == "Backup B"

    def test_null_playerbygamestats_returns_none(self):
        mock_sess = MagicMock()
        mock_sess.get.return_value = make_response(
            {"id": 99, "playerByGameStats": None}
        )
        result = get_nhl_starters_for_game(99, session=mock_sess)
        assert result is None


# ---------------------------------------------------------------------------
# TestGetStartersForOddsGame
# ---------------------------------------------------------------------------

class TestGetStartersForOddsGame:
    def _make_starters_response(self) -> dict:
        return make_boxscore_response(
            away_starters=[{"name": {"default": "S. Knight"}, "starter": True}],
            home_starters=[{"name": {"default": "A. Soderblom"}, "starter": True}],
            game_id=2001,
        )

    def _make_schedule_with_game(self, away: str = "BOS", home: str = "NYR") -> dict:
        return make_schedule_response(
            "2026-02-19",
            [make_schedule_game(2001, away, home, start_utc="2026-02-19T23:00:00Z")]
        )

    def test_successful_lookup(self):
        mock_sess = MagicMock()
        # First call = schedule, second = boxscore
        mock_sess.get.side_effect = [
            make_response(self._make_schedule_with_game("BOS", "NYR")),
            make_response(self._make_starters_response()),
        ]
        with patch("core.nhl_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 19, 22, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            result = get_starters_for_odds_game(
                "Boston Bruins", "New York Rangers",
                game_start_utc=datetime(2026, 2, 19, 23, 0, tzinfo=timezone.utc),
                session=mock_sess,
            )
        assert result is not None
        assert result["game_id"] == 2001

    def test_timing_gate_too_early(self):
        """Returns None if >90 min before game start."""
        future_start = datetime.now(timezone.utc) + timedelta(hours=3)
        result = get_starters_for_odds_game(
            "Boston Bruins", "New York Rangers",
            game_start_utc=future_start,
        )
        assert result is None

    def test_unknown_team_returns_none(self):
        result = get_starters_for_odds_game("Fake Team FC", "Another Fake")
        assert result is None

    def test_game_not_in_schedule_returns_none(self):
        mock_sess = MagicMock()
        # Schedule has different matchup
        mock_sess.get.return_value = make_response(
            self._make_schedule_with_game("TOR", "MTL")
        )
        past_start = datetime.now(timezone.utc) - timedelta(minutes=30)
        with patch("core.nhl_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime.now(timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            result = get_starters_for_odds_game(
                "Boston Bruins", "New York Rangers",
                game_start_utc=past_start,
                session=mock_sess,
            )
        assert result is None

    def test_no_game_start_provided(self):
        """Without game_start_utc, timing gate is skipped — proceeds to schedule lookup."""
        mock_sess = MagicMock()
        mock_sess.get.side_effect = [
            make_response(self._make_schedule_with_game("BOS", "NYR")),
            make_response(self._make_starters_response()),
        ]
        with patch("core.nhl_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 19, 22, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            result = get_starters_for_odds_game(
                "Boston Bruins", "New York Rangers",
                game_start_utc=None,
                session=mock_sess,
            )
        assert result is not None
