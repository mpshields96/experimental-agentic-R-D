"""
tests/test_probe_logger.py — Probe logger tests (Session 9)

Tests cover:
- log_probe_result: writes entry, fields preserved, rolling trim
- read_probe_log: read-back, last_n, sport filter, missing file
- probe_summary: aggregate stats, pinnacle rate, book coverage
- probe_log_status: status string format
"""

import json
import os
import pytest
from pathlib import Path

from core.probe_logger import (
    _MAX_ENTRIES,
    log_probe_result,
    probe_log_status,
    probe_summary,
    read_probe_log,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def log(tmp_path) -> str:
    return str(tmp_path / "probe_test.json")


def _result(pinnacle: bool = False, books: list = None, preferred: list = None,
            n_games: int = 5) -> dict:
    b = books or (["pinnacle", "draftkings"] if pinnacle else ["draftkings", "fanduel"])
    p = preferred or (["draftkings"] if not pinnacle else ["draftkings"])
    return {
        "all_keys":         sorted(b),
        "pinnacle_present": pinnacle,
        "preferred_found":  p,
        "n_games_sampled":  n_games,
        "per_game":         [],
    }


# ---------------------------------------------------------------------------
# log_probe_result
# ---------------------------------------------------------------------------

class TestLogProbeResult:

    def test_creates_file(self, log):
        assert not Path(log).exists()
        log_probe_result(_result(), "NBA", log)
        assert Path(log).exists()

    def test_returns_entry_dict(self, log):
        entry = log_probe_result(_result(), "NBA", log)
        assert isinstance(entry, dict)
        for key in ("timestamp", "sport", "n_games_sampled",
                    "pinnacle_present", "all_keys", "preferred_found", "n_books"):
            assert key in entry, f"Missing key: {key}"

    def test_sport_stored(self, log):
        entry = log_probe_result(_result(), "NHL", log)
        assert entry["sport"] == "NHL"

    def test_pinnacle_present_true(self, log):
        entry = log_probe_result(_result(pinnacle=True), "NBA", log)
        assert entry["pinnacle_present"] is True

    def test_pinnacle_present_false(self, log):
        entry = log_probe_result(_result(pinnacle=False), "NBA", log)
        assert entry["pinnacle_present"] is False

    def test_n_books_is_len_all_keys(self, log):
        entry = log_probe_result(_result(books=["dk", "fd", "bm"]), "NBA", log)
        assert entry["n_books"] == 3

    def test_appends_multiple_entries(self, log):
        for _ in range(5):
            log_probe_result(_result(), "NBA", log)
        entries = read_probe_log(log_path=log)
        assert len(entries) == 5

    def test_rolling_trim_at_max(self, log):
        # Write _MAX_ENTRIES + 10 entries — should trim to _MAX_ENTRIES
        for i in range(_MAX_ENTRIES + 10):
            log_probe_result(_result(n_games=i), "NBA", log)
        entries = read_probe_log(log_path=log)
        assert len(entries) == _MAX_ENTRIES

    def test_rolling_trim_keeps_newest(self, log):
        for i in range(_MAX_ENTRIES + 5):
            log_probe_result(_result(n_games=i), "NBA", log)
        entries = read_probe_log(log_path=log)
        # Last entry should have n_games = _MAX_ENTRIES + 4
        assert entries[-1]["n_games_sampled"] == _MAX_ENTRIES + 4

    def test_json_file_is_valid_list(self, log):
        log_probe_result(_result(), "NBA", log)
        with open(log) as f:
            data = json.load(f)
        assert isinstance(data, list)

    def test_creates_parent_directory(self, tmp_path):
        deep = str(tmp_path / "a" / "b" / "probe.json")
        log_probe_result(_result(), "NBA", deep)
        assert Path(deep).exists()

    def test_empty_all_keys(self, log):
        entry = log_probe_result(
            {"all_keys": [], "pinnacle_present": False,
             "preferred_found": [], "n_games_sampled": 0, "per_game": []},
            "NBA", log,
        )
        assert entry["n_books"] == 0
        assert entry["all_keys"] == []


# ---------------------------------------------------------------------------
# read_probe_log
# ---------------------------------------------------------------------------

class TestReadProbeLog:

    def test_missing_file_returns_empty(self, log):
        entries = read_probe_log(log_path=log)
        assert entries == []

    def test_returns_all_entries(self, log):
        for i in range(8):
            log_probe_result(_result(n_games=i), "NBA", log)
        entries = read_probe_log(log_path=log)
        assert len(entries) == 8

    def test_last_n_slices_tail(self, log):
        for i in range(10):
            log_probe_result(_result(n_games=i), "NBA", log)
        entries = read_probe_log(last_n=3, log_path=log)
        assert len(entries) == 3

    def test_last_n_larger_than_log(self, log):
        for i in range(4):
            log_probe_result(_result(), "NBA", log)
        entries = read_probe_log(last_n=100, log_path=log)
        assert len(entries) == 4

    def test_sport_filter_case_insensitive(self, log):
        log_probe_result(_result(), "NBA", log)
        log_probe_result(_result(), "NHL", log)
        log_probe_result(_result(), "nba", log)
        nba_entries = read_probe_log(sport="NBA", log_path=log)
        assert len(nba_entries) == 2

    def test_sport_filter_excludes_others(self, log):
        log_probe_result(_result(), "NBA", log)
        log_probe_result(_result(), "NHL", log)
        nhl_entries = read_probe_log(sport="NHL", log_path=log)
        assert len(nhl_entries) == 1
        assert nhl_entries[0]["sport"] == "NHL"

    def test_sport_filter_no_match_returns_empty(self, log):
        log_probe_result(_result(), "NBA", log)
        entries = read_probe_log(sport="NCAAB", log_path=log)
        assert entries == []

    def test_corrupt_file_returns_empty(self, log):
        Path(log).write_text("not json {{{{")
        entries = read_probe_log(log_path=log)
        assert entries == []


# ---------------------------------------------------------------------------
# probe_summary
# ---------------------------------------------------------------------------

class TestProbeSummary:

    def test_empty_entries_returns_zeros(self):
        s = probe_summary([])
        assert s["n_probes"] == 0
        assert s["pinnacle_rate"] == 0.0
        assert s["pinnacle_present"] is False
        assert s["all_books_seen"] == []

    def test_n_probes_correct(self, log):
        entries = [_result() for _ in range(7)]
        results = []
        for e in entries:
            results.append({
                "timestamp": "2026-01-01T00:00:00+00:00",
                "sport": "NBA",
                "n_games_sampled": 5,
                "pinnacle_present": False,
                "all_keys": e["all_keys"],
                "preferred_found": e["preferred_found"],
                "n_books": 2,
            })
        s = probe_summary(results)
        assert s["n_probes"] == 7

    def test_pinnacle_rate_all_present(self):
        entries = [
            {"pinnacle_present": True, "all_keys": ["pinnacle"], "preferred_found": [],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
        ] * 4
        s = probe_summary(entries)
        assert s["pinnacle_rate"] == 1.0
        assert s["pinnacle_present"] is True

    def test_pinnacle_rate_none_present(self):
        entries = [
            {"pinnacle_present": False, "all_keys": ["draftkings"], "preferred_found": ["draftkings"],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
        ] * 4
        s = probe_summary(entries)
        assert s["pinnacle_rate"] == 0.0
        assert s["pinnacle_present"] is False

    def test_pinnacle_rate_partial(self):
        entries = [
            {"pinnacle_present": True, "all_keys": ["pinnacle"], "preferred_found": [],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"pinnacle_present": False, "all_keys": ["draftkings"], "preferred_found": ["draftkings"],
             "sport": "NBA", "timestamp": "2026-01-01T01:00:00+00:00"},
        ]
        s = probe_summary(entries)
        assert s["pinnacle_rate"] == 0.5

    def test_all_books_seen_is_union(self):
        entries = [
            {"pinnacle_present": False, "all_keys": ["dk", "fd"], "preferred_found": ["dk"],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"pinnacle_present": False, "all_keys": ["fd", "bm"], "preferred_found": ["dk"],
             "sport": "NBA", "timestamp": "2026-01-01T01:00:00+00:00"},
        ]
        s = probe_summary(entries)
        assert sorted(s["all_books_seen"]) == ["bm", "dk", "fd"]

    def test_all_books_seen_sorted(self):
        entries = [
            {"pinnacle_present": False, "all_keys": ["zzz", "aaa", "mmm"],
             "preferred_found": [], "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"}
        ]
        s = probe_summary(entries)
        assert s["all_books_seen"] == sorted(s["all_books_seen"])

    def test_preferred_coverage_counts(self):
        entries = [
            {"pinnacle_present": False, "all_keys": ["dk"], "preferred_found": ["dk"],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"pinnacle_present": False, "all_keys": ["dk"], "preferred_found": ["dk"],
             "sport": "NBA", "timestamp": "2026-01-01T01:00:00+00:00"},
        ]
        s = probe_summary(entries)
        assert s["preferred_coverage"]["dk"] == 2

    def test_sports_probed_unique(self):
        entries = [
            {"pinnacle_present": False, "all_keys": [], "preferred_found": [],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"pinnacle_present": False, "all_keys": [], "preferred_found": [],
             "sport": "NHL", "timestamp": "2026-01-01T01:00:00+00:00"},
            {"pinnacle_present": False, "all_keys": [], "preferred_found": [],
             "sport": "NBA", "timestamp": "2026-01-01T02:00:00+00:00"},
        ]
        s = probe_summary(entries)
        assert sorted(s["sports_probed"]) == ["NBA", "NHL"]

    def test_last_seen_is_last_entry_timestamp(self):
        entries = [
            {"pinnacle_present": False, "all_keys": [], "preferred_found": [],
             "sport": "NBA", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"pinnacle_present": False, "all_keys": [], "preferred_found": [],
             "sport": "NBA", "timestamp": "2026-02-15T09:30:00+00:00"},
        ]
        s = probe_summary(entries)
        assert s["last_seen"] == "2026-02-15T09:30:00+00:00"

    def test_reads_from_file_when_entries_none(self, log):
        log_probe_result(_result(), "NBA", log)
        s = probe_summary(log_path=log)
        assert s["n_probes"] == 1


# ---------------------------------------------------------------------------
# probe_log_status
# ---------------------------------------------------------------------------

class TestProbeLogStatus:

    def test_empty_log_returns_empty_string(self, log):
        status = probe_log_status(log)
        assert "empty" in status

    def test_non_empty_includes_entry_count(self, log):
        log_probe_result(_result(), "NBA", log)
        status = probe_log_status(log)
        assert "1 entries" in status

    def test_includes_pinnacle_rate(self, log):
        log_probe_result(_result(pinnacle=False), "NBA", log)
        status = probe_log_status(log)
        assert "pinnacle_rate" in status

    def test_includes_books(self, log):
        log_probe_result(_result(books=["draftkings", "fanduel"]), "NBA", log)
        status = probe_log_status(log)
        assert "draftkings" in status or "fanduel" in status

    def test_no_crash_with_many_books(self, log):
        log_probe_result(
            _result(books=["b1", "b2", "b3", "b4", "b5", "b6", "b7"]), "NBA", log
        )
        status = probe_log_status(log)
        assert "more" in status  # "+N more" truncation
