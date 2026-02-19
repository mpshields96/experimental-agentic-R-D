"""
tests/test_clv_tracker.py — CLV Tracker tests (Session 7)

Tests cover:
- log_clv_snapshot: writes row, correct CLV math, grade populated
- read_clv_log: reads back entries, type coercion, last_n
- clv_summary: aggregate stats, gate logic, verdict strings
- print_clv_report: smoke test (no crash, output to stdout)
- probe_bookmakers: bookmaker key survey, pinnacle detection
- print_pinnacle_report: smoke test

Each test uses a tmp_path fixture or an isolated tmp file to avoid CSV bleed.
"""

import os
import csv
import tempfile
from pathlib import Path

import pytest

from core.clv_tracker import (
    CLV_GATE,
    clv_summary,
    log_clv_snapshot,
    print_clv_report,
    read_clv_log,
)
from core.odds_fetcher import probe_bookmakers, print_pinnacle_report


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_log(tmp_path) -> str:
    """Return a unique temp CSV path for each test."""
    return str(tmp_path / "clv_test.csv")


def _make_entries(n: int, clv_pct: float = 1.5) -> list[dict]:
    """Create n synthetic log entry dicts with fixed clv_pct."""
    return [
        {"clv_pct": clv_pct, "grade": "GOOD", "event_id": f"ev{i}", "side": "TeamA"}
        for i in range(n)
    ]


def _make_game(home: str, away: str, book_keys: list[str]) -> dict:
    """Build a minimal raw game dict with specified bookmaker keys."""
    return {
        "home_team": home,
        "away_team": away,
        "bookmakers": [{"key": k, "markets": [{"key": "h2h"}]} for k in book_keys],
    }


# ---------------------------------------------------------------------------
# log_clv_snapshot
# ---------------------------------------------------------------------------

class TestLogClvSnapshot:

    def test_returns_dict_with_required_keys(self, tmp_log):
        row = log_clv_snapshot("ev001", "Duke", -110, -110, -120, log_path=tmp_log)
        for key in ("timestamp", "event_id", "side", "open_price", "bet_price",
                    "close_price", "clv_pct", "grade"):
            assert key in row, f"Missing key: {key}"

    def test_event_id_and_side_preserved(self, tmp_log):
        row = log_clv_snapshot("abc123", "Over", -115, -115, -118, log_path=tmp_log)
        assert row["event_id"] == "abc123"
        assert row["side"] == "Over"

    def test_clv_pct_positive_when_beat_close(self, tmp_log):
        # Bet at -110, closed at -120 (worse for bettors) → we got a better number
        row = log_clv_snapshot("ev002", "TeamA", -115, -110, -120, log_path=tmp_log)
        assert row["clv_pct"] > 0, f"Expected positive CLV, got {row['clv_pct']}"

    def test_clv_pct_negative_when_missed_close(self, tmp_log):
        # Bet at -120, closed at -110 (better for bettors) → we paid more
        row = log_clv_snapshot("ev003", "TeamB", -110, -120, -110, log_path=tmp_log)
        assert row["clv_pct"] < 0, f"Expected negative CLV, got {row['clv_pct']}"

    def test_clv_pct_zero_when_bet_equals_close(self, tmp_log):
        row = log_clv_snapshot("ev004", "TeamC", -110, -110, -110, log_path=tmp_log)
        assert row["clv_pct"] == 0.0

    def test_grade_populated(self, tmp_log):
        row = log_clv_snapshot("ev005", "TeamA", -110, -110, -130, log_path=tmp_log)
        assert row["grade"] in ("EXCELLENT", "GOOD", "NEUTRAL", "POOR")

    def test_creates_csv_file(self, tmp_log):
        assert not Path(tmp_log).exists()
        log_clv_snapshot("ev006", "TeamA", -110, -110, -115, log_path=tmp_log)
        assert Path(tmp_log).exists()

    def test_appends_multiple_rows(self, tmp_log):
        for i in range(5):
            log_clv_snapshot(f"ev{i:03d}", "TeamA", -110, -110, -115, log_path=tmp_log)
        entries = read_clv_log(log_path=tmp_log)
        assert len(entries) == 5

    def test_clv_pct_is_percentage_not_decimal(self, tmp_log):
        # calculate_clv returns ~0.0188 for -110 bet vs -120 close
        # We store as % so clv_pct should be ~1.88, not 0.0188
        row = log_clv_snapshot("ev007", "TeamA", -115, -110, -120, log_path=tmp_log)
        assert 0.5 < row["clv_pct"] < 5.0, (
            f"clv_pct={row['clv_pct']} looks like it might be stored as decimal "
            f"instead of percentage"
        )

    def test_creates_parent_directory_if_missing(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "clv.csv")
        row = log_clv_snapshot("ev008", "TeamA", -110, -110, -115, log_path=deep_path)
        assert Path(deep_path).exists()


# ---------------------------------------------------------------------------
# read_clv_log
# ---------------------------------------------------------------------------

