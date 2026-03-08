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

MIN_EDGE: float = 0.035          # 3.5% minimum edge  → Grade A (full stake)
MIN_BOOKS: int = 2               # minimum books for consensus
KELLY_FRACTION: float = 0.25     # fractional Kelly multiplier
SHARP_THRESHOLD: float = 45.0    # minimum Sharp Score to pass (raise to 50-55 after RLM wired)
COLLAR_MIN: int = -180           # minimum allowed American odds
COLLAR_MAX: int = 150            # maximum allowed American odds
COLLAR_MAX_SOCCER: int = 400     # expanded cap for soccer 3-way h2h (dogs/draws reach +350+)
COLLAR_MIN_SOCCER: int = -250    # expanded floor for soccer heavy favourites

# ---------------------------------------------------------------------------
# Bet Grade thresholds — tiered confidence system (Session 27, 2026-02-25)
#
# Grade A  ≥ 3.5%  (MIN_EDGE)  — Full stake. Model has high confidence.
# Grade B  ≥ 1.5%              — Reduced stake. Market partially efficient.
# Grade C  ≥ 0.5%              — Tracking/data only. Positive EV but small.
# Near-Miss ≥ -1.0%            — No stake. Displayed for market transparency only.
#
# Kelly sizing by grade:
#   A: use existing fractional_kelly() result (KELLY_FRACTION = 0.25x)
#   B: kelly × KELLY_FRACTION_B / KELLY_FRACTION  → effectively 0.12x
#   C: kelly × KELLY_FRACTION_C / KELLY_FRACTION  → effectively 0.05x
#   Near-Miss: kelly shown but strike-through; do not bet
# ---------------------------------------------------------------------------
GRADE_B_MIN_EDGE: float = 0.015   # 1.5% — moderate confidence
GRADE_C_MIN_EDGE: float = 0.005   # 0.5% — data collection / tracking
NEAR_MISS_MIN_EDGE: float = -0.01  # -1.0% — near-miss transparency display
KELLY_FRACTION_B: float = 0.12    # Grade B fractional Kelly
KELLY_FRACTION_C: float = 0.05    # Grade C fractional Kelly (tracking)

# NCAAB tournament edge floor (S44).
# Conference and NCAA tournament games are neutralsite, high-juice, sharp-heavy markets.
# Below this threshold the consensus is too uncertain to bet with high confidence.
# Applied in parse_game_markets() when conference_tournament=True.
NCAAB_CONF_TOURNEY_MIN_EDGE: float = 0.08  # 8% floor during tournament window

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
    grade: str = ""         # Confidence tier: "A", "B", "C", "NEAR_MISS" — set by pipeline
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
# Bet grade assignment — tiered confidence (Session 27, 2026-02-25)
# ---------------------------------------------------------------------------

def assign_grade(bet: "BetCandidate") -> None:
    """
    Set bet.grade and scale kelly_size for sub-standard tiers. Mutates in place.

    Grade thresholds:
        A  (≥3.5%)  → Full Kelly (KELLY_FRACTION = 0.25×). Standard production bets.
        B  (≥1.5%)  → Kelly scaled to KELLY_FRACTION_B (0.12×). Reduced stake.
        C  (≥0.5%)  → Kelly scaled to KELLY_FRACTION_C (0.05×). Data / tracking only.
        NEAR_MISS   → kelly_size forced to 0.0. Display only — never stake.

    This function belongs in math_engine (not UI layer) because:
    - It operates solely on BetCandidate fields (pure math)
    - It must be testable in isolation from Streamlit

    >>> from core.math_engine import BetCandidate, assign_grade, KELLY_FRACTION
    >>> bet = BetCandidate(sport="NBA", matchup="X @ Y", market_type="h2h",
    ...     target="X ML", line=0.0, price=-110, edge_pct=0.04,
    ...     win_prob=0.55, market_implied=0.524, fair_implied=0.52, kelly_size=0.02)
    >>> assign_grade(bet)
    >>> bet.grade
    'A'
    """
    if bet.edge_pct >= MIN_EDGE:
        bet.grade = "A"
        # kelly_size already computed at KELLY_FRACTION — no change
    elif bet.edge_pct >= GRADE_B_MIN_EDGE:
        bet.grade = "B"
        if KELLY_FRACTION > 0:
            bet.kelly_size = round(bet.kelly_size * KELLY_FRACTION_B / KELLY_FRACTION, 4)
    elif bet.edge_pct >= GRADE_C_MIN_EDGE:
        bet.grade = "C"
        if KELLY_FRACTION > 0:
            bet.kelly_size = round(bet.kelly_size * KELLY_FRACTION_C / KELLY_FRACTION, 4)
    else:
        bet.grade = "NEAR_MISS"
        bet.kelly_size = 0.0  # never size a near-miss bet


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


