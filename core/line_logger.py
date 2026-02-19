"""
core/line_logger.py — Titanium-Agentic
========================================
SQLite persistent line history storage. No UI, no API calls, no math.

This is the PRIMARY new capability vs V36.1.

Responsibilities:
- Initialize SQLite schema (WAL mode enabled for safe concurrent access)
- Log line snapshots every 5 minutes (called by scheduler)
- Delta detection: flag movement > 3 points between snapshots
- Query line history for analysis tab (CLV, RLM visualization)
- Return line movement data for active (non-passive) RLM detection

Schema: line_history table
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  event_id    TEXT NOT NULL
  sport       TEXT NOT NULL
  market_type TEXT NOT NULL     -- "spread", "total", "moneyline"
  team        TEXT NOT NULL     -- team name or "Over"/"Under"
  matchup     TEXT NOT NULL     -- "Away @ Home"
  open_line   REAL              -- first recorded line value
  current_line REAL             -- most recent line value
  open_price  INTEGER           -- first recorded American odds
  current_price INTEGER         -- most recent American odds
  movement_delta REAL           -- current_line - open_line (>3 = flagged)
  price_delta INTEGER           -- current_price - open_price
  commence_time TEXT            -- ISO 8601 game start time
  first_seen  TEXT NOT NULL     -- ISO 8601 UTC when first logged
  last_updated TEXT NOT NULL    -- ISO 8601 UTC when last updated
  n_snapshots INTEGER DEFAULT 1 -- how many times we've polled this line

Schema: bet_log table (Tab 4 — Bet Tracker)
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  logged_at   TEXT NOT NULL     -- ISO 8601 UTC
  sport       TEXT NOT NULL
  matchup     TEXT NOT NULL
  market_type TEXT NOT NULL
  target      TEXT NOT NULL     -- e.g. "Duke -4.5"
  price       INTEGER NOT NULL  -- American odds at bet time
  edge_pct    REAL              -- edge% at bet time
  kelly_size  REAL              -- recommended Kelly units
  stake       REAL DEFAULT 0.0  -- actual units wagered
  result      TEXT DEFAULT 'pending'  -- "pending", "win", "loss", "void"
  profit      REAL DEFAULT 0.0  -- P&L (positive = win, negative = loss)
  clv         REAL DEFAULT 0.0  -- closing line value (filled post-game)
  close_price INTEGER           -- closing market price (filled post-game)
  notes       TEXT DEFAULT ''

DO NOT add API calls or Streamlit calls to this file.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Default DB path — can be overridden in tests
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "line_history.db"
)

# Movement threshold: flag lines that moved more than this many points
MOVEMENT_THRESHOLD = 3.0

# Price movement threshold: flag when implied prob shift >= this value
PRICE_SHIFT_THRESHOLD = 0.03  # 3% — same as RLM threshold


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

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

CREATE INDEX IF NOT EXISTS idx_line_history_event
    ON line_history(event_id);

CREATE INDEX IF NOT EXISTS idx_line_history_sport
    ON line_history(sport, market_type);

CREATE INDEX IF NOT EXISTS idx_line_history_movement
    ON line_history(movement_delta);

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

CREATE INDEX IF NOT EXISTS idx_bet_log_sport
    ON bet_log(sport, logged_at);

CREATE INDEX IF NOT EXISTS idx_bet_log_result
    ON bet_log(result);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Open a SQLite connection with WAL mode.

    WAL mode: enables safe concurrent reads+writes (critical for scheduler).
    Row factory set to sqlite3.Row for dict-like access.

    Args:
        db_path: Path to the SQLite DB file.
                 Defaults to data/line_history.db in the sandbox root.

    Returns:
        sqlite3.Connection object.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    # Ensure the data directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the database schema. Safe to call multiple times (CREATE IF NOT EXISTS).

    Should be called once at app startup before the scheduler begins.

    Args:
        db_path: Path to the SQLite DB file. Defaults to DEFAULT_DB_PATH.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized: %s", db_path or DEFAULT_DB_PATH)
    except sqlite3.Error as exc:
        logger.error("Schema init failed: %s", exc)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Line history — write
# ---------------------------------------------------------------------------

def upsert_line(
    conn: sqlite3.Connection,
    event_id: str,
    sport: str,
    market_type: str,
    team: str,
    matchup: str,
    line: float,
    price: int,
    commence_time: str = "",
) -> dict:
    """
    Insert or update a line snapshot in line_history.

    On first insert: open_line = current_line, movement_delta = 0.
    On update: update current_line and movement_delta = current - open.
    Increment n_snapshots on every call.

    Args:
        conn:          Active SQLite connection.
        event_id:      Odds API event identifier.
        sport:         Sport name (e.g. "NBA").
        market_type:   "spread", "total", "moneyline".
        team:          Team name or "Over"/"Under".
        matchup:       "Away @ Home".
        line:          Current numeric line value.
        price:         Current American odds.
        commence_time: ISO 8601 game start time.

    Returns:
        Dict with keys: event_id, movement_delta, price_delta, flagged,
        is_new (True if first insert).
    """
    now = datetime.now(timezone.utc).isoformat()

    # Check if this line already exists
    existing = conn.execute(
        "SELECT id, open_line, open_price, n_snapshots FROM line_history "
        "WHERE event_id = ? AND market_type = ? AND team = ?",
        (event_id, market_type, team),
    ).fetchone()

    if existing is None:
        # First snapshot — insert
        conn.execute(
            """
            INSERT INTO line_history
                (event_id, sport, market_type, team, matchup,
                 open_line, current_line, open_price, current_price,
                 movement_delta, price_delta, commence_time,
                 first_seen, last_updated, n_snapshots)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0, ?, ?, ?, 1)
            """,
            (event_id, sport, market_type, team, matchup,
             line, line, price, price,
             commence_time, now, now),
        )
        conn.commit()
        return {
            "event_id": event_id,
            "movement_delta": 0.0,
            "price_delta": 0,
            "flagged": False,
            "is_new": True,
        }
    else:
        open_line = existing["open_line"]
        open_price = existing["open_price"]
        movement_delta = line - open_line if open_line is not None else 0.0
        price_delta = price - open_price if open_price is not None else 0

        conn.execute(
            """
            UPDATE line_history SET
                current_line = ?,
                current_price = ?,
                movement_delta = ?,
                price_delta = ?,
                last_updated = ?,
                n_snapshots = n_snapshots + 1
            WHERE event_id = ? AND market_type = ? AND team = ?
            """,
            (line, price, movement_delta, price_delta, now,
             event_id, market_type, team),
        )
        conn.commit()

        flagged = abs(movement_delta) >= MOVEMENT_THRESHOLD
        return {
            "event_id": event_id,
            "movement_delta": movement_delta,
            "price_delta": price_delta,
            "flagged": flagged,
            "is_new": False,
        }


def log_snapshot(
    games: list[dict],
    sport: str,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Process a full game list from odds_fetcher and upsert all line snapshots.

    Called by the APScheduler every 5 minutes per sport.
    Extracts all markets (spreads, moneylines, totals) from each game
    and upserts them individually.

    Args:
        games:    Raw game list from fetch_game_lines().
        sport:    Sport name (e.g. "NBA").
        db_path:  Optional DB path override.

    Returns:
        List of result dicts for each upserted line (includes flagged movements).
    """
    if not games:
        return []

    conn = get_connection(db_path)
    results = []

    try:
        for game in games:
            event_id = game.get("id", "")
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            matchup = f"{away} @ {home}"
            commence_time = game.get("commence_time", "")
            bookmakers = game.get("bookmakers", [])

            if not event_id or not bookmakers:
                continue

            # Extract best price for each market/side across all books
            seen: dict[tuple, tuple] = {}  # (market_type, team) → (best_price, line)

            for book in bookmakers:
                for market in book.get("markets", []):
                    mkt_key = market.get("key", "")
                    if mkt_key not in ("spreads", "h2h", "totals"):
                        continue

                    market_type = {
                        "spreads": "spread",
                        "h2h": "moneyline",
                        "totals": "total",
                    }[mkt_key]

                    for outcome in market.get("outcomes", []):
                        team_name = outcome.get("name", "")
                        price = outcome.get("price")
                        line_val = outcome.get("point", 0.0)

                        if not team_name or price is None:
                            continue

                        key = (market_type, team_name)
                        current_best = seen.get(key)
                        if current_best is None or price > current_best[0]:
                            seen[key] = (price, line_val or 0.0)

            # Upsert each (market_type, team) combination
            for (market_type, team_name), (price, line_val) in seen.items():
                result = upsert_line(
                    conn=conn,
                    event_id=event_id,
                    sport=sport,
                    market_type=market_type,
                    team=team_name,
                    matchup=matchup,
                    line=line_val,
                    price=price,
                    commence_time=commence_time,
                )
                results.append(result)

    except sqlite3.Error as exc:
        logger.error("Error logging snapshot for %s: %s", sport, exc)
    finally:
        conn.close()

    flagged = sum(1 for r in results if r.get("flagged"))
    if flagged:
        logger.info("Logged %s lines for %s — %s flagged for movement", len(results), sport, flagged)

    return results


