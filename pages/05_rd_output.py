"""
pages/05_rd_output.py — R&D Output Tab (Session 5)

Mathematical validation dashboard — all charts computed from math_engine
directly, zero dependency on live data or bet log.

Panels:
1. Sharp Score Anatomy       — stacked bar showing component contribution ranges
2. Score Sensitivity Sandbox — interactive sliders, live score readout
3. Kelly Frontier            — bet size vs win_prob heatmap across odds range
4. Collar Boundary Map       — which odds pass/fail collar at each edge threshold
5. Score Threshold Analysis  — how many hypothetical bets pass at 45/50/55
6. Math Constraint Summary   — static table of all non-negotiable rules

Design: dark terminal aesthetic, amber accent, Plotly dark charts
"""

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.math_engine import (
    COLLAR_MAX,
    COLLAR_MIN,
    KELLY_FRACTION,
    MIN_BOOKS,
    MIN_EDGE,
    SHARP_THRESHOLD,
    calculate_sharp_score,
    fractional_kelly,
    implied_probability,
    passes_collar,
    sharp_to_size,
)
from core.clv_tracker import CLV_GATE, clv_summary, read_clv_log
from core.probe_logger import probe_summary, read_probe_log

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLOTLY_BASE = dict(
    paper_bgcolor="#0e1117",
    plot_bgcolor="#13161d",
    font=dict(color="#d1d5db", size=11, family="monospace"),
    margin=dict(l=55, r=20, t=40, b=50),
    xaxis=dict(gridcolor="#2d3139", linecolor="#2d3139", tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#2d3139", linecolor="#2d3139", tickfont=dict(size=10)),
    hoverlabel=dict(bgcolor="#1a1d23", bordercolor="#2d3139", font_color="#f3f4f6"),
)
AMBER = "#f59e0b"
GREEN = "#22c55e"
RED = "#ef4444"
BLUE = "#60a5fa"
GRAY = "#6b7280"


def _section_header(title: str, subtitle: str = "") -> None:
    sub_html = (
        f'<div style="font-size:0.72rem; color:#6b7280; margin-top:2px;">{subtitle}</div>'
        if subtitle else ""
    )
    st.html(f"""
    <div style="margin-bottom:12px; margin-top:4px;">
        <span style="
            font-size:0.65rem; font-weight:700; letter-spacing:0.12em;
            color:{AMBER}; text-transform:uppercase;
        ">{title}</span>
        {sub_html}
    </div>
    """)


# ---------------------------------------------------------------------------
# Panel 1: Sharp Score Component Anatomy
# ---------------------------------------------------------------------------
def _build_score_anatomy():
    """Stacked bar: max contribution per component under different scenarios."""
    scenarios = [
        ("No RLM, 5% edge, no sit.", 0.05, False, 0.0, 0.0, 0.0),
        ("No RLM, 8% edge, no sit.", 0.08, False, 0.0, 0.0, 0.0),
        ("No RLM, 8% edge, full sit.", 0.08, False, 0.0, 5.0, 3.0),
        ("RLM confirmed, 5% edge", 0.05, True, 0.0, 0.0, 0.0),
        ("RLM confirmed, 8% edge", 0.08, True, 0.0, 0.0, 0.0),
        ("RLM + 8% edge + full sit.", 0.08, True, 0.0, 5.0, 3.0),
        ("Max possible (10%+, all on)", 0.12, True, 5.0, 5.0, 3.0),
    ]

    labels, edge_pts, rlm_pts, eff_pts, sit_pts_list, totals = [], [], [], [], [], []

    for label, edge, rlm, rest, injury, motivation in scenarios:
        # efficiency: set to 8.0 (default for unknown teams in rank_bets)
        score, bd = calculate_sharp_score(
            edge_pct=edge,
            rlm_confirmed=rlm,
            efficiency_gap=8.0,
            rest_edge=rest,
            injury_leverage=injury,
            motivation=motivation,
        )
        labels.append(label)
        edge_pts.append(bd["edge"])
        rlm_pts.append(bd["rlm"])
        eff_pts.append(bd["efficiency"])
        sit_pts_list.append(bd["situational"])
        totals.append(score)

    fig = go.Figure()
    for name, vals, color in [
        ("Edge (40 max)", edge_pts, GREEN),
        ("Efficiency (20 max)", eff_pts, BLUE),
        ("Situational (15 max)", sit_pts_list, AMBER),
        ("RLM (25 pts flat)", rlm_pts, RED),
    ]:
        fig.add_trace(go.Bar(
            name=name, x=labels, y=vals,
            marker_color=color, opacity=0.85,
        ))

    # Threshold lines
    for thresh, dash, color in [(45, "dash", AMBER), (80, "dot", GREEN), (90, "dot", RED)]:
        fig.add_hline(
            y=thresh, line_color=color, line_width=1, line_dash=dash,
            annotation_text=f"{'LEAN' if thresh == 45 else 'STD' if thresh == 80 else 'NUCLEAR'} threshold {thresh}",
            annotation_font=dict(color=color, size=9),
            annotation_position="right",
        )

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="Sharp Score Component Anatomy", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 320
    layout["barmode"] = "stack"
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Score", range=[0, 105])
    layout["xaxis"] = {**PLOTLY_BASE["xaxis"], "tickangle": -20, "tickfont": dict(size=9)}
    layout["legend"] = dict(
        orientation="h", y=1.12, x=0,
        font=dict(size=9, color="#9ca3af"),
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Panel 3: Kelly Frontier heatmap
# ---------------------------------------------------------------------------
def _build_kelly_frontier():
    """Heatmap: fractional Kelly size (units) across win_prob × american_odds grid."""
    win_probs = [i / 100 for i in range(48, 68, 2)]  # 0.48 → 0.66
    odds_range = list(range(-180, 155, 10))  # -180 → +150, step 10

    z = []
    for wp in win_probs:
        row = []
        for odds in odds_range:
            if not passes_collar(odds):
                row.append(None)
            else:
                # Only compute if there's positive edge (win_prob > implied)
                ip = implied_probability(odds)
                if wp <= ip:
                    row.append(0.0)
                else:
                    row.append(fractional_kelly(wp, odds))
        z.append(row)

    x_labels = [f"{o:+d}" for o in odds_range]
    y_labels = [f"{wp:.0%}" for wp in win_probs]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        colorscale=[
            [0.0, "#13161d"],
            [0.01, "#1a3a2a"],
            [0.3, "#16a34a"],
            [0.6, AMBER],
            [1.0, RED],
        ],
        zmin=0, zmax=2.0,
        colorbar=dict(
            title="Units",
            title_font=dict(color="#9ca3af", size=10),
            tickfont=dict(color="#9ca3af", size=9),
            thickness=12,
        ),
        hovertemplate="Win prob: %{y}<br>Odds: %{x}<br>Kelly: %{z:.2f}u<extra></extra>",
    ))

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text="Kelly Frontier (0.25× fractional) — units by win prob × odds",
        font=dict(size=12, color="#9ca3af"), x=0,
    )
    layout["height"] = 280
    layout["xaxis"] = {
        **PLOTLY_BASE["xaxis"],
        "title": "American odds (collar: −180 to +150)",
        "tickangle": -45,
        "tickfont": dict(size=9),
    }
    layout["yaxis"] = {**PLOTLY_BASE["yaxis"], "title": "Win probability", "tickfont": dict(size=9)}
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Panel 4: Collar boundary pass/fail
# ---------------------------------------------------------------------------
def _build_collar_map():
    """Bar chart: pass/fail rate across the full American odds spectrum."""
    test_range = list(range(-300, 300, 5))
    pass_odds = [o for o in test_range if passes_collar(o)]
    fail_low = [o for o in test_range if o < COLLAR_MIN]
    fail_high = [o for o in test_range if o > COLLAR_MAX]

    fig = go.Figure()
    # Pass zone
    fig.add_trace(go.Scatter(
        x=pass_odds, y=[1] * len(pass_odds),
        mode="markers", name="PASS",
        marker=dict(color=GREEN, size=5, symbol="square"),
        hovertemplate="Odds: %{x}<br>Status: PASS<extra></extra>",
    ))
    # Fail zones
    for label, fail_list, color in [("FAIL (< −180)", fail_low, RED), ("FAIL (> +150)", fail_high, RED)]:
        fig.add_trace(go.Scatter(
            x=fail_list, y=[1] * len(fail_list),
            mode="markers", name=label,
            marker=dict(color=color, size=5, symbol="x"),
            hovertemplate="Odds: %{x}<br>Status: BLOCKED<extra></extra>",
        ))

    # Collar boundaries
    for val in [COLLAR_MIN, COLLAR_MAX]:
        fig.add_vline(x=val, line_color=AMBER, line_width=1.5, line_dash="dash",
                      annotation_text=f"{val:+d}",
                      annotation_font=dict(color=AMBER, size=10))

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text=f"Collar: {COLLAR_MIN:+d} to {COLLAR_MAX:+d} — pass zone only",
                           font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 160
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], showticklabels=False, showgrid=False, title="")
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="American odds", dtick=50)
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Panel 5: Threshold pass-rate analysis
# ---------------------------------------------------------------------------
def _build_threshold_analysis():
    """Line chart: % of bets that would pass at each Sharp Score threshold,
    across a synthetic population of 500 bets with varying edge/RLM/efficiency."""
    import random
    random.seed(42)

    # Synthetic bet population: edge 3.5-12%, RLM 20% probability, efficiency 5-15
    population = []
    for _ in range(500):
        edge = random.uniform(0.035, 0.12)
        rlm = random.random() < 0.20
        eff = random.uniform(5.0, 15.0)
        rest = random.uniform(0, 3.0)
        score, _ = calculate_sharp_score(edge, rlm, eff, rest_edge=rest)
        population.append(score)

    thresholds = list(range(30, 96, 5))
    pass_rates = [sum(1 for s in population if s >= t) / len(population) * 100
                  for t in thresholds]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=thresholds, y=pass_rates,
        mode="lines+markers",
        line=dict(color=AMBER, width=2),
        marker=dict(size=6, color=AMBER),
        hovertemplate="Threshold: %{x}<br>Pass rate: %{y:.1f}%<extra></extra>",
    ))

    # Current threshold
    current_idx = thresholds.index(45) if 45 in thresholds else None
    if current_idx is not None:
        fig.add_vline(x=45, line_color=GREEN, line_width=1.5, line_dash="dash",
                      annotation_text="current 45",
                      annotation_font=dict(color=GREEN, size=10),
                      annotation_position="top right")
    fig.add_vline(x=50, line_color=AMBER, line_width=1, line_dash="dot",
                  annotation_text="target 50",
                  annotation_font=dict(color=AMBER, size=9),
                  annotation_position="top left")

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text="Threshold Analysis — % of synthetic bets passing (n=500, 20% RLM rate)",
        font=dict(size=12, color="#9ca3af"), x=0,
    )
    layout["height"] = 240
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Sharp Score threshold", dtick=5)
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Pass rate %", ticksuffix="%")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Panel 6: Edge implied probability surface
# ---------------------------------------------------------------------------
def _build_edge_surface():
    """Line chart: edge% as function of win_prob at key market odds lines."""
    key_odds = [-130, -110, -105, 100, 110, 130, 150]
    win_probs = [i / 100 for i in range(45, 73, 1)]

    fig = go.Figure()
    colors = [RED, "#f97316", AMBER, "#84cc16", GREEN, BLUE, "#a78bfa"]

    for odds, color in zip(key_odds, colors):
        if not passes_collar(odds):
            continue
        ip = implied_probability(odds)
        edges = [(wp - ip) * 100 for wp in win_probs]
        fig.add_trace(go.Scatter(
            x=[wp * 100 for wp in win_probs],
            y=edges,
            mode="lines",
            name=f"{odds:+d}",
            line=dict(color=color, width=1.5),
            hovertemplate=f"Odds {odds:+d}<br>Win prob: %{{x:.0f}}%<br>Edge: %{{y:.1f}}%<extra></extra>",
        ))

    # Min edge floor
    fig.add_hline(y=MIN_EDGE * 100, line_color=GRAY, line_width=1, line_dash="dash",
                  annotation_text=f"floor {MIN_EDGE*100:.1f}%",
                  annotation_font=dict(color=GRAY, size=9),
                  annotation_position="right")
    fig.add_hline(y=0, line_color="#2d3139", line_width=1)

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text="Edge % surface — win probability × market odds",
        font=dict(size=12, color="#9ca3af"), x=0,
    )
    layout["height"] = 260
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Win probability %", ticksuffix="%")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Edge %", ticksuffix="%")
    layout["legend"] = dict(
        title=dict(text="Odds", font=dict(size=9, color="#9ca3af")),
        font=dict(size=9, color="#9ca3af"),
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------
st.title("🔬 R&D Output")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">Mathematical validation — Sharp Score anatomy, Kelly frontier, edge surface. All charts computed from math_engine directly.</span>',
    unsafe_allow_html=True,
)

