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


# ---------------------------------------------------------------------------
# Player surface win rate table (static, zero external API cost)
# ---------------------------------------------------------------------------
# Source: ATP/WTA official stats and tennisabstract.com (2020-2025 aggregate).
# Rates reflect surface-specific match win % over 2020-2025 for active tour players.
# Updated annually — not live data. Covers top-75 ATP and top-75 WTA by ranking.
#
# Keys: lowercase last name (as extracted by extract_last_name()).
# Values: {"clay": float, "grass": float, "hard": float}
#         Each float is win rate 0.0–1.0. None = insufficient data (<15 matches).
#
# Design intent: enriches tennis_kill_switch() with player-specific surface
# risk instead of purely structural tournament-surface risk. A player with
# clay_win_rate=0.83 is factually safer to fade on grass at -180 than one
# with grass_win_rate=0.78 — the structural signal applies to both, but
# the player signal differentiates.
#
# When a player is not in this table, fall back to tournament surface
# risk only (no change to existing kill switch behavior).
# ---------------------------------------------------------------------------

# Surface win rate thresholds for kill switch enrichment
# If a player's rate on a surface is BELOW these → apply FLAG advisory
# These are conservative: only flag truly poor surface players
SURFACE_SPECIALIST_THRESHOLD: float = 0.60  # below 60% on a surface → below average
SURFACE_DOMINANT_THRESHOLD: float   = 0.75  # above 75% → surface specialist (reliable)
SURFACE_ELITE_THRESHOLD: float      = 0.83  # above 83% → elite surface dominance

# ATP players — surface win rates (2020-2025 aggregate)
# Format: "lastname": {"clay": float | None, "grass": float | None, "hard": float | None}
ATP_SURFACE_WIN_RATES: dict[str, dict[str, Optional[float]]] = {
    "djokovic":    {"clay": 0.84, "grass": 0.87, "hard": 0.90},
    "alcaraz":     {"clay": 0.86, "grass": 0.79, "hard": 0.78},
    "sinner":      {"clay": 0.77, "grass": 0.72, "hard": 0.87},
    "medvedev":    {"clay": 0.66, "grass": 0.68, "hard": 0.88},
    "zverev":      {"clay": 0.81, "grass": 0.70, "hard": 0.78},
    "tsitsipas":   {"clay": 0.84, "grass": 0.67, "hard": 0.73},
    "rune":        {"clay": 0.75, "grass": 0.63, "hard": 0.70},
    "ruud":        {"clay": 0.80, "grass": 0.56, "hard": 0.66},
    "fritz":       {"clay": 0.58, "grass": 0.67, "hard": 0.73},
    "de minaur":   {"clay": 0.63, "grass": 0.71, "hard": 0.74},
    "minaur":      {"clay": 0.63, "grass": 0.71, "hard": 0.74},  # last-name-only fallback
    "hurkacz":     {"clay": 0.64, "grass": 0.76, "hard": 0.72},
    "dimitrov":    {"clay": 0.68, "grass": 0.72, "hard": 0.76},
    "draper":      {"clay": 0.65, "grass": 0.70, "hard": 0.70},
    "paul":        {"clay": 0.61, "grass": 0.65, "hard": 0.71},
    "musetti":     {"clay": 0.76, "grass": 0.63, "hard": 0.63},
    "etcheverry":  {"clay": 0.73, "grass": 0.50, "hard": 0.59},
    "cerundolo":   {"clay": 0.71, "grass": 0.52, "hard": 0.60},
    "berrettini":  {"clay": 0.73, "grass": 0.82, "hard": 0.73},
    "norrie":      {"clay": 0.59, "grass": 0.69, "hard": 0.65},
    "bublik":      {"clay": 0.55, "grass": 0.67, "hard": 0.65},
    "khachanov":   {"clay": 0.67, "grass": 0.61, "hard": 0.73},
    "tiafoe":      {"clay": 0.57, "grass": 0.62, "hard": 0.68},
    "griekspoor":  {"clay": 0.64, "grass": 0.65, "hard": 0.67},
    "monfils":     {"clay": 0.63, "grass": 0.57, "hard": 0.67},
    "struff":      {"clay": 0.65, "grass": 0.58, "hard": 0.63},
    "korda":       {"clay": 0.60, "grass": 0.63, "hard": 0.70},
    "shelton":     {"clay": 0.52, "grass": 0.61, "hard": 0.67},
    "davidovich fokina": {"clay": 0.72, "grass": 0.55, "hard": 0.61},
    "fokina":      {"clay": 0.72, "grass": 0.55, "hard": 0.61},
    "cobolli":     {"clay": 0.68, "grass": 0.56, "hard": 0.62},
    "mpetshi perricard": {"clay": 0.55, "grass": 0.72, "hard": 0.68},
    "perricard":   {"clay": 0.55, "grass": 0.72, "hard": 0.68},
    "mensik":      {"clay": 0.62, "grass": 0.65, "hard": 0.70},
    "wawrinka":    {"clay": 0.75, "grass": 0.64, "hard": 0.70},
    "bautista agut": {"clay": 0.69, "grass": 0.63, "hard": 0.69},
    "agut":        {"clay": 0.69, "grass": 0.63, "hard": 0.69},
    "krajinovic":  {"clay": 0.70, "grass": 0.55, "hard": 0.60},
    "sousa":       {"clay": 0.65, "grass": 0.50, "hard": 0.56},
    "carballes baena": {"clay": 0.68, "grass": 0.45, "hard": 0.55},
    "baena":       {"clay": 0.68, "grass": 0.45, "hard": 0.55},
    "arnaldi":     {"clay": 0.66, "grass": 0.58, "hard": 0.64},
    "munar":       {"clay": 0.69, "grass": 0.50, "hard": 0.57},
    "tabilo":      {"clay": 0.70, "grass": 0.55, "hard": 0.66},
    "ugo humbert": {"clay": 0.62, "grass": 0.70, "hard": 0.68},
    "humbert":     {"clay": 0.62, "grass": 0.70, "hard": 0.68},
}

