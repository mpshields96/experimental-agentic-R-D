"""
app.py — Titanium-Agentic Streamlit Entry Point

Multi-page navigation via st.navigation() (Streamlit 1.36+).
Scheduler initialized once per process via st.session_state guard.

Design principles:
- Dark terminal aesthetic: #0e1117 bg, amber accent (#f59e0b)
- st.html() for custom cards (not st.markdown — style tags sandboxed)
- Inline styles only — Streamlit strips <style> blocks in components
- No rainbow metrics — single accent color hierarchy

Run: streamlit run app.py
"""

import logging
import os
import sys
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Path setup — allow 'from core.xxx import' regardless of cwd
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Logging setup — write to logs/error.log
# ---------------------------------------------------------------------------
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "error.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Titanium-Agentic",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Titanium-Agentic — Personal Sports Betting Analytics",
    },
)

# ---------------------------------------------------------------------------
# Scheduler initialization — guarded against Streamlit reruns
# ---------------------------------------------------------------------------
def _init_scheduler() -> None:
    """
    Start background line-polling scheduler exactly once per process.
    The session_state flag survives reruns but not process restarts.
    """
    if st.session_state.get("scheduler_started"):
        return

    try:
        from core.scheduler import start_scheduler
        db_path = str(ROOT / "data" / "line_history.db")
        start_scheduler(db_path=db_path, poll_interval_minutes=5)
        st.session_state["scheduler_started"] = True
        logger.info("Scheduler initialized from app.py")
    except Exception as exc:  # noqa: BLE001
        logger.error("Scheduler init failed: %s", exc)
        st.session_state["scheduler_started"] = False
        st.session_state["scheduler_error"] = str(exc)


def _seed_rlm_cache() -> None:
    """
    Pre-seed the math_engine RLM open price cache from line_history.db.

    Called once at app startup. Loads 30+ polls of historical open prices
    so RLM detection is active from the first fetch of a new session,
    rather than requiring two live fetches to initialize.
    """
    if st.session_state.get("rlm_cache_seeded"):
        return
    try:
        from core.line_logger import get_open_prices_for_rlm
        from core.math_engine import seed_open_prices_from_db
        db_path = str(ROOT / "data" / "line_history.db")
        open_prices = get_open_prices_for_rlm(db_path=db_path)
        n_seeded = seed_open_prices_from_db(open_prices)
        st.session_state["rlm_cache_seeded"] = True
        logger.info("RLM cache seeded: %d events from line_history.db", n_seeded)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RLM cache seed failed (non-fatal): %s", exc)
        st.session_state["rlm_cache_seeded"] = False


_init_scheduler()
_seed_rlm_cache()

