"""
pages/01_live_lines.py — Live Lines Tab (Priority 2)

Full bet-ranking pipeline:
1. Fetch live odds from Odds API (all configured sports)
2. Parse each game through math_engine.parse_game_markets()
3. Apply collar, edge floor, book floor filters
4. Rank all candidates by edge% (globally across all sports)
5. Display ranked bets with full math breakdown

Design non-negotiables (inherited from V36.1, fixed bugs):
- No duplicate market sides (parse_game_markets deduplicates)
- Correct bet type filtering via collar (-180/+150)
- Edge threshold: 3.5% minimum
- Global ranking by edge%, not per-sport buckets
- No narrative — every displayed number shows its calculation
- Sharp Score displayed with component breakdown
- Kill switches suppress unsuitable bets (not just warn)

UI:
- Bet cards via st.html() with inline styles
- Sport filter + market filter in sidebar
- Auto-refresh toggle (st.empty + time.sleep for live mode)
- Graceful degradation: "No bets found" state with reason
"""

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.math_engine import (
    BetCandidate,
    MIN_EDGE,
    SHARP_THRESHOLD,
    parse_game_markets,
    sharp_to_size,
)
from core.odds_fetcher import fetch_batch_odds, quota

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SIZE_COLORS = {
    "NUCLEAR_2.0U": "#ef4444",   # red — max bet
    "STANDARD_1.0U": "#f59e0b",  # amber — normal
    "LEAN_0.5U": "#6b7280",      # gray — small
}
SIZE_LABELS = {
    "NUCLEAR_2.0U": "2.0u NUCLEAR",
    "STANDARD_1.0U": "1.0u STANDARD",
    "LEAN_0.5U": "0.5u LEAN",
}
MARKET_DISPLAY = {
    "spreads": "SPREAD",
    "totals": "TOTAL",
    "h2h": "ML",
}
SPORT_OPTIONS = ["All", "NBA", "NFL", "NCAAB", "MLB", "NHL", "Soccer"]


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _fetch_and_rank(sports_filter: str) -> tuple[list[BetCandidate], str, int]:
    """
    Fetch odds, parse all games, return ranked bet candidates.

    Returns:
        (candidates, error_message, quota_remaining)
        candidates is empty list on error or no data.
    """
    try:
        sports = None if sports_filter == "All" else [sports_filter]
        raw = fetch_batch_odds(sports=sports)
    except Exception as exc:
        return [], f"API error: {exc}", 0

    candidates: list[BetCandidate] = []
    for sport, games in raw.items():
        for game in games:
            try:
                bets = parse_game_markets(game, sport)
                candidates.extend(bets)
            except Exception:
                continue  # individual game parse failure doesn't crash the page

    # Sort globally by edge% descending
    candidates.sort(key=lambda b: b.edge_pct, reverse=True)

    remaining = quota.remaining if quota.remaining is not None else -1
    return candidates, "", remaining


