"""
FolioIQ Configuration
Constants, benchmarks, and configuration settings
"""

# Benchmark mappings
BENCHMARKS = {
    "Nifty 50":      "^NSEI",
    "Sensex":        "^BSESN",
    "Nifty Midcap 150": "^NSMIDCP",
    "Nifty Smallcap 250": "^NSSMLCP",
    "Nifty Next 50": "^NSMIDCP",
}

# Time period mapping
PERIOD_MAP = {
    "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "3Y": 1095, "5Y": 1825, "All": 9999
}

# Category colors
CATEGORY_COLORS = {
    "Equity": "#3B82F6", "Debt": "#10B981", "Hybrid": "#F59E0B",
    "ELSS": "#8B5CF6", "Liquid": "#06B6D4", "Index": "#6366F1",
    "FOF": "#F43F5E", "Other": "#94A3B8"
}

# Per-fund benchmark mapping
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

# Risk tiers
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

# Maximum drawdown estimates
MAX_DD_ESTIMATE = {
    "Equity":45, "ELSS":42, "Index":38, "Hybrid":28,
    "FOF":38, "Debt":10, "Liquid":2, "Other":22,
}

# Sector colors
SECTOR_COLORS = [
    "#3B82F6","#10B981","#F59E0B","#8B5CF6","#F43F5E",
    "#06B6D4","#6366F1","#EC4899","#14B8A6","#F97316"
]

# Expense ratios (Direct / Regular)
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

# Sector detection keywords
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
    "Diversified": [],
}

# App metadata
APP_TITLE = "FolioIQ · MF Portfolio Intelligence"
APP_ICON = "📈"
APP_DESCRIPTION = "Institutional-grade mutual fund portfolio analytics"
APP_VERSION = "5.0"
FOOTER_TEXT = f"FolioIQ v{APP_VERSION} · SEBI CSCRF 2025 · Zero Data Retention Architecture"
