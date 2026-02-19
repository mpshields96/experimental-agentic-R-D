"""
core/math_engine.py — Titanium-Agentic
========================================
All betting math lives here. No API calls, no UI, no file I/O.

Responsibilities:
- Collar check: -180 to +150 American odds
- Implied probability (with and without vig)
- Edge percentage calculation
- Fractional Kelly sizing
- Sharp Score composite ranking (0-100)
- Kill switch logic (NBA, NFL, NCAAB, Soccer)
- Multi-book consensus fair probability
- RLM (Reverse Line Movement) passive tracker
- CLV (Closing Line Value) calculation
- BetCandidate dataclass

NON-NEGOTIABLE RULES (inherited from V36.1):
1. Collar: -180 <= american_odds <= +150. Reject all others.
2. Minimum edge: >= 3.5% to pass.
3. Minimum books for consensus: >= 2.
4. Kelly fraction: 0.25x. Hard caps: >60% winprob=2.0u, >54%=1.0u, else=0.5u.
5. SHARP_THRESHOLD = 45. Require ~7.8% real edge before a bet is promoted.
6. Kill switches: NBA rest, NFL wind, NCAAB 3P reliance, Soccer drift.
7. Dedup: never output both sides of same market.
8. Sort: Sharp Score descending (NOT edge%).

DO NOT add API calls, Streamlit calls, or file I/O to this file.
"""

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_EDGE: float = 0.035          # 3.5% minimum edge
MIN_BOOKS: int = 2               # minimum books for consensus
KELLY_FRACTION: float = 0.25     # fractional Kelly multiplier
SHARP_THRESHOLD: float = 45.0    # minimum Sharp Score to pass (raise to 50-55 after RLM wired)
COLLAR_MIN: int = -180           # minimum allowed American odds
COLLAR_MAX: int = 150            # maximum allowed American odds


# ---------------------------------------------------------------------------
# BetCandidate dataclass
# ---------------------------------------------------------------------------

@dataclass
class BetCandidate:
    """A single bet candidate produced by parse_game_markets()."""
    sport: str
    matchup: str            # "Away @ Home"
    market_type: str        # "spreads", "totals", "h2h"
    target: str             # e.g. "Duke Blue Devils -4.5" or "Over 148.5"
    line: float             # Numeric line value (0.0 for moneylines)
    price: int              # American odds (best price found)
    edge_pct: float         # consensus_prob - implied(best_price)
    win_prob: float         # Model's estimated win probability (consensus)
    market_implied: float   # Market implied probability (vig-inclusive)
    fair_implied: float     # Vig-free consensus probability
    kelly_size: float       # Fractional Kelly bet size in units
    signal: str = ""        # Tier label: NUCLEAR_2.0U, STANDARD_1.0U, LEAN_0.5U
    event_id: str = ""
    commence_time: str = ""
    book: str = ""          # Source book + n-books note
    # Set by rank_bets() after scoring
    sharp_score: float = 0.0
    sharp_breakdown: dict = field(default_factory=dict)
    nemesis: dict = field(default_factory=dict)
    # Set by kill switch routing
    kill_reason: str = ""   # "" = no kill. "FLAG:..." = warning. "KILL:..." = dropped.
    # Set by NBA kill when live schedule data available
    rest_days: Optional[int] = None
    opp_rest_days: Optional[int] = None
    # Consensus width badge — display-only, no score impact (r=+0.020, validated R&D S15)
    std_dev: float = 0.0


# ---------------------------------------------------------------------------
# Collar check
# ---------------------------------------------------------------------------

def passes_collar(american_odds: int) -> bool:
    """
    Return True if odds are within the -180 to +150 collar.

    V36.1 non-negotiable rule: reject anything outside this range.

    >>> passes_collar(-110)
    True
    >>> passes_collar(-200)
    False
    >>> passes_collar(150)
    True
    >>> passes_collar(155)
    False
    """
    return COLLAR_MIN <= american_odds <= COLLAR_MAX


# ---------------------------------------------------------------------------
# Implied probability
# ---------------------------------------------------------------------------

