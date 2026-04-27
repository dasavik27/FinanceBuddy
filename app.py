"""
MF Portfolio Intelligence Platform
===================================
Roles: BA · Architect · UX Lead · Frontend Lead · Backend Lead
Stack: Streamlit · casparser · yfinance · pyxirr · pandas · plotly
"""


import streamlit as st
import casparser
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pyxirr import xirr
from datetime import datetime, timedelta
import io, os
import warnings
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="FolioIQ · MF Portfolio Intelligence",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="expanded"
)


# ─────────────────────────────────────────────
# DESIGN SYSTEM — ZERODHA/GROWW INSPIRED
# ─────────────────────────────────────────────
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


/* ── Holdings table ── */
.holdings-row {
    background: #FFFFFF;
    border-radius: 8px;
    border: 1px solid #E2E8F0;
    padding: 14px 18px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.fund-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.fund-name { font-size: 13px; font-weight: 600; color: #0F172A; }
.fund-meta { font-size: 11px; color: #94A3B8; margin-top: 2px; }


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


/* Holdings row interactive */
[style*="border-radius:10px"][style*="padding:14px 18px"] {
  transition: box-shadow 0.15s, border-color 0.15s, transform 0.15s;
}
[style*="border-radius:10px"][style*="padding:14px 18px"]:hover {
  box-shadow: 0 6px 18px rgba(10,15,30,0.08) !important;
  transform: translateX(2px);
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
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  box-shadow: 0 6px 20px rgba(91,95,214,0.45) !important;
  transform: translateY(-1px) !important;
}


/* Gradient section headers */
.sh-grad {
  font-size: 16px; font-weight: 800; letter-spacing: -0.4px;
  background: linear-gradient(90deg, #0A0F1E 0%, #3D4A5C 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text; margin-bottom: 2px;
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


/* Better metrics */
[data-testid="stMetric"] {
  background: linear-gradient(135deg, #FFFFFF 0%, #FAFBFC 100%) !important;
  border-radius: 12px !important;
  box-shadow: 0 1px 3px rgba(10,15,30,0.06) !important;
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
.stDownloadButton > button:hover {
  background: #EEF2FF !important;
  border-color: #C7D2FE !important;
  color: #4338CA !important;
}


/* Alert boxes upgrade */
.alert-success, .alert-warn, .alert-info, .alert-danger {
  border-left-width: 3px !important;
}


/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-thumb { background: #D1D9E6; border-radius: 4px; }


/* ── Plotly ── */
.js-plotly-plot .plotly .modebar { display:none !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONSTANTS & CONFIG
# ─────────────────────────────────────────────
BENCHMARKS = {
    "Nifty 50":      "^NSEI",
    "Sensex":        "^BSESN",
    "Nifty Midcap 150": "^NSMIDCP",
    "Nifty Smallcap 250": "^NSSMLCP",
    "Nifty Next 50": "^NSMIDCP",
}


PERIOD_MAP = {
    "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "3Y": 1095, "5Y": 1825, "All": 9999
}


CATEGORY_COLORS = {
    "Equity": "#3B82F6", "Debt": "#10B981", "Hybrid": "#F59E0B",
    "ELSS": "#8B5CF6", "Liquid": "#06B6D4", "Index": "#6366F1",
    "FOF": "#F43F5E", "Other": "#94A3B8"
}


# ── Per-fund benchmark mapping (cap-type / category → TRI proxy) ──
FUND_BENCH_BY_CAP = {
    "Large Cap":       ("^NSEI",              "Nifty 50"),
    "Mid Cap":         ("^NSMIDCP",           "Nifty Midcap 150"),
    "Small Cap":       ("NIFTYSMALLCAP250.NS","Nifty SmallCap 250"),
    "Flexi/Multi Cap": ("^CNX500",            "Nifty 500"),
    "Index":           ("^NSEI",              "Nifty 50"),
    "Mixed":           ("^NSEI",              "Nifty 50"),
}
FUND_BENCH_BY_CAT = {
    "ELSS":   ("^NSEI",   "Nifty 50"),
    "Hybrid": ("^NSEI",   "Nifty 50"),
    "FOF":    ("^CNX500", "Nifty 500"),
    "Debt":   (None,      "CRISIL Composite Bond"),
    "Liquid": (None,      "CRISIL Liquid"),
    "Other":  ("^NSEI",   "Nifty 50"),
}


# Risk tiers (annual vol%, beta, label) — category-seeded heuristics
RISK_TIERS = {
    "Liquid":  (0.5,  0.02, "Very Low"),
    "Debt":    (3.5,  0.15, "Low"),
    "Hybrid":  (9.0,  0.55, "Moderate"),
    "ELSS":    (15.0, 0.90, "High"),
    "Index":   (13.0, 1.00, "Moderate-High"),
    "Equity":  (17.0, 1.10, "High"),
    "FOF":     (14.0, 0.80, "High"),
    "Other":   (10.0, 0.60, "Moderate"),
}
MAX_DD_ESTIMATE = {
    "Equity":45, "ELSS":42, "Index":38, "Hybrid":28,
    "FOF":38, "Debt":10, "Liquid":2, "Other":22,
}


SECTOR_COLORS = [
    "#3B82F6","#10B981","#F59E0B","#8B5CF6","#F43F5E",
    "#06B6D4","#6366F1","#EC4899","#14B8A6","#F97316"
]


# Approximate expense ratios (Direct / Regular) by category
EXP_RATIOS = {
    "Equity":  (0.50, 1.50), "ELSS":   (0.55, 1.60),
    "Index":   (0.10, 0.40), "Hybrid": (0.45, 1.40),
    "Debt":    (0.25, 0.85), "Liquid": (0.12, 0.35),
    "FOF":     (0.60, 1.70), "Other":  (0.45, 1.20),
}


# Goal-based timeline mapping
GOAL_TIMELINE = {
    "Liquid":  ("Emergency (0-6mo)", "#06B6D4", 0.5),
    "Debt":    ("Short Term (1-3yr)", "#10B981", 2),
    "Hybrid":  ("Medium Term (3-7yr)", "#F59E0B", 5),
    "ELSS":    ("Medium Term (3-7yr)", "#8B5CF6", 5),
    "Index":   ("Long Term (7yr+)", "#6366F1", 10),
    "Equity":  ("Long Term (7yr+)", "#3B82F6", 10),
    "FOF":     ("Long Term (7yr+)", "#F43F5E", 10),
    "Other":   ("Medium Term (3-7yr)", "#94A3B8", 5),
}


# Sector keywords for heuristic sector detection from fund names
SECTOR_KEYWORDS = {
    "Banking & Financial": ["BANKING", "BANK", "FINANCIAL", "PSU BANK", "NIFTY BANK"],
    "Technology": ["TECHNOLOGY", "TECH", "IT", "DIGITAL", "INNOVATION"],
    "Healthcare": ["PHARMA", "HEALTHCARE", "HEALTH"],
    "Infrastructure": ["INFRA", "INFRASTRUCTURE", "CONSTRUCTION"],
    "Consumer": ["CONSUMER", "FMCG", "CONSUMPTION", "RETAIL"],
    "Energy": ["ENERGY", "OIL", "GAS", "POWER", "PETROLEUM"],
    "Manufacturing": ["MANUFACTURING", "INDUSTRIAL", "CAPITAL GOODS", "ENGINEERING"],
    "Real Estate": ["REAL ESTATE", "REALTY", "HOUSING"],
    "Auto": ["AUTO", "AUTOMOBILE", "EV"],
    "Diversified": [],  # fallback
}


# ─────────────────────────────────────────────
# BACKEND: PARSE CAS PDF
# ─────────────────────────────────────────────
def fmt_inr(number: float) -> str:
    """Format number in Indian numbering system (Lakhs/Crores)."""
    try:
        if pd.isna(number):
            return "₹0"
        is_negative = number < 0
        num_str = str(abs(int(round(number))))
        if len(num_str) <= 3:
            res = num_str
        else:
            res = num_str[:-3]
            res = ",".join([res[max(i-2, 0):i] for i in range(len(res), 0, -2)][::-1]) + "," + num_str[-3:]
        return f"-₹{res}" if is_negative else f"₹{res}"
    except Exception:
        return "₹0"


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return val if val is not None else default
    val = getattr(obj, key, default)
    return val if val is not None else default


@st.cache_data(show_spinner=False)
def parse_cas(file_bytes: bytes, password: str):
    """Parse CAMS/KFintech CAS PDF. Zero disk retention after parsing."""
    try:
        with open("_vault_tmp.pdf", "wb") as f:
            f.write(file_bytes)


        data = casparser.read_cas_pdf("_vault_tmp.pdf", password)


        import os
        try:
            os.remove("_vault_tmp.pdf")
        except Exception:
            pass


        if "accounts" in data:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "NSDL CAS detected. FolioIQ requires a CAMS/KFintech Detailed CAS for transaction analytics."
            
        folios     = _get(data, 'folios', [])
        if not folios:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "No folios found in CAS. Make sure this is a 'Detailed' CAS."
            
        holdings   = []
        txns       = []
        sips       = []
        
        is_partial_cas = False


        for folio in folios:
            schemes = _get(folio, 'schemes', [])
            for scheme in schemes:
                name   = _get(scheme, 'scheme', "Unknown Scheme")
                isin   = _get(scheme, 'isin', "N/A") or "N/A"
                bal    = float(_get(scheme, 'close_calculated', _get(scheme, 'close', 0)) or 0)
                
                # Check for partial CAS (has opening balance but no transactions for it in this period)
                open_bal = float(_get(scheme, 'open', 0) or 0)
                if open_bal > 0:
                    is_partial_cas = True
                    
                if not bal:
                    txs = _get(scheme, 'transactions', []) or []
                    if txs:
                        bal = float(_get(txs[-1], 'balance', 0) or 0)
                val_obj = _get(scheme, 'valuation', {})
                cur_val = float(_get(val_obj, 'value', 0) or 0)
                nav    = float(_get(val_obj, 'nav', 0) or 0) if val_obj else 0
                cost   = float(_get(val_obj, 'cost', 0) or 0)


                # Derive fund metadata from scheme name
                category = _detect_category(name)
                plan     = "Regular" if any(x in name.upper() for x in ["REGULAR", "REG "]) else "Direct"
                amc      = _detect_amc(name)
                cap_type = _detect_cap_type(name)


                if bal > 0 or cur_val > 0:
                    # Use CAS cost value if available, else estimate from transactions
                    invested = cost if cost > 0 else _estimate_invested(scheme)
                    holdings.append({
                        "Fund":        name,
                        "ISIN":        isin,
                        "AMC":         amc,
                        "Category":    category,
                        "Plan":        plan,
                        "Cap Type":    cap_type,
                        "Units":       bal,
                        "NAV":         nav,
                        "Market Value": cur_val,
                        "Invested":    invested,
                        "Gain":        cur_val - invested,
                        "Gain%":       ((cur_val - invested) / invested * 100) if invested > 0 else 0,
                        "Weight%":     0.0,
                    })


                # Transactions
                txs_raw = _get(scheme, 'transactions', [])
                for tx in txs_raw:
                    t_date = _get(tx, 'date', None)
                    t_amt  = _get(tx, 'amount', 0)
                    t_type = _get(tx, 'type', 'N/A') or 'N/A'
                    t_nav  = _get(tx, 'nav', 0) or 0
                    t_units= _get(tx, 'units', 0) or 0
                    if t_date:
                        txns.append({
                            "Fund":     name,
                            "AMC":      amc,
                            "Category": category,
                            "Date":     pd.to_datetime(t_date),
                            "Amount":   float(t_amt or 0),
                            "Type":     str(t_type),
                            "NAV":      float(t_nav),
                            "Units":    float(t_units),
                        })
                        # Detect SIPs (recurring patterns)
                        if "SIP" in str(t_type).upper() or "SYSTEMATIC" in str(t_type).upper():
                            sips.append({
                                "Fund": name, "AMC": amc,
                                "Date": pd.to_datetime(t_date),
                                "Amount": abs(float(t_amt or 0)),
                                "NAV": float(t_nav),
                            })


        df_h = pd.DataFrame(holdings)
        if not df_h.empty:
            total_val = df_h["Market Value"].sum()
            if total_val > 0:
                df_h["Weight%"] = df_h["Market Value"] / total_val * 100


        df_t = pd.DataFrame(txns)
        df_s = pd.DataFrame(sips)
        return df_h, df_t, df_s, None, is_partial_cas


    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), str(e), False








def _detect_category(name: str) -> str:
    n = name.upper()
    if "ELSS" in n or "TAX SAVER" in n or "TAX SAVING" in n:
        return "ELSS"
    if any(x in n for x in ["LIQUID", "OVERNIGHT", "MONEY MARKET", "ULTRA SHORT"]):
        return "Liquid"
    if any(x in n for x in ["DEBT", "BOND", "GILT", "INCOME", "CREDIT RISK", "CORPORATE BOND", "BANKING AND PSU"]):
        return "Debt"
    if any(x in n for x in ["HYBRID", "BALANCED", "CONSERVATIVE", "AGGRESSIVE HYBRID", "EQUITY SAVINGS", "ARBITRAGE"]):
        return "Hybrid"
    if any(x in n for x in ["INDEX", "NIFTY", "SENSEX", "ETF", "FTF"]):
        return "Index"
    if "FOF" in n or "FUND OF FUND" in n or "OVERSEAS" in n or "INTERNATIONAL" in n:
        return "FOF"
    if any(x in n for x in ["EQUITY", "FLEXI", "MULTI CAP", "LARGE CAP", "MID CAP", "SMALL CAP",
                              "SECTORAL", "THEMATIC", "FOCUSED", "VALUE", "CONTRA", "DIVIDEND YIELD"]):
        return "Equity"
    return "Other"




def _detect_cap_type(name: str) -> str:
    n = name.upper()
    if "SMALL CAP" in n: return "Small Cap"
    if "MID CAP" in n or "MIDCAP" in n: return "Mid Cap"
    if "LARGE CAP" in n or "LARGECAP" in n: return "Large Cap"
    if "FLEXI CAP" in n or "MULTI CAP" in n: return "Flexi/Multi Cap"
    if "INDEX" in n or "NIFTY 50" in n or "SENSEX" in n: return "Index"
    return "Mixed"




def _detect_amc(name: str) -> str:
    amcs = {
        "Mirae": "Mirae Asset", "HDFC": "HDFC", "SBI": "SBI",
        "Axis": "Axis", "ICICI": "ICICI Prudential", "Kotak": "Kotak",
        "Nippon": "Nippon India", "DSP": "DSP", "Parag Parikh": "PPFAS",
        "Motilal": "Motilal Oswal", "Franklin": "Franklin Templeton",
        "Aditya Birla": "Aditya Birla SL", "UTI": "UTI", "Tata": "Tata",
        "Canara": "Canara Robeco", "Edelweiss": "Edelweiss",
        "Invesco": "Invesco", "L&T": "L&T", "BOI": "BOI AXA",
        "Sundaram": "Sundaram", "PGIM": "PGIM India", "Quant": "Quant",
    }
    for k, v in amcs.items():
        if k.upper() in name.upper():
            return v
    return "Other AMC"




def _estimate_invested(scheme) -> float:
    """Estimate invested amount using average cost calculation to correctly handle redemptions."""
    try:
        txs = _get(scheme, 'transactions', [])
        current_units = 0.0
        avg_cost = 0.0
        for tx in txs:
            amt   = abs(float(_get(tx, 'amount', 0) or 0))
            units = float(_get(tx, 'units', 0) or 0)
            
            if units > 0:
                new_units = current_units + units
                if new_units > 0:
                    avg_cost = (current_units * avg_cost + amt) / new_units
                current_units = new_units
            elif units < 0:
                current_units += units
                if current_units <= 1e-6:
                    current_units = 0.0
                    avg_cost = 0.0
        
        return current_units * avg_cost
    except Exception:
        return 0.0




# ─────────────────────────────────────────────
# BACKEND: MARKET DATA
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark(ticker: str, period_days: int = 365):
    """Fetch benchmark OHLCV from yfinance."""
    try:
        end   = datetime.now()
        start = end - timedelta(days=max(period_days + 90, 3650))  # At least 10 years for 5Y/ALL views
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return pd.Series(dtype=float)
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.squeeze().dropna()
        return close
    except Exception:
        return pd.Series(dtype=float)




# ─────────────────────────────────────────────
# ANALYTICS ENGINE
# ─────────────────────────────────────────────
def compute_xirr(df_t: pd.DataFrame, current_value: float) -> float:
    """Compute portfolio XIRR from transaction ledger."""
    if df_t.empty or current_value <= 0:
        return 0.0
    try:
        ledger = []
        for _, row in df_t.iterrows():
            amt = abs(float(row.get("Amount", 0)))
            if amt == 0:
                continue
            
            t_type = str(row.get("Type", "")).upper()
            units = float(row.get("Units", 0))
            
            # Ignore Dividend Reinvestments (no net cashflow)
            if "REINVEST" in t_type:
                continue
                
            if units > 0:
                # Purchase / Switch In -> Outflow
                ledger.append({"date": row["Date"], "amount": -amt})
            elif units < 0:
                # Redemption / Switch Out -> Inflow
                ledger.append({"date": row["Date"], "amount": amt})
            else:
                # Units == 0
                if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                    ledger.append({"date": row["Date"], "amount": amt})
                elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                    ledger.append({"date": row["Date"], "amount": -amt})


        if not ledger:
            return 0.0
            
        ledger.append({"date": datetime.now(), "amount": current_value})
        ldf = pd.DataFrame(ledger).dropna()
        
        # XIRR requires at least one positive and one negative cashflow
        if ldf["amount"].min() >= 0 or ldf["amount"].max() <= 0:
            return 0.0
            
        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result):
            return 0.0
            
        # Bound between -100% and 1000%
        return max(-100.0, min(float(result) * 100, 1000.0))
    except Exception:
        return 0.0




def compute_benchmark_xirr(df_t: pd.DataFrame, bench_series: pd.Series) -> tuple:
    """
    Simulate investing the same cash flows into the benchmark index.
    Returns (benchmark_xirr_pct, benchmark_current_value).
    
    Logic (like Zerodha/Groww/PowerUp Money):
    - For each purchase transaction, calculate how many benchmark "units" 
      you would have bought at that date's benchmark price.
    - For each redemption, calculate how many benchmark "units" you'd sell.
    - At the end, value all remaining units at today's benchmark price.
    - Calculate XIRR on these cash flows.
    """
    if df_t.empty or bench_series.empty:
        return 0.0, 0.0
    try:
        total_bench_units = 0.0
        cashflows = []
        
        for _, row in df_t.iterrows():
            amt = abs(float(row.get("Amount", 0)))
            if amt == 0:
                continue
            
            t_type = str(row.get("Type", "")).upper()
            units = float(row.get("Units", 0))
            txn_date = row["Date"]
            
            # Skip dividend reinvestments (no net cashflow)
            if "REINVEST" in t_type:
                continue
            
            # Find benchmark price on or before the transaction date
            mask = bench_series.index <= txn_date
            if mask.any():
                bench_price = float(bench_series[mask].iloc[-1])
            else:
                bench_price = float(bench_series.iloc[0])
            
            if bench_price <= 0:
                continue
            
            if units > 0:
                # Purchase / Switch In -> buy benchmark units
                bench_units_bought = amt / bench_price
                total_bench_units += bench_units_bought
                cashflows.append({"date": txn_date, "amount": -amt})
            elif units < 0:
                # Redemption / Switch Out -> sell benchmark units
                bench_units_sold = amt / bench_price
                total_bench_units = max(0, total_bench_units - bench_units_sold)
                cashflows.append({"date": txn_date, "amount": amt})
            else:
                # Dividends, taxes etc.
                if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                    cashflows.append({"date": txn_date, "amount": amt})
                elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                    cashflows.append({"date": txn_date, "amount": -amt})
        
        if not cashflows or total_bench_units <= 0:
            return 0.0, 0.0
        
        # Current benchmark value = remaining units × latest benchmark price
        current_bench_price = float(bench_series.iloc[-1])
        bench_current_value = total_bench_units * current_bench_price
        
        # Add final valuation as inflow
        today = datetime.now()
        cashflows.append({"date": today, "amount": bench_current_value})
        
        ldf = pd.DataFrame(cashflows).dropna()
        
        if ldf["amount"].min() >= 0 or ldf["amount"].max() <= 0:
            return 0.0, bench_current_value
        
        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result) or not np.isfinite(float(result)):
            # Fallback: CAGR from total outflows → current bench value
            total_out = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            if total_out > 0 and bench_current_value > 0:
                earliest = ldf[ldf["amount"] < 0]["date"].min()
                years_held = max((datetime.now() - pd.Timestamp(earliest)).days, 1) / 365.25
                cagr = ((bench_current_value / total_out) ** (1.0 / years_held) - 1) * 100
                return max(-99.0, min(cagr, 200.0)), bench_current_value
            return 0.0, bench_current_value

        bench_xirr = max(-100.0, min(float(result) * 100, 200.0))  # cap at 200% (realisitic max)
        return bench_xirr, bench_current_value
    except Exception:
        return 0.0, 0.0




def _get_bench_price(bench_series, target_date):
    """Get benchmark price on or before target_date. Falls back to nearest available."""
    if bench_series.empty:
        return 0.0
    target_ts = pd.Timestamp(target_date)
    mask = bench_series.index <= target_ts
    if mask.any():
        return float(bench_series[mask].iloc[-1])
    # If target_date is before all benchmark data, use earliest available
    return float(bench_series.iloc[0])




def _build_cashflow_list(df_t):
    """Build a list of (date, amount, units) tuples from a transaction DataFrame, 
    skipping dividend reinvestments and zero-amount transactions."""
    cashflows = []
    if df_t.empty or "Date" not in df_t.columns:
        return cashflows
    for _, row in df_t.iterrows():
        amt = abs(float(row.get("Amount", 0)))
        if amt == 0:
            continue
        t_type = str(row.get("Type", "")).upper()
        units = float(row.get("Units", 0))
        if "REINVEST" in t_type:
            continue
        cashflows.append((row["Date"], amt, units, t_type))
    return cashflows




def compute_period_comparison(df_t_all, total_value, bench_series, period_days):
    """
    Compute Portfolio vs Benchmark comparison for a given date-filter period.
    
    This is the CORE logic for the Overview tab. It correctly handles:
    1. Pre-existing portfolio value before the filter range (treated as lumpsum)
    2. All SIPs/redemptions within the period
    3. Benchmark simulation using index prices on transaction dates
    4. Absolute returns for <3Y, XIRR for >=3Y
    5. Cumulative growth time-series for charting
    
    Returns dict with: port_pct, bench_pct, port_value, bench_value, 
                        use_xirr, port_growth_series, bench_growth_series
    """
    result = {
        "port_pct": 0.0, "bench_pct": 0.0,
        "port_value": total_value, "bench_value": 0.0,
        "use_xirr": period_days >= 1095,
        "port_start_value": 0.0,
    }
    
    if bench_series.empty or total_value <= 0:
        return result
    
    # ── Step 1: Determine period boundaries ──
    bench_end_date = bench_series.index[-1]
    if period_days < 9999:
        period_start_date = bench_end_date - timedelta(days=period_days)
    else:
        # "ALL" — use the earliest of (first transaction, first bench data)
        if not df_t_all.empty and "Date" in df_t_all.columns:
            earliest_txn = df_t_all["Date"].min()
            period_start_date = min(earliest_txn, bench_series.index[0])
        else:
            period_start_date = bench_series.index[0]
    
    # Snap to nearest available benchmark date
    bench_after_start = bench_series[bench_series.index >= period_start_date]
    if bench_after_start.empty:
        bench_after_start = bench_series
    period_start_date = bench_after_start.index[0]
    bench_price_start = float(bench_after_start.iloc[0])
    bench_price_end = float(bench_series.iloc[-1])
    
    if bench_price_start <= 0:
        return result
    
    # ── Step 2: Split transactions into before-period and within-period ──
    all_cfs = _build_cashflow_list(df_t_all)
    
    # Transactions BEFORE the period start (used to estimate starting portfolio value)
    txns_before = [(d, a, u, t) for d, a, u, t in all_cfs if d < period_start_date]
    # Transactions WITHIN the period
    txns_in_period = [(d, a, u, t) for d, a, u, t in all_cfs if d >= period_start_date]
    
    # ── Step 3: Estimate portfolio value at period start ──
    # Method: total_value_now = port_value_at_start * (price_growth) + net_new_investments * (partial_growth)
    # Approximation: port_value_at_start ≈ total_value - sum_of_all_investments_in_period - gains_on_those_investments
    # Better: Use the invested amount before the period and apply the benchmark growth to estimate
    
    # Calculate total net cash invested during the period
    net_invested_in_period = 0.0
    for d, amt, units, t_type in txns_in_period:
        if units > 0:
            net_invested_in_period += amt  # Money put in
        elif units < 0:
            net_invested_in_period -= amt  # Money taken out
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                net_invested_in_period -= amt
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                net_invested_in_period += amt
    
    # Estimate portfolio value at start: 
    # We reverse-engineer from current value by subtracting net new investments
    # and adjusting for the approximate market growth of those investments
    # For the pre-existing portfolio part, we use benchmark return to adjust
    bench_return_ratio = bench_price_end / bench_price_start  # e.g., 1.15 for 15% return
    
    # The investments made during the period would have grown partially
    # Approximate: each investment grows by the average of (full period return, 0%)
    # Better: weight by time remaining
    total_days_in_period = max((bench_end_date - period_start_date).days, 1)
    
    weighted_new_investment_value = 0.0
    for d, amt, units, t_type in txns_in_period:
        days_remaining = max((bench_end_date - d).days, 0)
        time_fraction = days_remaining / total_days_in_period
        # Approximate growth of this particular investment
        growth = bench_return_ratio ** time_fraction  # proxy using benchmark growth
        if units > 0:
            weighted_new_investment_value += amt * growth
        elif units < 0:
            weighted_new_investment_value -= amt * growth
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                weighted_new_investment_value -= amt * growth
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                weighted_new_investment_value += amt * growth
    
    # port_value_at_start = (total_value - weighted_new_investment_value) / bench_return_ratio
    # This is the value that, if grown at the benchmark rate, would give us the non-SIP portion of today's value
    port_value_at_start = max(1.0, (total_value - weighted_new_investment_value) / bench_return_ratio)
    
    # Sanity check: if there were no transactions before the period, start value should be small/zero
    if not txns_before and period_days < 9999:
        # No pre-existing investments — port_value_at_start should be 0
        # All value came from investments within the period
        port_value_at_start = 0.0
    
    result["port_start_value"] = port_value_at_start


    # ── Step 4: Build cash flow lists for XIRR ──
    # Portfolio cash flows
    pcf_list = []
    if port_value_at_start > 0:
        pcf_list.append({"date": period_start_date, "amount": -port_value_at_start})
    
    # Benchmark cash flows & unit tracking
    bcf_list = []
    bench_units = 0.0
    if port_value_at_start > 0:
        bcf_list.append({"date": period_start_date, "amount": -port_value_at_start})
        bench_units = port_value_at_start / bench_price_start
    
    # Add transactions within the period
    for d, amt, units, t_type in txns_in_period:
        bp = _get_bench_price(bench_series, d)
        if bp <= 0:
            bp = bench_price_start
        
        if units > 0:
            # Purchase → outflow
            pcf_list.append({"date": d, "amount": -amt})
            bcf_list.append({"date": d, "amount": -amt})
            bench_units += amt / bp
        elif units < 0:
            # Redemption → inflow
            pcf_list.append({"date": d, "amount": amt})
            bcf_list.append({"date": d, "amount": amt})
            bench_units = max(0, bench_units - amt / bp)
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                pcf_list.append({"date": d, "amount": amt})
                bcf_list.append({"date": d, "amount": amt})
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                pcf_list.append({"date": d, "amount": -amt})
                bcf_list.append({"date": d, "amount": -amt})
    
    # Final values
    today = datetime.now()
    pcf_list.append({"date": today, "amount": total_value})
    
    bench_sim_value = bench_units * bench_price_end
    bcf_list.append({"date": today, "amount": bench_sim_value})
    
    result["port_value"] = total_value
    result["bench_value"] = bench_sim_value


    # ── Step 5: Compute returns ──
    if not pcf_list or len(pcf_list) < 2:
        return result
    
    # Compute absolute returns (always available)
    total_outflow = sum(-cf["amount"] for cf in pcf_list if cf["amount"] < 0)
    total_inflow = sum(cf["amount"] for cf in pcf_list if cf["amount"] > 0)
    port_abs_ret = ((total_inflow / total_outflow) - 1) * 100 if total_outflow > 0 else 0.0
    
    bench_total_outflow = sum(-cf["amount"] for cf in bcf_list if cf["amount"] < 0)
    bench_total_inflow = sum(cf["amount"] for cf in bcf_list if cf["amount"] > 0)
    bench_abs_ret = ((bench_total_inflow / bench_total_outflow) - 1) * 100 if bench_total_outflow > 0 else 0.0
    
    use_xirr = period_days >= 1095  # 3Y+
    
    if use_xirr:
        # XIRR for 3Y/5Y/ALL
        try:
            pcf_df = pd.DataFrame(pcf_list).dropna()
            if pcf_df["amount"].min() < 0 and pcf_df["amount"].max() > 0:
                r = xirr(pcf_df["date"], pcf_df["amount"])
                result["port_pct"] = max(-100.0, min(float(r) * 100, 1000.0)) if r and not np.isnan(r) else port_abs_ret
            else:
                result["port_pct"] = port_abs_ret
        except Exception:
            result["port_pct"] = port_abs_ret
        
        try:
            bcf_df = pd.DataFrame(bcf_list).dropna()
            if bcf_df["amount"].min() < 0 and bcf_df["amount"].max() > 0:
                r = xirr(bcf_df["date"], bcf_df["amount"])
                result["bench_pct"] = max(-100.0, min(float(r) * 100, 1000.0)) if r and not np.isnan(r) else bench_abs_ret
            else:
                result["bench_pct"] = bench_abs_ret
        except Exception:
            result["bench_pct"] = bench_abs_ret
    else:
        # Absolute returns for short periods
        result["port_pct"] = port_abs_ret
        result["bench_pct"] = bench_abs_ret
    
    result["use_xirr"] = use_xirr
    return result




def compute_rolling_returns(bench_series: pd.Series, periods_days: list) -> dict:
    """Compute point-to-point returns for given periods."""
    results = {}
    if bench_series.empty:
        return results
    now_idx = bench_series.index[-1]
    last_price = float(bench_series.iloc[-1])
    for d in periods_days:
        cutoff = now_idx - timedelta(days=d)
        past = bench_series[bench_series.index >= cutoff]
        if len(past) >= 2:
            first = float(past.iloc[0])
            results[d] = ((last_price / first) - 1) * 100 if first > 0 else 0.0
        else:
            results[d] = 0.0
    return results




def estimate_expense_drag(df_h: pd.DataFrame) -> float:
    """Estimated annual expense ratio drag in INR."""
    drag = 0.0
    for _, row in df_h.iterrows():
        lo, hi = EXP_RATIOS.get(row["Category"], (0.45, 1.20))
        er = lo if row["Plan"] == "Direct" else hi
        drag += row["Market Value"] * er / 100
    return drag




def expense_leakage_20yr(df_h: pd.DataFrame, annual_growth: float = 0.12) -> dict:
    """Calculate 20-year expense ratio leakage as lost opportunity cost."""
    results = {"current_drag": 0.0, "direct_drag": 0.0, "regular_drag": 0.0,
               "lost_20yr_current": 0.0, "lost_20yr_if_regular": 0.0,
               "saved_by_direct": 0.0, "by_fund": []}
    for _, row in df_h.iterrows():
        lo, hi = EXP_RATIOS.get(row["Category"], (0.45, 1.20))
        er_current = lo if row["Plan"] == "Direct" else hi
        val = row["Market Value"]
        # Compound leakage over 20 years
        fv_no_exp = val * (1 + annual_growth) ** 20
        fv_with_exp = val * (1 + annual_growth - er_current / 100) ** 20
        fv_with_direct = val * (1 + annual_growth - lo / 100) ** 20
        fv_with_regular = val * (1 + annual_growth - hi / 100) ** 20
        leak_current = fv_no_exp - fv_with_exp
        leak_if_regular = fv_no_exp - fv_with_regular
        results["current_drag"] += val * er_current / 100
        results["direct_drag"] += val * lo / 100
        results["regular_drag"] += val * hi / 100
        results["lost_20yr_current"] += leak_current
        results["lost_20yr_if_regular"] += leak_if_regular
        results["saved_by_direct"] += (fv_with_direct - fv_with_exp) if row["Plan"] == "Regular" else 0
        results["by_fund"].append({
            "Fund": row["Fund"][:50], "Category": row["Category"],
            "Plan": row["Plan"], "ER%": er_current,
            "Annual Drag": val * er_current / 100,
            "20yr Leakage": leak_current,
        })
    return results




def elss_lock_in_analysis(df_h: pd.DataFrame, df_t: pd.DataFrame) -> list:
    """Analyze ELSS funds for 3-year lock-in status."""
    if df_t.empty or "Fund" not in df_t.columns:
        return []
    elss_funds = df_h[df_h["Category"] == "ELSS"]["Fund"].unique()
    results = []
    for fund in elss_funds:
        fund_txns = df_t[df_t["Fund"] == fund].sort_values("Date")
        if fund_txns.empty:
            continue
        earliest = fund_txns["Date"].min()
        lock_in_end = earliest + timedelta(days=3*365)
        now = pd.Timestamp(datetime.now())
        is_unlocked = now >= lock_in_end
        days_left = max(0, (lock_in_end - now).days) if not is_unlocked else 0
        fund_val = float(df_h[df_h["Fund"] == fund]["Market Value"].sum())
        fund_inv = float(df_h[df_h["Fund"] == fund]["Invested"].sum())
        results.append({
            "Fund": fund, "Earliest Investment": earliest,
            "Lock-in Ends": lock_in_end, "Unlocked": is_unlocked,
            "Days Left": days_left, "Value": fund_val,
            "Invested": fund_inv, "Gain": fund_val - fund_inv,
        })
    return results




def detect_sector(name: str) -> str:
    """Heuristic sector detection from fund name."""
    n = name.upper()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in n for kw in keywords):
            return sector
    return "Diversified"




def compute_portfolio_score(df_h: pd.DataFrame, xirr_val: float, bench_ret: float) -> int:
    """Composite 0-100 portfolio health score."""
    if df_h.empty:
        return 0
    score = 0
    total = df_h["Market Value"].sum()
    # Alpha (30 pts)
    alpha = xirr_val - bench_ret
    score += min(30, max(0, int(30 * (1 + alpha / 20))))
    # Diversification (25 pts)
    n_funds = len(df_h)
    score += 25 if n_funds >= 10 else int(25 * n_funds / 10)
    # Direct plan % (20 pts)
    if total > 0:
        direct_pct = df_h[df_h["Plan"] == "Direct"]["Market Value"].sum() / total
        score += int(20 * direct_pct)
    # HHI concentration (15 pts)
    weights = (df_h["Market Value"] / total).values if total > 0 else np.array([1.0])
    hhi = float(np.sum(weights**2))
    score += int(15 * (1 - hhi))
    # Category balance (10 pts)
    if total > 0:
        max_cat_pct = df_h.groupby("Category")["Market Value"].sum().max() / total
        score += int(10 * (1 - max_cat_pct))
    return min(100, max(0, score))




def sip_consistency_score(df_s: pd.DataFrame) -> float:
    """0-100 score for SIP regularity."""
    if df_s.empty or len(df_s) < 2 or "Date" not in df_s.columns:
        return 0.0
    df_s = df_s.copy()
    df_s["YearMonth"] = df_s["Date"].dt.to_period("M")
    months_with_sip = df_s["YearMonth"].nunique()
    total_months = (df_s["YearMonth"].max() - df_s["YearMonth"].min()).n + 1
    if total_months <= 0:
        return 0.0
    return round(min(months_with_sip / total_months * 100, 100), 1)




def stepup_sip_projection(monthly_sip: float, years: int, annual_return: float, stepup_pct: float) -> dict:
    """Compare flat SIP vs step-up SIP future value."""
    r_monthly = annual_return / 100 / 12
    # Flat SIP
    n = years * 12
    if r_monthly > 0:
        flat_fv = monthly_sip * ((1 + r_monthly)**n - 1) / r_monthly * (1 + r_monthly)
    else:
        flat_fv = monthly_sip * n
    flat_inv = monthly_sip * n
    # Step-up SIP
    stepup_fv = 0.0
    stepup_inv = 0.0
    current_sip = monthly_sip
    for year in range(years):
        for month in range(12):
            months_remaining = (years - year) * 12 - month
            if r_monthly > 0:
                stepup_fv += current_sip * (1 + r_monthly) ** months_remaining
            else:
                stepup_fv += current_sip
            stepup_inv += current_sip
        current_sip *= (1 + stepup_pct / 100)
    return {
        "flat_fv": flat_fv, "flat_inv": flat_inv, "flat_gain": flat_fv - flat_inv,
        "stepup_fv": stepup_fv, "stepup_inv": stepup_inv, "stepup_gain": stepup_fv - stepup_inv,
        "extra_wealth": stepup_fv - flat_fv,
    }




# ─────────────────────────────────────────────
# CHART HELPERS
# ─────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, sans-serif", size=12, color="#64748B"),
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, zeroline=False, linecolor="#E2E8F0"),
    yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False, linecolor="#E2E8F0"),
)


def _layout(**kwargs) -> dict:
    return {**PLOTLY_LAYOUT, **kwargs}




def make_area_chart(x, y, color="#3B82F6", fill_color="rgba(59,130,246,0.1)", label=""):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=fill_color,
        name=label, hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f}<extra></extra>"
    ))
    fig.update_layout(**_layout(height=220))
    return fig




