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

import html
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
from core.clv_tracker import log_clv_snapshot
from core.math_engine import get_open_price
from core.result_resolver import auto_resolve_pending

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
    grade = bet.get("grade", "") or ""
    logged_at = bet.get("logged_at", "")[:16].replace("T", " ")

    # Escape all user-controlled strings before HTML injection (stored XSS prevention)
    _target  = html.escape(str(bet.get("target", bet.get("matchup", "")) or ""))
    _matchup = html.escape(str(bet.get("matchup", "") or ""))

    # Grade pill
    grade_pill = ""
    if grade in ("A", "B", "C"):
        _gcfg = {
            "A": ("#f59e0b", "rgba(245,158,11,0.08)", "rgba(245,158,11,0.2)"),
            "B": ("#3b82f6", "rgba(59,130,246,0.08)",  "rgba(59,130,246,0.2)"),
            "C": ("#6b7280", "rgba(107,114,128,0.08)", "rgba(107,114,128,0.2)"),
        }
        gc, gbg, gbd = _gcfg[grade]
        grade_pill = (
            f'<span style="font-family:\'IBM Plex Mono\',monospace; font-size:0.48rem;'
            f' font-weight:700; color:{gc}; letter-spacing:0.12em; background:{gbg};'
            f' border:1px solid {gbd}; border-radius:3px; padding:1px 5px; margin-left:6px;">'
            f'GRADE {grade}</span>'
        )

    return f"""
    <div style="
        background: linear-gradient(160deg, #1c1f28 0%, #171a22 100%);
        border: 1px solid rgba(255,255,255,0.05);
        border-left: 3px solid {color};
        border-radius: 10px;
        padding: 13px 17px 11px;
        margin-bottom: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.25), 0 4px 12px rgba(0,0,0,0.18),
                    inset 0 1px 0 rgba(255,255,255,0.04);
        font-family: 'IBM Plex Sans', sans-serif;
    ">
        <!-- Header row -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:9px;">
            <div style="flex:1; min-width:0; padding-right:12px;">
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px; flex-wrap:wrap;">
                    <span style="font-family:'IBM Plex Mono',monospace; font-size:0.52rem;
                                 color:#4b5563; letter-spacing:0.12em; font-weight:600;">
                        {sport} · {mkt}
                    </span>
                    {grade_pill}
                </div>
                <div style="font-family:'IBM Plex Sans',sans-serif; font-size:1.0rem;
                             font-weight:700; color:#f3f4f6; letter-spacing:-0.01em; line-height:1.25;">
                    {_target}
                </div>
                <div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.7rem;
                             color:#6b7280; margin-top:2px;">{_matchup}</div>
            </div>
            <div style="text-align:right; flex-shrink:0;">
                <div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.88rem;
                             font-weight:700; color:{color}; letter-spacing:-0.01em;">{label}</div>
                <div style="font-family:'IBM Plex Mono',monospace; font-size:1.1rem;
                             font-weight:700; color:{profit_color}; letter-spacing:-0.02em;
                             line-height:1.1; margin-top:2px;">{profit_str}</div>
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.58rem;
                             color:#4b5563; margin-top:3px;">{logged_at}</div>
            </div>
        </div>
        <!-- Math tiles -->
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:6px;">
            <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.04);
                        border-radius:6px; padding:6px 9px;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.5rem;
                             color:#4b5563; letter-spacing:0.1em;">PRICE</div>
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.88rem;
                             font-weight:600; color:#d1d5db; margin-top:1px;">{price_str}</div>
            </div>
            <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.04);
                        border-radius:6px; padding:6px 9px;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.5rem;
                             color:#4b5563; letter-spacing:0.1em;">STAKE</div>
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.88rem;
                             font-weight:600; color:#d1d5db; margin-top:1px;">${stake:.2f}</div>
            </div>
            <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.04);
                        border-radius:6px; padding:6px 9px;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.5rem;
                             color:#4b5563; letter-spacing:0.1em;">EDGE</div>
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.88rem;
                             font-weight:600; color:#22c55e; margin-top:1px;">+{edge:.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.04);
                        border-radius:6px; padding:6px 9px;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.5rem;
                             color:#4b5563; letter-spacing:0.1em;">CLV</div>
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.88rem;
                             font-weight:600; color:{clv_color}; margin-top:1px;">{clv_str}</div>
            </div>
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

# --- Global design system injection ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
code, pre, .mono { font-family: 'IBM Plex Mono', monospace !important; }
h1, h2, h3 { font-family: 'IBM Plex Sans', sans-serif !important; letter-spacing: -0.02em; }
</style>
""", unsafe_allow_html=True)