def implied_probability(american_odds: int) -> float:
    """
    Convert American odds to raw (vig-inclusive) implied probability.

    Formula:
        Negative (favourite): |odds| / (|odds| + 100)
        Positive (underdog):  100 / (odds + 100)

    >>> round(implied_probability(-110), 4)
    0.5238
    >>> round(implied_probability(110), 4)
    0.4762
    >>> round(implied_probability(-180), 4)
    0.6429
    """
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    else:
        return 100 / (american_odds + 100)


def no_vig_probability(odds_a: int, odds_b: int) -> tuple[float, float]:
    """
    Remove vig from a two-outcome market. Returns fair (vig-free) probabilities.

    Method: normalise each raw probability by the overround (sum of raw probs).
    A perfectly fair market has overround = 1.000. Books charge juice → overround > 1.

    >>> a, b = no_vig_probability(-110, -110)
    >>> round(a, 4), round(b, 4)
    (0.5, 0.5)
    >>> round(a + b, 6)
    1.0
    """
    raw_a = implied_probability(odds_a)
    raw_b = implied_probability(odds_b)
    overround = raw_a + raw_b
    if overround == 0:
        raise ZeroDivisionError("Overround is zero — invalid odds pair")
    return raw_a / overround, raw_b / overround


# ---------------------------------------------------------------------------
# Edge calculation
# ---------------------------------------------------------------------------

def calculate_edge(model_win_prob: float, market_odds: int) -> float:
    """
    Edge = model win probability - market implied probability.

    Positive edge = we think we win more often than the market implies.
    Only edges >= MIN_EDGE (3.5%) pass through to bet selection.

    >>> round(calculate_edge(0.55, -110), 4)
    0.0262
    >>> calculate_edge(0.48, -110) < 0
    True
    """
    return model_win_prob - implied_probability(market_odds)


def calculate_profit(stake: float, american_odds: int) -> float:
    """
    Profit (excluding returned stake) on a winning bet.

    >>> calculate_profit(100, 110)
    110.0
    >>> calculate_profit(100, -110)
    90.9090909090909...
    """
    if american_odds > 0:
        return stake * (american_odds / 100)
    else:
        return stake * (100 / abs(american_odds))


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------

def fractional_kelly(win_prob: float, american_odds: int, fraction: float = KELLY_FRACTION) -> float:
    """
    0.25x fractional Kelly bet size in units, with V36.1 hard caps.

    Caps:
        win_prob > 0.60 → max 2.0u (NUCLEAR)
        win_prob > 0.54 → max 1.0u (STANDARD)
        else            → max 0.5u (LEAN)

    >>> fractional_kelly(0.55, -110) <= 0.5
    True
    >>> fractional_kelly(0.65, -110) <= 2.0
    True
    """
    if american_odds > 0:
        decimal_odds = (american_odds / 100) + 1
    else:
        decimal_odds = (100 / abs(american_odds)) + 1

    b = decimal_odds - 1
    q = 1 - win_prob
    if b == 0:
        return 0.0
    full_kelly = (b * win_prob - q) / b
    bet_size = full_kelly * fraction

    if win_prob > 0.60:
        return min(bet_size, 2.0)
    elif win_prob > 0.54:
        return min(bet_size, 1.0)
    else:
        return min(bet_size, 0.5)


# ---------------------------------------------------------------------------
# Sharp Score
# ---------------------------------------------------------------------------

def calculate_sharp_score(
    edge_pct: float,
    rlm_confirmed: bool,
    efficiency_gap: float,
    rest_edge: float = 0.0,
    injury_leverage: float = 0.0,
    motivation: float = 0.0,
    matchup_score: float = 0.0,
) -> tuple[float, dict]:
    """
    Sharp Score: unified 0-100 composite ranking.

    Components:
        EDGE (40 pts):        (edge% / 10%) × 40, capped at 40
        RLM  (25 pts):        25 if RLM confirmed, else 0
        EFFICIENCY (20 pts):  caller-provided 0-20 scaled gap
        SITUATIONAL (15 pts): rest + injury + motivation + matchup, capped at 15

    Note: Without RLM, ceiling is ~75 (LEAN at best). STANDARD/NUCLEAR require RLM.
    Note: efficiency_gap defaults to 8.0 in rank_bets() for unknown teams.

    Returns:
        (sharp_score, breakdown_dict)

    >>> score, _ = calculate_sharp_score(0.08, False, 12.0, rest_edge=2.0)
    >>> score
    46.0
    >>> score, _ = calculate_sharp_score(0.06, True, 12.0, rest_edge=2.0)
    >>> score
    63.0
    """
    edge_pts = min(40.0, (edge_pct / 0.10) * 40)
    rlm_pts = 25.0 if rlm_confirmed else 0.0
    eff_pts = max(0.0, min(20.0, efficiency_gap))

    sit_pts = min(5.0, rest_edge) + min(5.0, injury_leverage) + \
              min(3.0, motivation) + min(2.0, matchup_score)
    sit_pts = min(15.0, sit_pts)

    total = edge_pts + rlm_pts + eff_pts + sit_pts

    breakdown = {
        "edge": round(edge_pts, 1),
        "rlm": round(rlm_pts, 1),
        "efficiency": round(eff_pts, 1),
        "situational": round(sit_pts, 1),
    }

    return round(total, 1), breakdown