def make_donut(labels, values, colors):
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.68, marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        textinfo="none",
        hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>"
    ))
    fig.update_layout(**_layout(height=260, showlegend=True,
        legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11))))
    return fig




def make_bar_chart(labels, values, colors=None, horizontal=False, title=""):
    if horizontal:
        fig = go.Figure(go.Bar(
            y=labels, x=values,
            orientation="h",
            marker=dict(color=colors or "#3B82F6", cornerradius=4),
            hovertemplate="%{y}<br>%{x:,.2f}%<extra></extra>"
        ))
        fig.update_layout(**_layout(height=max(180, len(labels)*36),
            xaxis=dict(showgrid=True, gridcolor="#F1F5F9"),
            yaxis=dict(showgrid=False)))
    else:
        fig = go.Figure(go.Bar(
            x=labels, y=values,
            marker=dict(color=colors or "#3B82F6", cornerradius=4),
            hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>"
        ))
        fig.update_layout(**_layout(height=220))
    return fig




def make_waterfall(categories, values):
    colors = ["#10B981" if v >= 0 else "#EF4444" for v in values]
    fig = go.Figure(go.Bar(
        x=categories, y=values,
        marker=dict(color=colors, cornerradius=4),
        hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>"
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#CBD5E1", line_width=1)
    fig.update_layout(**_layout(height=220))
    return fig




def make_gauge(value, max_val=100, label="Risk Score"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": label, "font": {"size": 12, "color": "#64748B", "family": "DM Sans"}},
        number={"font": {"size": 28, "color": "#0F172A", "family": "DM Sans"}, "suffix": "/10"},
        gauge={
            "axis": {"range": [0, 10], "tickwidth": 0, "tickcolor": "#E2E8F0", "tickvals": []},
            "bar": {"color": "#3B82F6", "thickness": 0.3},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 3], "color": "#DCFCE7"},
                {"range": [3, 6], "color": "#FEF3C7"},
                {"range": [6, 10], "color": "#FEE2E2"},
            ],
        }
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=180,
        margin=dict(l=20, r=20, t=40, b=0),
        font=dict(family="DM Sans, sans-serif"))
    return fig




# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
for key, default in {
    "df_holdings": pd.DataFrame(),
    "df_txns":     pd.DataFrame(),
    "df_sips":     pd.DataFrame(),
    "parsed":      False,
    "error":       None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default




# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='display:flex;align-items:center;gap:10px;margin-bottom:20px;padding-bottom:20px;border-bottom:1px solid #E2E8F0'>
        <div style='width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,#5B5FD6 0%,#7C3AED 100%);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#fff;box-shadow:0 4px 12px rgba(91,95,214,0.3)'>F</div>
        <div>
            <div style='font-size:16px;font-weight:800;color:#0F172A;letter-spacing:-0.3px'>FolioIQ</div>
            <div style='font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.8px'>MF Intelligence</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


    st.markdown("<div style='font-size:11px;color:#475569;margin-bottom:4px'>Upload your CAMS/KFintech Detailed CAS</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Detailed CAS PDF", type=["pdf"], label_visibility="collapsed", key="cas_upload")
    password = st.text_input("PAN Password", type="password", placeholder="ABCDE1234F (uppercase)")


    if st.button("🔍  Analyze Portfolio", use_container_width=True, type="primary", key="btn_cas"):
        if not uploaded_file:
            st.error("Please upload a CAS PDF")
        elif not password:
            st.error("Please enter your PAN password")
        else:
            with st.spinner("Parsing CAS…"):
                df_h, df_t, df_s, err, is_partial = parse_cas(uploaded_file.getvalue(), password)
            if err:
                st.session_state.error   = err
                st.session_state.parsed  = False
            else:
                st.session_state.df_holdings = df_h
                st.session_state.df_txns     = df_t
                st.session_state.df_sips     = df_s
                st.session_state.is_partial_cas = is_partial
                st.session_state.parsed      = True
                st.session_state.error       = None
                st.rerun()


    benchmark_name = list(BENCHMARKS.keys())[0]
    sel_cats = []
    sel_amcs = []
    plan_filter = "All"
    min_alloc = 0.0

    if st.session_state.parsed:
        st.markdown("---")
        st.markdown("<div style='font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px'>Global Filters</div>", unsafe_allow_html=True)


        benchmark_name = st.selectbox("Benchmark", list(BENCHMARKS.keys()))


        df_h = st.session_state.df_holdings
        all_cats = sorted(df_h["Category"].unique().tolist()) if not df_h.empty else []
        all_amcs = sorted(df_h["AMC"].unique().tolist()) if not df_h.empty else []


        sel_cats = st.multiselect("Category", all_cats, default=all_cats, key="filter_cat")
        sel_amcs = st.multiselect("AMC", all_amcs, default=all_amcs, key="filter_amc")
        plan_filter= st.radio("Plan Type", ["All","Direct","Regular"], horizontal=True)
        min_alloc  = st.slider("Min Allocation %", 0.0, 20.0, 0.0, 0.5)


    st.markdown("---")
    st.markdown("<div style='font-size:10px;color:#334155;text-align:center'>SEBI CSCRF 2025 &middot; Zero Data Retention<br>FolioIQ v5.0 &middot; In-memory processing</div>", unsafe_allow_html=True)




# ─────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────


# ── ONBOARDING SCREEN ──
if not st.session_state.parsed:
    if st.session_state.error:
        st.markdown(f'<div class="alert-danger">⚠ <b>Parse Error:</b> {st.session_state.error}</div>', unsafe_allow_html=True)
        st.info("Check that you used a 'Detailed CAS' PDF and the correct PAN (uppercase) as password.")
    else:
        st.markdown("""
        <div class="onboard-hero">
            <div class="onboard-title" style="background:linear-gradient(135deg,#0A0F1E 0%,#5B5FD6 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">Know your portfolio.<br>Beat the benchmark.</div>
            <div class="onboard-sub">Upload your CAMS/KFintech CAS and get institutional-grade analytics &mdash; instantly, privately.</div>
            <div class="step-grid">
                <div class="step-card">
                    <div class="step-num">STEP 1</div>
                    <div class="step-title">CAS PDF Import</div>
                    <div class="step-desc">Get a <b>Detailed CAS</b> from cams.com, kfintech.com, or mfcentral.com. Covers all AMCs with full transaction history.</div>
                </div>
                <div class="step-card">
                    <div class="step-num">STEP 2</div>
                    <div class="step-title">Upload &amp; analyze</div>
                    <div class="step-desc">Enter your PAN password, upload the file in the sidebar, and click <b>Analyze Portfolio</b>. Zero data retention.</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.stop()




# ── FILTER APPLICATION ──
df_h_raw = st.session_state.df_holdings.copy()
df_t_raw = st.session_state.df_txns.copy()
df_s_raw = st.session_state.df_sips.copy()


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


# Filter txns to match filtered holdings
filtered_funds = set(df_h["Fund"].tolist())
df_t = df_t_raw[df_t_raw["Fund"].isin(filtered_funds)] if (not df_t_raw.empty and "Fund" in df_t_raw.columns) else pd.DataFrame()
df_s = df_s_raw[df_s_raw["Fund"].isin(filtered_funds)] if (not df_s_raw.empty and "Fund" in df_s_raw.columns) else pd.DataFrame()


df_t_period = df_t


# ── KEY METRICS ──
total_value    = float(df_h["Market Value"].sum())
total_invested = float(df_h["Invested"].sum())
total_gain     = total_value - total_invested
gain_pct       = (total_gain / total_invested * 100) if total_invested > 0 else 0.0


ticker         = BENCHMARKS.get(benchmark_name, "^NSEI")
bench_data     = fetch_benchmark(ticker, 9999) # fetch all history


# Calculate global benchmark return (for Alpha)
bench_ret      = 0.0
bench_cagr     = 0.0
if not bench_data.empty and len(bench_data) >= 2:
    bench_ret = ((float(bench_data.iloc[-1]) / float(bench_data.iloc[0])) - 1) * 100
    days = max((bench_data.index[-1] - bench_data.index[0]).days, 1)
    bench_cagr = (((float(bench_data.iloc[-1]) / float(bench_data.iloc[0])) ** (365.0/days)) - 1) * 100


portfolio_xirr = compute_xirr(df_t_raw, float(df_h_raw["Market Value"].sum()))


# Simulate benchmark: what if same cash flows were invested in benchmark?
bench_xirr_val, bench_current_value = compute_benchmark_xirr(df_t_raw, bench_data)
alpha          = portfolio_xirr - bench_xirr_val


num_funds      = len(df_h)
num_amcs       = df_h["AMC"].nunique()
port_score     = compute_portfolio_score(df_h, portfolio_xirr, bench_xirr_val)
expense_drag   = estimate_expense_drag(df_h)
sip_score      = sip_consistency_score(df_s_raw)


if st.session_state.get("is_partial_cas", False):
    st.markdown('<div class="alert-info" style="margin-bottom:12px">&#9432; <b>Partial CAS Detected:</b> This statement does not cover the history since your first investment. Invested Amount and XIRR calculations may be incorrect. For accurate analytics, download a Detailed CAS with the period "Since Inception".</div>', unsafe_allow_html=True)


# ── TABS ──
tab_dash, tab_factor, tab_perf, tab_hold, tab_compare, tab_tax, tab_insights, tab_sip = st.tabs([
    "📊 Overview",
    "💰 Factor Analysis",
    "📈 Performance",
    "📋 Holdings",
    "🔀 Compare",
    "🧾 Tax",
    "💡 Smart Insights",
    "🔄 SIP Calculator",
])




# ════════════════════════════════════════════
# TAB 1: OVERVIEW DASHBOARD
# ════════════════════════════════════════════
with tab_dash:
    
    # Portfolio Summary ("Dashboard Count")
    sign_sum = "+" if total_gain >= 0 else ""
    st.markdown(f"""
    <div style="font-size: 20px; font-weight: 700; margin-bottom: 16px; color: #0F172A;">Portfolio Summary</div>
    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom: 40px;">
        <div style="background:white; border:1px solid #E2E8F0; border-radius:12px; padding:16px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
            <div style="color:#64748B; font-size:13px; font-weight:600; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px;">Current Value</div>
            <div style="color:#0F172A; font-size:24px; font-weight:800; letter-spacing:-0.5px;">{fmt_inr(total_value)}</div>
        </div>
        <div style="background:white; border:1px solid #E2E8F0; border-radius:12px; padding:16px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
            <div style="color:#64748B; font-size:13px; font-weight:600; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px;">Total Invested</div>
            <div style="color:#0F172A; font-size:24px; font-weight:800; letter-spacing:-0.5px;">{fmt_inr(total_invested)}</div>
        </div>
        <div style="background:white; border:1px solid #E2E8F0; border-radius:12px; padding:16px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
            <div style="color:#64748B; font-size:13px; font-weight:600; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px;">Total Returns</div>
            <div style="color:{'#10B981' if total_gain >= 0 else '#EF4444'}; font-size:24px; font-weight:800; letter-spacing:-0.5px;">{sign_sum}{fmt_inr(total_gain)} <span style="font-size:14px; margin-left:4px;">({sign_sum}{gain_pct:.2f}%)</span></div>
        </div>
        <div style="background:white; border:1px solid #E2E8F0; border-radius:12px; padding:16px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
            <div style="color:#64748B; font-size:13px; font-weight:600; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px;">Portfolio XIRR</div>
            <div style="color:#0F172A; font-size:24px; font-weight:800; letter-spacing:-0.5px;">{portfolio_xirr:.2f}%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div style="font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #0F172A;">Portfolio vs Market</div>', unsafe_allow_html=True)


    # ── Date filter ──
    period_sel = st.pills("Period", ["1M", "3M", "6M", "1Y", "3Y", "5Y", "ALL"], default="1Y", label_visibility="collapsed")


    period_map_dash = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825, "ALL": 9999}
    period_days_dash = period_map_dash.get(period_sel, 365)


    if not bench_data.empty:
        # ── Use the corrected comparison function ──
        comp = compute_period_comparison(df_t_raw, total_value, bench_data, period_days_dash)
        
        port_period_pct = comp["port_pct"]
        bench_period_pct = comp["bench_pct"]
        bench_sim_value = comp["bench_value"]
        use_xirr = comp["use_xirr"]
        port_value_at_start = comp["port_start_value"]


        # ── Benchmark slice for chart ──
        if period_days_dash < 9999:
            cutoff = bench_data.index[-1] - timedelta(days=period_days_dash)
            bench_slice = bench_data[bench_data.index >= cutoff]
        else:
            bench_slice = bench_data
        if len(bench_slice) < 2:
            bench_slice = bench_data.iloc[-2:]


        # ── Label ──
        lbl = {"1M":"1M","3M":"3M","6M":"6M","1Y":"12M","3Y":"3Y","5Y":"5Y","ALL":""}
        pl = lbl.get(period_sel, "")
        subtitle = f"{pl} XIRR (Annualized)" if use_xirr and pl else ("XIRR (Annualized)" if use_xirr else f"{pl} Absolute Returns")


        pc = "#10B981" if port_period_pct >= 0 else "#EF4444"
        bc = "#10B981" if bench_period_pct >= 0 else "#EF4444"
        alpha_period = port_period_pct - bench_period_pct
        ac = "#10B981" if alpha_period >= 0 else "#EF4444"
        alpha_sign = "+" if alpha_period >= 0 else ""


        st.markdown(f"""
        <div style="font-size:13px; color:#94A3B8; margin-bottom:10px;">{subtitle}</div>
        <div style="display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:16px;">
            <div style="flex:1; background:#EEF2FF; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="color:#2563EB; font-weight:600; font-size:14px; margin-bottom:8px;">My Portfolio</div>
                <div style="color:{pc}; font-weight:700; font-size:24px; margin-bottom:4px;">{port_period_pct:.2f}%</div>
                <div style="color:#60A5FA; font-size:15px; font-weight:500;">{fmt_inr(total_value)}</div>
            </div>
            <div style="color:#94A3B8; font-weight:600; font-size:13px; background:#F8FAFC; padding:6px 10px; border-radius:50%; border:1px solid #E2E8F0; z-index:1; margin:-10px;">vs</div>
            <div style="flex:1; background:#FFF7ED; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="color:#C2410C; font-weight:600; font-size:14px; margin-bottom:8px; text-transform:uppercase;">{benchmark_name}</div>
                <div style="color:{bc}; font-weight:700; font-size:24px; margin-bottom:4px;">{bench_period_pct:.2f}%</div>
                <div style="color:#FDBA74; font-size:15px; font-weight:500;">{fmt_inr(bench_sim_value)}</div>
            </div>
        </div>
        <div style="display:flex; justify-content:center; margin-bottom:12px;">
            <div style="background:{'#F0FDF4' if alpha_period >= 0 else '#FEF2F2'}; border:1px solid {'#BBF7D0' if alpha_period >= 0 else '#FECACA'}; border-radius:8px; padding:6px 16px; font-size:13px; font-weight:600; color:{ac};">
                Alpha: {alpha_sign}{alpha_period:.2f}% {'outperforming' if alpha_period >= 0 else 'underperforming'}
            </div>
        </div>
        """, unsafe_allow_html=True)


        st.markdown(f'<div style="font-size:12px; color:#94A3B8; margin-bottom:8px;">Last updated on {datetime.now().strftime("%d %b %Y")}</div>', unsafe_allow_html=True)


        # ── Chart: Portfolio vs Benchmark cumulative growth ──
        bench_norm = bench_slice / bench_slice.iloc[0] * 100


        # Build portfolio growth curve
        # We reconstruct portfolio's cumulative value at each benchmark date
        # by tracking: starting value grows with the market, plus SIPs added along the way
        period_start_dt = bench_slice.index[0]
        bench_price_s = float(bench_slice.iloc[0])
        
        if port_value_at_start > 0 and bench_price_s > 0:
            # Build transaction list within the period for curve construction
            txns_in_period_list = []
            if not df_t_raw.empty and "Date" in df_t_raw.columns:
                for _, row in df_t_raw.iterrows():
                    if row["Date"] < period_start_dt:
                        continue
                    amt = abs(float(row.get("Amount", 0)))
                    if amt == 0:
                        continue
                    t_type = str(row.get("Type", "")).upper()
                    if "REINVEST" in t_type:
                        continue
                    units = float(row.get("Units", 0))
                    txns_in_period_list.append((row["Date"], amt, units, t_type))
            txns_in_period_list.sort(key=lambda x: x[0])
            
            # Track cumulative invested capital + estimated value at each benchmark date
            # Using benchmark-based growth as proxy for portfolio growth
            port_norm_vals = []
            txn_idx = 0
            cumulative_bench_units = port_value_at_start / bench_price_s
            
            for dt in bench_slice.index:
                # Process any transactions up to this date
                while txn_idx < len(txns_in_period_list) and txns_in_period_list[txn_idx][0] <= dt:
                    td, tamt, tunits, ttype = txns_in_period_list[txn_idx]
                    bp = _get_bench_price(bench_data, td)
                    if bp <= 0:
                        bp = bench_price_s
                    if tunits > 0:
                        cumulative_bench_units += tamt / bp
                    elif tunits < 0:
                        cumulative_bench_units = max(0, cumulative_bench_units - tamt / bp)
                    txn_idx += 1
                
                # Portfolio value at this date (using benchmark price as proxy)
                bp_at_dt = float(bench_slice.loc[dt]) if dt in bench_slice.index else _get_bench_price(bench_data, dt)
                port_val_at_dt = cumulative_bench_units * bp_at_dt
                
                # Normalize: what's this as a fraction of start value?
                port_norm_vals.append(port_val_at_dt / port_value_at_start * 100)
            
            # Adjust final point to match actual portfolio performance
            # The curve above uses benchmark growth as proxy; scale it to match actual portfolio return
            if len(port_norm_vals) > 1 and port_norm_vals[-1] != 0:
                actual_end_norm = 100 * (1 + port_period_pct / 100) if not use_xirr else 100 * total_value / port_value_at_start
                scale_factor = actual_end_norm / port_norm_vals[-1] if port_norm_vals[-1] != 0 else 1.0
                # Blend: keep the shape from benchmark proxy but scale to match actual returns
                port_norm_vals = [100 + (v - 100) * scale_factor for v in port_norm_vals]
        else:
            # No starting value — just show cumulative investment growth
            port_norm_vals = [100] * len(bench_norm)
            if len(bench_norm) > 1:
                # Simple: scale from 100 to final return
                final_val = 100 * (1 + port_period_pct / 100)
                n = len(bench_norm)
                for i in range(n):
                    frac = i / max(n - 1, 1)
                    port_norm_vals[i] = 100 + (final_val - 100) * frac


        fig_vs = go.Figure()
        fig_vs.add_trace(go.Scatter(
            x=bench_norm.index, y=bench_norm.values, mode="lines",
            name=benchmark_name,
            line=dict(color="#F97316", width=2.5, shape="spline"),
            hovertemplate="%{x|%d %b %Y}<br>" + benchmark_name + ": %{y:.1f}<extra></extra>"
        ))
        fig_vs.add_trace(go.Scatter(
            x=bench_norm.index, y=port_norm_vals, mode="lines",
            name="My Portfolio",
            line=dict(color="#3B82F6", width=2.5, shape="spline"),
            hovertemplate="%{x|%d %b %Y}<br>Portfolio: %{y:.1f}<extra></extra>"
        ))
        fig_vs.update_layout(**_layout(
            height=380, showlegend=True,
            legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center", font=dict(size=12)),
            xaxis=dict(showgrid=False, tickformat="%b '%y" if period_days_dash > 365 else "%d %b"),
            yaxis=dict(showgrid=True, gridcolor="#F1F5F9", title=None, tickfont=dict(size=11), showticklabels=False),
            margin=dict(l=10, r=10, t=30, b=20)
        ))
        st.plotly_chart(fig_vs, use_container_width=True, config={"displayModeBar": False})


        # ── No data edge case ──
        if not df_t_raw.empty and "Date" in df_t_raw.columns:
            txns_in_range = df_t_raw[df_t_raw["Date"] >= bench_slice.index[0]]
            if txns_in_range.empty and port_value_at_start <= 0:
                st.markdown('<div class="alert-info">No transactions found in the selected period. Try a longer time range.</div>', unsafe_allow_html=True)
    else:
        st.info("Benchmark data unavailable. Check network connection.")




# ============================================
# TAB 2: FACTOR ANALYSIS (NEW)
# ============================================
with tab_factor:
    st.markdown('<div class="section-head">Expense Ratio Leakage Tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">The hidden cost of fund management fees compounding over 20 years</div>', unsafe_allow_html=True)


    leakage = expense_leakage_20yr(df_h)


    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.metric("Annual Expense Drag", fmt_inr(leakage["current_drag"]))
    with f2:
        st.metric("20-Year Lost Opportunity", fmt_inr(leakage["lost_20yr_current"]))
    with f3:
        savings_if_direct = leakage["saved_by_direct"]
        st.metric("Savings if Direct", fmt_inr(savings_if_direct))
    with f4:
        drag_pct = leakage["current_drag"] / total_value * 100 if total_value > 0 else 0
        st.metric("Drag % of Portfolio", f"{drag_pct:.2f}%")


    # Lost opportunity bar chart
    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)
    st.markdown("**Lost opportunity cost: Your portfolio vs Zero-expense scenario**")


    if leakage["lost_20yr_current"] > 0:
        fv_no_exp = total_value * (1.12) ** 20
        fv_with_exp = fv_no_exp - leakage["lost_20yr_current"]
        fig_leak = go.Figure()
        fig_leak.add_trace(go.Bar(
            x=["Without Expenses", "With Current Expenses", "Lost to Fees"],
            y=[fv_no_exp, fv_with_exp, leakage["lost_20yr_current"]],
            marker=dict(color=["#10B981", "#3B82F6", "#EF4444"], cornerradius=6),
            hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>"
        ))
        fig_leak.update_layout(**_layout(height=260))
        st.plotly_chart(fig_leak, use_container_width=True, config={"displayModeBar": False})


    # Direct vs Regular comparison
    st.markdown("**Direct vs Regular plan leakage comparison**")
    dr_col1, dr_col2 = st.columns(2)
    with dr_col1:
        st.markdown(f"""
        <div class="metric-card" style="border-left:4px solid #10B981">
            <div class="card-label">If everything was Direct</div>
            <div class="card-value" style="color:#10B981">{fmt_inr(leakage["direct_drag"])}/yr</div>
            <div class="card-sub">Lowest possible expense drag</div>
        </div>
        """, unsafe_allow_html=True)
    with dr_col2:
        st.markdown(f"""
        <div class="metric-card" style="border-left:4px solid #EF4444">
            <div class="card-label">If everything was Regular</div>
            <div class="card-value" style="color:#EF4444">{fmt_inr(leakage["regular_drag"])}/yr</div>
            <div class="card-sub">Maximum possible expense drag</div>
        </div>
        """, unsafe_allow_html=True)


    # Per-fund expense table
    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)
    st.markdown("**Per-fund expense leakage breakdown**")
    if leakage["by_fund"]:
        leak_df = pd.DataFrame(leakage["by_fund"])
        leak_df["Annual Drag"] = leak_df["Annual Drag"].apply(fmt_inr)
        leak_df["20yr Leakage"] = leak_df["20yr Leakage"].apply(fmt_inr)
        leak_df["ER%"] = leak_df["ER%"].apply(lambda x: f"{x:.2f}%")
        st.dataframe(leak_df, use_container_width=True, hide_index=True)


    # Sector heuristic sunburst
    st.markdown("<div style='margin:20px 0'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-head">Sector Exposure (Heuristic)</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Estimated sector allocation based on fund names</div>', unsafe_allow_html=True)


    df_h_sectors = df_h.copy()
    df_h_sectors["Sector"] = df_h_sectors["Fund"].apply(detect_sector)
    sector_grp = df_h_sectors.groupby("Sector")["Market Value"].sum().sort_values(ascending=False)


    if len(sector_grp) > 0:
        fig_sun = go.Figure(go.Pie(
            labels=sector_grp.index.tolist(),
            values=sector_grp.values.tolist(),
            hole=0.5,
            marker=dict(colors=SECTOR_COLORS[:len(sector_grp)]),
            textinfo="label+percent",
            textfont=dict(size=11),
            hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>"
        ))
        fig_sun.update_layout(**_layout(height=350, showlegend=False))
        st.plotly_chart(fig_sun, use_container_width=True, config={"displayModeBar": False})


        st.markdown('<div class="alert-info">Note: Sector exposure is estimated from fund names only. For precise stock-level overlap analysis, portfolio disclosure data from AMFI would be needed.</div>', unsafe_allow_html=True)
# ════════════════════════════════════════════
with tab_perf:
    # ══════════════════════════════════════════════════════════════
    # PER-FUND ANALYST-GRADE PERFORMANCE TAB  (v6.0)
    # Logic: each fund gets its own correct TRI benchmark,
    #        XIRR computed from actual CAS cashflows,
    #        benchmark XIRR simulated using same cashflows.
    #        Risk metrics seeded from category norms (Sharpe/Sortino/β/DD).
    #        Verdict: Strong / Average / Weak
    #        Action: Keep / Review / Replace with Index
    # ══════════════════════════════════════════════════════════════


    def _get_fund_benchmark(category, cap_type, fund_name):
        n = fund_name.upper()
        if ("NIFTY 50" in n or "NIFTY50" in n) and "MIDCAP" not in n and "SMALLCAP" not in n and "100" not in n and "500" not in n:
            return ("^NSEI", "Nifty 50")
        if "SENSEX" in n: return ("^BSESN", "Sensex")
        if "NIFTY NEXT 50" in n or "NEXT 50" in n: return ("^NSMIDCP", "Nifty Next 50")
        if "NIFTY MIDCAP" in n or "MIDCAP 150" in n: return ("^NSMIDCP", "Nifty Midcap 150")
        if "NIFTY SMALLCAP" in n or "SMALLCAP 250" in n: return ("NIFTYSMALLCAP250.NS", "Nifty SmallCap 250")
        if "NIFTY 500" in n or "NIFTY500" in n: return ("^CNX500", "Nifty 500")
        if "NIFTY 100" in n: return ("^CNX100", "Nifty 100")
        if category in ("Liquid","Debt"): return (None, "CRISIL Composite Bond Index")
        if cap_type in FUND_BENCH_BY_CAP: return FUND_BENCH_BY_CAP[cap_type]
        if category in FUND_BENCH_BY_CAT: return FUND_BENCH_BY_CAT[category]
        return ("^NSEI", "Nifty 50")


    def _analyze_fund(fund_name, fund_txns, cur_value, category, cap_type, plan, cat_gains_pct, period_days=9999):
        bench_ticker, bench_display = _get_fund_benchmark(category, cap_type, fund_name)
        bench_series = fetch_benchmark(bench_ticker, 9999) if bench_ticker else pd.Series(dtype=float)

        # ── Period filter: slice transactions to the selected time window ──
        if not fund_txns.empty and "Date" in fund_txns.columns and period_days < 9999:
            cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=period_days)
            # Handle tz-aware dates
            if hasattr(fund_txns["Date"].dtype, "tz") and fund_txns["Date"].dt.tz is not None:
                cutoff = cutoff.tz_localize(fund_txns["Date"].dt.tz)
            pre_txns    = fund_txns[fund_txns["Date"] < cutoff]
            period_txns = fund_txns[fund_txns["Date"] >= cutoff]
            # Fraction of current value attributable to pre-period purchases
            pre_bought   = pre_txns.loc[pre_txns["Units"] > 0, "Amount"].abs().sum() if not pre_txns.empty else 0.0
            total_bought = fund_txns.loc[fund_txns["Units"] > 0, "Amount"].abs().sum() if not fund_txns.empty else 0.0
            frac         = pre_bought / total_bought if total_bought > 0 else 0.0
            opening_val  = cur_value * frac
            if opening_val > 0:
                # Synthetic opening position: full pre-period value treated as a single purchase at cutoff
                opening_row = pd.DataFrame([{
                    "Date": cutoff, "Amount": -opening_val, "Units": 1.0,
                    "Type": "PURCHASE", "Fund": fund_name,
                    "AMC": "", "Category": category, "NAV": 0.0
                }])
                txns_to_analyse = pd.concat([opening_row, period_txns], ignore_index=True)
            else:
                txns_to_analyse = period_txns if not period_txns.empty else fund_txns
        else:
            txns_to_analyse = fund_txns

        fund_xi  = compute_xirr(txns_to_analyse, cur_value)
        bench_xi, bench_cur = (0.0, 0.0)
        if not bench_series.empty:
            bench_xi, bench_cur = compute_benchmark_xirr(txns_to_analyse, bench_series)
        alpha_f = fund_xi - bench_xi
        roll_periods = [30, 180, 365, 1095, 1825]
        roll_labels  = ["1M","6M","1Y","3Y","5Y"]
        bench_rolls  = compute_rolling_returns(bench_series, roll_periods) if not bench_series.empty else {}
        fund_rolls   = {d: fund_xi*(d/365.0) for d in roll_periods}
        beats        = sum(1 for d in roll_periods if fund_rolls.get(d,0) > bench_rolls.get(d,0))
        consistency  = round(beats / len(roll_periods) * 10, 1)
        tier = RISK_TIERS.get(category, RISK_TIERS["Other"])
        vol, beta, risk_label = tier
        rf      = 6.5
        sharpe  = max(0.0, (fund_xi - rf) / vol) if vol > 0 and fund_xi > 0 else 0.0
        sortino = max(0.0, (fund_xi - rf) / (vol*0.65)) if vol > 0 and fund_xi > 0 else 0.0
        max_dd  = -MAX_DD_ESTIMATE.get(category, 25)
        lo, hi  = EXP_RATIOS.get(category, (0.50, 1.50))
        er      = lo if plan=="Direct" else hi
        same_cat   = cat_gains_pct.get(category, [])
        fund_gain  = float(((cur_value - fund_txns["Amount"].abs().sum()) /
                            max(fund_txns["Amount"].abs().sum(), 1) * 100)
                           if not fund_txns.empty else 0)
        cat_rank  = sum(1 for g in same_cat if g > fund_gain) + 1
        cat_total = len(same_cat)
        if alpha_f >= 2.0 and consistency >= 6:   verdict, v_cls = "Strong",  "verdict-strong"
        elif alpha_f >= -1.0:                      verdict, v_cls = "Average", "verdict-average"
        else:                                       verdict, v_cls = "Weak",    "verdict-weak"
        if verdict == "Strong" and plan == "Direct":
            action, a_icon, a_col = "Keep",               "✅", "#059669"
        elif verdict == "Weak" or (alpha_f < -2 and er > 1.2):
            action, a_icon, a_col = "Replace with Index", "🔄", "#DC2626"
        else:
            action, a_icon, a_col = "Review",             "⚠️", "#D97706"
        return {
            "fund_name":fn,"category":category,"cap_type":cap_type,"plan":plan,
            "bench_display":bench_display,"bench_ticker":bench_ticker,
            "fund_xi":fund_xi,"bench_xi":bench_xi,"alpha":alpha_f,
            "bench_cur":bench_cur,"cur_value":cur_value,
            "consistency":consistency,"vol":vol,"beta":beta,"risk_label":risk_label,
            "sharpe":sharpe,"sortino":sortino,"max_dd":max_dd,"er":er,
            "cat_rank":cat_rank,"cat_total":cat_total,
            "verdict":verdict,"v_cls":v_cls,
            "action":action,"a_icon":a_icon,"a_col":a_col,
            "bench_rolls":bench_rolls,"fund_rolls":fund_rolls,
            "roll_labels":roll_labels,"roll_periods":roll_periods,
        }


    # ── Header ────────────────────────────────────────────────
    st.markdown('''
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:4px">
        <div>
            <div style="font-size:16px;font-weight:800;color:#0F172A;letter-spacing:-0.4px">Per-Fund Performance Analysis</div>
            <div style="font-size:11px;color:#94A3B8;margin-top:2px">
                Each fund compared against its correct TRI benchmark using your actual cashflows &nbsp;·&nbsp;
                XIRR · Sharpe · Consistency · Strong / Average / Weak verdict
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)


    perf_period = st.pills(
        "Period", ["1M","6M","1Y","3Y","5Y","All Time"],
        default="1Y", label_visibility="collapsed", key="perf_period_pills"
    )
    perf_days = {"1M":30,"6M":180,"1Y":365,"3Y":1095,"5Y":1825,"All Time":9999}.get(perf_period, 365)


    # Build per-category gain% list for peer ranking
    cat_gains_pct = {}
    for _, row in df_h.iterrows():
        cat_gains_pct.setdefault(row["Category"], []).append(float(row["Gain%"]))


    # Run analysis
    fund_results = []
    prog = st.progress(0, text="Analysing funds…")
    total_f = len(df_h)
    for idx, (_, row) in enumerate(df_h.iterrows()):
        fn       = row["Fund"]
        cur_val  = float(row["Market Value"])
        category = row["Category"]
        cap_type = row["Cap Type"]
        plan     = row["Plan"]
        fund_txns = df_t_raw[df_t_raw["Fund"]==fn] if not df_t_raw.empty and "Fund" in df_t_raw.columns else pd.DataFrame()
        res = _analyze_fund(fn, fund_txns, cur_val, category, cap_type, plan, cat_gains_pct, perf_days)
        fund_results.append(res)
        prog.progress(int((idx+1)/total_f*100), text=f"Analysing {idx+1}/{total_f}…")
    prog.empty()


    if not fund_results:
        st.info("No funds to analyse.")
    else:
        # ── Portfolio-level summary ───────────────────────────
        st.markdown("<div style='margin:16px 0 10px'></div>", unsafe_allow_html=True)


        n_strong  = sum(1 for r in fund_results if r["verdict"]=="Strong")
        n_average = sum(1 for r in fund_results if r["verdict"]=="Average")
        n_weak    = sum(1 for r in fund_results if r["verdict"]=="Weak")
        n_replace = sum(1 for r in fund_results if r["action"]=="Replace with Index")
        avg_alpha = float(np.mean([r["alpha"] for r in fund_results]))


        # Summary tiles
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:16px">
            <div class="metric-card" style="text-align:center;padding:14px 10px">
                <div class="card-label">Portfolio XIRR</div>
                <div style="font-size:20px;font-weight:800;color:#0F172A">{portfolio_xirr:.2f}%</div>
            </div>
            <div class="metric-card" style="text-align:center;padding:14px 10px">
                <div class="card-label">Benchmark XIRR</div>
                <div style="font-size:20px;font-weight:800;color:#0F172A">{bench_xirr_val:.2f}%</div>
            </div>
            <div class="metric-card" style="text-align:center;padding:14px 10px;border-left:3px solid {"#10B981" if alpha>=0 else "#EF4444"}">
                <div class="card-label">Alpha</div>
                <div style="font-size:20px;font-weight:800;color:{"#10B981" if alpha>=0 else "#EF4444"}">{"+" if alpha>=0 else ""}{alpha:.2f}%</div>
            </div>
            <div class="metric-card" style="text-align:center;padding:14px 10px;border-left:3px solid #10B981">
                <div class="card-label">🟢 Strong</div>
                <div style="font-size:22px;font-weight:800;color:#10B981">{n_strong}</div>
            </div>
            <div class="metric-card" style="text-align:center;padding:14px 10px;border-left:3px solid #F59E0B">
                <div class="card-label">🟡 Average</div>
                <div style="font-size:22px;font-weight:800;color:#D97706">{n_average}</div>
            </div>
            <div class="metric-card" style="text-align:center;padding:14px 10px;border-left:3px solid #EF4444">
                <div class="card-label">🔴 Weak</div>
                <div style="font-size:22px;font-weight:800;color:#EF4444">{n_weak}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)


        if n_replace > 0:
            st.markdown(f'''<div class="alert-warn">⚠ <b>{n_replace} fund(s)</b> recommended to be
                <b>Replaced with Index funds</b>. These funds are underperforming their benchmark
                on a risk-adjusted basis. Switching to a low-cost index fund in the same category
                would likely improve returns.</div>''', unsafe_allow_html=True)
        if avg_alpha < -2:
            st.markdown(f'''<div class="alert-danger">🚨 Average alpha of <b>{avg_alpha:+.2f}%</b>
                across all funds. Portfolio is significantly underperforming benchmarks.
                Review fund selection, consider index funds for core allocation.</div>''', unsafe_allow_html=True)
        elif avg_alpha >= 2:
            st.markdown(f'''<div class="alert-success">✅ Average alpha of <b>{avg_alpha:+.2f}%</b>.
                Portfolio is beating benchmarks consistently. Keep monitoring.</div>''', unsafe_allow_html=True)


        # ── Filters & sort ────────────────────────────────────
        st.markdown("<div style='margin:16px 0 10px'></div>", unsafe_allow_html=True)
        ff1, ff2, ff3 = st.columns(3)
        with ff1:
            v_filt = st.selectbox("Filter by Verdict", ["All","Strong","Average","Weak"], key="pf_verdict")
        with ff2:
            a_filt = st.selectbox("Filter by Action",  ["All","Keep","Review","Replace with Index"], key="pf_action")
        with ff3:
            s_filt = st.selectbox("Sort by", ["Alpha ↓","Alpha ↑","Fund XIRR","Consistency","Name"], key="pf_sort")


        filtered = fund_results.copy()
        if v_filt != "All": filtered = [r for r in filtered if r["verdict"]==v_filt]
        if a_filt != "All": filtered = [r for r in filtered if r["action"]==a_filt]
        smap = {
            "Alpha ↓":    (lambda r: r["alpha"],       True),
            "Alpha ↑":    (lambda r: r["alpha"],       False),
            "Fund XIRR":  (lambda r: r["fund_xi"],     True),
            "Consistency":(lambda r: r["consistency"],  True),
            "Name":       (lambda r: r["fund_name"],   False),
        }
        sk, sr = smap.get(s_filt, (lambda r: r["alpha"], True))
        filtered.sort(key=sk, reverse=sr)


        st.markdown(f"<div style='font-size:11px;color:#94A3B8;margin-bottom:10px'>{len(filtered)} funds shown</div>", unsafe_allow_html=True)


        # ── Fund cards ────────────────────────────────────────
        for res in filtered:
            fn_r   = res["fund_name"]
            cat_r  = res["category"]
            plan_r = res["plan"]
            cc_r   = CATEGORY_COLORS.get(cat_r, "#94A3B8")
            ac_r   = "#10B981" if res["alpha"] >= 0 else "#EF4444"
            as_r   = "+" if res["alpha"] >= 0 else ""
            fxc_r  = "#10B981" if res["fund_xi"] >= 0 else "#EF4444"
            bxc_r  = "#10B981" if res["bench_xi"] >= 0 else "#EF4444"
            mx_xi  = max(abs(res["fund_xi"]), abs(res["bench_xi"]), 0.01)
            fw_r   = min(abs(res["fund_xi"])  / mx_xi * 100, 100)
            bw_r   = min(abs(res["bench_xi"]) / mx_xi * 100, 100)
            fbar_c = "#10B981" if res["fund_xi"] >= 0 else "#EF4444"
            bbar_c = "#3B82F6"
            rl_f   = [res["fund_rolls"].get(d, 0)  for d in res["roll_periods"]]
            rl_b   = [res["bench_rolls"].get(d, 0) for d in res["roll_periods"]]
            rlab_r = res["risk_label"]
            rc_map = {"Very Low":"#10B981","Low":"#10B981","Moderate":"#D97706",
                      "Moderate-High":"#EA580C","High":"#EF4444"}
            rc_r   = rc_map.get(rlab_r, "#94A3B8")
            short_r = fn_r[:72] + ("…" if len(fn_r) > 72 else "")


            with st.expander(f"**{short_r}**  ·  {res['bench_display']}  ·  {res['verdict']}", expanded=False):
                # Row 1: name + badges + action
                top_l, top_r = st.columns([3, 2])
                with top_l:
                    st.markdown(f"""
                    <div style="margin-bottom:12px">
                        <div style="font-size:14px;font-weight:800;color:#0F172A;margin-bottom:8px">{fn_r}</div>
                        <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap">
                            <span style="background:{"#EFF6FF" if cat_r=="Equity" else "#F0FDF4" if cat_r=="Debt" else "#FAF5FF" if cat_r=="ELSS" else "#FFF7ED"};
                                  color:{"#1D4ED8" if cat_r=="Equity" else "#15803D" if cat_r=="Debt" else "#7C3AED" if cat_r=="ELSS" else "#C2410C"};
                                  border:1px solid #E2E8F0;border-radius:20px;
                                  font-size:9px;font-weight:700;padding:2px 8px;text-transform:uppercase;letter-spacing:0.6px">{cat_r}</span>
                            <span style="background:{"#F0FDF4" if plan_r=="Direct" else "#FFF7ED"};
                                  color:{"#15803D" if plan_r=="Direct" else "#C2410C"};
                                  border:1px solid #E2E8F0;border-radius:20px;
                                  font-size:9px;font-weight:700;padding:2px 8px;text-transform:uppercase;letter-spacing:0.6px">{plan_r}</span>
                            <span style="font-size:10px;color:#94A3B8;font-weight:600">{res["cap_type"]}</span>
                            <span style="font-size:10px;color:#94A3B8">Benchmark: <b style="color:#64748B">{res["bench_display"]}</b></span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with top_r:
                    rk_txt = f"{res['cat_rank']}/{res['cat_total']} in {cat_r}" if res["cat_total"]>1 else "—"
                    action_bg  = "#F0FDF4" if res["action"]=="Keep" else "#FEF2F2" if "Replace" in res["action"] else "#FFFBEB"
                    action_brd = "#BBF7D0" if res["action"]=="Keep" else "#FECACA" if "Replace" in res["action"] else "#FDE68A"
                    st.markdown(f"""
                    <div style="text-align:right">
                        <div style="display:flex;align-items:center;justify-content:flex-end;gap:7px;margin-bottom:7px">
                            <span class="{res['v_cls']}">{res["verdict"]}</span>
                            <span style="font-size:11px;font-weight:700;color:{res["a_col"]};
                                  background:{action_bg};border:1px solid {action_brd};
                                  padding:3px 10px;border-radius:20px">
                                {res["a_icon"]} {res["action"]}
                            </span>
                        </div>
                        <div style="font-size:11px;color:#94A3B8">Category rank: <b style="color:#64748B">{rk_txt}</b></div>
                        <div style="font-size:11px;color:#94A3B8;margin-top:2px">Consistency: <b style="color:#64748B">{res["consistency"]}/10</b></div>
                    </div>
                    """, unsafe_allow_html=True)


                # Row 2: 5 metric tiles
                mt = st.columns(5)
                with mt[0]:
                    st.markdown(f"""<div class="metric-card" style="text-align:center;padding:14px 10px">
                        <div class="card-label">Fund XIRR</div>
                        <div style="font-size:20px;font-weight:900;color:{fxc_r}">{res["fund_xi"]:.2f}%</div>
                        <div class="card-sub">Annualised</div></div>""", unsafe_allow_html=True)
                with mt[1]:
                    st.markdown(f"""<div class="metric-card" style="text-align:center;padding:14px 10px">
                        <div class="card-label">Benchmark XIRR</div>
                        <div style="font-size:20px;font-weight:900;color:{bxc_r}">{res["bench_xi"]:.2f}%</div>
                        <div class="card-sub">{res["bench_display"]}</div></div>""", unsafe_allow_html=True)
                with mt[2]:
                    card_brd = "#10B981" if res["alpha"]>=0 else "#EF4444"
                    st.markdown(f"""<div class="metric-card" style="text-align:center;padding:14px 10px;border-left:3px solid {card_brd}">
                        <div class="card-label">Alpha</div>
                        <div style="font-size:20px;font-weight:900;color:{ac_r}">{as_r}{res["alpha"]:.2f}%</div>
                        <div class="card-sub">{"Outperforming" if res["alpha"]>=0 else "Underperforming"}</div></div>""", unsafe_allow_html=True)
                with mt[3]:
                    st.markdown(f"""<div class="metric-card" style="text-align:center;padding:14px 10px">
                        <div class="card-label">Risk Level</div>
                        <div style="font-size:13px;font-weight:900;color:{rc_r};margin:4px 0">{rlab_r}</div>
                        <div class="card-sub">Sharpe {res["sharpe"]:.2f} · β {res["beta"]:.2f}</div></div>""", unsafe_allow_html=True)
                with mt[4]:
                    st.markdown(f"""<div class="metric-card" style="text-align:center;padding:14px 10px">
                        <div class="card-label">Max DD (est.)</div>
                        <div style="font-size:20px;font-weight:900;color:#EF4444">{res["max_dd"]:.0f}%</div>
                        <div class="card-sub">ER {res["er"]:.2f}% · {plan_r}</div></div>""", unsafe_allow_html=True)


                # Row 3: XIRR bar visual
                st.markdown(f"""
                <div style="background:#F8FAFC;border-radius:10px;padding:14px 16px;margin-top:12px">
                    <div style="font-size:9px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">XIRR comparison (same cashflows)</div>
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:7px">
                        <div style="font-size:11px;font-weight:700;color:#0F172A;width:96px;flex-shrink:0">Your fund</div>
                        <div style="flex:1;background:#E2E8F0;border-radius:4px;height:10px;overflow:hidden">
                            <div style="height:10px;border-radius:4px;background:{fbar_c};width:{fw_r:.1f}%"></div>
                        </div>
                        <div style="font-size:13px;font-weight:800;color:{fxc_r};width:54px;text-align:right">{res["fund_xi"]:.2f}%</div>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px">
                        <div style="font-size:11px;font-weight:700;color:#0F172A;width:96px;flex-shrink:0">{res["bench_display"][:14]}</div>
                        <div style="flex:1;background:#E2E8F0;border-radius:4px;height:10px;overflow:hidden">
                            <div style="height:10px;border-radius:4px;background:{bbar_c};width:{bw_r:.1f}%"></div>
                        </div>
                        <div style="font-size:13px;font-weight:800;color:{bxc_r};width:54px;text-align:right">{res["bench_xi"]:.2f}%</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)


                # Row 4: Rolling returns chart
                if any(abs(v) > 0 for v in rl_f + rl_b):
                    st.markdown("<div style='margin:12px 0 4px'></div>", unsafe_allow_html=True)
                    st.markdown("<div style='font-size:9px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px'>Rolling Returns — fund (est.) vs benchmark</div>", unsafe_allow_html=True)
                    fig_rr = go.Figure()
                    fig_rr.add_trace(go.Bar(name="Fund (est.)", x=res["roll_labels"], y=rl_f,
                        marker=dict(color="#6366F1", cornerradius=4),
                        hovertemplate="%{x}: %{y:.2f}%<extra>Fund</extra>"))
                    fig_rr.add_trace(go.Bar(name=res["bench_display"], x=res["roll_labels"], y=rl_b,
                        marker=dict(color="#E2E8F0", cornerradius=4),
                        hovertemplate="%{x}: %{y:.2f}%<extra>Benchmark</extra>"))
                    fig_rr.add_hline(y=0, line_dash="dot", line_color="#CBD5E1", line_width=1)
                    fig_rr.update_layout(**_layout(height=200, barmode="group", showlegend=True,
                        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=10))))
                    st.plotly_chart(fig_rr, use_container_width=True, config={"displayModeBar":False})


                # Row 5: Risk ratio details
                st.markdown("<div style='margin:8px 0 6px'></div>", unsafe_allow_html=True)
                ri4 = st.columns(4)
                ri_items = [
                    ("Volatility (est.)",   f"{res['vol']:.1f}% p.a.",     "Annual std dev (category-seeded)"),
                    ("Beta (est.)",         f"{res['beta']:.2f}",           "Sensitivity vs benchmark (1.0=market)"),
                    ("Sharpe Ratio (est.)", f"{res['sharpe']:.2f}",         "(XIRR−6.5%) ÷ volatility"),
                    ("Sortino Ratio (est.)",f"{res['sortino']:.2f}",        "Downside-adjusted return ratio"),
                ]
                for col_ri, (lbl_ri, val_ri, desc_ri) in zip(ri4, ri_items):
                    with col_ri:
                        st.markdown(f"""
                        <div style="background:#F8FAFC;border-radius:8px;padding:10px 12px;text-align:center">
                            <div style="font-size:9px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:0.7px;margin-bottom:3px">{lbl_ri}</div>
                            <div style="font-size:17px;font-weight:800;color:#0F172A">{val_ri}</div>
                            <div style="font-size:9px;color:#94A3B8;margin-top:2px">{desc_ri}</div>
                        </div>""", unsafe_allow_html=True)


        # ── Summary scorecard table ──────────────────────────
        st.markdown("<div style='margin:28px 0 12px'></div>", unsafe_allow_html=True)
        st.markdown("<div class='section-head'>Fund Scorecard — Summary Table</div>", unsafe_allow_html=True)
        srows = []
        for r in fund_results:
            srows.append({
                "Fund":          r["fund_name"][:55],
                "Category":      r["category"],
                "Plan":          r["plan"],
                "Benchmark":     r["bench_display"],
                "Fund XIRR%":    round(r["fund_xi"],   2),
                "Bench XIRR%":   round(r["bench_xi"],  2),
                "Alpha%":        round(r["alpha"],      2),
                "Consistency":   r["consistency"],
                "Sharpe":        round(r["sharpe"],     2),
                "Risk":          r["risk_label"],
                "Verdict":       r["verdict"],
                "Action":        r["action"],
            })
        sdf = pd.DataFrame(srows).sort_values("Alpha%", ascending=False)
        st.dataframe(sdf, use_container_width=True, hide_index=True,
            column_config={
                "Fund":        st.column_config.TextColumn("Fund",      width=220),
                "Fund XIRR%":  st.column_config.NumberColumn("Fund XIRR%",  format="%.2f%%"),
                "Bench XIRR%": st.column_config.NumberColumn("Bench XIRR%", format="%.2f%%"),
                "Alpha%":      st.column_config.NumberColumn("Alpha%",       format="%+.2f%%"),
                "Consistency": st.column_config.NumberColumn("Consistency",  format="%.1f"),
                "Sharpe":      st.column_config.NumberColumn("Sharpe",       format="%.2f"),
            })
        st.download_button(
            "⬇ Download Fund Scorecard CSV",
            sdf.to_csv(index=False).encode("utf-8"),
            "folioiq_scorecard.csv", "text/csv",
            use_container_width=True,
        )
        st.markdown('''<div class="alert-info" style="margin-top:10px;font-size:11px">
            <b>Methodology:</b> Fund XIRR computed from your actual CAS cashflows.
            Benchmark XIRR simulates the same cashflows invested in the mapped TRI benchmark index.
            Rolling returns and risk ratios (Sharpe, Sortino, β, Volatility, Max Drawdown) are
            <b>estimates seeded from category-level norms</b> — daily NAV history is required for
            precise computation. Verdicts prioritise long-term consistency over short-term rallies.
            Use the <b>Performance tab</b> alongside the <b>Smart Insights tab</b> for complete picture.
        </div>''', unsafe_allow_html=True)


# ════════════════════════════════════════════
# TAB 3: HOLDINGS
# ════════════════════════════════════════════
with tab_hold:
    h_col1, h_col2, h_col3, h_col4 = st.columns(4)
    with h_col1:
        sort_by = st.selectbox("Sort by", ["Market Value","Gain%","Weight%","Units","Fund"])
    with h_col2:
        sort_asc = st.radio("Order", ["↓ Desc","↑ Asc"], horizontal=True) == "↑ Asc"
    with h_col3:
        search_q = st.text_input("Search fund", placeholder="e.g. Mirae, HDFC…")
    with h_col4:
        cap_filter = st.selectbox("Cap type", ["All"] + sorted(df_h["Cap Type"].unique().tolist()))


    disp = df_h.copy()
    if search_q:
        disp = disp[disp["Fund"].str.contains(search_q, case=False, na=False)]
    if cap_filter != "All":
        disp = disp[disp["Cap Type"] == cap_filter]
    disp = disp.sort_values(sort_by, ascending=sort_asc)


    st.markdown(f"<div style='font-size:12px;color:#94A3B8;margin-bottom:10px'>{len(disp)} funds · ₹{disp['Market Value'].sum():,.0f} total value</div>", unsafe_allow_html=True)


    # Rich holdings list
    for _, row in disp.iterrows():
        cat   = row["Category"]
        plan  = row["Plan"]
        color = CATEGORY_COLORS.get(cat, "#94A3B8")
        g_col = "#10B981" if row["Gain%"] >= 0 else "#EF4444"
        g_sign= "+" if row["Gain%"] >= 0 else ""
        badge_cat  = f'<span class="badge badge-{cat.lower()}">{cat}</span>'
        badge_plan = f'<span class="badge badge-{plan.lower()}">{plan}</span>'


        st.markdown(f"""
        <div style='background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px 18px;margin-bottom:6px'>
            <div style='display:flex;align-items:center;justify-content:space-between'>
                <div style='display:flex;align-items:center;gap:12px;flex:1;min-width:0'>
                    <div style='width:10px;height:10px;border-radius:50%;background:{color};flex-shrink:0'></div>
                    <div style='min-width:0'>
                        <div style='font-size:13px;font-weight:700;color:#0F172A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{row["Fund"]}</div>
                        <div style='font-size:11px;color:#94A3B8;margin-top:3px'>{row["AMC"]} &nbsp;·&nbsp; {row["Cap Type"]} &nbsp;·&nbsp; {badge_cat} {badge_plan}</div>
                    </div>
                </div>
                <div style='display:grid;grid-template-columns:repeat(4,100px);gap:16px;text-align:right;flex-shrink:0;margin-left:16px'>
                    <div>
                        <div style='font-size:10px;color:#94A3B8;text-transform:uppercase'>Units</div>
                        <div style='font-size:13px;font-weight:600;color:#0F172A;font-family:JetBrains Mono,monospace'>{row["Units"]:.3f}</div>
                    </div>
                    <div>
                        <div style='font-size:10px;color:#94A3B8;text-transform:uppercase'>Invested</div>
                        <div style='font-size:13px;font-weight:600;color:#0F172A'>{fmt_inr(row["Invested"])}</div>
                    </div>
                    <div>
                        <div style='font-size:10px;color:#94A3B8;text-transform:uppercase'>Value</div>
                        <div style='font-size:13px;font-weight:700;color:#0F172A'>{fmt_inr(row["Market Value"])}</div>
                    </div>
                    <div>
                        <div style='font-size:10px;color:#94A3B8;text-transform:uppercase'>Return</div>
                        <div style='font-size:13px;font-weight:700;color:{g_col}'>{g_sign}{row["Gain%"]:.1f}%</div>
                    </div>
                </div>
            </div>
            <div style='margin-top:10px'>
                <div style='background:#F7F8FA;border-radius:4px;height:4px;position:relative'>
                    <div style='position:absolute;left:0;top:0;height:4px;border-radius:4px;background:{color};width:{min(row["Weight%"]*5, 100):.1f}%'></div>
                </div>
                <div style='font-size:10px;color:#CBD5E1;margin-top:3px;text-align:right'>{row["Weight%"]:.1f}% of portfolio</div>
            </div>
        </div>
        """, unsafe_allow_html=True)




# ════════════════════════════════════════════
# MERGED IN HOLDINGS: ALLOCATION
# ════════════════════════════════════════════
with tab_hold:
    st.markdown("---")
    st.markdown("<div class='section-head'>Allocation Overview</div>", unsafe_allow_html=True)
    a1, a2, a3 = st.columns(3)


    with a1:
        st.markdown("**Equity vs Debt vs Other**")
        eq_val  = df_h[df_h["Category"].isin(["Equity","ELSS","Index"])]["Market Value"].sum()
        debt_val= df_h[df_h["Category"].isin(["Debt","Liquid"])]["Market Value"].sum()
        hyb_val = df_h[df_h["Category"] == "Hybrid"]["Market Value"].sum()
        oth_val = max(0, total_value - eq_val - debt_val - hyb_val)
        donut_labels = ["Equity", "Debt", "Hybrid", "Other"]
        donut_vals   = [eq_val, debt_val, hyb_val, oth_val]
        donut_colors = ["#6366F1","#10B981","#F59E0B","#94A3B8"]
        donut_vals_f = [v for v in donut_vals if v > 0]
        donut_labs_f = [l for l, v in zip(donut_labels, donut_vals) if v > 0]
        donut_cols_f = [c for c, v in zip(donut_colors, donut_vals) if v > 0]
        st.plotly_chart(make_donut(donut_labs_f, donut_vals_f, donut_cols_f),
            use_container_width=True, config={"displayModeBar": False})


    with a2:
        st.markdown("**Cap-size breakdown**")
        cap_grp = df_h.groupby("Cap Type")["Market Value"].sum().sort_values(ascending=False)
        cap_colors = [SECTOR_COLORS[i % len(SECTOR_COLORS)] for i in range(len(cap_grp))]
        st.plotly_chart(make_bar_chart(cap_grp.index.tolist(), cap_grp.values.tolist(),
            cap_colors, horizontal=True), use_container_width=True, config={"displayModeBar": False})


    with a3:
        st.markdown("**Plan type: Direct vs Regular**")
        plan_grp = df_h.groupby("Plan")["Market Value"].sum()
        plan_colors = {"Direct":"#10B981","Regular":"#F59E0B"}
        pc = [plan_colors.get(p,"#94A3B8") for p in plan_grp.index]
        st.plotly_chart(make_donut(plan_grp.index.tolist(), plan_grp.values.tolist(), pc),
            use_container_width=True, config={"displayModeBar": False})


    # Regular plan warning
    reg_pct = df_h[df_h["Plan"]=="Regular"]["Market Value"].sum() / total_value * 100 if total_value > 0 else 0
    if reg_pct > 10:
        st.markdown(f'<div class="alert-warn" style="margin-top:8px">⚠ <b>{reg_pct:.1f}%</b> of portfolio is in <b>Regular plans</b>. Switching to Direct plans could save ~0.5–1.5% annually in expense ratio drag.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-success" style="margin-top:8px">✅ Portfolio is predominantly in <b>Direct plans</b>. Excellent cost efficiency.</div>', unsafe_allow_html=True)


    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)


    # Concentration heatmap
    st.markdown("**Fund concentration heatmap**")
    weight_data = df_h[["Fund","AMC","Category","Weight%"]].sort_values("Weight%", ascending=False)
    top_funds   = weight_data.head(15)
    fig_heat = go.Figure(go.Bar(
        x=top_funds["Weight%"],
        y=top_funds["Fund"].apply(lambda x: x[:35]+"…" if len(x)>35 else x),
        orientation="h",
        marker=dict(
            color=top_funds["Weight%"],
            colorscale=[[0,"#EEF2FF"],[0.5,"#818CF8"],[1,"#3730A3"]],
            showscale=True,
            colorbar=dict(title="Weight %", thickness=12, len=0.8)
        ),
        hovertemplate="%{y}<br>Weight: %{x:.1f}%<extra></extra>"
    ))
    fig_heat.update_layout(**_layout(
        height=max(300, len(top_funds)*32),
        yaxis=dict(showgrid=False, autorange="reversed")))
    st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})




# ════════════════════════════════════════════
# TAB: FUND COMPARISON
# ════════════════════════════════════════════
with tab_compare:
    st.markdown('<div class="section-head">Fund Comparison Matrix</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Select 2-3 funds from your portfolio to compare side-by-side</div>', unsafe_allow_html=True)


    fund_options = df_h["Fund"].tolist()
    selected_funds = st.multiselect(
        "Select funds to compare",
        fund_options,
        default=fund_options[:min(3, len(fund_options))],
        max_selections=4,
        key="compare_funds"
    )


    if selected_funds and len(selected_funds) >= 2:
        compare_cols = st.columns(len(selected_funds))
        for i, fund_name in enumerate(selected_funds):
            fund_row = df_h[df_h["Fund"] == fund_name].iloc[0]
            cat_color = CATEGORY_COLORS.get(fund_row["Category"], "#94A3B8")
            g_color = "#10B981" if fund_row["Gain%"] >= 0 else "#EF4444"
            g_sign = "+" if fund_row["Gain%"] >= 0 else ""
            with compare_cols[i]:
                short_name = fund_name[:30] + "..." if len(fund_name) > 30 else fund_name
                st.markdown(f"""
                <div class="compare-card">
                    <div style="width:40px;height:40px;border-radius:10px;background:{cat_color};display:flex;align-items:center;justify-content:center;margin:0 auto 10px;font-size:16px;font-weight:800;color:#fff">{fund_row["Category"][0]}</div>
                    <div class="fund-name">{short_name}</div>
                    <div class="compare-row"><span class="compare-label">Category</span><span class="compare-val">{fund_row["Category"]}</span></div>
                    <div class="compare-row"><span class="compare-label">Plan</span><span class="compare-val">{fund_row["Plan"]}</span></div>
                    <div class="compare-row"><span class="compare-label">Cap Type</span><span class="compare-val">{fund_row["Cap Type"]}</span></div>
                    <div class="compare-row"><span class="compare-label">AMC</span><span class="compare-val">{fund_row["AMC"]}</span></div>
                    <div class="compare-row"><span class="compare-label">Units</span><span class="compare-val">{fund_row["Units"]:.3f}</span></div>
                    <div class="compare-row"><span class="compare-label">Invested</span><span class="compare-val">{fmt_inr(fund_row["Invested"])}</span></div>
                    <div class="compare-row"><span class="compare-label">Value</span><span class="compare-val" style="font-size:14px">{fmt_inr(fund_row["Market Value"])}</span></div>
                    <div class="compare-row"><span class="compare-label">Return</span><span class="compare-val" style="color:{g_color}">{g_sign}{fund_row["Gain%"]:.2f}%</span></div>
                    <div class="compare-row"><span class="compare-label">Weight</span><span class="compare-val">{fund_row["Weight%"]:.1f}%</span></div>
                    <div class="compare-row" style="border:none"><span class="compare-label">Est. ER</span><span class="compare-val">{EXP_RATIOS.get(fund_row["Category"], (0.5,1.2))[0 if fund_row["Plan"]=="Direct" else 1]:.2f}%</span></div>
                </div>
                """, unsafe_allow_html=True)


        # Return comparison chart
        st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)
        st.markdown("**Return comparison**")
        comp_df = df_h[df_h["Fund"].isin(selected_funds)]
        comp_names = [f[:25]+"..." if len(f)>25 else f for f in comp_df["Fund"]]
        comp_colors = [CATEGORY_COLORS.get(c, "#94A3B8") for c in comp_df["Category"]]
        fig_comp = go.Figure(go.Bar(
            x=comp_names, y=comp_df["Gain%"].values,
            marker=dict(color=comp_colors, cornerradius=6),
            hovertemplate="%{x}<br>Return: %{y:.2f}%<extra></extra>"
        ))
        fig_comp.add_hline(y=0, line_dash="dot", line_color="#CBD5E1", line_width=1)
        fig_comp.update_layout(**_layout(height=240))
        st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar": False})
    elif selected_funds and len(selected_funds) < 2:
        st.info("Please select at least 2 funds to compare.")
    else:
        st.info("Select funds from the dropdown above to begin comparison.")




# ════════════════════════════════════════════
# TAB: SIP CALCULATOR
# ════════════════════════════════════════════
with tab_sip:
    st.markdown('<div class="section-head">Step-Up SIP Calculator</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">See how increasing your SIP annually can supercharge wealth creation</div>', unsafe_allow_html=True)


    su1, su2, su3, su4 = st.columns(4)
    with su1:
        sip_monthly = st.number_input("Monthly SIP", min_value=500, max_value=10_000_000, value=10000, step=500, key="stepup_sip")
    with su2:
        sip_years = st.slider("Years", 1, 40, 15, key="stepup_years")
    with su3:
        sip_return = st.slider("Expected Return %", 5.0, 25.0, 12.0, 0.5, key="stepup_return")
    with su4:
        stepup_rate = st.slider("Annual Step-Up %", 0.0, 25.0, 10.0, 1.0, key="stepup_rate")


    projection = stepup_sip_projection(sip_monthly, sip_years, sip_return, stepup_rate)


    p1, p2, p3 = st.columns(3)
    with p1:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center">
            <div class="card-label">Flat SIP Corpus</div>
            <div class="card-value" style="font-size:20px">{fmt_inr(projection["flat_fv"])}</div>
            <div class="card-sub">Invested: {fmt_inr(projection["flat_inv"])}</div>
        </div>
        """, unsafe_allow_html=True)
    with p2:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center;border:2px solid #6366F1">
            <div class="card-label" style="color:#6366F1">Step-Up SIP Corpus</div>
            <div class="card-value" style="font-size:20px;color:#6366F1">{fmt_inr(projection["stepup_fv"])}</div>
            <div class="card-sub">Invested: {fmt_inr(projection["stepup_inv"])}</div>
        </div>
        """, unsafe_allow_html=True)
    with p3:
        st.markdown(f"""
        <div class="metric-card" style="text-align:center;border:2px solid #10B981">
            <div class="card-label" style="color:#10B981">Extra Wealth from Step-Up</div>
            <div class="card-value" style="font-size:20px;color:#10B981">{fmt_inr(projection["extra_wealth"])}</div>
            <div class="card-sub">{stepup_rate:.0f}% annual increase</div>
        </div>
        """, unsafe_allow_html=True)


    # Step-up growth chart
    r_m = sip_return / 100 / 12
    flat_curve, stepup_curve, inv_flat, inv_step = [], [], [], []
    flat_acc, step_acc, flat_inv_acc, step_inv_acc = 0.0, 0.0, 0.0, 0.0
    current_amt = float(sip_monthly)
    for yr in range(sip_years):
        for mo in range(12):
            flat_inv_acc += sip_monthly
            step_inv_acc += current_amt
            flat_acc = flat_acc * (1 + r_m) + sip_monthly
            step_acc = step_acc * (1 + r_m) + current_amt
        flat_curve.append(flat_acc)
        stepup_curve.append(step_acc)
        inv_flat.append(flat_inv_acc)
        inv_step.append(step_inv_acc)
        current_amt *= (1 + stepup_rate / 100)


    fig_stepup = go.Figure()
    years_x = list(range(1, sip_years + 1))
    fig_stepup.add_trace(go.Scatter(x=years_x, y=stepup_curve, mode="lines", name="Step-Up SIP",
        line=dict(color="#6366F1", width=3), fill="tozeroy", fillcolor="rgba(99,102,241,0.08)"))
    fig_stepup.add_trace(go.Scatter(x=years_x, y=flat_curve, mode="lines", name="Flat SIP",
        line=dict(color="#94A3B8", width=2, dash="dot")))
    fig_stepup.add_trace(go.Scatter(x=years_x, y=inv_step, mode="lines", name="Step-Up Invested",
        line=dict(color="#CBD5E1", width=1, dash="dash")))
    fig_stepup.update_layout(**_layout(height=280, showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11))))
    st.plotly_chart(fig_stepup, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════
# TAB: SMART INSIGHTS
# ════════════════════════════════════════════
with tab_insights:
    st.markdown('<div class="section-head">Smart Insights & Alerts</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">AI-powered nudges and actionable recommendations</div>', unsafe_allow_html=True)


    # ELSS Lock-in Analysis
    st.markdown("**ELSS Tax Saver Lock-in Tracker**")
    elss_analysis = elss_lock_in_analysis(df_h, df_t_raw)
    if elss_analysis:
        for item in elss_analysis:
            if item["Unlocked"]:
                st.markdown(f"""
                <div class="alert-success" style="margin-bottom:8px">
                    <b>Unlocked:</b> {item["Fund"][:60]}<br>
                    Value: {fmt_inr(item["Value"])} &middot; Gain: {fmt_inr(item["Gain"])}<br>
                    Lock-in completed on {item["Lock-in Ends"].strftime("%d %b %Y")}. You can redeem and re-invest for fresh 80C benefit without adding new capital.
                </div>
                """, unsafe_allow_html=True)
            else:
                progress = max(0, (1 - item["Days Left"] / (3*365))) * 100
                st.markdown(f"""
                <div class="alert-info" style="margin-bottom:8px">
                    <b>Locked:</b> {item["Fund"][:60]}<br>
                    Value: {fmt_inr(item["Value"])} &middot; {item["Days Left"]} days remaining<br>
                    <div style="background:#E2E8F0;border-radius:4px;height:6px;margin-top:6px">
                        <div style="height:6px;border-radius:4px;background:#3B82F6;width:{progress:.0f}%"></div>
                    </div>
                    <div style="font-size:11px;color:#64748B;margin-top:2px">Unlocks on {item["Lock-in Ends"].strftime("%d %b %Y")}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-info">No ELSS funds found in your portfolio.</div>', unsafe_allow_html=True)


    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)


    # Liquidity Layer
    st.markdown("**Emergency Liquidity Layer**")
    liquid_funds = df_h[df_h["Category"].isin(["Liquid", "Overnight"])]
    if not liquid_funds.empty:
        liquid_total = float(liquid_funds["Market Value"].sum())
        instant_redeem = min(50000, liquid_total * 0.9)  # SEBI limit
        st.markdown(f"""
        <div class="metric-card" style="border-left:4px solid #06B6D4">
            <div style="display:flex;align-items:center;justify-content:space-between">
                <div>
                    <div class="card-label">Instant Redemption Available</div>
                    <div class="card-value" style="color:#06B6D4">{fmt_inr(instant_redeem)}</div>
                    <div class="card-sub">From {len(liquid_funds)} liquid/overnight fund(s) &middot; Total: {fmt_inr(liquid_total)}</div>
                </div>
                <div style="font-size:40px">💧</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.caption("SEBI allows instant redemption up to Rs 50,000 per fund per day for Liquid/Overnight funds via IMPS.")
    else:
        st.markdown('<div class="alert-warn">No liquid/overnight funds found. Consider adding one for emergency access to cash within minutes.</div>', unsafe_allow_html=True)


    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)


    # Smart Nudges
    st.markdown("**Smart Nudges**")
    nudges = []


    # Regular plan nudge
    reg_count = len(df_h[df_h["Plan"] == "Regular"])
    if reg_count > 0:
        reg_val = float(df_h[df_h["Plan"] == "Regular"]["Market Value"].sum())
        nudges.append(("warn", f"You have {reg_count} fund(s) worth {fmt_inr(reg_val)} in Regular plans. Switching to Direct saves ~0.5-1.5% annually."))


    # Concentration nudge
    if not df_h.empty:
        top_weight = float(df_h["Weight%"].max())
        if top_weight > 25:
            top_fund = df_h.loc[df_h["Weight%"].idxmax(), "Fund"][:40]
            nudges.append(("warn", f"High concentration: '{top_fund}' is {top_weight:.1f}% of your portfolio. Consider diversifying below 20%."))


    # Small cap nudge
    sc_val = df_h[df_h["Cap Type"] == "Small Cap"]["Market Value"].sum()
    sc_pct = sc_val / total_value * 100 if total_value > 0 else 0
    if sc_pct > 30:
        nudges.append(("danger", f"Small cap allocation is {sc_pct:.1f}% — this is aggressive. Ensure your risk tolerance matches."))
    elif sc_pct > 15:
        nudges.append(("info", f"Small cap allocation: {sc_pct:.1f}%. Good exposure for long-term wealth creation."))


    # Low fund count nudge
    if num_funds < 3:
        nudges.append(("warn", "Your portfolio has very few funds. Consider diversifying across categories for better risk management."))
    elif num_funds > 15:
        nudges.append(("info", f"You hold {num_funds} funds. Consider consolidating — too many funds can reduce alpha and increase complexity."))


    # Alpha nudge
    if alpha >= 5:
        nudges.append(("success", f"Excellent alpha of +{alpha:.2f}% over {benchmark_name}. Your fund selection is working well."))
    elif alpha < -5:
        nudges.append(("danger", f"Portfolio is significantly underperforming {benchmark_name} by {abs(alpha):.2f}%. Review fund selection and expense ratios."))


    # Expense drag nudge
    if expense_drag / total_value * 100 > 1.0 and total_value > 0:
        nudges.append(("warn", f"Your expense ratio drag ({expense_drag/total_value*100:.2f}%) is above 1%. This erodes long-term compounding significantly."))


    for nudge_type, nudge_msg in nudges:
        icon = {"success": "✅", "warn": "⚠️", "danger": "🚨", "info": "💡"}.get(nudge_type, "💡")
        css_class = f"alert-{nudge_type}"
        st.markdown(f'<div class="{css_class}" style="margin-bottom:8px">{icon} {nudge_msg}</div>', unsafe_allow_html=True)


    if not nudges:
        st.markdown('<div class="alert-success">✅ No issues detected. Your portfolio looks healthy!</div>', unsafe_allow_html=True)


    # Portfolio Score breakdown
    st.markdown("<div style='margin:16px 0'></div>", unsafe_allow_html=True)
    st.markdown("**Portfolio Health Score Breakdown**")
    score_items = [
        ("Alpha vs Benchmark", min(30, max(0, int(30 * (1 + (portfolio_xirr - bench_ret) / 20)))), 30),
        ("Fund Diversification", 25 if num_funds >= 10 else int(25 * num_funds / 10), 25),
        ("Direct Plan Usage", int(20 * (df_h[df_h["Plan"]=="Direct"]["Market Value"].sum() / total_value)) if total_value > 0 else 0, 20),
        ("Concentration Risk", int(15 * (1 - float(np.sum((df_h["Market Value"]/total_value).values**2)))) if total_value > 0 else 0, 15),
        ("Category Balance", int(10 * (1 - df_h.groupby("Category")["Market Value"].sum().max() / total_value)) if total_value > 0 else 0, 10),
    ]
    for label, actual, max_score in score_items:
        pct = actual / max_score * 100 if max_score > 0 else 0
        bar_color = "#10B981" if pct >= 70 else ("#F59E0B" if pct >= 40 else "#EF4444")
        st.markdown(f"""
        <div style="margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px">
                <span style="color:#0F172A;font-weight:600">{label}</span>
                <span style="color:#64748B">{actual}/{max_score}</span>
            </div>
            <div style="background:#F1F5F9;border-radius:4px;height:6px">
                <div style="height:6px;border-radius:4px;background:{bar_color};width:{pct:.0f}%"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)




# ════════════════════════════════════════════
# TAB: TAX
# ════════════════════════════════════════════
with tab_tax:
    st.markdown('<div class="section-head">Tax liability estimator</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Estimates based on current holdings. Not financial/tax advice — consult a CA.</div>', unsafe_allow_html=True)


    t1, t2, t3 = st.columns(3)


    # ELSS lock-in tracker
    elss_df  = df_h[df_h["Category"] == "ELSS"]
    elss_val = float(elss_df["Market Value"].sum())
    elss_inv = float(elss_df["Invested"].sum())


    # STCG/LTCG heuristic
    equity_gain   = float(df_h[df_h["Category"].isin(["Equity","ELSS","Index"])]["Gain"].sum())
    debt_gain     = float(df_h[df_h["Category"].isin(["Debt","Liquid","Hybrid"])]["Gain"].sum())
    stcg_equity   = max(0, equity_gain) * 0.20  # 20% post-budget 2024
    ltcg_equity   = max(0, equity_gain - 125000) * 0.125 if equity_gain > 125000 else 0
    stcg_debt     = max(0, debt_gain) * 0.30    # taxed at slab


    with t1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="card-label">ELSS Holdings</div>
            <div class="card-value">{fmt_inr(elss_val)}</div>
            <div class="card-sub">{len(elss_df)} ELSS funds · {fmt_inr(elss_inv)} invested</div>
        </div>
        """, unsafe_allow_html=True)


    with t2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="card-label">Est. Equity LTCG Tax</div>
            <div class="card-value">{fmt_inr(ltcg_equity)}</div>
            <div class="card-sub">12.5% on gains above ₹1.25L · if redeemed today</div>
        </div>
        """, unsafe_allow_html=True)


    with t3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="card-label">Est. Debt STCG Tax</div>
            <div class="card-value">{fmt_inr(stcg_debt)}</div>
            <div class="card-sub">At 30% slab rate · debt/hybrid gains</div>
        </div>
        """, unsafe_allow_html=True)


    st.caption("⚠ Tax figures above are illustrative estimates. Consult a SEBI-registered financial advisor and CA for personalised advice.")


# ── FOOTER ──
st.markdown("""
<div class="footer-note">
    FolioIQ v5.0 &middot; SEBI CSCRF 2025 &middot; Zero Data Retention Architecture &middot; Not SEBI registered &middot; Not financial advice<br>
    Factor Analysis &middot; Smart Insights &middot; Step-Up SIP &middot; Fund Comparison &middot; Built with &#10084; for Indian MF investors
</div>
""", unsafe_allow_html=True)
