"""
Tests for scripts/bet_summary.py

Smoke tests: verifies the script runs cleanly against an in-memory DB
with known data and produces expected output tokens.
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
from io import StringIO
from unittest import mock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_db(path: str) -> None:
    """Create a minimal bet_log DB with 3 resolved + 1 pending bet."""
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at TEXT NOT NULL DEFAULT '',
            matchup TEXT NOT NULL DEFAULT '',
            market_type TEXT NOT NULL DEFAULT '',
            target TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL DEFAULT 0,
            edge_pct REAL DEFAULT 0.0,
            grade TEXT DEFAULT '',
            result TEXT DEFAULT 'pending',
            profit REAL DEFAULT 0.0,
            stake REAL DEFAULT 0.0,
            close_price INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        )
    """)
    bets = [
        ("OKC @ TOR", "spreads", "OKC -7.5", -115, 0.172, "A", "win",  43.48, 50.0),
        ("NYK @ CLE", "spreads", "CLE -17.5", 120, 0.049, "A", "loss",  0.0,  0.0),
        ("BRA @ UIC", "h2h",    "UIC ML",   -134, 0.112, "A", "win",  18.66, 25.0),
        ("FRE @ CSU", "h2h",    "CSU ML",    143, 0.052, "B", "pending", 0.0, 25.0),
    ]
    conn.executemany(
        "INSERT INTO bet_log (matchup,market_type,target,price,edge_pct,grade,result,profit,stake)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        bets,
    )
    conn.commit()
    conn.close()


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "bet_summary",
        os.path.join(os.path.dirname(__file__), "..", "scripts", "bet_summary.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBetSummarySmoke:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        _create_test_db(self.tmp.name)
        self.mod = _load_module()

    def teardown_method(self):
        os.unlink(self.tmp.name)

    def _run(self, extra_args=None):
        args = ["bet_summary.py", "--db", self.tmp.name] + (extra_args or [])
        with mock.patch("sys.argv", args):
            buf = StringIO()
            with mock.patch("sys.stdout", buf):
                self.mod.main()
        return buf.getvalue()

    def test_runs_without_error(self):
        output = self._run()
        assert output  # non-empty

    def test_shows_gate_progress(self):
        output = self._run()
        assert "2/10" in output or "3/10" in output  # 2 or 3 resolved (loss stake=0 may vary)
        assert "ANALYTICS GATE" in output

    def test_shows_record(self):
        output = self._run()
        assert "W –" in output or "W -" in output
        assert "RECORD" in output

    def test_shows_roi(self):
        output = self._run()
        assert "ROI" in output
        assert "%" in output

    def test_shows_grade_breakdown(self):
        output = self._run()
        assert "GRADE BREAKDOWN" in output
        assert "A" in output

    def test_locked_status_when_below_gate(self):
        output = self._run()
        assert "LOCKED" in output

    def test_all_flag_includes_pending(self):
        output = self._run(["--all"])
        assert "pending" in output.lower() or "⏳" in output

    def test_gate_unlocked_when_ten_resolved(self):
        conn = sqlite3.connect(self.tmp.name)
        for i in range(8):
            conn.execute(
                "INSERT INTO bet_log (matchup,market_type,target,price,edge_pct,grade,result,profit,stake)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (f"Team{i} @ Team{i+1}", "h2h", f"Team{i} ML", -110, 0.05, "A", "win", 9.0, 10.0),
            )
        conn.commit()
        conn.close()
        output = self._run()
        assert "UNLOCKED" in output

    def test_empty_db_does_not_crash(self):
        tmp2 = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp2.close()
        conn = sqlite3.connect(tmp2.name)
        conn.execute("""
            CREATE TABLE bet_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at TEXT DEFAULT '', matchup TEXT DEFAULT '',
                market_type TEXT DEFAULT '', target TEXT DEFAULT '',
                price INTEGER DEFAULT 0, edge_pct REAL DEFAULT 0.0,
                grade TEXT DEFAULT '', result TEXT DEFAULT 'pending',
                profit REAL DEFAULT 0.0, stake REAL DEFAULT 0.0,
                close_price INTEGER DEFAULT 0, notes TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()
        args = ["bet_summary.py", "--db", tmp2.name]
        with mock.patch("sys.argv", args):
            buf = StringIO()
            with mock.patch("sys.stdout", buf):
                self.mod.main()
        output = buf.getvalue()
        assert "0/10" in output
        os.unlink(tmp2.name)