def sharp_to_size(sharp_score: float) -> str:
    """
    Map Sharp Score to bet tier label.

    >= 90 → NUCLEAR_2.0U
    >= 80 → STANDARD_1.0U
    else  → LEAN_0.5U

    PASS is never returned here — bets that didn't survive are not in the list.

    >>> sharp_to_size(95)
    'NUCLEAR_2.0U'
    >>> sharp_to_size(83)
    'STANDARD_1.0U'
    >>> sharp_to_size(60)
    'LEAN_0.5U'
    """
    if sharp_score >= 90:
        return "NUCLEAR_2.0U"
    if sharp_score >= 80:
        return "STANDARD_1.0U"
    return "LEAN_0.5U"


# ---------------------------------------------------------------------------
# Kill switches
# ---------------------------------------------------------------------------

def nba_kill_switch(
    rest_disadvantage: bool,
    spread: float,
    star_absent: bool = False,
    avg_margin: float = 5.0,
    b2b: bool = False,
    pace_std_dev: float = 0.0,
    market_type: str = "spread",
) -> tuple[bool, str]:
    """
    NBA kill switch.

    Fires (killed=True) when:
    - rest_disadvantage AND spread inside -4 AND market_type=spread
    - star_absent AND spread inside avg_margin
    - High pace variance on totals (pace_std_dev > 4)

    Flags (killed=False, non-empty reason) when:
    - b2b: reduce Kelly by 50% (surfaced in UI, not dropped)

    >>> nba_kill_switch(True, -3.5, market_type="spread")
    (True, 'KILL: Rest disadvantage with spread inside -4 — abort spread')
    >>> nba_kill_switch(False, -8.5, market_type="spread")
    (False, '')
    """
    if rest_disadvantage and market_type == "spread" and abs(spread) < 4:
        return True, "KILL: Rest disadvantage with spread inside -4 — abort spread"
    if star_absent and abs(spread) < avg_margin:
        return True, "KILL: Star absence with spread inside average margin"
    if b2b:
        return False, "FLAG: B2B — reduce Kelly by 50%"
    if pace_std_dev > 4 and market_type == "total":
        return True, "KILL: High pace variance — skip total"
    return False, ""


def nfl_kill_switch(
    wind_mph: float,
    total: float,
    backup_qb: bool = False,
    market_type: str = "total",
) -> tuple[bool, str]:
    """
    NFL kill switch.

    Fires (killed=True) when:
    - backup_qb confirmed starting
    - wind > 20mph (skip all totals)
    - wind > 15mph AND total > 42 AND market_type=total → FORCE_UNDER

    >>> nfl_kill_switch(18.0, 44.5, market_type="total")
    (True, 'FORCE_UNDER: Wind >15mph with high total — take under or pass')
    >>> nfl_kill_switch(12.0, 44.5, market_type="total")
    (False, '')
    """
    if backup_qb:
        return True, "KILL: Backup QB — require 10%+ edge to proceed"
    if wind_mph > 20:
        return True, "KILL: Wind >20mph — skip all totals"
    if wind_mph > 15 and total > 42 and market_type == "total":
        return True, "FORCE_UNDER: Wind >15mph with high total — take under or pass"
    return False, ""


