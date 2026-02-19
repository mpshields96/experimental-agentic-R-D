"""
tests/test_tennis_data.py — Titanium-Agentic
=============================================
Unit tests for core/tennis_data.py.

Coverage:
  - surface_from_sport_key(): clay/grass/hard/unknown detection, priority order
  - is_tennis_sport_key(): detection of tennis markets
  - normalize_player_name(): whitespace, multi-space
  - extract_last_name(): all name formats
  - surface_label(): display labels
  - is_upset_surface(): clay/grass vs hard
  - Architecture: no imports from other core modules
"""

import pytest
from core.tennis_data import (
    SURFACE_CLAY,
    SURFACE_GRASS,
    SURFACE_HARD,
    SURFACE_UNKNOWN,
    extract_last_name,
    is_tennis_sport_key,
    is_upset_surface,
    normalize_player_name,
    surface_from_sport_key,
    surface_label,
)


# ---------------------------------------------------------------------------
# surface_from_sport_key
# ---------------------------------------------------------------------------

class TestSurfaceFromSportKey:

    # --- Clay ---
    def test_french_open_is_clay(self):
        assert surface_from_sport_key("tennis_atp_french_open") == SURFACE_CLAY

    def test_roland_garros_is_clay(self):
        assert surface_from_sport_key("tennis_wta_roland_garros") == SURFACE_CLAY

    def test_madrid_open_is_clay(self):
        assert surface_from_sport_key("tennis_atp_madrid_open") == SURFACE_CLAY

    def test_barcelona_is_clay(self):
        assert surface_from_sport_key("tennis_atp_barcelona") == SURFACE_CLAY

    def test_monte_carlo_is_clay(self):
        assert surface_from_sport_key("tennis_atp_monte_carlo") == SURFACE_CLAY

    def test_rome_is_clay(self):
        assert surface_from_sport_key("tennis_atp_rome") == SURFACE_CLAY

    def test_hamburg_is_clay(self):
        assert surface_from_sport_key("tennis_atp_hamburg") == SURFACE_CLAY

    # --- Grass ---
    def test_wimbledon_is_grass(self):
        assert surface_from_sport_key("tennis_atp_wimbledon") == SURFACE_GRASS

    def test_queens_club_is_grass(self):
        assert surface_from_sport_key("tennis_atp_queens_club") == SURFACE_GRASS

    def test_halle_is_grass(self):
        assert surface_from_sport_key("tennis_atp_halle") == SURFACE_GRASS

    def test_hertogenbosch_is_grass(self):
        assert surface_from_sport_key("tennis_atp_hertogenbosch") == SURFACE_GRASS

    def test_eastbourne_is_grass(self):
        assert surface_from_sport_key("tennis_wta_eastbourne") == SURFACE_GRASS

    def test_nottingham_is_grass(self):
        assert surface_from_sport_key("tennis_wta_nottingham") == SURFACE_GRASS

    # --- Hard ---
    def test_us_open_is_hard(self):
        assert surface_from_sport_key("tennis_atp_us_open") == SURFACE_HARD

    def test_australian_open_is_hard(self):
        assert surface_from_sport_key("tennis_atp_australian_open") == SURFACE_HARD

    def test_qatar_open_is_hard(self):
        assert surface_from_sport_key("tennis_atp_qatar_open") == SURFACE_HARD

    def test_indian_wells_is_hard(self):
        assert surface_from_sport_key("tennis_atp_indian_wells") == SURFACE_HARD

    def test_miami_open_is_hard(self):
        assert surface_from_sport_key("tennis_wta_miami_open") == SURFACE_HARD

    def test_cincinnati_is_hard(self):
        assert surface_from_sport_key("tennis_atp_cincinnati") == SURFACE_HARD

    def test_paris_masters_is_hard(self):
        assert surface_from_sport_key("tennis_atp_paris_masters") == SURFACE_HARD

    def test_dubai_is_hard(self):
        assert surface_from_sport_key("tennis_atp_dubai") == SURFACE_HARD

    def test_atp_finals_is_hard(self):
        assert surface_from_sport_key("tennis_atp_finals") == SURFACE_HARD

    # Hard overrides clay keywords (e.g. "paris" is hard despite being in France)
    def test_paris_beats_clay_keywords(self):
        result = surface_from_sport_key("tennis_atp_paris")
        assert result == SURFACE_HARD

    # --- Unknown ---
    def test_empty_key_is_unknown(self):
        assert surface_from_sport_key("") == SURFACE_UNKNOWN

    def test_unrecognized_tournament_is_unknown(self):
        assert surface_from_sport_key("tennis_atp_unrecognized_invitational") == SURFACE_UNKNOWN

    def test_non_tennis_key_likely_unknown(self):
        # basketball_nba has no surface keywords
        result = surface_from_sport_key("basketball_nba")
        assert result == SURFACE_UNKNOWN

    # Case-insensitive
    def test_case_insensitive_clay(self):
        assert surface_from_sport_key("TENNIS_ATP_FRENCH_OPEN") == SURFACE_CLAY

    def test_case_insensitive_grass(self):
        assert surface_from_sport_key("Tennis_ATP_Wimbledon") == SURFACE_GRASS

    def test_case_insensitive_hard(self):
        assert surface_from_sport_key("TENNIS_ATP_QATAR_OPEN") == SURFACE_HARD

    # Returns correct constants
    def test_returns_string_constants(self):
        assert isinstance(surface_from_sport_key("tennis_atp_french_open"), str)
        assert isinstance(surface_from_sport_key("tennis_atp_wimbledon"), str)
        assert isinstance(surface_from_sport_key("tennis_atp_us_open"), str)


