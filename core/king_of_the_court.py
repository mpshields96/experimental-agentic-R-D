"""
core/king_of_the_court.py — DraftKings King of the Court (KOTC) Analyzer
=========================================================================
DraftKings runs a KOTC promo every Tuesday during the NBA season:
  - Opt in, place a $5+ player prop bet at -200 odds or longer
  - The player with the most raw PRA (Points + Rebounds + Assists) across
    ALL Tuesday games wins; users who picked correctly split the prize pool

This module ranks KOTC candidates mathematically using:
  1. Projected PRA — season averages adjusted for matchup and context
  2. Matchup quality — opponent defensive rating (lower = better defense)
  3. Ceiling multiplier — players with higher game-to-game variance score higher
  4. Triple-double threat flag — players averaging 7+ AST or 10+ REB
  5. Injury and role-expansion context (caller-provided)

KOTC-specific math notes:
  - Unlike DFS, there's no ownership penalty — pick the TRUE best, not contrarian
  - Ceiling matters more than floor: pick the player with the highest upside
  - Late games (10:00+ PM ET) carry a slight advantage — no score is "locked in" yet
  - A single monster game (55+ PRA) beats multiple consistent 40-PRA performances

Architecture rule: NO imports from math_engine, odds_fetcher, line_logger, or scheduler.
Caller passes team list; this module does NOT fetch live data.

Data source:
  _PLAYER_SEASONS — static snapshot of 2025-26 NBA season averages for top
  PRA producers. Same pattern as efficiency_feed.py. Update each October.
  _TEAM_DEF_RATING — approximate defensive ratings (raw points allowed per 100
  possessions). Lower = better defense → harder matchup for scorer.
  Scale: 108 (elite) to 122 (bottom-tier).

Usage:
    from core.king_of_the_court import rank_kotc_candidates, KotcCandidate
    teams_tonight = ["LAL", "ORL", "ATL", "WAS", "PHI", "IND"]
    injury_outs = {"Jaylen Brown", "Joel Embiid"}  # confirmed DNPs
    star_outs = {"Jayson Tatum": "BOS"}  # key teammate missing → role expansion
    candidates = rank_kotc_candidates(teams_tonight, injury_outs, star_outs)
    top3 = candidates[:3]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KOTC_MIN_PRA_THRESHOLD: float = 30.0   # below this → not a KOTC candidate
KOTC_TOP_N: int = 10                    # max candidates to return
_LATE_GAME_START_HOUR: int = 22         # 10:00 PM ET — ceiling advantage


# ---------------------------------------------------------------------------
# Static player season averages table — 2025-26 NBA season
# Top 55 PRA producers. Update each October at season start.
# ---------------------------------------------------------------------------

@dataclass
class _PlayerProfile:
    name: str
    team: str           # NBA official abbreviation
    pos: str            # "G", "F", "C", "G/F", "F/C"
    pts: float          # season avg pts per game
    reb: float          # season avg reb per game
    ast: float          # season avg ast per game
    ceil_mult: float    # ceiling multiplier (1.0 = avg variance, 1.2 = boom/bust)
    min_pg: float       # minutes per game (affects floor reliability)


_PLAYER_SEASONS: list[_PlayerProfile] = [
    # Elite triple-double/PRA machines
    _PlayerProfile("Nikola Jokic",      "DEN", "C",   27.5, 12.8, 10.2, 1.25, 34.8),
    _PlayerProfile("Luka Doncic",       "LAL", "G",   30.1,  8.2,  9.1, 1.22, 38.2),
    _PlayerProfile("Giannis Antetokounmpo","MIL","F", 30.8, 11.9,  6.3, 1.18, 37.1),
    _PlayerProfile("Joel Embiid",       "PHI", "C",   32.4, 11.2,  5.3, 1.20, 33.2),
    _PlayerProfile("Jalen Johnson",     "ATL", "F",   23.4, 10.8,  8.1, 1.15, 36.8),
    _PlayerProfile("Jaylen Brown",      "BOS", "G/F", 29.2,  7.0,  4.9, 1.12, 36.5),

    # High-usage guards with playmaking
    _PlayerProfile("Shai Gilgeous-Alexander","OKC","G",32.0, 5.1,  6.5, 1.15, 34.9),
    _PlayerProfile("Tyrese Maxey",      "PHI", "G",   27.0,  3.3,  6.8, 1.18, 36.2),
    _PlayerProfile("Donovan Mitchell",  "CLE", "G",   27.3,  4.8,  5.5, 1.14, 34.6),
    _PlayerProfile("Ja Morant",         "MEM", "G",   25.1,  5.1,  8.3, 1.20, 33.8),
    _PlayerProfile("Tyrese Haliburton", "IND", "G",   22.3,  3.8, 10.4, 1.10, 34.2),
    _PlayerProfile("Trae Young",        "ATL", "G",   26.2,  3.1, 10.8, 1.18, 35.0),
    _PlayerProfile("Darius Garland",    "CLE", "G",   22.4,  2.9,  7.6, 1.08, 33.5),
    _PlayerProfile("Jalen Brunson",     "NYK", "G",   27.8,  3.4,  6.9, 1.14, 35.8),
    _PlayerProfile("Anthony Edwards",   "MIN", "G",   26.8,  5.3,  5.9, 1.16, 35.2),
    _PlayerProfile("Damian Lillard",    "MIL", "G",   24.1,  4.2,  6.8, 1.15, 34.5),
    _PlayerProfile("Kevin Porter Jr.",  "MIL", "G/F", 24.5,  7.2,  7.5, 1.18, 34.8),

    # Big men + stretch forwards
    _PlayerProfile("Bam Adebayo",       "MIA", "C",   22.4,  9.8,  4.2, 1.05, 36.0),
    _PlayerProfile("Karl-Anthony Towns","NYK", "C",   24.8, 12.9,  3.1, 1.10, 33.8),
    _PlayerProfile("Victor Wembanyama", "SAS", "F/C", 24.8,  9.8,  3.9, 1.22, 33.4),
    _PlayerProfile("Paolo Banchero",    "ORL", "F",   24.3,  7.4,  4.8, 1.14, 35.5),
    _PlayerProfile("Evan Mobley",       "CLE", "F/C", 18.1,  9.9,  3.8, 1.05, 33.2),
    _PlayerProfile("Alperen Sengun",    "HOU", "C",   20.1, 10.2,  4.1, 1.08, 32.8),
    _PlayerProfile("Nikola Vucevic",    "CHI", "C",   22.3, 11.1,  3.1, 1.06, 33.0),
    _PlayerProfile("Lauri Markkanen",   "UTA", "F",   24.2,  8.3,  2.9, 1.08, 33.5),
    _PlayerProfile("Zion Williamson",   "NOP", "F",   26.1,  6.3,  3.9, 1.16, 30.5),

    # Versatile wings / secondary stars
    _PlayerProfile("Kevin Durant",      "PHX", "F",   27.3,  6.1,  4.8, 1.10, 36.2),
    _PlayerProfile("Devin Booker",      "PHX", "G",   27.1,  4.8,  5.1, 1.12, 35.5),
    _PlayerProfile("LeBron James",      "LAL", "F",   24.1,  7.8,  8.3, 1.15, 35.0),
    _PlayerProfile("Pascal Siakam",     "IND", "F",   20.8,  7.1,  4.2, 1.05, 33.8),
    _PlayerProfile("Franz Wagner",      "ORL", "F",   22.5,  5.1,  4.1, 1.08, 34.2),
    _PlayerProfile("Scottie Barnes",    "TOR", "F",   21.3,  8.2,  4.1, 1.07, 33.5),
    _PlayerProfile("Brandon Ingram",    "NOP", "F",   23.2,  5.9,  4.5, 1.10, 33.2),
    _PlayerProfile("Cade Cunningham",   "DET", "G",   25.1,  5.1,  7.8, 1.14, 35.3),
    _PlayerProfile("De'Aaron Fox",      "SAC", "G",   25.2,  4.2,  7.3, 1.12, 35.0),
    _PlayerProfile("Jayson Tatum",      "BOS", "F",   26.4,  8.3,  5.1, 1.14, 36.0),
    _PlayerProfile("Paul George",       "PHI", "F",   22.3,  5.8,  4.2, 1.08, 33.1),
    _PlayerProfile("RJ Barrett",        "TOR", "G/F", 24.8,  5.9,  3.8, 1.08, 34.5),
    _PlayerProfile("Desmond Bane",      "MEM", "G",   21.8,  4.1,  4.9, 1.08, 33.0),
    _PlayerProfile("Steph Curry",       "GSW", "G",   26.2,  4.2,  4.8, 1.20, 33.8),
    _PlayerProfile("Andrew Wiggins",    "GSW", "F",   19.2,  5.1,  2.9, 1.04, 33.5),
    _PlayerProfile("Jarrett Allen",     "CLE", "C",   16.8, 10.1,  2.4, 1.04, 30.2),
    _PlayerProfile("Draymond Green",    "GSW", "F",   10.8,  7.2,  7.4, 1.08, 30.5),
    _PlayerProfile("Tyrese Maxey-Embiid-out", "PHI", "G", 34.0, 4.5, 9.2, 1.22, 38.5),  # virtual: Maxey when Embiid out
    _PlayerProfile("Klay Thompson",     "DAL", "G",   20.2,  3.4,  2.8, 1.10, 31.5),
    _PlayerProfile("Luka Garza",        "DAL", "C",   14.2,  7.1,  2.1, 1.02, 28.0),
    _PlayerProfile("Immanuel Quickley", "TOR", "G",   17.8,  4.3,  6.5, 1.08, 30.5),
    _PlayerProfile("Miles Bridges",     "CHA", "F",   20.5,  6.9,  3.1, 1.07, 33.5),
    _PlayerProfile("Deni Avdija",       "POR", "F",   16.8,  7.4,  4.3, 1.06, 33.2),
    _PlayerProfile("Jamal Murray",      "DEN", "G",   21.2,  4.1,  6.2, 1.12, 32.5),
    _PlayerProfile("Michael Porter Jr.","DEN", "F",   19.8,  7.2,  2.1, 1.08, 31.5),
    _PlayerProfile("Cole Anthony",      "ORL", "G",   16.5,  4.9,  5.3, 1.08, 29.2),
    _PlayerProfile("Jimmy Butler",      "MIA", "F",   21.2,  5.8,  4.9, 1.10, 33.0),
    _PlayerProfile("Kawhi Leonard",     "LAC", "F",   22.4,  6.8,  4.1, 1.10, 32.0),
]

# Build lookup dict: player name (lowercase) → profile
_PLAYER_LOOKUP: dict[str, _PlayerProfile] = {
    p.name.lower(): p for p in _PLAYER_SEASONS
}

# Build team → players lookup
_TEAM_ROSTER: dict[str, list[_PlayerProfile]] = {}
for _p in _PLAYER_SEASONS:
    _TEAM_ROSTER.setdefault(_p.team, []).append(_p)


# ---------------------------------------------------------------------------
# Opponent defensive ratings (approximate, 2025-26 season)
# Lower = better defense = harder for scorer.
# Scale roughly mirrors NBA defensive rating (points allowed per 100 possessions).
# Update each October.
# ---------------------------------------------------------------------------

_TEAM_DEF_RATING: dict[str, float] = {
    # Elite defenses (108-112)
    "OKC": 108.2,
    "CLE": 109.1,
    "BOS": 109.8,
    "MIL": 110.2,
    "NYK": 110.5,
    "MIA": 110.8,
    "IND": 111.1,
    "PHI": 111.5,
    "MIN": 111.6,
    # Average (112-115)
    "LAL": 112.0,
    "MEM": 112.4,
    "DEN": 112.8,
    "NOP": 113.1,
    "DAL": 113.2,
    "GSW": 113.5,
    "ORL": 113.8,
    "CHI": 114.0,
    "HOU": 114.2,
    "TOR": 114.5,
    "UTA": 114.6,
    "SAS": 114.8,
    "PHX": 115.0,
    "LAC": 115.1,
    "ATL": 115.3,
    "SAC": 115.4,
    # Weak defenses (115-122)
    "POR": 115.8,
    "CHA": 116.1,
    "DET": 116.3,
    "BKN": 116.8,
    "WAS": 117.2,
}

# Matchup multiplier: opponent def_rating → how much to scale PRA projection
def _matchup_multiplier(opponent_team: str) -> float:
    """
    Compute a PRA multiplier based on the opponent's defensive rating.
    Weak defense (high rating) → more scoring opportunity → higher multiplier.
    """
    rating = _TEAM_DEF_RATING.get(opponent_team, 113.5)  # default: league avg

    if rating >= 117.0:
        return 1.18   # terrible defense (e.g. WAS)
    elif rating >= 115.5:
        return 1.12   # weak defense
    elif rating >= 113.5:
        return 1.06   # below average
    elif rating >= 111.0:
        return 1.00   # average
    elif rating >= 109.0:
        return 0.95   # good defense
    else:
        return 0.90   # elite defense (OKC, CLE)


# ---------------------------------------------------------------------------
# KOTC Candidate
# ---------------------------------------------------------------------------

@dataclass
class KotcCandidate:
    player_name: str
    team: str                   # NBA team abbreviation
    position: str
    pts_avg: float
    reb_avg: float
    ast_avg: float
    pra_avg: float              # raw season average PRA
    pra_projection: float       # adjusted projected PRA (matchup + context)
    pra_ceiling: float          # high-game ceiling (85th percentile)
    pra_floor: float            # low-game floor (15th percentile)
    opponent: str               # opponent team abbreviation
    matchup_grade: str          # "GREAT" | "GOOD" | "NEUTRAL" | "TOUGH" | "ELITE"
    triple_double_threat: bool
    kotc_score: float           # 0-100 composite score
    reasoning: str
    is_out: bool = False
    role_expansion: bool = False  # teammate star is out


# ---------------------------------------------------------------------------
# Core ranking logic
# ---------------------------------------------------------------------------

def _matchup_grade(opponent: str) -> str:
    rating = _TEAM_DEF_RATING.get(opponent, 113.5)
    if rating >= 117.0:
        return "GREAT"
    elif rating >= 115.5:
        return "GOOD"
    elif rating >= 113.0:
        return "NEUTRAL"
    elif rating >= 110.0:
        return "TOUGH"
    else:
        return "ELITE"


def _compute_ceiling_floor(
    pra_avg: float,
    ceil_mult: float,
    role_expansion: bool = False,
) -> tuple[float, float]:
    """
    Estimate 85th percentile ceiling and 15th percentile floor.
    Ceiling matters most for KOTC; floor is just context.
    """
    expansion_boost = 0.12 if role_expansion else 0.0
    ceiling = round(pra_avg * (ceil_mult + expansion_boost), 1)
    floor = round(pra_avg * (2.0 - ceil_mult - expansion_boost), 1)
    return ceiling, floor


def _kotc_score(
    pra_proj: float,
    pra_ceiling: float,
    triple_double_threat: bool,
    matchup_grade: str,
    is_out: bool,
) -> float:
    """
    Compute a 0-100 KOTC score.

    Formula:
      base = (pra_projection / 55.0) × 60   (projection drives 60% of score)
      ceil = (pra_ceiling / 70.0) × 30       (ceiling drives 30% of score)
      bonus = 10 if triple-double threat      (10% bonus for TD threat)
      total = clamp(base + ceil + bonus, 0, 100)
      total = 0 if player is OUT

    Reference points:
      Jokic avg (50 PRA / 62.5 ceiling): base=54.5, ceil=26.8, TD=10 → 91.3
      Luka Doncic (47.4 / 57.8 ceil): base=51.7, ceil=24.8, TD=10 → 86.5
      Jalen Johnson (42.3 / 48.6 ceil): base=46.1, ceil=20.8, no-TD → 66.9
      Maxey w/ Embiid out (47.7 / 58.3 ceil): base=52.0, ceil=24.9, no-TD → 76.9
    """
    if is_out:
        return 0.0

    base = (pra_proj / 55.0) * 60.0
    ceil_component = (pra_ceiling / 70.0) * 30.0
    td_bonus = 10.0 if triple_double_threat else 0.0

    # Grade bonus for elite matchup
    matchup_bonus = {
        "GREAT": 3.0, "GOOD": 1.5, "NEUTRAL": 0.0, "TOUGH": -1.5, "ELITE": -3.0
    }.get(matchup_grade, 0.0)

    raw = base + ceil_component + td_bonus + matchup_bonus
    return round(max(0.0, min(100.0, raw)), 1)


def _build_reasoning(
    profile: _PlayerProfile,
    pra_proj: float,
    pra_ceiling: float,
    opponent: str,
    mgrade: str,
    role_expansion: bool,
    is_td_threat: bool,
) -> str:
    """Build a one-line reasoning string for display."""
    parts = []
    parts.append(f"Proj PRA {pra_proj:.1f} (ceil {pra_ceiling:.1f})")
    parts.append(f"vs {opponent} [{mgrade} matchup]")
    if is_td_threat:
        parts.append("triple-double threat")
    if role_expansion:
        parts.append("role-expansion boost")
    return " | ".join(parts)


def rank_kotc_candidates(
    teams_playing: list[str],
    injury_outs: Optional[set[str]] = None,
    star_outs: Optional[dict[str, str]] = None,
    opponent_map: Optional[dict[str, str]] = None,
) -> list[KotcCandidate]:
    """
    Rank KOTC candidates for a given night's NBA slate.

    Args:
        teams_playing: List of NBA team abbreviations playing tonight.
                       Each team should appear once (e.g. ["LAL", "ORL", "ATL"...]).
        injury_outs:   Set of player names confirmed OUT (e.g. {"Jaylen Brown"}).
                       Case-insensitive.
        star_outs:     Dict of {player_name: team_abbrev} for injured TEAMMATES
                       whose absence expands another player's role.
                       E.g. {"Jayson Tatum": "BOS"} boosts Jaylen Brown's projection.
        opponent_map:  Dict of {team_abbrev: opponent_abbrev} for explicit matchup routing.
                       If not provided, the function matches teams as game pairs
                       (assumes pairs: [team0, team1], [team2, team3], ...).

    Returns:
        List of KotcCandidate sorted by kotc_score descending.
        OUT players are excluded entirely.
        Minimum pra_projection threshold: KOTC_MIN_PRA_THRESHOLD (30.0).
    """
    if injury_outs is None:
        injury_outs = set()
    if star_outs is None:
        star_outs = {}

    outs_lower = {name.lower() for name in injury_outs}
    star_outs_lower = {name.lower(): team for name, team in star_outs.items()}

    # Build opponent map if not provided (pair sequential teams)
    if opponent_map is None:
        opponent_map = {}
        teams = list(teams_playing)
        for i in range(0, len(teams) - 1, 2):
            opponent_map[teams[i]] = teams[i + 1]
            opponent_map[teams[i + 1]] = teams[i]

    teams_set = set(teams_playing)
    candidates: list[KotcCandidate] = []

    for profile in _PLAYER_SEASONS:
        # Skip players whose team isn't playing tonight
        if profile.team not in teams_set:
            continue

        # Skip virtual profiles (e.g. "Tyrese Maxey-Embiid-out")
        if "-" in profile.name and profile.name.lower() not in outs_lower:
            # Only activate virtual profiles when the triggering event occurs
            continue

        is_out = profile.name.lower() in outs_lower
        if is_out:
            continue  # exclude OUT players entirely

        opponent = opponent_map.get(profile.team, "")
        mult = _matchup_multiplier(opponent)

        # Role expansion: star teammate is out
        role_expansion = any(
            team == profile.team
            for team in star_outs_lower.values()
        )
        role_boost = 1.12 if role_expansion else 1.0

        pra_avg = round(profile.pts + profile.reb + profile.ast, 1)
        pra_proj = round(pra_avg * mult * role_boost, 1)

        if pra_proj < KOTC_MIN_PRA_THRESHOLD:
            continue

        pra_ceiling, pra_floor = _compute_ceiling_floor(
            pra_avg, profile.ceil_mult, role_expansion
        )
        is_td_threat = (profile.ast >= 7.0) or (profile.reb >= 10.0)
        mgrade = _matchup_grade(opponent)

        score = _kotc_score(pra_proj, pra_ceiling, is_td_threat, mgrade, is_out)
        reasoning = _build_reasoning(
            profile, pra_proj, pra_ceiling, opponent, mgrade, role_expansion, is_td_threat
        )

        candidates.append(KotcCandidate(
            player_name=profile.name,
            team=profile.team,
            position=profile.pos,
            pts_avg=profile.pts,
            reb_avg=profile.reb,
            ast_avg=profile.ast,
            pra_avg=pra_avg,
            pra_projection=pra_proj,
            pra_ceiling=pra_ceiling,
            pra_floor=pra_floor,
            opponent=opponent,
            matchup_grade=mgrade,
            triple_double_threat=is_td_threat,
            kotc_score=score,
            reasoning=reasoning,
            is_out=is_out,
            role_expansion=role_expansion,
        ))

    # Handle virtual Maxey-Embiid-out profile
    embiid_out = "joel embiid" in outs_lower
    if embiid_out and "PHI" in teams_set:
        vp = _PLAYER_LOOKUP.get("tyrese maxey-embiid-out")
        if vp:
            opponent = opponent_map.get("PHI", "")
            mult = _matchup_multiplier(opponent)
            pra_avg = round(vp.pts + vp.reb + vp.ast, 1)
            pra_proj = round(pra_avg * mult, 1)
            pra_ceiling, pra_floor = _compute_ceiling_floor(pra_avg, vp.ceil_mult)
            is_td_threat = (vp.ast >= 7.0)
            mgrade = _matchup_grade(opponent)
            score = _kotc_score(pra_proj, pra_ceiling, is_td_threat, mgrade, False)
            reasoning = (
                f"Proj PRA {pra_proj:.1f} (ceil {pra_ceiling:.1f}) | "
                f"vs {opponent} [{mgrade} matchup] | EMBIID OUT → role-expansion"
            )
            candidates.append(KotcCandidate(
                player_name="Tyrese Maxey",
                team="PHI",
                position="G",
                pts_avg=vp.pts,
                reb_avg=vp.reb,
                ast_avg=vp.ast,
                pra_avg=pra_avg,
                pra_projection=pra_proj,
                pra_ceiling=pra_ceiling,
                pra_floor=pra_floor,
                opponent=opponent,
                matchup_grade=mgrade,
                triple_double_threat=is_td_threat,
                kotc_score=score,
                reasoning=reasoning,
                is_out=False,
                role_expansion=True,
            ))
            # Remove the standard Maxey entry (it's already lower)
            candidates = [c for c in candidates if not (
                c.player_name == "Tyrese Maxey" and c.role_expansion is False
            )]

    candidates.sort(key=lambda c: c.kotc_score, reverse=True)
    return candidates[:KOTC_TOP_N]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def get_kotc_top_pick(
    teams_playing: list[str],
    injury_outs: Optional[set[str]] = None,
    star_outs: Optional[dict[str, str]] = None,
    opponent_map: Optional[dict[str, str]] = None,
) -> Optional[KotcCandidate]:
    """Return the single top KOTC pick, or None if no candidates found."""
    ranked = rank_kotc_candidates(teams_playing, injury_outs, star_outs, opponent_map)
    return ranked[0] if ranked else None


def format_kotc_summary(candidate: KotcCandidate) -> str:
    """
    One-line summary for sidebar/card display.

    Example:
      "Luka Doncic (LAL G) | KOTC 86.5 | Proj PRA 48.1 | vs ORL [NEUTRAL]"
    """
    td_flag = " ★TD" if candidate.triple_double_threat else ""
    exp_flag = " ↑EXPAND" if candidate.role_expansion else ""
    return (
        f"{candidate.player_name} ({candidate.team} {candidate.position}){td_flag}{exp_flag}"
        f" | KOTC {candidate.kotc_score:.0f}"
        f" | Proj PRA {candidate.pra_projection:.1f}"
        f" | vs {candidate.opponent} [{candidate.matchup_grade}]"
    )


def is_kotc_eligible_day(weekday: Optional[int] = None) -> bool:
    """
    Return True if today is Tuesday (DraftKings KOTC promo day).
    weekday: 0=Monday ... 6=Sunday. None → use today's date.
    """
    if weekday is not None:
        return weekday == 1  # Tuesday
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).weekday() == 1