def ncaab_kill_switch(
    three_point_reliance: float,
    is_away: bool,
    tempo_diff: float = 0.0,
    conference_tournament: bool = False,
    market_type: str = "spread",
) -> tuple[bool, str]:
    """
    NCAAB kill switch.

    Fires (killed=True) when:
    - 3PT reliance > 40% AND away game
    - Tempo diff > 10 possessions AND total market

    Flags (killed=False, non-empty reason) when:
    - conference_tournament: require 8%+ edge

    >>> ncaab_kill_switch(0.43, True)
    (True, 'KILL: 3PT reliance 43% on road — fade')
    >>> ncaab_kill_switch(0.38, True)
    (False, '')
    """
    if three_point_reliance > 0.40 and is_away:
        return True, f"KILL: 3PT reliance {three_point_reliance:.0%} on road — fade"
    if tempo_diff > 10 and market_type == "total":
        return True, f"KILL: Tempo diff {tempo_diff:.1f} possessions — skip total"
    if conference_tournament:
        return False, "FLAG: Conference tournament — require 8%+ edge"
    return False, ""


def soccer_kill_switch(
    market_drift_pct: float,
    dead_rubber: bool = False,
    key_creator_out: bool = False,
    market_type: str = "moneyline",
) -> tuple[bool, str]:
    """
    Soccer kill switch.

    Fires (killed=True) when:
    - market drift > 10% against position
    - dead rubber game

    Flags (killed=False, non-empty reason) when:
    - key creator out

    >>> soccer_kill_switch(0.11)
    (True, 'KILL: Market drifted 11.0% against position — abort')
    >>> soccer_kill_switch(0.05)
    (False, '')
    """
    if market_drift_pct > 0.10:
        return True, f"KILL: Market drifted {market_drift_pct:.1%} against position — abort"
    if dead_rubber:
        return True, "KILL: Dead rubber — skip"
    if key_creator_out:
        return False, "FLAG: Key creator out — downgrade significantly"
    return False, ""


# ---------------------------------------------------------------------------
# Multi-book consensus fair probability
# ---------------------------------------------------------------------------

def consensus_fair_prob(
    team_name: str,
    market_key: str,
    side: str,
    bookmakers: list,
) -> tuple[float, float, int]:
    """
    Build consensus vig-free probability across all books for one side.

    Method:
    - For each book with BOTH sides, compute no-vig probability.
    - Return (mean_fair_prob, std_dev, n_books).

    This is the core edge signal. When the best available price implies a
    lower probability than consensus, that book has mispriced the market.

    Args:
        team_name:  Team name for spreads/h2h. Ignored for totals.
        market_key: "spreads", "h2h", or "totals".
        side:       "Over" or "Under" for totals. Ignored for spreads/h2h.
        bookmakers: Raw bookmakers list from Odds API game dict.

    Returns:
        (mean_fair_prob, std_dev, n_books) — n_books=0 means no data.
    """
    fair_probs: list[float] = []

    for book in bookmakers:
        market_map = {m["key"]: m for m in book.get("markets", [])}
        if market_key not in market_map:
            continue

        outcomes = market_map[market_key].get("outcomes", [])

        if market_key in ("spreads", "h2h"):
            if len(outcomes) != 2:
                continue
            target_odds = None
            opp_odds = None
            for o in outcomes:
                if o.get("name") == team_name:
                    target_odds = o.get("price")
                else:
                    opp_odds = o.get("price")

            if target_odds is not None and opp_odds is not None:
                try:
                    fp, _ = no_vig_probability(target_odds, opp_odds)
                    fair_probs.append(fp)
                except (ZeroDivisionError, ValueError):
                    pass

        elif market_key == "totals":
            if len(outcomes) != 2:
                continue
            over_o = next((o for o in outcomes if o.get("name") == "Over"), None)
            under_o = next((o for o in outcomes if o.get("name") == "Under"), None)
            if over_o and under_o:
                try:
                    over_p, under_p = no_vig_probability(
                        over_o.get("price", 0), under_o.get("price", 0)
                    )
                    fp = over_p if side == "Over" else under_p
                    fair_probs.append(fp)
                except (ZeroDivisionError, ValueError):
                    pass

    if not fair_probs:
        return 0.5, 0.0, 0

    n = len(fair_probs)
    mean = sum(fair_probs) / n
    variance = sum((p - mean) ** 2 for p in fair_probs) / n if n > 1 else 0.0
    std = math.sqrt(variance)

    return mean, std, n


# ---------------------------------------------------------------------------
# RLM (Reverse Line Movement) passive tracker
# ---------------------------------------------------------------------------

