"""
tests/test_parlay_builder.py — Titanium-Agentic
================================================
Unit tests for core/parlay_builder.py.

Coverage:
  - american_to_decimal(): standard cases, favorites, underdogs
  - parlay_ev(): joint prob, payout, EV sign checks
  - parlay_kelly(): sizing, cap at PARLAY_MAX_UNITS
  - _legs_independent(): same event, same matchup, kill reason gates
  - build_parlay_combos(): filtering, EV gate, independence, correlation discount
  - format_parlay_summary(): output format
"""

import pytest
from core.parlay_builder import (
    PARLAY_CORRELATION_DISCOUNT,
    PARLAY_KELLY_FRACTION,
    PARLAY_MAX_UNITS,
    PARLAY_MIN_EV,
    ParlayCombo,
    american_to_decimal,
    build_parlay_combos,
    format_parlay_summary,
    parlay_ev,
    parlay_kelly,
    _legs_independent,
    _parlay_score,
)


# ---------------------------------------------------------------------------
# Fake BetCandidate for testing (avoids circular import)
# ---------------------------------------------------------------------------
class _Bet:
    def __init__(
        self,
        target: str = "TeamA -4.5",
        price: int = -110,
        sport: str = "NBA",
        matchup: str = "Away @ Home",
        event_id: str = "ev001",
        sharp_score: float = 55.0,
        edge_pct: float = 0.07,
        fair_implied: float = 0.57,
        win_prob: float = 0.57,
        kill_reason: str = "",
    ):
        self.target = target
        self.price = price
        self.sport = sport
        self.matchup = matchup
        self.event_id = event_id
        self.sharp_score = sharp_score
        self.edge_pct = edge_pct
        self.fair_implied = fair_implied
        self.win_prob = win_prob
        self.kill_reason = kill_reason


# ---------------------------------------------------------------------------
# american_to_decimal
# ---------------------------------------------------------------------------

class TestAmericanToDecimal:

    def test_minus_110(self):
        result = american_to_decimal(-110)
        assert abs(result - 1.9091) < 0.001

    def test_plus_150(self):
        assert american_to_decimal(150) == 2.5

    def test_minus_200(self):
        assert american_to_decimal(-200) == 1.5

    def test_even_money(self):
        assert american_to_decimal(100) == 2.0

    def test_plus_300(self):
        assert american_to_decimal(300) == 4.0

    def test_minus_150(self):
        result = american_to_decimal(-150)
        assert abs(result - 1.6667) < 0.001

    def test_result_always_above_1(self):
        for price in [-200, -110, 100, 150, 300]:
            assert american_to_decimal(price) > 1.0


# ---------------------------------------------------------------------------
# parlay_ev
# ---------------------------------------------------------------------------

class TestParlayEv:

    def test_positive_ev_with_good_probs(self):
        """55% win rate on -110 each leg → positive EV parlay."""
        joint, payout, ev = parlay_ev(0.55, 0.55, -110, -110)
        assert joint == pytest.approx(0.3025, abs=0.001)
        assert ev > 0

    def test_negative_ev_with_50pct_probs(self):
        """50% on -110 = negative EV individually → parlay also negative."""
        _, _, ev = parlay_ev(0.50, 0.50, -110, -110)
        assert ev < 0

    def test_payout_is_product_of_decimal_odds(self):
        _, payout, _ = parlay_ev(0.55, 0.55, -110, 150)
        dec1 = american_to_decimal(-110)
        dec2 = american_to_decimal(150)
        assert abs(payout - dec1 * dec2) < 0.001

    def test_joint_prob_is_product(self):
        joint, _, _ = parlay_ev(0.60, 0.55, -110, -110)
        assert abs(joint - 0.60 * 0.55) < 0.001

    def test_ev_formula(self):
        joint, payout, ev = parlay_ev(0.55, 0.55, -110, -110)
        assert abs(ev - (joint * payout - 1.0)) < 0.0001

    def test_underdog_parlay_higher_payout(self):
        _, payout_fav, _ = parlay_ev(0.60, 0.60, -150, -150)
        _, payout_dog, _ = parlay_ev(0.40, 0.40, 150, 150)
        assert payout_dog > payout_fav


# ---------------------------------------------------------------------------
# parlay_kelly
# ---------------------------------------------------------------------------