class TestReadClvLog:

    def test_returns_empty_list_for_missing_file(self, tmp_log):
        entries = read_clv_log(log_path=tmp_log)
        assert entries == []

    def test_returns_all_entries_by_default(self, tmp_log):
        for i in range(10):
            log_clv_snapshot(f"ev{i:03d}", "Team", -110, -110, -115, log_path=tmp_log)
        entries = read_clv_log(log_path=tmp_log)
        assert len(entries) == 10

    def test_last_n_slices_tail(self, tmp_log):
        for i in range(10):
            log_clv_snapshot(f"ev{i:03d}", "Team", -110, -110, -115, log_path=tmp_log)
        entries = read_clv_log(last_n=3, log_path=tmp_log)
        assert len(entries) == 3

    def test_last_n_larger_than_log_returns_all(self, tmp_log):
        for i in range(5):
            log_clv_snapshot(f"ev{i:03d}", "Team", -110, -110, -115, log_path=tmp_log)
        entries = read_clv_log(last_n=100, log_path=tmp_log)
        assert len(entries) == 5

    def test_clv_pct_coerced_to_float(self, tmp_log):
        log_clv_snapshot("ev001", "Team", -110, -110, -120, log_path=tmp_log)
        entries = read_clv_log(log_path=tmp_log)
        assert isinstance(entries[0]["clv_pct"], float)

    def test_prices_coerced_to_int(self, tmp_log):
        log_clv_snapshot("ev001", "Team", -115, -110, -120, log_path=tmp_log)
        entries = read_clv_log(log_path=tmp_log)
        e = entries[0]
        assert isinstance(e["open_price"], int)
        assert isinstance(e["bet_price"], int)
        assert isinstance(e["close_price"], int)

    def test_event_id_preserved(self, tmp_log):
        log_clv_snapshot("unique_event_xyz", "Team", -110, -110, -115, log_path=tmp_log)
        entries = read_clv_log(log_path=tmp_log)
        assert entries[0]["event_id"] == "unique_event_xyz"


# ---------------------------------------------------------------------------
# clv_summary
# ---------------------------------------------------------------------------

class TestClvSummary:

    def test_empty_entries_returns_insufficient_data(self):
        s = clv_summary([])
        assert s["verdict"] == "INSUFFICIENT DATA"
        assert s["n"] == 0
        assert s["below_gate"] is True

    def test_below_gate_with_few_entries(self):
        entries = _make_entries(CLV_GATE - 1)
        s = clv_summary(entries)
        assert s["below_gate"] is True
        assert s["verdict"] == "INSUFFICIENT DATA"

    def test_at_gate_no_longer_below(self):
        entries = _make_entries(CLV_GATE, clv_pct=2.0)
        s = clv_summary(entries)
        assert s["below_gate"] is False

    def test_strong_edge_capture_verdict(self):
        # avg=2.0, positive_rate=1.0 → STRONG EDGE CAPTURE
        entries = _make_entries(CLV_GATE, clv_pct=2.0)
        s = clv_summary(entries)
        assert s["verdict"] == "STRONG EDGE CAPTURE"

    def test_marginal_verdict(self):
        # avg=1.0, positive_rate=1.0 → MARGINAL (avg>=0.5, rate>=0.5)
        entries = _make_entries(CLV_GATE, clv_pct=1.0)
        s = clv_summary(entries)
        assert s["verdict"] == "MARGINAL"

    def test_no_edge_verdict(self):
        # all negative → NO EDGE
        entries = _make_entries(CLV_GATE, clv_pct=-1.0)
        s = clv_summary(entries)
        assert s["verdict"] == "NO EDGE"

    def test_n_matches_entry_count(self):
        entries = _make_entries(7, clv_pct=1.0)
        s = clv_summary(entries)
        assert s["n"] == 7

    def test_avg_clv_pct_correct(self):
        entries = [{"clv_pct": 1.0}, {"clv_pct": 3.0}]
        s = clv_summary(entries)
        assert s["avg_clv_pct"] == 2.0

    def test_positive_rate_correct(self):
        entries = [
            {"clv_pct": 1.0},
            {"clv_pct": -1.0},
            {"clv_pct": 2.0},
            {"clv_pct": -0.5},
        ]
        s = clv_summary(entries)
        assert s["positive_rate"] == 0.5

    def test_max_min_clv(self):
        entries = [{"clv_pct": -2.0}, {"clv_pct": 5.0}, {"clv_pct": 1.0}]
        s = clv_summary(entries)
        assert s["max_clv_pct"] == 5.0
        assert s["min_clv_pct"] == -2.0

    def test_single_entry_no_crash(self):
        entries = [{"clv_pct": 1.5, "grade": "GOOD"}]
        s = clv_summary(entries)
        assert s["n"] == 1

    def test_all_zero_clv(self):
        entries = _make_entries(CLV_GATE, clv_pct=0.0)
        s = clv_summary(entries)
        assert s["verdict"] == "NO EDGE"
        assert s["positive_rate"] == 0.0


# ---------------------------------------------------------------------------
# print_clv_report (smoke test)
# ---------------------------------------------------------------------------

