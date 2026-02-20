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
- Kill switch logic (NBA, NFL, NCAAB, NCAAF, Soccer, NHL, Tennis)
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
from datetime import datetime, timezone
from typing import Optional

# Lazy import guard: originator_engine must NOT import math_engine (circular).
# math_engine CAN import originator_engine safely (one-way dependency).
from core.originator_engine import (
    poisson_soccer,
    efficiency_gap_to_soccer_strength,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_EDGE: float = 0.035          # 3.5% minimum edge
MIN_BOOKS: int = 2               # minimum books for consensus
KELLY_FRACTION: float = 0.25     # fractional Kelly multiplier
SHARP_THRESHOLD: float = 45.0    # minimum Sharp Score to pass (raise to 50-55 after RLM wired)
COLLAR_MIN: int = -180           # minimum allowed American odds
COLLAR_MAX: int = 150            # maximum allowed American odds
COLLAR_MAX_SOCCER: int = 400     # expanded cap for soccer 3-way h2h (dogs/draws reach +350+)
COLLAR_MIN_SOCCER: int = -250    # expanded floor for soccer heavy favourites

# Soccer sports use 3-way h2h (home/away/draw) — need separate consensus logic
SOCCER_SPORTS: frozenset = frozenset({
    "EPL", "LIGUE1", "BUNDESLIGA", "SERIE_A", "LA_LIGA", "MLS",
})


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


def passes_collar_soccer(american_odds: int) -> bool:
    """
    Expanded collar for soccer 3-way h2h markets.

    Soccer dogs and draws commonly price at +200 to +400.
    The standard collar (+150 max) would reject all such outcomes.
    Favourites can be heavier than -180, so floor is also expanded.

    Only used for soccer h2h outcomes (home/away/draw), NOT for soccer totals.

    >>> passes_collar_soccer(-110)
    True
    >>> passes_collar_soccer(-250)
    True
    >>> passes_collar_soccer(-260)
    False
    >>> passes_collar_soccer(400)
    True
    >>> passes_collar_soccer(401)
    False
    """
    return COLLAR_MIN_SOCCER <= american_odds <= COLLAR_MAX_SOCCER


# ---------------------------------------------------------------------------
# 3-way no-vig probability (soccer h2h)
# ---------------------------------------------------------------------------

def no_vig_probability_3way(
    odds_a: int,
    odds_b: int,
    odds_c: int,
) -> tuple[float, float, float]:
    """
    Remove bookmaker margin from a 3-outcome market (home/away/draw).

    Method: proportional normalization (fair share of total overround).
    Each raw implied probability is divided by the sum of all three.

    Args:
        odds_a: American odds for outcome A (home win).
        odds_b: American odds for outcome B (away win).
        odds_c: American odds for outcome C (draw).

    Returns:
        (fair_a, fair_b, fair_c) vig-free probabilities summing to 1.0.

    Raises:
        ZeroDivisionError: if any implied probability is zero.
        ValueError: if total implied prob is zero.

    >>> a, b, c = no_vig_probability_3way(-105, 290, 250)
    >>> round(a + b + c, 4)
    1.0
    >>> a > b  # favourite always has higher fair prob
    True
    """
    p_a = implied_probability(odds_a)
    p_b = implied_probability(odds_b)
    p_c = implied_probability(odds_c)
    total = p_a + p_b + p_c
    if total <= 0:
        raise ValueError(f"Total implied probability non-positive: {total}")
    return p_a / total, p_b / total, p_c / total


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
    is_road_b2b: bool = False,
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
    - is_road_b2b: road team on B2B — require 8%+ edge (harsher than home B2B)
    - b2b (home): reduce Kelly by 50% only

    Home B2B vs. Road B2B differentiation:
    - Road B2B compounds fatigue + travel — higher edge requirement (8%+)
    - Home B2B is partially offset by home court — Kelly reduction only
    - is_road_b2b=True overrides b2b=True with the stricter flag

    >>> nba_kill_switch(True, -3.5, market_type="spread")
    (True, 'KILL: Rest disadvantage with spread inside -4 — abort spread')
    >>> nba_kill_switch(False, -8.5, market_type="spread")
    (False, '')
    >>> nba_kill_switch(False, 0.0, b2b=True, is_road_b2b=True)
    (False, 'FLAG: Road B2B — require 8%+ edge (travel + fatigue compound)')
    >>> nba_kill_switch(False, 0.0, b2b=True, is_road_b2b=False)
    (False, 'FLAG: Home B2B — reduce Kelly 50%')
    """
    if rest_disadvantage and market_type == "spread" and abs(spread) < 4:
        return True, "KILL: Rest disadvantage with spread inside -4 — abort spread"
    if star_absent and abs(spread) < avg_margin:
        return True, "KILL: Star absence with spread inside average margin"
    if b2b:
        if is_road_b2b:
            return False, "FLAG: Road B2B — require 8%+ edge (travel + fatigue compound)"
        return False, "FLAG: Home B2B — reduce Kelly 50%"
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


def nhl_kill_switch(
    backup_goalie: bool,
    b2b: bool = False,
    goalie_confirmed: bool = True,
) -> tuple[bool, str]:
    """
    NHL kill switch.

    Fires (killed=True) when:
    - backup_goalie confirmed starting (no star between pipes)

    Flags (killed=False, non-empty reason) when:
    - b2b: reduce Kelly by 50%
    - not goalie_confirmed: starter data not yet available — require higher edge

    Returns immediately if backup confirmed — b2b is secondary.

    Args:
        backup_goalie: True if backup/non-starter goalie is in net.
        b2b: True if team is on back-to-back (second game in 2 nights).
        goalie_confirmed: False if starter data not yet available from NHL API.

    >>> nhl_kill_switch(True)
    (True, 'KILL: Backup goalie confirmed — require 12%+ edge to override')
    >>> nhl_kill_switch(False, b2b=True)
    (False, 'FLAG: B2B — reduce Kelly 50%')
    >>> nhl_kill_switch(False, goalie_confirmed=False)
    (False, 'FLAG: Goalie not yet confirmed — require 8%+ edge')
    >>> nhl_kill_switch(False)
    (False, '')
    """
    if backup_goalie:
        return True, "KILL: Backup goalie confirmed — require 12%+ edge to override"
    if b2b:
        return False, "FLAG: B2B — reduce Kelly 50%"
    if not goalie_confirmed:
        return False, "FLAG: Goalie not yet confirmed — require 8%+ edge"
    return False, ""


NCAAF_SPREAD_KILL_THRESHOLD: float = 28.0   # spreads ≥ this are noise-dominated blowouts
NCAAF_SEASON_MONTHS: frozenset = frozenset({9, 10, 11, 12, 1})  # Sep–Jan inclusive


def ncaaf_kill_switch(
    spread_line: float,
    current_month: int,
) -> tuple[bool, str]:
    """
    NCAAF kill switch — blowout spread filter + off-season gate.

    NCAAF spreads regularly reach -35 or more for elite teams vs. inferior opponents.
    These "blowout" spreads exhibit high book-to-book variance that creates false
    consensus signals: the noise in agreeing on -33 vs -36 is structural, not sharp.

    Kill logic:
    - Off-season (Feb–Aug): kill all NCAAF markets — no reliable data.
    - Spread ≥ 28 pts (either side): kill — blowout noise zone.

    Args:
        spread_line: The absolute value of the spread (e.g. 14.5, 28.0, 35.0).
                     Pass abs(point) from the bookmaker outcome.
        current_month: Integer month (1–12). Use datetime.now().month.

    Returns:
        (killed: bool, reason: str)

    >>> ncaaf_kill_switch(14.5, 10)
    (False, '')
    >>> ncaaf_kill_switch(28.0, 10)
    (True, 'KILL: NCAAF spread 28.0 ≥ 28 pts — blowout noise zone')
    >>> ncaaf_kill_switch(14.5, 4)
    (True, 'KILL: NCAAF off-season (month 4) — no reliable model data')
    >>> ncaaf_kill_switch(35.0, 11)
    (True, 'KILL: NCAAF spread 35.0 ≥ 28 pts — blowout noise zone')
    """
    if current_month not in NCAAF_SEASON_MONTHS:
        return True, f"KILL: NCAAF off-season (month {current_month}) — no reliable model data"
    if spread_line >= NCAAF_SPREAD_KILL_THRESHOLD:
        return True, f"KILL: NCAAF spread {spread_line} ≥ {NCAAF_SPREAD_KILL_THRESHOLD:.0f} pts — blowout noise zone"
    return False, ""


def tennis_kill_switch(
    surface: str,
    favourite_implied_prob: float,
    is_favourite_bet: bool,
    market_type: str = "h2h",
) -> tuple[bool, str]:
    """
    Tennis kill switch — zero external API cost, static surface inference only.

    Surface data is derived from tournament name (Odds API sport key).
    Surface data is free — inferred from Odds API tournament key, zero cost.
    Player-specific surface win rates are not needed: structural surface risk
    (clay variance, grass serve dominance) is the mathematically valid signal.

    Kill logic:
    - Clay + heavy favourite (>72% implied) + h2h → FLAG: surface upsets frequent
    - Grass + heavy favourite (>75% implied) + h2h → FLAG: serve variance high
    - Unknown surface → FLAG: require 8%+ edge
    - Hard court → no flag (most predictable surface)
    - Totals are not flagged for surface (not applicable in tennis context)

    Note: We do NOT kill outright — without per-player surface records we cannot
    confirm the specific surface handicap. The FLAG reduces confidence and prompts
    higher edge requirement, consistent with the incomplete-information doctrine.

    Args:
        surface: "clay", "grass", "hard", or "unknown" from tennis_data.surface_from_sport_key().
        favourite_implied_prob: Market-implied win probability for the favourite.
            Use implied_probability(price) to compute from American odds.
        is_favourite_bet: True if this candidate is betting ON the favourite.
        market_type: "h2h", "spreads", or "totals".

    Returns:
        (killed, reason) — killed is always False (FLAG only, no KILL).

    >>> tennis_kill_switch("clay", 0.75, True, "h2h")
    (False, 'FLAG: Clay court + heavy favourite (75.0%) — upsets common, require 8%+ edge')
    >>> tennis_kill_switch("hard", 0.75, True, "h2h")
    (False, '')
    >>> tennis_kill_switch("unknown", 0.60, True, "h2h")
    (False, 'FLAG: Surface unknown — require 8%+ edge')
    >>> tennis_kill_switch("clay", 0.65, False, "h2h")
    (False, '')
    >>> tennis_kill_switch("clay", 0.75, True, "totals")
    (False, '')
    """
    # Totals are not surface-sensitive in tennis (not typically offered or relevant)
    if market_type == "totals":
        return False, ""

    # Unknown surface — incomplete information, apply blanket edge requirement
    if surface == "unknown":
        return False, "FLAG: Surface unknown — require 8%+ edge"

    # Clay: highest upset frequency for heavy favourites
    if surface == "clay" and is_favourite_bet and favourite_implied_prob > 0.72:
        pct = favourite_implied_prob * 100
        return False, f"FLAG: Clay court + heavy favourite ({pct:.1f}%) — upsets common, require 8%+ edge"

    # Grass: high variance due to serving dominance
    if surface == "grass" and is_favourite_bet and favourite_implied_prob > 0.75:
        pct = favourite_implied_prob * 100
        return False, f"FLAG: Grass court + heavy favourite ({pct:.1f}%) — serve variance high, require 7%+ edge"

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


def consensus_fair_prob_3way(
    team_name: str,
    bookmakers: list,
    outcome_label: str = "home",
) -> tuple[float, float, int]:
    """
    Consensus vig-free probability for one outcome in a 3-way h2h market.

    Used for soccer h2h where each book posts home/away/draw odds.
    Requires all 3 outcomes present per book to compute no-vig probability.

    Args:
        team_name:     Name of the team (home or away) or "Draw" for the draw.
        bookmakers:    Raw bookmakers list from Odds API game dict.
        outcome_label: "home", "away", or "draw" — used only for logging.
                       The actual matching is done by team_name.

    Returns:
        (mean_fair_prob, std_dev, n_books) — n_books=0 means no data.

    >>> # Cannot easily doctest without mock data; see test_math_engine.py
    """
    fair_probs: list[float] = []

    for book in bookmakers:
        market_map = {m["key"]: m for m in book.get("markets", [])}
        if "h2h" not in market_map:
            continue
        outcomes = market_map["h2h"].get("outcomes", [])
        if len(outcomes) != 3:
            continue

        prices = {o.get("name"): o.get("price") for o in outcomes}
        if len(prices) != 3 or None in prices.values():
            continue
        if team_name not in prices:
            continue

        price_list = list(prices.values())
        try:
            odds_a, odds_b, odds_c = price_list[0], price_list[1], price_list[2]
            fp_all = no_vig_probability_3way(odds_a, odds_b, odds_c)
            # Find which index corresponds to team_name
            names_list = list(prices.keys())
            idx = names_list.index(team_name)
            fair_probs.append(fp_all[idx])
        except (ZeroDivisionError, ValueError, IndexError):
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

# RLM fire counter — increments each time compute_rlm() returns True.
# Accumulates across scheduler polls for the SHARP_THRESHOLD raise gate.
# Target: raise SHARP_THRESHOLD 45 → 50 once _rlm_fire_count >= RLM_FIRE_GATE.
RLM_FIRE_GATE: int = 20          # minimum confirmed RLM fires before threshold raise
_rlm_fire_count: int = 0


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
    global _rlm_fire_count

    open_price = get_open_price(event_id, side)
    if open_price is None:
        return False, 0.0

    open_prob = implied_probability(open_price)
    current_prob = implied_probability(current_price)
    drift = abs(current_prob - open_prob)

    if drift >= 0.03 and public_on_side:
        # Price moved against the public — sharp activity on the other side
        _rlm_fire_count += 1
        return True, drift

    return False, drift


def seed_open_prices_from_db(open_prices_dict: dict) -> int:
    """
    Pre-seed the RLM cache from persisted line_history open prices.

    Called once at app startup after init_db(). Fills _OPEN_PRICE_CACHE with
    historical open prices so RLM detection works from the first fetch of
    a new session, rather than requiring two fetches in the same process.

    Args:
        open_prices_dict: Dict from line_logger.get_open_prices_for_rlm().
                          Format: { event_id: { team_name: open_price } }

    Returns:
        Number of events seeded (new entries only — never overwrites existing).
    """
    seeded = 0
    for event_id, prices in open_prices_dict.items():
        if event_id not in _OPEN_PRICE_CACHE:
            _OPEN_PRICE_CACHE[event_id] = dict(prices)
            seeded += 1
    return seeded


def clear_open_price_cache() -> None:
    """Clear the open price cache. Use in tests to prevent state bleed."""
    _OPEN_PRICE_CACHE.clear()


def open_price_cache_size() -> int:
    """Return number of events currently cached. Useful for monitoring."""
    return len(_OPEN_PRICE_CACHE)


def get_rlm_fire_count() -> int:
    """
    Return the cumulative number of confirmed RLM fires this process.

    Increments each time compute_rlm() detects a genuine reverse line move.
    Used by the sidebar health dashboard and SHARP_THRESHOLD raise gate.

    Returns:
        int — total RLM fires since process start (or last reset).
    """
    return _rlm_fire_count


def reset_rlm_fire_count() -> None:
    """
    Reset the RLM fire counter to zero.
    Intended for testing only — never call from production code.
    """
    global _rlm_fire_count
    _rlm_fire_count = 0


def rlm_gate_status() -> dict:
    """
    Return structured RLM raise-gate status for sidebar display.

    Returns:
        {
            "fire_count":   int,   confirmed RLM fires this process
            "gate":         int,   RLM_FIRE_GATE constant
            "pct_to_gate":  float, fraction toward gate (capped at 1.0)
            "gate_reached": bool,  True if fire_count >= RLM_FIRE_GATE
        }
    """
    pct = min(1.0, _rlm_fire_count / RLM_FIRE_GATE) if RLM_FIRE_GATE > 0 else 0.0
    return {
        "fire_count":   _rlm_fire_count,
        "gate":         RLM_FIRE_GATE,
        "pct_to_gate":  pct,
        "gate_reached": _rlm_fire_count >= RLM_FIRE_GATE,
    }


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

def parse_game_markets(
    game: dict,
    sport: str = "NCAAB",
    nhl_goalie_status: Optional[dict] = None,
    efficiency_gap: float = 0.0,
    tennis_sport_key: str = "",
    rest_days: Optional[dict] = None,
    wind_mph: float = 0.0,
) -> list[BetCandidate]:
    """
    Parse a raw game dict from odds_fetcher into BetCandidate objects.

    Edge detection: multi-book consensus (see consensus_fair_prob()).
    Applies: collar filter, min edge (3.5%), min books (2).

    Args:
        game:  Raw game dict from fetch_game_lines() / fetch_batch_odds().
        sport: Sport key for BetCandidate (e.g. "NCAAB", "NHL", "TENNIS_ATP").
        nhl_goalie_status: Optional goalie starter dict from nhl_data module.
            If provided and sport=="NHL", nhl_kill_switch() is evaluated.
            Format: {"away": {"starter_confirmed": bool, "starter_name": str|None},
                     "home": {"starter_confirmed": bool, "starter_name": str|None}}
        efficiency_gap: Pre-scaled 0-20 efficiency advantage for home team.
            Computed by efficiency_feed.get_efficiency_gap(home, away).
            10.0 = evenly matched. >10 = home structural edge.
            Defaults to 0.0 (no efficiency component) — callers should supply
            this from efficiency_feed rather than leaving at default.
        tennis_sport_key: Odds API sport key string for tennis markets, e.g.
            "tennis_atp_french_open". Used to infer court surface via
            tennis_data.surface_from_sport_key(). Empty string = not a tennis game.
            When non-empty and sport starts with "TENNIS", tennis_kill_switch() fires.
        rest_days: Optional dict mapping team_name → rest_days (int) or None.
            Computed by compute_rest_days_from_schedule() in odds_fetcher.
            rest_days=0 means B2B. None means only 1 game in window — treated as
            adequate rest. Used for NBA B2B home/road differentiation.
        wind_mph: Wind speed in mph at the home stadium for NFL games.
            Computed by weather_feed.get_stadium_wind(). Defaults to 0.0 (stub).
            Indoor/retractable stadiums should pass 0.0. Used for nfl_kill_switch().

    Returns:
        List of BetCandidates passing collar AND minimum edge.
        BetCandidates with KILL reason have kill_reason set and are included
        so the UI can display them as killed (not silently dropped).
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

    def _get_all_h2h_outcome_names(bks: list) -> list[str]:
        """Return all unique outcome names from h2h markets across books."""
        seen: dict[str, int] = {}
        for book in bks:
            for mkt in book.get("markets", []):
                if mkt["key"] != "h2h":
                    continue
                for o in mkt.get("outcomes", []):
                    name = o.get("name", "")
                    if name:
                        seen[name] = seen.get(name, 0) + 1
        # Only include outcomes seen in at least MIN_BOOKS books
        return [name for name, count in seen.items() if count >= MIN_BOOKS]

    # NCAAF off-season + blowout gate (fired once per game, before inner loop)
    is_ncaaf = sport.upper() == "NCAAF"
    _ncaaf_month = datetime.now(timezone.utc).month

    # NBA B2B rest-day lookup (zero extra API calls — derived from schedule timestamps)
    is_nba = sport.upper() == "NBA"
    _rd = rest_days or {}

    def _nba_b2b_flags(team_name: str, is_road: bool) -> tuple[bool, bool]:
        """Return (b2b, is_road_b2b) for a team. False,False if rest data absent."""
        days = _rd.get(team_name)
        if days is None:
            return False, False
        on_b2b = days == 0
        return on_b2b, (on_b2b and is_road)

    # --- Spreads ---
    for team_name in [home, away]:
        cp, std, n_books = consensus_fair_prob(team_name, "spreads", "team", bookmakers)
        if n_books < MIN_BOOKS:
            continue
        best_price, best_line, best_book_name = _best_price_for(team_name, "spreads")
        if best_price is None or not passes_collar(best_price):
            continue
        # NCAAF: blowout filter + off-season gate
        if is_ncaaf:
            _spread_abs = abs(best_line) if best_line is not None else 0.0
            _ncaaf_killed, _ = ncaaf_kill_switch(_spread_abs, _ncaaf_month)
            if _ncaaf_killed:
                continue
        edge = cp - implied_probability(best_price)
        if edge >= MIN_EDGE:
            kelly = fractional_kelly(cp, best_price)
            public_on_side = best_price < -105
            rlm_confirmed, _rlm_drift = compute_rlm(event_id, team_name, best_price, public_on_side)
            score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap)
            # NBA B2B — home/road differentiated flag
            _kill_reason = ""
            if is_nba:
                _is_road = team_name == away
                _opp = home if _is_road else away
                _b2b, _is_road_b2b = _nba_b2b_flags(team_name, _is_road)
                _opp_rest = _rd.get(_opp)
                _team_rest = _rd.get(team_name)
                _rest_disadv = (
                    _team_rest is not None and _opp_rest is not None
                    and _team_rest < _opp_rest
                )
                _, _kill_reason = nba_kill_switch(
                    rest_disadvantage=_rest_disadv,
                    spread=best_line or 0.0,
                    b2b=_b2b,
                    is_road_b2b=_is_road_b2b,
                    market_type="spread",
                )
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
                kill_reason=_kill_reason,
            ))

    # --- Moneylines / Soccer 3-way H2H ---
    is_soccer = sport.upper() in SOCCER_SPORTS
    if is_soccer:
        # Soccer 3-way: evaluate home, away, and draw separately
        # Uses expanded collar and 3-way no-vig consensus
        all_h2h_outcomes = _get_all_h2h_outcome_names(bookmakers)
        for outcome_name in all_h2h_outcomes:
            cp, std, n_books = consensus_fair_prob_3way(outcome_name, bookmakers)
            if n_books < MIN_BOOKS:
                continue
            best_price, _, best_book_name = _best_price_for(outcome_name, "h2h")
            if best_price is None or not passes_collar_soccer(best_price):
                continue
            edge = cp - implied_probability(best_price)
            if edge >= MIN_EDGE:
                kelly = fractional_kelly(cp, best_price)
                public_on_side = best_price < -105
                rlm_confirmed, _rlm_drift = compute_rlm(event_id, outcome_name, best_price, public_on_side)
                score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap)
                label = outcome_name if outcome_name == "Draw" else f"{outcome_name} ML"
                candidates.append(BetCandidate(
                    sport=sport,
                    matchup=matchup,
                    market_type="h2h",
                    target=label,
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
    else:
        # Standard 2-way moneyline (NBA, NFL, NHL, NCAAB, Tennis, etc.)
        for team_name in [home, away]:
            cp, std, n_books = consensus_fair_prob(team_name, "h2h", "team", bookmakers)
            if n_books < MIN_BOOKS:
                continue
            best_price, _, best_book_name = _best_price_for(team_name, "h2h")
            if best_price is None or not passes_collar(best_price):
                continue
            # NCAAF: off-season gate applies to h2h too (no spread line to filter by here)
            if is_ncaaf:
                _ncaaf_killed_h2h, _ = ncaaf_kill_switch(0.0, _ncaaf_month)
                if _ncaaf_killed_h2h:
                    continue
            edge = cp - implied_probability(best_price)
            if edge >= MIN_EDGE:
                kelly = fractional_kelly(cp, best_price)
                public_on_side = best_price < -105
                rlm_confirmed, _rlm_drift = compute_rlm(event_id, team_name, best_price, public_on_side)
                score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap)
                # NBA B2B — h2h (spread=0 proxy)
                _h2h_kill_reason = ""
                if is_nba:
                    _is_road = team_name == away
                    _opp = home if _is_road else away
                    _b2b_h, _is_road_b2b_h = _nba_b2b_flags(team_name, _is_road)
                    _opp_rest_h = _rd.get(_opp)
                    _team_rest_h = _rd.get(team_name)
                    _rest_disadv_h = (
                        _team_rest_h is not None and _opp_rest_h is not None
                        and _team_rest_h < _opp_rest_h
                    )
                    _, _h2h_kill_reason = nba_kill_switch(
                        rest_disadvantage=_rest_disadv_h,
                        spread=0.0,
                        b2b=_b2b_h,
                        is_road_b2b=_is_road_b2b_h,
                        market_type="h2h",
                    )
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
                    kill_reason=_h2h_kill_reason,
                ))

    # NFL wind: pre-compute is_nfl flag for totals + spreads blocks below
    is_nfl = sport.upper() == "NFL"

    # Soccer Poisson: pre-compute 1X2 + over/under probs for soccer totals validation
    _poisson_over_prob: Optional[float] = None
    _poisson_under_prob: Optional[float] = None
    if is_soccer:
        try:
            _h_att, _a_att, _h_def, _a_def = efficiency_gap_to_soccer_strength(efficiency_gap)
            _pr = poisson_soccer(
                home_attack=_h_att,
                away_attack=_a_att,
                home_defense=_h_def,
                away_defense=_a_def,
                total_line=2.5,  # default; overridden per candidate below
                apply_home_advantage=True,
            )
            _poisson_over_prob = _pr.over_probability
            _poisson_under_prob = _pr.under_probability
        except Exception:
            pass  # Poisson failure never blocks standard consensus path

    # --- Totals ---
    for side in ["Over", "Under"]:
        cp, std, n_books = consensus_fair_prob("", "totals", side, bookmakers)
        if n_books < MIN_BOOKS:
            continue
        best_price, best_line, best_book_name = _best_price_for(side, "totals")
        if best_price is None or not passes_collar(best_price):
            continue
        # NFL wind kill — fires before edge check so we don't waste time
        if is_nfl:
            _nfl_killed, _nfl_reason = nfl_kill_switch(
                wind_mph=wind_mph,
                total=best_line or 0.0,
                market_type="total",
            )
            if _nfl_killed and "FORCE_UNDER" not in _nfl_reason:
                # Hard kill (wind > 20): skip entirely
                continue
        edge = cp - implied_probability(best_price)
        if edge >= MIN_EDGE:
            kelly = fractional_kelly(cp, best_price)
            # Totals: "Over" tends to be the public side (fans like scoring)
            public_on_side = (side == "Over" and best_price < -105)
            rlm_confirmed, _rlm_drift = compute_rlm(event_id, side, best_price, public_on_side)
            score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap)
            # NFL FORCE_UNDER: keep candidate but mark with kill_reason
            _totals_kill_reason = ""
            if is_nfl:
                _, _totals_kill_reason = nfl_kill_switch(
                    wind_mph=wind_mph, total=best_line or 0.0, market_type="total"
                )
            # Soccer: attach Poisson cross-validation signal
            _totals_signal = ""
            if is_soccer and best_line:
                try:
                    _h_att, _a_att, _h_def, _a_def = efficiency_gap_to_soccer_strength(efficiency_gap)
                    _pr2 = poisson_soccer(
                        home_attack=_h_att, away_attack=_a_att,
                        home_defense=_h_def, away_defense=_a_def,
                        total_line=best_line,
                        apply_home_advantage=True,
                    )
                    _p_side = _pr2.over_probability if side == "Over" else _pr2.under_probability
                    _totals_signal = f"Poisson {side}={_p_side*100:.0f}% (xG {_pr2.expected_total:.2f})"
                    # Poisson divergence kill: if Poisson strongly disagrees with market
                    # consensus direction (>20% gap), add advisory to kill_reason
                    if not _totals_kill_reason and _p_side < 0.35:
                        _totals_kill_reason = f"FLAG: Poisson disagrees ({_totals_signal})"
                except Exception:
                    pass
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
                kill_reason=_totals_kill_reason,
                signal=_totals_signal,
            ))

    # --- NHL Kill Switch ---
    # Apply after all candidates are built so kill reason is visible in UI.
    if sport == "NHL" and candidates:
        if nhl_goalie_status is not None:
            # Determine per-team backup status from goalie data
            away_data = nhl_goalie_status.get("away", {})
            home_data = nhl_goalie_status.get("home", {})
            away_backup = not away_data.get("starter_confirmed", True)
            home_backup = not home_data.get("starter_confirmed", True)
            goalie_confirmed = (
                away_data.get("starter_confirmed", False)
                or home_data.get("starter_confirmed", False)
            )

            for c in candidates:
                # Determine which team's goalie we care about for this candidate
                # If betting on a team's spread or ML, opponent's goalie is the risk
                is_away_bet = away in c.target
                backup = home_backup if is_away_bet else away_backup

                killed, reason = nhl_kill_switch(
                    backup_goalie=backup,
                    goalie_confirmed=goalie_confirmed,
                )
                if reason:
                    c.kill_reason = reason
        else:
            # No goalie data available — apply FLAG to all NHL candidates
            for c in candidates:
                killed, reason = nhl_kill_switch(
                    backup_goalie=False,
                    goalie_confirmed=False,
                )
                if reason:
                    c.kill_reason = reason

    # --- Tennis Kill Switch ---
    # Applies when sport starts with "TENNIS" and a sport key is provided.
    # Surface derived from Odds API sport key (zero external API cost).
    if sport.upper().startswith("TENNIS") and tennis_sport_key and candidates:
        from core.tennis_data import surface_from_sport_key
        surface = surface_from_sport_key(tennis_sport_key)

        for c in candidates:
            if c.kill_reason:
                continue  # don't overwrite an existing kill reason
            # Favourite is the player whose price is < -105 (< even money)
            is_favourite = c.market_implied > 0.5
            is_favourite_bet = is_favourite
            _, reason = tennis_kill_switch(
                surface=surface,
                favourite_implied_prob=c.market_implied if is_favourite else (1.0 - c.market_implied),
                is_favourite_bet=is_favourite_bet,
                market_type=c.market_type,
            )
            if reason:
                c.kill_reason = reason

    return candidates
