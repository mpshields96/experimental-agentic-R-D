"""
pages/04_bet_tracker.py — Bet Tracker Tab (Session 3 target)

Planned:
- Log bets manually or from Live Lines tab
- Track outcomes and P&L
- CLV validation per bet
- Win rate, ROI, avg edge over time
"""

import streamlit as st

st.title("Bet Tracker")
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
        <strong style="color: #f59e0b;">Coming in Session 3</strong><br><br>
        Log bets, track outcomes, calculate P&amp;L and CLV.
        Rebuild cleanly from bet-tracker logic — not a file copy.
    </div>
    """
)