# ---------------------------------------------------------------------------
# is_tennis_sport_key
# ---------------------------------------------------------------------------

class TestIsTennisSportKey:

    def test_atp_key_is_tennis(self):
        assert is_tennis_sport_key("tennis_atp_french_open") is True

    def test_wta_key_is_tennis(self):
        assert is_tennis_sport_key("tennis_wta_wimbledon") is True

    def test_nba_is_not_tennis(self):
        assert is_tennis_sport_key("basketball_nba") is False

    def test_empty_is_not_tennis(self):
        assert is_tennis_sport_key("") is False

    def test_nfl_is_not_tennis(self):
        assert is_tennis_sport_key("americanfootball_nfl") is False

    def test_soccer_is_not_tennis(self):
        assert is_tennis_sport_key("soccer_epl") is False

    def test_case_insensitive(self):
        assert is_tennis_sport_key("TENNIS_ATP_WIMBLEDON") is True


# ---------------------------------------------------------------------------
# normalize_player_name
# ---------------------------------------------------------------------------

class TestNormalizePlayerName:

    def test_strips_whitespace(self):
        assert normalize_player_name("  N. Djokovic  ") == "N. Djokovic"

    def test_collapses_multiple_spaces(self):
        assert normalize_player_name("carlos  alcaraz") == "carlos alcaraz"

    def test_empty_returns_empty(self):
        assert normalize_player_name("") == ""

    def test_single_name_unchanged(self):
        assert normalize_player_name("Djokovic") == "Djokovic"

    def test_abbreviated_first_name_preserved(self):
        assert normalize_player_name("S. Swiatek") == "S. Swiatek"

    def test_full_name_preserved(self):
        assert normalize_player_name("Carlos Alcaraz") == "Carlos Alcaraz"


# ---------------------------------------------------------------------------
# extract_last_name
# ---------------------------------------------------------------------------

class TestExtractLastName:

    def test_abbreviated_first_name(self):
        assert extract_last_name("N. Djokovic") == "Djokovic"

    def test_full_name(self):
        assert extract_last_name("Carlos Alcaraz") == "Alcaraz"

    def test_single_name(self):
        assert extract_last_name("Djokovic") == "Djokovic"

    def test_empty_returns_empty(self):
        assert extract_last_name("") == ""

    def test_three_part_name(self):
        assert extract_last_name("A. De Minaur") == "Minaur"

    def test_whitespace_stripped(self):
        assert extract_last_name("  N. Djokovic  ") == "Djokovic"


# ---------------------------------------------------------------------------
# surface_label
# ---------------------------------------------------------------------------

class TestSurfaceLabel:

    def test_clay_label(self):
        assert surface_label("clay") == "Clay"

    def test_grass_label(self):
        assert surface_label("grass") == "Grass"

    def test_hard_label(self):
        assert surface_label("hard") == "Hard"

    def test_unknown_label(self):
        assert surface_label("unknown") == "Unknown"


# ---------------------------------------------------------------------------
# is_upset_surface
# ---------------------------------------------------------------------------

class TestIsUpsetSurface:

    def test_clay_is_upset_surface(self):
        assert is_upset_surface("clay") is True

    def test_grass_is_upset_surface(self):
        assert is_upset_surface("grass") is True

    def test_hard_is_not_upset_surface(self):
        assert is_upset_surface("hard") is False

    def test_unknown_is_not_upset_surface(self):
        assert is_upset_surface("unknown") is False


# ---------------------------------------------------------------------------
# Architecture: no imports from other core modules
# ---------------------------------------------------------------------------

class TestArchitecture:

    def test_no_math_engine_import(self):
        import inspect
        import core.tennis_data as mod
        source = inspect.getsource(mod)
        assert "from core.math_engine" not in source
        assert "import math_engine" not in source

    def test_no_odds_fetcher_import(self):
        import inspect
        import core.tennis_data as mod
        source = inspect.getsource(mod)
        assert "from core.odds_fetcher" not in source
        assert "import odds_fetcher" not in source

    def test_no_line_logger_import(self):
        import inspect
        import core.tennis_data as mod
        source = inspect.getsource(mod)
        assert "from core.line_logger" not in source
        assert "import line_logger" not in source

    def test_no_scheduler_import(self):
        import inspect
        import core.tennis_data as mod
        source = inspect.getsource(mod)
        assert "from core.scheduler" not in source
        assert "import scheduler" not in source
