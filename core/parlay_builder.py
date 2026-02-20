"""
core/parlay_builder.py — Positive-EV Parlay Combo Builder
==========================================================
Finds all 2-leg parlays with positive expected value across independent games.

V36 parlay_builder.py port with improvements:
- V36: fixed 2-leg only, no Kelly sizing, no independence verification
- Sandbox improvements:
  * Independence gate: same event_id → rejected (no correlated legs)
  * Same-game parlay detection: same matchup string → rejected
  * Kelly sizing for parlay: kelly_fraction * parlay_win_prob / parlay_payout
  * Correlation discount: legs in same sport → apply 5% EV haircut
  * Parlay score: composite of EV, individual Sharp Scores, and leg count
  * Max legs: 2 (validated; 3+ parlay math degrades rapidly with model uncertainty)

Math:
  parlay_prob = prod(win_prob_i)   # assumes independence
  parlay_payout = prod((price_to_decimal(price_i)))  # decimal odds product
  parlay_ev = parlay_prob * parlay_payout - 1.0     # per unit wagered

Parlay Kelly:
  f* = (parlay_prob * parlay_payout - 1) / (parlay_payout - 1)
  Capped at 0.5 units (parlay risk is compounded; never size aggressively).

Architecture rule: NO imports from odds_fetcher, scheduler, or line_logger.
Import BetCandidate from math_engine only.

DO NOT use for correlated events (e.g., two sides of same game).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PARLAY_KELLY_FRACTION: float = 0.10   # conservative: 10% Kelly for parlays
PARLAY_MAX_UNITS: float       = 0.50  # hard cap: never more than 0.5 units on a parlay
PARLAY_MIN_EV: float          = 0.02  # minimum EV to surface a combo (2% per unit)
PARLAY_CORRELATION_DISCOUNT: float = 0.05  # EV haircut when both legs in same sport

# Minimum individual leg quality for parlay inclusion
PARLAY_MIN_SHARP_SCORE: float = 40.0  # both legs must clear this threshold
PARLAY_MIN_EDGE: float        = 0.04  # both legs must have 4%+ edge

# American odds conversion bounds
_MAX_AMERICAN_ODDS: int = 10_000   # prevents extreme parlay payouts


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ParlayCombo:
    """
    A 2-leg parlay with pre-computed EV and Kelly sizing.

    leg_1, leg_2: BetCandidate objects (legs of the parlay).
    parlay_prob:   Joint win probability (product of individual probs).
    parlay_payout: Decimal odds payout (product of decimal odds per leg).
    parlay_ev:     Expected value per unit: prob * payout - 1.0.
    kelly_size:    Recommended bet size in units (capped at PARLAY_MAX_UNITS).
    parlay_score:  Composite quality score (higher = stronger parlay).
    correlation_discounted: True if EV was reduced for same-sport legs.
    notes: Human-readable signal notes.
    """
    leg_1: object  # BetCandidate (avoid circular import with type annotation)
    leg_2: object
    parlay_prob: float
    parlay_payout: float
    parlay_ev: float
    kelly_size: float
    parlay_score: float
    correlation_discounted: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def american_to_decimal(american: int) -> float:
    """
    Convert American odds to decimal odds.

    Decimal odds = payout per unit (includes stake return).

    >>> american_to_decimal(-110)  # doctest: +ELLIPSIS
    1.909...
    >>> american_to_decimal(150)
    2.5
    >>> american_to_decimal(-200)
    1.5
    >>> american_to_decimal(100)
    2.0
    """
    if american >= 100:
        return 1.0 + american / 100.0
    else:
        return 1.0 + 100.0 / abs(american)


def parlay_ev(win_prob_1: float, win_prob_2: float, price_1: int, price_2: int) -> tuple[float, float, float]:
    """
    Compute 2-leg parlay expected value, joint probability, and payout.

    Args:
        win_prob_1: Model win probability for leg 1 (0.0–1.0).
        win_prob_2: Model win probability for leg 2 (0.0–1.0).
        price_1:    American odds for leg 1.
        price_2:    American odds for leg 2.

    Returns:
        (joint_prob, parlay_payout, ev) where:
            joint_prob     = win_prob_1 × win_prob_2
            parlay_payout  = decimal_1 × decimal_2
            ev             = joint_prob × parlay_payout − 1.0

    >>> ev = parlay_ev(0.55, 0.55, -110, -110)
    >>> abs(ev[0] - 0.3025) < 0.001  # joint prob
    True
    >>> ev[2] > 0  # should be positive EV with 55% win rate on -110
    True
    >>> parlay_ev(0.50, 0.50, -110, -110)[2] < 0  # 50% on -110 = negative EV
    True
    """
    dec_1 = american_to_decimal(price_1)
    dec_2 = american_to_decimal(price_2)
    joint_prob = win_prob_1 * win_prob_2
    payout = dec_1 * dec_2
    ev = joint_prob * payout - 1.0
    return joint_prob, payout, ev


def parlay_kelly(joint_prob: float, parlay_payout: float) -> float:
    """
    Fractional Kelly bet size for a parlay.

    f* = kelly_fraction * (prob * payout - 1) / (payout - 1)
    Capped at PARLAY_MAX_UNITS.

    >>> parlay_kelly(0.30, 3.50) > 0
    True
    >>> parlay_kelly(0.10, 3.50)  # low prob → low Kelly
    0.0
    """
    if parlay_payout <= 1.0 or joint_prob <= 0:
        return 0.0
    raw_kelly = PARLAY_KELLY_FRACTION * (joint_prob * parlay_payout - 1.0) / (parlay_payout - 1.0)
    return min(PARLAY_MAX_UNITS, max(0.0, raw_kelly))


def _legs_independent(leg_1, leg_2) -> bool:
    """
    Return True if the two legs are from independent events.

    Rejects:
    - Same event_id (same game, different markets — perfectly correlated)
    - Same matchup string (belt-and-suspenders for event_id dupes)
    - Any leg with a KILL reason (already filtered upstream, defensive check)

    >>> class FakeBet:
    ...     def __init__(self, eid, matchup, kill_reason=""):
    ...         self.event_id = eid; self.matchup = matchup; self.kill_reason = kill_reason
    >>> _legs_independent(FakeBet("a", "X @ Y"), FakeBet("b", "A @ B"))
    True
    >>> _legs_independent(FakeBet("a", "X @ Y"), FakeBet("a", "X @ Y"))
    False
    >>> _legs_independent(FakeBet("a", "X @ Y"), FakeBet("b", "X @ Y"))
    False
    """
    if leg_1.event_id and leg_2.event_id and leg_1.event_id == leg_2.event_id:
        return False
    if leg_1.matchup and leg_2.matchup and leg_1.matchup.strip() == leg_2.matchup.strip():
        return False
    if leg_1.kill_reason.startswith("KILL") or leg_2.kill_reason.startswith("KILL"):
        return False
    return True


def _parlay_score(joint_prob: float, ev: float, s1: float, s2: float) -> float:
    """
    Composite parlay quality score.

    Weights:
    - 40%: EV (normalized to 0-100 range, capping at 20% EV = 100)
    - 30%: joint_prob (0-100 range)
    - 30%: average of individual Sharp Scores (0-100)

    Higher = stronger parlay recommendation.

    >>> _parlay_score(0.30, 0.05, 60.0, 55.0) > 0
    True
    """
    ev_component = min(100.0, ev * 500.0)       # 20% EV → 100 pts
    prob_component = joint_prob * 100.0
    score_component = (s1 + s2) / 2.0
    return 0.40 * ev_component + 0.30 * prob_component + 0.30 * score_component


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def build_parlay_combos(
    bets: list,
    min_ev: float = PARLAY_MIN_EV,
    min_sharp_score: float = PARLAY_MIN_SHARP_SCORE,
    min_edge: float = PARLAY_MIN_EDGE,
    max_results: int = 10,
) -> list[ParlayCombo]:
    """
    Find all 2-leg parlays with positive expected value from a list of BetCandidates.

    Filters applied before combo evaluation:
    1. Legs must have sharp_score >= min_sharp_score
    2. Legs must have edge_pct >= min_edge
    3. Legs must not have KILL kill_reason
    4. Legs must have valid price (not 0)

    Combo filters:
    1. Legs must be from independent events (different event_id AND matchup)
    2. Parlay EV must exceed min_ev

    Parlay EV is discounted by PARLAY_CORRELATION_DISCOUNT when both legs
    are in the same sport (not perfectly correlated but structurally related
    through shared market forces).

    Args:
        bets:            List of BetCandidate objects from parse_game_markets().
        min_ev:          Minimum parlay EV per unit (default: 0.02 = 2%).
        min_sharp_score: Minimum Sharp Score for each leg (default: 40.0).
        min_edge:        Minimum edge_pct for each leg (default: 0.04).
        max_results:     Maximum combos to return, sorted by parlay_score desc.

    Returns:
        List of ParlayCombo sorted by parlay_score descending (best first).
        Empty list if no qualifying combos found.

    >>> build_parlay_combos([]) == []
    True
    """
    if not bets or len(bets) < 2:
        return []

    # Pre-filter: only quality legs enter the combo search
    qualified: list = [
        b for b in bets
        if (b.sharp_score >= min_sharp_score
            and b.edge_pct >= min_edge
            and b.price != 0
            and not b.kill_reason.startswith("KILL")
            and abs(b.price) <= _MAX_AMERICAN_ODDS)
    ]

    if len(qualified) < 2:
        return []

    combos: list[ParlayCombo] = []

    for leg_1, leg_2 in itertools.combinations(qualified, 2):
        # Independence gate
        if not _legs_independent(leg_1, leg_2):
            continue

        joint_prob, payout, ev = parlay_ev(
            leg_1.fair_implied, leg_2.fair_implied,
            leg_1.price, leg_2.price,
        )

        # Correlation discount for same-sport legs
        discounted = False
        if leg_1.sport.upper() == leg_2.sport.upper():
            ev *= (1.0 - PARLAY_CORRELATION_DISCOUNT)
            discounted = True

        if ev < min_ev:
            continue

        kelly = parlay_kelly(joint_prob, payout)
        score = _parlay_score(joint_prob, ev, leg_1.sharp_score, leg_2.sharp_score)

        notes_parts = []
        if discounted:
            notes_parts.append(f"same-sport ({leg_1.sport.upper()}) EV discount applied")
        notes_parts.append(f"Leg1: {leg_1.target} @ {leg_1.price:+d}")
        notes_parts.append(f"Leg2: {leg_2.target} @ {leg_2.price:+d}")

        combos.append(ParlayCombo(
            leg_1=leg_1,
            leg_2=leg_2,
            parlay_prob=round(joint_prob, 4),
            parlay_payout=round(payout, 3),
            parlay_ev=round(ev, 4),
            kelly_size=round(kelly, 3),
            parlay_score=round(score, 2),
            correlation_discounted=discounted,
            notes=" · ".join(notes_parts),
        ))

    # Sort by composite score descending
    combos.sort(key=lambda c: c.parlay_score, reverse=True)
    return combos[:max_results]


def format_parlay_summary(combo: ParlayCombo) -> str:
    """
    Return a concise one-line summary string for a ParlayCombo.

    Suitable for signal injection or UI display.

    >>> class FakeBet:
    ...     target = "A -4.5"; price = -110; sport = "NBA"; matchup = "X @ Y"
    ...     sharp_score = 60.0; edge_pct = 0.07; event_id = "ev1"
    ...     kill_reason = ""; fair_implied = 0.56
    >>> class FakeBet2:
    ...     target = "B +3.5"; price = 130; sport = "NFL"; matchup = "A @ B"
    ...     sharp_score = 55.0; edge_pct = 0.06; event_id = "ev2"
    ...     kill_reason = ""; fair_implied = 0.52
    >>> from core.parlay_builder import ParlayCombo
    >>> c = ParlayCombo(FakeBet(), FakeBet2(), 0.291, 3.45, 0.050, 0.25, 42.0)
    >>> s = format_parlay_summary(c)
    >>> "EV" in s and "%" in s
    True
    """
    sport_1 = combo.leg_1.sport.upper()
    sport_2 = combo.leg_2.sport.upper()
    legs = f"{combo.leg_1.target} + {combo.leg_2.target}"
    pct = f"EV={combo.parlay_ev * 100:.1f}%"
    prob = f"P={combo.parlay_prob * 100:.1f}%"
    size = f"{combo.kelly_size:.2f}u"
    sports = f"{sport_1}/{sport_2}" if sport_1 != sport_2 else sport_1
    return f"[PARLAY-{sports}] {legs} | {pct} | {prob} | {size}"