class TestPrintClvReport:

    def test_no_crash_empty_log(self, tmp_log, capsys):
        print_clv_report(log_path=tmp_log)
        out = capsys.readouterr().out
        assert "CLV TRACKER REPORT" in out
        assert "INSUFFICIENT DATA" in out

    def test_no_crash_with_entries(self, tmp_log, capsys):
        for i in range(5):
            log_clv_snapshot(f"ev{i:03d}", "Team", -110, -110, -115, log_path=tmp_log)
        print_clv_report(log_path=tmp_log)
        out = capsys.readouterr().out
        assert "CLV TRACKER REPORT" in out
        assert "5" in out

    def test_report_shows_grade_breakdown(self, tmp_log, capsys):
        for i in range(3):
            log_clv_snapshot(f"ev{i:03d}", "Team", -110, -110, -120, log_path=tmp_log)
        print_clv_report(log_path=tmp_log)
        out = capsys.readouterr().out
        assert "Grade breakdown" in out


# ---------------------------------------------------------------------------
# probe_bookmakers
# ---------------------------------------------------------------------------

class TestProbeBookmakers:

    def test_empty_games_returns_zeroed_result(self):
        result = probe_bookmakers([])
        assert result["n_games_sampled"] == 0
        assert result["pinnacle_present"] is False
        assert result["all_keys"] == []
        assert result["preferred_found"] == []
        assert result["per_game"] == []

    def test_detects_pinnacle_when_present(self):
        games = [_make_game("Home", "Away", ["pinnacle", "draftkings"])]
        result = probe_bookmakers(games)
        assert result["pinnacle_present"] is True

    def test_no_pinnacle_when_absent(self):
        games = [_make_game("Home", "Away", ["draftkings", "fanduel"])]
        result = probe_bookmakers(games)
        assert result["pinnacle_present"] is False

    def test_all_keys_deduped_across_games(self):
        games = [
            _make_game("HA", "AA", ["draftkings", "fanduel"]),
            _make_game("HB", "AB", ["fanduel", "betmgm"]),
        ]
        result = probe_bookmakers(games)
        assert sorted(result["all_keys"]) == ["betmgm", "draftkings", "fanduel"]

    def test_n_games_sampled_correct(self):
        games = [_make_game(f"H{i}", f"A{i}", ["draftkings"]) for i in range(7)]
        result = probe_bookmakers(games)
        assert result["n_games_sampled"] == 7

    def test_per_game_capped_at_5(self):
        games = [_make_game(f"H{i}", f"A{i}", ["draftkings"]) for i in range(10)]
        result = probe_bookmakers(games)
        assert len(result["per_game"]) == 5

    def test_per_game_has_matchup_and_books(self):
        games = [_make_game("Lakers", "Celtics", ["draftkings", "fanduel"])]
        result = probe_bookmakers(games)
        pg = result["per_game"][0]
        assert "matchup" in pg
        assert "books" in pg
        assert "Celtics @ Lakers" in pg["matchup"]

    def test_preferred_found_subset_of_known_books(self):
        from core.odds_fetcher import PREFERRED_BOOKS
        games = [_make_game("H", "A", ["draftkings", "pinnacle", "randombook"])]
        result = probe_bookmakers(games)
        for b in result["preferred_found"]:
            assert b in PREFERRED_BOOKS

    def test_preferred_found_not_including_unknown_books(self):
        games = [_make_game("H", "A", ["unknownbook1", "unknownbook2"])]
        result = probe_bookmakers(games)
        assert result["preferred_found"] == []

    def test_game_with_no_bookmakers(self):
        games = [{"home_team": "H", "away_team": "A", "bookmakers": []}]
        result = probe_bookmakers(games)
        assert result["n_games_sampled"] == 1
        assert result["all_keys"] == []

    def test_all_keys_sorted(self):
        games = [_make_game("H", "A", ["zzz", "aaa", "mmm"])]
        result = probe_bookmakers(games)
        assert result["all_keys"] == sorted(result["all_keys"])


# ---------------------------------------------------------------------------
# print_pinnacle_report (smoke test)
# ---------------------------------------------------------------------------

class TestPrintPinnacleReport:

    def test_no_crash_pinnacle_absent(self, capsys):
        result = probe_bookmakers([_make_game("H", "A", ["draftkings"])])
        print_pinnacle_report(result)
        out = capsys.readouterr().out
        assert "PINNACLE PROBE REPORT" in out
        assert "NO" in out

    def test_no_crash_pinnacle_present(self, capsys):
        result = probe_bookmakers([_make_game("H", "A", ["pinnacle", "draftkings"])])
        print_pinnacle_report(result)
        out = capsys.readouterr().out
        assert "PINNACLE PROBE REPORT" in out
        assert "YES" in out

    def test_empty_games_no_crash(self, capsys):
        result = probe_bookmakers([])
        print_pinnacle_report(result)
        out = capsys.readouterr().out
        assert "PINNACLE PROBE REPORT" in out