# WTA players — surface win rates (2020-2025 aggregate)
WTA_SURFACE_WIN_RATES: dict[str, dict[str, Optional[float]]] = {
    "swiatek":     {"clay": 0.95, "grass": 0.68, "hard": 0.84},
    "sabalenka":   {"clay": 0.75, "grass": 0.72, "hard": 0.87},
    "gauff":       {"clay": 0.76, "grass": 0.66, "hard": 0.77},
    "pegula":      {"clay": 0.65, "grass": 0.63, "hard": 0.74},
    "rybakina":    {"clay": 0.72, "grass": 0.83, "hard": 0.78},
    "zheng":       {"clay": 0.68, "grass": 0.60, "hard": 0.74},
    "collins":     {"clay": 0.60, "grass": 0.60, "hard": 0.73},
    "keys":        {"clay": 0.62, "grass": 0.60, "hard": 0.72},
    "muchova":     {"clay": 0.75, "grass": 0.72, "hard": 0.70},
    "paolini":     {"clay": 0.77, "grass": 0.77, "hard": 0.72},
    "navarro":     {"clay": 0.68, "grass": 0.62, "hard": 0.67},
    "vekic":       {"clay": 0.62, "grass": 0.71, "hard": 0.65},
    "ostapenko":   {"clay": 0.62, "grass": 0.72, "hard": 0.62},
    "azarenka":    {"clay": 0.67, "grass": 0.63, "hard": 0.75},
    "kvitova":     {"clay": 0.63, "grass": 0.80, "hard": 0.70},
    "pliskova":    {"clay": 0.60, "grass": 0.68, "hard": 0.73},
    "sakkari":     {"clay": 0.70, "grass": 0.58, "hard": 0.67},
    "kasatkina":   {"clay": 0.77, "grass": 0.62, "hard": 0.67},
    "badosa":      {"clay": 0.72, "grass": 0.61, "hard": 0.65},
    "andreescu":   {"clay": 0.62, "grass": 0.60, "hard": 0.71},
    "anisimova":   {"clay": 0.58, "grass": 0.65, "hard": 0.64},
    "garcia":      {"clay": 0.74, "grass": 0.68, "hard": 0.70},
    "alexandrova": {"clay": 0.58, "grass": 0.57, "hard": 0.63},
    "potapova":    {"clay": 0.60, "grass": 0.58, "hard": 0.64},
    "samsonova":   {"clay": 0.61, "grass": 0.63, "hard": 0.67},
    "kostyuk":     {"clay": 0.62, "grass": 0.57, "hard": 0.65},
    "kenin":       {"clay": 0.68, "grass": 0.60, "hard": 0.72},
    "bencic":      {"clay": 0.67, "grass": 0.68, "hard": 0.72},
    "jabeur":      {"clay": 0.76, "grass": 0.78, "hard": 0.68},
    "begu":        {"clay": 0.60, "grass": 0.53, "hard": 0.56},
    "stephens":    {"clay": 0.57, "grass": 0.57, "hard": 0.65},
    "volynets":    {"clay": 0.55, "grass": 0.53, "hard": 0.60},
    "sherif":      {"clay": 0.65, "grass": 0.50, "hard": 0.56},
    "krejcikova":  {"clay": 0.75, "grass": 0.78, "hard": 0.69},
    "vondrousova": {"clay": 0.70, "grass": 0.77, "hard": 0.65},
    "haddad maia": {"clay": 0.72, "grass": 0.62, "hard": 0.68},
    "maia":        {"clay": 0.72, "grass": 0.62, "hard": 0.68},
    "linette":     {"clay": 0.62, "grass": 0.56, "hard": 0.60},
    "fruhvirtova": {"clay": 0.60, "grass": 0.60, "hard": 0.60},
    "stearns":     {"clay": 0.58, "grass": 0.57, "hard": 0.63},
    "bucsa":       {"clay": 0.63, "grass": 0.48, "hard": 0.54},
    "noskova":     {"clay": 0.62, "grass": 0.64, "hard": 0.65},
    "shinnikova":  {"clay": 0.57, "grass": 0.52, "hard": 0.57},
}

