"""
pages/03_line_history.py — Line History Tab (Priority 1)

Displays:
1. Flagged line movements (delta > 3 pts) — sorted by magnitude
2. Full line history for selected event
3. RLM seed data — open prices cached from first snapshot
4. System stats: snapshot count, last poll time

Design:
- Dark terminal aesthetic with amber accent
- st.html() for flagged movement cards (not markdown)
- st.dataframe() with column_config for typed columns
- Inline Plotly dark charts for line movement over time
- Graceful degradation when no data exists
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.line_logger import (
    count_snapshots,
    get_line_history,
    get_movements,
    get_open_prices_for_rlm,
)
from core.scheduler import get_status

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = str(ROOT / "data" / "line_history.db")

PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0e1117",
    plot_bgcolor="#13161d",
    font=dict(color="#d1d5db", size=11, family="monospace"),
    margin=dict(l=40, r=20, t=30, b=40),
    xaxis=dict(gridcolor="#2d3139", linecolor="#2d3139", tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#2d3139", linecolor="#2d3139", tickfont=dict(size=10)),
    hoverlabel=dict(bgcolor="#1a1d23", bordercolor="#2d3139", font_color="#f3f4f6"),
    showlegend=True,
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="#2d3139",
        font=dict(size=10, color="#9ca3af"),
    ),
)

SPORT_OPTIONS = ["All", "NBA", "NFL", "NCAAB", "MLB", "NHL", "Soccer"]
MARKET_LABELS = {
    "spreads": "Spread",
    "totals": "Total",
    "h2h": "ML",
}


# ---------------------------------------------------------------------------
# Helper: render a flagged movement card
# ---------------------------------------------------------------------------
def _movement_card(row: dict) -> str:
    delta = row.get("movement_delta", 0.0)
    sport = row.get("sport", "?").upper()
    matchup = row.get("matchup", "?")
    team = row.get("team", "?")
    mkt = MARKET_LABELS.get(row.get("market_type", ""), row.get("market_type", ""))
    open_line = row.get("open_line", 0.0)
    current_line = row.get("current_line", 0.0)
    open_price = row.get("open_price")
    current_price = row.get("current_price")
    n_snaps = row.get("n_snapshots", 1)
    last_updated = row.get("last_updated", "")
    flagged = row.get("flagged", False)

    # Direction indicator
    direction = "▲" if delta > 0 else "▼"
    delta_color = "#22c55e" if delta > 0 else "#ef4444"

    # Price change display
    price_html = ""
    if open_price is not None and current_price is not None and open_price != current_price:
        p_delta = current_price - open_price
        p_dir = "+" if p_delta > 0 else ""
        price_html = f"""
        <span style="font-size:0.7rem; color:#9ca3af; margin-left:8px;">
            price: {open_price:+d} → <strong style="color:#e5e7eb;">{current_price:+d}</strong>
            <span style="color:{delta_color};">({p_dir}{p_delta})</span>
        </span>
        """

    flag_badge = ""
    if flagged:
        flag_badge = """
        <span style="
            background:#f59e0b; color:#000; font-size:0.6rem;
            font-weight:700; padding:1px 5px; border-radius:3px;
            letter-spacing:0.06em; margin-left:6px;
        ">FLAG</span>
        """

    ts_str = ""
    if last_updated:
        try:
            ts = datetime.fromisoformat(last_updated)
            ts_str = ts.strftime("%m/%d %H:%M")
        except ValueError:
            ts_str = last_updated[:16]

    return f"""
    <div style="
        background: #1a1d23;
        border: 1px solid #2d3139;
        border-left: 3px solid {delta_color};
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 8px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="
                    font-size:0.6rem; font-weight:600; letter-spacing:0.1em;
                    color:#6b7280; margin-right:6px;
                ">{sport} · {mkt}</span>
                <span style="font-size:0.85rem; font-weight:600; color:#e5e7eb;">{team}</span>
                {flag_badge}
                <div style="font-size:0.7rem; color:#6b7280; margin-top:2px;">{matchup}</div>
            </div>
            <div style="text-align:right;">
                <div>
                    <span style="font-size:0.75rem; color:#9ca3af;">
                        {open_line:+.1f} → <strong style="color:#e5e7eb;">{current_line:+.1f}</strong>
                    </span>
                    <span style="
                        font-size:1rem; font-weight:700; color:{delta_color};
                        margin-left:8px;
                    ">{direction} {abs(delta):.1f}</span>
                </div>
                {price_html}
                <div style="font-size:0.6rem; color:#4b5563; margin-top:3px;">
                    {n_snaps} snapshots · {ts_str}
                </div>
            </div>
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Helper: line movement sparkline (Plotly)
# ---------------------------------------------------------------------------
def _build_sparkline(history: list[dict], team: str) -> go.Figure:
    if not history:
        return None

    timestamps = []
    lines = []
    prices = []
    for row in history:
        ts_raw = row.get("last_updated", "")
        try:
            ts = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            continue
        timestamps.append(ts)
        lines.append(row.get("current_line", 0.0))
        prices.append(row.get("current_price"))

    if len(timestamps) < 2:
        return None

    fig = go.Figure()

    # Line movement trace
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=lines,
            mode="lines+markers",
            name="Line",
            line=dict(color="#f59e0b", width=2),
            marker=dict(size=5, color="#f59e0b"),
            hovertemplate="%{x|%H:%M}<br>Line: %{y:+.1f}<extra></extra>",
        )
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["title"] = dict(
        text=f"Line Movement — {team}",
        font=dict(size=12, color="#9ca3af"),
        x=0,
    )
    layout["height"] = 200
    layout["xaxis"] = dict(
        **PLOTLY_LAYOUT["xaxis"],
        tickformat="%H:%M",
        nticks=6,
    )
    layout["yaxis"] = dict(
        **PLOTLY_LAYOUT["yaxis"],
        ticksuffix="",
    )
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("📈 Line History")