# --- Page header ---
st.html("""
<div style="margin-bottom:6px;">
  <div style="display:flex; align-items:baseline; gap:10px;">
    <span style="font-family:'IBM Plex Sans',sans-serif; font-size:1.55rem;
                 font-weight:700; color:#f3f4f6; letter-spacing:-0.03em;">Bet Tracker</span>
  </div>
  <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem;
               color:#4b5563; margin-top:3px; letter-spacing:0.04em;">
    P&amp;L · CLV · calibration history
  </div>
</div>
""")

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

win_rate_color = "#22c55e" if win_rate >= 50 else ("#ef4444" if total_bets else "#6b7280")
roi_color = "#22c55e" if roi > 0 else ("#ef4444" if roi < 0 else "#6b7280")
clv_color_s = "#22c55e" if avg_clv > 0 else ("#ef4444" if avg_clv < 0 else "#6b7280")
roi_display = f"{roi:+.1f}%" if total_bets else "—"
win_rate_display = f"{win_rate:.1f}%" if total_bets else "—"
clv_display = f"{avg_clv:+.2f}%" if total_bets else "—"

st.html(f"""
<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:7px;
            margin-top:4px; margin-bottom:14px;">
    <div style="background:rgba(107,114,128,0.07); border:1px solid rgba(107,114,128,0.14);
                border-radius:8px; padding:9px 11px;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem;
                     color:#4b5563; letter-spacing:0.10em; margin-bottom:4px;">TOTAL BETS</div>
        <div style="font-family:'IBM Plex Mono',monospace; font-size:1.4rem;
                     font-weight:700; color:#9ca3af; line-height:1;">{total_bets}</div>
    </div>
    <div style="background:rgba(107,114,128,0.07); border:1px solid rgba(107,114,128,0.14);
                border-radius:8px; padding:9px 11px;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem;
                     color:#4b5563; letter-spacing:0.10em; margin-bottom:4px;">RECORD</div>
        <div style="font-family:'IBM Plex Mono',monospace; font-size:1.1rem;
                     font-weight:700; color:#d1d5db; line-height:1;">{wins}W&nbsp;–&nbsp;{losses}L</div>
    </div>
    <div style="background:rgba(107,114,128,0.07); border:1px solid rgba(107,114,128,0.14);
                border-radius:8px; padding:9px 11px;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem;
                     color:#4b5563; letter-spacing:0.10em; margin-bottom:4px;">WIN RATE</div>
        <div style="font-family:'IBM Plex Mono',monospace; font-size:1.4rem;
                     font-weight:700; color:{win_rate_color}; line-height:1;">{win_rate_display}</div>
    </div>
    <div style="background:rgba(107,114,128,0.07); border:1px solid rgba(107,114,128,0.14);
                border-radius:8px; padding:9px 11px;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem;
                     color:#4b5563; letter-spacing:0.10em; margin-bottom:4px;">ROI</div>
        <div style="font-family:'IBM Plex Mono',monospace; font-size:1.4rem;
                     font-weight:700; color:{roi_color}; line-height:1;">{roi_display}</div>
    </div>
    <div style="background:rgba(107,114,128,0.07); border:1px solid rgba(107,114,128,0.14);
                border-radius:8px; padding:9px 11px;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem;
                     color:#4b5563; letter-spacing:0.10em; margin-bottom:4px;">AVG CLV</div>
        <div style="font-family:'IBM Plex Mono',monospace; font-size:1.4rem;
                     font-weight:700; color:{clv_color_s}; line-height:1;">{clv_display}</div>
    </div>
</div>
<div style="height:1px; background:rgba(255,255,255,0.05); margin-bottom:14px;"></div>
""")

# --- Two-column layout: Log form LEFT, Pending bets RIGHT ---
log_col, pending_col = st.columns([1, 1], gap="large")

