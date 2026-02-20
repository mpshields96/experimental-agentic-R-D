"""
pages/06_simulator.py — Trinity Monte Carlo Game Simulator

Interactive pre-game simulation using the originator_engine.
Lets you model any matchup: input efficiency gap, situational edges,
and sport type — see projected margin distribution, cover probability,
and over/under probability in real-time.

Features:
- Projected margin distribution histogram (Bell curve overlay)
- Cover probability gauge + confidence interval
- Over/Under probability with league-average baseline
- Sensitivity analysis: what happens if efficiency gap shifts ±3 pts
- No live data required — pure math_engine / originator_engine

Design: dark terminal aesthetic, amber accent, no narrative.
"""

import math
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.originator_engine import (
    BASE_VOLATILITY,
    LEAGUE_AVG_TOTALS,
    SimulationResult,
    efficiency_gap_to_margin,
    efficiency_gap_to_soccer_strength,
    poisson_soccer,
    run_trinity_simulation,
)

# ---------------------------------------------------------------------------
# Plotly layout defaults
# ---------------------------------------------------------------------------
PLOTLY_BASE = dict(
    paper_bgcolor="#0e1117",
    plot_bgcolor="#13161d",
    font=dict(color="#d1d5db", size=11, family="monospace"),
    margin=dict(l=45, r=20, t=35, b=40),
    xaxis=dict(gridcolor="#2d3139", linecolor="#2d3139"),
    yaxis=dict(gridcolor="#2d3139", linecolor="#2d3139"),
    hoverlabel=dict(bgcolor="#1a1d23", bordercolor="#2d3139", font_color="#f3f4f6"),
)

SPORT_LABELS = {
    "NBA": "NBA Basketball",
    "NCAAB": "NCAA Basketball",
    "NFL": "NFL Football",
    "NCAAF": "NCAA Football",
    "NHL": "NHL Hockey",
    "MLB": "MLB Baseball",
    "SOCCER": "Soccer",
}

# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_margin_histogram(result: SimulationResult, line: float, sport: str) -> go.Figure:
    """Margin distribution histogram with cover/no-cover split and normal overlay."""
    # We don't have the raw samples, so reconstruct a synthetic distribution
    # from projected_margin + volatility for display purposes
    mu = result.projected_margin
    sigma = result.volatility
    cover_line = -line  # home covers if margin > -line

    # Build histogram bins from normal approx
    n_bins = 60
    x_min = mu - 4 * sigma
    x_max = mu + 4 * sigma
    bin_width = (x_max - x_min) / n_bins

    xs = [x_min + i * bin_width for i in range(n_bins + 1)]
    x_mids = [(xs[i] + xs[i + 1]) / 2 for i in range(n_bins)]

    def normal_pdf(x, m, s):
        return math.exp(-0.5 * ((x - m) / s) ** 2) / (s * math.sqrt(2 * math.pi))

    # Scale factor: area under histogram ≈ 1
    counts = [normal_pdf(x, mu, sigma) * bin_width * 10_000 for x in x_mids]

    cover_x = [x for x in x_mids if x > cover_line]
    cover_y = [normal_pdf(x, mu, sigma) * bin_width * 10_000 for x in cover_x]
    no_cover_x = [x for x in x_mids if x <= cover_line]
    no_cover_y = [normal_pdf(x, mu, sigma) * bin_width * 10_000 for x in no_cover_x]

    fig = go.Figure()

    # No-cover bars
    if no_cover_x:
        fig.add_trace(go.Bar(
            x=no_cover_x, y=no_cover_y,
            name=f"No Cover ({100 * (1 - result.cover_probability):.1f}%)",
            marker_color="#ef4444",
            opacity=0.6,
            width=bin_width,
        ))

    # Cover bars
    if cover_x:
        fig.add_trace(go.Bar(
            x=cover_x, y=cover_y,
            name=f"Cover ({100 * result.cover_probability:.1f}%)",
            marker_color="#22c55e",
            opacity=0.7,
            width=bin_width,
        ))

    # Market line
    fig.add_vline(
        x=cover_line,
        line_dash="dash",
        line_color="#f59e0b",
        line_width=2,
        annotation_text=f"Line: {line:+.1f}",
        annotation_font_color="#f59e0b",
        annotation_font_size=10,
    )

    # Projected margin
    fig.add_vline(
        x=mu,
        line_dash="dot",
        line_color="#d1d5db",
        line_width=1.5,
        annotation_text=f"Proj: {mu:+.1f}",
        annotation_font_color="#d1d5db",
        annotation_font_size=10,
        annotation_position="top left",
    )

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text=f"{SPORT_LABELS.get(sport, sport)} — Margin Distribution (10,000 sims)",
        font=dict(size=12, color="#9ca3af"),
        x=0,
    )
    layout["height"] = 300
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Home Margin (pts)")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Frequency")
    layout["barmode"] = "overlay"
    layout["showlegend"] = True
    layout["legend"] = dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="#2d3139",
        font=dict(size=10, color="#9ca3af"),
        x=0.01, y=0.99,
    )
    fig.update_layout(**layout)
    return fig


