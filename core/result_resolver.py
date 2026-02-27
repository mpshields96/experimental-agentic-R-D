"""
core/result_resolver.py — Titanium-Agentic
============================================
Paper bet auto-resolver using ESPN unofficial API (zero Odds API credits).

Fetches completed game scores and resolves pending paper bets (win/loss/void).
No API key required. NBA, NFL, NCAAB, NHL supported.

Design:
- fetch_espn_scoreboard(sport, date_str, _fetcher) → list[dict]
- _find_game(scoreboard, matchup) → dict | None
- _resolve_spread(bet, game) → "win" | "loss" | "void" | None
- _resolve_total(bet, game) → "win" | "loss" | "void" | None
- _resolve_moneyline(bet, game) → "win" | "loss" | "void" | None
- auto_resolve_pending(db_path, _fetcher) → ResolveResult

Bet log fields consumed:
  id, sport, matchup, market_type, target, line, stake, logged_at, result

Spread cover logic:
  adjusted = actual_margin (from team perspective) + line
  adjusted > 0 → WIN | < 0 → LOSS | == 0 → VOID

Totals logic:
  total_score = home + away vs line
  Over: total > line → WIN | Under: total < line → WIN | == → VOID

Moneyline logic:
  Bet team score > opponent → WIN | < → LOSS | == → VOID

DO NOT add Streamlit or Odds API calls to this file.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import requests

from core.line_logger import get_bets, update_bet_result

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
_REQUEST_TIMEOUT = 10

# Sport key → ESPN path segment
_ESPN_SPORT_PATHS: dict[str, str] = {
    "NBA":    "basketball/nba",
    "NFL":    "football/nfl",
    "NCAAB":  "basketball/mens-college-basketball",
    "NHL":    "hockey/nhl",
    "NCAAF":  "football/college-football",
}

# Extra URL query params per sport. NCAAB default endpoint returns ~10 featured
# games; groups=50 (all D1) + limit=200 returns the full slate.
_ESPN_EXTRA_PARAMS: dict[str, str] = {
    "NCAAB": "groups=50&limit=200",
    "NCAAF": "groups=80&limit=200",
}

# How many days forward from logged_at to search for the completed game
_DATE_SEARCH_WINDOW = 3


# ---------------------------------------------------------------------------
# ESPN fetch
# ---------------------------------------------------------------------------

def _espn_sport_path(sport: str) -> Optional[str]:
    """Map sport key to ESPN API path. Returns None for unsupported sports.

    >>> _espn_sport_path("NBA")
    'basketball/nba'
    >>> _espn_sport_path("MLB") is None
    True
    """
    return _ESPN_SPORT_PATHS.get(sport.upper())


def fetch_espn_scoreboard(
    sport: str,
    date_str: str,
    _fetcher: Optional[Callable[[str], dict]] = None,
) -> list[dict]:
    """
    Fetch completed games from ESPN unofficial scoreboard API.

    Args:
        sport:    Sport key ("NBA", "NFL", etc.).
        date_str: Date in YYYYMMDD format (e.g. "20260226").
        _fetcher: Optional injected function (url: str) → dict for testing.
                  Replaces requests.get — ONLY override in tests.

    Returns:
        List of game dicts. Each dict has:
            espn_id, home_team, away_team, home_score, away_score, completed.
        Empty list on unsupported sport, network error, or no games.

    NOTE: ESPN unofficial API — no API key required, no credits consumed.
    """
    path = _espn_sport_path(sport)
    if not path:
        logger.debug("result_resolver: unsupported sport '%s'", sport)
        return []

    extra = _ESPN_EXTRA_PARAMS.get(sport.upper(), "")
    url = f"{_ESPN_BASE}/{path}/scoreboard?dates={date_str}"
    if extra:
        url = f"{url}&{extra}"
    try:
        if _fetcher is not None:
            raw = _fetcher(url)
        else:
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as exc:
        logger.warning("result_resolver: ESPN fetch failed (%s %s): %s", sport, date_str, exc)
        return []

    games: list[dict] = []
    for event in raw.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        status = comp.get("status", {}).get("type", {})
        completed = bool(status.get("completed", False))
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        try:
            home_score = int(float(home.get("score", 0) or 0))
            away_score = int(float(away.get("score", 0) or 0))
        except (TypeError, ValueError):
            continue

        games.append({
            "espn_id":    event.get("id", ""),
            "home_team":  (home.get("team") or {}).get("displayName", ""),
            "away_team":  (away.get("team") or {}).get("displayName", ""),
            "home_score": home_score,
            "away_score": away_score,
            "completed":  completed,
        })

    return games


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for fuzzy match.

    >>> _normalize("Los Angeles Lakers")
    'los angeles lakers'
    >>> _normalize("L.A. Lakers")
    'la lakers'
    """
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _team_matches(espn_name: str, fragment: str) -> bool:
    """
    Fuzzy team name match: True if fragment is contained in espn_name or vice versa.

    Handles full names ("Los Angeles Lakers"), city fragments ("Lakers"),
    abbreviations, and Odds API abbreviations vs ESPN full names.

    Abbreviation expansion: "Colorado St Rams" (Odds API) → "Colorado State Rams"
    (ESPN) — applies \bst\b → "state" expansion to the fragment only, preventing
    "St. Louis Blues" from incorrectly expanding to "State Louis Blues".

    >>> _team_matches("Los Angeles Lakers", "Lakers")
    True
    >>> _team_matches("Los Angeles Lakers", "Celtics")
    False
    >>> _team_matches("Colorado State Rams", "Colorado St Rams")
    True
    >>> _team_matches("Fresno State Bulldogs", "Fresno St Bulldogs")
    True
    """
    if not espn_name or not fragment:
        return False
    n_espn = _normalize(espn_name)
    n_frag = _normalize(fragment)
    if n_frag in n_espn or n_espn in n_frag:
        return True
    # Abbreviation expansion (fragment only — Odds API uses abbreviated names):
    #   "colorado st rams" → "colorado state rams" → matches ESPN "Colorado State Rams"
    # Do NOT expand n_espn to prevent "St. Louis Blues" → "State Louis Blues" errors.
    n_frag_exp = re.sub(r"\bst\b", "state", n_frag)
    if n_frag_exp != n_frag and (n_frag_exp in n_espn or n_espn in n_frag_exp):
        return True
    return False


