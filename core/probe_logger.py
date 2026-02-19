"""
core/probe_logger.py — Pinnacle Probe Log (Session 9)
=======================================================
Persistent JSON log of bookmaker probe results from scheduler polls.

Responsibilities:
- Append one probe result per poll (per sport) to probe_log.json
- Read back entries for R&D Output dashboard display
- Summarise Pinnacle presence rate + preferred book coverage over time

Design decisions:
- JSON (not SQLite): probe data is tiny + sequential; JSON is readable in the repo
- Append-only list: each entry is a complete probe_result dict + timestamp + sport
- Max 200 entries stored (rolling window) — auto-trimmed on write
- File created on first write; missing file = empty log

Wire-in point (scheduler._poll_all_sports, per sport with games):
    from core.probe_logger import log_probe_result
    from core.odds_fetcher import probe_bookmakers
    result = probe_bookmakers(games)
    log_probe_result(result, sport=sport)

DO NOT add API calls or Streamlit imports to this file.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_LOG_PATH = str(Path(__file__).parent.parent / "data" / "probe_log.json")
_MAX_ENTRIES = 200


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_path() -> str:
    return os.environ.get("PROBE_LOG_PATH", _DEFAULT_LOG_PATH)


def _read_raw(path: str) -> list[dict]:
    """Read raw list from JSON file. Returns empty list on missing/corrupt file."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write_raw(entries: list[dict], path: str) -> None:
    """Write list to JSON file, creating parent dirs if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(entries, f, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_probe_result(
    probe_result: dict,
    sport: str = "",
    log_path: Optional[str] = None,
) -> dict:
    """
    Append one probe result to the JSON log.

    Trims the log to _MAX_ENTRIES (200) on each write to prevent unbounded growth.

    Args:
        probe_result: Dict returned by probe_bookmakers(). Expected keys:
                      all_keys, pinnacle_present, preferred_found,
                      n_games_sampled, per_game.
        sport:        Sport name (e.g. "NBA"). Stored for filtering.
        log_path:     Override log file path.

    Returns:
        The entry dict written to the log (for test assertions).

    >>> import os; os.environ["PROBE_LOG_PATH"] = "/tmp/test_probe.json"
    >>> result = {"all_keys": ["draftkings"], "pinnacle_present": False,
    ...           "preferred_found": ["draftkings"], "n_games_sampled": 5, "per_game": []}
    >>> entry = log_probe_result(result, "NBA", "/tmp/test_probe.json")
    >>> entry["sport"]
    'NBA'
    >>> entry["pinnacle_present"]
    False
    """
    path = log_path or _log_path()
    entries = _read_raw(path)

    entry = {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "sport":            sport,
        "n_games_sampled":  probe_result.get("n_games_sampled", 0),
        "pinnacle_present": probe_result.get("pinnacle_present", False),
        "all_keys":         probe_result.get("all_keys", []),
        "preferred_found":  probe_result.get("preferred_found", []),
        "n_books":          len(probe_result.get("all_keys", [])),
    }

    entries.append(entry)

    # Rolling trim
    if len(entries) > _MAX_ENTRIES:
        entries = entries[-_MAX_ENTRIES:]

    _write_raw(entries, path)
    return entry


def read_probe_log(
    last_n: Optional[int] = None,
    sport: Optional[str] = None,
    log_path: Optional[str] = None,
) -> list[dict]:
    """
    Read probe log entries.

    Args:
        last_n:   Return only the most recent N entries. None = all.
        sport:    Filter by sport name (case-insensitive). None = all.
        log_path: Override log file path.

    Returns:
        List of entry dicts. Empty list if file doesn't exist.

    >>> import os; os.environ["PROBE_LOG_PATH"] = "/tmp/test_probe_read.json"
    >>> r = {"all_keys": [], "pinnacle_present": False, "preferred_found": [],
    ...      "n_games_sampled": 0, "per_game": []}
    >>> _ = log_probe_result(r, "NBA", "/tmp/test_probe_read.json")
    >>> entries = read_probe_log(log_path="/tmp/test_probe_read.json")
    >>> len(entries) >= 1
    True
    """
    path = log_path or _log_path()
    entries = _read_raw(path)

    if sport is not None:
        entries = [e for e in entries if e.get("sport", "").upper() == sport.upper()]

    if last_n is not None:
        entries = entries[-last_n:]

    return entries


def probe_summary(
    entries: Optional[list[dict]] = None,
    log_path: Optional[str] = None,
) -> dict:
    """
    Aggregate probe statistics from log entries.

    Args:
        entries:  Pre-loaded entries (skips file read if provided).
        log_path: Override log file path (used if entries is None).

    Returns:
        {
            "n_probes":           int,   total observations
            "pinnacle_rate":      float, fraction of probes where pinnacle appeared
            "pinnacle_present":   bool,  True if pinnacle found in ANY probe
            "all_books_seen":     list,  sorted union of all bookmaker keys ever seen
            "preferred_coverage": dict,  {book_key: times_seen} for PREFERRED_BOOKS
            "sports_probed":      list,  unique sports probed
            "last_seen":          str,   ISO timestamp of most recent entry
        }

    >>> probe_summary([])["n_probes"]
    0
    >>> probe_summary([{"pinnacle_present": True, "all_keys": ["pinnacle", "dk"],
    ...                 "preferred_found": ["dk"], "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"}])["pinnacle_rate"]
    1.0
    """
    if entries is None:
        entries = read_probe_log(log_path=log_path)

    if not entries:
        return {
            "n_probes":           0,
            "pinnacle_rate":      0.0,
            "pinnacle_present":   False,
            "all_books_seen":     [],
            "preferred_coverage": {},
            "sports_probed":      [],
            "last_seen":          "",
        }

    n = len(entries)
    pinnacle_count = sum(1 for e in entries if e.get("pinnacle_present", False))
    all_books: set[str] = set()
    preferred_counts: dict[str, int] = {}
    sports: set[str] = set()

    for e in entries:
        all_books.update(e.get("all_keys", []))
        for b in e.get("preferred_found", []):
            preferred_counts[b] = preferred_counts.get(b, 0) + 1
        sp = e.get("sport", "")
        if sp:
            sports.add(sp)

    last_seen = entries[-1].get("timestamp", "") if entries else ""

    return {
        "n_probes":           n,
        "pinnacle_rate":      round(pinnacle_count / n, 4),
        "pinnacle_present":   pinnacle_count > 0,
        "all_books_seen":     sorted(all_books),
        "preferred_coverage": preferred_counts,
        "sports_probed":      sorted(sports),
        "last_seen":          last_seen,
    }


def probe_log_status(log_path: Optional[str] = None) -> str:
    """
    Return a one-line status string for logging and sidebar display.

    Args:
        log_path: Override log file path.

    Returns:
        E.g. "probe_log: 47 entries, pinnacle_rate=0.0%, books=[draftkings, fanduel]"
    """
    entries = read_probe_log(log_path=log_path)
    if not entries:
        return "probe_log: empty"
    s = probe_summary(entries)
    books = ", ".join(s["all_books_seen"][:5])
    if len(s["all_books_seen"]) > 5:
        books += f" +{len(s['all_books_seen']) - 5} more"
    return (
        f"probe_log: {s['n_probes']} entries, "
        f"pinnacle_rate={s['pinnacle_rate']:.1%}, "
        f"books=[{books}]"
    )