def is_ncaab_tournament_period(month: int, day: int) -> bool:
    """
    Return True when the calendar falls in the NCAAB conference-tournament or
    NCAA Tournament window (early March through early April).

    Windows (approximate — valid for any year):
      - Conference tournaments:  Mar 4 – Mar 17
      - NCAA Tournament (March Madness): Mar 18 – Apr 7

    Used by scheduler and parse_game_markets callers to auto-set
    conference_tournament=True without hardcoding dates.

    >>> is_ncaab_tournament_period(3, 10)
    True
    >>> is_ncaab_tournament_period(3, 25)
    True
    >>> is_ncaab_tournament_period(4, 10)
    False
    >>> is_ncaab_tournament_period(2, 28)
    False
    """
    if month == 3 and 4 <= day <= 31:
        return True
    if month == 4 and day <= 7:
        return True
    return False


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
    favourite_last_name: str = "",
    underdog_last_name: str = "",
) -> tuple[bool, str]:
    """
    Tennis kill switch — zero external API cost, static surface inference only.

    Surface data is derived from tournament name (Odds API sport key).
    Surface data is free — inferred from Odds API tournament key, zero cost.

    Kill logic (structural):
    - Clay + heavy favourite (>72% implied) + h2h → FLAG: surface upsets frequent
    - Grass + heavy favourite (>75% implied) + h2h → FLAG: serve variance high
    - Unknown surface → FLAG: require 8%+ edge
    - Hard court → no flag (most predictable surface)
    - Totals are not flagged for surface (not applicable in tennis context)

    Player-specific enrichment (when name provided):
    - Looks up surface win rates from tennis_data static table (zero API cost).
    - If favourite's surface rate < SURFACE_SPECIALIST_THRESHOLD (0.60) → FLAG warning
    - If underdog has superior surface rate vs favourite → FLAG differential
    - Rate data covers top-75 ATP + top-75 WTA (2020-2025 aggregate).

    Args:
        surface:               "clay", "grass", "hard", or "unknown".
        favourite_implied_prob: Market-implied win probability for the favourite.
        is_favourite_bet:      True if this candidate bets ON the favourite.
        market_type:           "h2h", "spreads", or "totals".
        favourite_last_name:   Optional: last name for player surface rate lookup.
        underdog_last_name:    Optional: last name for opponent surface rate lookup.

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
    from core.tennis_data import (
        get_player_surface_rate,
        get_surface_risk_summary,
        SURFACE_SPECIALIST_THRESHOLD,
    )

    # Totals are not surface-sensitive in tennis (not typically offered or relevant)
    if market_type == "totals":
        return False, ""

    # Unknown surface — incomplete information, apply blanket edge requirement
    if surface == "unknown":
        return False, "FLAG: Surface unknown — require 8%+ edge"

    reasons: list[str] = []

    # Structural surface risk (tournament-level, always applied)
    pct = favourite_implied_prob * 100

    if surface == "clay" and is_favourite_bet and favourite_implied_prob > 0.72:
        reasons.append(f"Clay court + heavy favourite ({pct:.1f}%) — upsets common, require 8%+ edge")

    if surface == "grass" and is_favourite_bet and favourite_implied_prob > 0.75:
        reasons.append(f"Grass court + heavy favourite ({pct:.1f}%) — serve variance high, require 7%+ edge")

    # Player-specific surface enrichment (static table, zero cost)
    if is_favourite_bet and favourite_last_name:
        fav_rate = get_player_surface_rate(favourite_last_name, surface)
        if fav_rate is not None and fav_rate < SURFACE_SPECIALIST_THRESHOLD:
            reasons.append(
                f"{favourite_last_name} {surface} win rate={fav_rate*100:.0f}% (below avg) — "
                f"surface mismatch for favourite"
            )

    if favourite_last_name and underdog_last_name:
        risk = get_surface_risk_summary(favourite_last_name, underdog_last_name, surface)
        if risk["surface_delta"] is not None:
            delta_pp = risk["surface_delta"] * 100
            if delta_pp < -5:
                # Underdog is meaningfully better on this surface
                reasons.append(
                    f"Surface edge: underdog better on {surface} by {-delta_pp:.0f}pp "
                    f"({risk['advisory']})"
                )
        if risk["risk_flag"]:
            reasons.append(f"Player surface risk detected: {risk['advisory']}")

    if not reasons:
        return False, ""

    return False, "FLAG: " + " · ".join(reasons)


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

    PRECONDITION — Totals markets only:
        All bookmakers in `bookmakers` MUST quote the same total line.
        Callers must filter to canonical line via `_canonical_totals_books()` before passing here.
        Mixed-line input produces undefined fair probability (probability anchored to one line,
        best price potentially at another line → false edge signal).

    PRECONDITION — All markets:
        Each bookmaker dict must follow Odds API format:
        {"markets": [{"key": "spreads"|"totals"|"h2h", "outcomes": [...]}]}
        Non-standard formats silently produce empty results (no validation error raised).

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

    PRECONDITION — Direction consistency:
        `current_price` and the cached open price MUST represent the same outcome direction.
        `side` (team name, "Over", "Under") is used as the cache key — consistent naming
        across calls is required. If the side name changes between open and current
        (e.g. team alias mismatch), get_open_price() returns None → cold-cache fallback.

    COLD CACHE BEHAVIOUR (already implemented — document for future maintainers):
        When get_open_price() returns None (no historical open stored), function returns
        (False, 0.0) immediately — RLM cannot fire without an open price baseline.
        This is correct and intentional. Do NOT add a fallback that treats 0.0 as a valid
        open price — that would cause drift = current_prob - 0.0 = positive spurious RLM fire.

    POSTCONDITION:
        Signed drift > 0 means implied probability INCREASED (line got harder/more expensive).
        On public-bet side, this means sharp money is on the other side → RLM.
        Negative drift means line moved in public's favour (normal public-following move).

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
    # Signed drift: positive = implied prob increased = price got MORE EXPENSIVE for bettor.
    # RLM fires only when the line moved AGAINST the public (price worsened for public side).
    # Using abs() was a bug — it fired on ANY movement including normal public-following moves.
    drift = current_prob - open_prob

    if drift >= 0.03 and public_on_side:
        # Price moved against the public (got harder to bet) — sharp money on the other side.
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
    nba_pdo: Optional[dict] = None,
    min_edge: float = MIN_EDGE,
    injury_leverage: float = 0.0,
    conference_tournament: bool = False,
    ncaab_three_point_data: Optional[dict] = None,
) -> list[BetCandidate]:
    """
    Parse a raw game dict from odds_fetcher into BetCandidate objects.

    Edge detection: multi-book consensus (see consensus_fair_prob()).
    Applies: collar filter, min edge (min_edge param, default 3.5%), min books (2).

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
        nba_pdo: Optional dict mapping canonical team name → PdoResult from nba_pdo module.
            Format: {"Los Angeles Lakers": PdoResult(...), "Denver Nuggets": PdoResult(...)}
            Pre-fetched by scheduler/live_lines (once per hour). NOT fetched here.
            If provided and sport=="NBA", pdo_kill_switch() is evaluated per candidate.
            Totals candidates are skipped (PDO is directional, not total-relevant).
        conference_tournament: When True and sport=="NCAAB", ncaab_kill_switch() fires
            with conference_tournament=True — requires 8%+ edge (FLAG, not KILL).
            Use is_ncaab_tournament_period(month, day) to auto-detect March window.
            Defaults False (regular season behaviour).
        ncaab_three_point_data: Optional dict mapping team_name → 3PT reliance rate (float).
            If provided and sport=="NCAAB", road-3PT kill fires when rate > 40%.
            Example: {"Gonzaga Bulldogs": 0.42, "Duke Blue Devils": 0.35}
            Defaults None (3PT kill dormant — safe for missing static data).

    Returns:
        List of BetCandidates passing collar AND minimum edge.
        BetCandidates with KILL reason have kill_reason set and are included
        so the UI can display them as killed (not silently dropped).

    INVARIANTS (must hold for correct output):
        1. Totals consensus and best-price always computed from the SAME canonical-line book set.
           _canonical_totals_books() enforces this. Do not split these two calls.
        2. Both sides of a totals market (Over + Under) share one dedup bucket via
           _deduplicate_markets() using key (event_id, market_type) — line excluded intentionally.
           Do NOT re-add the line to the totals dedup key. See V37 CLAUDE.md Architecture Decisions.
        3. Kill switches fire ONLY on mathematical inputs. No narrative conditions added here.
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

    def _best_price_for(team: str, mkt: str, bks: Optional[list] = None) -> tuple[Optional[int], Optional[float], str]:
        """Find best (highest) price for a team/side across all books.

        PRECONDITION — Totals markets:
            When `mkt` is "totals", `bks` parameter MUST be restricted to canonical-line
            books only (same set passed to consensus_fair_prob). Passing `all_bks` for totals
            allows best price to be found at a non-modal line, creating consensus/price mismatch.
            Default `bks=None` (→ all_bks) is intentionally unsafe for totals — caller must scope it.

        Args:
            team: Outcome name to match (e.g. "Over", "Under", or team name).
            mkt:  Market key ("totals", "spreads", "h2h").
            bks:  Optional pre-filtered book list. Defaults to all_bks.
        """
        _source = bks if bks is not None else all_bks
        best_price = None
        best_line = None
        best_book = ""
        for book in _source:
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

    # NCAAB
    is_ncaab = sport.upper() == "NCAAB"
    _ncaab_3pt = ncaab_three_point_data or {}

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
        if edge >= min_edge:
            kelly = fractional_kelly(cp, best_price)
            public_on_side = best_price < -105
            rlm_confirmed, _rlm_drift = compute_rlm(event_id, team_name, best_price, public_on_side)
            score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap, injury_leverage=injury_leverage)
            # NBA B2B — home/road differentiated flag
            _kill_reason = ""
            if is_ncaab:
                # Neutral venue: tournament games are neither home nor away.
                # road-3PT kill only applies to true road games, not neutral site.
                _is_road_ncaab = (team_name == away) and not conference_tournament
                _3pt_rate = _ncaab_3pt.get(team_name, 0.0)
                _ncaab_killed, _ncaab_reason = ncaab_kill_switch(
                    three_point_reliance=_3pt_rate,
                    is_away=_is_road_ncaab,
                    market_type="spread",
                    conference_tournament=conference_tournament,
                )
                if _ncaab_killed:
                    _kill_reason = _ncaab_reason
                elif conference_tournament and edge < NCAAB_CONF_TOURNEY_MIN_EDGE:
                    # Enforce 8% floor: tournament markets are sharp + neutral site.
                    # The FLAG from ncaab_kill_switch alone is not enough — we must KILL.
                    _kill_reason = (
                        f"KILL: Conf tournament edge {edge:.1%} < "
                        f"{NCAAB_CONF_TOURNEY_MIN_EDGE:.0%} floor"
                    )
                elif _ncaab_reason:
                    _kill_reason = _ncaab_reason
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
            if edge >= min_edge:
                kelly = fractional_kelly(cp, best_price)
                public_on_side = best_price < -105
                rlm_confirmed, _rlm_drift = compute_rlm(event_id, outcome_name, best_price, public_on_side)
                score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap, injury_leverage=injury_leverage)
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
            if edge >= min_edge:
                kelly = fractional_kelly(cp, best_price)
                public_on_side = best_price < -105
                rlm_confirmed, _rlm_drift = compute_rlm(event_id, team_name, best_price, public_on_side)
                score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap, injury_leverage=injury_leverage)
                # NCAAB — conference tournament flag on h2h
                _h2h_kill_reason = ""
                if is_ncaab:
                    # Neutral venue: tournament games are neither home nor away.
                    _is_road_ncaab_h2h = (team_name == away) and not conference_tournament
                    _3pt_rate_h2h = _ncaab_3pt.get(team_name, 0.0)
                    _ncaab_h2h_killed, _ncaab_h2h_reason = ncaab_kill_switch(
                        three_point_reliance=_3pt_rate_h2h,
                        is_away=_is_road_ncaab_h2h,
                        market_type="h2h",
                        conference_tournament=conference_tournament,
                    )
                    if _ncaab_h2h_killed:
                        _h2h_kill_reason = _ncaab_h2h_reason
                    elif conference_tournament and edge < NCAAB_CONF_TOURNEY_MIN_EDGE:
                        _h2h_kill_reason = (
                            f"KILL: Conf tournament edge {edge:.1%} < "
                            f"{NCAAB_CONF_TOURNEY_MIN_EDGE:.0%} floor"
                        )
                    elif _ncaab_h2h_reason:
                        _h2h_kill_reason = _ncaab_h2h_reason
                # NBA B2B — h2h (spread=0 proxy)
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

    # --- Totals ---
    # Canonical line scoping: books that quote different total lines (e.g. 6.5 vs 7.0
    # on the same game) must NOT be mixed in a single consensus computation. Mixing them
    # produces impossible results — both Over 7.0 and Under 6.5 can show positive edge
    # simultaneously. Fix: find the modal (most-quoted) total line across all books,
    # restrict ALL totals work — consensus AND best-price — to that canonical set only.
    def _canonical_totals_books() -> tuple[Optional[float], list]:
        """Return (modal_total_line, books_quoting_that_line) across all_bks.

        CONTRACT:
            Input:  full bookmaker list (may contain books at mixed total lines)
            Output: (modal_line: float, filtered_books: list) where all books in filtered_books
                    quote exactly modal_line for the totals market.

            Edge cases:
            - Tiebreak when two lines have equal book count: Counter insertion order determines
              winner (non-deterministic across Python versions, deterministic within a run).
              Acceptable — affects <5% of games (requires exact tie in book distribution).
            - Single-book game: returns that book's line + [that book]. No MIN_BOOKS guard
              applies inside this function — caller must check len(filtered_books) >= MIN_BOOKS.
            - No books with totals market: returns (None, []). Caller must handle.
        """
        from collections import Counter
        line_counts: Counter = Counter()
        for book in all_bks:
            for m in book.get("markets", []):
                if m["key"] == "totals":
                    for o in m.get("outcomes", []):
                        pt = o.get("point")
                        if pt is not None:
                            line_counts[pt] += 1
                            break  # one line per book is sufficient
        if not line_counts:
            return None, []
        canonical = line_counts.most_common(1)[0][0]
        filtered = [
            b for b in all_bks
            if any(
                m["key"] == "totals"
                and any(o.get("point") == canonical for o in m.get("outcomes", []))
                for m in b.get("markets", [])
            )
        ]
        return canonical, filtered

    _canonical_line, _totals_bks = _canonical_totals_books()
    for side in ["Over", "Under"]:
        if not _totals_bks:  # no books quote a consistent canonical line
            break
        cp, std, n_books = consensus_fair_prob("", "totals", side, _totals_bks)
        if n_books < MIN_BOOKS:
            continue
        best_price, best_line, best_book_name = _best_price_for(side, "totals", bks=_totals_bks)
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
        if edge >= min_edge:
            kelly = fractional_kelly(cp, best_price)
            # Totals: "Over" tends to be the public side (fans like scoring)
            public_on_side = (side == "Over" and best_price < -105)
            rlm_confirmed, _rlm_drift = compute_rlm(event_id, side, best_price, public_on_side)
            score, breakdown = calculate_sharp_score(edge, rlm_confirmed, efficiency_gap, injury_leverage=injury_leverage)
            # NFL FORCE_UNDER: keep candidate but mark with kill_reason
            _totals_kill_reason = ""
            if is_nfl:
                _, _totals_kill_reason = nfl_kill_switch(
                    wind_mph=wind_mph, total=best_line or 0.0, market_type="total"
                )
            # NCAAB totals: enforce 8% floor during tournament; apply tempo kill if available
            if is_ncaab:
                _ncaab_total_killed, _ncaab_total_reason = ncaab_kill_switch(
                    three_point_reliance=0.0,  # 3PT not relevant for totals
                    is_away=False,             # neutral venue always
                    tempo_diff=0.0,            # tempo_diff not yet wired — safe default
                    market_type="total",
                    conference_tournament=conference_tournament,
                )
                if _ncaab_total_killed:
                    _totals_kill_reason = _ncaab_total_reason
                elif conference_tournament and edge < NCAAB_CONF_TOURNEY_MIN_EDGE:
                    _totals_kill_reason = (
                        f"KILL: Conf tournament edge {edge:.1%} < "
                        f"{NCAAB_CONF_TOURNEY_MIN_EDGE:.0%} floor"
                    )
                elif _ncaab_total_reason:
                    _totals_kill_reason = _ncaab_total_reason
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
    # Player names extracted from game home/away for static surface rate lookup.
    if sport.upper().startswith("TENNIS") and tennis_sport_key and candidates:
        from core.tennis_data import extract_last_name, surface_from_sport_key
        surface = surface_from_sport_key(tennis_sport_key)

        # Extract last names for player-specific surface enrichment
        home_last = extract_last_name(home)
        away_last = extract_last_name(away)

        for c in candidates:
            if c.kill_reason:
                continue  # don't overwrite an existing kill reason
            # Favourite is the player whose price is < -105 (< even money)
            is_favourite = c.market_implied > 0.5
            is_favourite_bet = is_favourite

            # Determine which player is the favourite for name routing
            # target usually == home or away player name for h2h
            target_last = extract_last_name(c.target.split()[0] if c.target else "")
            if home_last and away_last:
                fav_last = home_last if is_favourite else away_last
                dog_last = away_last if is_favourite else home_last
            else:
                fav_last = target_last
                dog_last = ""

            _, reason = tennis_kill_switch(
                surface=surface,
                favourite_implied_prob=c.market_implied if is_favourite else (1.0 - c.market_implied),
                is_favourite_bet=is_favourite_bet,
                market_type=c.market_type,
                favourite_last_name=fav_last,
                underdog_last_name=dog_last,
            )
            if reason:
                c.kill_reason = reason

    # --- NBA PDO Kill Switch ---
    # Evaluates luck-regression signal for NBA spreads and h2h.
    # PDO pre-fetched by scheduler/live_lines — NOT fetched here.
    # Totals are skipped (PDO is directional; total-direction is ambiguous).
    if sport == "NBA" and nba_pdo and candidates:
        from core.nba_pdo import _pdo_cache as _pdo_module_cache
        # Seed module cache from the passed dict so pdo_kill_switch() can find the data.
        # This does not overwrite entries that are fresher (fetched_at comparison).
        for _name, _result in nba_pdo.items():
            if _name not in _pdo_module_cache or _result.fetched_at >= _pdo_module_cache[_name].fetched_at:
                _pdo_module_cache[_name] = _result
        from core.nba_pdo import pdo_kill_switch
        for c in candidates:
            if c.kill_reason:
                continue  # don't overwrite an existing kill reason
            if c.market_type == "totals":
                continue
            # Determine which team this candidate is betting ON
            is_home_bet = home and c.target.startswith(home)
            team_name = home if is_home_bet else away
            if team_name not in nba_pdo:
                continue
            pdo_result = nba_pdo[team_name]
            _killed, reason = pdo_kill_switch(
                team_name=pdo_result.team_name,
                bet_direction="with",
                market_type=c.market_type,
            )
            if reason:
                c.kill_reason = reason

    return candidates


