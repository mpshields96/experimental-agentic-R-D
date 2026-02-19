"""
pages/04_bet_tracker.py — Bet Tracker Tab (Session 3)

Full bet lifecycle:
1. Log a bet (manually or pre-filled from Live Lines)
2. Mark result (WIN / LOSS / PUSH) + enter close price for CLV
3. View P&L summary: win rate, ROI, avg edge, avg CLV
4. Filter/sort bet history

P&L Formula (from bet-tracker reference):
    win, positive odds (+150): profit = stake × (odds / 100)
    win, negative odds (-110): profit = stake × (100 / |odds|)
    loss: profit = -stake
    pending: excluded from totals

Design:
- Dark terminal aesthetic consistent with live_lines
- st.html() cards for individual bets
- st.dataframe() with column_config for full history table
- No narrative — numbers only
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.line_logger import (
    get_bets,
    get_pnl_summary,
    log_bet,
    update_bet_result,
)

DB_PATH = str(ROOT / "data" / "line_history.db")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESULT_COLORS = {
    "win":     "#22c55e",
    "loss":    "#ef4444",
    "push":    "#6b7280",
    "pending": "#f59e0b",
}
RESULT_LABELS = {
    "win":     "WIN ✓",
    "loss":    "LOSS ✗",
    "void":    "PUSH/VOID",
    "pending": "PENDING",
}
MARKET_DISPLAY = {"spreads": "SPREAD", "h2h": "ML", "totals": "TOTAL"}


# ---------------------------------------------------------------------------
# P&L helper (matches bet-tracker reference formula exactly)
# ---------------------------------------------------------------------------
def _calc_profit(stake: float, odds: int, result: str) -> float:
    if result in ("pending", "void"):
        return 0.0
    if result == "loss":
        return -stake
    # win
    if odds > 0:
        return stake * (odds / 100)
    else:
        return stake * (100 / abs(odds))


# ---------------------------------------------------------------------------
# Bet card HTML
# ---------------------------------------------------------------------------
def _bet_card(bet: dict, idx: int) -> str:
    result = bet.get("result", "pending")
    color = RESULT_COLORS.get(result, "#6b7280")
    label = RESULT_LABELS.get(result, result.upper())

    stake = bet.get("stake") or 0
    price = bet.get("price", 0)
    edge = bet.get("edge_pct", 0) * 100
    profit = _calc_profit(stake, price, result)
    profit_str = f"+${profit:.2f}" if profit > 0 else (f"${profit:.2f}" if profit < 0 else "—")
    profit_color = "#22c55e" if profit > 0 else ("#ef4444" if profit < 0 else "#6b7280")

    clv = bet.get("clv")
    clv_str = f"{clv*100:+.1f}%" if clv is not None else "—"
    clv_color = "#22c55e" if (clv or 0) > 0 else ("#ef4444" if (clv or 0) < 0 else "#6b7280")

    price_str = f"{price:+d}" if price > 0 else str(price)
    mkt = MARKET_DISPLAY.get(bet.get("market_type", ""), bet.get("market_type", "").upper())
    sport = bet.get("sport", "?").upper()

    logged_at = bet.get("logged_at", "")[:16].replace("T", " ")

    return f"""
    <div style="
        background: #1a1d23;
        border: 1px solid #2d3139;
        border-left: 4px solid {color};
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
                <span style="font-size:0.6rem; color:#6b7280; letter-spacing:0.1em; font-weight:600;">
                    {sport} · {mkt}
                </span>
                <div style="font-size:0.95rem; font-weight:700; color:#e5e7eb; margin-top:2px;">
                    {bet.get("target", bet.get("matchup", ""))}
                </div>
                <div style="font-size:0.7rem; color:#9ca3af;">
                    {bet.get("matchup", "")}
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:1.1rem; font-weight:800; color:{color};">{label}</div>
                <div style="font-size:1.0rem; font-weight:700; color:{profit_color};">{profit_str}</div>
            </div>
        </div>
        <div style="
            display:grid; grid-template-columns:1fr 1fr 1fr 1fr 1fr;
            gap:6px; margin-top:10px;
        ">
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">PRICE</div>
                <div style="font-size:0.85rem; font-weight:600; color:#e5e7eb;">{price_str}</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">STAKE</div>
                <div style="font-size:0.85rem; font-weight:600; color:#e5e7eb;">${stake:.2f}</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">EDGE</div>
                <div style="font-size:0.85rem; font-weight:600; color:#22c55e;">+{edge:.1f}%</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">CLV</div>
                <div style="font-size:0.85rem; font-weight:600; color:{clv_color};">{clv_str}</div>
            </div>
            <div style="background:#0e1117; border-radius:4px; padding:5px 8px;">
                <div style="font-size:0.55rem; color:#6b7280; letter-spacing:0.08em;">LOGGED</div>
                <div style="font-size:0.7rem; color:#9ca3af;">{logged_at}</div>
            </div>
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("📋 Bet Tracker")

