"""
pages/08_player_props.py — Titanium-Agentic
============================================
On-demand player props lookup.

Conditions (V37 APPROVED Session 35):
  (a) Separate quota tracking — never consumes main odds budget
  (b) No scheduler polling — on-demand UI only
  (c) Event-level only — one event at a time

Usage:
  1. Go to Live Lines and find a game you want props for
  2. Copy the event_id from the matchup row (or enter it manually)
  3. Select prop markets and click Fetch Props
"""

import html
import logging
from collections import defaultdict

import streamlit as st

from core.math_engine import PropCandidate, parse_props_candidates
from core.odds_fetcher import (
    PROP_MARKETS,
    PROPS_SESSION_CREDIT_CAP,
    fetch_props_for_event,
    props_quota,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPORT_OPTIONS: dict[str, str] = {
    "NBA": "basketball_nba",
    "NFL": "americanfootball_nfl",
}

_DEFAULT_MARKETS = ["player_points", "player_rebounds", "player_assists"]

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

.pp-root { font-family: 'IBM Plex Sans', sans-serif; }

.pp-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #f59e0b;
    margin: 0 0 1.5rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #2d3139;
}

.pp-budget-bar {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 6px;
    padding: 0.7rem 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.25rem;
}

.pp-budget-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    color: #6b7280;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.pp-budget-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    color: #22c55e;
}

.pp-budget-value.warn {
    color: #f59e0b;
}

.pp-budget-value.danger {
    color: #ef4444;
}

/* Player prop card */
.pp-player-card {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 8px;
    margin-bottom: 0.75rem;
    overflow: hidden;
}

.pp-player-header {
    background: #14171e;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid #2d3139;
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.pp-player-name {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.85rem;
    font-weight: 600;
    color: #f3f4f6;
    flex: 1;
}

.pp-market-tag {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #f59e0b;
    background: rgba(245,158,11,0.12);
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: 3px;
    padding: 0.15rem 0.4rem;
}

.pp-lines-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
}

.pp-line-cell {
    padding: 0.55rem 1rem;
    border-right: 1px solid #2d3139;
}

.pp-line-cell:nth-child(2) { border-right: none; }

.pp-line-direction {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}

.pp-line-direction.over { color: #22c55e; }
.pp-line-direction.under { color: #ef4444; }

.pp-line-point {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 600;
    color: #f3f4f6;
}

.pp-line-books {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    color: #6b7280;
    margin-top: 0.15rem;
}

.pp-line-odds {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #9ca3af;
    margin-top: 0.1rem;
}

.pp-best-odds {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    color: #f3f4f6;
    background: rgba(34,197,94,0.08);
    border: 1px solid rgba(34,197,94,0.2);
    border-radius: 3px;
    padding: 0.05rem 0.3rem;
}

.pp-no-results {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #6b7280;
    padding: 1.5rem 0;
    text-align: center;
}

.pp-edge-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 1rem;
    background: rgba(34,197,94,0.04);
    border-top: 1px solid #2d3139;
}

.pp-edge-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6b7280;
}

.pp-edge-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    color: #22c55e;
}