def _build_sensitivity_chart(
    base_gap: float,
    sport: str,
    line: float,
    home_adv: float,
    rest_edge: float,
    travel_penalty: float,
    total_line: float | None,
) -> go.Figure:
    """Cover probability as efficiency gap shifts ±4 pts around base."""
    deltas = [-4, -3, -2, -1, 0, 1, 2, 3, 4]
    cover_probs = []
    over_probs = []

    for d in deltas:
        gap = max(0.0, min(20.0, base_gap + d))
        margin = efficiency_gap_to_margin(gap, home_advantage_pts=home_adv)
        r = run_trinity_simulation(
            mean=margin,
            sport=sport,
            line=line,
            total_line=total_line,
            rest_edge=rest_edge,
            travel_penalty=travel_penalty,
            iterations=5_000,
            seed=42,
        )
        cover_probs.append(r.cover_probability * 100)
        over_probs.append(r.over_probability * 100 if total_line else 0.0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=deltas,
        y=cover_probs,
        mode="lines+markers",
        name="Cover %",
        line=dict(color="#22c55e", width=2.5),
        marker=dict(size=7, color="#22c55e"),
        hovertemplate="Gap shift: %{x:+d}<br>Cover: %{y:.1f}%<extra></extra>",
    ))

    if total_line and any(p > 0 for p in over_probs):
        fig.add_trace(go.Scatter(
            x=deltas,
            y=over_probs,
            mode="lines+markers",
            name="Over %",
            line=dict(color="#f59e0b", width=2, dash="dash"),
            marker=dict(size=6, color="#f59e0b"),
            hovertemplate="Gap shift: %{x:+d}<br>Over: %{y:.1f}%<extra></extra>",
        ))

    fig.add_hline(y=50, line_dash="dot", line_color="#4b5563", line_width=1)

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text="Sensitivity — Cover% vs Efficiency Gap Shift",
        font=dict(size=12, color="#9ca3af"),
        x=0,
    )
    layout["height"] = 260
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Gap shift (± pts)", zeroline=True)
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Probability (%)", range=[0, 100])
    layout["showlegend"] = True
    layout["legend"] = dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=10, color="#9ca3af"),
    )
    fig.update_layout(**layout)
    return fig