with log_col:
    st.html("""
    <div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.95rem;
                font-weight:700; color:#f3f4f6; letter-spacing:-0.02em; margin-bottom:8px;">
        Log a Bet
    </div>
    """)

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

        # --- Analytics metadata (for 07_analytics.py correlation charts) ---
        st.html("""
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem;
                     text-transform:uppercase; letter-spacing:0.10em; color:#4b5563;
                     border-top:1px solid rgba(255,255,255,0.05); margin:12px 0 6px;
                     padding-top:10px;">Analytics Metadata</div>
        """)
        a1, a2, a3 = st.columns(3)
        with a1:
            sharp_score_input = st.number_input(
                "Sharp Score (0-100)", value=0, step=1,
                min_value=0, max_value=100, key="bt_sharp_score",
                help="Copy from the candidate card. 45–59 = LEAN, 60–89 = STANDARD, 90+ = NUCLEAR. Powers ROI correlation chart in Analytics.",
            )
        with a2:
            line_input = st.number_input(
                "Line (spread/total)", value=0.0, step=0.5, key="bt_line",
                help="The spread or total value at time of bet. e.g. -4.5 for a spread, 223.5 for a total. Used for line-movement timing analysis.",
            )
        with a3:
            book_input = st.selectbox(
                "Book",
                ["", "FanDuel", "DraftKings", "BetMGM",
                 "Caesars", "PointsBet", "bet365", "Other"],
                key="bt_book",
                help="Which sportsbook you placed the bet at. Enables per-book ROI breakdown in Analytics.",
            )
        a4, a5, a6, a7 = st.columns(4)
        with a4:
            rlm_fired_input = st.checkbox(
                "RLM Confirmed", value=False, key="bt_rlm_fired",
                help="Check if the Live Lines page showed an RLM (Reverse Line Movement) signal on this game. Enables RLM lift analysis — did RLM bets outperform non-RLM?",
            )
        with a5:
            days_to_game_input = st.number_input(
                "Days to Game", value=0.0, step=0.5, min_value=0.0,
                key="bt_days_to_game",
                help="How many days before tip/kickoff you placed the bet. 0 = day of game, 1 = day before, etc. Timing analysis for future models.",
            )
        with a6:
            signal_input = st.text_input(
                "Signal", value="", key="bt_signal",
                placeholder="sharp",
                help="What model signal triggered this bet. Examples: sharp, rlm_confirmed, efficiency_edge, b2b, pdo_regression. Used for signal-type performance slicing.",
            )
        with a7:
            tags_input = st.text_input(
                "Tags (comma-sep)", value="", key="bt_tags",
                placeholder="nba,home_dog",
                help="Comma-separated labels for filtering analytics. Examples: nba,home_dog,rlm or nfl,totals,wind. Tag freely — used for slice-and-dice once 10 bets logged.",
            )

        b1, b2 = st.columns(2)
        with b1:
            grade_input = st.selectbox(
                "Grade", ["", "A", "B", "C"],
                key="bt_grade",
                help="Confidence tier from Live Lines. A=≥3.5% edge (full stake), B=≥1.5% (reduced stake), C=≥0.5% (tracking only). Auto-filled when logging from Live Lines.",
            )

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
                        sharp_score=int(sharp_score_input),
                        rlm_fired=rlm_fired_input,
                        tags=tags_input.strip(),
                        book=book_input,
                        days_to_game=float(days_to_game_input),
                        line=float(line_input),
                        signal=signal_input.strip(),
                        grade=grade_input,
                        db_path=DB_PATH,
                    )
                    st.success(f"Bet #{bet_id} logged.")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Failed to log bet: {exc}")