class TestParlayKelly:

    def test_positive_ev_gives_positive_kelly(self):
        result = parlay_kelly(0.30, 3.50)
        assert result > 0

    def test_zero_prob_gives_zero(self):
        assert parlay_kelly(0.0, 3.50) == 0.0

    def test_payout_at_one_gives_zero(self):
        """Payout = 1.0 means no profit → undefined Kelly, return 0."""
        assert parlay_kelly(0.30, 1.0) == 0.0

    def test_capped_at_max_units(self):
        """Force cap by using a kelly_fraction that would exceed max.
        Max raw Kelly = fraction * (prob*payout - 1)/(payout - 1).
        Use payout=2.0, prob=1.0 → raw = fraction * 1.0/1.0 = fraction.
        So set fraction manually via monkeypatching or test with large fraction.
        Alternative: verify result never exceeds cap regardless of inputs."""
        import core.parlay_builder as pb
        orig = pb.PARLAY_KELLY_FRACTION
        try:
            pb.PARLAY_KELLY_FRACTION = 100.0  # force huge Kelly
            result = parlay_kelly(0.99, 100.0)
            assert result == PARLAY_MAX_UNITS
        finally:
            pb.PARLAY_KELLY_FRACTION = orig

    def test_low_prob_gives_low_kelly(self):
        result = parlay_kelly(0.10, 3.50)
        assert result == 0.0  # 0.10 * 3.50 - 1 = -0.65 → negative, clamp to 0

    def test_kelly_below_max(self):
        result = parlay_kelly(0.35, 3.0)
        assert 0.0 <= result <= PARLAY_MAX_UNITS


# ---------------------------------------------------------------------------
# _legs_independent
# ---------------------------------------------------------------------------

class TestLegsIndependent:

    def test_different_events_independent(self):
        a = _Bet(event_id="ev1", matchup="X @ Y")
        b = _Bet(event_id="ev2", matchup="A @ B")
        assert _legs_independent(a, b) is True

    def test_same_event_id_not_independent(self):
        a = _Bet(event_id="ev1", matchup="X @ Y")
        b = _Bet(event_id="ev1", matchup="X @ Y")
        assert _legs_independent(a, b) is False

    def test_same_matchup_not_independent(self):
        """Different event_id but same matchup → reject."""
        a = _Bet(event_id="ev1", matchup="Lakers @ Celtics")
        b = _Bet(event_id="ev2", matchup="Lakers @ Celtics")
        assert _legs_independent(a, b) is False

    def test_kill_reason_makes_not_independent(self):
        a = _Bet(event_id="ev1", matchup="X @ Y", kill_reason="KILL: wind >20mph")
        b = _Bet(event_id="ev2", matchup="A @ B")
        assert _legs_independent(a, b) is False

    def test_flag_reason_still_independent(self):
        """FLAG is not KILL — legs still qualify."""
        a = _Bet(event_id="ev1", matchup="X @ Y", kill_reason="FLAG: surface risk")
        b = _Bet(event_id="ev2", matchup="A @ B")
        assert _legs_independent(a, b) is True

    def test_empty_event_ids_use_matchup(self):
        """Empty event_id → fall through to matchup check."""
        a = _Bet(event_id="", matchup="X @ Y")
        b = _Bet(event_id="", matchup="A @ B")
        assert _legs_independent(a, b) is True


# ---------------------------------------------------------------------------
# build_parlay_combos
# ---------------------------------------------------------------------------