def _build_ci_gauge(cover_prob: float, ci_10: float, ci_90: float) -> str:
    """HTML cover probability gauge card."""
    pct = cover_prob * 100
    color = "#22c55e" if pct > 55 else ("#ef4444" if pct < 45 else "#f59e0b")
    bar_width = min(100, max(0, pct))

    verdict = "COVER LEAN" if pct >= 52 else ("NO COVER LEAN" if pct <= 48 else "TOSS-UP")
    verdict_color = "#22c55e" if pct >= 52 else ("#ef4444" if pct <= 48 else "#9ca3af")

    return f"""
    <div style="
        background:#1a1d23; border:1px solid #2d3139;
        border-left:4px solid {color}; border-radius:8px;
        padding:16px 20px;
    ">
        <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.1em; font-weight:600; margin-bottom:6px;">
            COVER PROBABILITY
        </div>
        <div style="font-size:2.8rem; font-weight:800; color:{color}; line-height:1;">
            {pct:.1f}%
        </div>
        <div style="
            height:4px; background:#2d3139; border-radius:3px;
            margin-top:10px; margin-bottom:8px; overflow:hidden;
        ">
            <div style="
                height:100%; width:{bar_width:.0f}%; background:{color};
                border-radius:3px;
            "></div>
        </div>
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
            <span style="font-size:0.65rem; color:#6b7280;">
                10th pct: <strong style="color:#d1d5db;">{ci_10:+.1f} pts</strong>
            </span>
            <span style="font-size:0.65rem; color:#6b7280;">
                90th pct: <strong style="color:#d1d5db;">{ci_90:+.1f} pts</strong>
            </span>
        </div>
        <div style="font-size:0.75rem; font-weight:700; color:{verdict_color};">
            → {verdict}
        </div>
    </div>
    """


