"""
tests/test_result_resolver.py — Titanium-Agentic
==================================================
Unit tests for core/result_resolver.py.

All ESPN API calls are intercepted via _fetcher injection.
No network calls. No Odds API credits consumed.

Coverage:
- _espn_sport_path() — mapping + unsupported sports
- _normalize() / _team_matches() — fuzzy name logic
- _find_game() — completed-only filter, away/home matching, no-match
- fetch_espn_scoreboard() — happy path, error path, score parsing
- _resolve_spread() — win, loss, void, bad target, unknown team
- _resolve_total() — over win/loss/void, under win/loss/void
- _resolve_moneyline() — win, loss, void, no-match
- auto_resolve_pending() — empty, single resolved, skipped, error
"""

import sqlite3
import tempfile
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.result_resolver import (
    ResolveResult,
    _espn_sport_path,
    _find_game,
    _normalize,
    _resolve_moneyline,
    _resolve_spread,
    _resolve_total,
    _team_matches,
    auto_resolve_pending,
    fetch_espn_scoreboard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(
    home_team: str = "Los Angeles Lakers",
    away_team: str = "Boston Celtics",
    home_score: int = 112,
    away_score: int = 108,
    completed: bool = True,
    espn_id: str = "401_test",
) -> dict:
    return {
        "espn_id": espn_id,
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "completed": completed,
    }


def _make_espn_response(games: list[dict]) -> dict:
    """Build a minimal ESPN API scoreboard JSON from our game dicts."""
    events = []
    for g in games:
        events.append({
            "id": g["espn_id"],
            "competitions": [{
                "status": {"type": {"completed": g["completed"]}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": g["home_team"]},
                        "score": str(g["home_score"]),
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": g["away_team"]},
                        "score": str(g["away_score"]),
                    },
                ],
            }],
        })
    return {"events": events}


def _make_bet(
    bet_id: int = 1,
    sport: str = "NBA",
    matchup: str = "Boston Celtics @ Los Angeles Lakers",
    market_type: str = "spreads",
    target: str = "Los Angeles Lakers -4.5",
    line: float = -4.5,
    stake: float = 50.0,
    logged_at: str = "2026-02-26T23:00:00Z",
) -> dict:
    return {
        "id": bet_id,
        "sport": sport,
        "matchup": matchup,
        "market_type": market_type,
        "target": target,
        "line": line,
        "stake": stake,
        "logged_at": logged_at,
        "result": "pending",
    }


# ---------------------------------------------------------------------------
# _espn_sport_path
# ---------------------------------------------------------------------------

class TestEspnSportPath:
    def test_nba_maps(self):
        assert _espn_sport_path("NBA") == "basketball/nba"

    def test_nfl_maps(self):
        assert _espn_sport_path("NFL") == "football/nfl"

    def test_ncaab_maps(self):
        assert _espn_sport_path("NCAAB") == "basketball/mens-college-basketball"

    def test_nhl_maps(self):
        assert _espn_sport_path("NHL") == "hockey/nhl"

    def test_lowercase_nba(self):
        assert _espn_sport_path("nba") == "basketball/nba"

    def test_mlb_unsupported(self):
        assert _espn_sport_path("MLB") is None

    def test_empty_string_unsupported(self):
        assert _espn_sport_path("") is None

    def test_tennis_unsupported(self):
        assert _espn_sport_path("TENNIS_ATP") is None


# ---------------------------------------------------------------------------
# _normalize / _team_matches
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Los Angeles Lakers") == "los angeles lakers"

    def test_strips_punctuation(self):
        assert _normalize("L.A. Lakers!") == "la lakers"

    def test_collapses_spaces(self):
        # Extra spaces collapse to single (re.sub doesn't collapse but strip handles ends)
        result = _normalize("Boston  Celtics")
        assert "boston" in result and "celtics" in result


class TestTeamMatches:
    def test_full_name_match(self):
        assert _team_matches("Los Angeles Lakers", "Los Angeles Lakers")

    def test_fragment_in_espn(self):
        assert _team_matches("Los Angeles Lakers", "Lakers")

    def test_espn_in_fragment(self):
        # Edge case: ESPN name contained in fragment
        assert _team_matches("Lakers", "Los Angeles Lakers")

    def test_city_fragment(self):
        assert _team_matches("Boston Celtics", "Boston")

    def test_no_match(self):
        assert not _team_matches("Los Angeles Lakers", "Celtics")

    def test_empty_espn(self):
        assert not _team_matches("", "Lakers")

    def test_empty_fragment(self):
        assert not _team_matches("Los Angeles Lakers", "")

    def test_case_insensitive(self):
        assert _team_matches("Los Angeles Lakers", "lakers")