def _find_game(
    scoreboard: list[dict],
    matchup: str,
    completed_only: bool = True,
) -> Optional[dict]:
    """
    Find a game in an ESPN scoreboard by matchup string.

    Args:
        scoreboard:     List from fetch_espn_scoreboard().
        matchup:        Our format: "Away Team @ Home Team".
        completed_only: If True, only return completed games.

    Returns:
        Matching game dict or None if not found.
    """
    if not matchup:
        return None
    parts = re.split(r"\s*@\s*", matchup, maxsplit=1)
    if len(parts) != 2:
        return None
    away_frag, home_frag = parts[0].strip(), parts[1].strip()

    for game in scoreboard:
        if completed_only and not game.get("completed"):
            continue
        if _team_matches(game["home_team"], home_frag) and _team_matches(game["away_team"], away_frag):
            return game
    return None


# ---------------------------------------------------------------------------
# Market-specific resolvers
# ---------------------------------------------------------------------------

def _resolve_spread(bet: dict, game: dict) -> Optional[str]:
    """
    Resolve a spread bet (market_type="spreads").

    Target format: "{Team Name} {+/-line}" e.g. "Chicago Bulls +7.0"
    Line stored in bet["line"] (float, same sign as target).

    Adjusted margin from the bet team's perspective:
        adjusted = actual_margin + line

    adjusted > 0 → "win" | < 0 → "loss" | == 0 → "void"

    Returns "win", "loss", "void", or None if resolution fails.
    """
    target = bet.get("target", "")
    line = bet.get("line")
    matchup = bet.get("matchup", "")

    if line is None:
        return None

    # Strip spread suffix to extract team name: "Chicago Bulls +7.0" → "Chicago Bulls"
    m = re.match(r"^(.+?)\s+[+-]\d+\.?\d*$", target.strip())
    if not m:
        return None
    team_name = m.group(1).strip()

    # Identify home vs away
    parts = re.split(r"\s*@\s*", matchup, maxsplit=1)
    if len(parts) != 2:
        return None
    away_frag, home_frag = parts[0].strip(), parts[1].strip()

    if _team_matches(game["away_team"], team_name) or _team_matches(team_name, away_frag):
        actual_margin = game["away_score"] - game["home_score"]
    elif _team_matches(game["home_team"], team_name) or _team_matches(team_name, home_frag):
        actual_margin = game["home_score"] - game["away_score"]
    else:
        logger.debug(
            "result_resolver: can't place team '%s' as home/away in '%s'", team_name, matchup
        )
        return None

    adjusted = actual_margin + float(line)
    if adjusted > 0:
        return "win"
    elif adjusted < 0:
        return "loss"
    else:
        return "void"


def _resolve_total(bet: dict, game: dict) -> Optional[str]:
    """
    Resolve a totals bet (market_type="totals").

    Target format: "Over 221.5" or "Under 221.5"
    Line stored in bet["line"].

    total_score = home_score + away_score

    Over: total > line → "win" | < → "loss" | == → "void"
    Under: total < line → "win" | > → "loss" | == → "void"

    Returns "win", "loss", "void", or None.
    """
    target = bet.get("target", "").strip()
    line = bet.get("line")

    if line is None:
        return None

    target_upper = target.upper()
    if target_upper.startswith("OVER"):
        direction = "over"
    elif target_upper.startswith("UNDER"):
        direction = "under"
    else:
        return None

    total_score = game["home_score"] + game["away_score"]
    line_f = float(line)

    if direction == "over":
        if total_score > line_f:
            return "win"
        elif total_score < line_f:
            return "loss"
        else:
            return "void"
    else:  # under
        if total_score < line_f:
            return "win"
        elif total_score > line_f:
            return "loss"
        else:
            return "void"