# --- P&L Summary bar ---
try:
    summary = get_pnl_summary(DB_PATH)
except Exception:
    summary = {}

total_bets = summary.get("total_bets", 0)
wins = summary.get("wins", 0)
losses = summary.get("losses", 0)
win_rate = summary.get("win_rate", 0)   # already 0-100 from get_pnl_summary
roi = summary.get("roi_pct", 0)
avg_clv = (summary.get("avg_clv") or 0) * 100   # stored as decimal, display as %

s1, s2, s3, s4, s5 = st.columns(5)
with s1:
    st.metric("Total Bets", total_bets)
with s2:
    st.metric("Record", f"{wins}W – {losses}L")
with s3:
    st.metric("Win Rate", f"{win_rate:.1f}%" if total_bets else "—")
with s4:
    roi_str = f"{roi:+.1f}%" if total_bets else "—"
    st.metric("ROI", roi_str)
with s5:
    clv_str = f"{avg_clv:+.2f}%" if total_bets else "—"
    st.metric("Avg CLV", clv_str)

st.markdown("---")

# --- Two-column layout: Log form LEFT, Pending bets RIGHT ---
log_col, pending_col = st.columns([1, 1], gap="large")

with log_col:
    st.subheader("Log a Bet")

    with st.form("log_bet_form", clear_on_submit=True):
        f1, f2 = st.columns(2)
        with f1:
            sport_input = st.selectbox(
                "Sport", ["NBA", "NFL", "NCAAB", "MLB", "NHL", "EPL", "LA_LIGA", "Other"],
                key="bt_sport"
            )
        with f2:
            market_input = st.selectbox(
                "Market", ["spreads", "h2h", "totals"],
                format_func=lambda x: MARKET_DISPLAY.get(x, x),
                key="bt_market"
            )

        target_input = st.text_input(
            "Team / Bet Target",
            placeholder="e.g. Georgia Tech +26.5",
            key="bt_target",
        )
        matchup_input = st.text_input(
            "Matchup",
            placeholder="e.g. Virginia @ Georgia Tech",
            key="bt_matchup",
        )

        p1, p2 = st.columns(2)
        with p1:
            price_input = st.number_input(
                "Price (American odds)", value=-110, step=1,
                min_value=-10000, max_value=10000,
                key="bt_price",
            )
        with p2:
            edge_input = st.number_input(
                "Edge %", value=5.0, step=0.1, min_value=0.0, max_value=100.0,
                key="bt_edge",
            )

        e1, e2 = st.columns(2)
        with e1:
            kelly_input = st.number_input(
                "Kelly size (units)", value=0.5, step=0.5,
                min_value=0.0, max_value=10.0,
                key="bt_kelly",
            )
        with e2:
            stake_input = st.number_input(
                "Stake ($)", value=50.0, step=10.0,
                min_value=0.01,
                key="bt_stake",
            )

        notes_input = st.text_input("Notes (optional)", key="bt_notes")

        submitted = st.form_submit_button("Log Bet", use_container_width=True, type="primary")
        if submitted:
            if not target_input.strip():
                st.error("Target is required.")
            elif price_input == 0:
                st.error("Price cannot be 0.")
            else:
                try:
                    bet_id = log_bet(
                        sport=sport_input,
                        matchup=matchup_input,
                        market_type=market_input,
                        target=target_input.strip(),
                        price=int(price_input),
                        edge_pct=edge_input / 100,
                        kelly_size=kelly_input,
                        stake=stake_input,
                        notes=notes_input,
                        db_path=DB_PATH,
                    )
                    st.success(f"Bet #{bet_id} logged.")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Failed to log bet: {exc}")

with pending_col:
    st.subheader("Pending Bets")
    try:
        pending = get_bets(result_filter="pending", db_path=DB_PATH)
    except Exception:
        pending = []

    if not pending:
        st.html(
            """
            <div style="
                background:#1a1d23; border:1px solid #2d3139;
                border-radius:6px; padding:24px; text-align:center;
                color:#6b7280; font-size:0.85rem;
            ">
                No pending bets.<br>Log a bet on the left.
            </div>
            """
        )
    else:
        for bet in pending:
            bet_id = bet.get("id")
            st.html(_bet_card(bet, bet_id))

            # Grade result inline
            with st.expander(f"Grade #{bet_id} — {bet.get('target','')}", expanded=False):
                gc1, gc2, gc3 = st.columns(3)
                with gc1:
                    result_choice = st.selectbox(
                        "Result",
                        ["win", "loss", "void"],
                        format_func=lambda x: {"win": "WIN", "loss": "LOSS", "void": "PUSH/VOID"}[x],
                        key=f"result_{bet_id}",
                    )
                with gc2:
                    stake_actual = st.number_input(
                        "Actual stake ($)",
                        value=float(bet.get("stake") or 50),
                        min_value=0.01,
                        key=f"stake_{bet_id}",
                    )
                with gc3:
                    close_price = st.number_input(
                        "Close price",
                        value=int(bet.get("price", -110)),
                        step=1,
                        key=f"close_{bet_id}",
                    )
                if st.button(f"Submit result", key=f"grade_{bet_id}", type="primary"):
                    try:
                        update_bet_result(
                            bet_id=bet_id,
                            result=result_choice,
                            stake=stake_actual,
                            close_price=close_price if close_price != 0 else None,
                            db_path=DB_PATH,
                        )
                        st.success("Result saved.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed: {exc}")

