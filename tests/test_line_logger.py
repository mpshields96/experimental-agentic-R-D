"""
tests/test_line_logger.py — Titanium-Agentic
=============================================
Unit tests for core/line_logger.py.

All tests use an in-memory SQLite DB (:memory:) — no file I/O required.
Run: pytest tests/test_line_logger.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.line_logger import (
    get_connection,
    init_db,
    upsert_line,
    log_snapshot,
    get_movements,
    get_line_history,
    get_open_prices_for_rlm,
    count_snapshots,
    log_bet,
    update_bet_result,
    get_bets,
    get_pnl_summary,
    MOVEMENT_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Test fixture — in-memory DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Provide a fresh in-memory SQLite DB for each test."""
    conn = get_connection(":memory:")
    # Run schema directly on this connection
    conn.executescript("""
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS line_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        TEXT NOT NULL,
            sport           TEXT NOT NULL,
            market_type     TEXT NOT NULL,
            team            TEXT NOT NULL,
            matchup         TEXT NOT NULL,
            open_line       REAL,
            current_line    REAL,
            open_price      INTEGER,
            current_price   INTEGER,
            movement_delta  REAL DEFAULT 0.0,
            price_delta     INTEGER DEFAULT 0,
            commence_time   TEXT DEFAULT '',
            first_seen      TEXT NOT NULL,
            last_updated    TEXT NOT NULL,
            n_snapshots     INTEGER DEFAULT 1,
            UNIQUE(event_id, market_type, team)
        );
        CREATE TABLE IF NOT EXISTS bet_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at       TEXT NOT NULL,
            sport           TEXT NOT NULL,
            matchup         TEXT NOT NULL,
            market_type     TEXT NOT NULL,
            target          TEXT NOT NULL,
            price           INTEGER NOT NULL,
            edge_pct        REAL DEFAULT 0.0,
            kelly_size      REAL DEFAULT 0.0,
            stake           REAL DEFAULT 0.0,
            result          TEXT DEFAULT 'pending',
            profit          REAL DEFAULT 0.0,
            clv             REAL DEFAULT 0.0,
            close_price     INTEGER DEFAULT 0,
            notes           TEXT DEFAULT ''
        );
    """)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_creates_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        conn = get_connection(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}
        assert "line_history" in table_names
        assert "bet_log" in table_names
        conn.close()

    def test_idempotent(self, tmp_path):
        """Calling init_db twice should not raise."""
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        init_db(db_path)  # should not raise


# ---------------------------------------------------------------------------
# upsert_line
# ---------------------------------------------------------------------------

class TestUpsertLine:
    def test_first_insert_returns_is_new(self, db):
        result = upsert_line(
            conn=db, event_id="evt_001", sport="NBA",
            market_type="spread", team="Celtics", matchup="Heat @ Celtics",
            line=-4.5, price=-110, commence_time="2026-02-20T01:00:00Z",
        )
        assert result["is_new"] is True
        assert result["movement_delta"] == 0.0
        assert result["flagged"] is False

    def test_second_call_is_not_new(self, db):
        upsert_line(db, "evt_001", "NBA", "spread", "Celtics",
                    "Heat @ Celtics", -4.5, -110)
        result = upsert_line(db, "evt_001", "NBA", "spread", "Celtics",
                             "Heat @ Celtics", -4.5, -110)
        assert result["is_new"] is False

    def test_movement_delta_computed(self, db):
        """Line moves from -4.5 to -7.5 → delta = -3.0"""
        upsert_line(db, "evt_002", "NBA", "spread", "Lakers",
                    "Warriors @ Lakers", -4.5, -110)
        result = upsert_line(db, "evt_002", "NBA", "spread", "Lakers",
                             "Warriors @ Lakers", -7.5, -115)
        assert abs(result["movement_delta"] - (-3.0)) < 0.001

    def test_flagged_on_large_movement(self, db):
        """Movement >= 3 points triggers flagged=True"""
        upsert_line(db, "evt_003", "NCAAB", "spread", "Duke",
                    "Virginia @ Duke", -4.5, -110)
        result = upsert_line(db, "evt_003", "NCAAB", "spread", "Duke",
                             "Virginia @ Duke", -8.0, -115)
        assert result["flagged"] is True
        assert abs(result["movement_delta"] - (-3.5)) < 0.001

    def test_not_flagged_on_small_movement(self, db):
        """Movement < 3 points → not flagged"""
        upsert_line(db, "evt_004", "NCAAB", "spread", "Duke",
                    "Virginia @ Duke", -4.5, -110)
        result = upsert_line(db, "evt_004", "NCAAB", "spread", "Duke",
                             "Virginia @ Duke", -6.0, -112)
        assert result["flagged"] is False

    def test_n_snapshots_increments(self, db):
        upsert_line(db, "evt_005", "NBA", "moneyline", "Heat",
                    "Bucks @ Heat", 0.0, -110)
        upsert_line(db, "evt_005", "NBA", "moneyline", "Heat",
                    "Bucks @ Heat", 0.0, -112)
        upsert_line(db, "evt_005", "NBA", "moneyline", "Heat",
                    "Bucks @ Heat", 0.0, -115)
        row = db.execute(
            "SELECT n_snapshots FROM line_history WHERE event_id = 'evt_005'"
        ).fetchone()
        assert row["n_snapshots"] == 3

    def test_open_line_preserved(self, db):
        """open_line should never change after first insert"""
        upsert_line(db, "evt_006", "NBA", "total", "Over",
                    "Bulls @ Knicks", 220.5, -110)
        upsert_line(db, "evt_006", "NBA", "total", "Over",
                    "Bulls @ Knicks", 225.0, -115)
        row = db.execute(
            "SELECT open_line, current_line FROM line_history WHERE event_id = 'evt_006'"
        ).fetchone()
        assert row["open_line"] == 220.5  # unchanged
        assert row["current_line"] == 225.0  # updated

    def test_price_delta_computed(self, db):
        """Price moves from -110 to -120 → price_delta = -10"""
        upsert_line(db, "evt_007", "NBA", "spread", "Warriors",
                    "Lakers @ Warriors", -3.5, -110)
        result = upsert_line(db, "evt_007", "NBA", "spread", "Warriors",
                             "Lakers @ Warriors", -3.5, -120)
        assert result["price_delta"] == -10

    def test_movement_threshold_constant(self):
        assert MOVEMENT_THRESHOLD == 3.0