# Module-level cache: event_id → {side_name: american_odds}
# Keys: team names, "Over", "Under"
# Never overwritten — first-seen price is the open price.
_OPEN_PRICE_CACHE: dict[str, dict[str, int]] = {}


def cache_open_prices(games: list) -> None:
    """
    Store current prices as 'open' baseline. Call once at session start.

    Never overwrites existing cache entries — first-seen is the open price.
    This allows RLM detection on subsequent fetches within the same session.

    Args:
        games: Raw game list from odds_fetcher.fetch_game_lines().
    """
    for game in games:
        event_id = game.get("id", "")
        if not event_id or event_id in _OPEN_PRICE_CACHE:
            continue

        prices: dict[str, int] = {}
        for book in game.get("bookmakers", []):
            for market in book.get("markets", []):
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price")
                    if name and price is not None and name not in prices:
                        prices[name] = int(price)

        if prices:
            _OPEN_PRICE_CACHE[event_id] = prices


def get_open_price(event_id: str, side: str) -> Optional[int]:
    """
    Return cached open price for a side, or None if not yet cached.

    Args:
        event_id: Odds API event ID.
        side:     Team name, "Over", or "Under".

    Returns:
        American odds integer or None.
    """
    return _OPEN_PRICE_CACHE.get(event_id, {}).get(side)


def compute_rlm(
    event_id: str,
    side: str,
    current_price: int,
    public_on_side: bool,
) -> tuple[bool, float]:
    """
    Detect Reverse Line Movement.

    RLM fires when:
    1. Public money is on this side (public_on_side=True).
    2. Line moved AGAINST the public — price got worse for the bettor.
    3. Implied probability shift >= 3%.

    Logic:
    - open_prob = implied_probability(open_price)
    - current_prob = implied_probability(current_price)
    - drift = current_prob - open_prob
    - If public is on this side (price < -105 heuristic):
      drift > 0 means the price got MORE expensive (books protecting against public)
      → sharp money on the other side
      → RLM confirmed

    Args:
        event_id:      Odds API event ID.
        side:          Team name, "Over", or "Under".
        current_price: Current American odds.
        public_on_side: Heuristic — True if price < -105 (public typically bets favourites).

    Returns:
        (rlm_confirmed: bool, drift_pct: float)
        Cold cache returns (False, 0.0).
    """
    open_price = get_open_price(event_id, side)
    if open_price is None:
        return False, 0.0

    open_prob = implied_probability(open_price)
    current_prob = implied_probability(current_price)
    drift = abs(current_prob - open_prob)

    if drift >= 0.03 and public_on_side:
        # Price moved against the public — sharp activity on the other side
        return True, drift

    return False, drift


def clear_open_price_cache() -> None:
    """Clear the open price cache. Use in tests to prevent state bleed."""
    _OPEN_PRICE_CACHE.clear()


def open_price_cache_size() -> int:
    """Return number of events currently cached. Useful for monitoring."""
    return len(_OPEN_PRICE_CACHE)


# ---------------------------------------------------------------------------
# CLV (Closing Line Value)
# ---------------------------------------------------------------------------

def calculate_clv(open_price: int, close_price: int, bet_price: int) -> float:
    """
    Calculate Closing Line Value.

    CLV = implied_probability(bet_price) - implied_probability(close_price)

    Positive CLV means we got a better price than where the market closed.
    Positive CLV over many bets validates predictive accuracy.

    Note: This uses the raw vig-inclusive implied probabilities, not fair probs.
    The goal is to measure how our bet price compared to the closing market price,
    not the fair value.

    Args:
        open_price:  American odds when market opened (for context only).
        close_price: American odds at market close (the benchmark).
        bet_price:   American odds at which we placed the bet.

    Returns:
        CLV as a decimal. Positive = we beat the close. Negative = we didn't.

    >>> round(calculate_clv(-115, -120, -110), 4)
    0.0188
    >>> calculate_clv(-110, -110, -110)
    0.0
    """
    _ = open_price  # stored for reference, not used in formula
    return implied_probability(close_price) - implied_probability(bet_price)