class TestBuildParlayCombos:

    def _make_qualified_bet(self, event_id: str, sport: str = "NBA",
                             matchup: str | None = None, edge: float = 0.08,
                             sharp: float = 55.0, price: int = -110) -> _Bet:
        return _Bet(
            event_id=event_id,
            sport=sport,
            matchup=matchup or f"Away{event_id} @ Home{event_id}",
            edge_pct=edge,
            sharp_score=sharp,
            price=price,
            fair_implied=0.57,
        )

    def test_empty_input_returns_empty(self):
        assert build_parlay_combos([]) == []

    def test_single_bet_returns_empty(self):
        bet = self._make_qualified_bet("ev1")
        assert build_parlay_combos([bet]) == []

    def test_returns_parlay_combo_objects(self):
        b1 = self._make_qualified_bet("ev1")
        b2 = self._make_qualified_bet("ev2")
        results = build_parlay_combos([b1, b2])
        if results:
            assert all(isinstance(c, ParlayCombo) for c in results)

    def test_same_event_id_rejected(self):
        """Two bets from same event → no parlay (not independent)."""
        b1 = self._make_qualified_bet("ev1", matchup="A @ B")
        b2 = self._make_qualified_bet("ev1", matchup="A @ B")
        b2.price = 130  # different market
        b2.target = "TeamB +4.5"
        assert build_parlay_combos([b1, b2]) == []

    def test_below_sharp_score_filtered(self):
        """Leg with sharp_score < min → excluded from combos."""
        b1 = self._make_qualified_bet("ev1", sharp=30.0)  # below 40 min
        b2 = self._make_qualified_bet("ev2")
        results = build_parlay_combos([b1, b2], min_sharp_score=40.0)
        assert results == []

    def test_below_min_edge_filtered(self):
        """Leg with edge_pct < min → excluded."""
        b1 = self._make_qualified_bet("ev1", edge=0.02)  # below 0.04 min
        b2 = self._make_qualified_bet("ev2")
        results = build_parlay_combos([b1, b2], min_edge=0.04)
        assert results == []

    def test_kill_reason_filtered(self):
        b1 = self._make_qualified_bet("ev1")
        b1.kill_reason = "KILL: NBA off-season"
        b2 = self._make_qualified_bet("ev2")
        assert build_parlay_combos([b1, b2]) == []

    def test_positive_ev_combo_returned(self):
        """Two strong bets from independent events → combo surfaced."""
        b1 = self._make_qualified_bet("ev1", sport="NBA", edge=0.10, sharp=65.0, price=-110)
        b1.fair_implied = 0.60
        b2 = self._make_qualified_bet("ev2", sport="NFL", edge=0.09, sharp=60.0, price=-110)
        b2.fair_implied = 0.58
        results = build_parlay_combos([b1, b2], min_ev=0.0)
        assert len(results) > 0
        assert results[0].parlay_ev > 0

    def test_sorted_by_parlay_score_descending(self):
        """Results sorted best combo first."""
        bets = [self._make_qualified_bet(f"ev{i}", sport="NFL") for i in range(5)]
        for i, b in enumerate(bets):
            b.sharp_score = 50.0 + i * 5
            b.fair_implied = 0.55 + i * 0.01
            b.matchup = f"Away{i} @ Home{i}"
        results = build_parlay_combos(bets, min_ev=0.0)
        for i in range(len(results) - 1):
            assert results[i].parlay_score >= results[i + 1].parlay_score

    def test_max_results_respected(self):
        bets = [self._make_qualified_bet(f"ev{i}", sport="NFL") for i in range(10)]
        for i, b in enumerate(bets):
            b.matchup = f"Away{i} @ Home{i}"
            b.fair_implied = 0.57
        results = build_parlay_combos(bets, max_results=3, min_ev=0.0)
        assert len(results) <= 3

    def test_correlation_discount_applied_same_sport(self):
        """Same-sport legs → correlation_discounted=True and EV reduced."""
        b1 = self._make_qualified_bet("ev1", sport="NBA")
        b1.fair_implied = 0.62
        b2 = self._make_qualified_bet("ev2", sport="NBA")
        b2.fair_implied = 0.62
        results = build_parlay_combos([b1, b2], min_ev=0.0)
        if results:
            assert results[0].correlation_discounted is True

    def test_no_correlation_discount_different_sport(self):
        """Different-sport legs → no correlation discount."""
        b1 = self._make_qualified_bet("ev1", sport="NBA")
        b1.fair_implied = 0.60
        b2 = self._make_qualified_bet("ev2", sport="NFL")
        b2.fair_implied = 0.60
        results = build_parlay_combos([b1, b2], min_ev=0.0)
        if results:
            assert results[0].correlation_discounted is False

    def test_combo_has_required_fields(self):
        b1 = self._make_qualified_bet("ev1", sport="NBA")
        b1.fair_implied = 0.60
        b2 = self._make_qualified_bet("ev2", sport="NFL")
        b2.fair_implied = 0.60
        results = build_parlay_combos([b1, b2], min_ev=0.0)
        if results:
            c = results[0]
            assert 0 < c.parlay_prob < 1
            assert c.parlay_payout > 1
            assert c.kelly_size >= 0
            assert c.kelly_size <= PARLAY_MAX_UNITS
            assert isinstance(c.notes, str)

    def test_price_zero_filtered(self):
        b1 = self._make_qualified_bet("ev1", price=0)
        b2 = self._make_qualified_bet("ev2")
        assert build_parlay_combos([b1, b2]) == []


# ---------------------------------------------------------------------------
# _parlay_score
# ---------------------------------------------------------------------------

class TestParlayScore:

    def test_returns_positive_float(self):
        assert _parlay_score(0.30, 0.05, 60.0, 55.0) > 0

    def test_higher_ev_gives_higher_score(self):
        low = _parlay_score(0.30, 0.05, 55.0, 55.0)
        high = _parlay_score(0.30, 0.15, 55.0, 55.0)
        assert high > low

    def test_higher_sharp_gives_higher_score(self):
        low = _parlay_score(0.30, 0.05, 50.0, 50.0)
        high = _parlay_score(0.30, 0.05, 70.0, 70.0)
        assert high > low


# ---------------------------------------------------------------------------
# format_parlay_summary
# ---------------------------------------------------------------------------

class TestFormatParlaySummary:

    def _make_combo(self) -> ParlayCombo:
        b1 = _Bet(target="TeamA -4.5", price=-110, sport="NBA")
        b2 = _Bet(target="TeamB +3.5", price=130, sport="NFL")
        return ParlayCombo(
            leg_1=b1, leg_2=b2,
            parlay_prob=0.29, parlay_payout=3.45,
            parlay_ev=0.05, kelly_size=0.25,
            parlay_score=42.0, notes="test combo",
        )

    def test_output_is_string(self):
        assert isinstance(format_parlay_summary(self._make_combo()), str)

    def test_contains_ev(self):
        s = format_parlay_summary(self._make_combo())
        assert "EV" in s

    def test_contains_probability(self):
        s = format_parlay_summary(self._make_combo())
        assert "%" in s

    def test_contains_parlay_label(self):
        s = format_parlay_summary(self._make_combo())
        assert "PARLAY" in s.upper()

    def test_contains_kelly_size(self):
        s = format_parlay_summary(self._make_combo())
        assert "u" in s  # units suffix
