"""Scan universes for the research engine (no MarketSmith lists)."""

from __future__ import annotations

# Current Nifty 50 constituents (maintenance: refresh periodically).
NIFTY_50: list[str] = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO",
    "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY",
    "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

# Broader liquid set for research scans (Nifty 50 + common mid/large names).
LIQUID_100: list[str] = NIFTY_50 + [
    "ABB", "ABBOTINDIA", "ATGL", "AUROPHARMA", "BANKBARODA",
    "BHEL", "BIOCON", "BOSCHLTD", "BRITANNIA", "CANBK",
    "CHOLAFIN", "COLPAL", "CONCOR", "CUMMINSIND", "DABUR",
    "DALBHARAT", "DEEPAKNTR", "DIVISLAB", "DIXON", "DLF",
    "DMART", "FEDERALBNK", "GAIL", "GODREJCP", "HAL",
    "HAVELLS", "HDFCAMC", "ICICIGI", "ICICIPRULI", "IDFCFIRSTB",
    "INDIGO", "INDUSTOWER", "IOC", "IRCTC", "JINDALSTEL",
    "JUBLFOOD", "LUPIN", "MFSL", "MOTHERSON", "MPHASIS",
    "MRF", "MUTHOOTFIN", "NAUKRI", "OFSS", "PAGEIND",
    "PERSISTENT", "PETRONET", "PIDILITIND", "PIIND", "POLYCAB",
    "PVRINOX", "SBICARD", "SIEMENS", "SRF", "TORNTPHARM",
    "TVSMOTOR", "UBL", "UNITDSPR", "VEDL", "VOLTAS",
    "YESBANK", "ZOMATO", "ZYDUSLIFE",
]


def resolve_universe(name: str, symbols: list[str] | None = None) -> list[str]:
    """Return a de-duplicated symbol list for a named universe or custom symbols."""
    if symbols:
        out: list[str] = []
        seen: set[str] = set()
        for raw in symbols:
            s = str(raw).upper().strip().replace("-EQ", "")
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    key = (name or "nifty50").strip().lower()
    if key in ("nifty50", "nifty_50", "n50"):
        return list(NIFTY_50)
    if key in ("liquid", "liquid100", "liquid_100"):
        return list(dict.fromkeys(LIQUID_100))
    return list(NIFTY_50)