st.markdown("---")

# ---------------------------------------------------------------------------
# ① Math Constraint Summary (static table — always visible first)
# ---------------------------------------------------------------------------
_section_header("Math Constraints", "Non-negotiable rules (inherited from V36.1)")

constraint_cols = st.columns(3)
constraints = [
    ("Collar", f"{COLLAR_MIN:+d} → {COLLAR_MAX:+d}", "American odds range"),
    ("Min Edge", f"{MIN_EDGE*100:.1f}%", "Minimum to pass filter"),
    ("Min Books", str(MIN_BOOKS), "For consensus fair prob"),
    ("Kelly Fraction", f"{KELLY_FRACTION:.2f}×", "Fractional multiplier"),
    ("LEAN Cap", "0.5u", "win_prob ≤ 54%"),
    ("STD Cap", "1.0u", "win_prob 54–60%"),
    ("NUCLEAR Cap", "2.0u", "win_prob > 60%"),
    ("SHARP Threshold", f"{SHARP_THRESHOLD:.0f}", "Current pass threshold"),
    ("RLM Trigger", "3% prob shift", "Passive → active on 2nd fetch"),
]

for i, (name, val, desc) in enumerate(constraints):
    col = constraint_cols[i % 3]
    with col:
        st.html(f"""
        <div style="
            background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
            padding:8px 12px; margin-bottom:8px;
        ">
            <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em;">{name.upper()}</div>
            <div style="font-size:1.05rem; font-weight:800; color:{AMBER}; margin:2px 0;">{val}</div>
            <div style="font-size:0.65rem; color:#9ca3af;">{desc}</div>
        </div>
        """)