with pending_col:
    _pcol_header, _pcol_btn = st.columns([2, 1], gap="small")
    with _pcol_header:
        st.html("""
        <div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.95rem;
                    font-weight:700; color:#f3f4f6; letter-spacing:-0.02em; margin-bottom:8px;">
            Pending Bets
        </div>
        """)
    with _pcol_btn:
        if st.button(
            "🔄 Auto-Resolve",
            key="auto_resolve_btn",
            use_container_width=True,
            help="Fetch ESPN scores and resolve all pending paper bets. Zero API credits.",
        ):
            try:
                rr = auto_resolve_pending(db_path=DB_PATH)
                if rr.resolved > 0:
                    st.toast(
                        f"✅ {rr.resolved} bet{'s' if rr.resolved != 1 else ''} resolved"
                        + (f" · {rr.skipped} skipped" if rr.skipped else ""),
                        icon="✅",
                    )
                    st.cache_data.clear()
                    st.rerun()
                elif rr.skipped > 0 and rr.resolved == 0:
                    st.toast(f"⏳ {rr.skipped} bets still pending (games not completed yet)", icon="⏳")
                else:
                    st.toast("No pending bets to resolve.", icon="ℹ️")
                if rr.errors:
                    st.warning(f"{rr.errors} resolution error(s) — check logs.")
            except Exception as exc:
                st.error(f"Auto-resolve failed: {exc}")

    try:
        pending = get_bets(result_filter="pending", db_path=DB_PATH)
    except Exception:
        pending = []

    if not pending:
        st.html("""
        <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.05);
                    border-radius:8px; padding:24px; text-align:center;">
            <div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.82rem;
                         color:#4b5563; line-height:1.6;">
                No pending bets.<br>
                <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem;
                              color:#374151;">Log a bet on the left to start tracking.</span>
            </div>
        </div>
        """)
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
                    # Default: use stake_usd (dollar amount from Kelly sizing) if set,
                    # else fall back to stake column, else $25 placeholder.
                    _default_stake = (
                        float(bet.get("stake_usd") or 0)
                        or float(bet.get("stake") or 0)
                        or 25.0
                    )
                    stake_actual = st.number_input(
                        "Actual stake ($)",
                        value=_default_stake,
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
                        # Log CLV snapshot to CSV when close price is provided
                        if close_price and close_price != 0:
                            try:
                                event_id = bet.get("event_id") or ""
                                bet_price = int(bet.get("price", close_price))
                                side = bet.get("target") or bet.get("matchup") or "unknown"
                                # Use RLM cache for open price; fall back to bet_price
                                open_p = get_open_price(event_id, side) if event_id else None
                                open_price_val = open_p if open_p is not None else bet_price
                                log_clv_snapshot(
                                    event_id=event_id or f"manual_{bet_id}",
                                    side=side,
                                    open_price=open_price_val,
                                    bet_price=bet_price,
                                    close_price=int(close_price),
                                )
                            except Exception:
                                pass  # CLV log failure must never block bet result save
                        st.success("Result saved.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed: {exc}")

st.html('<div style="height:1px; background:rgba(255,255,255,0.05); margin:14px 0 12px;"></div>')

# --- Full history table ---
st.html("""
<div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.95rem;
            font-weight:700; color:#f3f4f6; letter-spacing:-0.02em; margin-bottom:10px;">
    Bet History
</div>
""")

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
    st.html("""
    <div style="background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.05);
                border-radius:8px; padding:20px; text-align:center;">
        <div style="font-family:'IBM Plex Sans',sans-serif; font-size:0.82rem; color:#4b5563;">
            No bets match the current filters.
        </div>
    </div>
    """)
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
        <div style="display:flex; gap:20px; align-items:center; padding:9px 14px; margin-top:6px;
                    background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.05);
                    border-radius:8px;">
            <span style="font-family:'IBM Plex Sans',sans-serif; font-size:0.72rem; color:#4b5563;">
                Showing&nbsp;
                <span style="font-family:'IBM Plex Mono',monospace; font-weight:600;
                              color:#9ca3af;">{len(all_bets)}</span>
                &nbsp;bets
            </span>
            <div style="width:1px; height:12px; background:rgba(255,255,255,0.06);"></div>
            <span style="font-family:'IBM Plex Sans',sans-serif; font-size:0.72rem; color:#4b5563;">
                Total staked:&nbsp;
                <span style="font-family:'IBM Plex Mono',monospace; font-weight:600;
                              color:#9ca3af;">${total_stake:.2f}</span>
            </span>
            <div style="width:1px; height:12px; background:rgba(255,255,255,0.06);"></div>
            <span style="font-family:'IBM Plex Sans',sans-serif; font-size:0.72rem; color:#4b5563;">
                Net P&amp;L:&nbsp;
                <span style="font-family:'IBM Plex Mono',monospace; font-weight:700;
                              color:{pnl_color};">{'+' if total_pnl > 0 else ''}${total_pnl:.2f}</span>
            </span>
        </div>
        """
    )