# ---------------------------------------------------------------------------
# Player props — PropCandidate + parse_props_candidates() (Session 35)
#
# Math model (V37 spec): same consensus approach as game lines.
#   - no_vig_probability() per book for each player + market + line
#   - Modal line pinning: only books quoting the same line contribute to consensus
#     (same principle as _canonical_totals_books in parse_game_markets)
#   - Edge = consensus_prob - implied(best_price)
#   - Collar: COLLAR_MIN/COLLAR_MAX — props are binary O/U (not 3-way)
#   - Grade: same thresholds as BetCandidate (A/B/C/NEAR_MISS)
#
# Props raw data format (Odds API event endpoint):
#   event["bookmakers"][i]["markets"][j]["outcomes"] = list of:
#   {"name": "Over"|"Under", "description": "Player Name", "price": int, "point": float}
#   All players share the same market list entry — must group by (description, point).
# ---------------------------------------------------------------------------


@dataclass
class PropCandidate:
    """A single player prop candidate with edge and grade signal.

    Produced by parse_props_candidates() from raw Odds API event props data.
    """

    player: str           # "LeBron James"
    market_key: str       # "player_points"
    market_label: str     # "PTS" (display label)
    line: float           # 24.5
    direction: str        # "Over" or "Under"
    price: int            # Best available american odds
    best_book: str        # Book key with best price
    win_prob: float       # Consensus fair probability
    market_implied: float # Implied probability of best_price (vig-inclusive)
    edge_pct: float       # win_prob - market_implied
    n_books: int          # Number of books in consensus
    grade: str = ""       # A / B / C / NEAR_MISS / BELOW_MIN


