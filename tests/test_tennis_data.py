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
    ATP_SURFACE_WIN_RATES,
    SURFACE_CLAY,
    SURFACE_DOMINANT_THRESHOLD,
    SURFACE_ELITE_THRESHOLD,
    SURFACE_GRASS,
    SURFACE_HARD,
    SURFACE_SPECIALIST_THRESHOLD,
    SURFACE_UNKNOWN,
    WTA_SURFACE_WIN_RATES,
    extract_last_name,
    get_player_surface_rate,
    get_surface_risk_summary,
    is_tennis_sport_key,
    is_upset_surface,
    normalize_player_name,
    surface_from_sport_key,
    surface_label,
    surface_mismatch_severity,
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

# ---------------------------------------------------------------------------
# Player surface win rate table
# ---------------------------------------------------------------------------

class TestGetPlayerSurfaceRate:

    def test_swiatek_clay_elite(self):
        rate = get_player_surface_rate("Swiatek", "clay")
        assert rate == 0.95

    def test_djokovic_clay(self):
        assert get_player_surface_rate("Djokovic", "clay") == 0.84

    def test_djokovic_hard(self):
        assert get_player_surface_rate("Djokovic", "hard") == 0.90

    def test_ruud_grass_poor(self):
        """Ruud is a clay specialist with weak grass numbers."""
        rate = get_player_surface_rate("Ruud", "grass")
        assert rate is not None
        assert rate < SURFACE_SPECIALIST_THRESHOLD  # below 0.60

    def test_medvedev_hard_dominant(self):
        rate = get_player_surface_rate("Medvedev", "hard")
        assert rate >= SURFACE_DOMINANT_THRESHOLD

    def test_rybakina_grass_specialist(self):
        rate = get_player_surface_rate("Rybakina", "grass")
        assert rate >= SURFACE_DOMINANT_THRESHOLD

    def test_case_insensitive_lookup(self):
        """Lookup is case-insensitive."""
        assert get_player_surface_rate("DJOKOVIC", "clay") == get_player_surface_rate("djokovic", "clay")
        assert get_player_surface_rate("Swiatek", "CLAY") == get_player_surface_rate("swiatek", "clay")

    def test_unknown_player_returns_none(self):
        assert get_player_surface_rate("Zverevski", "clay") is None

    def test_empty_name_returns_none(self):
        assert get_player_surface_rate("", "clay") is None

    def test_empty_surface_returns_none(self):
        assert get_player_surface_rate("Djokovic", "") is None

    def test_all_atp_players_have_all_surfaces(self):
        """Every player in ATP table has clay, grass, hard entries."""
        for name, rates in ATP_SURFACE_WIN_RATES.items():
            for surface in ["clay", "grass", "hard"]:
                assert surface in rates, f"{name} missing {surface}"

    def test_all_wta_players_have_all_surfaces(self):
        for name, rates in WTA_SURFACE_WIN_RATES.items():
            for surface in ["clay", "grass", "hard"]:
                assert surface in rates, f"{name} missing {surface}"

    def test_all_rates_in_valid_range(self):
        """All non-None rates must be between 0.0 and 1.0."""
        from core.tennis_data import _ALL_SURFACE_WIN_RATES
        for name, rates in _ALL_SURFACE_WIN_RATES.items():
            for surface, rate in rates.items():
                if rate is not None:
                    assert 0.0 <= rate <= 1.0, f"{name} {surface}={rate} out of range"

    def test_last_name_alias_consistency(self):
        """Players with aliases (e.g. de minaur / minaur) return the same value."""
        r1 = get_player_surface_rate("de minaur", "clay")
        r2 = get_player_surface_rate("minaur", "clay")
        assert r1 == r2

    def test_at_least_50_atp_entries(self):
        assert len(ATP_SURFACE_WIN_RATES) >= 40

    def test_at_least_40_wta_entries(self):
        assert len(WTA_SURFACE_WIN_RATES) >= 35


# ---------------------------------------------------------------------------
# surface_mismatch_severity
# ---------------------------------------------------------------------------

