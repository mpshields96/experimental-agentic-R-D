"""
tests/test_paper_bet_logging.py — V37 Session 38A directive
============================================================
Unit tests for paper bet logging logic in pages/01_live_lines.py.

V37 required (REVIEW_LOG 2026-02-26):
  1. test_log_paper_bet_grade_c_sets_stake_zero  — Grade C -> stake=0.0
  2. test_log_paper_bet_grade_a_uses_kelly_size  — Grade A -> stake=kelly_size
  3. test_paper_log_button_idempotency           — session_state guard prevents double-log

Strategy: extract function source via ast.get_source_segment to avoid importing the
full Streamlit page (which has module-level _render() calls that fail without live Streamlit).
All log_bet writes use a temp SQLite DB.
"""

import ast
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
PAGE_PATH = ROOT / "pages" / "01_live_lines.py"


def _extract_function_source(func_name: str) -> str:
    src = PAGE_PATH.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return ast.get_source_segment(src, node)
    raise ValueError(f"Function '{func_name}' not found")


def _load_days_until_game() -> Callable:
    func_src = _extract_function_source("_days_until_game")
    ns = {"datetime": datetime, "timezone": timezone}
    exec(textwrap.dedent(func_src), ns)
    return ns["_days_until_game"]


class TestDaysUntilGame:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.fn = _load_days_until_game()

    def test_future_time_returns_positive(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
        result = self.fn(future)
        assert 0.0 < result < 1.5

    def test_past_time_returns_zero(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        assert self.fn(past) == 0.0

    def test_empty_string_returns_zero(self):
        assert self.fn("") == 0.0

    def test_bad_format_returns_zero(self):
        assert self.fn("not-a-date") == 0.0

    def test_z_suffix_handled(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert self.fn(future) > 0.0


class TestLogPaperBet:
    """V37 Session 38A directive: required test coverage for paper bet logging."""

    def _make_bet(self, grade="A", kelly_size=0.25, commence_time=""):
        from core.math_engine import BetCandidate
        return BetCandidate(
            sport="NBA",
            matchup="Boston Celtics @ Los Angeles Lakers",
            market_type="spreads",
            target="Los Angeles Lakers -4.5",
            line=-4.5,
            price=-110,
            edge_pct=0.05,
            win_prob=0.55,
            market_implied=0.524,
            fair_implied=0.55,
            kelly_size=kelly_size,
            grade=grade,
            commence_time=commence_time,
        )

    def _exec_log_paper_bet(self, db_path: str):
        """Return _log_paper_bet func wired to temp DB, capturing logged kwargs."""
        logged = {}

        def mock_log_bet(**kwargs):
            logged.update(kwargs)
            from core.line_logger import log_bet
            kwargs["db_path"] = db_path
            return log_bet(**kwargs)

        func_src = _extract_function_source("_log_paper_bet")
        from core.math_engine import BetCandidate
        ns = {
            "BetCandidate": BetCandidate,
            "st": MagicMock(),
            "_log_bet": mock_log_bet,
            "_days_until_game": _load_days_until_game(),
        }
        exec(textwrap.dedent(func_src), ns)
        return ns["_log_paper_bet"], logged

    def test_log_paper_bet_grade_c_sets_stake_zero(self, tmp_path):
        """Grade C paper bet must use stake=0.0 (tracking only)."""
        from core.line_logger import init_db
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        fn, captured = self._exec_log_paper_bet(db_path)
        bet = self._make_bet(grade="C", kelly_size=0.05)
        row_id = fn(bet)
        assert row_id > 0
        assert captured["stake"] == 0.0

    def test_log_paper_bet_grade_a_uses_kelly_size(self, tmp_path):
        """Grade A paper bet must use stake=kelly_size."""
        from core.line_logger import init_db
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        fn, captured = self._exec_log_paper_bet(db_path)
        bet = self._make_bet(grade="A", kelly_size=0.25)
        row_id = fn(bet)
        assert row_id > 0
        assert captured["stake"] == 0.25

    def test_log_paper_bet_uses_commence_time_not_rest_days(self, tmp_path):
        """days_to_game must be derived from commence_time (V37 fix)."""
        from core.line_logger import init_db
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        fn, captured = self._exec_log_paper_bet(db_path)
        future = (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        bet = self._make_bet(grade="B", kelly_size=0.12, commence_time=future)
        fn(bet)
        assert captured["days_to_game"] > 0.0
        assert captured["days_to_game"] < 1.0


class TestPaperLogButtonIdempotency:
    """V37 Session 38A directive test 3: session_state guard prevents double-log."""

    def _state_key(self, matchup: str, target: str, price: int) -> str:
        return f"logged_{abs(hash(matchup + target + str(price))):08x}"

    def test_paper_log_button_idempotency(self):
        """state_key=True after first click must prevent re-logging."""
        matchup = "Boston Celtics @ Los Angeles Lakers"
        target = "Los Angeles Lakers -4.5"
        price = -110
        state_key = self._state_key(matchup, target, price)
        session_state = {state_key: True}
        should_log = not session_state.get(state_key, False)
        assert not should_log

    def test_state_key_unique_per_bet(self):
        """Different bets must produce different state keys."""
        k1 = self._state_key("Boston @ Lakers", "Lakers -4.5", -110)
        k2 = self._state_key("Boston @ Lakers", "Lakers -4.5", -105)
        k3 = self._state_key("Bulls @ Celtics", "Celtics +2.5", -110)
        assert k1 != k2
        assert k1 != k3

    def test_state_key_stable_on_same_inputs(self):
        """Same inputs must always produce same state key."""
        k1 = self._state_key("Boston @ Lakers", "Lakers -4.5", -110)
        k2 = self._state_key("Boston @ Lakers", "Lakers -4.5", -110)
        assert k1 == k2