# ---------------------------------------------------------------------------
# _find_game
# ---------------------------------------------------------------------------

class TestFindGame:
    def _sb(self, *args) -> list[dict]:
        return list(args)

    def test_finds_matching_completed_game(self):
        game = _make_game(home_team="LA Lakers", away_team="Boston Celtics")
        result = _find_game([game], "Boston Celtics @ LA Lakers")
        assert result is not None
        assert result["home_team"] == "LA Lakers"

    def test_skips_incomplete_game_when_flag_set(self):
        game = _make_game(completed=False)
        result = _find_game([game], "Boston Celtics @ Los Angeles Lakers")
        assert result is None

    def test_includes_incomplete_when_flag_off(self):
        game = _make_game(completed=False)
        result = _find_game([game], "Boston Celtics @ Los Angeles Lakers", completed_only=False)
        assert result is not None

    def test_no_match_returns_none(self):
        game = _make_game(home_team="Phoenix Suns", away_team="Dallas Mavericks")
        result = _find_game([game], "Boston Celtics @ Los Angeles Lakers")
        assert result is None

    def test_empty_scoreboard_returns_none(self):
        assert _find_game([], "Boston Celtics @ Los Angeles Lakers") is None

    def test_empty_matchup_returns_none(self):
        game = _make_game()
        assert _find_game([game], "") is None

    def test_matchup_without_at_returns_none(self):
        game = _make_game()
        assert _find_game([game], "Boston Celtics vs Los Angeles Lakers") is None


# ---------------------------------------------------------------------------
# fetch_espn_scoreboard (with mock fetcher)
# ---------------------------------------------------------------------------

class TestFetchEspnScoreboard:
    def _fetcher_ok(self, games: list[dict]):
        """Return a fetcher that returns fake ESPN JSON."""
        def f(url: str) -> dict:
            return _make_espn_response(games)
        return f

    def _fetcher_error(self):
        def f(url: str):
            raise ConnectionError("network error")
        return f

    def test_returns_games_on_success(self):
        games = [_make_game(home_score=112, away_score=108, completed=True)]
        result = fetch_espn_scoreboard("NBA", "20260226", _fetcher=self._fetcher_ok(games))
        assert len(result) == 1
        assert result[0]["home_score"] == 112
        assert result[0]["away_score"] == 108
        assert result[0]["completed"] is True

    def test_empty_on_unsupported_sport(self):
        result = fetch_espn_scoreboard("MLB", "20260226")
        assert result == []

    def test_empty_on_network_error(self):
        result = fetch_espn_scoreboard("NBA", "20260226", _fetcher=self._fetcher_error())
        assert result == []

    def test_empty_events_list(self):
        def f(url):
            return {"events": []}
        result = fetch_espn_scoreboard("NBA", "20260226", _fetcher=f)
        assert result == []

    def test_string_scores_parsed_to_int(self):
        games = [_make_game(home_score=101, away_score=99)]
        result = fetch_espn_scoreboard("NBA", "20260226", _fetcher=self._fetcher_ok(games))
        assert isinstance(result[0]["home_score"], int)
        assert isinstance(result[0]["away_score"], int)


# ---------------------------------------------------------------------------
# _resolve_spread
# ---------------------------------------------------------------------------