# --- System status bar ---
try:
    sched_status = get_status()
    stats = count_snapshots(DB_PATH)

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Total Lines Tracked", f"{stats.get('total_lines', 0):,}")
    with col_b:
        st.metric("Distinct Games", f"{stats.get('distinct_events', 0):,}")
    with col_c:
        st.metric("Flagged Movements", f"{stats.get('flagged', 0):,}")
    with col_d:
        is_running = sched_status.get("running", False)
        last_poll = sched_status.get("last_poll_time")
        poll_str = last_poll.strftime("%H:%M UTC") if last_poll else "—"
        st.metric(
            "Scheduler",
            "LIVE" if is_running else "IDLE",
            delta=f"Last: {poll_str}",
            delta_color="off",
        )
except Exception:  # noqa: BLE001
    pass

st.markdown("---")

# --- Filters ---
col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
with col_f1:
    sport_filter = st.selectbox("Sport", SPORT_OPTIONS, index=0)
with col_f2:
    min_delta = st.slider("Min movement (pts)", min_value=0.5, max_value=10.0, value=3.0, step=0.5)
with col_f3:
    st.markdown("")  # spacer

# --- Flagged Movements Section ---
st.subheader("Significant Line Movements")

sport_arg = None if sport_filter == "All" else sport_filter
try:
    movements = get_movements(
        db_path=DB_PATH,
        sport=sport_arg,
        min_delta=min_delta,
        limit=50,
    )
except Exception as exc:
    movements = []
    st.warning(f"Could not load movements: {exc}")

if not movements:
    st.html(
        """
        <div style="
            background: #1a1d23;
            border: 1px solid #2d3139;
            border-radius: 6px;
            padding: 24px 20px;
            text-align: center;
            color: #6b7280;
            font-size: 0.85rem;
        ">
            <div style="font-size:1.4rem; margin-bottom:8px;">—</div>
            No line movements detected yet.<br>
            Scheduler needs to run multiple polls to accumulate deltas.
        </div>
        """
    )
else:
    # Render cards in two columns for visual density
    left_col, right_col = st.columns(2)
    for i, row in enumerate(movements):
        target_col = left_col if i % 2 == 0 else right_col
        with target_col:
            st.html(_movement_card(row))

st.markdown("---")

# --- Drill-down: individual game line history ---
st.subheader("Game Line History")