_PROP_MARKET_LABELS: dict[str, str] = {
    "player_points": "PTS",
    "player_rebounds": "REB",
    "player_assists": "AST",
    "player_threes": "3PM",
    "player_blocks": "BLK",
    "player_steals": "STL",
    "player_points_rebounds_assists": "PRA",
    "player_points_rebounds": "P+R",
    "player_points_assists": "P+A",
    "player_pass_tds": "PASS TD",
    "player_pass_yds": "PASS YD",
    "player_rush_yds": "RUSH YD",
    "player_receptions": "REC",
    "player_reception_yds": "REC YD",
}


def _prop_grade(edge_pct: float) -> str:
    """Assign grade tier to a player prop candidate.

    Uses same thresholds as assign_grade() for BetCandidate.
    """
    if edge_pct >= MIN_EDGE:
        return "A"
    elif edge_pct >= GRADE_B_MIN_EDGE:
        return "B"
    elif edge_pct >= GRADE_C_MIN_EDGE:
        return "C"
    elif edge_pct >= NEAR_MISS_MIN_EDGE:
        return "NEAR_MISS"
    else:
        return "BELOW_MIN"


def parse_props_candidates(
    event_data: dict,
    min_edge: float = NEAR_MISS_MIN_EDGE,
    min_books: int = MIN_BOOKS,
) -> list[PropCandidate]:
    """Parse raw Odds API event props response into PropCandidate list with edge signal.

    PRECONDITION: event_data must be the dict returned by fetch_props_for_event() —
                  the event-level Odds API response with bookmakers → markets → outcomes.
    PRECONDITION: min_books ≥ 2 (single-book consensus is not meaningful).
    POSTCONDITION: Returns only candidates where edge_pct ≥ min_edge AND n_books ≥ min_books.
                   Candidates are sorted by edge_pct descending.

    Line pinning (canonical line rule):
        When different books quote different lines for the same player+market
        (e.g. DK: LeBron PTS 24.5, FD: LeBron PTS 25.5), only books quoting
        the MODAL (most common) line are included in consensus. This prevents
        cross-line false edge — same principle as _canonical_totals_books().

    Collar:
        Both Over and Under prices must pass passes_collar() (COLLAR_MIN/COLLAR_MAX).
        Props are binary O/U markets — standard collar applies. No soccer expansion.

    Args:
        event_data: Raw event dict from fetch_props_for_event(). {} produces [].
        min_edge:   Minimum edge threshold. Default NEAR_MISS_MIN_EDGE (-1%) to
                    return all grade tiers for display.
        min_books:  Minimum consensus book count. Default MIN_BOOKS (2).

    Returns:
        List of PropCandidate sorted by edge_pct descending.
        Empty list if event_data is empty or no candidates meet thresholds.
    """
    if not event_data:
        return []

    # Step 1: Collect (player, market_key, point, over_price, under_price, book_key)
    # per book. Props outcomes mix all players in one market — must group by description.
    #
    # Structure: raw_pairs[(player, market_key, point)] = [(over_price, under_price, book_key)]
    from collections import defaultdict, Counter

    raw_pairs: dict[tuple, list[tuple]] = defaultdict(list)

    for bk in event_data.get("bookmakers", []):
        book_key = bk.get("key", "?")
        for mkt in bk.get("markets", []):
            mkt_key = mkt.get("key", "")
            if not mkt_key.startswith("player_"):
                continue

            # Group outcomes by (description, point) within this book+market
            outcome_map: dict[tuple, dict[str, int]] = defaultdict(dict)
            for outcome in mkt.get("outcomes", []):
                player_name = outcome.get("description", "").strip()
                direction = outcome.get("name", "")  # "Over" or "Under"
                price = outcome.get("price")
                point = outcome.get("point")
                if player_name and direction in ("Over", "Under") and price is not None and point is not None:
                    outcome_map[(player_name, point)][direction] = price

            # Only include pairs where BOTH Over and Under are present at same line
            for (player_name, point), sides in outcome_map.items():
                if "Over" in sides and "Under" in sides:
                    raw_pairs[(player_name, mkt_key, point)].append(
                        (sides["Over"], sides["Under"], book_key)
                    )

    # Step 2: For each (player, market_key), find the modal line (canonical line pinning)
    # Group all (point, data) by (player, market_key)
    player_market_lines: dict[tuple, dict[float, list]] = defaultdict(lambda: defaultdict(list))
    for (player, mkt_key, point), entries in raw_pairs.items():
        player_market_lines[(player, mkt_key)][point].extend(entries)

    candidates: list[PropCandidate] = []

    # Step 3: For each (player, market_key), pin to modal line, compute consensus + edge
    for (player, mkt_key), line_groups in player_market_lines.items():
        # Find modal line (most books quote this line)
        book_counts = {pt: len(entries) for pt, entries in line_groups.items()}
        canonical_line = max(book_counts, key=book_counts.get)
        entries_at_line = line_groups[canonical_line]  # [(over_price, under_price, book_key)]

        if len(entries_at_line) < min_books:
            continue

        # Step 4: Compute vig-free consensus probability using no_vig_probability()
        over_fair_probs: list[float] = []
        for (over_price, under_price, _) in entries_at_line:
            if not (passes_collar(over_price) and passes_collar(under_price)):
                continue
            try:
                over_fp, _ = no_vig_probability(over_price, under_price)
                over_fair_probs.append(over_fp)
            except (ZeroDivisionError, ValueError):
                continue

        if len(over_fair_probs) < min_books:
            continue

        consensus_over = sum(over_fair_probs) / len(over_fair_probs)
        consensus_under = 1.0 - consensus_over

        # Step 5: Find best available price for each direction at canonical line
        best_over_price = max(
            (ep[0] for ep in entries_at_line if passes_collar(ep[0])),
            default=None,
        )
        best_under_price = max(
            (ep[1] for ep in entries_at_line if passes_collar(ep[1])),
            default=None,
        )
        best_over_book = next(
            (ep[2] for ep in entries_at_line if ep[0] == best_over_price),
            "?",
        ) if best_over_price is not None else "?"
        best_under_book = next(
            (ep[2] for ep in entries_at_line if ep[1] == best_under_price),
            "?",
        ) if best_under_price is not None else "?"

        mkt_label = _PROP_MARKET_LABELS.get(mkt_key, mkt_key.replace("player_", "").upper())
        n = len(over_fair_probs)

        # Step 6: Compute edge for each direction and build PropCandidates
        for direction, consensus_prob, best_price, best_book in (
            ("Over", consensus_over, best_over_price, best_over_book),
            ("Under", consensus_under, best_under_price, best_under_book),
        ):
            if best_price is None:
                continue
            market_implied = implied_probability(best_price)
            edge = consensus_prob - market_implied

            if edge < min_edge:
                continue

            grade = _prop_grade(edge)
            candidates.append(PropCandidate(
                player=player,
                market_key=mkt_key,
                market_label=mkt_label,
                line=canonical_line,
                direction=direction,
                price=best_price,
                best_book=best_book,
                win_prob=round(consensus_prob, 4),
                market_implied=round(market_implied, 4),
                edge_pct=round(edge, 4),
                n_books=n,
                grade=grade,
            ))

    candidates.sort(key=lambda c: -c.edge_pct)
    return candidates