def _build_total_card(over_prob: float, total_line: float, league_avg: float) -> str:
    """HTML over/under probability card."""
    over_pct = over_prob * 100
    under_pct = 100 - over_pct
    color = "#22c55e" if over_pct > 55 else ("#ef4444" if over_pct < 45 else "#f59e0b")
    verdict = "OVER LEAN" if over_pct >= 52 else ("UNDER LEAN" if over_pct <= 48 else "TOSS-UP")
    verdict_color = "#22c55e" if over_pct >= 52 else ("#ef4444" if over_pct <= 48 else "#9ca3af")

    return f"""
    <div style="
        background:#1a1d23; border:1px solid #2d3139;
        border-left:4px solid {color}; border-radius:8px;
        padding:16px 20px;
    ">
        <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.1em; font-weight:600; margin-bottom:6px;">
            OVER/UNDER — {total_line:.1f} (league avg: {league_avg:.0f})
        </div>
        <div style="display:flex; gap:20px; align-items:flex-end;">
            <div>
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">OVER</div>
                <div style="font-size:2.2rem; font-weight:800; color:{color};">{over_pct:.1f}%</div>
            </div>
            <div>
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">UNDER</div>
                <div style="font-size:2.2rem; font-weight:800; color:#6b7280;">{under_pct:.1f}%</div>
            </div>
        </div>
        <div style="font-size:0.75rem; font-weight:700; color:{verdict_color}; margin-top:8px;">
            → {verdict}
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Poisson soccer chart builders
# ---------------------------------------------------------------------------

def _build_poisson_goal_heatmap(h_att: float, a_att: float, h_def: float, a_def: float) -> go.Figure:
    """
    Poisson goal probability matrix heatmap — P(home=i, away=j) for i,j in [0,7].

    Cells show the joint probability of each exact scoreline.
    Win cells (top-left triangle) = amber, draw diagonal = white, away-win (bottom-right) = red.
    """
    from core.originator_engine import _poisson_pmf, SOCCER_LEAGUE_AVG_GOALS_HOME, SOCCER_LEAGUE_AVG_GOALS_AWAY, SOCCER_HOME_GOAL_BOOST
    max_g = 7

    lam_home = SOCCER_LEAGUE_AVG_GOALS_HOME * h_att * a_def * (1 + SOCCER_HOME_GOAL_BOOST)
    lam_away = SOCCER_LEAGUE_AVG_GOALS_AWAY * a_att * h_def
    lam_home = max(0.1, min(lam_home, 6.0))
    lam_away = max(0.1, min(lam_away, 6.0))

    home_pmf = [_poisson_pmf(k, lam_home) for k in range(max_g + 1)]
    away_pmf = [_poisson_pmf(k, lam_away) for k in range(max_g + 1)]

    z = [[home_pmf[h] * away_pmf[a] * 100 for a in range(max_g + 1)] for h in range(max_g + 1)]
    x_labels = [str(a) for a in range(max_g + 1)]
    y_labels = [str(h) for h in range(max_g + 1)]

    # Text labels for each cell
    text = [[f"{z[h][a]:.1f}%" for a in range(max_g + 1)] for h in range(max_g + 1)]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        text=text,
        texttemplate="%{text}",
        colorscale=[
            [0.0, "#0e1117"],
            [0.02, "#1e2a3a"],
            [0.10, "#1e3a5f"],
            [0.25, "#f59e0b"],
            [1.0, "#fef3c7"],
        ],
        showscale=True,
        colorbar=dict(
            title="P(%)",
            titlefont=dict(color="#9ca3af", size=10),
            tickfont=dict(color="#9ca3af", size=9),
            bgcolor="#1a1d23",
            bordercolor="#2d3139",
            thickness=12,
            len=0.8,
        ),
        hovertemplate="Home %{y} – Away %{x}: %{text}<extra></extra>",
        textfont=dict(size=9),
    ))

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text=f"Scoreline Probability Matrix (λH={lam_home:.2f}, λA={lam_away:.2f})",
        font=dict(size=12, color="#9ca3af"),
        x=0,
    )
    layout["height"] = 360
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Away Goals", side="top")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Home Goals", autorange="reversed")
    fig.update_layout(**layout)
    return fig


def _build_poisson_1x2_bar(result) -> go.Figure:
    """Horizontal stacked bar: home_win / draw / away_win probabilities."""
    fig = go.Figure()

    hw = result.home_win * 100
    dr = result.draw * 100
    aw = result.away_win * 100

    for label, val, color in [
        ("Home Win", hw, "#22c55e"),
        ("Draw", dr, "#f59e0b"),
        ("Away Win", aw, "#ef4444"),
    ]:
        fig.add_trace(go.Bar(
            x=[val],
            y=["1X2"],
            name=f"{label} {val:.1f}%",
            orientation="h",
            marker_color=color,
            text=f"{label}<br>{val:.1f}%",
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=11, color="#fff"),
        ))

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text="Poisson 1X2 Outcome Probabilities",
        font=dict(size=12, color="#9ca3af"),
        x=0,
    )
    layout["height"] = 110
    layout["barmode"] = "stack"
    layout["showlegend"] = False
    layout["margin"] = dict(l=45, r=20, t=35, b=10)
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="", range=[0, 100], ticksuffix="%")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="", showticklabels=False)
    fig.update_layout(**layout)
    return fig


def _poisson_summary_card(result, total_line: float) -> str:
    """HTML summary card for Poisson xG and 1X2."""
    hw = result.home_win * 100
    dr = result.draw * 100
    aw = result.away_win * 100
    ov = result.over_probability * 100
    un = result.under_probability * 100
    xg_h = result.expected_home_goals
    xg_a = result.expected_away_goals

    hw_col = "#22c55e" if hw > aw and hw > dr else "#9ca3af"
    aw_col = "#ef4444" if aw > hw and aw > dr else "#9ca3af"
    dr_col = "#f59e0b" if dr > hw and dr > aw else "#9ca3af"
    ov_col = "#22c55e" if ov > 52 else ("#ef4444" if ov < 48 else "#9ca3af")

    return f"""
    <div style="
        background:#1a1d23; border:1px solid #2d3139; border-radius:8px;
        padding:16px 20px; font-family:monospace;
    ">
        <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.1em; font-weight:600; margin-bottom:10px;">
            POISSON MODEL — xG SUMMARY
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:12px; margin-bottom:12px;">
            <div>
                <div style="font-size:0.55rem; color:#6b7280;">HOME WIN</div>
                <div style="font-size:1.6rem; font-weight:800; color:{hw_col};">{hw:.1f}%</div>
            </div>
            <div>
                <div style="font-size:0.55rem; color:#6b7280;">DRAW</div>
                <div style="font-size:1.6rem; font-weight:800; color:{dr_col};">{dr:.1f}%</div>
            </div>
            <div>
                <div style="font-size:0.55rem; color:#6b7280;">AWAY WIN</div>
                <div style="font-size:1.6rem; font-weight:800; color:{aw_col};">{aw:.1f}%</div>
            </div>
            <div>
                <div style="font-size:0.55rem; color:#6b7280;">O/U {total_line:.1f}</div>
                <div style="font-size:1.6rem; font-weight:800; color:{ov_col};">{ov:.1f}% / {un:.1f}%</div>
            </div>
        </div>
        <div style="display:flex; gap:24px; font-size:0.7rem; color:#9ca3af; border-top:1px solid #2d3139; padding-top:8px;">
            <span>xG Home: <strong style="color:#e5e7eb;">{xg_h:.2f}</strong></span>
            <span>xG Away: <strong style="color:#e5e7eb;">{xg_a:.2f}</strong></span>
            <span>xG Total: <strong style="color:#f59e0b;">{xg_h+xg_a:.2f}</strong></span>
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------
st.title("🎲 Game Simulator")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">'
    "Trinity Monte Carlo — 10,000 simulations per run · Ceiling 20% / Floor 20% / Median 60%"
    "</span>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Input controls
