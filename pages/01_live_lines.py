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

import html as _html
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
DB_PATH = str(ROOT / "data" / "line_history.db")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.efficiency_feed import get_efficiency_gap
from core.nba_pdo import get_all_pdo_data
from core.king_of_the_court import (
    rank_kotc_candidates,
    format_kotc_summary,
    is_kotc_eligible_day,
)
from core.injury_data import (
    injury_kill_switch,
    list_high_leverage_positions,
    evaluate_injury_impact,
)
from core.line_logger import log_bet as _log_bet
from core.math_engine import (
    BetCandidate,
    MIN_EDGE,
    GRADE_B_MIN_EDGE,
    GRADE_C_MIN_EDGE,
    NEAR_MISS_MIN_EDGE,
    KELLY_FRACTION,
    KELLY_FRACTION_B,
    KELLY_FRACTION_C,
    SHARP_THRESHOLD,
    assign_grade,
    parse_game_markets,
    sharp_to_size,
)
from core.odds_fetcher import fetch_batch_odds, quota, compute_rest_days_from_schedule
from core.weather_feed import get_stadium_wind
from core.originator_engine import (
    efficiency_gap_to_margin,
    run_trinity_simulation,
)
from core.parlay_builder import (
    build_parlay_combos,
    format_parlay_summary,
    ParlayCombo,
    PARLAY_MAX_UNITS,
)

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
SPORT_OPTIONS = ["All", "NBA", "NFL", "NCAAB", "MLB", "NHL", "Soccer", "Tennis"]