# ---------------------------------------------------------------------------
# Bet card HTML
# ---------------------------------------------------------------------------
def _bet_card(bet: BetCandidate, rank: int) -> str:
    size_key = sharp_to_size(bet.sharp_score)
    size_color = SIZE_COLORS.get(size_key, "#6b7280")
    size_label = SIZE_LABELS.get(size_key, size_key)

    edge_pct = bet.edge_pct * 100
    kelly_pct = bet.kelly_size * 100
    win_pct = bet.win_prob * 100

    # Sharp score bar (0–100)
    sharp_bar_width = min(100, max(0, bet.sharp_score))
    sharp_color = "#22c55e" if bet.sharp_score >= SHARP_THRESHOLD else "#6b7280"

    # Market/sport badges
    mkt_display = MARKET_DISPLAY.get(bet.market_type, bet.market_type.upper())
    price_str = f"{bet.price:+d}" if bet.price > 0 else str(bet.price)

    # Line display (spread/total show value; ML shows nothing)
    line_html = ""
    if bet.market_type in ("spreads", "totals") and bet.line != 0:
        line_html = f'<div style="font-size:0.75rem; color:#9ca3af; margin-bottom:1px;">{bet.line:+.1f}</div>'

    # Kill reason warning
    kill_html = ""
    if bet.kill_reason:
        kill_html = f"""
        <div style="
            background:#1f1010; border:1px solid #7f1d1d;
            border-radius:4px; padding:4px 8px; margin-top:6px;
            font-size:0.65rem; color:#fca5a5;
        ">⚠ {bet.kill_reason}</div>
        """

    # Sharp score breakdown tooltip-style
    bd = bet.sharp_breakdown or {}
    breakdown_items = ""
    for label, val in [
        ("Edge", bd.get("edge_contribution", 0)),
        ("RLM", bd.get("rlm_contribution", 0)),
        ("Efficiency", bd.get("efficiency_contribution", 0)),
        ("Situational", bd.get("situational_contribution", 0)),
    ]:
        breakdown_items += f"""
        <span style="margin-right:10px; color:#6b7280;">
            {label}: <span style="color:#9ca3af;">{val:.0f}</span>
        </span>
        """

    return f"""
    <div style="
        background: #1a1d23;
        border: 1px solid #2d3139;
        border-left: 4px solid {size_color};
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
        position: relative;
    ">
        <!-- Header row -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div>
                <span style="
                    font-size:0.6rem; color:#6b7280;
                    letter-spacing:0.1em; font-weight:600;
                "># {rank} &nbsp;·&nbsp; {bet.sport.upper()} &nbsp;·&nbsp; {mkt_display}</span>
                <div style="
                    font-size:1.0rem; font-weight:700; color:#e5e7eb; margin-top:3px;
                ">{bet.target}</div>
                <div style="font-size:0.75rem; color:#9ca3af;">{bet.matchup}</div>
            </div>
            <div style="text-align:right;">
                {line_html}
                <div style="
                    font-size:1.3rem; font-weight:800; color:{size_color};
                ">{price_str}</div>
                <div style="
                    font-size:0.65rem; font-weight:600; color:{size_color};
                    letter-spacing:0.08em; margin-top:1px;
                ">{size_label}</div>
                <div style="font-size:0.65rem; color:#6b7280;">via {bet.book}</div>
            </div>
        </div>

        <!-- Math row -->
        <div style="
            display:grid; grid-template-columns:1fr 1fr 1fr 1fr;
            gap:8px; margin-bottom:10px;
        ">
            <div style="background:#0e1117; border-radius:4px; padding:6px 8px;">
                <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.08em;">EDGE</div>
                <div style="font-size:0.95rem; font-weight:700; color:#22c55e;">+{edge_pct:.1f}%</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:6px 8px;">
                <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.08em;">WIN PROB</div>
                <div style="font-size:0.95rem; font-weight:700; color:#e5e7eb;">{win_pct:.1f}%</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:6px 8px;">
                <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.08em;">KELLY</div>
                <div style="font-size:0.95rem; font-weight:700; color:#e5e7eb;">{kelly_pct:.1f}%</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:6px 8px;">
                <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.08em;">SHARP</div>
                <div style="font-size:0.95rem; font-weight:700; color:{sharp_color};">{bet.sharp_score:.0f}</div>
            </div>
        </div>

        <!-- Sharp Score bar -->
        <div style="margin-bottom:6px;">
            <div style="
                height:3px; background:#2d3139; border-radius:2px; overflow:hidden;
            ">
                <div style="
                    height:100%; width:{sharp_bar_width}%; background:{sharp_color};
                    border-radius:2px;
                "></div>
            </div>
            <div style="margin-top:3px; font-size:0.6rem;">
                {breakdown_items}
            </div>
        </div>

        {kill_html}
    </div>
    """


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("🔴 Live Lines")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">Global bet ranking by edge%. '
    f'Min edge: {MIN_EDGE*100:.1f}% | Collar: −180 to +150 | Kelly: 0.25×</span>',
    unsafe_allow_html=True,
)

# --- Filters ---
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 3])
with col_f1:
    sport_filter = st.selectbox("Sport", SPORT_OPTIONS, key="ll_sport")
with col_f2:
    market_options = ["All", "Spread", "Total", "Moneyline"]
    market_filter = st.selectbox("Market", market_options, key="ll_market")
with col_f3:
    min_sharp = st.slider("Min Sharp Score", 0, 100, 0, 5, key="ll_sharp")
with col_f4:
    auto_refresh = st.toggle("Auto-refresh (60s)", value=False, key="ll_auto")

