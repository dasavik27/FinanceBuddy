"""
FolioIQ - MF Portfolio Intelligence Platform
Main entry point - coordinates UI and business logic

Architecture:
- config.py: Constants and configuration
- utils/: Business logic (formatting, parsing, calculations)
- ui/: User interface (styling, components)
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# Import configuration
from config import (
    BENCHMARKS, PERIOD_MAP, CATEGORY_COLORS, APP_TITLE, APP_ICON, FOOTER_TEXT,
    FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT, RISK_TIERS, MAX_DD_ESTIMATE, EXP_RATIOS
)

# Import utilities
from utils.formatting import fmt_inr, fmt_percentage, fmt_decimal
from utils.parsers import parse_cas, detect_category, detect_amc, detect_cap_type
from utils.calculations import (
    fetch_benchmark, compute_xirr, compute_benchmark_xirr,
    compute_period_comparison, compute_rolling_returns, estimate_expense_drag,
    expense_leakage_20yr, elss_lock_in_analysis, detect_sector, compute_portfolio_score
)

# Import UI components
from ui.styles import apply_theme, show_alert
from ui.components import (
    render_header, render_section_header, render_metric_row,
    render_holdings_table, render_category_distribution, show_onboarding_screen, show_footer
)


# ─────────────────────────────────────────────
# PAGE CONFIGURATION
# ─────────────────────────────────────────────

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon=APP_ICON,
    initial_sidebar_state="expanded"
)

# Apply theme
apply_theme()

# Initialize session state
if "parsed" not in st.session_state:
    st.session_state.parsed = False
    st.session_state.error = None
    st.session_state.df_holdings = pd.DataFrame()
    st.session_state.df_txns = pd.DataFrame()
    st.session_state.df_sips = pd.DataFrame()
    st.session_state.is_partial_cas = False


# ─────────────────────────────────────────────
# SIDEBAR: FILE UPLOAD & FILTERS
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
        <div style='text-align:center; padding: 20px 0;'>
            <div style='font-size:16px;font-weight:800;color:#0F172A;letter-spacing:-0.3px'>FolioIQ</div>
            <div style='font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.8px'>MF Intelligence</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='font-size:11px;color:#475569;margin-bottom:4px'>Upload your CAMS/KFintech Detailed CAS</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Detailed CAS PDF", type=["pdf"], label_visibility="collapsed", key="cas_upload")
    password = st.text_input("PAN Password", type="password", placeholder="ABCDE1234F (uppercase)")

    if st.button("🔍 Analyze Portfolio", use_container_width=True, type="primary", key="btn_cas"):
        if not uploaded_file:
            st.error("Please upload a CAS PDF")
        elif not password:
            st.error("Please enter your PAN password")
        else:
            with st.spinner("Parsing CAS…"):
                df_h, df_t, df_s, err, is_partial = parse_cas(uploaded_file.getvalue(), password)
            if err:
                st.session_state.error = err
                st.session_state.parsed = False
            else:
                st.session_state.df_holdings = df_h
                st.session_state.df_txns = df_t
                st.session_state.df_sips = df_s
                st.session_state.is_partial_cas = is_partial
                st.session_state.parsed = True
                st.session_state.error = None
                st.rerun()

    # Filters (only show if data is parsed)
    if st.session_state.parsed:
        st.markdown("---")
        st.markdown("<div style='font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px'>Global Filters</div>", unsafe_allow_html=True)

        benchmark_name = st.selectbox("Benchmark", list(BENCHMARKS.keys()))

        df_h = st.session_state.df_holdings
        all_cats = sorted(df_h["Category"].unique().tolist()) if not df_h.empty else []
        all_amcs = sorted(df_h["AMC"].unique().tolist()) if not df_h.empty else []

        sel_cats = st.multiselect("Category", all_cats, default=all_cats, key="filter_cat")
        sel_amcs = st.multiselect("AMC", all_amcs, default=all_amcs, key="filter_amc")
        plan_filter = st.radio("Plan Type", ["All", "Direct", "Regular"], horizontal=True)
        min_alloc = st.slider("Min Allocation %", 0.0, 20.0, 0.0, 0.5)

    st.markdown("---")
    st.markdown("<div style='font-size:10px;color:#334155;text-align:center'>SEBI CSCRF 2025 · Zero Data Retention<br>FolioIQ v5.0 · In-memory processing</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────

# Show onboarding if not parsed
if not st.session_state.parsed:
    if st.session_state.error:
        show_alert(f"⚠ <b>Parse Error:</b> {st.session_state.error}", alert_type="danger")
        st.info("Check that you used a 'Detailed CAS' PDF and the correct PAN (uppercase) as password.")
    else:
        show_onboarding_screen()
    st.stop()


# ─────────────────────────────────────────────
# FILTER APPLICATION
# ─────────────────────────────────────────────

df_h_raw = st.session_state.df_holdings.copy()
df_t_raw = st.session_state.df_txns.copy()

if df_h_raw.empty:
    st.warning("PDF parsed but no active holdings found. Ensure you used a 'Detailed' CAS.")
    st.stop()

# Apply filters
df_h = df_h_raw.copy()
if sel_cats:
    df_h = df_h[df_h["Category"].isin(sel_cats)]
if sel_amcs:
    df_h = df_h[df_h["AMC"].isin(sel_amcs)]
if plan_filter != "All":
    df_h = df_h[df_h["Plan"] == plan_filter]
if min_alloc > 0:
    df_h = df_h[df_h["Weight%"] >= min_alloc]

filtered_funds = set(df_h["Fund"].tolist())
df_t = df_t_raw[df_t_raw["Fund"].isin(filtered_funds)] if (not df_t_raw.empty and "Fund" in df_t_raw.columns) else pd.DataFrame()


# ─────────────────────────────────────────────
# KEY METRICS COMPUTATION
# ─────────────────────────────────────────────

total_value = float(df_h["Market Value"].sum())
total_invested = float(df_h["Invested"].sum())
total_gain = total_value - total_invested
gain_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0.0

ticker = BENCHMARKS.get(benchmark_name, "^NSEI")
bench_data = fetch_benchmark(ticker, 9999)

portfolio_xirr = compute_xirr(df_t, total_value)
bench_xirr, bench_sim_value = compute_benchmark_xirr(df_t, bench_data)
alpha = portfolio_xirr - bench_xirr 

portfolio_score = compute_portfolio_score(df_h, portfolio_xirr, bench_xirr)


# ─────────────────────────────────────────────
# HEADER & KEY METRICS
# ─────────────────────────────────────────────

render_header("Portfolio Overview")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Portfolio Value", fmt_inr(total_value), fmt_inr(total_gain))
with col2:
    st.metric("Invested", fmt_inr(total_invested), f"{len(df_h)} funds")
with col3:
    st.metric("XIRR", f"{portfolio_xirr:+.2f}%", f"Alpha: {alpha:+.2f}%")
with col4:
    st.metric("Benchmark XIRR", f"{bench_xirr:+.2f}%", benchmark_name)
with col5:
    st.metric("Portfolio Score", f"{portfolio_score}/100", "Health")


# ─────────────────────────────────────────────
# HOLDINGS & ANALYSIS
# ─────────────────────────────────────────────

st.markdown("---")
render_section_header("Holdings Analysis")

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Fund Holdings")
    render_holdings_table(df_h[["Fund", "Category", "Plan", "Units", "NAV", "Market Value", "Gain%"]].sort_values("Market Value", ascending=False))

with col2:
    render_section_header("Category Distribution")
    render_category_distribution(df_h)


# ─────────────────────────────────────────────
# EXPENSE ANALYSIS
# ─────────────────────────────────────────────

st.markdown("---")
render_section_header("Expense Analysis")

col1, col2, col3 = st.columns(3)
with col1:
    annual_drag = estimate_expense_drag(df_h)
    st.metric("Annual ER Drag", fmt_inr(annual_drag))

with col2:
    exp_20yr = expense_leakage_20yr(df_h)
    st.metric("20yr Lost Opportunity", fmt_inr(exp_20yr["lost_20yr_if_regular"]))

with col3:
    direct_pct = (df_h[df_h["Plan"] == "Direct"]["Market Value"].sum() / total_value * 100) if total_value > 0 else 0
    st.metric("Direct Plans %", f"{direct_pct:.1f}%")


# ─────────────────────────────────────────────
# ELSS ANALYSIS
# ─────────────────────────────────────────────

elss_data = elss_lock_in_analysis(df_h, df_t)
if elss_data:
    st.markdown("---")
    render_section_header("ELSS Lock-in Status")
    st.dataframe(pd.DataFrame(elss_data), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# REGULAR PLAN ALERT
# ─────────────────────────────────────────────

reg_funds = df_h[df_h["Plan"] == "Regular"]["Fund"].tolist()
if reg_funds:
    st.markdown("---")
    show_alert(f'💡 <b>Regular plan alert:</b> {len(reg_funds)} fund(s) are in regular plans. Consider switching to direct equivalents to save on distributor commission.',
              alert_type="warn")


# ─────────────────────────────────────────────
# PORTFOLIO STATISTICS
# ─────────────────────────────────────────────

st.markdown("---")
st.markdown("**Portfolio statistics**")
col_stat1, col_stat2 = st.columns(2)

with col_stat1:
    st.markdown(f"""
    | Parameter | Value |
    |-----------|-------|
    | Total funds | {len(df_h)} |
    | Active holdings | {len(df_h[df_h['Market Value'] > 0])} |
    | AMCs covered | {df_h['AMC'].nunique()} |
    | Categories | {df_h['Category'].nunique()} |
    | Direct plans | {len(df_h[df_h['Plan'] == 'Direct'])} |
    | Regular plans | {len(df_h[df_h['Plan'] == 'Regular'])} |
    """)

with col_stat2:
    st.markdown(f"""
    | Metric | Value |
    |--------|-------|
    | Total invested | {fmt_inr(total_invested)} |
    | Current value | {fmt_inr(total_value)} |
    | Absolute gain | {fmt_inr(total_gain)} |
    | Gain % | {gain_pct:+.2f}% |
    | XIRR | {portfolio_xirr:.2f}% |
    | Alpha vs {benchmark_name} | {alpha:+.2f}% |
    """)


# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────

st.markdown("---")
st.markdown(f"""
<div class="footer-note">
    {FOOTER_TEXT} · Zero Data Retention Architecture · Not financial advice<br>
    Factor Analysis · Smart Insights · Fund Comparison · Built with ❤ for Indian MF investors
</div>
""", unsafe_allow_html=True)