# ---------------------------------------------------------------------------
# Line history — read
# ---------------------------------------------------------------------------

def get_movements(
    db_path: Optional[str] = None,
    sport: Optional[str] = None,
    min_delta: float = MOVEMENT_THRESHOLD,
    limit: int = 100,
) -> list[dict]:
    """
    Query flagged line movements (movement_delta >= min_delta).

    Used by the analysis tab to surface significant line movement.

    Args:
        db_path:   Optional DB path override.
        sport:     Filter by sport. None = all sports.
        min_delta: Minimum absolute movement to include. Default = 3.0.
        limit:     Maximum rows returned.

    Returns:
        List of dicts (from sqlite3.Row), sorted by abs(movement_delta) descending.
    """
    conn = get_connection(db_path)
    try:
        if sport:
            rows = conn.execute(
                """
                SELECT * FROM line_history
                WHERE sport = ? AND ABS(movement_delta) >= ?
                ORDER BY ABS(movement_delta) DESC
                LIMIT ?
                """,
                (sport, min_delta, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM line_history
                WHERE ABS(movement_delta) >= ?
                ORDER BY ABS(movement_delta) DESC
                LIMIT ?
                """,
                (min_delta, limit),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_upcoming_movements(
    db_path: Optional[str] = None,
    sport: Optional[str] = None,
    min_delta: float = MOVEMENT_THRESHOLD,
    limit: int = 100,
) -> list[dict]:
    """
    Query significant line movements for UPCOMING games only.

    Filters out games whose commence_time has already passed, which removes
    the extreme locked-line prices (e.g. -20000) that appear post-game and
    would pollute RLM analysis with false signals.

    Args:
        db_path:   Optional DB path override.
        sport:     Filter by sport. None = all sports.
        min_delta: Minimum absolute movement to include. Default = 3.0.
        limit:     Maximum rows returned.

    Returns:
        List of dicts sorted by abs(movement_delta) descending.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        conditions = ["ABS(movement_delta) >= ?", "(commence_time = '' OR commence_time > ?)"]
        params: list = [min_delta, now]

        if sport:
            conditions.append("sport = ?")
            params.append(sport)

        params.append(limit)
        where = " AND ".join(conditions)

        rows = conn.execute(
            f"""
            SELECT * FROM line_history
            WHERE {where}
            ORDER BY ABS(movement_delta) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_line_history(
    event_id: str,
    market_type: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Get all tracked lines for a specific event.

    Args:
        event_id:    Odds API event ID.
        market_type: Optional filter: "spread", "total", "moneyline".
        db_path:     Optional DB path override.

    Returns:
        List of row dicts for this event.
    """
    conn = get_connection(db_path)
    try:
        if market_type:
            rows = conn.execute(
                "SELECT * FROM line_history WHERE event_id = ? AND market_type = ?",
                (event_id, market_type),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM line_history WHERE event_id = ?",
                (event_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_open_prices_for_rlm(
    sport: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict[str, dict[str, int]]:
    """
    Build an open price dict from line_history for active RLM detection.

    This enables the math_engine RLM cache to be pre-populated from persistent
    storage on app restart (rather than only from the current session).

    Returns:
        Dict: { event_id: { team_name: open_price, ... } }
    """
    conn = get_connection(db_path)
    try:
        if sport:
            rows = conn.execute(
                "SELECT event_id, team, open_price FROM line_history WHERE sport = ?",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT event_id, team, open_price FROM line_history"
            ).fetchall()

        result: dict[str, dict[str, int]] = {}
        for row in rows:
            eid = row["event_id"]
            if eid not in result:
                result[eid] = {}
            if row["open_price"] is not None:
                result[eid][row["team"]] = row["open_price"]

        return result
    finally:
        conn.close()


def count_snapshots(db_path: Optional[str] = None) -> dict[str, int]:
    """
    Return counts of tracked events, lines, and flagged movements.

    Used by the line history tab header for status display.
    """
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM line_history").fetchone()[0]
        events = conn.execute(
            "SELECT COUNT(DISTINCT event_id) FROM line_history"
        ).fetchone()[0]
        flagged = conn.execute(
            "SELECT COUNT(*) FROM line_history WHERE ABS(movement_delta) >= ?",
            (MOVEMENT_THRESHOLD,),
        ).fetchone()[0]
        return {"total_lines": total, "distinct_events": events, "flagged": flagged}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bet log — write
# ---------------------------------------------------------------------------

def log_bet(
    sport: str,
    matchup: str,
    market_type: str,
    target: str,
    price: int,
    edge_pct: float,
    kelly_size: float,
    stake: float = 0.0,
    notes: str = "",
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a new bet into bet_log. Returns the new row ID.

    Args:
        sport, matchup, market_type, target: Bet identification.
        price:      American odds at bet time.
        edge_pct:   Edge percentage at bet time.
        kelly_size: Recommended Kelly units at bet time.
        stake:      Actual units wagered (0 = not yet set).
        notes:      Optional free-form notes.
        db_path:    Optional DB path override.

    Returns:
        Integer row ID of the new bet record.
    """
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor = conn.execute(
            """
            INSERT INTO bet_log
                (logged_at, sport, matchup, market_type, target,
                 price, edge_pct, kelly_size, stake, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, sport, matchup, market_type, target,
             price, edge_pct, kelly_size, stake, notes),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as exc:
        logger.error("log_bet failed: %s", exc)
        raise
    finally:
        conn.close()


def update_bet_result(
    bet_id: int,
    result: str,
    stake: float,
    close_price: Optional[int] = None,
    db_path: Optional[str] = None,
) -> None:
    """
    Update a bet with its outcome.

    Args:
        bet_id:      Row ID from log_bet().
        result:      "win", "loss", or "void".
        stake:       Actual units wagered.
        close_price: Closing market price (for CLV calculation).
        db_path:     Optional DB path override.
    """
    from core.math_engine import calculate_profit, calculate_clv

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT price, edge_pct FROM bet_log WHERE id = ?",
            (bet_id,),
        ).fetchone()

        if row is None:
            logger.error("Bet ID %d not found in bet_log", bet_id)
            return

        original_price = row["price"]

        # Calculate profit
        if result == "win":
            profit = calculate_profit(stake, original_price)
        elif result == "loss":
            profit = -stake
        else:
            profit = 0.0

        # Calculate CLV if closing price provided
        clv = 0.0
        if close_price and close_price != 0:
            clv = calculate_clv(
                open_price=original_price,
                close_price=close_price,
                bet_price=original_price,
            )

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE bet_log SET
                result = ?, stake = ?, profit = ?,
                clv = ?, close_price = ?
            WHERE id = ?
            """,
            (result, stake, profit, clv, close_price or 0, bet_id),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("update_bet_result failed: %s", exc)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bet log — read
# ---------------------------------------------------------------------------

def get_bets(
    result_filter: Optional[str] = None,
    sport_filter: Optional[str] = None,
    limit: int = 200,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Query the bet log.

    Args:
        result_filter: "pending", "win", "loss", "void", or None (all).
        sport_filter:  Sport name or None (all).
        limit:         Max rows returned.
        db_path:       Optional DB path override.

    Returns:
        List of bet dicts, sorted by logged_at descending.
    """
    conn = get_connection(db_path)
    try:
        conditions = []
        params = []

        if result_filter:
            conditions.append("result = ?")
            params.append(result_filter)
        if sport_filter:
            conditions.append("sport = ?")
            params.append(sport_filter)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM bet_log {where} ORDER BY logged_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_pnl_summary(db_path: Optional[str] = None) -> dict:
    """
    Compute P&L summary stats from the bet log.

    Returns:
        Dict with: total_bets, wins, losses, pending, total_profit,
                   roi_pct, avg_clv, win_rate.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT result, profit, stake, clv FROM bet_log"
        ).fetchall()

        total_bets = len(rows)
        wins = sum(1 for r in rows if r["result"] == "win")
        losses = sum(1 for r in rows if r["result"] == "loss")
        pending = sum(1 for r in rows if r["result"] == "pending")
        total_profit = sum(r["profit"] for r in rows)
        total_stake = sum(r["stake"] for r in rows if r["result"] in ("win", "loss"))
        roi_pct = (total_profit / total_stake * 100) if total_stake > 0 else 0.0
        clv_values = [r["clv"] for r in rows if r["clv"] != 0.0]
        avg_clv = sum(clv_values) / len(clv_values) if clv_values else 0.0
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

        return {
            "total_bets": total_bets,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "total_profit": round(total_profit, 2),
            "roi_pct": round(roi_pct, 2),
            "avg_clv": round(avg_clv, 4),
            "win_rate": round(win_rate, 1),
        }
    finally:
        conn.close()
