"""
tests/test_price_history_store.py — RLM 2.0 price history store tests (Session 8)

Tests cover:
- init_price_history_db: schema creation, idempotent
- record_open_prices: insert, never-overwrite invariant, empty input
- integrate_with_session_cache: scan raw_games, dedup, multi-game
- get_historical_open_price: retrieval, miss returns None
- inject_historical_prices_into_cache: seeds math_engine cache
- purge_old_events: count rows deleted, fresh events preserved
- price_history_status: status string format
- get_all_open_prices: full retrieval with sport filter
"""

import os
import pytest

from core.price_history_store import (
    get_all_open_prices,
    get_historical_open_price,
    init_price_history_db,
    inject_historical_prices_into_cache,
    integrate_with_session_cache,
    price_history_status,
    purge_old_events,
    record_open_prices,
)
from core.math_engine import (
    clear_open_price_cache,
    get_open_price,
    open_price_cache_size,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_cache():
    """Clear the math_engine open price cache before every test."""
    clear_open_price_cache()
    yield
    clear_open_price_cache()


@pytest.fixture()
def db(tmp_path) -> str:
    """Return an initialised price_history DB path."""
    path = str(tmp_path / "ph_test.db")
    init_price_history_db(path)
    return path


def _make_game(event_id: str, home: str, away: str, books: list[dict]) -> dict:
    return {
        "id": event_id,
        "home_team": home,
        "away_team": away,
        "bookmakers": books,
    }


def _book(key: str, outcomes: list[dict]) -> dict:
    return {"key": key, "markets": [{"key": "h2h", "outcomes": outcomes}]}


def _outcome(name: str, price: int) -> dict:
    return {"name": name, "price": price}


# ---------------------------------------------------------------------------
# init_price_history_db
# ---------------------------------------------------------------------------

class TestInitPriceHistoryDb:

    def test_creates_db_file(self, tmp_path):
        path = str(tmp_path / "new.db")
        assert not os.path.exists(path)
        init_price_history_db(path)
        assert os.path.exists(path)

    def test_idempotent(self, db):
        # Should not raise on second call
        init_price_history_db(db)

    def test_creates_parent_directory(self, tmp_path):
        path = str(tmp_path / "a" / "b" / "ph.db")
        init_price_history_db(path)
        assert os.path.exists(path)


# ---------------------------------------------------------------------------
# record_open_prices
# ---------------------------------------------------------------------------

class TestRecordOpenPrices:

    def test_inserts_new_sides(self, db):
        n = record_open_prices("ev001", {"TeamA": -110, "TeamB": 100}, "NBA", db)
        assert n == 2

    def test_never_overwrites_existing(self, db):
        record_open_prices("ev001", {"TeamA": -110}, "NBA", db)
        n2 = record_open_prices("ev001", {"TeamA": -125}, "NBA", db)
        assert n2 == 0
        # Price should still be the original
        assert get_historical_open_price("ev001", "TeamA", db) == -110

    def test_partial_overwrite_adds_new_skips_existing(self, db):
        record_open_prices("ev001", {"TeamA": -110}, "NBA", db)
        n = record_open_prices("ev001", {"TeamA": -125, "TeamB": 100}, "NBA", db)
        # TeamA already exists (skip), TeamB is new (insert)
        assert n == 1

    def test_empty_sides_returns_zero(self, db):
        assert record_open_prices("ev001", {}, "NBA", db) == 0

    def test_stores_correct_price(self, db):
        record_open_prices("ev001", {"Over": -115}, "NBA", db)
        assert get_historical_open_price("ev001", "Over", db) == -115

    def test_multiple_events_isolated(self, db):
        record_open_prices("ev001", {"TeamA": -110}, "NBA", db)
        record_open_prices("ev002", {"TeamA": -120}, "NBA", db)
        assert get_historical_open_price("ev001", "TeamA", db) == -110
        assert get_historical_open_price("ev002", "TeamA", db) == -120


# ---------------------------------------------------------------------------
# integrate_with_session_cache
# ---------------------------------------------------------------------------

class TestIntegrateWithSessionCache:

    def test_new_games_written(self, db):
        games = [
            _make_game("ev001", "Home", "Away",
                       [_book("dk", [_outcome("Home", -130), _outcome("Away", 110)])])
        ]
        n = integrate_with_session_cache(games, "NBA", db)
        assert n == 2

    def test_second_call_returns_zero(self, db):
        games = [
            _make_game("ev001", "Home", "Away",
                       [_book("dk", [_outcome("Home", -130), _outcome("Away", 110)])])
        ]
        integrate_with_session_cache(games, "NBA", db)
        n2 = integrate_with_session_cache(games, "NBA", db)
        assert n2 == 0

    def test_multiple_games_all_written(self, db):
        games = [
            _make_game("ev001", "H1", "A1", [_book("dk", [_outcome("H1", -110), _outcome("A1", -110)])]),
            _make_game("ev002", "H2", "A2", [_book("dk", [_outcome("H2", -120), _outcome("A2", 100)])]),
        ]
        n = integrate_with_session_cache(games, "NBA", db)
        assert n == 4

    def test_empty_games_returns_zero(self, db):
        assert integrate_with_session_cache([], "NBA", db) == 0

    def test_game_without_id_skipped(self, db):
        games = [{"bookmakers": [_book("dk", [_outcome("Team", -110)])]}]
        n = integrate_with_session_cache(games, "NBA", db)
        assert n == 0

    def test_deduplicates_sides_across_books(self, db):
        # Two books offering same outcome — side should only be written once
        games = [
            _make_game("ev001", "Home", "Away", [
                _book("dk", [_outcome("Home", -130), _outcome("Away", 110)]),
                _book("fd", [_outcome("Home", -128), _outcome("Away", 108)]),
            ])
        ]
        n = integrate_with_session_cache(games, "NBA", db)
        # Should be 2 sides (Home, Away) not 4 — first-seen wins
        assert n == 2

    def test_sport_tag_stored(self, db):
        games = [
            _make_game("ev001", "H", "A", [_book("dk", [_outcome("H", -110)])])
        ]
        integrate_with_session_cache(games, "NHL", db)
        all_prices = get_all_open_prices("NHL", db)
        assert "ev001" in all_prices


# ---------------------------------------------------------------------------
# get_historical_open_price
# ---------------------------------------------------------------------------

class TestGetHistoricalOpenPrice:

    def test_returns_stored_price(self, db):
        record_open_prices("ev001", {"Lakers": -130}, "NBA", db)
        assert get_historical_open_price("ev001", "Lakers", db) == -130

    def test_returns_none_for_unknown_event(self, db):
        assert get_historical_open_price("unknown", "Team", db) is None

    def test_returns_none_for_unknown_side(self, db):
        record_open_prices("ev001", {"TeamA": -110}, "NBA", db)
        assert get_historical_open_price("ev001", "TeamB", db) is None

    def test_negative_odds_preserved(self, db):
        record_open_prices("ev001", {"Favourite": -180}, "NBA", db)
        assert get_historical_open_price("ev001", "Favourite", db) == -180

    def test_positive_odds_preserved(self, db):
        record_open_prices("ev001", {"Underdog": 140}, "NBA", db)
        assert get_historical_open_price("ev001", "Underdog", db) == 140


# ---------------------------------------------------------------------------
# inject_historical_prices_into_cache
# ---------------------------------------------------------------------------

class TestInjectHistoricalPricesIntoCache:

    def test_seeds_math_engine_cache(self, db):
        record_open_prices("ev001", {"Lakers": -130, "Celtics": 110}, "NBA", db)
        games = [_make_game("ev001", "Lakers", "Celtics",
                            [_book("dk", [_outcome("Lakers", -130), _outcome("Celtics", 110)])])]
        seeded = inject_historical_prices_into_cache(games, db)
        assert seeded == 1
        # math_engine cache now has the prices
        assert get_open_price("ev001", "Lakers") == -130

    def test_does_not_overwrite_existing_cache(self, db):
        # Pre-seed math_engine cache with a price
        from core.math_engine import seed_open_prices_from_db
        seed_open_prices_from_db({"ev001": {"Lakers": -110}})
        # Store a different price in price_history
        record_open_prices("ev001", {"Lakers": -130}, "NBA", db)
        games = [_make_game("ev001", "Lakers", "Celtics",
                            [_book("dk", [_outcome("Lakers", -110)])])]
        inject_historical_prices_into_cache(games, db)
        # Should still have the original -110 (first-seen wins)
        assert get_open_price("ev001", "Lakers") == -110

    def test_empty_games_seeds_nothing(self, db):
        seeded = inject_historical_prices_into_cache([], db)
        assert seeded == 0
        assert open_price_cache_size() == 0

    def test_no_history_seeds_nothing(self, db):
        # Games present but no history stored yet
        games = [_make_game("ev001", "H", "A",
                            [_book("dk", [_outcome("H", -110)])])]
        seeded = inject_historical_prices_into_cache(games, db)
        assert seeded == 0

    def test_multiple_events_all_seeded(self, db):
        record_open_prices("ev001", {"Home1": -110}, "NBA", db)
        record_open_prices("ev002", {"Home2": -120}, "NBA", db)
        games = [
            _make_game("ev001", "Home1", "Away1", [_book("dk", [_outcome("Home1", -110)])]),
            _make_game("ev002", "Home2", "Away2", [_book("dk", [_outcome("Home2", -120)])]),
        ]
        seeded = inject_historical_prices_into_cache(games, db)
        assert seeded == 2
        assert get_open_price("ev001", "Home1") == -110
        assert get_open_price("ev002", "Home2") == -120


# ---------------------------------------------------------------------------
# purge_old_events
# ---------------------------------------------------------------------------

class TestPurgeOldEvents:

    def test_purge_zero_when_all_fresh(self, db):
        record_open_prices("ev001", {"Team": -110}, "NBA", db)
        deleted = purge_old_events(days_old=14, db_path=db)
        assert deleted == 0

    def test_purge_old_rows(self, db):
        # Manually insert an old row with a timestamp in the past
        import sqlite3
        from datetime import timedelta
        old_ts = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            - timedelta(days=20)
        ).isoformat()
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO price_history (event_id, side, open_price, first_seen, sport) "
            "VALUES (?, ?, ?, ?, ?)",
            ("old_ev", "Team", -110, old_ts, "NBA"),
        )
        conn.commit()
        conn.close()

        deleted = purge_old_events(days_old=14, db_path=db)
        assert deleted == 1

    def test_purge_does_not_delete_fresh(self, db):
        record_open_prices("fresh_ev", {"Team": -110}, "NBA", db)
        import sqlite3
        from datetime import timedelta
        old_ts = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            - timedelta(days=20)
        ).isoformat()
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO price_history (event_id, side, open_price, first_seen, sport) "
            "VALUES (?, ?, ?, ?, ?)",
            ("old_ev", "Team", -110, old_ts, "NBA"),
        )
        conn.commit()
        conn.close()

        deleted = purge_old_events(days_old=14, db_path=db)
        assert deleted == 1  # Only old_ev deleted
        assert get_historical_open_price("fresh_ev", "Team", db) == -110