# Grade display config — border color + banner text per tier
# Grade A (≥3.5%): amber — full stake (existing behaviour, unchanged)
# Grade B (≥1.5%): blue  — reduced stake recommended
# Grade C (≥0.5%): slate — tracking/data only, $0 stake
# Near-Miss (≥-1%): dark  — market transparency, never bet
GRADE_COLORS = {
    "A":         "#f59e0b",  # amber
    "B":         "#3b82f6",  # blue
    "C":         "#6b7280",  # slate
    "NEAR_MISS": "#374151",  # dark
}
GRADE_BANNER = {
    "B": ("🔵 GRADE B — MODERATE VALUE",
          f"Edge ≥1.5% but below standard 3.5%. Positive EV — reduced stake recommended "
          f"(~0.12× Kelly). Log and track. May bet at your discretion."),
    "C": ("🟡 GRADE C — TRACKING ONLY",
          f"Edge ≥0.5%. Positive EV but thin. Log with stake=$0 for data collection."),
    "NEAR_MISS": ("📊 MARKET DATA — No positive edge found",
                  "Showing top near-miss candidates for transparency. These are NOT bets."),
}


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(raw: dict, min_edge: float = NEAR_MISS_MIN_EDGE) -> list[BetCandidate]:
    """
    Process raw Odds API game dict into graded BetCandidates. Zero API calls.

    Always runs at NEAR_MISS_MIN_EDGE (-1%) to capture ALL candidates for
    tiered display. Grades are assigned after parsing:
        A (≥3.5%) → full stake  |  B (≥1.5%) → reduced stake
        C (≥0.5%) → track only  |  NEAR_MISS (≥-1%) → no stake / market data

    The caller filters by grade for display. Passing a custom min_edge overrides
    (used in tests; production always uses NEAR_MISS_MIN_EDGE for full capture).

    Args:
        raw:      Dict from fetch_batch_odds() — {sport_key: [game_dicts]}
        min_edge: Edge floor (default: NEAR_MISS_MIN_EDGE).
    Returns:
        BetCandidates sorted by (grade A→NEAR_MISS, then sharp_score descending).
    """
    candidates: list[BetCandidate] = []
    for sport_key, games in raw.items():
        is_tennis = sport_key.startswith("tennis_atp") or sport_key.startswith("tennis_wta")
        if is_tennis:
            sport_label = "TENNIS_ATP" if "atp" in sport_key else "TENNIS_WTA"
            t_sport_key = sport_key
        else:
            sport_label = sport_key
            t_sport_key = ""

        rest_days_map: dict | None = None
        if sport_key == "NBA" and games:
            try:
                rest_days_map = compute_rest_days_from_schedule(games)
            except Exception:
                rest_days_map = None

        nba_pdo_data: dict | None = None
        if sport_key == "NBA":
            try:
                nba_pdo_data = get_all_pdo_data() or None
            except Exception:
                nba_pdo_data = None

        is_nfl_sport = sport_key == "NFL"

        for game in games:
            try:
                home = game.get("home_team", "")
                away = game.get("away_team", "")
                eff_gap = get_efficiency_gap(home, away)
                game_pdo: dict | None = None
                if nba_pdo_data and home and away:
                    game_pdo = {
                        k: v for k, v in nba_pdo_data.items()
                        if k in (home, away)
                    } or None
                wind = 0.0
                if is_nfl_sport:
                    try:
                        wind = get_stadium_wind(home, game.get("commence_time", ""))
                    except Exception:
                        wind = 0.0
                bets = parse_game_markets(
                    game,
                    sport_label,
                    efficiency_gap=eff_gap,
                    tennis_sport_key=t_sport_key,
                    rest_days=rest_days_map,
                    wind_mph=wind,
                    nba_pdo=game_pdo,
                    min_edge=min_edge,
                )
                sport_upper = sport_label.upper().replace("TENNIS_ATP", "NBA").replace("TENNIS_WTA", "NBA")
                proj_margin = efficiency_gap_to_margin(eff_gap)
                for bet in bets:
                    try:
                        total_arg = bet.line if bet.market_type == "totals" else None
                        spread_line = bet.line if bet.market_type == "spreads" else 0.0
                        sim = run_trinity_simulation(
                            mean=proj_margin,
                            sport=sport_upper,
                            line=spread_line,
                            total_line=total_arg,
                            iterations=2_000,
                            seed=42,
                        )
                        bet.signal = (bet.signal or "") + f" | Trinity cover={sim.cover_probability*100:.0f}%"
                        if bet.market_type == "totals" and sim.over_probability > 0:
                            bet.signal = (bet.signal or "") + f" over={sim.over_probability*100:.0f}%"
                    except Exception:
                        pass
                candidates.extend(bets)
            except Exception:
                continue

    # Assign grade + scale kelly for each candidate (math_engine.assign_grade)
    for bet in candidates:
        assign_grade(bet)

    # Sort: Grade A first, then B, C, NEAR_MISS; within each grade by sharp_score desc
    _grade_order = {"A": 0, "B": 1, "C": 2, "NEAR_MISS": 3, "": 4}
    candidates.sort(key=lambda b: (_grade_order.get(b.grade, 4), -b.sharp_score))
    return candidates


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_and_rank(sports_filter: str) -> tuple[list[BetCandidate], str, int]:
    """
    Fetch odds, parse all games through the full tiered pipeline.

    Returns candidates at ALL grade tiers (A/B/C/NEAR_MISS) — the caller
    filters by grade for display. No separate DC fallback call needed.

    Returns:
        (candidates, error_message, quota_remaining)
    """
    try:
        if sports_filter == "Tennis":
            raw = fetch_batch_odds(sports=[], include_tennis=True)
        elif sports_filter == "All":
            raw = fetch_batch_odds(sports=None, include_tennis=True)
        else:
            raw = fetch_batch_odds(sports=[sports_filter], include_tennis=False)
    except Exception as exc:
        return [], f"API error: {exc}", 0

    candidates = _run_pipeline(raw)  # always uses NEAR_MISS_MIN_EDGE — all grades captured
    remaining = quota.remaining if quota.remaining is not None else -1
    return candidates, "", remaining


