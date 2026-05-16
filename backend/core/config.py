"""
core/config.py

Institutional Portfolio Architecture Configuration Matrix
========================================================
Centralized parameter repository governing benchmark mappings, macroeconomic assumptions,
taxation slabs (Budget 2024 compliance), UI color tokens, and risk evaluation thresholds.
Provides strict mathematical bounds for mutual fund analytics across the entire backend.
"""
import os

# ── Caching & Performance Architecture ────────────────────────────────────

# Time-To-Live (TTL) for in-memory and disk persistence layers (NAV & CAS Records)
# Set via environment variable 'FOLIOIQ_CACHE_TTL' (Default: 60 minutes).
# A value <= 0 triggers real-time direct fetching across all network providers.
CACHE_TTL_MINUTES = int(os.getenv("FOLIOIQ_CACHE_TTL", 60))

# Absolute directory path for disk-backed JSON cache storage
CACHE_DIR = os.path.join(os.getcwd(), ".cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ── Macroeconomic & Market Index Definitions ──────────────────────────────
BENCHMARKS = {
    "Nifty 50": "^NSEI",
    "Nifty Next 50": "^NSMIDCP", # Proxy for junior large-cap equity
    "Nifty Midcap 150": "NIFTYMIDCAP150.NS",
    "Nifty Smallcap 250": "^CNXSC",
    "Nifty 500": "^CRSLDX",
    "Nifty Bank": "^NSEBANK",
    "S&P 500": "^GSPC",
    "Hybrid 50/50": "HYBRID_50_50",
    "Gold": "GC=F"
}

# ── Asset Class & Market Capitalization Mapping ───────────────────────────
# Maps fund categorization to precise Total Return Indices (TRI) for alpha computation
FUND_BENCH_BY_CAT = {
    "Equity":     ("^NSEI", "Nifty 50 TRI"),
    "Debt":       ("LICNETFGSC.NS", "CRISIL Composite Bond"),
    "Liquid":     ("LICNETFGSC.NS", "CRISIL Liquid Index"),
    "Hybrid":     ("HYBRID_50_50", "Hybrid 50/50 TRI"),
    "Index":      ("^NSEI", "Nifty 50 TRI"),
    "Commodities": ("GC=F", "Gold Spot TRI"),
    "International": ("^GSPC", "S&P 500 TRI")
}

FUND_BENCH_BY_CAP = {
    "Large Cap":       ("^NSEI", "Nifty 50 TRI"),
    "Mid Cap":         ("NIFTYMIDCAP150.NS", "Nifty Midcap 150 TRI"),
    "Small Cap":       ("^CNXSC", "Nifty Smallcap 250 TRI"),
    "Flexi Cap":       ("^CRSLDX", "Nifty 500 TRI"),
    "Multi Cap":       ("^CRSLDX", "Nifty 500 TRI"),
    "Large & Mid Cap": ("^CRSLDX", "Nifty 500 TRI"),
    "Focused":         ("^NSEI", "Nifty 50 TRI"),
    "Value":           ("^NSEI", "Nifty 50 TRI"),
    "Contra":          ("^NSEI", "Nifty 50 TRI"),
    "Thematic":        ("^NSEI", "Nifty 50 TRI")
}

# ── Institutional Taxation Parameters (Budget 2024 Slabs) ─────────────────
TAX_RATES = {
    "LTCG_EQUITY": 0.125,      # 12.5% Long Term Capital Gains on Equity (>12M)
    "STCG_EQUITY": 0.20,       # 20.0% Short Term Capital Gains on Equity (<12M)
    "LTCG_EXEMPTION": 125000,  # ₹1.25 Lakh annual tax-exempt threshold
    "STCG_DEBT": 0.20          # Marginal tax slab proxy for Debt instruments
}

# ── Design Tokens & Visual Hierarchy ──────────────────────────────────────
CATEGORY_COLORS = {
    "Equity": "#4F46E5",
    "ELSS": "#8B5CF6",
    "Index": "#06B6D4",
    "Debt": "#10B981",
    "Liquid": "#10B981",
    "Hybrid": "#EC4899",
    "Commodities": "#FACC15",
    "International": "#3B82F6",
    "Other": "#94A3B8"
}

# ── Quantitative Risk Classifications ─────────────────────────────────────
RISK_LABEL = {
    "LOW": "Low",
    "MODERATE": "Moderate",
    "HIGH": "High",
    "VERY HIGH": "Very High"
}

# Peer comparison memory space (Populated dynamically during runtime)
PEER_UNIVERSE = {}

# ── Valuation & Macroeconomic Assumptions ─────────────────────────────────
# Typical Expense Ratio (TER) baseline boundaries (Direct Plan norms)
EXP_RATIO_BANDS = {
    "Equity": (0.50, 1.20),
    "Debt": (0.10, 0.40),
    "Liquid": (0.10, 0.20),
    "ELSS": (0.40, 1.00)
}

# Sectoral Price-to-Earnings (P/E) proxy benchmarks
PE_ESTIMATES = {
    "Large Cap": 24.5,
    "Mid Cap": 32.0,
    "Small Cap": 38.5,
    "Default": 25.0
}

# Sectoral Price-to-Book (P/B) proxy benchmarks
PB_ESTIMATES = {
    "Large Cap": 3.8,
    "Mid Cap": 4.5,
    "Small Cap": 5.2,
    "Default": 3.5
}

# Fixed Income proxy metrics: (Modified Duration in Years, Credit Quality Rating, YTM %)
DEBT_METRICS_MAP = {
    "Liquid": (0.1, "AAA", 6.8),
    "Gilt": (6.5, "SOV", 7.2),
    "Banking & PSU": (2.5, "AAA", 7.5),
    "Default": (3.0, "AA", 7.5)
}

# Horizon day mappings for performance evaluations
PERIOD_MAP = {
    "1M": 30,
    "3M": 91,
    "6M": 182,
    "1Y": 365,
    "3Y": 1095,
    "5Y": 1825,
    "ALL": 9999
}

# Goal alignment mapping for wealth planning nudges
GOAL_TIMELINE = {
    "Equity":     ("Long Term Growth", "#6366F1", "10+ Years"),
    "ELSS":       ("Tax Saving", "#8B5CF6", "3 Years Lock-in"),
    "Mid Cap":    ("Wealth Creation", "#F59E0B", "7+ Years"),
    "Small Cap":  ("Aggressive Wealth", "#EC4899", "10+ Years"),
    "Liquid":     ("Emergency Fund", "#10B981", "Instant Access"),
    "Debt":       ("Stability", "#10B981", "3+ Years"),
    "Index":      ("Passive Growth", "#06B6D4", "10+ Years")
}

def get_standard_category(cat: str) -> str:
    """
    Standardizes granular mutual fund scheme nomenclature into top-level asset classes.
    Ensures robust roll-ups for multi-asset allocation modeling and rebalancing matrices.
    """
    c = str(cat).upper()
    if any(x in c for x in ["INTERNATIONAL", "GLOBAL", "WORLD", "US ", "NASDAQ", "OVERSEAS"]): return "Global"
    if any(x in c for x in ["HYBRID", "BALANCED", "ASSET ALLOCATOR", "MULTI ASSET", "EQUITY SAVINGS"]): return "Hybrid"
    if any(x in c for x in ["DEBT", "GILT", "BOND", "FIXED INCOME", "LIQUID", "OVERNIGHT", "MONEY MARKET", "CASH"]): return "Debt"
    if any(x in c for x in ["EQUITY", "ELSS", "VALUE", "GROWTH", "CAP", "INDEX", "ETF", "THEMATIC", "SECTORAL", "INFRA", "TECH", "PHARMA", "BANKING", "ARBITRAGE"]): return "Equity"
    return "Other"

def classify_er(er: float, category: str) -> str:
    """
    Evaluates fund expense ratio efficiency against category-specific boundary bands.
    Categorizes the drag as 'Low', 'Moderate', or 'High'.
    """
    if er is None: return "Unknown"
    lo, hi = EXP_RATIO_BANDS.get(category, (0.50, 1.20))
    if er <= lo: return "Low"
    if er <= hi: return "Moderate"
    return "High"

TEST_PASSWORD = os.getenv("FOLIOIQ_TEST_PASSWORD", "BBPPD9383N")
