"""
core/nba_pdo.py — NBA PDO Regression Signal
============================================
PDO = Team FG% + Opponent Save% (normalized to 100.0 baseline).

High PDO (>= 102): team is outperforming luck on both ends → expect regression.
Low PDO (<= 98):   team is underperforming luck on both ends → expect recovery.
Neutral (98–102):  no reliable regression signal.

Why PDO normalises to 100.0:
  Across the full league, sum(all team FG%) == sum(all opp-allowed FG%) by identity
  (every made shot is both a make for the offense and a make-allowed for the defense).
  Therefore league-average PDO = (avg_FG% + (1.0 - avg_FG%)) * 100 = 100.0 exactly.

Minimum sample guard: GP >= 10. Fewer games → variance dominates, signal is noise.

Data source:
  nba_api.stats.endpoints.LeagueDashTeamStats (free, no key required).
  Two sequential calls: MeasureType="Base" → FG_PCT; MeasureType="Opponent" → OPP_FG_PCT.
  1-hour TTL on fetched data. Fetch all 30 teams at once; callers do NOT call per-team.

Architecture rules:
  - NO imports from math_engine, odds_fetcher, line_logger, or scheduler.
  - math_engine.pdo_kill_switch_gate() acts on PdoResult — this module only provides data.
  - Scheduler / live_lines fetch all PDO data once per hour and pass into parse_game_markets().
  - nba_api is NOT called inside math_engine (no live I/O in the math layer).

Kill switch interface:
  pdo_kill_switch(team_name, bet_direction, market_type) → (bool, str)
  Mirrors nhl_kill_switch() / injury_kill_switch() exactly.

Season constant:
  _CURRENT_SEASON is hardcoded. Update annually at season start (October).
  Do NOT auto-compute — nba_api season detection is fragile during October turnover.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PDO_BASELINE: float = 100.0
PDO_REGRESS_THRESHOLD: float = 102.0   # overperforming luck → expect regression
PDO_RECOVER_THRESHOLD: float = 98.0    # underperforming luck → expect recovery
PDO_MIN_GAMES: int = 10                # sample size guard — below this, ignore signal
_CACHE_TTL_SECONDS: int = 3600         # 1-hour TTL
_REQUEST_TIMEOUT: int = 15             # nba_api can be slow; 15s is safe
_INTER_REQUEST_SLEEP: float = 0.6      # respect stats.nba.com rate limits
_CURRENT_SEASON: str = "2024-25"       # UPDATE ANNUALLY at season start (October)

# ---------------------------------------------------------------------------
# nba_api team name → efficiency_feed canonical name
#
# nba_api returns display names that differ from the canonical keys in
# efficiency_feed._TEAM_DATA for two teams:
#   "LA Clippers"  → "Los Angeles Clippers"
#   "LA Lakers"    → "Los Angeles Lakers"   (occasional variant)
# All 30 other entries are identical to the canonical names.
# ---------------------------------------------------------------------------

_NBA_API_TO_CANONICAL: dict[str, str] = {
    # Entries only where nba_api name ≠ efficiency_feed canonical key
    "LA Clippers": "Los Angeles Clippers",
    "LA Lakers":   "Los Angeles Lakers",
    # Full table for robustness (all 30 teams, canonical → canonical pass-through)
    "Atlanta Hawks":           "Atlanta Hawks",
    "Boston Celtics":          "Boston Celtics",
    "Brooklyn Nets":           "Brooklyn Nets",
    "Charlotte Hornets":       "Charlotte Hornets",
    "Chicago Bulls":           "Chicago Bulls",
    "Cleveland Cavaliers":     "Cleveland Cavaliers",
    "Dallas Mavericks":        "Dallas Mavericks",
    "Denver Nuggets":          "Denver Nuggets",
    "Detroit Pistons":         "Detroit Pistons",
    "Golden State Warriors":   "Golden State Warriors",
    "Houston Rockets":         "Houston Rockets",
    "Indiana Pacers":          "Indiana Pacers",
    "Los Angeles Clippers":    "Los Angeles Clippers",
    "Los Angeles Lakers":      "Los Angeles Lakers",
    "Memphis Grizzlies":       "Memphis Grizzlies",
    "Miami Heat":              "Miami Heat",
    "Milwaukee Bucks":         "Milwaukee Bucks",
    "Minnesota Timberwolves":  "Minnesota Timberwolves",
    "New Orleans Pelicans":    "New Orleans Pelicans",
    "New York Knicks":         "New York Knicks",
    "Oklahoma City Thunder":   "Oklahoma City Thunder",
    "Orlando Magic":           "Orlando Magic",
    "Philadelphia 76ers":      "Philadelphia 76ers",
    "Phoenix Suns":            "Phoenix Suns",
    "Portland Trail Blazers":  "Portland Trail Blazers",
    "Sacramento Kings":        "Sacramento Kings",
    "San Antonio Spurs":       "San Antonio Spurs",
    "Toronto Raptors":         "Toronto Raptors",
    "Utah Jazz":               "Utah Jazz",
    "Washington Wizards":      "Washington Wizards",
}

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PdoResult:
    team_name: str       # canonical name (efficiency_feed key)
    shoot_pct: float     # team FG% (e.g. 0.473)
    opp_save_pct: float  # 1.0 - opponent FG% (e.g. 0.539)
    pdo: float           # (shoot_pct + opp_save_pct) * 100, baseline 100.0
    signal: str          # "REGRESS", "RECOVER", or "NEUTRAL"
    games_played: int    # sample size
    fetched_at: float    # time.time() — for TTL checks


# ---------------------------------------------------------------------------
# Module-level cache — keyed by canonical team name
# Scheduler writes via get_all_pdo_data(); parse_game_markets() reads.
# ---------------------------------------------------------------------------

_pdo_cache: dict[str, PdoResult] = {}


def clear_pdo_cache() -> None:
    """Clear the PDO cache. Used in tests and on session restart."""
    _pdo_cache.clear()


def pdo_cache_size() -> int:
    """Return number of teams in the PDO cache."""
    return len(_pdo_cache)


# ---------------------------------------------------------------------------
# Pure math functions — no I/O, fully testable in isolation
# ---------------------------------------------------------------------------

def compute_pdo(fg_pct: float, opp_fg_pct: float) -> float:
    """
    Compute PDO from team FG% and opponent FG%.

    PDO = (team_shoot_pct + opp_save_pct) * 100
        = (fg_pct + (1.0 - opp_fg_pct)) * 100

    League average = 100.0 by mathematical identity.
    Typical range in practice: 95–105.

    Args:
        fg_pct:     Team's own FG% (e.g. 0.473 for 47.3%)
        opp_fg_pct: Opponent's FG% against this team (e.g. 0.461 for 46.1%)

    Returns:
        PDO float, e.g. 101.2
    """
    opp_save_pct = 1.0 - opp_fg_pct
    return round((fg_pct + opp_save_pct) * 100.0, 4)


def classify_pdo(pdo: float) -> str:
    """
    Classify a PDO value as REGRESS, RECOVER, or NEUTRAL.

    REGRESS (>= 102.0): Team is getting lucky on both ends; expect mean reversion.
    RECOVER (<= 98.0):  Team is unlucky; positive regression expected.
    NEUTRAL (98–102):   Within ~1 standard deviation; no reliable signal.

    Thresholds calibrated to NBA data: 1 SD of PDO ≈ 1.5–2.0 PDO points.
    """
    if pdo >= PDO_REGRESS_THRESHOLD:
        return "REGRESS"
    if pdo <= PDO_RECOVER_THRESHOLD:
        return "RECOVER"
    return "NEUTRAL"


def normalize_nba_team_name(raw_name: str) -> Optional[str]:
    """
    Map an nba_api team name to the canonical name used in efficiency_feed._TEAM_DATA.

    Critical edge cases handled:
      "LA Clippers"  → "Los Angeles Clippers"
      "LA Lakers"    → "Los Angeles Lakers"

    Returns None on no match (unknown team / expansion team not in table).
    Case-insensitive. Strips whitespace.
    """
    if not raw_name:
        return None
    cleaned = raw_name.strip()

    # Direct map (handles all known variants)
    result = _NBA_API_TO_CANONICAL.get(cleaned)
    if result:
        return result

    # Case-insensitive fallback
    cleaned_lower = cleaned.lower()
    for api_name, canonical in _NBA_API_TO_CANONICAL.items():
        if api_name.lower() == cleaned_lower:
            return canonical

    # Last-word partial match (e.g. "Clippers" → "Los Angeles Clippers")
    last_word = cleaned.split()[-1].lower() if cleaned else ""
    if last_word:
        for api_name, canonical in _NBA_API_TO_CANONICAL.items():
            if api_name.split()[-1].lower() == last_word:
                return canonical

    logger.debug("normalize_nba_team_name: no match for %r", raw_name)
    return None


# ---------------------------------------------------------------------------
# Data fetch — injectable _endpoint_factory for test mocking
# ---------------------------------------------------------------------------

def _fetch_league_shooting(
    measure_type: str = "Base",
    _endpoint_factory: Optional[Callable] = None,
) -> Optional[dict[str, dict]]:
    """
    Fetch one measure type from LeagueDashTeamStats.

    Args:
        measure_type: "Base" for team FG_PCT, or "Opponent" for OPP_FG_PCT.
        _endpoint_factory: Injectable callable for tests. Defaults to
            nba_api's LeagueDashTeamStats. Signature: factory(**kwargs) → endpoint object
            that has get_data_frames() → list[DataFrame].

    Returns:
        {team_name: {"fg_pct": float, "games_played": int}} on success.
        None on error (network, empty response, missing columns, off-season).
    """
    from nba_api.stats.endpoints import LeagueDashTeamStats  # lazy import

    factory = _endpoint_factory or LeagueDashTeamStats

    try:
        ep = factory(
            measure_type_detailed_defense=measure_type,
            per_mode_detailed="PerGame",
            season=_CURRENT_SEASON,
            season_type_all_star="Regular Season",
            timeout=_REQUEST_TIMEOUT,
        )
        frames = ep.get_data_frames()
        if not frames:
            logger.warning("_fetch_league_shooting(%s): no dataframes returned", measure_type)
            return None
        df = frames[0]
    except Exception as exc:
        logger.warning("_fetch_league_shooting(%s) error: %s", measure_type, exc)
        return None

    # Determine which column carries FG%
    if measure_type == "Base":
        pct_col = "FG_PCT"
    else:
        pct_col = "OPP_FG_PCT"

    required = {"TEAM_NAME", "GP", pct_col}
    if not required.issubset(set(df.columns)):
        logger.warning(
            "_fetch_league_shooting(%s): missing columns. Have: %s",
            measure_type, list(df.columns)
        )
        return None

    if df.empty:
        logger.info("_fetch_league_shooting(%s): empty dataframe (off-season?)", measure_type)
        return None

    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        name = str(row["TEAM_NAME"]).strip()
        gp = int(row["GP"])
        pct = float(row[pct_col])
        result[name] = {"fg_pct": pct, "games_played": gp}

    return result if result else None


def _merge_shooting_data(
    base: dict[str, dict],
    opponent: dict[str, dict],
) -> dict[str, dict]:
    """
    Inner join base (team FG%) and opponent (opp FG%) data on team name.

    Teams absent from either side are dropped — protects against partial data.

    Returns:
        {team_name: {"fg_pct": float, "opp_fg_pct": float, "games_played": int}}
    """
    merged: dict[str, dict] = {}
    for team_name, base_data in base.items():
        if team_name not in opponent:
            continue
        merged[team_name] = {
            "fg_pct": base_data["fg_pct"],
            "opp_fg_pct": opponent[team_name]["fg_pct"],
            "games_played": base_data["games_played"],
        }
    return merged


# ---------------------------------------------------------------------------
# High-level fetch — fetches all 30 teams in two sequential calls
# ---------------------------------------------------------------------------

def get_all_pdo_data(
    _endpoint_factory: Optional[Callable] = None,
) -> dict[str, "PdoResult"]:
    """
    Fetch PDO for all 30 NBA teams and populate the module-level cache.

    Makes two sequential nba_api calls (Base + Opponent), sleeps 0.6s between
    them to respect stats.nba.com rate limits.

    Should be called once per hour (from scheduler or session init).
    Callers should NOT call get_team_pdo() per game — use this + cache lookup.

    Returns:
        {canonical_team_name: PdoResult} — empty dict on any error.
    """
    base = _fetch_league_shooting("Base", _endpoint_factory=_endpoint_factory)
    if base is None:
        logger.warning("get_all_pdo_data: base fetch failed, returning empty")
        return {}

    if _endpoint_factory is None:
        time.sleep(_INTER_REQUEST_SLEEP)

    opponent = _fetch_league_shooting("Opponent", _endpoint_factory=_endpoint_factory)
    if opponent is None:
        logger.warning("get_all_pdo_data: opponent fetch failed, returning empty")
        return {}

    merged = _merge_shooting_data(base, opponent)
    if not merged:
        logger.warning("get_all_pdo_data: merge produced no teams")
        return {}

    now = time.time()
    results: dict[str, PdoResult] = {}

    for api_name, data in merged.items():
        canonical = normalize_nba_team_name(api_name)
        if canonical is None:
            logger.debug("get_all_pdo_data: skipping unknown team %r", api_name)
            continue

        gp = data["games_played"]
        if gp < PDO_MIN_GAMES:
            logger.debug(
                "get_all_pdo_data: skipping %s (GP=%d < %d)", canonical, gp, PDO_MIN_GAMES
            )
            continue

        fg_pct = data["fg_pct"]
        opp_fg_pct = data["opp_fg_pct"]
        pdo = compute_pdo(fg_pct, opp_fg_pct)
        signal = classify_pdo(pdo)

        r = PdoResult(
            team_name=canonical,
            shoot_pct=fg_pct,
            opp_save_pct=1.0 - opp_fg_pct,
            pdo=pdo,
            signal=signal,
            games_played=gp,
            fetched_at=now,
        )
        results[canonical] = r
        _pdo_cache[canonical] = r

    return results


def get_team_pdo(
    team_name: str,
    _endpoint_factory: Optional[Callable] = None,
) -> Optional["PdoResult"]:
    """
    Get PDO for a single team. Checks module-level cache first (1-hour TTL).

    Callers who need multiple teams should call get_all_pdo_data() once instead
    of calling this per team — avoids hitting the rate limit.

    Returns None on: off-season, API error, GP < PDO_MIN_GAMES, unknown team.
    """
    canonical = normalize_nba_team_name(team_name) or team_name

    # Cache hit within TTL
    cached = _pdo_cache.get(canonical)
    if cached is not None:
        age = time.time() - cached.fetched_at
        if age < _CACHE_TTL_SECONDS:
            return cached

    # Cache miss or TTL expired — refresh all teams
    all_data = get_all_pdo_data(_endpoint_factory=_endpoint_factory)
    return all_data.get(canonical)


# ---------------------------------------------------------------------------
# Kill switch — mirrors nhl_kill_switch() / injury_kill_switch() interface
# ---------------------------------------------------------------------------

def pdo_kill_switch(
    team_name: str,
    bet_direction: str,
    market_type: str = "spreads",
) -> tuple[bool, str]:
    """
    PDO-based kill switch gate.

    Args:
        team_name:     Canonical team name (efficiency_feed key).
        bet_direction: "with" (betting on this team) or "against" (fading this team).
        market_type:   "spreads", "h2h", or "totals".
                       PDO is directional — totals always returns (False, "").

    Returns:
        (True,  "KILL: reason")  — remove candidate from pipeline
        (False, "FLAG: reason")  — annotate but keep candidate
        (False, "")              — no signal; pass through

    Kill logic:
        REGRESS + betting WITH  → KILL (team luck will correct against them)
        REGRESS + betting AGAINST → FLAG (you have an edge, not a kill)
        RECOVER + betting WITH  → FLAG (value candidate, not a hard kill)
        RECOVER + betting AGAINST → KILL (opponent due for positive regression)
        NEUTRAL → no action
        totals → no action (PDO is directional; totals signal is ambiguous)
    """
    # Totals: PDO is not directional enough to kill a total
    if market_type == "totals":
        return (False, "")

    cached = _pdo_cache.get(team_name)
    if cached is None:
        # Try normalization fallback
        canonical = normalize_nba_team_name(team_name)
        if canonical:
            cached = _pdo_cache.get(canonical)
    if cached is None:
        return (False, "")

    signal = cached.signal
    direction = bet_direction.lower().strip()

    if signal == "NEUTRAL":
        return (False, "")

    if signal == "REGRESS":
        if direction == "with":
            return (
                True,
                f"KILL: PDO regress — {team_name} FG luck unsustainable (PDO {cached.pdo:.1f})",
            )
        else:
            return (
                False,
                f"FLAG: PDO regress opponent — {team_name} due for regression (PDO {cached.pdo:.1f})",
            )

    if signal == "RECOVER":
        if direction == "with":
            return (
                False,
                f"FLAG: PDO recovery candidate — {team_name} underperforming luck (PDO {cached.pdo:.1f})",
            )
        else:
            return (
                True,
                f"KILL: PDO recovery — fading {team_name} but they're due for positive regression (PDO {cached.pdo:.1f})",
            )

    return (False, "")
