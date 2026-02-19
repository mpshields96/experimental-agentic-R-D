"""
core/price_history_store.py — RLM 2.0: Persistent Open-Price Store (Session 8)
================================================================================
SQLite-backed store for first-ever-seen market prices across sessions.

The RLM problem with process-restarts:
  - math_engine._OPEN_PRICE_CACHE lives in memory only.
  - On every app restart, cache is cold → RLM needs 2 fetches in one session.
  - After a restart at 9am with game at 2pm: first fetch re-seeds "open" to 9am
    prices, not the real market open from days ago.

This module fixes it:
  - On every fetch: call integrate_with_session_cache(raw_games) — writes any
    new events to SQLite (first-ever-seen, never overwritten).
  - At session start: call inject_historical_prices_into_cache(raw_games) —
    seeds math_engine._OPEN_PRICE_CACHE with multi-day baseline prices.
  - Result: RLM detection is accurate even on the first fetch of a new process.

Schema: price_history table
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  event_id      TEXT NOT NULL
  side          TEXT NOT NULL       -- team name, "Over", or "Under"
  open_price    INTEGER NOT NULL    -- first-ever-seen American odds
  first_seen    TEXT NOT NULL       -- ISO 8601 UTC timestamp
  sport         TEXT DEFAULT ''     -- for purge targeting
  UNIQUE(event_id, side)            -- never overwrite

Wire-in sequence (scheduler._poll_all_sports or app startup):
  1. raw_games = fetch_batch_odds(...)
  2. integrate_with_session_cache(raw_games)    ← record new events
  3. inject_historical_prices_into_cache(raw_games)  ← seed math_engine cache
  4. cache_open_prices(raw_games)               ← existing call, unchanged

DO NOT add API calls or Streamlit imports to this file.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Default DB path — separate from line_history.db by design.
# price_history.db is append-only; line_history.db has upserts.
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "price_history.db"
)

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL,
    side        TEXT NOT NULL,
    open_price  INTEGER NOT NULL,
    first_seen  TEXT NOT NULL,
    sport       TEXT DEFAULT '',
    UNIQUE(event_id, side)
);

CREATE INDEX IF NOT EXISTS idx_ph_event
    ON price_history(event_id);

CREATE INDEX IF NOT EXISTS idx_ph_sport_seen
    ON price_history(sport, first_seen);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _db_path() -> str:
    return os.environ.get("PRICE_HISTORY_DB_PATH", _DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_price_history_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the price_history table. Safe to call multiple times.

    Should be called once at app startup, before integrate_with_session_cache.

    Args:
        db_path: Override DB file path (useful for testing).
    """
    conn = _get_conn(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("price_history DB initialized: %s", db_path or _db_path())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write: record new events (never overwrite existing)
# ---------------------------------------------------------------------------

def record_open_prices(
    event_id: str,
    sides: dict[str, int],
    sport: str = "",
    db_path: Optional[str] = None,
) -> int:
    """
    Write first-ever-seen prices for a single event.

    Uses INSERT OR IGNORE — if (event_id, side) already exists, skip.
    This is the core invariant: open price is never overwritten.

    Args:
        event_id: Odds API event identifier.
        sides:    Dict mapping side_name → American odds.
                  Keys: team names, "Over", "Under".
        sport:    Sport name for tracking/purge targeting.
        db_path:  Optional DB path override.

    Returns:
        Number of new rows inserted (0 if all already existed).

    >>> import os, tempfile
    >>> p = tempfile.mktemp(suffix=".db")
    >>> os.environ["PRICE_HISTORY_DB_PATH"] = p
    >>> init_price_history_db(p)
    >>> record_open_prices("ev001", {"TeamA": -110, "TeamB": 100}, "NBA", p)
    2
    >>> record_open_prices("ev001", {"TeamA": -115, "TeamB": 110}, "NBA", p)
    0
    """
    if not sides:
        return 0

    conn = _get_conn(db_path)
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    try:
        for side, price in sides.items():
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO price_history
                    (event_id, side, open_price, first_seen, sport)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, side, int(price), now, sport),
            )
            inserted += cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return inserted


def integrate_with_session_cache(
    raw_games: list[dict],
    sport: str = "",
    db_path: Optional[str] = None,
) -> int:
    """
    Scan raw_games and persist first-ever-seen prices to SQLite.

    Call this BEFORE cache_open_prices() each poll cycle.
    New events get their prices recorded. Existing events are skipped (INSERT OR IGNORE).

    This is the write half of RLM 2.0 — accumulates open prices over days.

    Args:
        raw_games: Raw game list from fetch_game_lines() or fetch_batch_odds value.
        sport:     Sport name for record tagging.
        db_path:   Optional DB path override.

    Returns:
        Total new (event_id, side) pairs written across all games.

    >>> import os, tempfile
    >>> p = tempfile.mktemp(suffix=".db")
    >>> init_price_history_db(p)
    >>> games = [{"id": "g1", "bookmakers": [{"key": "dk", "markets": [
    ...     {"key": "h2h", "outcomes": [
    ...         {"name": "Lakers", "price": -130},
    ...         {"name": "Celtics", "price": 110}
    ...     ]}
    ... ]}]}]
    >>> integrate_with_session_cache(games, "NBA", p)
    2
    >>> integrate_with_session_cache(games, "NBA", p)
    0
    """
    total_new = 0

    for game in raw_games:
        event_id = game.get("id", "")
        if not event_id:
            continue

        sides: dict[str, int] = {}
        for book in game.get("bookmakers", []):
            for market in book.get("markets", []):
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price")
                    if name and price is not None and name not in sides:
                        sides[name] = int(price)

        if sides:
            total_new += record_open_prices(event_id, sides, sport, db_path)

    return total_new