# ---------------------------------------------------------------------------
# Global CSS injection — minimal, purposeful
# Only things that CANNOT be done with inline styles go here.
# st.markdown with unsafe_allow_html works for global style block injection
# even in 1.54+ (the sandbox is per-component, not global).
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Sidebar refinements */
    [data-testid="stSidebar"] {
        background-color: #13161d;
    }
    [data-testid="stSidebar"] .stMarkdown p {
        color: #9ca3af;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    /* Remove default padding from main block */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    /* Metric card numbers */
    [data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 700 !important;
    }
    /* Suppress Streamlit footer */
    footer { visibility: hidden; }
    /* Table header styling */
    thead tr th {
        background-color: #1a1d23 !important;
        color: #f59e0b !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar — status + navigation context
# ---------------------------------------------------------------------------
with st.sidebar:
    st.html(
        """
        <div style="
            padding: 12px 0 8px 0;
            border-bottom: 1px solid #2d3139;
            margin-bottom: 12px;
        ">
            <span style="
                font-size: 1.1rem;
                font-weight: 700;
                color: #f59e0b;
                letter-spacing: 0.03em;
            ">⚡ TITANIUM</span>
            <span style="
                font-size: 0.65rem;
                color: #6b7280;
                margin-left: 6px;
                letter-spacing: 0.1em;
                vertical-align: middle;
            ">AGENTIC</span>
        </div>
        """
    )

    # Scheduler status
    try:
        from core.scheduler import get_status
        status = get_status()
        is_running = status["running"]
        last_poll = status["last_poll_time"]
        err_count = status["poll_error_count"]

        if is_running:
            dot_color = "#22c55e"
            label = "LIVE"
        elif st.session_state.get("scheduler_error"):
            dot_color = "#ef4444"
            label = "ERROR"
        else:
            dot_color = "#6b7280"
            label = "IDLE"

        poll_str = last_poll.strftime("%H:%M:%S UTC") if last_poll else "—"
        err_str = f"  ⚠ {err_count} errors" if err_count else ""

        st.html(
            f"""
            <div style="
                background: #1a1d23;
                border: 1px solid #2d3139;
                border-radius: 6px;
                padding: 10px 12px;
                margin-bottom: 12px;
            ">
                <div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">
                    <div style="
                        width:8px; height:8px; border-radius:50%;
                        background:{dot_color};
                        box-shadow: 0 0 6px {dot_color};
                    "></div>
                    <span style="
                        font-size:0.65rem; font-weight:600;
                        color:{dot_color}; letter-spacing:0.1em;
                    ">{label}</span>
                </div>
                <div style="font-size:0.65rem; color:#6b7280; line-height:1.6;">
                    <div>Polls: every 5 min</div>
                    <div>Last: {poll_str}</div>
                    {f'<div style="color:#ef4444;">{err_str}</div>' if err_count else ''}
                </div>
            </div>
            """
        )
    except ImportError:
        pass

    # Quick-poll button
    if st.button("↺  Refresh Now", use_container_width=True, type="secondary"):
        try:
            from core.scheduler import trigger_poll_now
            with st.spinner("Polling..."):
                result = trigger_poll_now()
            total = sum(result.values())
            st.success(f"Fetched {total} lines")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Poll failed: {exc}")

    st.markdown("---")

    # Quota display
    try:
        from core.odds_fetcher import quota
        st.markdown(quota.report())
    except ImportError:
        pass

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Health dashboard — probe, price history, CLV
    # ---------------------------------------------------------------------------
    st.html(
        """
        <div style="
            font-size:0.6rem; font-weight:700; color:#6b7280;
            letter-spacing:0.12em; text-transform:uppercase;
            margin-bottom:6px;
        ">SYSTEM HEALTH</div>
        """
    )

    # Pinnacle probe status
    try:
        from core.probe_logger import probe_log_status, probe_summary, read_probe_log
        _probe_entries = read_probe_log(last_n=1)
        _probe_s = probe_summary(read_probe_log())
        _n_probe = _probe_s.get("n_probes", 0)
        _pin_rate = _probe_s.get("pinnacle_rate", 0.0)
        _pin_present = _probe_s.get("pinnacle_present", False)
        _pin_color = "#22c55e" if _pin_present else "#ef4444"
        _pin_label = "ACTIVE" if _pin_present else "ABSENT"
        _books_seen = _probe_s.get("all_books_seen", [])
        _books_str = ", ".join(_books_seen[:4])
        if len(_books_seen) > 4:
            _books_str += f" +{len(_books_seen) - 4}"
        st.html(
            f"""
            <div style="
                background:#1a1d23; border:1px solid #2d3139;
                border-radius:6px; padding:8px 10px; margin-bottom:8px;
            ">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
                    <span style="font-size:0.6rem; font-weight:700; color:#9ca3af; letter-spacing:0.08em;">📡 PINNACLE PROBE</span>
                    <span style="font-size:0.6rem; font-weight:700; color:{_pin_color};">{_pin_label}</span>
                </div>
                <div style="font-size:0.6rem; color:#6b7280; line-height:1.7;">
                    <div>Probes logged: <span style="color:#d1d5db;">{_n_probe}</span></div>
                    <div>Pinnacle rate: <span style="color:#d1d5db;">{_pin_rate:.1%}</span></div>
                    {'<div>Books: <span style="color:#d1d5db;">' + _books_str + '</span></div>' if _books_str else ''}
                </div>
            </div>
            """
        )
    except ImportError:
        pass

    # Price history status
    try:
        from core.price_history_store import price_history_status
        _ph_path = str(ROOT / "data" / "line_history.db")
        _ph_status = price_history_status(_ph_path)
        _ph_empty = "empty" in _ph_status
        _ph_color = "#6b7280" if _ph_empty else "#22c55e"
        st.html(
            f"""
            <div style="
                background:#1a1d23; border:1px solid #2d3139;
                border-radius:6px; padding:8px 10px; margin-bottom:8px;
            ">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
                    <span style="font-size:0.6rem; font-weight:700; color:#9ca3af; letter-spacing:0.08em;">📦 PRICE HISTORY</span>
                    <span style="font-size:0.6rem; font-weight:700; color:{_ph_color};">{'EMPTY' if _ph_empty else 'OK'}</span>
                </div>
                <div style="font-size:0.6rem; color:#6b7280;">{_ph_status}</div>
            </div>
            """
        )
    except ImportError:
        pass

    # CLV tracker status
    try:
        from core.clv_tracker import CLV_GATE, clv_summary, read_clv_log
        _clv_entries = read_clv_log()
        _clv_s = clv_summary(_clv_entries)
        _clv_n = _clv_s.get("n", 0)
        _clv_avg = _clv_s.get("avg_clv_pct", 0.0)
        _clv_pos_rate = _clv_s.get("positive_rate", 0.0)
        _clv_verdict = _clv_s.get("verdict", "INSUFFICIENT DATA")
        _clv_color = "#22c55e" if "STRONG" in _clv_verdict else (
            "#f59e0b" if "MARGINAL" in _clv_verdict else
            "#ef4444" if "NO EDGE" in _clv_verdict else "#6b7280"
        )
        _gate_pct = min(1.0, _clv_n / CLV_GATE) if CLV_GATE > 0 else 0.0
        st.html(
            f"""
            <div style="
                background:#1a1d23; border:1px solid #2d3139;
                border-radius:6px; padding:8px 10px; margin-bottom:8px;
            ">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
                    <span style="font-size:0.6rem; font-weight:700; color:#9ca3af; letter-spacing:0.08em;">📐 CLV TRACKER</span>
                    <span style="font-size:0.6rem; font-weight:700; color:{_clv_color};">{_clv_verdict.split()[0]}</span>
                </div>
                <div style="font-size:0.6rem; color:#6b7280; line-height:1.7;">
                    <div>Graded: <span style="color:#d1d5db;">{_clv_n}</span> / {CLV_GATE}</div>
                    {'<div>Avg CLV: <span style="color:#d1d5db;">' + f"{_clv_avg:+.2f}%" + '</span></div>' if _clv_n > 0 else ''}
                    {'<div>Positive rate: <span style="color:#d1d5db;">' + f"{_clv_pos_rate:.0%}" + '</span></div>' if _clv_n > 0 else ''}
                </div>
                <div style="
                    background:#2d3139; border-radius:3px; height:3px;
                    margin-top:6px; overflow:hidden;
                ">
                    <div style="
                        background:#f59e0b; height:3px;
                        width:{_gate_pct:.0%}; transition:width 0.3s;
                    "></div>
                </div>
                <div style="font-size:0.55rem; color:#4b5563; margin-top:2px;">gate progress</div>
            </div>
            """
        )
    except ImportError:
        pass

    st.markdown("---")
    st.markdown("Math > Narrative")

# ---------------------------------------------------------------------------
# Multi-page navigation — programmatic (st.navigation, Streamlit 1.36+)
# ---------------------------------------------------------------------------
pages = [
    st.Page("pages/01_live_lines.py",     title="Live Lines",    icon="🔴", default=True),
    st.Page("pages/02_analysis.py",       title="Analysis",      icon="📊"),
    st.Page("pages/03_line_history.py",   title="Line History",  icon="📈"),
    st.Page("pages/04_bet_tracker.py",    title="Bet Tracker",   icon="📋"),
    st.Page("pages/05_rd_output.py",      title="R&D Output",    icon="🔬"),
]

pg = st.navigation(pages)
pg.run()
