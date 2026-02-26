"""
core/odds_fetcher.py — Titanium-Agentic
=========================================
All Odds API calls live here. No math, no UI, no file I/O.

Responsibilities:
- Authenticate with The Odds API (key from environment)
- Fetch game lines for all supported sports
- Batch fetch across sports with controlled API quota usage
- Track API quota across the session
- Open price caching support (calls math_engine.cache_open_prices)
- Exponential backoff on failures (max 3 retries)

API base URL: https://api.the-odds-api.com/v4/sports
Regions: us | Format: american
Book preference: DraftKings → FanDuel → BetMGM → BetRivers → Caesars

DO NOT add betting math or Streamlit calls to this file.
NEVER hardcode API keys. Use os.environ.get("ODDS_API_KEY").
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, date, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4/sports"

# ---------------------------------------------------------------------------
# Quota budget constants
#
# PERMANENT USER DIRECTIVE (2026-02-24): NEVER exceed 1,000 API credits per day.
# This applies to ALL usage — live fetches, testing, experiments. No exceptions.
#
# Subscription: 20,000 credits/month ($30/month plan)
# Monthly target: ≤ 10,000 credits/month (50% = always safe)
#
#   DAILY_CREDIT_CAP           — HARD limit: never exceed 1,000 credits per calendar day (UTC)
#   SESSION_CREDIT_SOFT_LIMIT  — warn in logs when session usage hits this
#   SESSION_CREDIT_HARD_STOP   — stop ALL fetches for the session when hit
#   BILLING_RESERVE            — global floor: never let remaining drop below this
#
# Math: 10,000 / 30 days = ~333/day. DAILY_CREDIT_CAP=300 = right at monthly target.
# Full 12-sport scan ≈ 15-20 credits. 300/day ≈ 15-20 full scans → plenty for normal use.
# BILLING_RESERVE=150 ensures buffer on any key (subscription or test).
# ---------------------------------------------------------------------------
DAILY_CREDIT_CAP: int = 300           # ~10 full 12-sport scans/day. Conservative ceiling.
SESSION_CREDIT_SOFT_LIMIT: int = 120  # Warn after ~6 full scans in one session
SESSION_CREDIT_HARD_STOP: int = 200   # Hard stop — ~10 full scans per session max
BILLING_RESERVE: int = 150            # Never drop below 150 remaining (any key)

# ---------------------------------------------------------------------------
# Daily budget constants — dynamic allowance spreading across billing period
# ---------------------------------------------------------------------------
SUBSCRIPTION_CREDITS: int = 20_000   # Full monthly subscription (credits/billing period)
BILLING_DAY: int = 1                 # Day-of-month billing resets (1st of each month)
# Monthly budget = SUBSCRIPTION_CREDITS * 0.50 = 10,000 (50% of subscription).
# Daily allowance = remaining monthly budget / days until next billing day.
# Recalculated on each update() call — self-adjusting as the month progresses.
_DAILY_BUDGET_FRACTION: float = 0.50
_DAILY_SOFT_FRACTION: float = 0.80   # 80% of daily allowance → soft warning
_DEFAULT_CREDIT_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "credit_log.db"
)

# ---------------------------------------------------------------------------
# Daily credit log — persisted across restarts
# ---------------------------------------------------------------------------

_DAILY_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "daily_quota.json")


class DailyCreditLog:
    """Persist daily credit usage to a JSON file so the cap survives app restarts.

    Resets automatically at midnight UTC when the date changes.
    Thread-safe for single-process use (Streamlit/APScheduler share one process).
    """

    def __init__(self, log_path: str = _DAILY_LOG_PATH) -> None:
        self._path = log_path
        self._data = self._load()

    def _today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> dict:
        today = self._today_str()
        try:
            with open(self._path) as f:
                data = json.load(f)
            if data.get("date") == today:
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        # New day or corrupt/missing file — reset
        return {"date": today, "start_remaining": None, "used_today": 0}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._data, f)
        except OSError as exc:
            logger.warning("DailyCreditLog._save failed: %s", exc)

    def record(self, remaining: int) -> None:
        """Update daily usage from a fresh API remaining count."""
        today = self._today_str()
        if today != self._data.get("date"):
            # Midnight rollover — reset for new day
            self._data = {"date": today, "start_remaining": remaining, "used_today": 0}
        elif self._data["start_remaining"] is None:
            self._data["start_remaining"] = remaining
            self._data["used_today"] = 0
        else:
            used = self._data["start_remaining"] - remaining
            self._data["used_today"] = max(0, used)
        self._save()

    def is_daily_cap_hit(self) -> bool:
        """Return True if today's usage has reached DAILY_CREDIT_CAP."""
        return self._data.get("used_today", 0) >= DAILY_CREDIT_CAP

    def used_today(self) -> int:
        return self._data.get("used_today", 0)

    def report(self) -> str:
        cap_warn = " ⛔DAILY_CAP" if self.is_daily_cap_hit() else ""
        return f"daily={self.used_today()}/{DAILY_CREDIT_CAP}{cap_warn}"