# ---------------------------------------------------------------------------
# Read: retrieve stored open price
# ---------------------------------------------------------------------------

def get_historical_open_price(
    event_id: str,
    side: str,
    db_path: Optional[str] = None,
) -> Optional[int]:
    """
    Return the first-ever-seen price for an event/side pair.

    Args:
        event_id: Odds API event ID.
        side:     Team name, "Over", or "Under".
        db_path:  Optional DB path override.

    Returns:
        American odds integer, or None if not recorded yet.

    >>> import os, tempfile
    >>> p = tempfile.mktemp(suffix=".db")
    >>> init_price_history_db(p)
    >>> _ = record_open_prices("ev001", {"Lakers": -130}, "NBA", p)
    >>> get_historical_open_price("ev001", "Lakers", p)
    -130
    >>> get_historical_open_price("ev001", "Celtics", p) is None
    True
    """
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT open_price FROM price_history WHERE event_id = ? AND side = ?",
            (event_id, side),
        ).fetchone()
        return int(row["open_price"]) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Seed: inject historical prices into the in-memory RLM cache
# ---------------------------------------------------------------------------

def inject_historical_prices_into_cache(
    raw_games: list[dict],
    db_path: Optional[str] = None,
) -> int:
    """
    Seed math_engine._OPEN_PRICE_CACHE with multi-day baseline prices.

    Call this AFTER integrate_with_session_cache() but BEFORE cache_open_prices().
    For each game in raw_games, if a historical open price exists in price_history.db,
    inject it into the math_engine cache (without overwriting existing cache entries).

    This is the read half of RLM 2.0 — makes the first fetch of a new session
    behave as if the process never restarted.

    Args:
        raw_games: Raw game list (used to enumerate known event IDs + sides).
        db_path:   Optional DB path override.

    Returns:
        Number of event IDs successfully seeded from history.
    """
    from core.math_engine import seed_open_prices_from_db

    seeded: dict[str, dict[str, int]] = {}

    for game in raw_games:
        event_id = game.get("id", "")
        if not event_id:
            continue

        prices: dict[str, int] = {}
        for book in game.get("bookmakers", []):
            for market in book.get("markets", []):
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = get_historical_open_price(event_id, name, db_path)
                    if name and price is not None and name not in prices:
                        prices[name] = price

        if prices:
            seeded[event_id] = prices

    if seeded:
        return seed_open_prices_from_db(seeded)
    return 0


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

def purge_old_events(days_old: int = 14, db_path: Optional[str] = None) -> int:
    """
    Delete events first seen more than `days_old` days ago.

    Prevents unbounded DB growth. Safe to run weekly.
    Never purges events whose games haven't started yet (based on first_seen only —
    commence_time not stored here; use 14-day conservative window).

    Args:
        days_old: Entries older than this many days are deleted.
        db_path:  Optional DB path override.

    Returns:
        Number of rows deleted.
    """
    from datetime import timedelta
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days_old)
    ).isoformat()

    conn = _get_conn(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM price_history WHERE first_seen < ?",
            (cutoff,),
        )
        conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("Purged %d old price_history entries (>%d days)", deleted, days_old)
        return deleted
    finally:
        conn.close()


def price_history_status(db_path: Optional[str] = None) -> str:
    """
    Return a one-line status string for logging and UI display.

    Args:
        db_path: Optional DB path override.

    Returns:
        E.g. "price_history: 142 events, 876 sides, oldest 2026-02-14T09:31:22+00:00"
    """
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT event_id) AS n_events, COUNT(*) AS n_sides, "
            "MIN(first_seen) AS oldest FROM price_history"
        ).fetchone()
        if not row or row["n_events"] == 0:
            return "price_history: empty"
        return (
            f"price_history: {row['n_events']} events, "
            f"{row['n_sides']} sides, "
            f"oldest {row['oldest']}"
        )
    finally:
        conn.close()


def get_all_open_prices(
    sport: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict[str, dict[str, int]]:
    """
    Return all stored open prices as a nested dict.

    Format: { event_id: { side: open_price } }

    Used by get_open_prices_for_rlm() replacement — returns the full
    historical baseline, not just what line_logger has seen this session.

    Args:
        sport:   Filter by sport. None = all sports.
        db_path: Optional DB path override.

    Returns:
        Nested dict mapping event_id → side → open_price (int).
    """
    conn = _get_conn(db_path)
    try:
        if sport:
            rows = conn.execute(
                "SELECT event_id, side, open_price FROM price_history WHERE sport = ?",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT event_id, side, open_price FROM price_history"
            ).fetchall()

        result: dict[str, dict[str, int]] = {}
        for row in rows:
            eid = row["event_id"]
            if eid not in result:
                result[eid] = {}
            result[eid][row["side"]] = int(row["open_price"])
        return result
    finally:
        conn.close()