.pp-edge-value.negative { color: #6b7280; }
.pp-edge-value.warn     { color: #f59e0b; }

.pp-grade-pill {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    border-radius: 3px;
    padding: 0.1rem 0.4rem;
    text-transform: uppercase;
}
.pp-grade-pill.A         { background: rgba(34,197,94,0.15);  border: 1px solid rgba(34,197,94,0.35);  color: #22c55e; }
.pp-grade-pill.B         { background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3);  color: #f59e0b; }
.pp-grade-pill.C         { background: rgba(156,163,175,0.1); border: 1px solid rgba(156,163,175,0.25); color: #9ca3af; }
.pp-grade-pill.NEAR_MISS { background: rgba(239,68,68,0.08);  border: 1px solid rgba(239,68,68,0.2);   color: #ef4444; }
.pp-grade-pill.BELOW_MIN { background: transparent;            border: 1px solid #2d3139;               color: #4b5563; }

.pp-guide {
    background: rgba(245,158,11,0.05);
    border: 1px solid rgba(245,158,11,0.18);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin-bottom: 1.25rem;
}

.pp-guide p {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.72rem;
    color: #9ca3af;
    margin: 0 0 0.3rem 0;
}

.pp-guide code {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #f59e0b;
    background: rgba(245,158,11,0.1);
    border-radius: 2px;
    padding: 0.05rem 0.2rem;
}

.pp-section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6b7280;
    margin: 1rem 0 0.4rem 0;
}

.pp-error {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #ef4444;
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.2);
    border-radius: 6px;
    padding: 0.65rem 1rem;
    margin-bottom: 1rem;
}
</style>
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_props_response(data: dict) -> dict:
    """Parse raw event props API response into a nested structure.

    Returns:
        {player_name: {market_key: {"over": [(book, price, point)], "under": [...]}}}
    """
    result: dict[str, dict[str, dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: {"over": [], "under": []})
    )

    for bk in data.get("bookmakers", []):
        book_key = bk.get("key", "?")
        for mkt in bk.get("markets", []):
            mkt_key = mkt.get("key", "?")
            for outcome in mkt.get("outcomes", []):
                player = outcome.get("description", "Unknown Player")
                direction = outcome.get("name", "").lower()  # "over" or "under"
                price = outcome.get("price")
                point = outcome.get("point")
                if direction in ("over", "under") and price is not None and point is not None:
                    result[player][mkt_key][direction].append((book_key, price, point))

    return result


def _best_odds(entries: list[tuple]) -> tuple | None:
    """Return the entry (book, price, point) with the best (highest) american price."""
    if not entries:
        return None
    return max(entries, key=lambda e: e[1])


def _fmt_price(price: int) -> str:
    return f"+{price}" if price > 0 else str(price)


def _market_label(key: str) -> str:
    labels = {
        "player_points": "PTS",
        "player_rebounds": "REB",
        "player_assists": "AST",
        "player_threes": "3PM",
        "player_blocks": "BLK",
        "player_steals": "STL",
        "player_points_rebounds_assists": "PRA",
        "player_points_rebounds": "P+R",
        "player_points_assists": "P+A",
        "player_pass_tds": "PASS TD",
        "player_pass_yds": "PASS YD",
        "player_rush_yds": "RUSH YD",
        "player_receptions": "REC",
        "player_reception_yds": "REC YD",
    }
    return labels.get(key, key.replace("player_", "").upper())


def _render_player_card(
    player: str,
    market_key: str,
    sides: dict,
    over_cand: PropCandidate | None = None,
    under_cand: PropCandidate | None = None,
) -> str:
    """Render a single player+market prop card as HTML."""
    p = html.escape(player)
    mkt_label = html.escape(_market_label(market_key))

    over_entries = sides.get("over", [])
    under_entries = sides.get("under", [])

    # Best available odds for each direction
    best_over = _best_odds(over_entries)
    best_under = _best_odds(under_entries)

    # Line value (use best_over point if available, else under)
    line_val = ""
    if best_over:
        line_val = str(best_over[2])
    elif best_under:
        line_val = str(best_under[2])

    def _side_html(label: str, css_class: str, entries: list, best: tuple | None) -> str:
        if not entries:
            return f"""
            <div class="pp-line-cell">
                <div class="pp-line-direction {css_class}">{label}</div>
                <div class="pp-line-point">{line_val}</div>
                <div class="pp-line-books">—</div>
            </div>"""
        books_str = html.escape(", ".join(e[0] for e in entries))
        best_price_str = _fmt_price(best[1]) if best else "—"
        return f"""
        <div class="pp-line-cell">
            <div class="pp-line-direction {css_class}">{label}</div>
            <div class="pp-line-point">{html.escape(line_val)} &nbsp;<span class="pp-best-odds">{html.escape(best_price_str)}</span></div>
            <div class="pp-line-books">{books_str}</div>
        </div>"""

    over_html = _side_html("Over", "over", over_entries, best_over)
    under_html = _side_html("Under", "under", under_entries, best_under)

    # Edge + grade row — shown only if at least one direction has a PropCandidate
    edge_row_html = ""
    edge_parts = []
    for cand in (over_cand, under_cand):
        if cand is None:
            continue
        sign = "+" if cand.edge_pct >= 0 else ""
        edge_cls = (
            "negative" if cand.edge_pct < 0
            else "warn" if cand.edge_pct < 0.015
            else ""
        )
        grade_cls = html.escape(cand.grade)
        edge_parts.append(
            f'<span class="pp-grade-pill {grade_cls}">{html.escape(cand.grade)}</span>'
            f' <span class="pp-edge-label">{html.escape(cand.direction)}</span>'
            f' <span class="pp-edge-value {edge_cls}">{sign}{cand.edge_pct*100:.1f}%</span>'
        )
    if edge_parts:
        edge_row_html = f"""
        <div class="pp-edge-row">
            <span class="pp-edge-label">Edge</span>
            {"&nbsp;&nbsp;".join(edge_parts)}
        </div>"""

    return f"""
    <div class="pp-player-card">
        <div class="pp-player-header">
            <div class="pp-player-name">{p}</div>
            <div class="pp-market-tag">{mkt_label}</div>
        </div>
        <div class="pp-lines-grid">
            {over_html}
            {under_html}
        </div>
        {edge_row_html}
    </div>"""


def _render_budget_bar() -> str:
    used = props_quota.session_used
    cap = PROPS_SESSION_CREDIT_CAP
    remaining = props_quota.remaining_session_budget()
    pct = used / cap if cap > 0 else 0

    if pct >= 1.0:
        cls = "danger"
        status = "EXHAUSTED"
    elif pct >= 0.8:
        cls = "warn"
        status = f"{remaining} left"
    else:
        cls = ""
        status = f"{remaining} left"

    return f"""
    <div class="pp-budget-bar">
        <span class="pp-budget-label">Props Budget</span>
        <span class="pp-budget-value {html.escape(cls)}">{used}/{cap} credits · {html.escape(status)}</span>
    </div>"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.markdown(_CSS, unsafe_allow_html=True)

st.html('<div class="pp-header">Player Props — On Demand</div>')

# Guidance note
st.html("""
<div class="pp-guide">
    <p>On-demand only — zero scheduler polling (V37 condition b). Props budget is separate from the main odds quota.</p>
    <p>To get an event ID: fetch odds on <strong>Live Lines</strong>, find the game, and use the <code>id</code> field from the raw game dict — or check the browser URL when viewing a specific game on the Odds API docs.</p>
</div>
""")

# Budget bar
st.html(_render_budget_bar())

# --- Input form ---
st.html('<div class="pp-section-label">Event Configuration</div>')

col_sport, col_event = st.columns([1, 3])

with col_sport:
    sport_label = st.selectbox(
        "Sport",
        options=list(_SPORT_OPTIONS.keys()),
        index=0,
        help="Select sport. NBA is primary — NFL props vary by season.",
    )

with col_event:
    event_id = st.text_input(
        "Event ID",
        placeholder="e.g. 401a3b9c2d... (from Odds API game dict 'id' field)",
        help="The Odds API event ID for a specific game. Find it via the Live Lines raw data.",
    )

sport_key = _SPORT_OPTIONS[sport_label]
available_markets = PROP_MARKETS.get(sport_key, [])

market_labels = {k: _market_label(k) for k in available_markets}
default_selection = [k for k in _DEFAULT_MARKETS if k in available_markets]

selected_markets = st.multiselect(
    "Prop Markets",
    options=available_markets,
    default=default_selection,
    format_func=lambda k: f"{_market_label(k)}  ({k})",
    help=f"Each market costs ~1 credit. Budget: {PROPS_SESSION_CREDIT_CAP} credits/session.",
)

st.markdown("")  # spacing

budget_exhausted = props_quota.is_session_hard_stop()
fetch_disabled = budget_exhausted or not event_id.strip() or not selected_markets

fetch_clicked = st.button(
    "Fetch Props" if not budget_exhausted else "Props Budget Exhausted",
    type="primary",
    disabled=fetch_disabled,
    help="Fetches player props for this event using the separate props quota.",
)

# --- Results ---
if fetch_clicked and not fetch_disabled:
    with st.spinner(f"Fetching {len(selected_markets)} prop market(s)…"):
        raw = fetch_props_for_event(
            event_id=event_id.strip(),
            sport_key=sport_key,
            prop_markets=selected_markets,
        )

    # Refresh budget bar after fetch
    st.html(_render_budget_bar())

    if not raw:
        st.html("""
        <div class="pp-error">
            No props returned. Possible causes: invalid event ID, market not available on this API tier,
            game not yet priced, or props budget exhausted. Check logs for details.
        </div>""")
    else:
        home = raw.get("home_team", "?")
        away = raw.get("away_team", "?")
        commence = raw.get("commence_time", "")
        n_books = len(raw.get("bookmakers", []))

        st.markdown(
            f"**{away} @ {home}** — {n_books} book(s) · `{html.escape(commence[:10]) if commence else '?'}`"
        )
        st.markdown("")

        parsed = _parse_props_response(raw)

        if not parsed:
            st.html('<div class="pp-no-results">No player prop outcomes found in response.</div>')
        else:
            # Run edge/grade analysis — produces PropCandidate list sorted by edge desc
            prop_candidates = parse_props_candidates(raw)
            # Build lookup: (player, market_key, direction) → PropCandidate
            cand_lookup: dict[tuple[str, str, str], PropCandidate] = {
                (c.player, c.market_key, c.direction): c for c in prop_candidates
            }

            # Group by market, then player — consistent order
            market_order = [m for m in selected_markets if m in
                            {mkt for player_data in parsed.values() for mkt in player_data}]

            for mkt_key in market_order:
                st.html(f'<div class="pp-section-label">{html.escape(_market_label(mkt_key))}</div>')
                cards_html = ""
                for player in sorted(parsed.keys()):
                    if mkt_key in parsed[player]:
                        over_cand = cand_lookup.get((player, mkt_key, "Over"))
                        under_cand = cand_lookup.get((player, mkt_key, "Under"))
                        cards_html += _render_player_card(
                            player, mkt_key, parsed[player][mkt_key],
                            over_cand=over_cand, under_cand=under_cand,
                        )
                if cards_html:
                    st.html(cards_html)
                else:
                    st.html('<div class="pp-no-results">No outcomes for this market.</div>')

elif budget_exhausted:
    st.html("""
    <div class="pp-error">
        Props session budget exhausted. Restart the app to reset the session counter
        (props quota resets on process restart — not persisted).
    </div>""")
