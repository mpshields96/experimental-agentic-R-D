"""
pages/07_analytics.py — Titanium-Agentic
==========================================
Advanced Analytics — Phase 1

V37 Schema Review approved 2026-02-24. Session 25 build.

Phase 1 charts:
  1. Sharp score ROI correlation (bin bar chart + Pearson r)
  2. RLM confirmation lift (win rate + ROI comparison)
  3. CLV beat rate (positive CLV %, avg CLV by result)

Sample-size guard: minimum 30 resolved bets before any chart renders.
Data source: core/line_logger.get_bets() → core/analytics.* pure functions.
Architecture: analytics logic is source-agnostic (accepts list[dict]) per V37 spec.

UI design: amber/dark trading terminal aesthetic.
  - Monospace data values, clean section headers
  - Amber accent (#f59e0b), card background (#1a1d23)
  - NO: rainbow palettes, excessive expanders, verbose labels
"""

import streamlit as st
import pandas as pd

from core.line_logger import get_bets
from core.analytics import (
    get_bet_counts,
    compute_sharp_roi_correlation,
    compute_rlm_correlation,
    compute_clv_beat_rate,
    compute_equity_curve,
    compute_rolling_metrics,
    compute_book_breakdown,
    MIN_RESOLVED,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Analytics — Titanium",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Global CSS — terminal dark aesthetic
# ---------------------------------------------------------------------------

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #0e1117;
    color: #d1d5db;
  }
  .block-container { padding-top: 1.5rem; max-width: 1400px; }

  h1, h2, h3 { font-family: 'IBM Plex Sans', sans-serif; }

  /* Section headers */
  .section-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 0.75rem;
    margin-top: 0.25rem;
  }

  /* KPI card */
  .kpi-card {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 6px;
    padding: 14px 18px 12px;
    text-align: center;
  }
  .kpi-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 4px;
  }
  .kpi-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #f59e0b;
    line-height: 1.1;
  }
  .kpi-value.positive { color: #22c55e; }
  .kpi-value.negative { color: #ef4444; }
  .kpi-value.neutral { color: #d1d5db; }
  .kpi-sub {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    color: #6b7280;
    margin-top: 3px;
  }

  /* Chart card wrapper */
  .chart-card {
    background: #1a1d23;
    border: 1px solid #2d3139;
    border-radius: 6px;
    padding: 20px;
    margin-bottom: 16px;
  }
  .chart-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #f59e0b;
    margin-bottom: 4px;
  }
  .chart-subtitle {
    font-size: 0.8rem;
    color: #6b7280;
    margin-bottom: 12px;
  }

  /* Sample guard */
  .sample-guard {
    background: #1a1d23;
    border: 1px solid #374151;
    border-left: 3px solid #f59e0b;
    border-radius: 4px;
    padding: 14px 18px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #9ca3af;
    margin-bottom: 12px;
  }
  .sample-guard .guard-title {
    color: #f59e0b;
    font-weight: 600;
    margin-bottom: 4px;
    font-size: 0.72rem;
    letter-spacing: 0.05em;
  }

  /* Comparison bar (RLM) */
  .comp-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
  }
  .comp-label { width: 90px; color: #9ca3af; text-align: right; }
  .comp-bar-wrap { flex: 1; background: #0e1117; border-radius: 3px; height: 10px; }
  .comp-bar { height: 10px; border-radius: 3px; }
  .comp-bar.rlm { background: #f59e0b; }
  .comp-bar.no-rlm { background: #374151; }
  .comp-val { width: 60px; text-align: right; color: #d1d5db; }

  /* Lift badge */
  .lift-badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    padding: 3px 10px;
    border-radius: 3px;
    font-weight: 600;
  }
  .lift-badge.positive { background: rgba(34,197,94,0.15); color: #22c55e; }
  .lift-badge.negative { background: rgba(239,68,68,0.12); color: #ef4444; }
  .lift-badge.neutral  { background: rgba(209,213,219,0.1); color: #9ca3af; }

  /* CLV beat row */
  .clv-beat-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #2d3139;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
  }
  .clv-beat-row:last-child { border-bottom: none; }
  .clv-key { color: #9ca3af; }
  .clv-val { color: #d1d5db; font-weight: 500; }
  .clv-val.pos { color: #22c55e; }
  .clv-val.neg { color: #ef4444; }

  /* Page title row */
  .page-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.05rem;
    font-weight: 600;
    color: #d1d5db;
    letter-spacing: 0.04em;
  }
  .page-badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    padding: 2px 7px;
    border-radius: 2px;
    background: rgba(245,158,11,0.15);
    color: #f59e0b;
    letter-spacing: 0.1em;
    vertical-align: middle;
    margin-left: 8px;
  }

  /* Divider */
  .dim-divider {
    border: none;
    border-top: 1px solid #2d3139;
    margin: 18px 0;
  }

  /* Correlation r badge */
  .r-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    padding: 3px 10px;
    border-radius: 3px;
  }

  /* Equity metric row */
  .eq-metric {
    background: #151720;
    border: 1px solid #2d3139;
    border-radius: 4px;
    padding: 10px 14px;
    text-align: center;
  }
  .eq-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #6b7280;
    margin-bottom: 4px;
  }
  .eq-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.1rem;
    font-weight: 600;
    color: #d1d5db;
  }
  .eq-val.pos { color: #22c55e; }
  .eq-val.neg { color: #ef4444; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data load
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _load_bets():
    return get_bets(limit=500)


bets = _load_bets()
counts = get_bet_counts(bets)

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.html("""
<div style="margin-bottom:20px;">
  <span class="page-title">ANALYTICS</span>
  <span class="page-badge">PHASE 1</span>
</div>
<div class="section-header">Model performance · Sharp score validation · CLV tracking</div>
""")

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------

c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    st.html(f"""
    <div class="kpi-card">
      <div class="kpi-label">Total Bets</div>
      <div class="kpi-value neutral">{counts['total']}</div>
    </div>
    """)

with c2:
    st.html(f"""
    <div class="kpi-card">
      <div class="kpi-label">Resolved</div>
      <div class="kpi-value neutral">{counts['resolved']}</div>
    </div>
    """)

with c3:
    st.html(f"""
    <div class="kpi-card">
      <div class="kpi-label">Pending</div>
      <div class="kpi-value neutral">{counts['pending']}</div>
    </div>
    """)

with c4:
    wr_pct = round(counts['wins'] / counts['resolved'] * 100, 1) if counts['resolved'] > 0 else 0.0
    wr_cls = "positive" if wr_pct >= 55 else "negative" if wr_pct < 45 else "neutral"
    st.html(f"""
    <div class="kpi-card">
      <div class="kpi-label">Win Rate</div>
      <div class="kpi-value {wr_cls}">{wr_pct:.1f}%</div>
    </div>
    """)

with c5:
    st.html(f"""
    <div class="kpi-card">
      <div class="kpi-label">Wins</div>
      <div class="kpi-value positive">{counts['wins']}</div>
    </div>
    """)

with c6:
    need = max(0, MIN_RESOLVED - counts["resolved"])
    prog_cls = "positive" if counts["resolved"] >= MIN_RESOLVED else "neutral"
    prog_val = f"{counts['resolved']}/{MIN_RESOLVED}" if counts["resolved"] < MIN_RESOLVED else "✓"
    st.html(f"""
    <div class="kpi-card">
      <div class="kpi-label">Cal. Gate</div>
      <div class="kpi-value {prog_cls}" style="font-size:1.1rem;">{prog_val}</div>
      <div class="kpi-sub">Need {need} more</div>
    </div>
    """)

st.html('<hr class="dim-divider">')

# ---------------------------------------------------------------------------
# Sample guard helper
# ---------------------------------------------------------------------------

def _sample_guard(n_resolved: int) -> bool:
    """
    Render guard if below threshold. Returns True if below (caller should stop).
    """
    if n_resolved < MIN_RESOLVED:
        need = MIN_RESOLVED - n_resolved
        st.html(f"""
        <div class="sample-guard">
          <div class="guard-title">⚠ INSUFFICIENT DATA</div>
          Minimum {MIN_RESOLVED} resolved bets required for correlation analysis.<br>
          Current: <strong style="color:#f59e0b;">{n_resolved}</strong> resolved —
          need <strong style="color:#d1d5db;">{need}</strong> more to unlock.
        </div>
        """)
        return True
    return False


# ---------------------------------------------------------------------------
# Section 1 — Sharp score ROI correlation
# ---------------------------------------------------------------------------

st.html('<div class="section-header">01 — Sharp Score ROI Correlation</div>')

sharp_result = compute_sharp_roi_correlation(bets)

if _sample_guard(sharp_result["n_resolved"]):
    # Show placeholder bar chart with zeroed bins
    st.html("""
    <div class="chart-card">
      <div class="chart-title">Sharp Score → ROI</div>
      <div class="chart-subtitle" style="color:#6b7280; font-size:0.75rem; margin-top:4px;">
        Chart unlocks at 30 resolved bets. Log bets via Live Lines → Log Bet.
      </div>
    </div>
    """)
else:
    bins_df = pd.DataFrame(sharp_result["bins"])

    col_chart, col_meta = st.columns([3, 1])

    with col_chart:
        if not bins_df.empty and bins_df["n"].sum() > 0:
            chart_data = bins_df[bins_df["n"] > 0].set_index("label")[["roi_pct"]]
            chart_data.index.name = "Score Bin"
            chart_data.columns = ["ROI %"]
            st.bar_chart(chart_data, color="#f59e0b", height=220)

    with col_meta:
        r_val = sharp_result.get("correlation_r")
        r_display = f"{r_val:.3f}" if r_val is not None else "—"
        r_label = sharp_result["correlation_label"]
        r_css = "positive" if r_val and r_val > 0.1 else "negative" if r_val and r_val < -0.1 else "neutral"

        mean_w = sharp_result["mean_score_winners"]
        mean_l = sharp_result["mean_score_losers"]
        gap = round(mean_w - mean_l, 1)
        gap_cls = "pos" if gap > 0 else "neg"

        st.html(f"""
        <div class="chart-card" style="height:100%;">
          <div class="chart-title">Correlation</div>
          <div style="margin: 14px 0;">
            <div class="kpi-label">Pearson r</div>
            <div class="lift-badge {r_css}" style="font-size:1rem; padding:5px 12px; margin-top:4px;">
              {r_display}
            </div>
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                        color:#9ca3af; margin-top:6px; text-transform:uppercase;
                        letter-spacing:0.08em;">
              {r_label}
            </div>
          </div>
          <hr class="dim-divider" style="margin:10px 0;">
          <div class="clv-beat-row">
            <span class="clv-key">Avg score (W)</span>
            <span class="clv-val pos">{mean_w}</span>
          </div>
          <div class="clv-beat-row">
            <span class="clv-key">Avg score (L)</span>
            <span class="clv-val neg">{mean_l}</span>
          </div>
          <div class="clv-beat-row">
            <span class="clv-key">Gap W-L</span>
            <span class="clv-val {gap_cls}">{gap:+.1f}</span>
          </div>
          <div class="clv-beat-row">
            <span class="clv-key">Resolved N</span>
            <span class="clv-val">{sharp_result["n_resolved"]}</span>
          </div>
        </div>
        """)

    # Bin detail table
    if not bins_df.empty:
        display_bins = bins_df[bins_df["n"] > 0].copy()
        if not display_bins.empty:
            display_bins.columns = ["Score Range", "Bets (N)", "ROI %", "Win Rate %"]
            st.dataframe(
                display_bins.style.format({
                    "ROI %": "{:.1f}",
                    "Win Rate %": "{:.1f}",
                }).background_gradient(subset=["ROI %"], cmap="RdYlGn", vmin=-20, vmax=20),
                use_container_width=True,
                hide_index=True,
            )

st.html('<hr class="dim-divider">')

# ---------------------------------------------------------------------------
# Section 2 — RLM Confirmation Lift
# ---------------------------------------------------------------------------

st.html('<div class="section-header">02 — RLM Confirmation Lift</div>')

rlm_result = compute_rlm_correlation(bets)

if _sample_guard(rlm_result["n_resolved"]):
    st.html("""
    <div class="chart-card">
      <div class="chart-title">RLM vs No-RLM Performance</div>
      <div class="chart-subtitle" style="color:#6b7280; font-size:0.75rem; margin-top:4px;">
        Unlocks at 30 resolved bets. RLM fires on 2nd fetch after 3% implied prob shift.
      </div>
    </div>
    """)
else:
    col_win, col_roi, col_lift = st.columns(3)

    rlm = rlm_result["rlm"]
    no_rlm = rlm_result["no_rlm"]
    lift_wr = rlm_result["lift_win_rate"]
    lift_roi = rlm_result["lift_roi"]

    # Normalize bar widths (max width = 100%)
    max_wr = max(rlm["win_rate"], no_rlm["win_rate"], 1.0)
    rlm_wr_w = int(rlm["win_rate"] / max_wr * 100)
    no_rlm_wr_w = int(no_rlm["win_rate"] / max_wr * 100)

    max_roi = max(abs(rlm["roi_pct"]), abs(no_rlm["roi_pct"]), 1.0)
    rlm_roi_w = int(abs(rlm["roi_pct"]) / max_roi * 100) if rlm["roi_pct"] >= 0 else 0
    no_rlm_roi_w = int(abs(no_rlm["roi_pct"]) / max_roi * 100) if no_rlm["roi_pct"] >= 0 else 0

    with col_win:
        st.html(f"""
        <div class="chart-card">
          <div class="chart-title">Win Rate</div>
          <div style="margin-top:14px;">
            <div class="comp-row">
              <div class="comp-label">RLM</div>
              <div class="comp-bar-wrap">
                <div class="comp-bar rlm" style="width:{rlm_wr_w}%;"></div>
              </div>
              <div class="comp-val">{rlm["win_rate"]:.1f}%</div>
            </div>
            <div class="comp-row">
              <div class="comp-label">No RLM</div>
              <div class="comp-bar-wrap">
                <div class="comp-bar no-rlm" style="width:{no_rlm_wr_w}%;"></div>
              </div>
              <div class="comp-val">{no_rlm["win_rate"]:.1f}%</div>
            </div>
          </div>
          <div style="margin-top:12px;">
            <span style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                         color:#6b7280; text-transform:uppercase; letter-spacing:0.08em;">
              Lift:
            </span>
            <span class="lift-badge {'positive' if lift_wr > 0 else 'negative' if lift_wr < 0 else 'neutral'}"
                  style="margin-left:6px;">
              {lift_wr:+.1f}pp
            </span>
          </div>
          <div style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                      color:#6b7280; margin-top:8px;">
            RLM N={rlm['n']} · No-RLM N={no_rlm['n']}
          </div>
        </div>
        """)

    with col_roi:
        st.html(f"""
        <div class="chart-card">
          <div class="chart-title">ROI %</div>
          <div style="margin-top:14px;">
            <div class="comp-row">
              <div class="comp-label">RLM</div>
              <div class="comp-bar-wrap">
                <div class="comp-bar rlm" style="width:{rlm_roi_w}%;"></div>
              </div>
              <div class="comp-val">{rlm["roi_pct"]:+.1f}%</div>
            </div>
            <div class="comp-row">
              <div class="comp-label">No RLM</div>
              <div class="comp-bar-wrap">
                <div class="comp-bar no-rlm" style="width:{no_rlm_roi_w}%;"></div>
              </div>
              <div class="comp-val">{no_rlm["roi_pct"]:+.1f}%</div>
            </div>
          </div>
          <div style="margin-top:12px;">
            <span style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                         color:#6b7280; text-transform:uppercase; letter-spacing:0.08em;">
              Lift:
            </span>
            <span class="lift-badge {'positive' if lift_roi > 0 else 'negative' if lift_roi < 0 else 'neutral'}"
                  style="margin-left:6px;">
              {lift_roi:+.1f}pp
            </span>
          </div>
          <div style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem;
                      color:#6b7280; margin-top:8px;">
            Edge signal confirming sharp money direction
          </div>
        </div>
        """)

    with col_lift:
        verdict_wr = "✓ Signal working" if lift_wr > 5 else "~ Inconclusive" if lift_wr >= 0 else "✗ Negative signal"
        verdict_roi = "✓ ROI premium" if lift_roi > 5 else "~ Inconclusive" if lift_roi >= 0 else "✗ ROI drag"
        st.html(f"""
        <div class="chart-card">
          <div class="chart-title">Verdict</div>
          <div style="margin-top:14px; font-family:'IBM Plex Mono',monospace; font-size:0.75rem;">
            <div style="padding: 8px 0; border-bottom: 1px solid #2d3139;">
              <div style="color:#6b7280; font-size:0.62rem; text-transform:uppercase;
                          letter-spacing:0.08em; margin-bottom:4px;">Win rate lift</div>
              <div style="color:{'#22c55e' if lift_wr > 5 else '#f59e0b' if lift_wr >= 0 else '#ef4444'}">
                {verdict_wr}
              </div>
            </div>
            <div style="padding: 8px 0; border-bottom: 1px solid #2d3139;">
              <div style="color:#6b7280; font-size:0.62rem; text-transform:uppercase;
                          letter-spacing:0.08em; margin-bottom:4px;">ROI lift</div>
              <div style="color:{'#22c55e' if lift_roi > 5 else '#f59e0b' if lift_roi >= 0 else '#ef4444'}">
                {verdict_roi}
              </div>
            </div>
            <div style="padding: 8px 0;">
              <div style="color:#6b7280; font-size:0.62rem; text-transform:uppercase;
                          letter-spacing:0.08em; margin-bottom:4px;">RLM threshold</div>
              <div style="color:#9ca3af;">3% implied prob shift</div>
            </div>
          </div>
        </div>
        """)

st.html('<hr class="dim-divider">')

# ---------------------------------------------------------------------------
# Section 3 — CLV Beat Rate
# ---------------------------------------------------------------------------

st.html('<div class="section-header">03 — Closing Line Value</div>')

clv_result = compute_clv_beat_rate(bets)

if _sample_guard(clv_result["n_resolved"]):
    st.html("""
    <div class="chart-card">
      <div class="chart-title">CLV Beat Rate</div>
      <div class="chart-subtitle" style="color:#6b7280; font-size:0.75rem; margin-top:4px;">
        Grade bets in Bet Tracker (Tab 4) with closing prices to populate CLV data.
      </div>
    </div>
    """)
else:
    col_gauge, col_detail = st.columns([1, 2])

    beat_rate = clv_result["beat_rate"]
    n_with_clv = clv_result["n_with_clv"]
    avg_clv = clv_result["avg_clv"]
    beat_cls = "positive" if beat_rate >= 55 else "negative" if beat_rate < 45 else "neutral"
    avg_cls = "pos" if avg_clv > 0 else "neg"
    avg_disp = f"+{avg_clv:.4f}" if avg_clv > 0 else f"{avg_clv:.4f}"

    with col_gauge:
        # Arc-style percentage display
        arc_pct = int(beat_rate)
        arc_color = "#22c55e" if beat_rate >= 55 else "#ef4444" if beat_rate < 45 else "#f59e0b"
        st.html(f"""
        <div class="chart-card" style="text-align:center; padding:28px 20px;">
          <div class="chart-title" style="text-align:left;">CLV Beat Rate</div>
          <div style="margin: 20px 0 8px; font-family:'IBM Plex Mono',monospace;">
            <div style="font-size:3rem; font-weight:600; color:{arc_color}; line-height:1;">
              {beat_rate:.1f}%
            </div>
            <div style="font-size:0.65rem; text-transform:uppercase; letter-spacing:0.12em;
                        color:#6b7280; margin-top:6px;">
              of bets beat closing line
            </div>
          </div>
          <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#9ca3af;
                      border-top:1px solid #2d3139; padding-top:10px; margin-top:10px;">
            N = {n_with_clv} with CLV data
          </div>
        </div>
        """)

    with col_detail:
        clv_w = clv_result["avg_clv_winners"]
        clv_l = clv_result["avg_clv_losers"]
        pos_n = clv_result["clv_positive"]
        neg_n = clv_result["clv_negative"]
        zero_n = clv_result["clv_zero"]
        clv_w_disp = f"+{clv_w:.4f}" if clv_w > 0 else f"{clv_w:.4f}"
        clv_l_disp = f"+{clv_l:.4f}" if clv_l > 0 else f"{clv_l:.4f}"

        st.html(f"""
        <div class="chart-card">
          <div class="chart-title">CLV Breakdown</div>
          <div style="margin-top:12px;">
            <div class="clv-beat-row">
              <span class="clv-key">Avg CLV (all bets)</span>
              <span class="clv-val {avg_cls}">{avg_disp}</span>
            </div>
            <div class="clv-beat-row">
              <span class="clv-key">Avg CLV — Winners</span>
              <span class="clv-val {'pos' if clv_w > 0 else 'neg'}">{clv_w_disp}</span>
            </div>
            <div class="clv-beat-row">
              <span class="clv-key">Avg CLV — Losers</span>
              <span class="clv-val {'pos' if clv_l > 0 else 'neg'}">{clv_l_disp}</span>
            </div>
            <div class="clv-beat-row">
              <span class="clv-key">Positive CLV bets</span>
              <span class="clv-val pos">{pos_n}</span>
            </div>
            <div class="clv-beat-row">
              <span class="clv-key">Negative CLV bets</span>
              <span class="clv-val neg">{neg_n}</span>
            </div>
            <div class="clv-beat-row">
              <span class="clv-key">No CLV data</span>
              <span class="clv-val">{zero_n}</span>
            </div>
          </div>
          <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#6b7280;
                      margin-top:10px; padding-top:8px; border-top:1px solid #2d3139;">
            Positive CLV = beat closing line = long-run edge confirmed.
            Target: beat rate &gt; 55%, avg CLV &gt; +0.01.
          </div>
        </div>
        """)

st.html('<hr class="dim-divider">')

# ---------------------------------------------------------------------------
# Section 4 — Equity Curve (always renders if any resolved bets)
# ---------------------------------------------------------------------------

st.html('<div class="section-header">04 — Equity Curve</div>')

equity = compute_equity_curve(bets)

if equity["n"] == 0:
    st.html("""
    <div class="sample-guard">
      <div class="guard-title">NO RESOLVED BETS</div>
      Grade bets in Bet Tracker to populate the equity curve.
    </div>
    """)
else:
    col_eq, col_eq_meta = st.columns([3, 1])

    with col_eq:
        eq_df = pd.DataFrame({
            "P&L (units)": equity["cumulative_pnl"]
        }, index=pd.to_datetime(equity["dates"]))
        eq_color = "#22c55e" if equity["final_pnl"] >= 0 else "#ef4444"
        st.line_chart(eq_df, color=eq_color, height=200)

    with col_eq_meta:
        final_pnl = equity["final_pnl"]
        max_dd = equity["max_drawdown"]
        pnl_cls = "pos" if final_pnl >= 0 else "neg"
        pnl_disp = f"+{final_pnl:.2f}" if final_pnl >= 0 else f"{final_pnl:.2f}"
        st.html(f"""
        <div class="chart-card">
          <div style="margin-bottom:10px;">
            <div class="eq-metric">
              <div class="eq-label">Total P&amp;L</div>
              <div class="eq-val {pnl_cls}">{pnl_disp}u</div>
            </div>
          </div>
          <div style="margin-bottom:10px;">
            <div class="eq-metric">
              <div class="eq-label">Max Drawdown</div>
              <div class="eq-val neg">-{max_dd:.2f}u</div>
            </div>
          </div>
          <div>
            <div class="eq-metric">
              <div class="eq-label">Resolved N</div>
              <div class="eq-val">{equity['n']}</div>
            </div>
          </div>
        </div>
        """)

st.html('<hr class="dim-divider">')

# ---------------------------------------------------------------------------
# Section 5 — Rolling Metrics
# ---------------------------------------------------------------------------

st.html('<div class="section-header">05 — Rolling Performance</div>')

rolling = compute_rolling_metrics(bets)

col_r1, col_r2, col_r3 = st.columns(3)
roll_cols = [(col_r1, 7, "7-Day"), (col_r2, 30, "30-Day"), (col_r3, 90, "90-Day")]

for col, days, label in roll_cols:
    m = rolling[days]
    wr_c = "positive" if m["win_rate"] >= 55 else "negative" if m["win_rate"] < 45 and m["n"] > 0 else "neutral"
    roi_c = "pos" if m["roi_pct"] > 0 else "neg"
    roi_d = f"+{m['roi_pct']:.1f}%" if m["roi_pct"] > 0 else f"{m['roi_pct']:.1f}%"
    with col:
        st.html(f"""
        <div class="chart-card" style="text-align:center;">
          <div class="chart-title" style="text-align:left;">{label}</div>
          <div style="display:flex; justify-content:space-around; margin-top:14px;">
            <div>
              <div class="kpi-label">Win Rate</div>
              <div class="kpi-value {wr_c}" style="font-size:1.3rem;">
                {m["win_rate"]:.1f}%
              </div>
            </div>
            <div>
              <div class="kpi-label">ROI</div>
              <div class="kpi-value {roi_c}" style="font-size:1.3rem;">{roi_d}</div>
            </div>
            <div>
              <div class="kpi-label">N</div>
              <div class="kpi-value neutral" style="font-size:1.3rem;">{m["n"]}</div>
            </div>
          </div>
        </div>
        """)

st.html('<hr class="dim-divider">')

# ---------------------------------------------------------------------------
# Section 6 — Book Breakdown
# ---------------------------------------------------------------------------

st.html('<div class="section-header">06 — Book Performance</div>')

book_data = compute_book_breakdown(bets)

if not book_data:
    st.html("""
    <div class="sample-guard">
      <div class="guard-title">NO BOOK DATA</div>
      Add book names when logging bets to enable per-book analytics.
    </div>
    """)
else:
    book_df = pd.DataFrame(book_data)
    book_df.columns = ["Book", "Bets (N)", "Win Rate %", "ROI %"]
    st.dataframe(
        book_df.style.format({
            "Win Rate %": "{:.1f}",
            "ROI %": "{:+.1f}",
        }).background_gradient(subset=["ROI %"], cmap="RdYlGn", vmin=-20, vmax=20),
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.html(f"""
<div style="font-family:'IBM Plex Mono',monospace; font-size:0.62rem; color:#374151;
            text-align:center; margin-top:24px; padding-top:12px;
            border-top:1px solid #1f2937;">
  TITANIUM ANALYTICS · PHASE 1 ·
  {counts['resolved']} RESOLVED / {MIN_RESOLVED} GATE · MATH &gt; NARRATIVE
</div>
""")