# ---------------------------------------------------------------------------
# log_snapshot
# ---------------------------------------------------------------------------

class TestLogSnapshot:
    def _make_games(self) -> list[dict]:
        return [
            {
                "id": "game_snap_001",
                "home_team": "Celtics",
                "away_team": "Heat",
                "commence_time": "2026-02-20T01:00:00Z",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "title": "DraftKings",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Celtics", "price": -110, "point": -5.5},
                                    {"name": "Heat", "price": -110, "point": 5.5},
                                ],
                            },
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Celtics", "price": -190},
                                    {"name": "Heat", "price": 160},
                                ],
                            },
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "price": -110, "point": 215.5},
                                    {"name": "Under", "price": -110, "point": 215.5},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

    def test_snapshot_inserts_lines(self, tmp_path):
        db_path = str(tmp_path / "snap.db")
        init_db(db_path)
        games = self._make_games()
        results = log_snapshot(games, "NBA", db_path)
        # Should have spread (2 sides) + moneyline (2 sides) + totals (2 sides) = 6
        assert len(results) == 6

    def test_second_snapshot_updates_not_inserts(self, tmp_path):
        db_path = str(tmp_path / "snap2.db")
        init_db(db_path)
        games = self._make_games()
        log_snapshot(games, "NBA", db_path)
        results = log_snapshot(games, "NBA", db_path)
        # All should be updates (is_new=False)
        assert all(not r["is_new"] for r in results)

    def test_empty_games_returns_empty(self, tmp_path):
        db_path = str(tmp_path / "snap3.db")
        init_db(db_path)
        results = log_snapshot([], "NBA", db_path)
        assert results == []

    def test_flagged_movement_detected(self, tmp_path):
        db_path = str(tmp_path / "snap4.db")
        init_db(db_path)
        games1 = self._make_games()
        log_snapshot(games1, "NBA", db_path)

        # Move line significantly for Celtics spread
        games2 = self._make_games()
        games2[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] = -8.5  # moved 3 pts
        games2[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = -115
        results = log_snapshot(games2, "NBA", db_path)
        celtics_spread = next(
            (r for r in results if r.get("movement_delta") is not None
             and abs(r["movement_delta"]) >= MOVEMENT_THRESHOLD),
            None
        )
        assert celtics_spread is not None, "Expected at least one flagged movement"


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

class TestGetMovements:
    def test_returns_flagged_movements(self, tmp_path):
        db_path = str(tmp_path / "q.db")
        init_db(db_path)
        # Create and flag a movement
        conn = get_connection(db_path)
        upsert_line(conn, "e1", "NBA", "spread", "Celtics", "Heat @ Celtics", -4.5, -110)
        upsert_line(conn, "e1", "NBA", "spread", "Celtics", "Heat @ Celtics", -8.0, -115)
        conn.close()
        movements = get_movements(db_path, min_delta=3.0)
        assert len(movements) == 1
        assert abs(movements[0]["movement_delta"]) >= 3.0

    def test_sport_filter_applied(self, tmp_path):
        db_path = str(tmp_path / "q2.db")
        init_db(db_path)
        conn = get_connection(db_path)
        upsert_line(conn, "e2", "NBA", "spread", "Warriors", "Lakers @ Warriors", -3.5, -110)
        upsert_line(conn, "e2", "NBA", "spread", "Warriors", "Lakers @ Warriors", -7.0, -115)
        upsert_line(conn, "e3", "NCAAB", "spread", "Duke", "Virginia @ Duke", -4.5, -110)
        upsert_line(conn, "e3", "NCAAB", "spread", "Duke", "Virginia @ Duke", -8.0, -115)
        conn.close()
        nba_movements = get_movements(db_path, sport="NBA", min_delta=3.0)
        ncaab_movements = get_movements(db_path, sport="NCAAB", min_delta=3.0)
        assert all(m["sport"] == "NBA" for m in nba_movements)
        assert all(m["sport"] == "NCAAB" for m in ncaab_movements)


class TestGetLineHistory:
    def test_returns_all_lines_for_event(self, tmp_path):
        db_path = str(tmp_path / "lh.db")
        init_db(db_path)
        conn = get_connection(db_path)
        upsert_line(conn, "e10", "NBA", "spread", "Celtics", "Heat @ Celtics", -5.5, -110)
        upsert_line(conn, "e10", "NBA", "moneyline", "Celtics", "Heat @ Celtics", 0.0, -190)
        upsert_line(conn, "e10", "NBA", "total", "Over", "Heat @ Celtics", 215.5, -110)
        conn.close()
        history = get_line_history("e10", db_path=db_path)
        assert len(history) == 3

    def test_market_type_filter(self, tmp_path):
        db_path = str(tmp_path / "lh2.db")
        init_db(db_path)
        conn = get_connection(db_path)
        upsert_line(conn, "e11", "NBA", "spread", "Heat", "Heat @ Celtics", 5.5, -110)
        upsert_line(conn, "e11", "NBA", "moneyline", "Heat", "Heat @ Celtics", 0.0, 160)
        conn.close()
        spreads = get_line_history("e11", market_type="spread", db_path=db_path)
        assert len(spreads) == 1
        assert spreads[0]["market_type"] == "spread"


class TestGetOpenPricesForRlm:
    def test_returns_open_prices_dict(self, tmp_path):
        db_path = str(tmp_path / "rlm.db")
        init_db(db_path)
        conn = get_connection(db_path)
        upsert_line(conn, "e20", "NBA", "moneyline", "Celtics", "Heat @ Celtics", 0.0, -190)
        upsert_line(conn, "e20", "NBA", "moneyline", "Heat", "Heat @ Celtics", 0.0, 160)
        conn.close()
        prices = get_open_prices_for_rlm(db_path=db_path)
        assert "e20" in prices
        assert "Celtics" in prices["e20"]
        assert prices["e20"]["Celtics"] == -190


class TestCountSnapshots:
    def test_counts_correct(self, tmp_path):
        db_path = str(tmp_path / "cnt.db")
        init_db(db_path)
        conn = get_connection(db_path)
        upsert_line(conn, "e30", "NBA", "spread", "Warriors", "Lakers @ Warriors", -3.5, -110)
        upsert_line(conn, "e30", "NBA", "spread", "Warriors", "Lakers @ Warriors", -7.5, -115)  # flagged
        upsert_line(conn, "e31", "NBA", "total", "Over", "Bulls @ Knicks", 220.5, -110)
        conn.close()
        counts = count_snapshots(db_path)
        assert counts["total_lines"] == 2
        assert counts["distinct_events"] == 2
        assert counts["flagged"] == 1


# ---------------------------------------------------------------------------
# Bet log
# ---------------------------------------------------------------------------

class TestLogBet:
    def test_inserts_and_returns_id(self, tmp_path):
        db_path = str(tmp_path / "bet.db")
        init_db(db_path)
        bet_id = log_bet(
            sport="NBA", matchup="Heat @ Celtics", market_type="spread",
            target="Celtics -5.5", price=-110, edge_pct=0.05, kelly_size=0.25,
            stake=1.0, db_path=db_path,
        )
        assert isinstance(bet_id, int)
        assert bet_id > 0

    def test_bet_retrievable(self, tmp_path):
        db_path = str(tmp_path / "bet2.db")
        init_db(db_path)
        log_bet("NBA", "Heat @ Celtics", "spread", "Celtics -5.5",
                -110, 0.05, 0.25, db_path=db_path)
        bets = get_bets(db_path=db_path)
        assert len(bets) == 1
        assert bets[0]["target"] == "Celtics -5.5"

    def test_default_result_is_pending(self, tmp_path):
        db_path = str(tmp_path / "bet3.db")
        init_db(db_path)
        log_bet("NBA", "Heat @ Celtics", "moneyline", "Celtics ML",
                -190, 0.04, 0.15, db_path=db_path)
        bets = get_bets(db_path=db_path)
        assert bets[0]["result"] == "pending"


class TestUpdateBetResult:
    def test_win_updates_profit(self, tmp_path):
        db_path = str(tmp_path / "bet4.db")
        init_db(db_path)
        bet_id = log_bet("NBA", "Heat @ Celtics", "spread", "Celtics -5.5",
                         -110, 0.05, 0.25, db_path=db_path)
        update_bet_result(bet_id, "win", stake=1.0, db_path=db_path)
        bets = get_bets(db_path=db_path)
        assert bets[0]["result"] == "win"
        assert bets[0]["profit"] > 0  # won money

    def test_loss_updates_profit_negative(self, tmp_path):
        db_path = str(tmp_path / "bet5.db")
        init_db(db_path)
        bet_id = log_bet("NBA", "Heat @ Celtics", "spread", "Celtics -5.5",
                         -110, 0.05, 0.25, db_path=db_path)
        update_bet_result(bet_id, "loss", stake=1.0, db_path=db_path)
        bets = get_bets(db_path=db_path)
        assert bets[0]["result"] == "loss"
        assert bets[0]["profit"] == -1.0

    def test_clv_calculated_when_close_price_provided(self, tmp_path):
        db_path = str(tmp_path / "bet6.db")
        init_db(db_path)
        bet_id = log_bet("NBA", "Heat @ Celtics", "spread", "Celtics -5.5",
                         -110, 0.05, 0.25, db_path=db_path)
        # Bet at -110, closed at -120 → positive CLV (we got a better price)
        update_bet_result(bet_id, "win", stake=1.0, close_price=-120, db_path=db_path)
        bets = get_bets(db_path=db_path)
        assert bets[0]["clv"] > 0


class TestGetBets:
    def test_result_filter(self, tmp_path):
        db_path = str(tmp_path / "bet7.db")
        init_db(db_path)
        b1 = log_bet("NBA", "A @ B", "spread", "A -3.5", -110, 0.05, 0.25, db_path=db_path)
        b2 = log_bet("NBA", "C @ D", "spread", "C -5.5", -110, 0.06, 0.25, db_path=db_path)
        update_bet_result(b1, "win", 1.0, db_path=db_path)
        wins = get_bets(result_filter="win", db_path=db_path)
        pending = get_bets(result_filter="pending", db_path=db_path)
        assert len(wins) == 1
        assert len(pending) == 1

    def test_sport_filter(self, tmp_path):
        db_path = str(tmp_path / "bet8.db")
        init_db(db_path)
        log_bet("NBA", "A @ B", "spread", "A -3.5", -110, 0.05, 0.25, db_path=db_path)
        log_bet("NCAAB", "C @ D", "spread", "C +5.5", 110, 0.04, 0.15, db_path=db_path)
        nba = get_bets(sport_filter="NBA", db_path=db_path)
        assert len(nba) == 1
        assert nba[0]["sport"] == "NBA"


class TestGetPnlSummary:
    def test_empty_returns_zeros(self, tmp_path):
        db_path = str(tmp_path / "pnl.db")
        init_db(db_path)
        summary = get_pnl_summary(db_path)
        assert summary["total_bets"] == 0
        assert summary["total_profit"] == 0.0
        assert summary["win_rate"] == 0.0

    def test_pnl_computed_correctly(self, tmp_path):
        db_path = str(tmp_path / "pnl2.db")
        init_db(db_path)
        b1 = log_bet("NBA", "A @ B", "spread", "A -3.5", -110, 0.05, 0.25, db_path=db_path)
        b2 = log_bet("NBA", "C @ D", "spread", "C -5.5", -110, 0.06, 0.25, db_path=db_path)
        update_bet_result(b1, "win", stake=1.0, db_path=db_path)
        update_bet_result(b2, "loss", stake=1.0, db_path=db_path)
        summary = get_pnl_summary(db_path)
        assert summary["wins"] == 1
        assert summary["losses"] == 1
        assert summary["win_rate"] == 50.0
        # Win: +0.909, Loss: -1.0 → total ≈ -0.091
        assert summary["total_profit"] < 0  # slight net loss at -110 1W1L


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    sys.exit(result.returncode)