def _resolve_moneyline(bet: dict, game: dict) -> Optional[str]:
    """
    Resolve a moneyline bet (market_type="h2h").

    Target format: "{Team Name} ML" e.g. "Chicago Bulls ML"

    Returns "win", "loss", "void", or None.
    """
    target = bet.get("target", "").strip()

    m = re.match(r"^(.+?)\s+ML$", target, re.IGNORECASE)
    if not m:
        return None
    team_name = m.group(1).strip()

    home_score = game["home_score"]
    away_score = game["away_score"]

    if _team_matches(game["home_team"], team_name):
        if home_score > away_score:
            return "win"
        elif home_score < away_score:
            return "loss"
        else:
            return "void"
    elif _team_matches(game["away_team"], team_name):
        if away_score > home_score:
            return "win"
        elif away_score < home_score:
            return "loss"
        else:
            return "void"
    else:
        logger.debug("result_resolver: can't match team '%s' in game %s", team_name, game)
        return None


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def _resolve_single_bet(
    bet: dict,
    _fetcher: Optional[Callable[[str], dict]] = None,
) -> Optional[str]:
    """
    Attempt to resolve one pending bet. Returns result string or None.

    Searches logged_at - 1 day through logged_at + _DATE_SEARCH_WINDOW days for completed game.

    The -1 offset handles US evening games logged after midnight UTC (e.g. a game
    played Feb 24 US time may be logged at 03:00 UTC Feb 25 — without the offset
    the actual game date would be missed).
    """
    sport = bet.get("sport", "")
    matchup = bet.get("matchup", "")
    market_type = bet.get("market_type", "")
    logged_at_str = bet.get("logged_at", "")

    if not sport or not matchup or not market_type:
        return None

    try:
        logged_dt = datetime.fromisoformat(logged_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    # Search 1 day before logged_at through _DATE_SEARCH_WINDOW days after.
    # Bets logged after midnight UTC for same-day US evening games will have
    # logged_at on the next UTC day — without the -1 offset, the actual game
    # date would be missed (e.g. game plays Feb 24 US, logged 03:17 UTC Feb 25).
    search_dates = [
        (logged_dt + timedelta(days=d)).strftime("%Y%m%d")
        for d in range(-1, _DATE_SEARCH_WINDOW + 1)
    ]

    for date_str in search_dates:
        scoreboard = fetch_espn_scoreboard(sport, date_str, _fetcher=_fetcher)
        game = _find_game(scoreboard, matchup)
        if game is None:
            continue

        if market_type == "spreads":
            return _resolve_spread(bet, game)
        elif market_type == "totals":
            return _resolve_total(bet, game)
        elif market_type == "h2h":
            return _resolve_moneyline(bet, game)
        else:
            logger.debug("result_resolver: unsupported market_type '%s'", market_type)
            return None

    return None


class ResolveResult:
    """Outcome summary returned by auto_resolve_pending()."""

    __slots__ = ("resolved", "skipped", "errors", "details")

    def __init__(self) -> None:
        self.resolved: int = 0
        self.skipped: int = 0
        self.errors: int = 0
        self.details: list[str] = []

    def __repr__(self) -> str:
        return (
            f"ResolveResult(resolved={self.resolved}, "
            f"skipped={self.skipped}, errors={self.errors})"
        )


def auto_resolve_pending(
    db_path: Optional[str] = None,
    _fetcher: Optional[Callable[[str], dict]] = None,
) -> ResolveResult:
    """
    Auto-resolve all pending paper bets using ESPN scores.

    Algorithm:
    1. Query bet_log for all result='pending' bets.
    2. For each bet, search ESPN scoreboard for logged_at date + window.
    3. Match game by matchup (fuzzy team name), assert completed.
    4. Compute win/loss/void from market_type + target + line.
    5. Call update_bet_result() for resolved bets.

    Args:
        db_path:  Optional DB path override for testing.
        _fetcher: Optional ESPN fetch function (url: str) → dict for testing.

    Returns:
        ResolveResult with resolved, skipped, errors counts and details list.

    NOTE: Does not raise — errors per-bet are counted in result.errors.
    """
    rr = ResolveResult()
    pending = get_bets(result_filter="pending", db_path=db_path)

    for bet in pending:
        bet_id = bet.get("id")
        if bet_id is None:
            rr.skipped += 1
            continue

        try:
            outcome = _resolve_single_bet(bet, _fetcher=_fetcher)
        except Exception as exc:
            logger.error("result_resolver: error resolving bet #%d: %s", bet_id, exc)
            rr.errors += 1
            continue

        if outcome is None:
            rr.skipped += 1
            continue

        try:
            stake = float(bet.get("stake") or 0.0)
            update_bet_result(
                bet_id=bet_id,
                result=outcome,
                stake=stake,
                db_path=db_path,
            )
            target = bet.get("target", "?")
            rr.details.append(f"#{bet_id} {target} → {outcome.upper()}")
            rr.resolved += 1
            logger.info("result_resolver: bet #%d resolved → %s", bet_id, outcome)
        except Exception as exc:
            logger.error("result_resolver: failed to save result for bet #%d: %s", bet_id, exc)
            rr.errors += 1

    return rr