st.markdown("---")

# ---------------------------------------------------------------------------
# ② Score Anatomy
# ---------------------------------------------------------------------------
_section_header("Sharp Score Anatomy", "Component stacking across representative scenarios")

anatomy_fig = _build_score_anatomy()
st.plotly_chart(anatomy_fig, use_container_width=True, config={"displayModeBar": False})

st.markdown("---")

# ---------------------------------------------------------------------------
# ③ Interactive Score Sandbox
# ---------------------------------------------------------------------------
_section_header(
    "Score Sensitivity Sandbox",
    "Adjust inputs — watch score update live"
)

sb_col1, sb_col2 = st.columns([2, 3])

with sb_col1:
    sb_edge = st.slider("Edge %", min_value=0.0, max_value=15.0, value=7.0, step=0.5, key="sb_edge")
    sb_rlm = st.checkbox("RLM Confirmed (+25 pts)", value=False, key="sb_rlm")
    sb_eff = st.slider("Efficiency gap (0–20)", min_value=0.0, max_value=20.0, value=8.0, step=0.5, key="sb_eff")
    sb_rest = st.slider("Rest edge (0–5)", min_value=0.0, max_value=5.0, value=0.0, step=0.5, key="sb_rest")
    sb_injury = st.slider("Injury leverage (0–5)", min_value=0.0, max_value=5.0, value=0.0, step=0.5, key="sb_injury")
    sb_motiv = st.slider("Motivation (0–3)", min_value=0.0, max_value=3.0, value=0.0, step=0.5, key="sb_motiv")