# ---------------------------------------------------------------------------
# Credit ledger — SQLite-backed daily record (survives restarts + month boundaries)
# ---------------------------------------------------------------------------

class CreditLedger:
    """SQLite-backed daily credit ledger for the dynamic daily allowance system.

    Schema: credit_log(date TEXT PK, used INT, remaining INT, allowance INT)

    PRECONDITION: data/ directory must be writable. Failures are non-fatal (warn + skip).
    POSTCONDITION: Each record() call upserts one row per UTC date.

    Implementation note: SQLite :memory: databases are per-connection — data is lost when
    a connection closes. For :memory: paths (tests), we store a single persistent connection
    as self._mem_conn. For file paths (production), we open/close on every call (WAL-safe).
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS credit_log (
        date      TEXT PRIMARY KEY,
        used      INTEGER NOT NULL DEFAULT 0,
        remaining INTEGER,
        allowance INTEGER
    );
    """

    def __init__(self, db_path: str = _DEFAULT_CREDIT_LOG_PATH) -> None:
        self._path = db_path
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            # Keep one persistent connection so in-memory data survives across calls.
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.executescript(self._SCHEMA)
        else:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
            with sqlite3.connect(self._path) as conn:
                conn.executescript(self._SCHEMA)
        except (sqlite3.OperationalError, OSError) as exc:
            logger.warning("CreditLedger._ensure_schema failed: %s", exc)

    def record(self, date_str: str, used: int, remaining: Optional[int], allowance: int) -> None:
        """Upsert today's credit record. Non-fatal on any DB error."""
        sql = """INSERT INTO credit_log(date, used, remaining, allowance)
                 VALUES(?,?,?,?)
                 ON CONFLICT(date) DO UPDATE SET
                     used=excluded.used,
                     remaining=excluded.remaining,
                     allowance=excluded.allowance"""
        try:
            if self._mem_conn is not None:
                self._mem_conn.execute(sql, (date_str, used, remaining, allowance))
                self._mem_conn.commit()
            else:
                with sqlite3.connect(self._path) as conn:
                    conn.execute(sql, (date_str, used, remaining, allowance))
        except (sqlite3.OperationalError, OSError) as exc:
            logger.warning("CreditLedger.record failed: %s", exc)

    def get_today_allowance(self, today_str: Optional[str] = None) -> Optional[int]:
        """Return stored allowance for today's date, or None if not yet recorded."""
        if today_str is None:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            if self._mem_conn is not None:
                row = self._mem_conn.execute(
                    "SELECT allowance FROM credit_log WHERE date=?", (today_str,)
                ).fetchone()
            else:
                with sqlite3.connect(self._path) as conn:
                    row = conn.execute(
                        "SELECT allowance FROM credit_log WHERE date=?", (today_str,)
                    ).fetchone()
            return row[0] if row else None
        except (sqlite3.OperationalError, OSError):
            return None


# Book preference order — DraftKings first, then fallbacks
PREFERRED_BOOKS = ["draftkings", "fanduel", "betmgm", "betrivers", "caesars"]

