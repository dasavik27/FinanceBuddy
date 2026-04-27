"""
UI Components Module
Reusable Streamlit components and UI helpers
"""

import streamlit as st
import pandas as pd
from utils.formatting import fmt_inr, fmt_percentage
from config import CATEGORY_COLORS


def render_header(title: str, subtitle: str = ""):
    """Render a page header."""
    st.markdown(f"""
        <div style='margin-bottom: 24px;'>
            <div style='font-size: 28px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px;'>{title}</div>
            {f'<div style="font-size: 14px; color: #64748B; margin-top: 4px;">{subtitle}</div>' if subtitle else ''}
        </div>
    """, unsafe_allow_html=True)


def render_section_header(title: str, subtitle: str = ""):
    """Render a section header."""
    st.markdown(f"""
        <div style='margin-bottom: 16px;'>
            <div class='section-head'>{title}</div>
            {f'<div class="section-sub">{subtitle}</div>' if subtitle else ''}
        </div>
    """, unsafe_allow_html=True)


def render_metric_row(metrics: dict):
    """Render a row of metrics in columns."""
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        with col:
            st.metric(label, value)


def render_holdings_table(df: pd.DataFrame, show_cols: list = None):
    """Render a formatted holdings table."""
    if df.empty:
        st.info("No holdings to display")
        return
    
    if show_cols:
        df = df[show_cols]
    
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_category_distribution(df: pd.DataFrame):
    """Render category-wise distribution summary."""
    if df.empty:
        st.info("No data available")
        return
    
    summary = df.groupby("Category").agg({
        "Market Value": "sum",
        "Invested": "sum",
        "Fund": "count"
    }).rename(columns={"Fund": "Count"})
    
    summary["% of Portfolio"] = (summary["Market Value"] / summary["Market Value"].sum() * 100).round(2)
    summary["Gain %"] = ((summary["Market Value"] - summary["Invested"]) / summary["Invested"] * 100).round(2)
    
    summary["Market Value"] = summary["Market Value"].apply(fmt_inr)
    summary["Invested"] = summary["Invested"].apply(fmt_inr)
    
    st.dataframe(summary, use_container_width=True)


def show_onboarding_screen():
    """Display the onboarding/welcome screen."""
    st.markdown("""
        <div class="onboard-hero">
            <div class="onboard-title" style="background:linear-gradient(135deg,#0A0F1E 0%,#5B5FD6 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">Know your portfolio.<br>Beat the benchmark.</div>
            <div class="onboard-sub">Upload your CAMS/KFintech CAS and get institutional-grade analytics — instantly, privately.</div>
            <div class="step-grid">
                <div class="step-card">
                    <div class="step-num">STEP 1</div>
                    <div class="step-title">CAS PDF Import</div>
                    <div class="step-desc">Get a <b>Detailed CAS</b> from cams.com, kfintech.com. Covers all AMCs with full transaction history.</div>
                </div>
                <div class="step-card">
                    <div class="step-num">STEP 2</div>
                    <div class="step-title">Upload & analyze</div>
                    <div class="step-desc">Enter your PAN password, upload the file in the sidebar, and click <b>Analyze Portfolio</b>. Zero data retention.</div>
                </div>
                <div class="step-card">
                    <div class="step-num">STEP 3</div>
                    <div class="step-title">Get Smart Insights</div>
                    <div class="step-desc">View alpha vs benchmark, expense analysis, risk metrics, and actionable recommendations.</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def show_footer():
    """Display the application footer."""
    from config import FOOTER_TEXT
    st.markdown(f"""
        <div class="footer-note">
            {FOOTER_TEXT} · Built with ❤ for Indian MF investors
        </div>
    """, unsafe_allow_html=True)