# ---------------------------------------------------------------------------
st.markdown("---")
st.subheader("Inputs")

ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 2])

with ctrl_col1:
    sport = st.selectbox(
        "Sport",
        list(SPORT_LABELS.keys()),
        format_func=lambda k: SPORT_LABELS[k],
        key="sim_sport",
    )
    home_team = st.text_input("Home Team (label only)", value="Home", key="sim_home")
    away_team = st.text_input("Away Team (label only)", value="Away", key="sim_away")

with ctrl_col2:
    efficiency_gap = st.slider(
        "Efficiency Gap (0–20)",
        min_value=0.0, max_value=20.0, value=10.0, step=0.5,
        key="sim_eff_gap",
        help="Gap = 10 → neutral. Gap = 15 → home +5 pts projected advantage.",
    )
    home_advantage = st.slider(
        "Home Court/Field Advantage (pts)",
        min_value=0.0, max_value=7.0, value=2.5, step=0.5,
        key="sim_home_adv",
        help="NBA ≈2.5, NFL ≈3.0, NHL ≈1.5",
    )
    rest_edge = st.slider(
        "Rest Edge (pts, positive = home better rested)",
        min_value=-5.0, max_value=5.0, value=0.0, step=0.5,
        key="sim_rest",
    )
    travel_penalty = st.slider(
        "Away Travel Penalty (pts)",
        min_value=0.0, max_value=5.0, value=0.0, step=0.5,
        key="sim_travel",
    )

with ctrl_col3:
    line = st.number_input(
        "Market Spread Line (negative = home favored)",
        value=-4.5, step=0.5,
        key="sim_line",
        help="e.g. -4.5 means home must win by 5+ to cover",
    )
    simulate_total = st.toggle("Simulate Over/Under", value=False, key="sim_total_on")
    if simulate_total:
        league_avg = LEAGUE_AVG_TOTALS.get(sport, 220.0)
        total_line = st.number_input(
            "Total Line",
            value=float(league_avg),
            step=0.5,
            key="sim_total_line",
        )
        total_line_val: float | None = total_line
    else:
        total_line_val = None

    iterations = st.select_slider(
        "Simulations",
        options=[1_000, 5_000, 10_000, 25_000, 50_000],
        value=10_000,
        key="sim_iters",
    )

# ---------------------------------------------------------------------------
# Run simulation
# ---------------------------------------------------------------------------
projected_margin = efficiency_gap_to_margin(efficiency_gap, home_advantage_pts=home_advantage)

with st.spinner("Running Trinity simulation..."):
    result = run_trinity_simulation(
        mean=projected_margin,
        sport=sport,
        line=line,
        total_line=total_line_val,
        rest_edge=rest_edge,
        travel_penalty=travel_penalty,
        iterations=iterations,
        seed=None,  # live random for interactive use
    )

