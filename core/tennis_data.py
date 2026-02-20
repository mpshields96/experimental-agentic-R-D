"""
core/tennis_data.py — Tennis surface lookup and player name normalization
=========================================================================
Zero external API cost. All surface data is static, derived from
tournament name inference via Odds API sport key fragments.

Strategy:
- Odds API sport keys encode tournament info: "tennis_atp_french_open",
  "tennis_atp_wimbledon", "tennis_wta_roland_garros", etc.
- Surface is determined by tournament name lookup only (free, zero quota).
- Player win rates by surface: zero external API needed.
  Surface kill switch operates on tournament name only (free, zero quota).
  Historical head-to-head and surface win-rate signals derived from static tables.

Architecture rule: NO imports from math_engine, odds_fetcher, line_logger, or scheduler.
This module is data-only; math_engine.tennis_kill_switch() is the gate that acts on it.

Surface classification:
  CLAY  — Roland Garros, French Open, Madrid, Barcelona, Monte Carlo, Rome,
           Hamburg, Lyon, Geneva, Bucharest, Casablanca, Gstaad, Bastad, etc.
  GRASS — Wimbledon, Queen's Club, Halle, 's-Hertogenbosch, Eastbourne,
           Birmingham, Nottingham, Newport
  HARD  — US Open, Australian Open, All other Masters (Miami, Indian Wells,
           Montreal/Toronto, Cincinnati, Paris, Shanghai, Beijing, Tokyo,
           Vienna, Basel, Stockholm, St. Petersburg, Doha, Dubai, Adelaide,
           Auckland, ATP Finals, Davis Cup hard, Qatar Open, Sydney, etc.)

Match surface via Odds API sport key:
  "tennis_atp_french_open"     → CLAY
  "tennis_atp_roland_garros"   → CLAY
  "tennis_atp_wimbledon"       → GRASS
  "tennis_atp_us_open"         → HARD
  "tennis_atp_australian_open" → HARD
  "tennis_atp_qatar_open"      → HARD
  ...etc.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Surface constants
# ---------------------------------------------------------------------------
SURFACE_CLAY = "clay"
SURFACE_GRASS = "grass"
SURFACE_HARD = "hard"
SURFACE_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Tournament → Surface static lookup
# Keyed on Odds API sport key substrings (match via 'in' check against lowercase key).
# Order matters: first match wins. More specific patterns go first.
# ---------------------------------------------------------------------------

# Clay court tournaments — matched via any of these substrings in sport key
_CLAY_KEYWORDS: tuple[str, ...] = (
    "french_open",
    "roland_garros",
    "madrid",
    "barcelona",
    "monte_carlo",
    "montecarlo",
    "rome",
    "italian_open",
    "hamburg",
    "lyon",
    "geneva",
    "bucharest",
    "casablanca",
    "gstaad",
    "bastad",
    "bogota",
    "umag",
    "kitzbuhel",
    "winston_salem",  # actually hard — will be overridden by hard check
    "estoril",
    "houston",       # ATP clay
    "marrakech",
    "buenos_aires",
    "cordoba",
    "rio_de_janeiro",
    "santiago",
    "munich",
    "belgrade",
    "madrid_open",
    "geneva_open",
    "french",
    "roland",
)

# Grass court tournaments
_GRASS_KEYWORDS: tuple[str, ...] = (
    "wimbledon",
    "queens_club",
    "queens",
    "halle",
    "hertogenbosch",
    "eastbourne",
    "birmingham",
    "nottingham",
    "newport",
    "grass",
)

# Hard court overrides — some substrings like "houston" could be clay;
# explicit hard-court keywords that override clay matches
_HARD_KEYWORDS: tuple[str, ...] = (
    "us_open",
    "australian_open",
    "australia",
    "indian_wells",
    "miami",
    "cincinnati",
    "montreal",
    "toronto",
    "canada_open",
    "canadian_open",
    "paris",
    "paris_masters",
    "shanghai",
    "beijing",
    "tokyo",
    "vienna",
    "basel",
    "stockholm",
    "st_petersburg",
    "doha",
    "qatar",
    "dubai",
    "adelaide",
    "auckland",
    "atpfinals",
    "atp_finals",
    "nitto",
    "winston_salem",
    "washington",
    "los_cabos",
    "metz",
    "sofia",
    "nur_sultan",
    "astana",
    "almaty",
    "dallas",
    "delray_beach",
    "acapulco",
    "rotterdam",
    "marseille",
    "memphis",
    "singapore",       # WTA Finals hard
    "wta_finals",
    "pan_pacific",
    "china_open",
    "hard",
)


def surface_from_sport_key(sport_key: str) -> str:
    """
    Derive court surface from Odds API sport key string.

    Uses keyword matching in priority order: hard > grass > clay > unknown.
    Hard-court keywords take priority because some city names (houston) are
    ambiguous but have unambiguous surface overrides in the hard list.

    Args:
        sport_key: Odds API sport key string, e.g. "tennis_atp_qatar_open".

    Returns:
        "clay", "grass", "hard", or "unknown".

    >>> surface_from_sport_key("tennis_atp_french_open")
    'clay'
    >>> surface_from_sport_key("tennis_atp_wimbledon")
    'grass'
    >>> surface_from_sport_key("tennis_atp_qatar_open")
    'hard'
    >>> surface_from_sport_key("tennis_atp_australian_open")
    'hard'
    >>> surface_from_sport_key("tennis_atp_roland_garros")
    'clay'
    >>> surface_from_sport_key("tennis_wta_miami_open")
    'hard'
    >>> surface_from_sport_key("tennis_atp_unknown_event")
    'unknown'
    """
    if not sport_key:
        return SURFACE_UNKNOWN

    lower_key = sport_key.lower()

    # Hard overrides first (some cities could match clay or grass otherwise)
    for kw in _HARD_KEYWORDS:
        if kw in lower_key:
            return SURFACE_HARD

    # Grass next
    for kw in _GRASS_KEYWORDS:
        if kw in lower_key:
            return SURFACE_GRASS

    # Clay
    for kw in _CLAY_KEYWORDS:
        if kw in lower_key:
            return SURFACE_CLAY

    return SURFACE_UNKNOWN


def is_tennis_sport_key(sport_key: str) -> bool:
    """
    Return True if the Odds API sport key is a tennis market.

    >>> is_tennis_sport_key("tennis_atp_french_open")
    True
    >>> is_tennis_sport_key("basketball_nba")
    False
    >>> is_tennis_sport_key("")
    False
    """
    return bool(sport_key) and sport_key.lower().startswith("tennis")


# ---------------------------------------------------------------------------
# Player name normalization
# Odds API returns abbreviated first names: "N. Djokovic", "S. Swiatek"
# We normalize to a canonical display name for kill_reason strings only.
# ---------------------------------------------------------------------------

def normalize_player_name(abbreviated: str) -> str:
    """
    Normalize an abbreviated player name to a consistent display form.

    The Odds API uses "N. Djokovic" format. We keep this format for display
    but strip leading/trailing whitespace and normalise internal spacing.

    Does NOT map to full first names — that requires external data (paid API).
    This function is for display consistency only.

    Args:
        abbreviated: Player name string from Odds API, e.g. "N. Djokovic".

    Returns:
        Cleaned display name or empty string if input is empty.

    >>> normalize_player_name("  N. Djokovic  ")
    'N. Djokovic'
    >>> normalize_player_name("carlos  alcaraz")
    'carlos alcaraz'
    >>> normalize_player_name("")
    ''
    """
    if not abbreviated:
        return ""
    # Collapse multiple spaces and strip
    return " ".join(abbreviated.split())


def extract_last_name(player_name: str) -> str:
    """
    Extract last name component from a player name string.

    Handles:
    - "N. Djokovic" → "Djokovic"
    - "Carlos Alcaraz" → "Alcaraz"
    - "Djokovic" → "Djokovic"
    - "de Minaur" → "Minaur" (last token — partial last names are edge cases)

    Args:
        player_name: Player name in any format.

    Returns:
        Last word of the name string, or empty string if input is empty.

    >>> extract_last_name("N. Djokovic")
    'Djokovic'
    >>> extract_last_name("Carlos Alcaraz")
    'Alcaraz'
    >>> extract_last_name("Djokovic")
    'Djokovic'
    >>> extract_last_name("")
    ''
    """
    if not player_name:
        return ""
    parts = player_name.strip().split()
    return parts[-1] if parts else ""


# ---------------------------------------------------------------------------
# Surface context helper for kill switch messaging
# ---------------------------------------------------------------------------

def surface_label(surface: str) -> str:
    """
    Return display label for a surface constant.

    >>> surface_label("clay")
    'Clay'
    >>> surface_label("grass")
    'Grass'
    >>> surface_label("hard")
    'Hard'
    >>> surface_label("unknown")
    'Unknown'
    """
    return surface.capitalize()


def is_upset_surface(surface: str) -> bool:
    """
    Return True if the surface is historically upset-prone for heavy favourites.

    Clay is the most unpredictable surface for heavy favourites in tennis.
    Grass is second most unpredictable (serves dominate, variance high early).
    Hard court is the most consistent surface.

    Used by tennis_kill_switch() to apply caution flags.

    >>> is_upset_surface("clay")
    True
    >>> is_upset_surface("grass")
    True
    >>> is_upset_surface("hard")
    False
    >>> is_upset_surface("unknown")
    False
    """
    return surface in (SURFACE_CLAY, SURFACE_GRASS)