st.markdown("---")

# --- Fetch & render ---
fetch_placeholder = st.empty()

def _render(sport_filter: str, market_filter: str, min_sharp: int) -> None:
    with fetch_placeholder.container():
        with st.spinner("Fetching odds..."):
            candidates, error, remaining = _fetch_and_rank(sport_filter)

        if error:
            st.error(error)
            return

        # Market filter
        mkt_key_map = {"Spread": "spreads", "Total": "totals", "Moneyline": "h2h"}
        if market_filter != "All":
            mkt_key = mkt_key_map.get(market_filter, "")
            candidates = [c for c in candidates if c.market_type == mkt_key]

        # Sharp score filter
        if min_sharp > 0:
            candidates = [c for c in candidates if c.sharp_score >= min_sharp]

        # Stats row
        n_total = len(candidates)
        n_nuclear = sum(1 for c in candidates if sharp_to_size(c.sharp_score) == "NUCLEAR_2.0U")
        n_standard = sum(1 for c in candidates if sharp_to_size(c.sharp_score) == "STANDARD_1.0U")
        n_lean = sum(1 for c in candidates if sharp_to_size(c.sharp_score) == "LEAN_0.5U")

        s_col1, s_col2, s_col3, s_col4, s_col5 = st.columns(5)
        with s_col1:
            st.metric("Total Bets", n_total)
        with s_col2:
            st.metric("Nuclear (2u)", n_nuclear, delta=None)
        with s_col3:
            st.metric("Standard (1u)", n_standard, delta=None)
        with s_col4:
            st.metric("Lean (0.5u)", n_lean, delta=None)
        with s_col5:
            remaining_str = str(remaining) if remaining >= 0 else "—"
            st.metric("API Quota Left", remaining_str)

        st.markdown("---")

        if not candidates:
            st.html(
                """
                <div style="
                    background: #1a1d23;
                    border: 1px solid #2d3139;
                    border-radius: 6px;
                    padding: 40px 20px;
                    text-align: center;
                    color: #6b7280;
                ">
                    <div style="font-size:2rem; margin-bottom:12px;">—</div>
                    <div style="font-size:0.9rem; font-weight:600; color:#9ca3af; margin-bottom:6px;">
                        No qualifying bets found
                    </div>
                    <div style="font-size:0.75rem; line-height:1.6;">
                        All candidates failed edge ≥3.5%, collar (−180/+150),
                        or min-books (≥2) filters.<br>
                        Check: API key configured? ODDS_API_KEY in environment?
                    </div>
                </div>
                """
            )
            return

        # Render cards
        for rank, bet in enumerate(candidates, start=1):
            st.html(_bet_card(bet, rank))

            # Full math expander — no narrative, numbers only
            with st.expander(f"Math breakdown — {bet.target} {bet.matchup[:30]}", expanded=False):
                mc1, mc2 = st.columns(2)
                with mc1:
                    st.markdown(
                        f"""
                        **Edge calculation**
                        - Model win prob: `{bet.win_prob*100:.2f}%`
                        - Market implied: `{bet.market_implied*100:.2f}%`
                        - Fair (no-vig): `{bet.fair_implied*100:.2f}%`
                        - Edge: `{bet.win_prob*100:.2f}% − {bet.market_implied*100:.2f}% = {bet.edge_pct*100:.2f}%`
                        """
                    )
                with mc2:
                    st.markdown(
                        f"""
                        **Kelly sizing (0.25×)**
                        - Win prob: `{bet.win_prob:.4f}`
                        - Price: `{bet.price:+d}` American
                        - Full Kelly: `{bet.kelly_size/0.25:.4f}` → ×0.25 = `{bet.kelly_size:.4f}`
                        - Bet size: `{bet.kelly_size*100:.2f}%` of bankroll

                        **Sharp Score: `{bet.sharp_score:.1f}` / 100**
                        """
                    )

                if bet.kill_reason:
                    st.warning(f"Kill switch active: {bet.kill_reason}")

                if bet.signal:
                    st.info(f"Signal: {bet.signal}")


_render(sport_filter, market_filter, min_sharp)

# Auto-refresh loop
if auto_refresh:
    time.sleep(60)
    st.cache_data.clear()
    st.rerun()