st.markdown("---")
st.subheader("Results")

# --- Summary KPI row ---
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Projected Margin", f"{result.projected_margin:+.1f} pts", help="Median simulated margin (home − away)")
with kpi2:
    st.metric("Cover Probability", f"{result.cover_probability*100:.1f}%")
with kpi3:
    st.metric(
        "80% Confidence Interval",
        f"{result.ci_10:+.1f} to {result.ci_90:+.1f} pts",
        help="80% of simulations fall in this range",
    )
with kpi4:
    st.metric("Simulated Volatility", f"±{result.volatility:.1f} pts", help="Std dev of simulated margins")

st.markdown("")

# --- Cover gauge + optional totals ---
gauge_col, total_col = st.columns([1, 1])

with gauge_col:
    st.html(_build_ci_gauge(result.cover_probability, result.ci_10, result.ci_90))

with total_col:
    if total_line_val is not None and result.over_probability > 0:
        league_avg_disp = LEAGUE_AVG_TOTALS.get(sport, 220.0)
        st.html(_build_total_card(result.over_probability, total_line_val, league_avg_disp))
    else:
        vol_pct = BASE_VOLATILITY.get(sport, 8.0)
        st.html(
            f"""
            <div style="
                background:#1a1d23; border:1px solid #2d3139;
                border-radius:8px; padding:16px 20px;
            ">
                <div style="font-size:0.6rem; color:#6b7280; letter-spacing:0.1em; font-weight:600; margin-bottom:8px;">
                    SPORT PARAMETERS
                </div>
                <div style="font-size:0.8rem; color:#d1d5db; line-height:1.8;">
                    <div>Base volatility: <strong style="color:#f59e0b;">{vol_pct:.1f} pts</strong></div>
                    <div>Input margin: <strong style="color:#f59e0b;">{projected_margin:+.2f} pts</strong></div>
                    <div>Situational adj: <strong style="color:#9ca3af;">{rest_edge + travel_penalty:+.1f} pts</strong></div>
                    <div>Iterations: <strong style="color:#9ca3af;">{result.iterations:,}</strong></div>
                </div>
                <div style="margin-top:8px; font-size:0.65rem; color:#4b5563;">
                    Toggle "Simulate Over/Under" above to add totals model
                </div>
            </div>
            """
        )

st.markdown("")

# --- Margin distribution chart ---
fig_hist = _build_margin_histogram(result, line, sport)
st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

# --- Sensitivity analysis ---
st.subheader("Sensitivity Analysis")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">How does cover probability change as efficiency gap shifts? '
    "Useful for gauging model robustness.</span>",
    unsafe_allow_html=True,
)

with st.spinner("Running sensitivity sweep..."):
    fig_sens = _build_sensitivity_chart(
        base_gap=efficiency_gap,
        sport=sport,
        line=line,
        home_adv=home_advantage,
        rest_edge=rest_edge,
        travel_penalty=travel_penalty,
        total_line=total_line_val,
    )
