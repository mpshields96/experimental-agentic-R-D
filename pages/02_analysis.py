"""
pages/02_analysis.py — Analysis Tab (Session 4)

Four panels — all degrade gracefully if data is sparse:

1. P&L Over Time      — cumulative profit chart by logged_at
2. CLV Distribution   — histogram of closing line value, with +/- annotation
3. Edge % Distribution — histogram of edge_pct from bet_log + live snapshot stats
4. ROI by Sport/Type  — bar chart breakdown

Plus a Line Pressure panel — uses line_history to show:
    - Price-implied probability vs open price for all tracked lines
    - Distribution of movement deltas (RLM seed visualization)

Design:
- Dark terminal aesthetic, Plotly dark charts, amber accent
- st.html() for section headers (not st.subheader — keeps font consistency)
- Graceful "no data" states for every section
- No narrative — numbers and charts only
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.line_logger import get_bets, get_movements, get_pnl_summary, count_snapshots
from core.math_engine import implied_probability

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = str(ROOT / "data" / "line_history.db")

PLOTLY_BASE = dict(
    paper_bgcolor="#0e1117",
    plot_bgcolor="#13161d",
    font=dict(color="#d1d5db", size=11, family="monospace"),
    margin=dict(l=50, r=20, t=40, b=50),
    xaxis=dict(gridcolor="#2d3139", linecolor="#2d3139", tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#2d3139", linecolor="#2d3139", tickfont=dict(size=10)),
    hoverlabel=dict(bgcolor="#1a1d23", bordercolor="#2d3139", font_color="#f3f4f6"),
)
AMBER = "#f59e0b"
GREEN = "#22c55e"
RED = "#ef4444"
GRAY = "#6b7280"
SPORT_OPTIONS = ["All", "NBA", "NFL", "NCAAB", "MLB", "NHL", "Soccer"]
MARKET_DISPLAY = {"spreads": "Spread", "h2h": "ML", "totals": "Total"}


# ---------------------------------------------------------------------------
# Section header helper
# ---------------------------------------------------------------------------
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


def _no_data_card(msg: str) -> None:
    st.html(f"""
    <div style="
        background:#1a1d23; border:1px solid #2d3139; border-radius:6px;
        padding:24px 20px; text-align:center; color:#6b7280; font-size:0.82rem;
    ">
        <div style="font-size:1.3rem; margin-bottom:8px;">—</div>
        {msg}
    </div>
    """)


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_cumulative_pnl(bets: list[dict]):
    """Cumulative P&L line chart — resolved bets only."""
    resolved = [b for b in bets if b["result"] in ("win", "loss", "void")]
    if len(resolved) < 2:
        return None

    resolved.sort(key=lambda b: b.get("logged_at", ""))

    dates = []
    cumulative = []
    running = 0.0
    for b in resolved:
        ts_raw = b.get("logged_at", "")
        try:
            ts = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            continue
        running += b.get("profit", 0.0)
        dates.append(ts)
        cumulative.append(round(running, 2))

    if len(dates) < 2:
        return None

    final_color = GREEN if cumulative[-1] >= 0 else RED

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=cumulative,
        mode="lines+markers",
        name="Cumulative P&L",
        line=dict(color=final_color, width=2),
        marker=dict(size=5, color=final_color),
        fill="tozeroy",
        fillcolor="rgba(34,197,94,0.08)" if final_color == GREEN else "rgba(239,68,68,0.08)",
        hovertemplate="%{x|%m/%d %H:%M}<br>P&L: %{y:+.2f}u<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#2d3139", line_width=1)

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="Cumulative P&L (units)", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 250
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], ticksuffix="u")
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], tickformat="%m/%d")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


def _build_clv_histogram(bets: list[dict]):
    """CLV distribution histogram — bets with recorded close price only."""
    clv_values = [b["clv"] * 100 for b in bets if b.get("clv") not in (None, 0.0)]
    if len(clv_values) < 3:
        return None

    avg_clv = sum(clv_values) / len(clv_values)
    pos_count = sum(1 for c in clv_values if c > 0)
    neg_count = sum(1 for c in clv_values if c < 0)

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=clv_values,
        nbinsx=15,
        marker_color=AMBER,
        opacity=0.75,
        name="CLV %",
        hovertemplate="CLV: %{x:.1f}%<br>Count: %{y}<extra></extra>",
    ))
    fig.add_vline(
        x=avg_clv,
        line_color=GREEN if avg_clv >= 0 else RED,
        line_width=1.5, line_dash="dash",
        annotation_text=f"avg {avg_clv:+.1f}%",
        annotation_font=dict(color="#d1d5db", size=10),
        annotation_position="top right",
    )

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(
        text=f"CLV Distribution — {pos_count}+ / {neg_count}−",
        font=dict(size=12, color="#9ca3af"), x=0,
    )
    layout["height"] = 220
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="CLV %", ticksuffix="%")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Count")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


def _build_edge_histogram(bets: list[dict]):
    """Edge% histogram from logged bets."""
    edges = [b["edge_pct"] * 100 for b in bets if b.get("edge_pct") not in (None, 0.0)]
    if len(edges) < 3:
        return None

    avg_edge = sum(edges) / len(edges)

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=edges,
        nbinsx=12,
        marker_color=GREEN,
        opacity=0.75,
        name="Edge %",
        hovertemplate="Edge: %{x:.1f}%<br>Count: %{y}<extra></extra>",
    ))
    fig.add_vline(
        x=avg_edge, line_color=AMBER, line_width=1.5, line_dash="dash",
        annotation_text=f"avg {avg_edge:.1f}%",
        annotation_font=dict(color="#d1d5db", size=10),
        annotation_position="top right",
    )
    fig.add_vline(
        x=3.5, line_color=GRAY, line_width=1, line_dash="dot",
        annotation_text="floor 3.5%",
        annotation_font=dict(color=GRAY, size=9),
        annotation_position="bottom right",
    )

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="Edge % at Bet Time", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 220
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Edge %", ticksuffix="%")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Count")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


def _build_roi_by_sport(bets: list[dict]):
    """ROI% bar chart by sport (resolved bets only)."""
    resolved = [b for b in bets if b["result"] in ("win", "loss")]
    if not resolved:
        return None

    sport_data: dict = {}
    for b in resolved:
        sport = b.get("sport", "?")
        if sport not in sport_data:
            sport_data[sport] = {"profit": 0.0, "stake": 0.0, "count": 0}
        sport_data[sport]["profit"] += b.get("profit", 0.0)
        sport_data[sport]["stake"] += b.get("stake", 0.0)
        sport_data[sport]["count"] += 1

    sports, rois, counts = [], [], []
    for sport, d in sorted(sport_data.items()):
        if d["stake"] > 0:
            sports.append(sport)
            rois.append(round(d["profit"] / d["stake"] * 100, 1))
            counts.append(d["count"])

    if not sports:
        return None

    bar_colors = [GREEN if r >= 0 else RED for r in rois]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sports, y=rois,
        marker_color=bar_colors, opacity=0.8,
        text=[f"{r:+.1f}%\n({c})" for r, c in zip(rois, counts)],
        textposition="outside",
        textfont=dict(size=10, color="#9ca3af"),
        hovertemplate="%{x}<br>ROI: %{y:+.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#2d3139", line_width=1)

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="ROI % by Sport", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 220
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="ROI %", ticksuffix="%")
    layout["showlegend"] = False
    layout["bargap"] = 0.3
    fig.update_layout(**layout)
    return fig


def _build_roi_by_market(bets: list[dict]):
    """ROI% bar chart by market type (resolved bets only)."""
    resolved = [b for b in bets if b["result"] in ("win", "loss")]
    if not resolved:
        return None

    mkt_data: dict = {}
    for b in resolved:
        mkt = MARKET_DISPLAY.get(b.get("market_type", ""), b.get("market_type", "?"))
        if mkt not in mkt_data:
            mkt_data[mkt] = {"profit": 0.0, "stake": 0.0, "count": 0}
        mkt_data[mkt]["profit"] += b.get("profit", 0.0)
        mkt_data[mkt]["stake"] += b.get("stake", 0.0)
        mkt_data[mkt]["count"] += 1

    markets, rois, counts = [], [], []
    for mkt, d in sorted(mkt_data.items()):
        if d["stake"] > 0:
            markets.append(mkt)
            rois.append(round(d["profit"] / d["stake"] * 100, 1))
            counts.append(d["count"])

    if not markets:
        return None

    bar_colors = [GREEN if r >= 0 else RED for r in rois]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=markets, y=rois,
        marker_color=bar_colors, opacity=0.8,
        text=[f"{r:+.1f}%\n({c})" for r, c in zip(rois, counts)],
        textposition="outside",
        textfont=dict(size=10, color="#9ca3af"),
        hovertemplate="%{x}<br>ROI: %{y:+.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#2d3139", line_width=1)

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="ROI % by Market Type", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 220
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="ROI %", ticksuffix="%")
    layout["showlegend"] = False
    layout["bargap"] = 0.4
    fig.update_layout(**layout)
    return fig


def _build_movement_delta_hist(movements: list[dict]):
    """Distribution of line movement deltas from line_history."""
    deltas = [abs(m.get("movement_delta", 0)) for m in movements if m.get("movement_delta")]
    if len(deltas) < 3:
        return None

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=deltas, nbinsx=15,
        marker_color=AMBER, opacity=0.75,
        name="Δ Line",
        hovertemplate="Δ %{x:.1f} pts<br>Count: %{y}<extra></extra>",
    ))

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="Line Movement Delta Distribution", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 200
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Absolute Δ pts")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Count")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


def _build_price_shift_scatter(movements: list[dict]):
    """Scatter: open price implied prob vs current price implied prob."""
    x_vals, y_vals, labels = [], [], []
    for m in movements:
        op = m.get("open_price")
        cp = m.get("current_price")
        team = m.get("team", "")
        if op and cp and op != 0 and cp != 0:
            try:
                x_vals.append(round(implied_probability(op) * 100, 1))
                y_vals.append(round(implied_probability(cp) * 100, 1))
                labels.append(team[:20])
            except (ValueError, ZeroDivisionError):
                continue

    if len(x_vals) < 3:
        return None

    colors = [GREEN if y > x else RED for x, y in zip(x_vals, y_vals)]

    fig = go.Figure()
    all_vals = x_vals + y_vals
    _min, _max = min(all_vals) - 2, max(all_vals) + 2
    fig.add_trace(go.Scatter(
        x=[_min, _max], y=[_min, _max],
        mode="lines", name="No movement",
        line=dict(color=GRAY, width=1, dash="dot"),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=x_vals, y=y_vals,
        mode="markers",
        name="Line",
        marker=dict(color=colors, size=6, opacity=0.7),
        text=labels,
        hovertemplate="%{text}<br>Open: %{x:.1f}%<br>Current: %{y:.1f}%<extra></extra>",
    ))

    layout = dict(PLOTLY_BASE)
    layout["title"] = dict(text="Price Implied Prob: Open → Current", font=dict(size=12, color="#9ca3af"), x=0)
    layout["height"] = 240
    layout["xaxis"] = dict(**PLOTLY_BASE["xaxis"], title="Open implied %", ticksuffix="%")
    layout["yaxis"] = dict(**PLOTLY_BASE["yaxis"], title="Current implied %", ticksuffix="%")
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("📊 Analysis")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">Performance analytics — P&L, CLV, edge distribution, line pressure</span>',
    unsafe_allow_html=True,
)

# --- Filter ---
col_f1, col_f2 = st.columns([2, 5])
with col_f1:
    sport_filter = st.selectbox("Sport", SPORT_OPTIONS, key="an_sport")

sport_arg = None if sport_filter == "All" else sport_filter

st.markdown("---")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120, show_spinner=False)
def _load_data(sport_arg):
    bets = get_bets(sport_filter=sport_arg, limit=500, db_path=DB_PATH)
    pnl = get_pnl_summary(db_path=DB_PATH)
    movements = get_movements(db_path=DB_PATH, sport=sport_arg, min_delta=0.5, limit=500)
    snap_stats = count_snapshots(DB_PATH)
    return bets, pnl, movements, snap_stats

try:
    bets, pnl, movements, snap_stats = _load_data(sport_arg)
except Exception as exc:
    st.error(f"Data load failed: {exc}")
    bets, pnl, movements, snap_stats = [], {}, [], {}

n_resolved = len([b for b in bets if b["result"] in ("win", "loss")])
n_bets = pnl.get("total_bets", 0)

# ---------------------------------------------------------------------------
# ① Summary KPI bar
# ---------------------------------------------------------------------------
_section_header(
    "Performance Summary",
    f"{n_bets} total bets · {n_resolved} resolved · {snap_stats.get('total_lines', 0):,} lines tracked"
)

k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    st.metric("Total Bets", pnl.get("total_bets", 0))
with k2:
    wins = pnl.get("wins", 0)
    losses = pnl.get("losses", 0)
    st.metric("Record", f"{wins}W / {losses}L")
with k3:
    st.metric("Win Rate", f"{pnl.get('win_rate', 0.0):.1f}%")
with k4:
    roi = pnl.get("roi_pct", 0.0)
    st.metric("ROI", f"{roi:+.1f}%")
with k5:
    avg_clv = pnl.get("avg_clv", 0.0) * 100
    st.metric("Avg CLV", f"{avg_clv:+.2f}%")
with k6:
    st.metric("Pending", pnl.get("pending", 0))

st.markdown("---")

# ---------------------------------------------------------------------------
# ② P&L Over Time
# ---------------------------------------------------------------------------
_section_header("P&L Over Time", "Cumulative units — resolved bets only")

if n_resolved < 2:
    _no_data_card(
        f"Need ≥ 2 resolved bets to plot. Currently {n_resolved} resolved.<br>"
        "Grade bets in Bet Tracker tab to populate this chart."
    )
else:
    pnl_fig = _build_cumulative_pnl(bets)
    if pnl_fig:
        st.plotly_chart(pnl_fig, use_container_width=True, config={"displayModeBar": False})
    else:
        _no_data_card("Could not build P&L chart — check logged_at timestamps in bet_log.")

st.markdown("---")

# ---------------------------------------------------------------------------
# ③ Edge% and CLV Distributions
# ---------------------------------------------------------------------------
_section_header("Distribution Analysis", "Edge% at bet time | CLV post-game")

dist_col1, dist_col2 = st.columns(2)

with dist_col1:
    if len(bets) >= 3:
        edge_fig = _build_edge_histogram(bets)
        if edge_fig:
            st.plotly_chart(edge_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _no_data_card("No edge data in bet log yet.")
    else:
        _no_data_card(f"Need ≥ 3 logged bets for edge histogram. Currently {len(bets)}.")

with dist_col2:
    clv_bets = [b for b in bets if b.get("clv") not in (None, 0.0)]
    if len(clv_bets) >= 3:
        clv_fig = _build_clv_histogram(bets)
        if clv_fig:
            st.plotly_chart(clv_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _no_data_card("Could not build CLV chart.")
    else:
        _no_data_card(
            f"Need ≥ 3 bets with closing price entered. Currently {len(clv_bets)}.<br>"
            "Enter close price when grading bets in Bet Tracker tab."
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# ④ ROI by Sport and Market
# ---------------------------------------------------------------------------
_section_header("ROI Breakdown", "By sport and market type — resolved bets only")

if n_resolved == 0:
    _no_data_card("No resolved bets yet. Grade bets in the Bet Tracker tab.")
else:
    roi_col1, roi_col2 = st.columns(2)
    with roi_col1:
        sport_fig = _build_roi_by_sport(bets)
        if sport_fig:
            st.plotly_chart(sport_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _no_data_card("Not enough sport data to plot.")
    with roi_col2:
        mkt_fig = _build_roi_by_market(bets)
        if mkt_fig:
            st.plotly_chart(mkt_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _no_data_card("Not enough market data to plot.")

st.markdown("---")

# ---------------------------------------------------------------------------
# ⑤ Line Pressure (from line_history — no bet log required)
# ---------------------------------------------------------------------------
_section_header(
    "Line Pressure",
    f"{snap_stats.get('total_lines', 0):,} tracked lines · "
    f"{snap_stats.get('distinct_events', 0):,} games · "
    f"{len(movements)} with movement ≥ 0.5 pts"
)

if not movements:
    _no_data_card(
        "No line movement data yet.<br>"
        "Scheduler needs multiple polls to accumulate deltas.<br>"
        "Check Line History tab for scheduler status."
    )
else:
    lp_col1, lp_col2 = st.columns(2)
    with lp_col1:
        delta_fig = _build_movement_delta_hist(movements)
        if delta_fig:
            st.plotly_chart(delta_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _no_data_card("Not enough movement data for histogram.")
    with lp_col2:
        scatter_fig = _build_price_shift_scatter(movements)
        if scatter_fig:
            st.plotly_chart(scatter_fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _no_data_card("Need price data on at least 3 lines for scatter.")

    # Movement stats bar
    max_delta = max((abs(m.get("movement_delta", 0)) for m in movements), default=0)
    avg_delta = sum(abs(m.get("movement_delta", 0)) for m in movements) / len(movements)
    flagged_count = snap_stats.get("flagged", 0)

    st.html(f"""
    <div style="
        display:grid; grid-template-columns:1fr 1fr 1fr 1fr;
        gap:8px; margin-top:8px;
    ">
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 12px;">
            <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:2px;">LINES MOVED</div>
            <div style="font-size:1rem; font-weight:700; color:#e5e7eb;">{len(movements)}</div>
        </div>
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 12px;">
            <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:2px;">FLAGGED (≥3 PTS)</div>
            <div style="font-size:1rem; font-weight:700; color:{AMBER};">{flagged_count}</div>
        </div>
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 12px;">
            <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:2px;">MAX |Δ|</div>
            <div style="font-size:1rem; font-weight:700; color:{RED};">{max_delta:.1f} pts</div>
        </div>
        <div style="background:#1a1d23; border:1px solid #2d3139; border-radius:4px; padding:8px 12px;">
            <div style="font-size:0.58rem; color:#6b7280; letter-spacing:0.1em; margin-bottom:2px;">AVG |Δ|</div>
            <div style="font-size:1rem; font-weight:700; color:#e5e7eb;">{avg_delta:.2f} pts</div>
        </div>
    </div>
    """)

st.markdown("---")

# ---------------------------------------------------------------------------
# ⑥ Bet Log Table (full history, filterable)
# ---------------------------------------------------------------------------
_section_header("Bet Log", "Full history with edge, CLV, P&L")

if not bets:
    _no_data_card("No bets logged yet. Use Live Lines → 📋 Log Bet, or enter manually in Bet Tracker.")
else:
    import pandas as pd

    res_f1, _ = st.columns([2, 5])
    with res_f1:
        result_filter = st.selectbox(
            "Result filter",
            ["All", "Pending", "Win", "Loss", "Void"],
            key="an_result",
        )

    rmap = {"Pending": "pending", "Win": "win", "Loss": "loss", "Void": "void"}
    filtered_bets = (
        bets if result_filter == "All"
        else [b for b in bets if b.get("result") == rmap.get(result_filter, "")]
    )

    rows = []
    for b in filtered_bets:
        ts_raw = b.get("logged_at", "")
        try:
            ts = datetime.fromisoformat(ts_raw).strftime("%m/%d %H:%M")
        except (ValueError, TypeError):
            ts = ts_raw[:16] if ts_raw else "—"

        result_raw = b.get("result", "pending")
        result_display = {
            "win": "WIN", "loss": "LOSS", "void": "PUSH/VOID", "pending": "PENDING"
        }.get(result_raw, result_raw.upper())

        clv_val = b.get("clv", 0.0)
        clv_display = f"{clv_val * 100:+.2f}%" if clv_val not in (None, 0.0) else "—"
        close_p = b.get("close_price", 0)
        close_display = f"{close_p:+d}" if close_p else "—"

        rows.append({
            "Date":    ts,
            "Sport":   b.get("sport", ""),
            "Matchup": b.get("matchup", "")[:35],
            "Target":  b.get("target", ""),
            "Mkt":     MARKET_DISPLAY.get(b.get("market_type", ""), b.get("market_type", "?")),
            "Price":   f"{b.get('price', 0):+d}",
            "Edge":    f"{b.get('edge_pct', 0) * 100:.1f}%",
            "Stake":   f"{b.get('stake', 0.0):.1f}u",
            "Result":  result_display,
            "P&L":     f"{b.get('profit', 0.0):+.2f}u",
            "CLV":     clv_display,
            "Close":   close_display,
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date":    st.column_config.TextColumn("Date",    width=90),
            "Sport":   st.column_config.TextColumn("Sport",   width=60),
            "Matchup": st.column_config.TextColumn("Matchup", width=180),
            "Target":  st.column_config.TextColumn("Target",  width=160),
            "Mkt":     st.column_config.TextColumn("Mkt",     width=60),
            "Price":   st.column_config.TextColumn("Price",   width=60),
            "Edge":    st.column_config.TextColumn("Edge %",  width=60),
            "Stake":   st.column_config.TextColumn("Stake",   width=65),
            "Result":  st.column_config.TextColumn("Result",  width=85),
            "P&L":     st.column_config.TextColumn("P&L",     width=70),
            "CLV":     st.column_config.TextColumn("CLV",     width=65),
            "Close":   st.column_config.TextColumn("Close",   width=65),
        },
    )

    total_profit = sum(b.get("profit", 0.0) for b in filtered_bets)
    total_stake = sum(
        b.get("stake", 0.0) for b in filtered_bets if b["result"] in ("win", "loss")
    )
    roi_shown = (total_profit / total_stake * 100) if total_stake > 0 else 0.0
    profit_color = GREEN if total_profit >= 0 else RED

    st.html(f"""
    <div style="
        background:#1a1d23; border:1px solid #2d3139; border-radius:4px;
        padding:8px 14px; margin-top:4px; font-size:0.72rem; color:#6b7280;
        display:flex; gap:24px;
    ">
        <span>Showing: <strong style="color:#e5e7eb;">{len(filtered_bets)}</strong></span>
        <span>Total P&amp;L: <strong style="color:{profit_color};">{total_profit:+.2f}u</strong></span>
        <span>ROI: <strong style="color:{profit_color};">{roi_shown:+.1f}%</strong></span>
    </div>
    """)