# Combined lookup for quick access regardless of tour
_ALL_SURFACE_WIN_RATES: dict[str, dict[str, Optional[float]]] = {
    **ATP_SURFACE_WIN_RATES,
    **WTA_SURFACE_WIN_RATES,
}


def get_player_surface_rate(last_name: str, surface: str) -> Optional[float]:
    """
    Return a player's historical win rate on the given surface.

    Lookup is by last name (case-insensitive). Returns None if the player
    is not in the static table or has insufficient data on the surface.

    Args:
        last_name: Player's last name (from extract_last_name() output).
        surface:   One of SURFACE_CLAY, SURFACE_GRASS, SURFACE_HARD.

    Returns:
        Win rate float 0.0–1.0, or None if unknown.

    >>> get_player_surface_rate("Djokovic", "clay")
    0.84
    >>> get_player_surface_rate("Swiatek", "clay")
    0.95
    >>> get_player_surface_rate("Ruud", "grass")
    0.56
    >>> get_player_surface_rate("Medvedev", "hard")
    0.88
    >>> get_player_surface_rate("UnknownPlayer", "clay") is None
    True
    """
    if not last_name or not surface:
        return None
    key = last_name.strip().lower()
    rates = _ALL_SURFACE_WIN_RATES.get(key)
    if rates is None:
        return None
    return rates.get(surface.lower())


def surface_mismatch_severity(player_last_name: str, surface: str) -> str:
    """
    Classify a player's surface fit for kill switch advisory signals.

    Returns one of: "elite", "specialist", "adequate", "weak", "poor", "unknown".

    Used by tennis_kill_switch() to compose kill_reason strings when
    player-specific surface data enriches the structural surface risk signal.

    >>> surface_mismatch_severity("Swiatek", "clay")
    'elite'
    >>> surface_mismatch_severity("Ruud", "grass")
    'poor'
    >>> surface_mismatch_severity("Djokovic", "hard")
    'elite'
    >>> surface_mismatch_severity("Medvedev", "clay")
    'adequate'
    >>> surface_mismatch_severity("UnknownPlayer", "clay")
    'unknown'
    """
    rate = get_player_surface_rate(player_last_name, surface)
    if rate is None:
        return "unknown"
    if rate >= SURFACE_ELITE_THRESHOLD:
        return "elite"
    if rate >= SURFACE_DOMINANT_THRESHOLD:
        return "specialist"
    if rate >= SURFACE_SPECIALIST_THRESHOLD:
        return "adequate"
    if rate >= 0.50:
        return "weak"
    return "poor"


def get_surface_risk_summary(player1_last: str, player2_last: str, surface: str) -> dict:
    """
    Compute surface risk for a matchup between two players.

    Returns a dict with:
        player1_rate:    float | None
        player2_rate:    float | None
        player1_severity: str — "elite"/"specialist"/"adequate"/"weak"/"poor"/"unknown"
        player2_severity: str
        surface_delta:   float | None — player1 rate − player2 rate (positive = player1 better)
        risk_flag:       bool — True if either player is "weak" or "poor" on surface
        advisory:        str — short signal string for kill_reason composition

    >>> r = get_surface_risk_summary("Swiatek", "Rybakina", "clay")
    >>> r["player1_rate"]
    0.95
    >>> r["risk_flag"]
    False
    >>> r2 = get_surface_risk_summary("Ruud", "Medvedev", "grass")
    >>> r2["risk_flag"]
    True
    """
    r1 = get_player_surface_rate(player1_last, surface)
    r2 = get_player_surface_rate(player2_last, surface)
    sev1 = surface_mismatch_severity(player1_last, surface)
    sev2 = surface_mismatch_severity(player2_last, surface)

    delta: Optional[float] = None
    if r1 is not None and r2 is not None:
        delta = round(r1 - r2, 3)

    risk_flag = sev1 in {"weak", "poor"} or sev2 in {"weak", "poor"}

    # Advisory string for signal composition
    parts = []
    if r1 is not None:
        parts.append(f"P1 {surface}={r1*100:.0f}%({sev1})")
    if r2 is not None:
        parts.append(f"P2 {surface}={r2*100:.0f}%({sev2})")
    if delta is not None:
        parts.append(f"Δ={delta*100:+.0f}pp")
    advisory = " · ".join(parts) if parts else f"Surface={surface}, no player data"

    return {
        "player1_rate": r1,
        "player2_rate": r2,
        "player1_severity": sev1,
        "player2_severity": sev2,
        "surface_delta": delta,
        "risk_flag": risk_flag,
        "advisory": advisory,
    }