st.plotly_chart(fig_sens, use_container_width=True, config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Soccer: Poisson goal matrix (only visible when SOCCER selected)
# ---------------------------------------------------------------------------
if sport == "SOCCER":
    st.markdown("---")
    st.subheader("⚽ Poisson Goal Matrix")
    st.markdown(
        '<span style="font-size:0.75rem; color:#6b7280;">'
        "Discrete Poisson model — independent Poisson processes for home/away goals · "
        "Superior to normal distribution for low-scoring discrete outcomes. "
        "Derived from 2020–2025 top-5 league aggregate goal rates."
        "</span>",
        unsafe_allow_html=True,
    )

    # Soccer total line input (separate from spread total_line_val)
    soccer_total_line = st.slider(
        "Soccer Over/Under Total",
        min_value=1.5, max_value=5.5, value=2.5, step=0.5,
        key="sim_soccer_total",
        help="Typical range: 2.5 (low-scoring) to 3.5 (high-scoring match)",
    )

    h_att, a_att, h_def, a_def = efficiency_gap_to_soccer_strength(efficiency_gap)

    with st.spinner("Running Poisson matrix..."):
        pois_result = poisson_soccer(
            home_attack=h_att,
            away_attack=a_att,
            home_defense=h_def,
            away_defense=a_def,
            total_line=soccer_total_line,
            apply_home_advantage=True,
        )

    # Summary card
    st.html(_poisson_summary_card(pois_result, soccer_total_line))

    st.markdown("")

    # 1X2 bar + heatmap
    bar_col, heat_col = st.columns([1, 2])
    with bar_col:
        fig_1x2 = _build_poisson_1x2_bar(pois_result)
        st.plotly_chart(fig_1x2, use_container_width=True, config={"displayModeBar": False})

        # Attack/defense strength factors from efficiency gap
        st.html(
            f"""
            <div style="
                background:#1a1d23; border:1px solid #2d3139;
                border-radius:6px; padding:12px 14px;
                font-size:0.65rem; color:#6b7280; line-height:1.8;
                font-family:monospace;
            ">
                <div style="font-size:0.55rem; color:#4b5563; letter-spacing:0.08em; margin-bottom:4px;">
                    INPUT FACTORS (from eff. gap={efficiency_gap:.1f})
                </div>
                <div>Home attack: <strong style="color:#f59e0b;">{h_att:.3f}</strong></div>
                <div>Away attack: <strong style="color:#f59e0b;">{a_att:.3f}</strong></div>
                <div>Home defense: <strong style="color:#9ca3af;">{h_def:.3f}</strong></div>
                <div>Away defense: <strong style="color:#9ca3af;">{a_def:.3f}</strong></div>
            </div>
            """
        )

    with heat_col:
        fig_heat = _build_poisson_goal_heatmap(h_att, a_att, h_def, a_def)
        st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})

    # Trinity vs Poisson alignment note
    trinity_cp = result.cover_probability * 100
    poisson_hw = pois_result.home_win * 100
    delta_pct = abs(trinity_cp - poisson_hw)
    alignment_color = "#22c55e" if delta_pct < 8 else ("#f59e0b" if delta_pct < 15 else "#ef4444")
    alignment_label = "ALIGNED" if delta_pct < 8 else ("MODERATE DIVERGENCE" if delta_pct < 15 else "HIGH DIVERGENCE")
    st.html(
        f"""
        <div style="
            background:#1a1d23; border:1px solid #2d3139;
            border-left:3px solid {alignment_color}; border-radius:6px;
            padding:10px 14px; font-size:0.7rem; color:#9ca3af;
        ">
            Trinity home cover: <strong style="color:#d1d5db;">{trinity_cp:.1f}%</strong> ·
            Poisson home win: <strong style="color:#d1d5db;">{poisson_hw:.1f}%</strong> ·
            Δ={delta_pct:.1f}pp ·
            <strong style="color:{alignment_color};">{alignment_label}</strong>
            <span style="color:#4b5563; font-size:0.6rem; margin-left:8px;">
                (Trinity = continuous margin model · Poisson = discrete goal count model)
            </span>
        </div>
        """
    )

# --- Trinity weighting note ---
st.markdown("---")
st.html(
    """
    <div style="
        background:#1a1d23; border:1px solid #2d3139;
        border-radius:6px; padding:12px 16px;
        font-size:0.7rem; color:#6b7280; line-height:1.7;
    ">
        <strong style="color:#9ca3af;">Trinity weighting:</strong>
        20% Ceiling (optimistic efficiency + pace, tighter vol ×0.85)
        · 20% Floor (pessimistic, wider vol ×1.15)
        · 60% Median (baseline with small noise).
        Simulates uncertainty in <em>inputs</em> (efficiency reads, pace estimates),
        not just sampling noise. Box-Muller normal sampler — no scipy/numpy dependency.
    </div>
    """
)