st.markdown("---")

# --- Full history table ---
st.subheader("Bet History")

filter_col, sort_col, _ = st.columns([2, 2, 3])
with filter_col:
    result_filter = st.selectbox(
        "Filter by result",
        ["All", "pending", "win", "loss", "void"],
        key="bt_filter",
    )
with sort_col:
    sport_filter = st.selectbox(
        "Filter by sport",
        ["All", "NBA", "NFL", "NCAAB", "MLB", "NHL", "EPL", "LA_LIGA"],
        key="bt_sport_filter",
    )

try:
    rf = None if result_filter == "All" else result_filter
    sf = None if sport_filter == "All" else sport_filter
    all_bets = get_bets(result_filter=rf, sport_filter=sf, db_path=DB_PATH)
except Exception as exc:
    all_bets = []
    st.warning(f"Could not load bets: {exc}")

if not all_bets:
    st.html(
        """
        <div style="
            background:#1a1d23; border:1px solid #2d3139;
            border-radius:6px; padding:20px; text-align:center;
            color:#6b7280; font-size:0.85rem;
        ">No bets match the current filters.</div>
        """
    )
else:
    import pandas as pd

    rows = []
    for b in all_bets:
        stake = b.get("stake") or 0
        price = b.get("price", 0)
        result = b.get("result", "pending")
        profit = _calc_profit(stake, price, result)
        clv = b.get("clv")

        rows.append({
            "#": b.get("id", ""),
            "Logged": (b.get("logged_at") or "")[:16].replace("T", " "),
            "Sport": b.get("sport", ""),
            "Target": b.get("target", b.get("matchup", "")),
            "Price": f"{price:+d}" if price != 0 else "—",
            "Stake": f"${stake:.2f}",
            "Edge%": f"+{b.get('edge_pct',0)*100:.1f}%",
            "Result": RESULT_LABELS.get(result, result.upper()),
            "P&L": f"+${profit:.2f}" if profit > 0 else (f"${profit:.2f}" if profit < 0 else "—"),
            "CLV": f"{clv*100:+.1f}%" if clv is not None else "—",
            "Notes": b.get("notes", "") or "",
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "#":       st.column_config.NumberColumn("#", width=45),
            "Logged":  st.column_config.TextColumn("Logged", width=120),
            "Sport":   st.column_config.TextColumn("Sport", width=70),
            "Target":  st.column_config.TextColumn("Target", width=200),
            "Price":   st.column_config.TextColumn("Price", width=65),
            "Stake":   st.column_config.TextColumn("Stake", width=70),
            "Edge%":   st.column_config.TextColumn("Edge%", width=65),
            "Result":  st.column_config.TextColumn("Result", width=85),
            "P&L":     st.column_config.TextColumn("P&L", width=80),
            "CLV":     st.column_config.TextColumn("CLV", width=65),
            "Notes":   st.column_config.TextColumn("Notes", width=150),
        },
    )

    # Totals row
    total_stake = sum((b.get("stake") or 0) for b in all_bets if b.get("result") != "pending")
    total_pnl = sum(
        _calc_profit(b.get("stake") or 0, b.get("price", 0), b.get("result", "pending"))
        for b in all_bets
    )
    pnl_color = "#22c55e" if total_pnl > 0 else "#ef4444"
    st.html(
        f"""
        <div style="
            background:#1a1d23; border:1px solid #2d3139;
            border-radius:6px; padding:10px 16px; margin-top:6px;
            display:flex; gap:24px; font-size:0.8rem;
        ">
            <span style="color:#6b7280;">
                Showing <strong style="color:#e5e7eb;">{len(all_bets)}</strong> bets
            </span>
            <span style="color:#6b7280;">
                Total staked: <strong style="color:#e5e7eb;">${total_stake:.2f}</strong>
            </span>
            <span style="color:#6b7280;">
                Net P&amp;L: <strong style="color:{pnl_color};">{'+' if total_pnl > 0 else ''}${total_pnl:.2f}</strong>
            </span>
        </div>
        """
    )