sb_score, sb_bd = calculate_sharp_score(
    edge_pct=sb_edge / 100,
    rlm_confirmed=sb_rlm,
    efficiency_gap=sb_eff,
    rest_edge=sb_rest,
    injury_leverage=sb_injury,
    motivation=sb_motiv,
)
sb_size = sharp_to_size(sb_score)
sb_pass = sb_score >= SHARP_THRESHOLD

tier_colors = {
    "NUCLEAR_2.0U": RED,
    "STANDARD_1.0U": AMBER,
    "LEAN_0.5U": GREEN,
}
sb_color = tier_colors.get(sb_size, GRAY)
sb_pass_str = "PASS ✓" if sb_pass else f"FAIL — need {SHARP_THRESHOLD:.0f}"

with sb_col2:
    st.html(f"""
    <div style="
        background:#1a1d23; border:2px solid {sb_color}; border-radius:8px;
        padding:20px 24px; text-align:center;
    ">
        <div style="font-size:0.65rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:4px;">SHARP SCORE</div>
        <div style="font-size:3.5rem; font-weight:900; color:{sb_color}; line-height:1;">{sb_score:.0f}</div>
        <div style="font-size:1rem; color:{'#22c55e' if sb_pass else '#ef4444'}; margin-top:6px; font-weight:700;">
            {sb_pass_str}
        </div>
        <div style="font-size:0.75rem; color:{sb_color}; margin-top:4px;">{sb_size.replace('_', ' ')}</div>
    </div>
    <div style="
        display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px;
    ">
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 10px;">
            <div style="font-size:0.58rem; color:#6b7280;">EDGE PTS</div>
            <div style="font-size:0.95rem; font-weight:700; color:{GREEN};">{sb_bd['edge']:.1f} / 40</div>
        </div>
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 10px;">
            <div style="font-size:0.58rem; color:#6b7280;">RLM PTS</div>
            <div style="font-size:0.95rem; font-weight:700; color:{RED};">{sb_bd['rlm']:.1f} / 25</div>
        </div>
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 10px;">
            <div style="font-size:0.58rem; color:#6b7280;">EFFICIENCY PTS</div>
            <div style="font-size:0.95rem; font-weight:700; color:{BLUE};">{sb_bd['efficiency']:.1f} / 20</div>
        </div>
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 10px;">
            <div style="font-size:0.58rem; color:#6b7280;">SITUATIONAL PTS</div>
            <div style="font-size:0.95rem; font-weight:700; color:{AMBER};">{sb_bd['situational']:.1f} / 15</div>
        </div>
    </div>
    <div style="
        background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
        padding:8px 10px; margin-top:8px; font-size:0.68rem; color:#6b7280;
    ">
        Without RLM: ceiling = {min(40 + 20 + 15, 75):.0f} pts (edge+eff+sit only) — LEAN tier max
    </div>
    """)