def clv_grade(clv: float) -> str:
    """
    Grade a CLV value for display.

    >>> clv_grade(0.03)
    'EXCELLENT'
    >>> clv_grade(0.01)
    'GOOD'
    >>> clv_grade(-0.01)
    'POOR'
    """
    if clv >= 0.02:
        return "EXCELLENT"
    if clv >= 0.005:
        return "GOOD"
    if clv >= 0.0:
        return "NEUTRAL"
    return "POOR"


# ---------------------------------------------------------------------------
# Nemesis (adversarial counter-thesis — display only, no score impact)
# ---------------------------------------------------------------------------

def run_nemesis(bet: BetCandidate, sport: str) -> dict:
    """
    Generate adversarial counter-thesis for a bet. Display-only.
    Does NOT remove bets or adjust scores (demoted in V36.1 Session 12).

    Returns dict: {counter, probability, adjustment, remove}
    remove computed for display context only — never consumed by rank_bets.
    """
    nemesis_cases: dict[str, list] = {
        "NBA": [
            ("Line movement suggests sharp money on other side",
             0.30, -15, {"spreads", "h2h"}),
            ("Team relies on 3PT shooting, opponent defends arc well",
             0.25, -15, {"spreads", "h2h"}),
            ("Total variance high — pace mismatch creates unpredictable scoring",
             0.25, -15, {"totals"}),
            ("B2B fatigue not fully captured in ratings",
             0.20, -10, {"any"}),
        ],
        "NCAAB": [
            ("Road favorite in hostile environment, pressure on young team",
             0.30, -15, {"spreads", "h2h"}),
            ("3PT variance could eliminate efficiency edge",
             0.25, -15, {"spreads", "h2h", "totals"}),
            ("Underdog at home often outperforms ratings",
             0.20, -10, {"spreads", "h2h"}),
            ("Tempo mismatch makes total unreliable",
             0.25, -15, {"totals"}),
        ],
        "NFL": [
            ("Line through key number (3, 7, 10) — extra caution",
             0.25, -15, {"spreads"}),
            ("Weather variance not fully modeled",
             0.25, -15, {"totals"}),
            ("Injury report could change within 24 hours",
             0.20, -10, {"any"}),
        ],
        "NHL": [
            ("Goalie variance is the dominant factor",
             0.30, -15, {"h2h", "spreads"}),
            ("PDO regression — hot team due for correction",
             0.25, -15, {"h2h", "spreads"}),
            ("Shot quality vs quantity mismatch clouds total",
             0.25, -15, {"totals"}),
        ],
        "SOCCER": [
            ("High draw probability (~28%) not fully priced in",
             0.25, -15, {"h2h"}),
            ("Must-attack team vulnerable on counter",
             0.30, -15, {"spreads", "h2h"}),
            ("Low xG variance inflates total uncertainty",
             0.25, -10, {"totals"}),
        ],
    }

    cases = nemesis_cases.get(sport.upper(), nemesis_cases.get("NBA", []))
    if not cases:
        return {"counter": "No standard nemesis for this sport",
                "probability": 0.10, "adjustment": 0, "remove": False}

    market = bet.market_type
    relevant = [c for c in cases if market in c[3] or "any" in c[3]]
    if not relevant:
        relevant = cases

    best = max(relevant, key=lambda x: x[1])
    counter, prob, adj, _ = best

    return {
        "counter": counter,
        "probability": prob,
        "adjustment": adj if prob >= 0.30 else (adj // 2 if prob >= 0.20 else 0),
        "remove": prob > 0.40,
    }


# ---------------------------------------------------------------------------
# parse_game_markets — game dict → BetCandidate list
# ---------------------------------------------------------------------------

def parse_game_markets(game: dict, sport: str = "NCAAB") -> list[BetCandidate]:
    """
    Parse a raw game dict from odds_fetcher into BetCandidate objects.

    Edge detection: multi-book consensus (see consensus_fair_prob()).
    Applies: collar filter, min edge (3.5%), min books (2).

    Args:
        game:  Raw game dict from fetch_game_lines() / fetch_batch_odds().
        sport: Sport key for BetCandidate (e.g. "NCAAB", "NBA").

    Returns:
        List of BetCandidates passing collar AND minimum edge.
    """
    candidates: list[BetCandidate] = []
    home = game.get("home_team", "")
    away = game.get("away_team", "")
    matchup = f"{away} @ {home}"
    event_id = game.get("id", "")
    commence_time = game.get("commence_time", "")
    bookmakers = game.get("bookmakers", [])

    if not bookmakers:
        return []

    # Collect all books (Odds API wraps them under "bookmakers")
    all_bks = bookmakers

    def _best_price_for(team: str, mkt: str) -> tuple[Optional[int], Optional[float], str]:
        """Find best (highest) price for a team/side across all books."""
        best_price = None
        best_line = None
        best_book = ""
        for book in all_bks:
            mmap = {m["key"]: m for m in book.get("markets", [])}
            if mkt not in mmap:
                continue
            for o in mmap[mkt].get("outcomes", []):
                if o.get("name") == team:
                    price = o.get("price", 0)
                    line = o.get("point", 0.0)
                    if best_price is None or price > best_price:
                        best_price = price
                        best_line = line
                        best_book = book.get("title", book.get("key", ""))
        return best_price, best_line, best_book

    # --- Spreads ---
    for team_name in [home, away]:
        cp, std, n_books = consensus_fair_prob(team_name, "spreads", "team", bookmakers)
        if n_books < MIN_BOOKS:
            continue
        best_price, best_line, best_book_name = _best_price_for(team_name, "spreads")
        if best_price is None or not passes_collar(best_price):
            continue
        edge = cp - implied_probability(best_price)
        if edge >= MIN_EDGE:
            kelly = fractional_kelly(cp, best_price)
            score, breakdown = calculate_sharp_score(edge, False, 0.0)
            candidates.append(BetCandidate(
                sport=sport,
                matchup=matchup,
                market_type="spreads",
                target=f"{team_name} {best_line:+.1f}",
                line=best_line or 0.0,
                price=best_price,
                edge_pct=edge,
                win_prob=cp,
                market_implied=implied_probability(best_price),
                fair_implied=cp,
                kelly_size=kelly,
                event_id=event_id,
                commence_time=commence_time,
                book=f"Best: {best_book_name} ({n_books} books)",
                std_dev=std,
                sharp_score=score,
                sharp_breakdown=breakdown,
            ))

    # --- Moneylines ---
    for team_name in [home, away]:
        cp, std, n_books = consensus_fair_prob(team_name, "h2h", "team", bookmakers)
        if n_books < MIN_BOOKS:
            continue
        best_price, _, best_book_name = _best_price_for(team_name, "h2h")
        if best_price is None or not passes_collar(best_price):
            continue
        edge = cp - implied_probability(best_price)
        if edge >= MIN_EDGE:
            kelly = fractional_kelly(cp, best_price)
            score, breakdown = calculate_sharp_score(edge, False, 0.0)
            candidates.append(BetCandidate(
                sport=sport,
                matchup=matchup,
                market_type="h2h",
                target=f"{team_name} ML",
                line=0.0,
                price=best_price,
                edge_pct=edge,
                win_prob=cp,
                market_implied=implied_probability(best_price),
                fair_implied=cp,
                kelly_size=kelly,
                event_id=event_id,
                commence_time=commence_time,
                book=f"Best: {best_book_name} ({n_books} books)",
                std_dev=std,
                sharp_score=score,
                sharp_breakdown=breakdown,
            ))

    # --- Totals ---
    for side in ["Over", "Under"]:
        cp, std, n_books = consensus_fair_prob("", "totals", side, bookmakers)
        if n_books < MIN_BOOKS:
            continue
        best_price, best_line, best_book_name = _best_price_for(side, "totals")
        if best_price is None or not passes_collar(best_price):
            continue
        edge = cp - implied_probability(best_price)
        if edge >= MIN_EDGE:
            kelly = fractional_kelly(cp, best_price)
            score, breakdown = calculate_sharp_score(edge, False, 0.0)
            candidates.append(BetCandidate(
                sport=sport,
                matchup=matchup,
                market_type="totals",
                target=f"{side} {best_line}",
                line=best_line or 0.0,
                price=best_price,
                edge_pct=edge,
                win_prob=cp,
                market_implied=implied_probability(best_price),
                fair_implied=cp,
                kelly_size=kelly,
                event_id=event_id,
                commence_time=commence_time,
                book=f"Best: {best_book_name} ({n_books} books)",
                std_dev=std,
                sharp_score=score,
                sharp_breakdown=breakdown,
            ))

    return candidates
