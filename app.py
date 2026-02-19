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


_init_scheduler()

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