# ---------------------------------------------------------------------------
# price_history_status
# ---------------------------------------------------------------------------

class TestPriceHistoryStatus:

    def test_empty_db_returns_empty_string(self, db):
        status = price_history_status(db)
        assert "empty" in status

    def test_non_empty_returns_counts(self, db):
        record_open_prices("ev001", {"TeamA": -110, "TeamB": 100}, "NBA", db)
        status = price_history_status(db)
        assert "1 events" in status
        assert "2 sides" in status

    def test_multiple_events_counted(self, db):
        record_open_prices("ev001", {"A": -110}, "NBA", db)
        record_open_prices("ev002", {"B": -115}, "NBA", db)
        status = price_history_status(db)
        assert "2 events" in status


# ---------------------------------------------------------------------------
# get_all_open_prices
# ---------------------------------------------------------------------------

class TestGetAllOpenPrices:

    def test_returns_nested_dict(self, db):
        record_open_prices("ev001", {"TeamA": -110, "TeamB": 100}, "NBA", db)
        all_p = get_all_open_prices(db_path=db)
        assert "ev001" in all_p
        assert all_p["ev001"]["TeamA"] == -110
        assert all_p["ev001"]["TeamB"] == 100

    def test_sport_filter(self, db):
        record_open_prices("ev001", {"TeamA": -110}, "NBA", db)
        record_open_prices("ev002", {"TeamB": -120}, "NHL", db)
        nba_only = get_all_open_prices("NBA", db)
        assert "ev001" in nba_only
        assert "ev002" not in nba_only

    def test_empty_db_returns_empty_dict(self, db):
        assert get_all_open_prices(db_path=db) == {}

    def test_multiple_events_all_returned(self, db):
        for i in range(5):
            record_open_prices(f"ev{i:03d}", {"Side": -110}, "NBA", db)
        all_p = get_all_open_prices(db_path=db)
        assert len(all_p) == 5
