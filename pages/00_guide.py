"""
pages/00_guide.py — Titanium-Agentic
======================================
Live Session Quick-Start Guide.

No math. No code. Just: what do I do, and in what order?
Shows first in the navigation (00_ prefix).
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Guide · Titanium",
    page_icon="📖",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Fonts + base style
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #0e1117;
    color: #e5e7eb;
}

/* ---- Section headers ---- */
.guide-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #f59e0b;
    border-bottom: 1px solid #f59e0b;
    padding-bottom: 6px;
    margin: 28px 0 16px 0;
}

/* ---- Step cards ---- */
.step-card {
    display: flex;
    gap: 16px;
    align-items: flex-start;
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-left: 3px solid #f59e0b;
    border-radius: 4px;
    padding: 14px 18px;
    margin-bottom: 10px;
}
.step-num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 22px;
    font-weight: 600;
    color: #f59e0b;
    line-height: 1;
    min-width: 32px;
}
.step-body {}
.step-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    font-weight: 600;
    color: #f3f4f6;
    margin-bottom: 4px;
}
.step-desc {
    font-size: 13px;
    color: #9ca3af;
    line-height: 1.55;
}
.step-nav {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #f59e0b;
    background: #0e1117;
    border: 1px solid #374151;
    border-radius: 3px;
    padding: 2px 7px;
    display: inline-block;
    margin-top: 5px;
}

/* ---- Signal grade pills ---- */
.sig-row {
    display: flex;
    align-items: center;
    gap: 14px;
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 4px;
    padding: 10px 14px;
    margin-bottom: 8px;
}
.sig-pill-nuclear {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #0e1117;
    background: #ef4444;
    border-radius: 3px;
    padding: 3px 8px;
    min-width: 80px;
    text-align: center;
}
.sig-pill-standard {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #0e1117;
    background: #f59e0b;
    border-radius: 3px;
    padding: 3px 8px;
    min-width: 80px;
    text-align: center;
}
.sig-pill-lean {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #9ca3af;
    background: #2d3139;
    border-radius: 3px;
    padding: 3px 8px;
    min-width: 80px;
    text-align: center;
}
.sig-detail {
    font-size: 13px;
    color: #d1d5db;
}
.sig-detail strong {
    color: #f3f4f6;
}

/* ---- Glossary table ---- */
.gloss-row {
    display: flex;
    gap: 0;
    border-bottom: 1px solid #1f2937;
    padding: 9px 0;
}
.gloss-row:last-child { border-bottom: none; }
.gloss-key {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    font-weight: 500;
    color: #f59e0b;
    min-width: 160px;
    padding-right: 16px;
}
.gloss-val {
    font-size: 13px;
    color: #9ca3af;
    line-height: 1.5;
}
.gloss-val strong { color: #e5e7eb; }
.gloss-container {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 4px;
    padding: 6px 16px;
    margin-bottom: 16px;
}

/* ---- Kill switch table ---- */
.ks-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    border-bottom: 1px solid #1f2937;
}
.ks-row:last-child { border-bottom: none; }
.ks-sport {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #f3f4f6;
    min-width: 70px;
}
.ks-rule {
    font-size: 12px;
    color: #9ca3af;
    flex: 1;
}
.ks-on {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    color: #22c55e;
    background: #14532d33;
    border: 1px solid #22c55e44;
    border-radius: 3px;
    padding: 2px 6px;
}
.ks-container {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 4px;
    padding: 0 12px;
}

/* ---- Gate status ---- */
.gate-row {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 9px 14px;
    border-bottom: 1px solid #1f2937;
}
.gate-row:last-child { border-bottom: none; }
.gate-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #d1d5db;
    min-width: 240px;
}
.gate-status-wait {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #f59e0b;
    background: #78350f33;
    border: 1px solid #f59e0b44;
    border-radius: 3px;
    padding: 2px 7px;
}
.gate-status-ok {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: #22c55e;
    background: #14532d33;
    border: 1px solid #22c55e44;
    border-radius: 3px;
    padding: 2px 7px;
}
.gate-note {
    font-size: 12px;
    color: #6b7280;
}
.gate-container {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 4px;
    padding: 0;
    overflow: hidden;
}

/* ---- Demo banner ---- */
.demo-banner {
    background: linear-gradient(135deg, #1a1d23 0%, #111827 100%);
    border: 1px solid #f59e0b;
    border-radius: 6px;
    padding: 16px 20px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 14px;
}
.demo-icon {
    font-size: 28px;
    line-height: 1;
}
.demo-text-head {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    font-weight: 600;
    color: #f59e0b;
}
.demo-text-body {
    font-size: 13px;
    color: #9ca3af;
    margin-top: 2px;
}

/* ---- Page title ---- */
.page-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 20px;
    font-weight: 600;
    color: #f3f4f6;
    letter-spacing: -0.02em;
}
.page-subtitle {
    font-size: 13px;
    color: #6b7280;
    margin-top: 2px;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.html("""
