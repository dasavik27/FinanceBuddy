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
# Set via environment variable 'FINANCEBUDDY_CACHE_TTL' (Default: 60 minutes).
# A value <= 0 triggers real-time direct fetching across all network providers.
def _get_ttl_from_db():
    """
    The operator-configured cache TTL, falling back to the environment.

    Read lazily rather than at import. It used to open the database at module import
    time, which was survivable against a local file and is not against a pooled
    network one: importing this module would build a connection pool as a side
    effect, and any blip made the whole application fail to start over a tunable
    that has a perfectly good default.
    """
    from shared import db

    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'cache_ttl'"
            ).fetchone()
            if row:
                return int(row[0])
    except Exception:
        pass
    return int(os.getenv("FINANCEBUDDY_CACHE_TTL", 60))


CACHE_TTL_MINUTES = int(os.getenv("FINANCEBUDDY_CACHE_TTL", 60))


def refresh_cache_ttl() -> int:
    """Reload the TTL from the database. Called at startup, and after /market/config."""
    global CACHE_TTL_MINUTES
    CACHE_TTL_MINUTES = _get_ttl_from_db()
    return CACHE_TTL_MINUTES

# Absolute directory path for disk-backed JSON cache storage.
#
# Anchored to this file rather than os.getcwd(): a CWD-relative path meant the cache
# location depended on where the process was launched from, so running from the repo
# root and from backend/ produced two independent caches that never shared a hit.
# Override with FINANCEBUDDY_CACHE_DIR when the app directory is read-only.
CACHE_DIR = os.getenv(
    "FINANCEBUDDY_CACHE_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".cache")),
)
os.makedirs(CACHE_DIR, exist_ok=True)

# ── Macroeconomic & Market Index Definitions ──────────────────────────────
BENCHMARKS = {
    "Nifty 50": "120716",
    "Nifty Next 50": "120711",
    "Nifty Midcap 150": "147726",
    "Nifty Smallcap 250": "147724",
    "Nifty 500": "147702",
    "Nifty Bank": "153432",
    "S&P 500": "^GSPC", # S&P 500 remains Yahoo as Indian proxies stop in 2022
    "Hybrid 50/50": "HYBRID_50_50",
    "Gold": "118272"
}

# ── Asset Class & Market Capitalization Mapping ───────────────────────────
# Maps fund categorization to precise Total Return Indices (TRI) for alpha computation
FUND_BENCH_BY_CAT = {
    "Equity":     ("120716", "Nifty 50 TRI"),
    "Debt":       ("119598", "CRISIL Composite Bond"),
    "Liquid":     ("119596", "CRISIL Liquid Index"),
    "Hybrid":     ("HYBRID_50_50", "Hybrid 50/50 TRI"),
    "Index":      ("120716", "Nifty 50 TRI"),
    "Commodities": ("118272", "Gold Spot TRI"),
    "International": ("^GSPC", "S&P 500 TRI")
}

FUND_BENCH_BY_CAP = {
    "Large Cap":       ("120716", "Nifty 50 TRI"),
    "Mid Cap":         ("147726", "Nifty Midcap 150 TRI"),
    "Small Cap":       ("147724", "Nifty Smallcap 250 TRI"),
    "Flexi Cap":       ("147702", "Nifty 500 TRI"),
    "Multi Cap":       ("147702", "Nifty 500 TRI"),
    "Large & Mid Cap": ("147702", "Nifty 500 TRI"),
    "Focused":         ("147702", "Nifty 500 TRI"),
    "Value":           ("147702", "Nifty 500 TRI"),
    "Contra":          ("147702", "Nifty 500 TRI"),
    "Thematic":        ("147702", "Nifty 500 TRI")
}

# ── Institutional Taxation Parameters (Budget 2024 Slabs) ─────────────────
# Re-exported from shared/reference/statutory.py, which is the single source of truth
# for capital-gains law across every domain that computes it.
#
# This used to build the table itself by opening
# `../domains/tax_expert/tax_rules.json` - the shared layer reaching into a domain's
# package directory, which quietly made the Mutual Funds tax-lot engine undeployable
# without the Tax Expert domain's files on disk. Neither domain owns Indian tax law,
# so it now lives in shared/reference and both read from there.
#
# Kept as a re-export rather than deleted: domains/mutual_funds imports
# `from shared.config import ... TAX_RATES` in two modules, and this is the stable
# name they already use.
from shared.reference.statutory import TAX_RATES  # noqa: E402,F401

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
