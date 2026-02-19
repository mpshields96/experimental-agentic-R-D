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

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4/sports"

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
    """Track API usage across the session."""

    def __init__(self) -> None:
        self.used: int = 0
        self.remaining: Optional[int] = None
        self.last_cost: int = 0

    def update(self, headers: dict) -> None:
        try:
            self.remaining = int(headers.get("x-requests-remaining", self.remaining or 0))
            self.used = int(headers.get("x-requests-used", self.used))
            self.last_cost = int(headers.get("x-requests-last", 0))
        except (ValueError, TypeError):
            pass

    def report(self) -> str:
        return (
            f"API quota | used={self.used} "
            f"remaining={self.remaining} "
            f"last_call={self.last_cost}"
        )

    def is_low(self, threshold: int = 50) -> bool:
        """Return True if remaining quota is below threshold."""
        if self.remaining is None:
            return False
        return self.remaining < threshold


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

    Used by the APScheduler every 5 minutes and by the Live Lines tab.
    Stops early if quota is critically low (< 20 remaining).

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

        if quota.is_low(threshold=20):
            logger.warning(
                "Quota critically low (%s remaining) — stopping batch after %s",
                quota.remaining, sport_name
            )
            results[sport_name] = []
            break

        games = fetch_game_lines(sport_key)
        results[sport_name] = games

    # Fetch tennis dynamically (active tournament keys change weekly)
    if include_tennis and not quota.is_low(threshold=20):
        tennis_keys = fetch_active_tennis_keys()
        for tennis_key in tennis_keys:
            if quota.is_low(threshold=20):
                logger.warning("Quota critically low — skipping remaining tennis keys")
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