<div style="padding:8px 0 20px 0;">
  <div class="page-title">📖 Live Session Guide</div>
  <div class="page-subtitle">Everything you need to run a live betting session. No experience required.</div>
</div>
""")


# ---------------------------------------------------------------------------
# Demo banner (shows when approaching live mode)
# ---------------------------------------------------------------------------
st.html("""
<div class="demo-banner">
  <div class="demo-icon">🤖</div>
  <div>
    <div class="demo-text-head">Claude is your co-pilot — it scans, recommends, and logs bets for you.</div>
    <div class="demo-text-body">
      Open a Claude session in the sandbox and say: <strong>"scan live lines and tell me what looks good."</strong>
      Claude handles analysis, kill switches, and logging. You approve or skip. The UI is your dashboard.
    </div>
  </div>
</div>
""")


col_main, col_side = st.columns([3, 2], gap="large")


# ---------------------------------------------------------------------------
# LEFT COL — Session workflow
# ---------------------------------------------------------------------------
with col_main:

    st.html('<div class="guide-header">Live Session Workflow</div>')

    steps = [
        ("1", "Start the app",
         "Open a terminal and run: <code style='color:#f59e0b;font-family:IBM Plex Mono,monospace;font-size:12px;'>streamlit run app.py --server.port 8504</code>"
         "<br>Then open <code style='color:#f59e0b;font-family:IBM Plex Mono,monospace;font-size:12px;'>http://localhost:8504</code> in your browser. "
         "Keep this tab open — the app is your log + analytics dashboard.",
         None),

        ("2", "Open Claude in the sandbox",
         "In a separate terminal: <code style='color:#f59e0b;font-family:IBM Plex Mono,monospace;font-size:12px;'>cd ~/ClaudeCode/agentic-rd-sandbox &amp;&amp; claude</code>"
         "<br>Tell it: <strong style='color:#d1d5db;'>\"scan live lines and tell me what looks good.\"</strong> "
         "Claude fetches the current odds, runs every kill switch and grade filter, and surfaces top candidates with full reasoning. "
         "You don't need to read each card manually.",
         None),

        ("3", "Review Claude's picks",
         "Claude shows each candidate: grade (A / B / C / NEAR MISS), edge%, sharp score, game time, and why it passed or failed kill switches. "
         "Ask anything: <em>\"why is this NUCLEAR?\"</em> or <em>\"is there RLM on this game?\"</em> or <em>\"what's the closing line for comp?\"</em> "
         "Claude has full context of the math — it doesn't just surface the card, it explains the signal.",
         "📊 Live Lines"),

        ("4", "Approve a bet",
         "Reply <strong style='color:#22c55e;'>\"bet it\"</strong> and Claude logs the bet in the UI for you, "
         "pre-filling sport, matchup, target, price, edge, kelly, grade, and all analytics metadata. "
         "Review the pre-filled fields, add your stake, confirm. "
         "Reply <strong style='color:#9ca3af;'>\"skip\"</strong> and Claude notes it in the session — useful for tracking near-misses.",
         "📝 Bet Tracker → Log Bet"),

        ("5", "Grade after the game",
         "Go to <strong>Bet Tracker → Grade Bet</strong>. Select the bet, choose Win / Loss / Void, "
         "enter the closing price (CLV). P&amp;L and CLV beat rate populate automatically. "
         "Ask Claude: <em>\"what was the final line for [game]?\"</em> if you need help finding it.",
         "📝 Bet Tracker → Grade Bet"),

        ("6", "Repeat until 10 resolved",
         "Once 10 bets are graded, the Analytics page unlocks: sharp score ROI correlation, "
         "CLV beat rate, RLM lift, equity curve. "
         "Ask Claude: <em>\"interpret the first analytics run\"</em> — it will tell you what the numbers mean and whether the model is validating.",
         "📈 Analytics (unlocks at 10)"),

        ("7", "Monitor line movement",
         "Claude alerts you to RLM events in chat — it detects when money moves against public consensus. "
         "A second poll confirming the shift is required before RLM is scored. "
         "The Line History page shows the full movement record for any game.",
         "📉 Line History"),
    ]

    for num, title, desc, nav in steps:
        nav_html = f'<div class="step-nav">→ {nav}</div>' if nav else ""
        st.html(f"""
        <div class="step-card">
          <div class="step-num">{num}</div>
          <div class="step-body">
            <div class="step-title">{title}</div>
            <div class="step-desc">{desc}</div>
            {nav_html}
          </div>
        </div>
        """)

    # ---- Signal grades ----
    st.html('<div class="guide-header">Signal Grades</div>')
    st.html("""
    <div class="sig-row">
      <div class="sig-pill-nuclear">NUCLEAR</div>
      <div class="sig-detail">
        <strong>Sharp Score ≥ 90.</strong> Requires RLM confirmation + injury boost in the same game.
        Kelly size: <strong>2.0u</strong>. Fires very rarely — treat it seriously.
      </div>
    </div>
    <div class="sig-row">
      <div class="sig-pill-standard">STANDARD</div>
      <div class="sig-detail">
        <strong>Sharp Score ≥ 80.</strong> Solid edge with market confirmation.
        Kelly size: <strong>1.0u</strong>. Main bread-and-butter bet grade.
      </div>
    </div>
    <div class="sig-row">
      <div class="sig-pill-lean">LEAN</div>
      <div class="sig-detail">
        <strong>Sharp Score ≥ 45.</strong> Minimum threshold met. Use as small position or pass.
        Kelly size: <strong>0.5u</strong>. Useful for data collection early in calibration phase.
      </div>
    </div>
    """)

    # ---- Kill switch reference ----
    st.html('<div class="guide-header">Kill Switches (auto-applied)</div>')
    st.markdown("These automatically disqualify candidates — you never need to check them manually.")

    st.html("""
    <div class="ks-container">
      <div class="ks-row">
        <div class="ks-sport">NBA</div>
        <div class="ks-rule">Road back-to-back with &lt;8% edge → KILL. PDO regression: team running hot/cold on luck → KILL.</div>
        <div class="ks-on">LIVE</div>
      </div>
      <div class="ks-row">
        <div class="ks-sport">NFL</div>
        <div class="ks-rule">Wind &gt;20mph → KILL totals. Wind &gt;15mph → force UNDER only. Backup QB → KILL <em>(STUB — not yet wired to live data)</em>.</div>
        <div class="ks-on">LIVE</div>
      </div>
      <div class="ks-row">
        <div class="ks-sport">NHL</div>
        <div class="ks-rule">Starting goalie not officially confirmed → KILL. Uses free NHL Stats API, zero quota cost.</div>
        <div class="ks-on">LIVE</div>
      </div>
      <div class="ks-row">
        <div class="ks-sport">TENNIS</div>
        <div class="ks-rule">Surface mismatch (clay specialist on grass, etc.) → KILL. Win rate from ATP/WTA data.</div>
        <div class="ks-on">LIVE</div>
      </div>
      <div class="ks-row">
        <div class="ks-sport">SOCCER</div>
        <div class="ks-rule">Market drift + dead rubber detection. 3-way consensus required for h2h lines.</div>
        <div class="ks-on">LIVE</div>
      </div>
      <div class="ks-row">
        <div class="ks-sport">NCAAB</div>
        <div class="ks-rule">3PT reliance &gt;40% + road game → KILL. Tempo mismatch gate.</div>
        <div class="ks-on">LIVE</div>
      </div>
      <div class="ks-row">
        <div class="ks-sport">MLB</div>
        <div class="ks-rule">Collar-only mode (season gate: active Apr 1, 2026).</div>
        <div class="ks-on">COLLAR</div>
      </div>
    </div>
    """)


# ---------------------------------------------------------------------------
# RIGHT COL — Log Bet glossary + gate status
# ---------------------------------------------------------------------------
with col_side:

    st.html('<div class="guide-header">Log Bet — Field Glossary</div>')
    st.html("""
    <div class="gloss-container">
      <div class="gloss-row">
        <div class="gloss-key">Sport</div>
        <div class="gloss-val">NBA, NFL, NHL, Soccer, Tennis, etc.</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Matchup</div>
        <div class="gloss-val">e.g. <strong>Lakers @ Celtics</strong></div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Market Type</div>
        <div class="gloss-val"><strong>spreads</strong> (point spread), <strong>totals</strong> (over/under), <strong>h2h</strong> (moneyline)</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Target</div>
        <div class="gloss-val">Team or side you are betting. e.g. <strong>Celtics -4.5</strong> or <strong>Over 225.5</strong></div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Price</div>
        <div class="gloss-val">American odds you got. e.g. <strong>-110</strong>, <strong>+135</strong></div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Edge %</div>
        <div class="gloss-val">How much you're beating the fair price. Min threshold: <strong>3.5%</strong></div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Kelly Size</div>
        <div class="gloss-val">Model-recommended stake in units. <strong>0.5</strong> = LEAN, <strong>1.0</strong> = STANDARD, <strong>2.0</strong> = NUCLEAR</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Stake ($)</div>
        <div class="gloss-val">Actual dollars wagered (your choice)</div>
      </div>
    </div>
    """)

    st.html('<div style="margin-top:4px;"></div>')
    st.html('<div class="guide-header">Analytics Metadata Fields</div>')
    st.html("""
    <div style="background:#111827;border:1px solid #374151;border-radius:4px;padding:8px 10px;margin-bottom:12px;">
      <div style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#6b7280;">
        Fill these when logging — they unlock the Analytics page at 10 resolved bets.
      </div>
    </div>
    <div class="gloss-container">
      <div class="gloss-row">
        <div class="gloss-key">Sharp Score</div>
        <div class="gloss-val">0–100. Copy from the candidate card. Drives ROI correlation analysis.</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Line</div>
        <div class="gloss-val">The spread or total value at time of bet. e.g. <strong>-4.5</strong> or <strong>223.5</strong></div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Book</div>
        <div class="gloss-val">Sportsbook where you placed the bet. Used for per-book ROI breakdown.</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">RLM Confirmed</div>
        <div class="gloss-val">Check if the app showed RLM (Reverse Line Movement) on this game. Enables RLM lift analysis.</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Days to Game</div>
        <div class="gloss-val">How far out you bet. <strong>0</strong> = day of, <strong>1</strong> = day before. Timing analysis.</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Signal</div>
        <div class="gloss-val">What triggered the bet. e.g. <strong>sharp</strong>, <strong>rlm_confirmed</strong>, <strong>efficiency_edge</strong>, <strong>b2b</strong></div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Tags</div>
        <div class="gloss-val">Comma-separated labels for slice-and-dice filtering. e.g. <strong>nba,home_dog,rlm</strong></div>
      </div>
    </div>
    """)

    st.html('<div class="guide-header">Gate Status</div>')
    st.html("""
    <div class="gate-container">
      <div class="gate-row">
        <div class="gate-name">Sharp score calibration (10 graded bets)</div>
        <div class="gate-status-wait">4 logged · 0 graded</div>
        <div class="gate-note">Need 6 more resolved to unlock</div>
      </div>
      <div class="gate-row">
        <div class="gate-name">CLV verdict (10 graded bets)</div>
        <div class="gate-status-wait">WAITING</div>
        <div class="gate-note">Shares gate with calibration</div>
      </div>
      <div class="gate-row">
        <div class="gate-name">SHARP_THRESHOLD raise (5 live sessions + 20 RLM fires)</div>
        <div class="gate-status-wait">IN PROGRESS</div>
        <div class="gate-note">Currently 45 → raises to 50–55 when gates met</div>
      </div>
      <div class="gate-row">
        <div class="gate-name">MLB kill switch</div>
        <div class="gate-status-wait">WAITING</div>
        <div class="gate-note">Activates Apr 1 2026</div>
      </div>
      <div class="gate-row">
        <div class="gate-name">Analytics page (charts)</div>
        <div class="gate-status-wait">LOCKED</div>
        <div class="gate-note">Unlocks at 10 graded bets</div>
      </div>
      <div class="gate-row">
        <div class="gate-name">Kill switch coverage</div>
        <div class="gate-status-ok">LIVE</div>
        <div class="gate-note">NBA / NFL / NHL / NCAAB / Soccer / Tennis active</div>
      </div>
    </div>
    """)

    st.html('<div class="guide-header">Odds API Budget</div>')
    st.html("""
    <div class="gloss-container">
      <div class="gloss-row">
        <div class="gloss-key">Monthly budget</div>
        <div class="gloss-val">≤ 10,000 / 20,000 credits (50% floor)</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Daily allowance</div>
        <div class="gloss-val">Auto-computed: remaining monthly budget ÷ days to billing</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Session soft limit</div>
        <div class="gloss-val">120 credits → warning logged</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Session hard stop</div>
        <div class="gloss-val">200 credits → all fetches halted</div>
      </div>
      <div class="gloss-row">
        <div class="gloss-key">Billing reserve</div>
        <div class="gloss-val">Never go below 150 remaining</div>
      </div>
    </div>
    """)