# ---------------------------------------------------------------------------
# Bet card HTML
# ---------------------------------------------------------------------------
def _bet_card(bet: BetCandidate, rank: int) -> str:
    size_key = sharp_to_size(bet.sharp_score)
    size_color = SIZE_COLORS.get(size_key, "#6b7280")
    size_label = SIZE_LABELS.get(size_key, size_key)

    # Grade-aware styling
    grade = bet.grade or "A"
    grade_color = GRADE_COLORS.get(grade, "#6b7280")
    # For non-A grades, override the left border with grade color
    left_border_color = grade_color if grade != "A" else size_color
    card_opacity = "0.65" if grade == "NEAR_MISS" else "1.0"

    # Grade pill — only shown for B / C / NEAR_MISS
    grade_pill_html = ""
    if grade == "B":
        grade_pill_html = (
            '<span style="display:inline-block;background:#1e3a5f;color:#60a5fa;'
            'border:1px solid #2563eb;border-radius:3px;padding:1px 6px;'
            'font-size:0.55rem;font-weight:700;letter-spacing:0.1em;margin-left:6px;">'
            '▼ B · MODERATE VALUE</span>'
        )
    elif grade == "C":
        grade_pill_html = (
            '<span style="display:inline-block;background:#1f2937;color:#9ca3af;'
            'border:1px solid #4b5563;border-radius:3px;padding:1px 6px;'
            'font-size:0.55rem;font-weight:700;letter-spacing:0.1em;margin-left:6px;">'
            '▼ C · TRACKING ONLY</span>'
        )
    elif grade == "NEAR_MISS":
        grade_pill_html = (
            '<span style="display:inline-block;background:#111827;color:#6b7280;'
            'border:1px solid #374151;border-radius:3px;padding:1px 6px;'
            'font-size:0.55rem;font-weight:700;letter-spacing:0.1em;margin-left:6px;">'
            '⊘ NEAR MISS</span>'
        )

    edge_pct = bet.edge_pct * 100
    kelly_pct = bet.kelly_size * 100
    win_pct = bet.win_prob * 100
    edge_color = "#22c55e" if edge_pct >= 3.5 else ("#60a5fa" if edge_pct >= 1.5 else ("#9ca3af" if edge_pct >= 0.5 else "#6b7280"))

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

    # Escape any external/API strings before HTML interpolation
    _target  = _html.escape(str(bet.target or ""))
    _matchup = _html.escape(str(bet.matchup or ""))
    _sport   = _html.escape(str(bet.sport or "").upper())

    # Kill reason warning
    kill_html = ""
    if bet.kill_reason:
        kill_html = f"""
        <div style="
            background:#1f1010; border:1px solid #7f1d1d;
            border-radius:4px; padding:4px 8px; margin-top:6px;
            font-size:0.65rem; color:#fca5a5;
        ">⚠ {_html.escape(str(bet.kill_reason))}</div>
        """

    # Sharp score breakdown tooltip-style
    bd = bet.sharp_breakdown or {}
    breakdown_items = ""
    for label, val in [
        ("Edge", bd.get("edge", 0)),
        ("RLM", bd.get("rlm", 0)),
        ("Efficiency", bd.get("efficiency", 0)),
        ("Situational", bd.get("situational", 0)),
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
        border-left: 4px solid {left_border_color};
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
        position: relative;
        opacity: {card_opacity};
    ">
        <!-- Header row -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div>
                <span style="
                    font-size:0.6rem; color:#6b7280;
                    letter-spacing:0.1em; font-weight:600;
                "># {rank} &nbsp;·&nbsp; {_sport} &nbsp;·&nbsp; {mkt_display}</span>{grade_pill_html}
                <div style="
                    font-size:1.0rem; font-weight:700; color:#e5e7eb; margin-top:3px;
                ">{_target}</div>
                <div style="font-size:0.75rem; color:#9ca3af;">{_matchup}</div>
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
                <div style="font-size:0.95rem; font-weight:700; color:{edge_color};">{edge_pct:+.1f}%</div>
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
# Parlay card HTML
# ---------------------------------------------------------------------------
def _parlay_card(combo: ParlayCombo, rank: int) -> str:
    ev_pct = combo.parlay_ev * 100
    prob_pct = combo.parlay_prob * 100
    ev_color = "#22c55e" if combo.parlay_ev > 0 else "#ef4444"
    discount_badge = ""
    if combo.correlation_discounted:
        discount_badge = (
            '<span style="font-size:0.6rem; color:#f59e0b; '
            'margin-left:6px; letter-spacing:0.08em;">SAME-SPORT DISC</span>'
        )
    return f"""
    <div style="
        background: #13161d;
        border: 1px solid #2d3139;
        border-left: 4px solid #8b5cf6;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div>
                <span style="font-size:0.6rem; color:#8b5cf6; letter-spacing:0.1em; font-weight:700;">
                    PARLAY #{rank}
                </span>{discount_badge}
                <div style="font-size:0.9rem; font-weight:700; color:#e5e7eb; margin-top:3px;">
                    {combo.leg_1.target} &nbsp;+&nbsp; {combo.leg_2.target}
                </div>
                <div style="font-size:0.7rem; color:#6b7280; margin-top:1px;">
                    {combo.leg_1.sport.upper()} · {combo.leg_1.matchup} &nbsp;|&nbsp;
                    {combo.leg_2.sport.upper()} · {combo.leg_2.matchup}
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:1.1rem; font-weight:800; color:{ev_color};">
                    EV {ev_pct:+.1f}%
                </div>
                <div style="font-size:0.7rem; color:#9ca3af;">{combo.kelly_size:.2f}u</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px;">
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">JOINT PROB</div>
                <div style="font-size:0.9rem; font-weight:700; color:#e5e7eb;">{prob_pct:.1f}%</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">PAYOUT</div>
                <div style="font-size:0.9rem; font-weight:700; color:#e5e7eb;">{combo.parlay_payout:.2f}×</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">SCORE</div>
                <div style="font-size:0.9rem; font-weight:700; color:#8b5cf6;">{combo.parlay_score:.1f}</div>
            </div>
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("🔴 Live Lines")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">Global bet ranking by edge%. '
    f'Grade A ≥{MIN_EDGE*100:.1f}% (0.25×K) &nbsp;·&nbsp; '
    f'B ≥{GRADE_B_MIN_EDGE*100:.1f}% (0.12×K) &nbsp;·&nbsp; '
    f'C ≥{GRADE_C_MIN_EDGE*100:.1f}% (track) &nbsp;·&nbsp; '
    'Collar: −180/+150 | Kelly 0.25×</span>',
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

# --- Injury Alert (sidebar input — static model, user is data source) ---
with st.sidebar:
    st.markdown("### ⚠️ Injury Alert")
    st.caption("Static model — no live feed. You enter known absences.")
    with st.expander("Add injury", expanded=False):
        inj_sport = st.selectbox(
            "Sport", ["NBA", "NFL", "NHL", "MLB", "Soccer"], key="inj_sport"
        )
        # Show high-leverage positions for selected sport
        _high_lev = list_high_leverage_positions(inj_sport, min_leverage=2.0)
        _pos_options = [p for p, _, _ in _high_lev] if _high_lev else ["QB", "PG", "G"]
        inj_position = st.selectbox("Position", _pos_options, key="inj_pos")
        inj_team_side = st.radio("Injured team", ["home", "away"], key="inj_side")
        inj_market = st.radio("Bet market", ["spreads", "h2h", "totals"], key="inj_market")
        inj_active = st.toggle("Apply injury gate", value=False, key="inj_active")
        if inj_active:
            _lev = next((l for p, l, _ in _high_lev if p == inj_position), 0.0)
            st.caption(f"Expected line shift: **{_lev:.1f} pts** · threshold KILL ≥ 3.5 pts")

# --- King of the Court (Tuesday only) ---
if is_kotc_eligible_day():
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 👑 King of the Court")
        st.caption("DraftKings Tuesday promo — highest PRA wins $2M prize pool.")
        with st.expander("KOTC Picks (tonight)", expanded=True):
            _kotc_outs_raw = st.text_input(
                "Confirmed DNPs (comma-separated)",
                value="",
                key="kotc_outs",
                placeholder="Jaylen Brown, Joel Embiid",
            )
            _kotc_outs = {
                name.strip() for name in _kotc_outs_raw.split(",") if name.strip()
            }
            _kotc_star_outs_raw = st.text_input(
                "Star-teammate DNPs (boosts others)",
                value="",
                key="kotc_star_outs",
                placeholder="Jayson Tatum (BOS)",
            )
            # Parse "Player Name (TEAM)" format
            _kotc_star_outs: dict[str, str] = {}
            for entry in _kotc_star_outs_raw.split(","):
                entry = entry.strip()
                if "(" in entry and entry.endswith(")"):
                    pname, team = entry[:-1].rsplit("(", 1)
                    _kotc_star_outs[pname.strip()] = team.strip()

            # Use tonight's full NBA slate — all 30 teams (scheduler has live games;
            # for sidebar we provide all known NBA team abbrevs as fallback)
            _NBA_ALL_TEAMS = [
                "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN",
                "DET", "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA",
                "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX",
                "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
            ]

            try:
                _kotc_candidates = rank_kotc_candidates(
                    _NBA_ALL_TEAMS,
                    injury_outs=_kotc_outs,
                    star_outs=_kotc_star_outs if _kotc_star_outs else None,
                )
            except Exception as _exc:
                _kotc_candidates = []

            if not _kotc_candidates:
                st.caption("No KOTC candidates found.")
            else:
                for _rank, _c in enumerate(_kotc_candidates[:3], 1):
                    _badge = "🥇" if _rank == 1 else ("🥈" if _rank == 2 else "🥉")
                    _td_flag = " ★TD" if _c.triple_double_threat else ""
                    _exp_flag = " ↑" if _c.role_expansion else ""
                    st.html(
                        f"""
                        <div style="background:#1a1d23;border:1px solid #2d3139;
                                    border-left:3px solid #f59e0b;border-radius:6px;
                                    padding:8px 10px;margin:4px 0;">
                          <div style="font-size:13px;font-weight:700;color:#f3f4f6;">
                            {_badge} {_c.player_name}{_td_flag}{_exp_flag}
                            <span style="color:#6b7280;font-weight:400;font-size:11px;">
                              ({_c.team} {_c.position})
                            </span>
                          </div>
                          <div style="font-size:11px;color:#9ca3af;margin-top:2px;">
                            KOTC Score <b style="color:#f59e0b">{_c.kotc_score:.0f}</b>
                            &nbsp;·&nbsp;Proj PRA <b style="color:#22c55e">{_c.pra_projection:.1f}</b>
                            &nbsp;·&nbsp;Ceil <b style="color:#a78bfa">{_c.pra_ceiling:.1f}</b>
                          </div>
                          <div style="font-size:10px;color:#6b7280;margin-top:2px;">
                            vs {_c.opponent} [{_c.matchup_grade}]
                          </div>
                        </div>
                        """
                    )
                st.caption(f"#1 bet: **{_kotc_candidates[0].player_name}** — {_kotc_candidates[0].reasoning[:60]}…")

# --- Fetch & render ---
fetch_placeholder = st.empty()

def _render(sport_filter: str, market_filter: str, min_sharp: int) -> None:
    with fetch_placeholder.container():
        with st.spinner("Fetching odds..."):
            candidates, error, remaining = _fetch_and_rank(sport_filter)

        if error:
            st.error(error)
            return

        # --- Injury gate (applies sidebar injury alert to all candidates) ---
        # Two effects:
        #   1. KILL/FLAG — when the injury hurts the bet (e.g. betting WITH injured team)
        #   2. Score boost — when the injury HELPS the bet (opponent's key player out)
        #      Boost = min(5.0, signed_impact) added to sharp_score. Capped at 5 pts
        #      (the situational bucket ceiling). This can push STANDARD → NUCLEAR.
        if st.session_state.get("inj_active", False):
            _inj_sport  = st.session_state.get("inj_sport", "NBA")
            _inj_pos    = st.session_state.get("inj_pos", "")
            _inj_side   = st.session_state.get("inj_side", "home")
            _inj_market = st.session_state.get("inj_market", "spreads")
            if _inj_pos:
                for c in candidates:
                    if c.sport.upper() != _inj_sport.upper():
                        continue
                    # Bet direction: are we betting on home or away team?
                    is_home_bet = _inj_side == "away" or (
                        _inj_side == "home" and "home" not in c.target.lower()
                    )
                    bet_dir = "home" if is_home_bet else "away"
                    report = evaluate_injury_impact(
                        sport=_inj_sport,
                        position=_inj_pos,
                        is_starter=True,
                        team_side=_inj_side,
                        bet_market=_inj_market,
                        bet_direction=bet_dir,
                    )
                    if report.kill and not c.kill_reason:
                        c.kill_reason = f"KILL: {report.advisory}"
                    elif report.flag and not c.kill_reason:
                        c.kill_reason = f"FLAG: {report.advisory}"
                    elif report.signed_impact > 0 and not c.kill_reason:
                        # Favorable: opponent key player out — boost sharp score
                        boost = min(5.0, report.signed_impact)
                        c.sharp_score = round(c.sharp_score + boost, 1)
                        # Update breakdown situational component
                        if c.sharp_breakdown:
                            c.sharp_breakdown["situational"] = round(
                                c.sharp_breakdown.get("situational", 0.0) + boost, 1
                            )

        # Market filter
        mkt_key_map = {"Spread": "spreads", "Total": "totals", "Moneyline": "h2h"}
        if market_filter != "All":
            mkt_key = mkt_key_map.get(market_filter, "")
            candidates = [c for c in candidates if c.market_type == mkt_key]

        # Sharp score filter
        if min_sharp > 0:
            candidates = [c for c in candidates if c.sharp_score >= min_sharp]

        # Separate by grade
        grade_a = [c for c in candidates if c.grade == "A" and not c.kill_reason]
        grade_b = [c for c in candidates if c.grade == "B" and not c.kill_reason]
        grade_c = [c for c in candidates if c.grade == "C" and not c.kill_reason]
        near_miss = [c for c in candidates if c.grade == "NEAR_MISS" and not c.kill_reason]
        killed = [c for c in candidates if c.kill_reason]

        # Stats row — grade-aware counts
        s_col1, s_col2, s_col3, s_col4, s_col5, s_col6 = st.columns(6)
        with s_col1:
            st.metric("Grade A (Full)", len(grade_a))
        with s_col2:
            st.metric("Grade B (Mod.)", len(grade_b))
        with s_col3:
            st.metric("Grade C (Track)", len(grade_c))
        with s_col4:
            st.metric("Near Miss", len(near_miss))
        with s_col5:
            st.metric("Killed", len(killed))
        with s_col6:
            remaining_str = str(remaining) if remaining >= 0 else "—"
            st.metric("API Quota Left", remaining_str)

        st.markdown("---")

        # ----------------------------------------------------------------
        # Grade A — full slate (amber, standard sizing)
        # ----------------------------------------------------------------
        if grade_a:
            for rank, bet in enumerate(grade_a, start=1):
                st.html(_bet_card(bet, rank))
        elif not grade_b and not grade_c and not near_miss:
            # Truly nothing at any grade — market efficient state
            st.html("""
            <div style="background:#111827;border:1px solid #1f2937;border-radius:6px;
                        padding:32px 20px;text-align:center;margin-bottom:12px;">
                <div style="font-size:1.5rem;margin-bottom:8px;">📊</div>
                <div style="font-size:0.9rem;font-weight:700;color:#9ca3af;margin-bottom:4px;">
                    MARKET EFFICIENT TODAY
                </div>
                <div style="font-size:0.75rem;color:#6b7280;line-height:1.6;">
                    No positive-edge candidates found at any tier after scanning all active sports.<br>
                    Books are tightly aligned. This is correct model behaviour — no edge = no bet.<br>
                    Try again closer to game time or after line movement.
                </div>
            </div>
            """)
            return

        # ----------------------------------------------------------------
        # Grade B — moderate value (blue banner + cards)
        # ----------------------------------------------------------------
        if grade_b:
            st.html(f"""
            <div style="background:#0f1f35;border:1px solid #1e40af;border-radius:6px;
                        padding:10px 16px;margin-bottom:10px;margin-top:{'16px' if grade_a else '0'};">
                <span style="color:#60a5fa;font-weight:700;font-size:0.82rem;">
                    🔵 GRADE B — MODERATE VALUE
                </span>
                <span style="color:#93c5fd;font-size:0.75rem;margin-left:8px;">
                    Edge ≥1.5%. Positive EV — books slightly misaligned. Reduced stake (~0.12× Kelly).
                    May bet at your discretion. Log and track for calibration.
                </span>
            </div>
            """)
            for rank, bet in enumerate(grade_b, start=len(grade_a) + 1):
                st.html(_bet_card(bet, rank))

        # ----------------------------------------------------------------
        # Grade C — tracking only (slate banner + cards)
        # ----------------------------------------------------------------
        if grade_c:
            st.html(f"""
            <div style="background:#111827;border:1px solid #374151;border-radius:6px;
                        padding:10px 16px;margin-bottom:10px;margin-top:12px;">
                <span style="color:#9ca3af;font-weight:700;font-size:0.82rem;">
                    🟡 GRADE C — TRACKING ONLY
                </span>
                <span style="color:#6b7280;font-size:0.75rem;margin-left:8px;">
                    Edge ≥0.5%. Thin positive EV. Log with stake=$0 for data collection.
                    Do not bet. Useful for calibration once 30-bet gate is hit.
                </span>
            </div>
            """)
            offset_c = len(grade_a) + len(grade_b) + 1
            for rank, bet in enumerate(grade_c[:8], start=offset_c):
                st.html(_bet_card(bet, rank))

        # ----------------------------------------------------------------
        # Near Miss — market transparency (dark banner + dim cards)
        # ----------------------------------------------------------------
        if near_miss and not grade_a:  # only show near-misses if nothing actionable above
            nm_top = sorted(near_miss, key=lambda b: b.edge_pct, reverse=True)[:5]
            st.html("""
            <div style="background:#0a0f1a;border:1px solid #1f2937;border-radius:6px;
                        padding:10px 16px;margin-bottom:10px;margin-top:12px;">
                <span style="color:#4b5563;font-weight:700;font-size:0.82rem;">
                    ⊘ NEAR MISS — MARKET DATA ONLY
                </span>
                <span style="color:#374151;font-size:0.75rem;margin-left:8px;">
                    Edge &lt;0.5%. Books tightly aligned — no positive EV. Shown for transparency.
                    These are NOT bets. Do not log or stake.
                </span>
            </div>
            """)
            offset_nm = len(grade_a) + len(grade_b) + len(grade_c) + 1
            for rank, bet in enumerate(nm_top, start=offset_nm):
                st.html(_bet_card(bet, rank))

        # If only killed and near_miss, show killed below
        if killed and not grade_a and not grade_b and not grade_c:
            with st.expander(f"🔴 {len(killed)} killed candidates (kill switch fired)"):
                for rank, bet in enumerate(killed, start=1):
                    st.html(_bet_card(bet, rank))
            return

        # Render Log Bet buttons only for Grade A and B (actionable tiers)
        actionable = grade_a + grade_b
        for rank, bet in enumerate(actionable, start=1):

            btn_col, info_col = st.columns([1, 4])
            with btn_col:
                if st.button("📋 Log Bet", key=f"log_{rank}_{bet.event_id}", use_container_width=True):
                    try:
                        size_key = sharp_to_size(bet.sharp_score)
                        # Grade-aware default stake:
                        # Grade A → full size-tier stake (200/100/50)
                        # Grade B → capped at $50 (reduced stake tier)
                        if bet.grade == "A":
                            default_stake = {"NUCLEAR_2.0U": 200.0, "STANDARD_1.0U": 100.0, "LEAN_0.5U": 50.0}.get(size_key, 50.0)
                        else:
                            default_stake = 50.0  # Grade B reduced stake
                        bet_id = _log_bet(
                            sport=bet.sport,
                            matchup=bet.matchup,
                            market_type=bet.market_type,
                            target=bet.target,
                            price=bet.price,
                            edge_pct=bet.edge_pct,
                            kelly_size=bet.kelly_size,
                            stake=default_stake,
                            notes=f"sharp={bet.sharp_score:.0f} grade={bet.grade}",
                            db_path=DB_PATH,
                        )
                        st.success(f"Logged as bet #{bet_id} → go to Bet Tracker to grade")
                    except Exception as exc:
                        st.error(f"Log failed: {exc}")

            # Full math expander — no narrative, numbers only
            with st.expander(f"Math breakdown — {bet.target} {bet.matchup[:30]}", expanded=False):
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    st.markdown(
                        f"""
                        **Edge calculation**
                        - Model win prob: `{bet.win_prob*100:.2f}%`
                        - Market implied: `{bet.market_implied*100:.2f}%`
                        - Fair (no-vig): `{bet.fair_implied*100:.2f}%`
                        - Edge: `{bet.edge_pct*100:.2f}%`
                        """
                    )
                with mc2:
                    _kf_map = {"A": KELLY_FRACTION, "B": KELLY_FRACTION_B, "C": KELLY_FRACTION_C}
                    _kf = _kf_map.get(bet.grade, KELLY_FRACTION)
                    _full_kelly = bet.kelly_size / _kf if _kf > 0 else 0.0
                    st.markdown(
                        f"""
                        **Kelly sizing ({_kf:.2f}×)**
                        - Win prob: `{bet.win_prob:.4f}`
                        - Price: `{bet.price:+d}` American
                        - Full Kelly: `{_full_kelly:.4f}` → ×{_kf:.2f} = `{bet.kelly_size:.4f}`
                        - Bet size: `{bet.kelly_size*100:.2f}%` of bankroll
                        - Grade: `{bet.grade}` ({"full" if bet.grade == "A" else "reduced"} stake)
                        """
                    )
                with mc3:
                    # Extract Trinity cover % from signal if present
                    signal = bet.signal or ""
                    trinity_str = "—"
                    if "Trinity cover=" in signal:
                        try:
                            trinity_str = signal.split("Trinity cover=")[1].split("%")[0] + "%"
                        except Exception:
                            pass
                    st.markdown(
                        f"""
                        **Sharp Score: `{bet.sharp_score:.1f}` / 100**
                        - Edge comp: `{(bet.sharp_breakdown or {}).get('edge', 0):.0f}`
                        - RLM comp: `{(bet.sharp_breakdown or {}).get('rlm', 0):.0f}`
                        - Efficiency: `{(bet.sharp_breakdown or {}).get('efficiency', 0):.0f}`

                        **Trinity MC Cover:** `{trinity_str}`
                        """
                    )

                if bet.kill_reason:
                    st.warning(f"Kill switch active: {bet.kill_reason}")

                if bet.signal:
                    st.caption(f"Signals: {bet.signal}")

        # --- Parlay Combo Section ---
        # Build combos from all candidates (pre-filter, not post-filter)
        # so parlay scanner sees full universe even when sharp filter is set.
        parlay_combos = build_parlay_combos(candidates, max_results=5)
        if parlay_combos:
            st.markdown("---")
            st.markdown(
                '<span style="font-size:0.85rem; font-weight:700; color:#8b5cf6;">'
                "PARLAY COMBOS — Positive EV only · Independence verified · Kelly capped 0.5u"
                "</span>",
                unsafe_allow_html=True,
            )
            for i, combo in enumerate(parlay_combos, start=1):
                st.html(_parlay_card(combo, i))


_render(sport_filter, market_filter, min_sharp)

# Auto-refresh loop
if auto_refresh:
    time.sleep(60)
    st.cache_data.clear()
    st.rerun()