st.markdown("---")

# ---------------------------------------------------------------------------
# ④ Kelly Frontier + Collar map (side by side)
# ---------------------------------------------------------------------------
_section_header("Kelly Frontier & Collar Map", "Bet sizing across the odds/winprob space")

kf_col1, kf_col2 = st.columns([3, 2])

with kf_col1:
    kelly_fig = _build_kelly_frontier()
    st.plotly_chart(kelly_fig, use_container_width=True, config={"displayModeBar": False})

with kf_col2:
    collar_fig = _build_collar_map()
    st.plotly_chart(collar_fig, use_container_width=True, config={"displayModeBar": False})

    # Kelly insight card
    st.html(f"""
    <div style="
        background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
        padding:12px 14px; font-size:0.72rem; color:#9ca3af; margin-top:4px;
    ">
        <strong style="color:{AMBER};">Kelly insight:</strong> At 0.25× fractional,
        full Kelly is dampened 4× vs optimal. Hard caps prevent
        runaway sizing even when the model is very confident.
        <br><br>
        <strong style="color:{AMBER};">Collar insight:</strong> The −180/+150 range
        excludes heavy juice (sharp books price efficiently here) and
        caps underdog exposure. {len([o for o in range(-180, 155, 1)])} valid odds integers.
    </div>
    """)

st.markdown("---")

# ---------------------------------------------------------------------------
# ⑤ Edge Surface + Threshold Analysis (side by side)
# ---------------------------------------------------------------------------
_section_header("Edge Surface & Threshold Analysis", "Win probability → edge → pass/fail")

es_col1, es_col2 = st.columns(2)

with es_col1:
    edge_fig = _build_edge_surface()
    st.plotly_chart(edge_fig, use_container_width=True, config={"displayModeBar": False})

with es_col2:
    thresh_fig = _build_threshold_analysis()
    st.plotly_chart(thresh_fig, use_container_width=True, config={"displayModeBar": False})

# Insight row
st.html(f"""
<div style="
    display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin-top:8px;
">
    <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:10px 14px;">
        <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:4px;">NO-RLM CEILING</div>
        <div style="font-size:1.1rem; font-weight:800; color:{GREEN};">75 pts</div>
        <div style="font-size:0.65rem; color:#9ca3af;">Edge (40) + Efficiency (20) + Situational (15)</div>
    </div>
    <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:10px 14px;">
        <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:4px;">STANDARD MINIMUM</div>
        <div style="font-size:1.1rem; font-weight:800; color:{AMBER};">80 pts</div>
        <div style="font-size:0.65rem; color:#9ca3af;">Requires RLM + solid edge + some efficiency</div>
    </div>
    <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:10px 14px;">
        <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:4px;">NUCLEAR MINIMUM</div>
        <div style="font-size:1.1rem; font-weight:800; color:{RED};">90 pts</div>
        <div style="font-size:0.65rem; color:#9ca3af;">RLM + 10%+ edge + high efficiency + situation</div>
    </div>
</div>
""")