# Market strings per sport key.
# NOTE: player props NOT supported on bulk endpoint — confirmed 422 Feb 2026.
# Soccer: spreads cause 422 on bulk endpoint — h2h,totals only.
# Tennis: h2h only — spreads not offered; totals rarely posted and highly variable.
# baseball_mlb: added for MLB season starting Mar 27, 2026.
MARKETS: dict[str, str] = {
    "basketball_nba":               "h2h,spreads,totals",
    "americanfootball_nfl":         "h2h,spreads,totals",
    "americanfootball_ncaaf":       "h2h,spreads,totals",
    "basketball_ncaab":             "h2h,spreads,totals",
    "icehockey_nhl":                "h2h,spreads,totals",
    "baseball_mlb":                 "h2h,spreads,totals",
    "soccer_epl":                   "h2h,totals",
    "soccer_france_ligue_one":      "h2h,totals",
    "soccer_germany_bundesliga":    "h2h,totals",
    "soccer_italy_serie_a":         "h2h,totals",
    "soccer_spain_la_liga":         "h2h,totals",
    "soccer_usa_mls":               "h2h,totals",
}

# Tennis market string — applied to ALL tennis_atp_* and tennis_wta_* sport keys.
# h2h only: spreads not available, totals (game lines) are rarely posted pre-match.
TENNIS_MARKETS = "h2h"

# Friendly sport name → API sport key (static sports only)
SPORT_KEYS: dict[str, str] = {
    "NBA":          "basketball_nba",
    "NFL":          "americanfootball_nfl",
    "NCAAF":        "americanfootball_ncaaf",
    "NCAAB":        "basketball_ncaab",
    "NHL":          "icehockey_nhl",
    "MLB":          "baseball_mlb",
    "EPL":          "soccer_epl",
    "LIGUE1":       "soccer_france_ligue_one",
    "BUNDESLIGA":   "soccer_germany_bundesliga",
    "SERIE_A":      "soccer_italy_serie_a",
    "LA_LIGA":      "soccer_spain_la_liga",
    "MLS":          "soccer_usa_mls",
}

# Active sports — built from SPORT_KEYS keys. Update when sports go in/out of season.
# Tennis NOT in ACTIVE_SPORTS — dynamically discovered via fetch_active_tennis_keys().
ACTIVE_SPORTS = list(SPORT_KEYS.keys())


# ---------------------------------------------------------------------------
# Quota tracker
# ---------------------------------------------------------------------------