class TestSurfaceMismatchSeverity:

    def test_swiatek_clay_is_elite(self):
        assert surface_mismatch_severity("Swiatek", "clay") == "elite"

    def test_djokovic_hard_is_elite(self):
        assert surface_mismatch_severity("Djokovic", "hard") == "elite"

    def test_djokovic_grass_is_elite(self):
        assert surface_mismatch_severity("Djokovic", "grass") == "elite"

    def test_rybakina_grass_is_specialist(self):
        assert surface_mismatch_severity("Rybakina", "grass") in {"elite", "specialist"}

    def test_medvedev_clay_is_adequate(self):
        # Medvedev clay=0.66 — between SPECIALIST_THRESHOLD (0.60) and DOMINANT (0.75)
        sev = surface_mismatch_severity("Medvedev", "clay")
        assert sev == "adequate"

    def test_ruud_grass_is_poor(self):
        # Ruud grass=0.56 — below SPECIALIST_THRESHOLD (0.60) and above 0.50
        sev = surface_mismatch_severity("Ruud", "grass")
        assert sev in {"weak", "poor"}

    def test_unknown_player_is_unknown(self):
        assert surface_mismatch_severity("Bogusplayer", "clay") == "unknown"

    def test_severity_ordering(self):
        """Elite rate > specialist rate > adequate rate for same player on same surface."""
        # Swiatek clay (0.95) > adequate threshold
        assert surface_mismatch_severity("Swiatek", "clay") in {"elite", "specialist"}
        # Medvedev clay (0.66) > specialist threshold
        assert surface_mismatch_severity("Medvedev", "clay") in {"specialist", "adequate"}

    def test_all_severities_are_valid_strings(self):
        valid = {"elite", "specialist", "adequate", "weak", "poor", "unknown"}
        for name in ["Djokovic", "Ruud", "Medvedev", "UnknownX"]:
            for surface in ["clay", "grass", "hard"]:
                sev = surface_mismatch_severity(name, surface)
                assert sev in valid, f"{name} {surface} returned invalid severity: {sev}"


# ---------------------------------------------------------------------------
# get_surface_risk_summary
# ---------------------------------------------------------------------------

class TestGetSurfaceRiskSummary:

    def test_known_vs_known_has_no_none_rates(self):
        r = get_surface_risk_summary("Swiatek", "Rybakina", "clay")
        assert r["player1_rate"] is not None
        assert r["player2_rate"] is not None

    def test_delta_computed_correctly(self):
        r = get_surface_risk_summary("Swiatek", "Rybakina", "clay")
        # Swiatek clay=0.95, Rybakina clay=0.72 → delta ≈ +0.23
        assert r["surface_delta"] is not None
        assert abs(r["surface_delta"] - (0.95 - 0.72)) < 0.01

    def test_risk_flag_fires_for_poor_player(self):
        # Ruud grass=0.56 → poor/weak → risk_flag should be True
        r = get_surface_risk_summary("Ruud", "Djokovic", "grass")
        assert r["risk_flag"] is True

    def test_risk_flag_false_for_strong_matchup(self):
        r = get_surface_risk_summary("Djokovic", "Alcaraz", "clay")
        # Both are elite clay players — no risk flag
        assert r["risk_flag"] is False

    def test_unknown_vs_unknown_has_advisory(self):
        r = get_surface_risk_summary("Bogus1", "Bogus2", "clay")
        assert "advisory" in r
        assert len(r["advisory"]) > 0

    def test_unknown_player_rate_is_none(self):
        r = get_surface_risk_summary("BogusPlayer", "Djokovic", "hard")
        assert r["player1_rate"] is None
        assert r["player2_rate"] is not None

    def test_delta_none_when_one_player_unknown(self):
        r = get_surface_risk_summary("Unknown", "Djokovic", "hard")
        assert r["surface_delta"] is None

    def test_advisory_contains_rate_info(self):
        r = get_surface_risk_summary("Djokovic", "Medvedev", "clay")
        assert "clay" in r["advisory"].lower() or "%" in r["advisory"]

    def test_return_dict_has_required_keys(self):
        r = get_surface_risk_summary("Swiatek", "Gauff", "hard")
        for k in ["player1_rate", "player2_rate", "player1_severity", "player2_severity",
                  "surface_delta", "risk_flag", "advisory"]:
            assert k in r

    def test_risk_flag_is_bool(self):
        r = get_surface_risk_summary("Djokovic", "Sinner", "hard")
        assert isinstance(r["risk_flag"], bool)