st.markdown("---")

# ---------------------------------------------------------------------------
# ⑥ CLV Tracker (live data from CSV log)
# ---------------------------------------------------------------------------
_section_header(
    "CLV Tracker",
    f"Closing Line Value accumulated across graded bets · gate = {CLV_GATE} entries",
)

_clv_log_path = str(ROOT / "data" / "clv_log.csv")
try:
    _entries = read_clv_log(log_path=_clv_log_path)
except Exception:
    _entries = []

_summary = clv_summary(_entries)
_n = _summary["n"]

# KPI strip
_c1, _c2, _c3, _c4, _c5 = st.columns(5)
_kpis = [
    ("Entries", str(_n), "#e5e7eb"),
    ("Avg CLV", f"{_summary['avg_clv_pct']:+.2f}%" if _n else "—",
     GREEN if _summary["avg_clv_pct"] >= 0 else RED),
    ("+ Rate", f"{_summary['positive_rate']:.0%}" if _n else "—",
     GREEN if _summary.get("positive_rate", 0) >= 0.5 else AMBER),
    ("Max", f"{_summary['max_clv_pct']:+.2f}%" if _n else "—", GREEN),
    ("Verdict", _summary["verdict"],
     AMBER if _summary["below_gate"] else (
         GREEN if _summary["verdict"] == "STRONG EDGE CAPTURE"
         else (AMBER if _summary["verdict"] == "MARGINAL" else RED)
     )),
]
for _col, (_label, _val, _color) in zip([_c1, _c2, _c3, _c4, _c5], _kpis):
    with _col:
        st.html(f"""
        <div style="
            background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
            padding:8px 12px;
        ">
            <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.1em;">{_label.upper()}</div>
            <div style="font-size:0.95rem; font-weight:800; color:{_color}; margin-top:2px;">{_val}</div>
        </div>
        """)

if _n == 0:
    st.html("""
    <div style="
        background:#1a1d23; border:1px dashed #2d3139; border-radius:6px;
        padding:20px; text-align:center; color:#6b7280; font-size:0.8rem;
        margin-top:8px;
    ">
        No CLV data yet. Grade bets in the Bet Tracker tab with a close price
        to begin accumulating CLV observations.
        <br><br>Gate: 30 entries required for statistical verdict.
    </div>
    """)