class QuotaTracker:
    """Track API usage across the session and enforce credit budget limits.

    Three independent guards (all checked in is_session_hard_stop):
      1. daily_log.is_daily_cap_hit()             → PERMANENT: ≤1,000 credits/day
      2. session_used >= SESSION_CREDIT_HARD_STOP  → per-process session cap
      3. remaining < BILLING_RESERVE               → global billing floor

    session_used resets to 0 on process restart (not persisted — intentional).
    daily_log persists to data/daily_quota.json and resets at midnight UTC.
    """

    def __init__(self) -> None:
        self.used: int = 0          # cumulative used across billing period (from API)
        self.remaining: Optional[int] = None   # remaining in billing period (from API)
        self.last_cost: int = 0     # cost of last single call
        self.session_used: int = 0  # credits consumed THIS session (resets on restart)
        self.daily_log: DailyCreditLog = DailyCreditLog()
        self.credit_ledger: CreditLedger = CreditLedger()

    def update(self, headers: dict) -> None:
        try:
            prev_remaining = self.remaining
            self.remaining = int(headers.get("x-requests-remaining", self.remaining or 0))
            self.used = int(headers.get("x-requests-used", self.used))
            self.last_cost = int(headers.get("x-requests-last", 0))
            # Track session spend from delta in remaining (robust to API gaps)
            if prev_remaining is not None and self.remaining is not None:
                delta = prev_remaining - self.remaining
                if delta > 0:
                    self.session_used += delta
            elif self.last_cost > 0:
                self.session_used += self.last_cost
            # Update daily log (JSON) and credit ledger (SQLite)
            self.daily_log.record(self.remaining)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self.credit_ledger.record(
                today_str,
                self.daily_log.used_today(),
                self.remaining,
                self.daily_allowance(),
            )
        except (ValueError, TypeError):
            pass

    def report(self) -> str:
        soft_warn = " SOFT_LIMIT" if self.session_used >= SESSION_CREDIT_SOFT_LIMIT else ""
        hard_stop = " HARD_STOP" if self.is_session_hard_stop() else ""
        allowance = self.daily_allowance()
        used_today = self.daily_log.used_today()
        daily_pct = f"{int(used_today / allowance * 100)}%" if allowance > 0 else "?%"
        daily_flags = ""
        if self.is_daily_hard_stop():
            daily_flags = " ⛔DAILY_HARD"
        elif self.is_daily_soft_limit():
            daily_flags = " ⚠DAILY_SOFT"
        return (
            f"API quota | used={self.used} "
            f"session={self.session_used}(/{SESSION_CREDIT_HARD_STOP}){soft_warn}{hard_stop} "
            f"remaining={self.remaining} "
            f"last_call={self.last_cost} | "
            f"{self.daily_log.report()} allowance={allowance}({daily_pct}){daily_flags}"
        )

    def _days_until_billing(self, _today: Optional[date] = None) -> int:
        """Days from today (inclusive) until next billing day.

        PRECONDITION: BILLING_DAY is a valid day-of-month (1-28).
        Accepts optional _today injection for test isolation.
        """
        today = _today or datetime.now(timezone.utc).date()
        if today.day < BILLING_DAY:
            next_billing = today.replace(day=BILLING_DAY)
        elif today.month == 12:
            next_billing = date(today.year + 1, 1, BILLING_DAY)
        else:
            next_billing = date(today.year, today.month + 1, BILLING_DAY)
        return max(1, (next_billing - today).days)

    def daily_allowance(self, _today: Optional[date] = None) -> int:
        """Compute today's recommended daily credit allowance.

        PRECONDITION:
            self.used is set from x-requests-used API header (billing period total).
            If self.used == 0 (no API call yet), allowance is estimated from full budget.
        Formula:
            monthly_budget = SUBSCRIPTION_CREDITS * _DAILY_BUDGET_FRACTION
            remaining_budget = max(0, monthly_budget - self.used)
            allowance = max(1, remaining_budget // days_until_billing)
        """
        monthly_budget = int(SUBSCRIPTION_CREDITS * _DAILY_BUDGET_FRACTION)
        remaining_budget = max(0, monthly_budget - self.used)
        return max(1, remaining_budget // self._days_until_billing(_today))

    def is_daily_soft_limit(self, _today: Optional[date] = None) -> bool:
        """Return True if today's usage has reached 80% of the daily allowance.

        Soft limit: logs a warning but does NOT stop fetches.
        POSTCONDITION: Does not mutate any state.
        """
        used_today = self.daily_log.used_today()
        return used_today >= int(self.daily_allowance(_today) * _DAILY_SOFT_FRACTION)

    def is_daily_hard_stop(self, _today: Optional[date] = None) -> bool:
        """Return True if today's usage has reached 100% of the daily allowance.

        Hard stop: halts all fetches for the remainder of the UTC day.
        POSTCONDITION: Does not mutate any state.
        """
        return self.daily_log.used_today() >= self.daily_allowance(_today)

    def is_low(self, threshold: int = BILLING_RESERVE) -> bool:
        """Return True if billing-period remaining is below threshold.

        Default threshold is BILLING_RESERVE (1,000) — the global floor.
        Pass a smaller threshold for intermediate checks.
        """
        if self.remaining is None:
            return False
        return self.remaining < threshold

    def is_session_soft_limit(self) -> bool:
        """Return True if session has consumed >= SESSION_CREDIT_SOFT_LIMIT credits."""
        return self.session_used >= SESSION_CREDIT_SOFT_LIMIT

    def is_session_hard_stop(self) -> bool:
        """Return True if session must stop ALL fetches.

        Hard stops (any one triggers):
          1. Daily cap hit: today's usage >= DAILY_CREDIT_CAP — absolute PERMANENT rule
          2. Session cap hit: session_used >= SESSION_CREDIT_HARD_STOP
          3. Billing floor: remaining < BILLING_RESERVE
          4. Daily budget exhausted: today's usage >= daily_allowance()
        """
        if self.daily_log.is_daily_cap_hit():
            logger.warning(
                "DAILY_CREDIT_CAP hit — used %d/%d credits today (UTC). No fetches until midnight.",
                self.daily_log.used_today(), DAILY_CREDIT_CAP,
            )
            return True
        if self.session_used >= SESSION_CREDIT_HARD_STOP:
            return True
        if self.is_low(BILLING_RESERVE):
            return True
        if self.is_daily_hard_stop():
            logger.warning(
                "Daily budget exhausted — used %d/%d allowance today (UTC). No fetches until midnight.",
                self.daily_log.used_today(), self.daily_allowance(),
            )
            return True
        return False


# Module-level tracker — imported by app.py for display
quota = QuotaTracker()


# ---------------------------------------------------------------------------
# API key loader
# ---------------------------------------------------------------------------

def get_api_key() -> Optional[str]:
    """
    Load Odds API key from environment. Never hardcode.

    Checks:
    1. ODDS_API_KEY env var (primary)
    2. Streamlit secrets (for Streamlit Cloud deployments)

    Returns None if no key found — callers must handle gracefully.
    """
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key

    # Streamlit secrets fallback (only import if streamlit is available)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ODDS_API_KEY" in st.secrets:
            return st.secrets["ODDS_API_KEY"]
    except (ImportError, Exception):
        pass

    return None


# ---------------------------------------------------------------------------
# HTTP fetch with exponential backoff
# ---------------------------------------------------------------------------

def _fetch_with_backoff(
    url: str,
    params: dict,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Optional[requests.Response]:
    """
    Perform a GET request with exponential backoff on failures.

    Stops (returns None) after max_retries consecutive failures.
    Logs each failure to the module logger.

    Args:
        url:         Full request URL.
        params:      Query string parameters.
        max_retries: Maximum retry attempts before giving up.
        base_delay:  Initial delay in seconds (doubles each retry).

    Returns:
        requests.Response on success, None on failure.
    """
    delay = base_delay
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response
            elif response.status_code == 422:
                # Unprocessable entity — likely unsupported market for this sport/tier
                logger.warning(
                    "422 Unprocessable Entity: %s params=%s", url, params
                )
                return None  # Don't retry — this is a permanent error
            elif response.status_code == 401:
                logger.error("401 Unauthorized — check ODDS_API_KEY")
                return None  # Don't retry — wrong key
            elif response.status_code == 429:
                logger.warning("429 Rate limited. Waiting %.1fs before retry.", delay * 2)
                time.sleep(delay * 2)
            else:
                logger.warning(
                    "Attempt %d/%d: HTTP %d for %s",
                    attempt, max_retries, response.status_code, url
                )
        except requests.exceptions.Timeout:
            logger.warning("Attempt %d/%d: Timeout for %s", attempt, max_retries, url)
        except requests.exceptions.ConnectionError:
            logger.warning("Attempt %d/%d: Connection error for %s", attempt, max_retries, url)
        except requests.exceptions.RequestException as exc:
            logger.warning("Attempt %d/%d: Request error: %s", attempt, max_retries, exc)

        if attempt < max_retries:
            time.sleep(delay)
            delay *= 2

    logger.error("All %d attempts failed for %s", max_retries, url)
    return None


# ---------------------------------------------------------------------------
# Tennis dynamic sport key discovery
# ---------------------------------------------------------------------------

def fetch_active_tennis_keys(
    include_atp: bool = True,
    include_wta: bool = True,
    session: Optional[requests.Session] = None,
) -> list[str]:
    """
    Fetch currently active tennis sport keys from the Odds API /v4/sports/ endpoint.

    Tennis sport keys change weekly (e.g. "tennis_atp_qatar_open",
    "tennis_atp_dubai", "tennis_wta_dubai"). This function discovers them
    dynamically so no manual MARKETS update is needed each week.

    Filters:
    - active == True (in-season, odds available now)
    - key starts with "tennis_atp" (if include_atp) or "tennis_wta" (if include_wta)

    Args:
        include_atp: Include ATP tour events (default True).
        include_wta: Include WTA tour events (default True).
        session: Optional requests.Session for test injection.

    Returns:
        List of active tennis sport key strings.
        Empty list on API error or no active tennis events.

    Example:
        ["tennis_atp_qatar_open", "tennis_wta_dubai"]
    """
    api_key = get_api_key()
    if not api_key:
        logger.error("No ODDS_API_KEY found. Cannot fetch tennis sport keys.")
        return []

    url = f"{BASE_URL}/"
    params = {"apiKey": api_key}
    requester = session or requests

    try:
        resp = requester.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            quota.update(resp.headers)
        else:
            logger.warning("fetch_active_tennis_keys: HTTP %d", resp.status_code)
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("fetch_active_tennis_keys error: %s", exc)
        return []

    active_keys: list[str] = []
    for sport in data:
        key = sport.get("key", "")
        active = sport.get("active", False)
        if not active:
            continue
        if include_atp and key.startswith("tennis_atp"):
            active_keys.append(key)
        elif include_wta and key.startswith("tennis_wta"):
            active_keys.append(key)

    logger.info("Active tennis keys: %s", active_keys)
    return active_keys


# ---------------------------------------------------------------------------
# Core fetch functions
# ---------------------------------------------------------------------------

def fetch_game_lines(sport_key: str) -> list[dict]:
    """
    Fetch live odds for a single sport from the Odds API.

    Returns the raw list of game dicts. Each game dict contains:
    - id, sport_key, commence_time, home_team, away_team
    - bookmakers: list of bookmaker dicts with markets and outcomes

    Args:
        sport_key: Odds API sport key (e.g. "basketball_nba").
                   Must be a key in the MARKETS dict.

    Returns:
        List of raw game dicts. Empty list on failure or no games.
    """
    api_key = get_api_key()
    if not api_key:
        logger.error("No ODDS_API_KEY found. Cannot fetch lines.")
        return []

    # Tennis keys are dynamic — not in MARKETS dict, use TENNIS_MARKETS fallback
    if sport_key.startswith("tennis_atp") or sport_key.startswith("tennis_wta"):
        markets = TENNIS_MARKETS
    else:
        markets = MARKETS.get(sport_key)
    if not markets:
        logger.warning("Unknown sport_key: %s — no MARKETS entry", sport_key)
        return []

    url = f"{BASE_URL}/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "oddsFormat": "american",
        "markets": markets,
        "bookmakers": ",".join(PREFERRED_BOOKS),
    }

    response = _fetch_with_backoff(url, params)
    if response is None:
        return []

    quota.update(response.headers)
    logger.info("Fetched %s | %s", sport_key, quota.report())

    try:
        data = response.json()
        if not isinstance(data, list):
            logger.warning("Unexpected response format for %s: %s", sport_key, type(data))
            return []
        return data
    except ValueError as exc:
        logger.error("JSON parse error for %s: %s", sport_key, exc)
        return []


def fetch_batch_odds(
    sports: Optional[list[str]] = None,
    include_tennis: bool = True,
) -> dict[str, list[dict]]:
    """
    Fetch odds for multiple sports in sequence. Returns a dict keyed by sport name.

    Used by the APScheduler and by the Live Lines tab.
    Stops early if session hard stop is reached (SESSION_CREDIT_HARD_STOP) or
    billing reserve floor is hit (BILLING_RESERVE).

    Tennis handling: tennis sport keys change weekly (tournament-specific).
    When include_tennis=True, calls fetch_active_tennis_keys() to discover
    current tournaments, then fetches each as "TENNIS_ATP:<sport_key>" or
    "TENNIS_WTA:<sport_key>" in the results dict.

    Args:
        sports: List of friendly sport names (e.g. ["NBA", "NCAAB"]).
                Defaults to ACTIVE_SPORTS if None.
                Pass ["Tennis"] to fetch only tennis.
        include_tennis: Discover and fetch active tennis events (default True).

    Returns:
        Dict mapping sport_name → list of raw game dicts.
        Tennis entries are keyed as the raw Odds API sport key string
        (e.g. "tennis_atp_qatar_open") for downstream kill switch use.
        Empty list for sports that failed or had no games.

    Example:
        results = fetch_batch_odds(["NBA", "NCAAB"])
        nba_games = results["NBA"]    # list[dict]
        ncaab_games = results["NCAAB"]
        # Tennis (when include_tennis=True):
        tennis_games = results.get("tennis_atp_qatar_open", [])
    """
    if sports is None:
        sports = ACTIVE_SPORTS

    results: dict[str, list[dict]] = {}

    # Fetch static sports
    for sport_name in sports:
        sport_key = SPORT_KEYS.get(sport_name.upper())
        if not sport_key:
            logger.warning("Unknown sport '%s' — skipping", sport_name)
            results[sport_name] = []
            continue

        if quota.is_session_hard_stop():
            logger.warning(
                "Credit hard stop — session=%d/%d remaining=%s — halting batch at %s",
                quota.session_used, SESSION_CREDIT_HARD_STOP, quota.remaining, sport_name,
            )
            results[sport_name] = []
            break

        if quota.is_session_soft_limit():
            logger.warning(
                "Credit soft limit reached (session=%d/%d) — continuing but check usage",
                quota.session_used, SESSION_CREDIT_SOFT_LIMIT,
            )

        games = fetch_game_lines(sport_key)
        results[sport_name] = games

    # Fetch tennis dynamically (active tournament keys change weekly)
    if include_tennis and not quota.is_session_hard_stop():
        tennis_keys = fetch_active_tennis_keys()
        for tennis_key in tennis_keys:
            if quota.is_session_hard_stop():
                logger.warning("Credit hard stop — skipping remaining tennis keys")
                break
            games = fetch_game_lines(tennis_key)
            # Keyed by the raw sport key so callers can pass it to tennis_kill_switch
            results[tennis_key] = games

    return results


# ---------------------------------------------------------------------------
# Schedule-derived rest days (zero extra API calls)
# ---------------------------------------------------------------------------

def compute_rest_days_from_schedule(raw_games: list[dict]) -> dict[str, Optional[int]]:
    """
    Derive NBA rest days from consecutive game timestamps in the fetch window.

    Method:
    - Parse commence_time (ISO 8601) per game → build per-team sorted schedule.
    - Diff consecutive timestamps:
      * < 36 hours → rest_days = 0 (B2B)
      * else → int(hours // 24)
    - First game per team in window → None (fall back to stub).

    This enables kill switch B2B detection at zero extra API cost.
    Verified reliable for back-to-back detection (both games co-appear in window).

    Args:
        raw_games: List of raw game dicts from fetch_game_lines().

    Returns:
        Dict mapping team_name → rest_days (int) or None.
        None means only 1 game in window — stub fallback needed.
    """
    from collections import defaultdict

    team_times: dict[str, list[datetime]] = defaultdict(list)

    for game in raw_games:
        ct = game.get("commence_time", "")
        if not ct:
            continue
        try:
            # ISO 8601 with Z suffix
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except ValueError:
            continue

        for team in [game.get("home_team", ""), game.get("away_team", "")]:
            if team:
                team_times[team].append(dt)

    rest_days: dict[str, Optional[int]] = {}

    for team, times in team_times.items():
        if len(times) < 2:
            rest_days[team] = None  # single game — fall back to stub
            continue

        times_sorted = sorted(times)
        # Use the two most recent/upcoming consecutive games
        latest = times_sorted[-1]
        prev = times_sorted[-2]
        diff_hours = (latest - prev).total_seconds() / 3600

        if diff_hours < 36:
            rest_days[team] = 0   # B2B
        else:
            rest_days[team] = int(diff_hours // 24)

    return rest_days


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def all_books(bookmakers: list[dict]) -> list[dict]:
    """
    Return all bookmakers from a raw game's bookmakers list.

    Filters out bookmakers with no markets (malformed entries).
    Used by parse_game_markets in math_engine.

    Args:
        bookmakers: Raw bookmakers list from a game dict.

    Returns:
        Filtered list of valid bookmaker dicts.
    """
    return [b for b in bookmakers if b.get("markets")]


def available_sports() -> list[str]:
    """Return list of all supported friendly sport names."""
    return list(SPORT_KEYS.keys())


def sport_key_for(sport_name: str) -> Optional[str]:
    """
    Convert friendly sport name to Odds API sport key.

    >>> sport_key_for("NBA")
    'basketball_nba'
    >>> sport_key_for("INVALID") is None
    True
    """
    return SPORT_KEYS.get(sport_name.upper())


def timestamp_now() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Pinnacle probe (Session 7 — R&D EXP 2)
# ---------------------------------------------------------------------------

def probe_bookmakers(raw_games: list[dict]) -> dict:
    """
    Survey all bookmaker keys present in a set of raw game dicts.

    Purpose: detect whether Pinnacle is available on our API tier.
    Run against a live NBA fetch; results drive whether consensus can use
    Pinnacle as a sharp-price anchor (higher closing accuracy than DK/FD).

    Args:
        raw_games: Raw game list from fetch_game_lines() or fetch_batch_odds().

    Returns:
        {
            "all_keys": sorted list of all bookmaker keys seen,
            "pinnacle_present": bool,
            "preferred_found": list of PREFERRED_BOOKS keys that appeared,
            "n_games_sampled": int,
            "per_game": [{"matchup": str, "books": [str]}]  # first 5 games
        }

    >>> result = probe_bookmakers([])
    >>> result["n_games_sampled"]
    0
    >>> result["pinnacle_present"]
    False
    """
    all_keys: set[str] = set()
    per_game: list[dict] = []

    for game in raw_games:
        home = game.get("home_team", "?")
        away = game.get("away_team", "?")
        books_here = [b["key"] for b in game.get("bookmakers", []) if b.get("key")]
        all_keys.update(books_here)
        if len(per_game) < 5:
            per_game.append({"matchup": f"{away} @ {home}", "books": sorted(books_here)})

    preferred_found = [b for b in PREFERRED_BOOKS if b in all_keys]

    return {
        "all_keys":        sorted(all_keys),
        "pinnacle_present": "pinnacle" in all_keys,
        "preferred_found": preferred_found,
        "n_games_sampled": len(raw_games),
        "per_game":        per_game,
    }


def print_pinnacle_report(probe_result: dict) -> None:
    """
    Print a human-readable Pinnacle probe report to stdout.

    Intended for CLI runs and R&D log capture.
    Does NOT modify any state.

    Args:
        probe_result: Dict returned by probe_bookmakers().
    """
    n = probe_result["n_games_sampled"]
    present = probe_result["pinnacle_present"]
    all_keys = probe_result["all_keys"]
    preferred = probe_result["preferred_found"]

    print(f"\n{'='*60}")
    print(f"  PINNACLE PROBE REPORT — {timestamp_now()}")
    print(f"{'='*60}")
    print(f"  Games sampled    : {n}")
    print(f"  Pinnacle present : {'YES ✓' if present else 'NO ✗'}")
    print(f"  Preferred books  : {', '.join(preferred) if preferred else 'none'}")
    print(f"  All book keys    : {', '.join(all_keys) if all_keys else 'none'}")
    print()

    if probe_result["per_game"]:
        print("  Sample games (first 5):")
        for g in probe_result["per_game"]:
            print(f"    {g['matchup']}")
            print(f"      books: {', '.join(g['books'])}")

    print()
    if present:
        print("  ✓ Pinnacle is available. Evaluate adding to PREFERRED_BOOKS")
        print("    for sharper consensus anchor — compare implied probs vs DK.")
    else:
        print("  ✗ Pinnacle not on this API tier. DraftKings remains primary.")
        print("    No action required in PREFERRED_BOOKS.")
    print(f"{'='*60}\n")