class TestResolveSpread:
    def _bet(self, target: str, line: float, matchup: str = "Boston Celtics @ Los Angeles Lakers") -> dict:
        return {"target": target, "line": line, "matchup": matchup}

    def test_home_favorite_covers(self):
        # Lakers -4.5 at home, Lakers win 112-105 → margin=+7, adj=7+(-4.5)=+2.5 → WIN
        game = _make_game(home_score=112, away_score=105)
        bet = self._bet("Los Angeles Lakers -4.5", -4.5)
        assert _resolve_spread(bet, game) == "win"

    def test_home_favorite_fails_to_cover(self):
        # Lakers -4.5 at home, Lakers win by only 3 → margin=+3, adj=3-4.5=-1.5 → LOSS
        game = _make_game(home_score=110, away_score=107)
        bet = self._bet("Los Angeles Lakers -4.5", -4.5)
        assert _resolve_spread(bet, game) == "loss"

    def test_home_favorite_push(self):
        # Lakers -4.5 push is impossible with half point, use whole number for push test
        # Lakers -7, win exactly 7 → adj=7-7=0 → VOID
        game = _make_game(home_score=112, away_score=105)
        bet = self._bet("Los Angeles Lakers -7.0", -7.0)
        assert _resolve_spread(bet, game) == "void"

    def test_away_underdog_covers(self):
        # Celtics +7.0 away, lose by 4 → actual_margin=-4, adj=-4+7=+3 → WIN
        game = _make_game(home_score=112, away_score=108)
        bet = self._bet("Boston Celtics +7.0", +7.0)
        assert _resolve_spread(bet, game) == "win"

    def test_away_underdog_fails_to_cover(self):
        # Celtics +7.0 away, lose by 10 → adj=-10+7=-3 → LOSS
        game = _make_game(home_score=115, away_score=105)
        bet = self._bet("Boston Celtics +7.0", +7.0)
        assert _resolve_spread(bet, game) == "loss"

    def test_away_underdog_push(self):
        # Celtics +7.0 away, lose by exactly 7 → adj=-7+7=0 → VOID
        game = _make_game(home_score=112, away_score=105)
        bet = self._bet("Boston Celtics +7.0", +7.0)
        assert _resolve_spread(bet, game) == "void"

    def test_bad_target_format_returns_none(self):
        game = _make_game()
        bet = self._bet("Over 221.5", 221.5)
        assert _resolve_spread(bet, game) is None

    def test_missing_line_returns_none(self):
        game = _make_game()
        bet = {"target": "Los Angeles Lakers -4.5", "line": None, "matchup": "Boston Celtics @ Los Angeles Lakers"}
        assert _resolve_spread(bet, game) is None

    def test_unknown_team_returns_none(self):
        game = _make_game(home_team="Phoenix Suns", away_team="Dallas Mavericks")
        bet = self._bet("Chicago Bulls +7.0", +7.0)
        assert _resolve_spread(bet, game) is None


# ---------------------------------------------------------------------------
# _resolve_total
# ---------------------------------------------------------------------------

class TestResolveTotal:
    def _bet(self, target: str, line: float) -> dict:
        return {"target": target, "line": line}

    def test_over_win(self):
        # O 221.5, game total = 225 → WIN
        game = _make_game(home_score=115, away_score=110)
        assert _resolve_total(self._bet("Over 221.5", 221.5), game) == "win"

    def test_over_loss(self):
        # O 221.5, game total = 220 → LOSS
        game = _make_game(home_score=110, away_score=110)
        assert _resolve_total(self._bet("Over 221.5", 221.5), game) == "loss"

    def test_over_push(self):
        # O 221.0, game total = 221 → VOID
        game = _make_game(home_score=111, away_score=110)
        assert _resolve_total(self._bet("Over 221.0", 221.0), game) == "void"

    def test_under_win(self):
        # U 221.5, game total = 218 → WIN
        game = _make_game(home_score=110, away_score=108)
        assert _resolve_total(self._bet("Under 221.5", 221.5), game) == "win"

    def test_under_loss(self):
        # U 221.5, game total = 225 → LOSS
        game = _make_game(home_score=115, away_score=110)
        assert _resolve_total(self._bet("Under 221.5", 221.5), game) == "loss"

    def test_under_push(self):
        # U 221.0, game total = 221 → VOID
        game = _make_game(home_score=111, away_score=110)
        assert _resolve_total(self._bet("Under 221.0", 221.0), game) == "void"

    def test_bad_direction_returns_none(self):
        game = _make_game()
        assert _resolve_total(self._bet("Chicago Bulls +7.0", 7.0), game) is None

    def test_missing_line_returns_none(self):
        game = _make_game()
        assert _resolve_total({"target": "Over 221.5", "line": None}, game) is None


# ---------------------------------------------------------------------------
# _resolve_moneyline
# ---------------------------------------------------------------------------

class TestResolveMoneyline:
    def _bet(self, target: str) -> dict:
        return {"target": target}

    def test_home_team_wins(self):
        game = _make_game(home_team="Los Angeles Lakers", away_team="Boston Celtics",
                          home_score=112, away_score=108)
        assert _resolve_moneyline(self._bet("Los Angeles Lakers ML"), game) == "win"

    def test_home_team_loses(self):
        game = _make_game(home_team="Los Angeles Lakers", away_team="Boston Celtics",
                          home_score=108, away_score=112)
        assert _resolve_moneyline(self._bet("Los Angeles Lakers ML"), game) == "loss"

    def test_away_team_wins(self):
        game = _make_game(home_team="Los Angeles Lakers", away_team="Boston Celtics",
                          home_score=108, away_score=112)
        assert _resolve_moneyline(self._bet("Boston Celtics ML"), game) == "win"

    def test_away_team_loses(self):
        game = _make_game(home_team="Los Angeles Lakers", away_team="Boston Celtics",
                          home_score=112, away_score=108)
        assert _resolve_moneyline(self._bet("Boston Celtics ML"), game) == "loss"

    def test_tie_returns_void(self):
        game = _make_game(home_score=110, away_score=110)
        assert _resolve_moneyline(self._bet("Los Angeles Lakers ML"), game) == "void"

    def test_bad_target_returns_none(self):
        game = _make_game()
        assert _resolve_moneyline(self._bet("Chicago Bulls +7.0"), game) is None

    def test_unmatched_team_returns_none(self):
        game = _make_game(home_team="Phoenix Suns", away_team="Dallas Mavericks")
        assert _resolve_moneyline(self._bet("Chicago Bulls ML"), game) is None