else:
    _clv_tab1, _clv_tab2 = st.tabs(["Grade Distribution", "CLV History"])

    with _clv_tab1:
        _grade_order = ["EXCELLENT", "GOOD", "NEUTRAL", "POOR"]
        _grade_colors = {"EXCELLENT": GREEN, "GOOD": "#4ade80", "NEUTRAL": GRAY, "POOR": RED}
        _grade_counts = {g: 0 for g in _grade_order}
        for _e in _entries:
            _g = _e.get("grade", "NEUTRAL")
            if _g in _grade_counts:
                _grade_counts[_g] += 1

        _fig_grades = go.Figure(data=go.Bar(
            x=_grade_order,
            y=[_grade_counts[g] for g in _grade_order],
            marker_color=[_grade_colors[g] for g in _grade_order],
            text=[str(_grade_counts[g]) for g in _grade_order],
            textposition="outside",
            textfont=dict(color="#d1d5db", size=10),
        ))
        _layout_g = dict(PLOTLY_BASE)
        _layout_g["title"] = dict(
            text=f"CLV Grade Distribution ({_n} entries)",
            font=dict(size=12, color="#9ca3af"), x=0,
        )
        _layout_g["height"] = 240
        _layout_g["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Count")
        _layout_g["showlegend"] = False
        _fig_grades.update_layout(**_layout_g)
        st.plotly_chart(_fig_grades, use_container_width=True, config={"displayModeBar": False})

        _gate_pct = min(_n / CLV_GATE, 1.0) * 100
        _bar_color = GREEN if _n >= CLV_GATE else AMBER
        st.html(f"""
        <div style="margin-top:6px;">
            <div style="font-size:0.6rem; color:#6b7280; margin-bottom:4px; letter-spacing:0.08em;">
                GATE PROGRESS — {_n}/{CLV_GATE} entries ({_gate_pct:.0f}%)
            </div>
            <div style="background:#1a1d23; border-radius:4px; height:6px; overflow:hidden;">
                <div style="
                    background:{_bar_color}; height:100%; width:{_gate_pct:.1f}%;
                    border-radius:4px;
                "></div>
            </div>
        </div>
        """)

    with _clv_tab2:
        _recent = list(reversed(_entries[-50:]))
        if _recent:
            _clv_vals = [e.get("clv_pct", 0) for e in _recent]
            _colors_scatter = [GREEN if v >= 0 else RED for v in _clv_vals]

            _fig_hist = go.Figure()
            _fig_hist.add_trace(go.Scatter(
                x=list(range(len(_clv_vals))),
                y=_clv_vals,
                mode="markers+lines",
                marker=dict(color=_colors_scatter, size=6, line=dict(width=0)),
                line=dict(color="#2d3139", width=1),
                hovertemplate="Entry %{x}<br>CLV: %{y:+.2f}%<extra></extra>",
                name="CLV",
            ))
            _fig_hist.add_hline(y=0, line_color="#6b7280", line_width=1, line_dash="dash")
            _fig_hist.add_hline(
                y=_summary["avg_clv_pct"],
                line_color=AMBER, line_width=1, line_dash="dot",
                annotation_text=f"avg {_summary['avg_clv_pct']:+.2f}%",
                annotation_font=dict(color=AMBER, size=9),
                annotation_position="right",
            )
            _layout_h = dict(PLOTLY_BASE)
            _layout_h["title"] = dict(
                text=f"CLV per bet — last {len(_clv_vals)} entries",
                font=dict(size=12, color="#9ca3af"), x=0,
            )
            _layout_h["height"] = 240
            _layout_h["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="CLV %", ticksuffix="%")
            _layout_h["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Entry #")
            _layout_h["showlegend"] = False
            _fig_hist.update_layout(**_layout_h)
            st.plotly_chart(_fig_hist, use_container_width=True, config={"displayModeBar": False})

st.markdown("---")

# ---------------------------------------------------------------------------
# ⑦ Pinnacle Probe (live data from probe_log.json)
# ---------------------------------------------------------------------------
_section_header(
    "Pinnacle Probe",
    "Bookmaker coverage accumulated from scheduler polls · fires each 5-min cycle",
)

_probe_log_path = str(ROOT / "data" / "probe_log.json")
try:
    _probe_entries = read_probe_log(log_path=_probe_log_path)
except Exception:
    _probe_entries = []

_psummary = probe_summary(_probe_entries)
_pn = _psummary["n_probes"]

# KPI strip
_p1, _p2, _p3, _p4 = st.columns(4)
_pinnacle_color = GREEN if _psummary["pinnacle_present"] else RED
_pkpis = [
    ("Probes", str(_pn), "#e5e7eb"),
    ("Pinnacle", "YES" if _psummary["pinnacle_present"] else "NO", _pinnacle_color),
    ("Pinnacle Rate", f"{_psummary['pinnacle_rate']:.1%}" if _pn else "—",
     GREEN if _psummary["pinnacle_rate"] > 0 else GRAY),
    ("Books Seen", str(len(_psummary["all_books_seen"])), AMBER),
]
for _pcol, (_plabel, _pval, _pcolor) in zip([_p1, _p2, _p3, _p4], _pkpis):
    with _pcol:
        st.html(f"""
        <div style="
            background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
            padding:8px 12px;
        ">
            <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.1em;">{_plabel.upper()}</div>
            <div style="font-size:0.95rem; font-weight:800; color:{_pcolor}; margin-top:2px;">{_pval}</div>
        </div>
        """)

if _pn == 0:
    st.html("""
    <div style="
        background:#1a1d23; border:1px dashed #2d3139; border-radius:6px;
        padding:20px; text-align:center; color:#6b7280; font-size:0.8rem;
        margin-top:8px;
    ">
        No probe data yet. The scheduler logs bookmaker coverage automatically
        on every 5-minute poll. Check back after the first fetch fires.
        <br><br>Pinnacle is not available on all API tiers — this panel confirms
        whether our key has access.
    </div>
    """)
else:
    _pb_tab1, _pb_tab2 = st.tabs(["Book Coverage", "Probe History"])

    with _pb_tab1:
        # Preferred book hit rate bar chart
        _from_core = __import__("core.odds_fetcher", fromlist=["PREFERRED_BOOKS"])
        _pref_books = _from_core.PREFERRED_BOOKS
        _pref_counts = _psummary.get("preferred_coverage", {})

        _fig_books = go.Figure(data=go.Bar(
            x=_pref_books,
            y=[_pref_counts.get(b, 0) for b in _pref_books],
            marker_color=[
                GREEN if _pref_counts.get(b, 0) > 0 else GRAY
                for b in _pref_books
            ],
            text=[str(_pref_counts.get(b, 0)) for b in _pref_books],
            textposition="outside",
            textfont=dict(color="#d1d5db", size=10),
        ))
        _layout_pb = dict(PLOTLY_BASE)
        _layout_pb["title"] = dict(
            text=f"Preferred Book Hit Rate — times seen in {_pn} probes",
            font=dict(size=12, color="#9ca3af"), x=0,
        )
        _layout_pb["height"] = 220
        _layout_pb["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Times seen")
        _layout_pb["showlegend"] = False
        _fig_books.update_layout(**_layout_pb)
        st.plotly_chart(_fig_books, use_container_width=True, config={"displayModeBar": False})

        # All books ever seen
        if _psummary["all_books_seen"]:
            _all_seen_str = " · ".join(_psummary["all_books_seen"])
            st.html(f"""
            <div style="
                background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
                padding:8px 12px; margin-top:4px; font-size:0.7rem; color:#9ca3af;
            ">
                <span style="color:{AMBER}; font-weight:600;">All books seen:</span>
                {_all_seen_str}
            </div>
            """)

        # Pinnacle verdict card
        _verdict_color = GREEN if _psummary["pinnacle_present"] else RED
        _verdict_text = (
            "Pinnacle is available on this API tier. "
            "Consider adding to PREFERRED_BOOKS for sharper consensus pricing."
            if _psummary["pinnacle_present"]
            else "Pinnacle is NOT available on this API tier. "
                 "DraftKings remains primary book. No action needed."
        )
        st.html(f"""
        <div style="
            background:#1a1d23; border-left:4px solid {_verdict_color};
            border-radius:4px; padding:10px 14px; margin-top:8px;
            font-size:0.72rem; color:#9ca3af;
        ">
            <strong style="color:{_verdict_color};">
                {'✓ PINNACLE AVAILABLE' if _psummary['pinnacle_present'] else '✗ PINNACLE ABSENT'}
            </strong>
            &nbsp;—&nbsp;{_verdict_text}
        </div>
        """)

    with _pb_tab2:
        # Pinnacle presence over probe history (binary scatter: 1=present, 0=absent)
        _recent_probes = list(reversed(_probe_entries[-60:]))
        if _recent_probes:
            _pvals = [1 if e.get("pinnacle_present") else 0 for e in _recent_probes]
            _pcolors = [GREEN if v else RED for v in _pvals]
            _n_books_trend = [e.get("n_books", 0) for e in _recent_probes]

            _fig_ph = go.Figure()
            _fig_ph.add_trace(go.Scatter(
                x=list(range(len(_pvals))),
                y=_n_books_trend,
                mode="markers+lines",
                marker=dict(color=_pcolors, size=7, line=dict(width=0)),
                line=dict(color="#2d3139", width=1),
                hovertemplate="Probe %{x}<br>Books: %{y}<br>Pinnacle: " +
                              "<br>".join(
                                  ["present" if v else "absent" for v in _pvals]
                              )[:20] + "<extra></extra>",
                name="n_books",
            ))
            _layout_ph = dict(PLOTLY_BASE)
            _layout_ph["title"] = dict(
                text=f"Book count per probe — last {len(_pvals)} entries "
                     f"(green=pinnacle present, red=absent)",
                font=dict(size=12, color="#9ca3af"), x=0,
            )
            _layout_ph["height"] = 220
            _layout_ph["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="# Books")
            _layout_ph["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Probe #")
            _layout_ph["showlegend"] = False
            _fig_ph.update_layout(**_layout_ph)
            st.plotly_chart(_fig_ph, use_container_width=True, config={"displayModeBar": False})

        if _psummary["last_seen"]:
            st.html(f"""
            <div style="font-size:0.6rem; color:#6b7280; margin-top:4px;">
                Last probe: {_psummary['last_seen'][:19].replace('T', ' ')} UTC ·
                Sports: {', '.join(_psummary['sports_probed']) or '—'}
            </div>
            """)
