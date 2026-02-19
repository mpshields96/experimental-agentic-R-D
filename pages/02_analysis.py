"""
pages/02_analysis.py — Analysis Tab (Session 4 target)

Requires tab_3 (line history) to have been running and accumulating data.
Build this only after tab_3 has been running for multiple sessions.

Planned:
- CLV tracking over time
- RLM detection visualization
- Edge% distribution charts
- ROI by bet type, sport, time period
"""

import streamlit as st

st.title("Analysis")
st.html(
    """
    <div style="
        background: #1a1d23;
        border: 1px solid #2d3139;
        border-left: 3px solid #f59e0b;
        border-radius: 6px;
        padding: 16px 20px;
        color: #9ca3af;
        font-size: 0.85rem;
    ">
        <strong style="color: #f59e0b;">Coming in Session 4</strong><br><br>
        This tab requires line history data to accumulate over multiple sessions
        before CLV tracking, RLM visualization, and ROI analysis become meaningful.
        Build after tab_3 has been running.
    </div>
    """
)
