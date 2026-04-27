"""
UI Styling Module
All CSS and design system for FolioIQ
"""

import streamlit as st


def apply_theme():
    """Apply the complete FolioIQ design system and styling."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
        background: #F7F8FA;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 1px solid #E2E8F0;
    }
    [data-testid="stSidebar"] h1 { color: #0F172A !important; font-size: 18px !important; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stFileUploader label,
    [data-testid="stSidebar"] .stTextInput label { color: #64748B !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.8px; }

    /* ── Metrics ── */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    [data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 700 !important; color: #0F172A !important; }
    [data-testid="stMetricLabel"] { font-size: 11px !important; font-weight: 600 !important; color: #64748B !important; text-transform: uppercase; letter-spacing: 0.6px; }
    [data-testid="stMetricDelta"] { font-size: 13px !important; font-weight: 500 !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 8px;
        color: #64748B;
        font-weight: 500;
        font-size: 13px;
        padding: 8px 18px;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background: #0F172A !important;
        color: #FFFFFF !important;
        border-bottom: none !important;
    }

    /* ── Cards ── */
    .metric-card {
        background: #FFFFFF;
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .card-label { font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px; }
    .card-value { font-size: 24px; font-weight: 700; color: #0F172A; }
    .card-sub { font-size: 13px; color: #64748B; margin-top: 4px; }
    .pos { color: #16A34A; }
    .neg { color: #DC2626; }

    /* ── Section headers ── */
    .section-head {
        font-size: 15px; font-weight: 700; color: #0F172A;
        margin-bottom: 2px; letter-spacing: -0.2px;
    }
    .section-sub { font-size: 12px; color: #94A3B8; margin-bottom: 16px; }

    /* ── Filter bar ── */
    .filter-bar {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    /* ── Badges ── */
    .badge {
        display: inline-block;
        font-size: 10px; font-weight: 700;
        padding: 2px 8px; border-radius: 20px;
        text-transform: uppercase; letter-spacing: 0.5px;
    }
    .badge-equity   { background: #EFF6FF; color: #1D4ED8; }
    .badge-debt     { background: #F0FDF4; color: #15803D; }
    .badge-hybrid   { background: #FFF7ED; color: #C2410C; }
    .badge-elss     { background: #FAF5FF; color: #7C3AED; }
    .badge-direct   { background: #F0FDF4; color: #15803D; }
    .badge-regular  { background: #FFF7ED; color: #C2410C; }

    /* ── Alert ── */
    .alert-success { background:#F0FDF4; border:1px solid #BBF7D0; border-radius:10px; padding:12px 16px; color:#15803D; font-size:13px; }
    .alert-warn    { background:#FFFBEB; border:1px solid #FDE68A; border-radius:10px; padding:12px 16px; color:#92400E; font-size:13px; }
    .alert-info    { background:#EFF6FF; border:1px solid #BFDBFE; border-radius:10px; padding:12px 16px; color:#1E40AF; font-size:13px; }
    .alert-danger  { background:#FEF2F2; border:1px solid #FECACA; border-radius:10px; padding:12px 16px; color:#991B1B; font-size:13px; }

    /* ── Onboarding ── */
    .onboard-hero { text-align:center; padding:60px 20px; }
    .onboard-title { font-size:32px; font-weight:800; color:#0F172A; letter-spacing:-1px; line-height:1.2; margin-bottom:12px; }
    .onboard-sub { font-size:15px; color:#64748B; max-width:480px; margin:0 auto 40px; line-height:1.7; }
    .step-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; max-width:700px; margin:0 auto; }
    .step-card { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:16px; padding:24px; text-align:left; }
    .step-num { font-size:11px; font-weight:700; color:#6366F1; margin-bottom:8px; }
    .step-title { font-size:14px; font-weight:700; color:#0F172A; margin-bottom:6px; }
    .step-desc { font-size:12px; color:#64748B; line-height:1.6; }

    /* ── Footer ── */
    .footer-note { font-size:10px; color:#CBD5E1; text-align:center; margin-top:60px; padding:20px; border-top:1px solid #E2E8F0; }

    /* ── Timeline ── */
    .timeline-bar {
        display: flex; align-items: stretch; border-radius: 10px;
        overflow: hidden; height: 44px; margin: 12px 0;
    }
    .timeline-seg { display:flex; align-items:center; justify-content:center;
        font-size:10px; font-weight:700; color:#fff; padding:0 8px;
        white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
    }

    /* ── Comparison ── */
    .compare-card {
        background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px;
        padding: 18px; text-align: center;
    }
    .compare-card .fund-name { font-size: 12px; font-weight: 700; color: #0F172A;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 10px; }
    .compare-row { display:flex; justify-content:space-between; padding:5px 0;
        border-bottom:1px solid #F1F5F9; font-size:12px; }
    .compare-label { color:#64748B; } .compare-val { font-weight:600; color:#0F172A; }

    /* ── Score ring ── */
    .score-ring {
        width:100px; height:100px; border-radius:50%;
        display:flex; align-items:center; justify-content:center;
        font-size:28px; font-weight:800; color:#0F172A;
        margin:0 auto;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width:4px; height:4px; }
    ::-webkit-scrollbar-thumb { background:#CBD5E1; border-radius:4px; }

    /* ══ v6.0 Premium UI additions ══ */

    /* Root tokens */
    :root {
      --shadow-sm: 0 1px 2px rgba(10,15,30,0.04);
      --shadow:    0 2px 6px rgba(10,15,30,0.06);
      --shadow-md: 0 6px 20px rgba(10,15,30,0.09);
      --r: 12px; --r-sm: 8px;
    }

    /* Elevated card hover */
    .metric-card {
      transition: box-shadow 0.18s ease, transform 0.18s ease !important;
    }
    .metric-card:hover {
      box-shadow: 0 6px 20px rgba(10,15,30,0.09) !important;
      transform: translateY(-1px) !important;
    }

    /* Better tab styling */
    .stTabs [data-baseweb="tab"] { transition: background 0.12s, color 0.12s; }
    .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
      background: #F0F2F5 !important;
      color: #3D4A5C !important;
    }

    /* Premium sidebar button */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
      background: linear-gradient(135deg, #5B5FD6 0%, #7C3AED 100%) !important;
      border: none !important;
      box-shadow: 0 4px 14px rgba(91,95,214,0.35) !important;
      font-weight: 700 !important;
      letter-spacing: 0.2px;
    }

    /* Verdict badges */
    .verdict-strong  { background:#ECFDF5; color:#059669; border:1px solid #A7F3D0; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; }
    .verdict-average { background:#FFFBEB; color:#D97706; border:1px solid #FDE68A; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; }
    .verdict-weak    { background:#FEF2F2; color:#DC2626; border:1px solid #FECACA; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; }

    /* Risk pill */
    .risk-low    { display:inline-block; padding:2px 9px; border-radius:20px; font-size:10px; font-weight:700; background:#ECFDF5; color:#059669; }
    .risk-mod    { display:inline-block; padding:2px 9px; border-radius:20px; font-size:10px; font-weight:700; background:#FFFBEB; color:#D97706; }
    .risk-high   { display:inline-block; padding:2px 9px; border-radius:20px; font-size:10px; font-weight:700; background:#FEF2F2; color:#DC2626; }

    /* Dataframe upgrade */
    [data-testid="stDataFrame"] {
      border-radius: 10px !important;
      overflow: hidden !important;
      border: 1px solid #E2E8F0 !important;
      box-shadow: 0 1px 3px rgba(10,15,30,0.04) !important;
    }

    /* Sidebar divider */
    [data-testid="stSidebar"] hr {
      border-color: #E2E8F0 !important;
      margin: 16px 0 !important;
    }

    /* Download button */
    .stDownloadButton > button {
      background: #F7F8FA !important;
      border: 1px solid #E2E8F0 !important;
      border-radius: 8px !important;
      font-weight: 600 !important;
      color: #3D4A5C !important;
      transition: all 0.15s !important;
    }

    /* Pills period selector */
    [data-testid="stPills"] button {
      border-radius: 20px !important;
      font-weight: 600 !important;
      font-size: 12px !important;
    }
    [data-testid="stPills"] button[aria-selected="true"] {
      background: #0A0F1E !important;
      color: #fff !important;
    }

    /* Plotly */
    .js-plotly-plot .plotly .modebar { display:none !important; }
    </style>
    """, unsafe_allow_html=True)


def show_alert(message: str, alert_type: str = "info"):
    """Display an alert box with specified type."""
    st.markdown(f'<div class="alert-{alert_type}">{message}</div>', unsafe_allow_html=True)


def show_metric_card(label: str, value: str, subtext: str = ""):
    """Display a formatted metric card."""
    html = f'<div class="metric-card"><div class="card-label">{label}</div><div class="card-value">{value}</div>'
    if subtext:
        html += f'<div class="card-sub">{subtext}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def show_badge(text: str, badge_type: str = "equity"):
    """Display a badge."""
    st.markdown(f'<span class="badge badge-{badge_type}">{text}</span>', unsafe_allow_html=True)