if movements:
    # Build event options from movements data
    event_options = {}
    for row in movements:
        event_id = row.get("event_id", "")
        matchup = row.get("matchup", event_id)
        sport = row.get("sport", "")
        label = f"[{sport.upper()}] {matchup}"
        if event_id and event_id not in event_options:
            event_options[event_id] = label

    if event_options:
        selected_label = st.selectbox(
            "Select game",
            options=list(event_options.values()),
            index=0,
        )
        selected_event_id = [k for k, v in event_options.items() if v == selected_label]
        selected_event_id = selected_event_id[0] if selected_event_id else None

        if selected_event_id:
            try:
                history = get_line_history(
                    event_id=selected_event_id,
                    db_path=DB_PATH,
                )
            except Exception as exc:
                history = []
                st.warning(f"Could not load history: {exc}")

            if history:
                # Show sparkline
                team_name = history[0].get("team", selected_label)
                fig = _build_sparkline(history, team_name)
                if fig:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

                # Show data table
                import pandas as pd
                df_rows = []
                for h in history:
                    ts_raw = h.get("last_updated", "")
                    try:
                        ts = datetime.fromisoformat(ts_raw).strftime("%m/%d %H:%M")
                    except ValueError:
                        ts = ts_raw
                    df_rows.append({
                        "Time": ts,
                        "Team": h.get("team", ""),
                        "Market": MARKET_LABELS.get(h.get("market_type", ""), h.get("market_type", "")),
                        "Line": f"{h.get('current_line', 0):+.1f}",
                        "Price": f"{h.get('current_price', 0):+d}" if h.get("current_price") else "—",
                        "Δ Line": f"{h.get('movement_delta', 0):+.1f}" if h.get("movement_delta") else "0.0",
                        "Snapshots": h.get("n_snapshots", 1),
                    })
                df = pd.DataFrame(df_rows)
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Time": st.column_config.TextColumn("Time", width=90),
                        "Team": st.column_config.TextColumn("Team", width=150),
                        "Market": st.column_config.TextColumn("Mkt", width=60),
                        "Line": st.column_config.TextColumn("Line", width=70),
                        "Price": st.column_config.TextColumn("Price", width=70),
                        "Δ Line": st.column_config.TextColumn("Δ Line", width=70),
                        "Snapshots": st.column_config.NumberColumn("Polls", width=60),
                    },
                )
            else:
                st.info("No granular history yet — only current state stored for this game.")
else:
    st.html(
        """
        <div style="
            background: #1a1d23;
            border: 1px solid #2d3139;
            border-radius: 6px;
            padding: 16px 20px;
            color: #6b7280;
            font-size: 0.8rem;
        ">
            No games with movement data yet. Start the scheduler and allow multiple polls.
        </div>
        """
    )

st.markdown("---")

# --- RLM Open Price Cache ---
st.subheader("RLM Open Price Seed")
st.markdown(
    '<span style="font-size:0.75rem; color:#6b7280;">Open prices from first snapshot — used by math_engine RLM detector</span>',
    unsafe_allow_html=True,
)

try:
    rlm_data = get_open_prices_for_rlm(
        sport=sport_arg,
        db_path=DB_PATH,
    )
except Exception as exc:
    rlm_data = {}
    st.warning(f"Could not load RLM data: {exc}")

if not rlm_data:
    st.html(
        """
        <div style="
            background: #1a1d23;
            border: 1px solid #2d3139;
            border-radius: 6px;
            padding: 16px 20px;
            color: #6b7280;
            font-size: 0.8rem;
        ">
            No open price data yet. These populate after the first poll.
        </div>
        """
    )
else:
    import pandas as pd

    rows = []
    for event_id, sides in rlm_data.items():
        for side, price in sides.items():
            rows.append({
                "Event ID": event_id[:20] + "..." if len(event_id) > 20 else event_id,
                "Side": side,
                "Open Price": f"{price:+d}" if price else "—",
            })

    if rows:
        df_rlm = pd.DataFrame(rows)
        st.dataframe(
            df_rlm,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Event ID": st.column_config.TextColumn("Event ID", width=200),
                "Side": st.column_config.TextColumn("Side", width=120),
                "Open Price": st.column_config.TextColumn("Open Price (American)", width=160),
            },
        )
        st.caption(f"{len(rows)} sides tracked across {len(rlm_data)} events")
