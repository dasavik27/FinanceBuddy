"""
domains/equity/sector_map.py

Static NSE sector and industry mapping for Nifty 500 stocks.
Used for sector allocation analytics and portfolio impact calculations.
"""

# Maps NSE stock symbol -> (sector, industry)
# Covers Nifty 500 + major liquid stocks
SECTOR_MAP: dict[str, tuple[str, str]] = {
    # ── Financials ───────────────────────────────────────────────────────────
    "HDFCBANK": ("Financials", "Banks"),
    "ICICIBANK": ("Financials", "Banks"),
    "KOTAKBANK": ("Financials", "Banks"),
    "AXISBANK": ("Financials", "Banks"),
    "SBIN": ("Financials", "Banks"),
    "BANKBARODA": ("Financials", "Banks"),
    "PNB": ("Financials", "Banks"),
    "CANBK": ("Financials", "Banks"),
    "UNIONBANK": ("Financials", "Banks"),
    "INDUSINDBK": ("Financials", "Banks"),
    "FEDERALBNK": ("Financials", "Banks"),
    "IDFCFIRSTB": ("Financials", "Banks"),
    "YESBANK": ("Financials", "Banks"),
    "RBLBANK": ("Financials", "Banks"),
    "AUBANK": ("Financials", "Banks"),
    "BANDHANBNK": ("Financials", "Banks"),
    "BAJFINANCE": ("Financials", "NBFC"),
    "BAJAJFINSV": ("Financials", "NBFC"),
    "CHOLAFIN": ("Financials", "NBFC"),
    "MUTHOOTFIN": ("Financials", "NBFC"),
    "M&MFIN": ("Financials", "NBFC"),
    "SHRIRAMFIN": ("Financials", "NBFC"),
    "HDFCLIFE": ("Financials", "Insurance"),
    "SBILIFE": ("Financials", "Insurance"),
    "ICICIGI": ("Financials", "Insurance"),
    "ICICIPRULI": ("Financials", "Insurance"),
    "LICI": ("Financials", "Insurance"),
    "NIACL": ("Financials", "Insurance"),
    "STARHEALTH": ("Financials", "Insurance"),
    "BSE": ("Financials", "Capital Markets"),
    "NSE": ("Financials", "Capital Markets"),
    "ANGELONE": ("Financials", "Capital Markets"),
    "CDSL": ("Financials", "Capital Markets"),
    "CAMS": ("Financials", "Capital Markets"),
    "HDFC AMC": ("Financials", "Asset Management"),
    "HDFCAMC": ("Financials", "Asset Management"),
    "NAM-INDIA": ("Financials", "Asset Management"),
    "360ONE": ("Financials", "Asset Management"),

    # ── Information Technology ───────────────────────────────────────────────
    "TCS": ("Information Technology", "IT Services"),
    "INFY": ("Information Technology", "IT Services"),
    "WIPRO": ("Information Technology", "IT Services"),
    "HCLTECH": ("Information Technology", "IT Services"),
    "TECHM": ("Information Technology", "IT Services"),
    "LTIM": ("Information Technology", "IT Services"),
    "MPHASIS": ("Information Technology", "IT Services"),
    "COFORGE": ("Information Technology", "IT Services"),
    "PERSISTENT": ("Information Technology", "IT Services"),
    "OFSS": ("Information Technology", "IT Services"),
    "KPITTECH": ("Information Technology", "IT Services"),
    "HEXAWARE": ("Information Technology", "IT Services"),
    "ZENSARTECH": ("Information Technology", "IT Services"),
    "NIITTECH": ("Information Technology", "IT Services"),

    # ── Energy ───────────────────────────────────────────────────────────────
    "RELIANCE": ("Energy", "Oil & Gas"),
    "ONGC": ("Energy", "Oil & Gas"),
    "BPCL": ("Energy", "Oil & Gas"),
    "IOC": ("Energy", "Oil & Gas"),
    "HINDPETRO": ("Energy", "Oil & Gas"),
    "PETRONET": ("Energy", "Oil & Gas"),
    "GAIL": ("Energy", "Oil & Gas"),
    "OIL": ("Energy", "Oil & Gas"),
    "MGL": ("Energy", "Oil & Gas"),
    "IGL": ("Energy", "Oil & Gas"),
    "NTPC": ("Energy", "Power"),
    "POWERGRID": ("Energy", "Power"),
    "TATAPOWER": ("Energy", "Power"),
    "ADANIGREEN": ("Energy", "Renewable Energy"),
    "ADANIPOWER": ("Energy", "Power"),
    "CESC": ("Energy", "Power"),
    "COALINDIA": ("Energy", "Coal"),

    # ── Consumer Staples ─────────────────────────────────────────────────────
    "HINDUNILVR": ("Consumer Staples", "FMCG"),
    "ITC": ("Consumer Staples", "FMCG"),
    "NESTLEIND": ("Consumer Staples", "FMCG"),
    "BRITANNIA": ("Consumer Staples", "FMCG"),
    "DABUR": ("Consumer Staples", "FMCG"),
    "MARICO": ("Consumer Staples", "FMCG"),
    "GODREJCP": ("Consumer Staples", "FMCG"),
    "COLPAL": ("Consumer Staples", "FMCG"),
    "EMAMILTD": ("Consumer Staples", "FMCG"),
    "VBL": ("Consumer Staples", "Beverages"),
    "UBL": ("Consumer Staples", "Beverages"),
    "MCDOWELL-N": ("Consumer Staples", "Beverages"),
    "TATACONSUM": ("Consumer Staples", "FMCG"),
    "PGHH": ("Consumer Staples", "FMCG"),

    # ── Consumer Discretionary ───────────────────────────────────────────────
    "TITAN": ("Consumer Discretionary", "Retail"),
    "TRENT": ("Consumer Discretionary", "Retail"),
    "DMART": ("Consumer Discretionary", "Retail"),
    "NYKAA": ("Consumer Discretionary", "Retail"),
    "ZOMATO": ("Consumer Discretionary", "Food Services"),
    "SWIGGY": ("Consumer Discretionary", "Food Services"),
    "BATA": ("Consumer Discretionary", "Footwear"),
    "RELAXO": ("Consumer Discretionary", "Footwear"),
    "WHIRLPOOL": ("Consumer Discretionary", "Consumer Electronics"),
    "BLUESTARCO": ("Consumer Discretionary", "Consumer Electronics"),
    "VOLTAS": ("Consumer Discretionary", "Consumer Electronics"),
    "HAVELLS": ("Consumer Discretionary", "Consumer Electronics"),
    "CROMPTON": ("Consumer Discretionary", "Consumer Electronics"),
    "VAIBHAVGBL": ("Consumer Discretionary", "Jewellery"),
    "KALYANKJIL": ("Consumer Discretionary", "Jewellery"),
    "RAYMOND": ("Consumer Discretionary", "Textiles"),
    "MANYAVAR": ("Consumer Discretionary", "Textiles"),
    "PAGEIND": ("Consumer Discretionary", "Textiles"),
    "MARUTI": ("Consumer Discretionary", "Automobiles"),
    "TATAMOTORS": ("Consumer Discretionary", "Automobiles"),
    "M&M": ("Consumer Discretionary", "Automobiles"),
    "BAJAJ-AUTO": ("Consumer Discretionary", "Automobiles"),
    "HEROMOTOCO": ("Consumer Discretionary", "Automobiles"),
    "EICHERMOT": ("Consumer Discretionary", "Automobiles"),
    "TVSMOTOR": ("Consumer Discretionary", "Automobiles"),
    "ASHOKLEY": ("Consumer Discretionary", "Automobiles"),
    "TIINDIA": ("Consumer Discretionary", "Automobiles"),
    "MOTHERSON": ("Consumer Discretionary", "Auto Ancillaries"),
    "BOSCHLTD": ("Consumer Discretionary", "Auto Ancillaries"),
    "EXIDEIND": ("Consumer Discretionary", "Auto Ancillaries"),
    "AMARON": ("Consumer Discretionary", "Auto Ancillaries"),
    "BALKRISIND": ("Consumer Discretionary", "Auto Ancillaries"),
    "MRF": ("Consumer Discretionary", "Auto Ancillaries"),
    "APOLLOTYRE": ("Consumer Discretionary", "Auto Ancillaries"),

    # ── Healthcare ───────────────────────────────────────────────────────────
    "SUNPHARMA": ("Healthcare", "Pharmaceuticals"),
    "CIPLA": ("Healthcare", "Pharmaceuticals"),
    "DRREDDY": ("Healthcare", "Pharmaceuticals"),
    "DIVISLAB": ("Healthcare", "Pharmaceuticals"),
    "BIOCON": ("Healthcare", "Biopharmaceuticals"),
    "LUPIN": ("Healthcare", "Pharmaceuticals"),
    "AUROPHARMA": ("Healthcare", "Pharmaceuticals"),
    "TORNTPHARM": ("Healthcare", "Pharmaceuticals"),
    "ABBOTINDIA": ("Healthcare", "Pharmaceuticals"),
    "PFIZER": ("Healthcare", "Pharmaceuticals"),
    "GLAXO": ("Healthcare", "Pharmaceuticals"),
    "ALKEM": ("Healthcare", "Pharmaceuticals"),
    "APOLLOHOSP": ("Healthcare", "Hospitals"),
    "FORTIS": ("Healthcare", "Hospitals"),
    "MAXHEALTH": ("Healthcare", "Hospitals"),
    "NARAYANAHRD": ("Healthcare", "Hospitals"),
    "METROPOLIS": ("Healthcare", "Diagnostics"),
    "DRLA": ("Healthcare", "Diagnostics"),
    "THYROCARE": ("Healthcare", "Diagnostics"),

    # ── Industrials ──────────────────────────────────────────────────────────
    "LT": ("Industrials", "Engineering & Construction"),
    "SIEMENS": ("Industrials", "Engineering"),
    "ABB": ("Industrials", "Engineering"),
    "BHEL": ("Industrials", "Engineering"),
    "BEL": ("Industrials", "Defence"),
    "HAL": ("Industrials", "Defence"),
    "COCHINSHIP": ("Industrials", "Shipbuilding"),
    "GRINDWELL": ("Industrials", "Engineering"),
    "CUMMINSIND": ("Industrials", "Engineering"),
    "THERMAX": ("Industrials", "Engineering"),
    "APLAPOLLO": ("Industrials", "Steel"),
    "TATAELXSI": ("Industrials", "Engineering"),
    "SOLARINDS": ("Industrials", "Defence"),
    "DELHIVERY": ("Industrials", "Logistics"),
    "BLUEDART": ("Industrials", "Logistics"),
    "CONCOR": ("Industrials", "Logistics"),

    # ── Materials ────────────────────────────────────────────────────────────
    "TATASTEEL": ("Materials", "Steel"),
    "JSWSTEEL": ("Materials", "Steel"),
    "SAIL": ("Materials", "Steel"),
    "HINDALCO": ("Materials", "Metals"),
    "VEDL": ("Materials", "Metals"),
    "NMDC": ("Materials", "Mining"),
    "HINDCOPPER": ("Materials", "Metals"),
    "NATIONALUM": ("Materials", "Aluminium"),
    "ULTRATECH": ("Materials", "Cement"),
    "SHREECEM": ("Materials", "Cement"),
    "AMBUJACEM": ("Materials", "Cement"),
    "ACC": ("Materials", "Cement"),
    "JKCEMENT": ("Materials", "Cement"),
    "RAMCOCEM": ("Materials", "Cement"),
    "PIDILITIND": ("Materials", "Chemicals"),
    "DEEPAKNTR": ("Materials", "Chemicals"),
    "AAVAS": ("Materials", "Chemicals"),
    "NAVINFLUOR": ("Materials", "Chemicals"),
    "SRF": ("Materials", "Chemicals"),
    "ATUL": ("Materials", "Chemicals"),
    "ASIANPAINT": ("Materials", "Paints"),
    "BERGEPAINT": ("Materials", "Paints"),
    "KANSAINER": ("Materials", "Paints"),

    # ── Communication Services ───────────────────────────────────────────────
    "BHARTIARTL": ("Communication Services", "Telecom"),
    "IDEA": ("Communication Services", "Telecom"),
    "TTML": ("Communication Services", "Telecom"),
    "INDUSTOWER": ("Communication Services", "Telecom Infrastructure"),
    "ZEEL": ("Communication Services", "Media"),
    "SUNTV": ("Communication Services", "Media"),
    "PVRINOX": ("Communication Services", "Entertainment"),
    "INDIGRID": ("Communication Services", "Infrastructure"),

    # ── Real Estate ──────────────────────────────────────────────────────────
    "DLF": ("Real Estate", "Real Estate"),
    "GODREJPROP": ("Real Estate", "Real Estate"),
    "OBEROIRLTY": ("Real Estate", "Real Estate"),
    "PRESTIGE": ("Real Estate", "Real Estate"),
    "PHOENIXLTD": ("Real Estate", "Real Estate"),
    "BRIGADE": ("Real Estate", "Real Estate"),
    "SOBHA": ("Real Estate", "Real Estate"),

    # ── Utilities ────────────────────────────────────────────────────────────
    "ADANIPORTS": ("Utilities", "Port & Logistics"),
    "GUJARATGAS": ("Utilities", "Gas Distribution"),
}

# Default sector when stock is not in the map
DEFAULT_SECTOR = "Others"
DEFAULT_INDUSTRY = "Miscellaneous"


def get_sector(symbol: str) -> tuple[str, str]:
    """Return (sector, industry) for a given NSE symbol. Defaults gracefully."""
    clean = symbol.upper().strip().replace("-EQ", "").replace(" ", "")
    entry = SECTOR_MAP.get(clean)
    if entry:
        return entry
    return (DEFAULT_SECTOR, DEFAULT_INDUSTRY)


def get_all_sectors() -> list[str]:
    """Distinct list of all sectors in the map."""
    return sorted(set(v[0] for v in SECTOR_MAP.values()))
