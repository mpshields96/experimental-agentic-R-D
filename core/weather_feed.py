"""
core/weather_feed.py — NFL Stadium Wind Forecasting

Replaces the static wind stub in nfl_kill_switch() with real forecast data.

Data source: Open-Meteo (https://open-meteo.com/)
- Completely free, no API key required
- Hourly wind speed forecast at stadium coordinates
- Rate limit: 10,000 requests/day (far above our needs)

Architecture:
1. NFL_STADIUMS: static dict of 32 NFL teams → (lat, lon, roof_type, avg_wind_mph)
2. get_stadium_wind(home_team, game_commence_utc) → float (mph)
   - Indoor/retractable roof → 0.0 (controlled environment)
   - Outdoor → Open-Meteo hourly forecast at game time
   - API failure → falls back to avg_wind_mph static stub

Usage:
    from core.weather_feed import get_stadium_wind
    wind_mph = get_stadium_wind("Buffalo Bills", "2026-09-13T17:00:00Z")

DO NOT import this from math_engine — circular import risk.
DO NOT call this from scheduler hot path — results are cached (1-hour TTL).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError
import json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 32-team NFL stadium data
# Roof types: "outdoor", "retractable", "dome"
# avg_wind_mph: static fallback (historical median for that stadium + season)
# ---------------------------------------------------------------------------
NFL_STADIUMS: dict[str, dict] = {
    # AFC East
    "Buffalo Bills":        {"lat": 42.774, "lon": -78.787, "roof": "outdoor",     "avg_wind": 13.0},
    "Miami Dolphins":       {"lat": 25.958, "lon": -80.239, "roof": "outdoor",     "avg_wind": 6.0},
    "New England Patriots": {"lat": 42.091, "lon": -71.264, "roof": "outdoor",     "avg_wind": 9.0},
    "New York Jets":        {"lat": 40.814, "lon": -74.074, "roof": "outdoor",     "avg_wind": 7.0},
    # AFC North
    "Baltimore Ravens":     {"lat": 39.278, "lon": -76.623, "roof": "outdoor",     "avg_wind": 7.0},
    "Cincinnati Bengals":   {"lat": 39.095, "lon": -84.516, "roof": "outdoor",     "avg_wind": 6.0},
    "Cleveland Browns":     {"lat": 41.506, "lon": -81.700, "roof": "outdoor",     "avg_wind": 10.0},
    "Pittsburgh Steelers":  {"lat": 40.447, "lon": -80.016, "roof": "outdoor",     "avg_wind": 7.0},
    # AFC South
    "Houston Texans":       {"lat": 29.685, "lon": -95.411, "roof": "retractable", "avg_wind": 0.0},
    "Indianapolis Colts":   {"lat": 39.760, "lon": -86.164, "roof": "dome",        "avg_wind": 0.0},
    "Jacksonville Jaguars": {"lat": 30.324, "lon": -81.638, "roof": "outdoor",     "avg_wind": 7.0},
    "Tennessee Titans":     {"lat": 36.166, "lon": -86.771, "roof": "outdoor",     "avg_wind": 5.0},
    # AFC West
    "Denver Broncos":       {"lat": 39.744, "lon": -105.020, "roof": "outdoor",    "avg_wind": 7.0},
    "Kansas City Chiefs":   {"lat": 39.049, "lon": -94.484, "roof": "outdoor",     "avg_wind": 9.0},
    "Las Vegas Raiders":    {"lat": 36.091, "lon": -115.184, "roof": "dome",       "avg_wind": 0.0},
    "Los Angeles Chargers": {"lat": 33.953, "lon": -118.339, "roof": "outdoor",    "avg_wind": 4.0},
    # NFC East
    "Dallas Cowboys":       {"lat": 32.748, "lon": -97.093, "roof": "retractable", "avg_wind": 0.0},
    "New York Giants":      {"lat": 40.814, "lon": -74.074, "roof": "outdoor",     "avg_wind": 7.0},
    "Philadelphia Eagles":  {"lat": 39.901, "lon": -75.168, "roof": "outdoor",     "avg_wind": 8.0},
    "Washington Commanders":{"lat": 38.908, "lon": -76.865, "roof": "outdoor",     "avg_wind": 7.0},
    # NFC North
    "Chicago Bears":        {"lat": 41.862, "lon": -87.617, "roof": "outdoor",     "avg_wind": 11.0},
    "Detroit Lions":        {"lat": 42.340, "lon": -83.046, "roof": "dome",        "avg_wind": 0.0},
    "Green Bay Packers":    {"lat": 44.501, "lon": -88.062, "roof": "outdoor",     "avg_wind": 10.0},
    "Minnesota Vikings":    {"lat": 44.974, "lon": -93.258, "roof": "dome",        "avg_wind": 0.0},
    # NFC South
    "Atlanta Falcons":      {"lat": 33.755, "lon": -84.401, "roof": "retractable", "avg_wind": 0.0},
    "Carolina Panthers":    {"lat": 35.226, "lon": -80.853, "roof": "outdoor",     "avg_wind": 5.0},
    "New Orleans Saints":   {"lat": 29.951, "lon": -90.081, "roof": "dome",        "avg_wind": 0.0},
    "Tampa Bay Buccaneers": {"lat": 27.976, "lon": -82.503, "roof": "outdoor",     "avg_wind": 6.0},
    # NFC West
    "Arizona Cardinals":    {"lat": 33.528, "lon": -112.263, "roof": "retractable","avg_wind": 0.0},
    "Los Angeles Rams":     {"lat": 33.953, "lon": -118.339, "roof": "outdoor",    "avg_wind": 4.0},
    "San Francisco 49ers":  {"lat": 37.403, "lon": -121.970, "roof": "outdoor",    "avg_wind": 8.0},
    "Seattle Seahawks":     {"lat": 47.595, "lon": -122.332, "roof": "outdoor",    "avg_wind": 7.0},
}

_DEFAULT_WIND_MPH: float = 5.0   # fallback for unknown teams

# ---------------------------------------------------------------------------
# In-process 1-hour result cache (stadium + date → wind_mph)
# Prevents redundant API calls within a single scheduler poll cycle.
# ---------------------------------------------------------------------------
_wind_cache: dict[str, tuple[float, float]] = {}  # key → (wind_mph, cache_time)
_CACHE_TTL_SECONDS: int = 3600  # 1 hour


def _cache_key(home_team: str, game_utc: datetime) -> str:
    """Cache key: team + date + hour (wind changes slowly)."""
    return f"{home_team}|{game_utc.year}-{game_utc.month:02d}-{game_utc.day:02d}T{game_utc.hour:02d}"


def _fetch_open_meteo_wind(lat: float, lon: float, target_utc: datetime) -> Optional[float]:
    """
    Query Open-Meteo hourly wind speed (10m height) for lat/lon at target_utc.

    Returns wind speed in mph, or None on any error.

    Open-Meteo hourly API:
    https://api.open-meteo.com/v1/forecast?latitude=X&longitude=Y
        &hourly=windspeed_10m&wind_speed_unit=mph&timezone=UTC
        &start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    """
    date_str = target_utc.strftime("%Y-%m-%d")
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&hourly=windspeed_10m"
        f"&wind_speed_unit=mph"
        f"&timezone=UTC"
        f"&start_date={date_str}&end_date={date_str}"
    )
    try:
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        hours = data.get("hourly", {}).get("time", [])
        winds = data.get("hourly", {}).get("windspeed_10m", [])
        if not hours or not winds:
            return None

        # Find the index closest to the game start hour
        target_str = target_utc.strftime("%Y-%m-%dT%H:00")
        if target_str in hours:
            idx = hours.index(target_str)
        else:
            # Fallback: find nearest hour
            target_hour = target_utc.hour
            idx = min(range(len(hours)), key=lambda i: abs(i - target_hour))

        wind_mph = winds[idx]
        if isinstance(wind_mph, (int, float)) and wind_mph >= 0:
            return float(wind_mph)
        return None

    except (URLError, json.JSONDecodeError, KeyError, ValueError, IndexError) as exc:
        logger.warning("Open-Meteo fetch failed (%s): %s", type(exc).__name__, exc)
        return None


def get_stadium_wind(
    home_team: str,
    game_commence_utc: Optional[str] = None,
) -> float:
    """
    Get wind speed in mph for an NFL home team's stadium at game time.

    Indoor and retractable-roof stadiums always return 0.0 (controlled).
    Outdoor stadiums fetch a live forecast from Open-Meteo.
    On API failure, falls back to the team's historical average.

    Args:
        home_team: NFL home team name (must match NFL_STADIUMS keys).
        game_commence_utc: ISO 8601 commence_time string from Odds API.
            If None or unparseable, uses current time as proxy.

    Returns:
        Wind speed in mph (float ≥ 0.0).

    >>> get_stadium_wind("Las Vegas Raiders")
    0.0
    >>> get_stadium_wind("Indianapolis Colts")
    0.0
    """
    stadium = NFL_STADIUMS.get(home_team)
    if stadium is None:
        logger.debug("Unknown NFL team '%s' — using default wind %.1f mph", home_team, _DEFAULT_WIND_MPH)
        return _DEFAULT_WIND_MPH

    # Indoor/retractable: no wind
    if stadium["roof"] in ("dome", "retractable"):
        return 0.0

    # Parse game time
    if game_commence_utc:
        try:
            game_dt = datetime.fromisoformat(
                game_commence_utc.replace("Z", "+00:00")
            ).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            game_dt = datetime.now(timezone.utc)
    else:
        game_dt = datetime.now(timezone.utc)

    # Check cache
    key = _cache_key(home_team, game_dt)
    if key in _wind_cache:
        wind_mph, cache_ts = _wind_cache[key]
        if time.time() - cache_ts < _CACHE_TTL_SECONDS:
            return wind_mph

    # Fetch live forecast
    lat, lon = stadium["lat"], stadium["lon"]
    fetched = _fetch_open_meteo_wind(lat, lon, game_dt)

    if fetched is not None:
        wind_mph = fetched
        logger.info(
            "Stadium wind: %s @ %.4f,%.4f → %.1f mph (Open-Meteo)",
            home_team, lat, lon, wind_mph,
        )
    else:
        wind_mph = stadium["avg_wind"]
        logger.debug(
            "Stadium wind: %s → %.1f mph (static stub fallback)",
            home_team, wind_mph,
        )

    _wind_cache[key] = (wind_mph, time.time())
    return wind_mph


def get_stadium_info(home_team: str) -> Optional[dict]:
    """
    Return stadium metadata for a home team, or None if unknown.

    Returns:
        {"lat": float, "lon": float, "roof": str, "avg_wind": float}
    """
    return NFL_STADIUMS.get(home_team)


def clear_wind_cache() -> None:
    """Clear the in-process wind cache. Intended for testing only."""
    global _wind_cache
    _wind_cache = {}