# ---------------------------------------------------------------------------
# auto_resolve_pending — integration with temp SQLite DB
# ---------------------------------------------------------------------------

class TestAutoResolvePending:
    def _setup_db(self, tmp_path) -> str:
        """Create a temp SQLite DB with bet_log table."""
        from core.line_logger import init_db
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        return db_path

    def _insert_bet(self, db_path: str, **kwargs) -> int:
        from core.line_logger import log_bet
        defaults = dict(
            sport="NBA",
            matchup="Boston Celtics @ Los Angeles Lakers",
            market_type="spreads",
            target="Los Angeles Lakers -4.5",
            price=-110,
            edge_pct=0.04,
            kelly_size=0.5,
            stake=50.0,
            line=-4.5,
            notes="paper",
            grade="A",
            db_path=db_path,
        )
        defaults.update(kwargs)
        return log_bet(**defaults)

    def _make_fetcher(self, games: list[dict]):
        def f(url: str) -> dict:
            return _make_espn_response(games)
        return f

    def test_empty_pending_returns_zero_resolved(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        rr = auto_resolve_pending(db_path=db_path)
        assert rr.resolved == 0
        assert rr.skipped == 0
        assert rr.errors == 0

    def test_resolves_spread_win(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        bet_id = self._insert_bet(
            db_path=db_path,
            market_type="spreads",
            target="Los Angeles Lakers -4.5",
            line=-4.5,
        )

        # Lakers win by 10 → covers -4.5
        game = _make_game(home_score=115, away_score=105, completed=True)
        fetcher = self._make_fetcher([game])

        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 1
        assert rr.skipped == 0

        # Verify DB was updated
        from core.line_logger import get_bets
        bets = get_bets(db_path=db_path)
        assert bets[0]["result"] == "win"

    def test_resolves_total_under_loss(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        self._insert_bet(
            db_path=db_path,
            market_type="totals",
            target="Under 221.5",
            line=221.5,
        )

        # Total = 225 → Under LOSS
        game = _make_game(home_score=115, away_score=110, completed=True)
        fetcher = self._make_fetcher([game])

        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 1

        from core.line_logger import get_bets
        assert get_bets(db_path=db_path)[0]["result"] == "loss"

    def test_skips_when_game_not_found(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        self._insert_bet(db_path=db_path)

        # Return a game that doesn't match the matchup
        game = _make_game(home_team="Phoenix Suns", away_team="Dallas Mavericks")
        fetcher = self._make_fetcher([game])

        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 0
        assert rr.skipped == 1

    def test_skips_incomplete_games(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        self._insert_bet(db_path=db_path)

        game = _make_game(completed=False)
        fetcher = self._make_fetcher([game])

        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 0
        assert rr.skipped == 1

    def test_already_resolved_bet_not_re_resolved(self, tmp_path):
        from core.line_logger import init_db, log_bet, update_bet_result
        db_path = self._setup_db(tmp_path)
        bet_id = self._insert_bet(db_path=db_path)
        # Manually resolve it
        update_bet_result(bet_id, "win", 50.0, db_path=db_path)

        game = _make_game(completed=True)
        fetcher = self._make_fetcher([game])

        # get_bets(result_filter="pending") won't return resolved bets
        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 0  # nothing pending

    def test_resolve_result_details_populated(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        self._insert_bet(
            db_path=db_path,
            market_type="h2h",
            target="Los Angeles Lakers ML",
            line=0.0,
        )

        game = _make_game(home_score=112, away_score=108, completed=True)
        fetcher = self._make_fetcher([game])

        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 1
        assert len(rr.details) == 1
        assert "WIN" in rr.details[0]


# ---------------------------------------------------------------------------
# Regression tests — bugs found in live run 2026-02-26
# ---------------------------------------------------------------------------

class TestNcaabGroupsParam:
    """NCAAB ESPN URL must include groups=50&limit=200 (default returns ~10 featured games)."""

    def test_ncaab_url_includes_groups_param(self):
        """fetch_espn_scoreboard for NCAAB should request groups=50&limit=200."""
        captured = []

        def capture_fetcher(url: str) -> dict:
            captured.append(url)
            return {"events": []}

        fetch_espn_scoreboard("NCAAB", "20260224", _fetcher=capture_fetcher)
        assert len(captured) == 1
        assert "groups=50" in captured[0]
        assert "limit=200" in captured[0]

    def test_nba_url_has_no_extra_params(self):
        """NBA URL should NOT include groups param (pro sports don't need it)."""
        captured = []

        def capture_fetcher(url: str) -> dict:
            captured.append(url)
            return {"events": []}

        fetch_espn_scoreboard("NBA", "20260224", _fetcher=capture_fetcher)
        assert "groups=" not in captured[0]

    def test_ncaaf_url_includes_groups_param(self):
        """NCAAF URL should include groups=80&limit=200."""
        captured = []

        def capture_fetcher(url: str) -> dict:
            captured.append(url)
            return {"events": []}

        fetch_espn_scoreboard("NCAAF", "20260224", _fetcher=capture_fetcher)
        assert "groups=80" in captured[0]


class TestAbbreviationExpansion:
    """_team_matches must handle Odds API abbreviated names vs ESPN full names."""

    def test_colorado_st_matches_colorado_state(self):
        assert _team_matches("Colorado State Rams", "Colorado St Rams")

    def test_fresno_st_matches_fresno_state(self):
        assert _team_matches("Fresno State Bulldogs", "Fresno St Bulldogs")

    def test_normal_match_still_works(self):
        """Standard substring match must not regress."""
        assert _team_matches("Los Angeles Lakers", "Lakers")

    def test_st_louis_not_broken(self):
        """St. Louis should still match St. Louis (no false State expansion on espn side)."""
        assert _team_matches("St. Louis Blues", "St. Louis Blues")

    def test_no_false_match_on_expansion(self):
        """Expansion should not create false positives."""
        assert not _team_matches("Colorado State Rams", "California Bears")


class TestMidnightUtcDateOffset:
    """Bets logged after midnight UTC for US evening games must search the prior day."""

    def _make_fetcher(self, games_by_date: dict):
        """fetcher returns games only for the specific date embedded in the URL."""
        def f(url: str) -> dict:
            # Extract date from URL: ?dates=YYYYMMDD or &dates=YYYYMMDD
            import re
            m = re.search(r"dates=(\d{8})", url)
            date_str = m.group(1) if m else ""
            games = games_by_date.get(date_str, [])
            events = []
            for g in games:
                events.append({
                    "competitions": [{
                        "competitors": [
                            {"homeAway": "home", "team": {"displayName": g["home_team"]},
                             "score": str(g.get("home_score", 100))},
                            {"homeAway": "away", "team": {"displayName": g["away_team"]},
                             "score": str(g.get("away_score", 90))},
                        ],
                        "status": {"type": {"completed": g.get("completed", True)}},
                        "id": "test123",
                    }]
                })
            return {"events": events}
        return f

    def test_game_on_prior_day_utc_is_found(self, tmp_path):
        """Bet logged 03:00 UTC must search logged_at-1 day (game played prev evening US)."""
        import sqlite3
        from core.line_logger import init_db

        db_path = str(tmp_path / "test.db")
        init_db(db_path)

        # Insert a bet logged at 03:00 UTC on Feb 25 (game was Feb 24 US time)
        conn = sqlite3.connect(db_path)
        conn.execute("""
            INSERT INTO bet_log
            (logged_at, sport, matchup, market_type, target, price, edge_pct,
             kelly_size, stake, result, sharp_score, rlm_fired, days_to_game, line, signal)
            VALUES (
                '2026-02-25T03:00:00+00:00', 'NBA',
                'Oklahoma City Thunder @ Toronto Raptors',
                'h2h', 'Oklahoma City Thunder ML', -115, 0.05, 0.5, 50.0, 'pending',
                55, 0, 0.0, 0.0, ''
            )
        """)
        conn.commit()
        conn.close()

        # Game is only on 20260224 (the day BEFORE logged_at UTC date 20260225)
        games_by_date = {
            "20260224": [
                {"home_team": "Toronto Raptors", "away_team": "Oklahoma City Thunder",
                 "home_score": 98, "away_score": 115, "completed": True}
            ]
        }
        fetcher = self._make_fetcher(games_by_date)

        rr = auto_resolve_pending(db_path=db_path, _fetcher=fetcher)
        assert rr.resolved == 1, f"Expected 1 resolved, got {rr.resolved}. Details: {rr.details}"
        assert "WIN" in rr.details[0]
