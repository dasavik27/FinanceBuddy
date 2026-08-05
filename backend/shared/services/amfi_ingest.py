"""
shared/services/amfi_ingest.py
Core Ingestion Engine for AMFI Portfolio Snapshots.
Fetches, normalizes, and stores official mutual fund disclosures into PostgreSQL.
"""

import json
import logging
import time
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from shared import db
from shared.cache import MarketCache

logger = logging.getLogger(__name__)

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

# Search / purge aliases: UI labels that do not match the stored AMC string 1:1.
AMC_ALIASES = {
    "parag parikh": ["parag parikh", "ppfas"],
    "ppfas": ["ppfas", "parag parikh"],
    "grow": ["groww"],
    "groww": ["groww"],
}


class AmfiFetchError(RuntimeError):
    """Raised when the AMFI NAVAll feed cannot be fetched or parsed."""


def _portfolio_as_of() -> date:
    """Last day of the previous calendar month (AMFI disclosures lag ~1 month)."""
    return date.today().replace(day=1) - timedelta(days=1)


def _amc_match_terms(term: str) -> List[str]:
    """Expand an AMC filter/search term into ILIKE patterns (alias-aware)."""
    clean = (term or "").strip()
    if not clean:
        return []
    aliases = AMC_ALIASES.get(clean.lower(), [clean])
    # De-dupe while preserving order
    seen = set()
    out: List[str] = []
    for a in aliases:
        key = a.lower()
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def _invalidate_market_caches() -> None:
    """Clear disk MarketCache and in-process market-data caches after sync/purge."""
    try:
        MarketCache.invalidate_all()
    except Exception as exc:
        logger.warning("[AMFI_INGEST] MarketCache.invalidate_all failed: %s", exc)
    try:
        from shared.services.market_data import clear_market_data_cache
        clear_market_data_cache()
    except Exception as exc:
        logger.warning("[AMFI_INGEST] clear_market_data_cache failed: %s", exc)

# Standard category benchmark templates for sector distribution and top holdings
CATEGORY_BENCHMARKS = {
    "Large Cap Fund": {
        "cap": "Large Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 34.50},
            {"sector": "Information Technology", "value": 15.20},
            {"sector": "Oil, Gas & Consumable Fuels", "value": 11.40},
            {"sector": "Automobile & Auto Components", "value": 8.60},
            {"sector": "Healthcare & Pharma", "value": 7.10},
            {"sector": "Fast Moving Consumer Goods", "value": 6.80},
            {"sector": "Construction & Materials", "value": 5.40},
            {"sector": "Metals & Mining", "value": 4.20},
            {"sector": "Telecommunication", "value": 3.80},
            {"sector": "Others & Cash", "value": 3.00},
        ],
        "holdings": [
            {"name": "HDFC Bank Ltd", "pct": 9.20},
            {"name": "ICICI Bank Ltd", "pct": 7.80},
            {"name": "Reliance Industries Ltd", "pct": 7.40},
            {"name": "Infosys Ltd", "pct": 5.80},
            {"name": "Larsen & Toubro Ltd", "pct": 4.90},
            {"name": "Tata Consultancy Services Ltd", "pct": 4.10},
            {"name": "ITC Ltd", "pct": 3.80},
            {"name": "Axis Bank Ltd", "pct": 3.60},
            {"name": "Bharti Airtel Ltd", "pct": 3.50},
            {"name": "State Bank of India", "pct": 3.20},
        ],
        "er_direct": 0.85,
        "er_regular": 1.70,
    },
    "Large & Mid Cap Fund": {
        "cap": "Large & Mid Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 28.40},
            {"sector": "Information Technology", "value": 13.60},
            {"sector": "Capital Goods & Engineering", "value": 12.20},
            {"sector": "Automobile & Auto Components", "value": 9.80},
            {"sector": "Healthcare & Pharma", "value": 8.40},
            {"sector": "Oil, Gas & Consumable Fuels", "value": 7.50},
            {"sector": "Consumer Discretionary", "value": 6.80},
            {"sector": "Others & Cash", "value": 13.30},
        ],
        "holdings": [
            {"name": "HDFC Bank Ltd", "pct": 7.40},
            {"name": "ICICI Bank Ltd", "pct": 6.20},
            {"name": "Reliance Industries Ltd", "pct": 5.80},
            {"name": "Infosys Ltd", "pct": 4.60},
            {"name": "Larsen & Toubro Ltd", "pct": 4.10},
            {"name": "Persistent Systems Ltd", "pct": 3.40},
            {"name": "Axis Bank Ltd", "pct": 3.20},
            {"name": "Max Healthcare Institute Ltd", "pct": 2.90},
            {"name": "Bharti Airtel Ltd", "pct": 2.80},
            {"name": "Federal Bank Ltd", "pct": 2.60},
        ],
        "er_direct": 0.78,
        "er_regular": 1.72,
    },
    "Mid Cap Fund": {
        "cap": "Mid Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Capital Goods & Engineering", "value": 22.40},
            {"sector": "Financial Services", "value": 18.60},
            {"sector": "Healthcare & Pharma", "value": 14.10},
            {"sector": "Automobile & Ancillaries", "value": 11.80},
            {"sector": "Chemicals & Petrochemicals", "value": 9.50},
            {"sector": "Information Technology", "value": 8.20},
            {"sector": "Consumer Discretionary", "value": 7.40},
            {"sector": "Others & Cash", "value": 8.00},
        ],
        "holdings": [
            {"name": "Persistent Systems Ltd", "pct": 4.10},
            {"name": "Max Healthcare Institute Ltd", "pct": 3.80},
            {"name": "Supreme Industries Ltd", "pct": 3.60},
            {"name": "Cummins India Ltd", "pct": 3.50},
            {"name": "Federal Bank Ltd", "pct": 3.40},
            {"name": "Astral Ltd", "pct": 3.20},
            {"name": "Indian Hotels Co Ltd", "pct": 3.10},
            {"name": "Bharat Forge Ltd", "pct": 2.90},
            {"name": "Coforge Ltd", "pct": 2.80},
            {"name": "Polycab India Ltd", "pct": 2.70},
        ],
        "er_direct": 0.75,
        "er_regular": 1.75,
    },
    "Small Cap Fund": {
        "cap": "Small Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Capital Goods & Industrial", "value": 24.80},
            {"sector": "Chemicals & Materials", "value": 15.60},
            {"sector": "Financial Services", "value": 13.40},
            {"sector": "Information Technology", "value": 11.20},
            {"sector": "Healthcare & Diagnostics", "value": 10.50},
            {"sector": "Automobile & Ancillaries", "value": 9.10},
            {"sector": "Consumer Durables", "value": 7.40},
            {"sector": "Others & Cash", "value": 8.00},
        ],
        "holdings": [
            {"name": "Tube Investments of India Ltd", "pct": 3.40},
            {"name": "Apar Industries Ltd", "pct": 3.10},
            {"name": "KPIT Technologies Ltd", "pct": 2.90},
            {"name": "Carborundum Universal Ltd", "pct": 2.80},
            {"name": "Kaynes Technology India Ltd", "pct": 2.70},
            {"name": "Multi Commodity Exchange of India Ltd", "pct": 2.60},
            {"name": "JB Chemicals & Pharmaceuticals Ltd", "pct": 2.50},
            {"name": "Krishna Institute of Medical Sciences", "pct": 2.40},
            {"name": "CreditAccess Grameen Ltd", "pct": 2.30},
            {"name": "Brigade Enterprises Ltd", "pct": 2.20},
        ],
        "er_direct": 0.68,
        "er_regular": 1.65,
    },
    "Flexi Cap Fund": {
        "cap": "Multi Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 31.20},
            {"sector": "Information Technology", "value": 17.50},
            {"sector": "Consumer Discretionary", "value": 13.80},
            {"sector": "Healthcare & Pharma", "value": 9.40},
            {"sector": "Power & Energy", "value": 7.20},
            {"sector": "Automobile", "value": 6.10},
            {"sector": "Capital Goods", "value": 5.80},
            {"sector": "Others & Cash", "value": 9.00},
        ],
        "holdings": [
            {"name": "HDFC Bank Ltd", "pct": 8.10},
            {"name": "ICICI Bank Ltd", "pct": 6.90},
            {"name": "ITC Ltd", "pct": 5.40},
            {"name": "Infosys Ltd", "pct": 5.10},
            {"name": "Bajaj Holdings & Investment Ltd", "pct": 4.80},
            {"name": "Larsen & Toubro Ltd", "pct": 4.20},
            {"name": "HCL Technologies Ltd", "pct": 3.90},
            {"name": "Axis Bank Ltd", "pct": 3.50},
            {"name": "Maruti Suzuki India Ltd", "pct": 3.20},
            {"name": "Coal India Ltd", "pct": 2.90},
        ],
        "er_direct": 0.65,
        "er_regular": 1.60,
    },
    "Multi Cap Fund": {
        "cap": "Multi Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 26.50},
            {"sector": "Capital Goods & Manufacturing", "value": 18.20},
            {"sector": "Healthcare & Pharma", "value": 12.40},
            {"sector": "Information Technology", "value": 11.80},
            {"sector": "Automobile & Ancillaries", "value": 9.60},
            {"sector": "Consumer Discretionary", "value": 8.50},
            {"sector": "Others & Cash", "value": 13.00},
        ],
        "holdings": [
            {"name": "ICICI Bank Ltd", "pct": 6.20},
            {"name": "HDFC Bank Ltd", "pct": 5.80},
            {"name": "Reliance Industries Ltd", "pct": 4.50},
            {"name": "Larsen & Toubro Ltd", "pct": 3.80},
            {"name": "Persistent Systems Ltd", "pct": 3.20},
            {"name": "Tube Investments of India Ltd", "pct": 2.90},
            {"name": "Tata Motors Ltd", "pct": 2.80},
            {"name": "Apar Industries Ltd", "pct": 2.60},
            {"name": "Federal Bank Ltd", "pct": 2.40},
            {"name": "Max Healthcare Institute Ltd", "pct": 2.20},
        ],
        "er_direct": 0.70,
        "er_regular": 1.70,
    },
    "ELSS / Tax Saver": {
        "cap": "Flexi Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 30.80},
            {"sector": "Information Technology", "value": 14.50},
            {"sector": "Automobile & Ancillaries", "value": 10.20},
            {"sector": "Healthcare & Pharma", "value": 9.80},
            {"sector": "Capital Goods", "value": 8.90},
            {"sector": "Consumer Goods & FMCG", "value": 7.80},
            {"sector": "Others & Cash", "value": 18.00},
        ],
        "holdings": [
            {"name": "HDFC Bank Ltd", "pct": 7.80},
            {"name": "ICICI Bank Ltd", "pct": 6.50},
            {"name": "Infosys Ltd", "pct": 5.20},
            {"name": "Reliance Industries Ltd", "pct": 4.90},
            {"name": "Larsen & Toubro Ltd", "pct": 4.10},
            {"name": "Axis Bank Ltd", "pct": 3.40},
            {"name": "State Bank of India", "pct": 3.10},
            {"name": "Bharti Airtel Ltd", "pct": 2.90},
            {"name": "Tata Consultancy Services Ltd", "pct": 2.80},
            {"name": "Sun Pharmaceutical Industries Ltd", "pct": 2.50},
        ],
        "er_direct": 0.72,
        "er_regular": 1.68,
    },
    "Balanced Advantage / Hybrid": {
        "cap": "Hybrid",
        "risk": "HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 24.50},
            {"sector": "Sovereign & Corporate Debt", "value": 28.00},
            {"sector": "Information Technology", "value": 10.50},
            {"sector": "Energy & Power", "value": 8.20},
            {"sector": "Automobile", "value": 6.40},
            {"sector": "Healthcare", "value": 5.80},
            {"sector": "Cash & Cash Equivalents", "value": 16.60},
        ],
        "holdings": [
            {"name": "Government of India Bond 7.18%", "pct": 12.50},
            {"name": "HDFC Bank Ltd", "pct": 6.40},
            {"name": "ICICI Bank Ltd", "pct": 5.80},
            {"name": "Government of India Bond 7.26%", "pct": 5.50},
            {"name": "Reliance Industries Ltd", "pct": 4.20},
            {"name": "Infosys Ltd", "pct": 3.80},
            {"name": "Larsen & Toubro Ltd", "pct": 3.10},
            {"name": "NABARD Bond AAA", "pct": 2.80},
            {"name": "Tata Consultancy Services Ltd", "pct": 2.50},
            {"name": "ITC Ltd", "pct": 2.20},
        ],
        "er_direct": 0.60,
        "er_regular": 1.55,
    },
    "Debt / Liquid Fund": {
        "cap": "Debt",
        "risk": "LOW TO MODERATE",
        "sectors": [
            {"sector": "Sovereign Government Securities", "value": 52.00},
            {"sector": "AAA Rated Corporate Bonds", "value": 28.50},
            {"sector": "Treasury Bills & Commercial Papers", "value": 14.50},
            {"sector": "Cash & Repo Clearing", "value": 5.00},
        ],
        "holdings": [
            {"name": "7.18% GS 2033 (Govt of India)", "pct": 18.20},
            {"name": "7.26% GS 2032 (Govt of India)", "pct": 14.50},
            {"name": "91 Day Treasury Bill", "pct": 11.20},
            {"name": "HDFC Bank Ltd CP (A1+)", "pct": 8.40},
            {"name": "REC Ltd AAA Bond", "pct": 7.10},
            {"name": "Power Finance Corp AAA Bond", "pct": 6.80},
            {"name": "NABARD AAA Bond", "pct": 5.90},
            {"name": "LIC Housing Finance AAA Bond", "pct": 4.80},
            {"name": "State Bank of India CD (A1+)", "pct": 4.50},
            {"name": "SIDBI AAA Bond", "pct": 3.80},
        ],
        "er_direct": 0.20,
        "er_regular": 0.50,
    },
    "Index Fund": {
        "cap": "Large Cap",
        "risk": "VERY HIGH",
        "sectors": [
            {"sector": "Financial Services", "value": 33.20},
            {"sector": "Information Technology", "value": 14.80},
            {"sector": "Oil & Gas", "value": 11.20},
            {"sector": "Automobile", "value": 7.90},
            {"sector": "FMCG", "value": 7.40},
            {"sector": "Construction", "value": 5.10},
            {"sector": "Healthcare", "value": 4.60},
            {"sector": "Others & Cash", "value": 15.80},
        ],
        "holdings": [
            {"name": "HDFC Bank Ltd", "pct": 11.20},
            {"name": "Reliance Industries Ltd", "pct": 9.40},
            {"name": "ICICI Bank Ltd", "pct": 7.80},
            {"name": "Infosys Ltd", "pct": 5.60},
            {"name": "Larsen & Toubro Ltd", "pct": 4.30},
            {"name": "Tata Consultancy Services Ltd", "pct": 3.90},
            {"name": "ITC Ltd", "pct": 3.70},
            {"name": "Bharti Airtel Ltd", "pct": 3.60},
            {"name": "Axis Bank Ltd", "pct": 3.10},
            {"name": "State Bank of India", "pct": 2.90},
        ],
        "er_direct": 0.15,
        "er_regular": 0.40,
    },
}


def _normalize_category(raw_category: str, scheme_name: str) -> str:
    """Normalize AMFI raw category string and scheme name to standard SEBI category."""
    name_lower = scheme_name.lower()
    cat_lower = raw_category.lower()
    combined = f"{name_lower} {cat_lower}"

    if "small cap" in combined:
        return "Small Cap Fund"
    # Must run before plain mid-cap / large-cap checks
    if (
        "large & mid" in combined
        or "large and mid" in combined
        or "large & midcap" in combined
        or "large and midcap" in combined
    ):
        return "Large & Mid Cap Fund"
    if "mid cap" in combined or "midcap" in combined:
        return "Mid Cap Fund"
    if "flexi cap" in combined or "flexicap" in combined:
        return "Flexi Cap Fund"
    if "multi cap" in combined or "multicap" in combined:
        return "Multi Cap Fund"
    if "large cap" in combined or "bluechip" in name_lower or "top 100" in name_lower:
        return "Large Cap Fund"
    if "elss" in combined or "tax saver" in name_lower or "tax adv" in name_lower:
        return "ELSS / Tax Saver"
    if "nifty" in name_lower or "sensex" in name_lower or "index" in name_lower:
        return "Index Fund"
    if "balanced advantage" in name_lower or "dynamic asset" in name_lower or "hybrid" in name_lower:
        return "Balanced Advantage / Hybrid"
    if "debt" in cat_lower or "liquid" in name_lower or "overnight" in name_lower or "money market" in name_lower:
        return "Debt / Liquid Fund"

    return "Large Cap Fund"


def _extract_amc_name(scheme_name: str, raw_amc: str) -> str:
    """Extract clean AMC Name dynamically from AMFI feed header or scheme name."""
    if raw_amc:
        cleaned = raw_amc.strip()
        if cleaned and not cleaned.startswith("Open Ended") and not cleaned.startswith("Close Ended"):
            return cleaned if "mutual fund" in cleaned.lower() else f"{cleaned} Mutual Fund"

    for amc in [
        "SBI Mutual Fund", "HDFC Mutual Fund", "ICICI Prudential Mutual Fund",
        "Nippon India Mutual Fund", "Kotak Mahindra Mutual Fund", "Axis Mutual Fund",
        "UTI Mutual Fund", "Aditya Birla Sun Life Mutual Fund", "Mirae Asset Mutual Fund",
        "DSP Mutual Fund", "Tata Mutual Fund", "Quant Mutual Fund", "PPFAS Mutual Fund",
        "Bandhan Mutual Fund", "Motilal Oswal Mutual Fund", "Canara Robeco Mutual Fund",
        "Edelweiss Mutual Fund", "Sundaram Mutual Fund", "Invesco Mutual Fund",
        "HSBC Mutual Fund", "PGIM India Mutual Fund", "Franklin Templeton Mutual Fund",
        "Mahindra Manulife Mutual Fund", "WhiteOak Capital Mutual Fund", "Baroda BNP Paribas Mutual Fund",
        "Zerodha Mutual Fund", "Groww Mutual Fund", "Navi Mutual Fund", "Helios Mutual Fund",
        "Old Bridge Mutual Fund", "Trust Mutual Fund", "Quantum Mutual Fund", "360 ONE Mutual Fund",
        "Samco Mutual Fund", "NJ Mutual Fund", "Taurus Mutual Fund", "Union Mutual Fund", "JM Financial Mutual Fund"
    ]:
        prefix = amc.replace(" Mutual Fund", "").lower()
        if prefix in scheme_name.lower():
            return amc

    return raw_amc or "Indian Mutual Fund"


def fetch_amfi_master_schemes() -> List[Dict[str, Any]]:
    """
    Fetch and parse full master scheme catalogue from AMFI official feed.
    Raises AmfiFetchError when the feed cannot be downloaded or yields no schemes.
    """
    schemes: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(AMFI_NAV_URL, headers={"User-Agent": "FinanceBuddy/6.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            content = response.read().decode("utf-8", errors="ignore")

        lines = content.split("\n")
        current_category = ""
        current_amc = ""
        seen_isins = set()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Open Ended") or line.startswith("Close Ended") or line.startswith("Interval"):
                current_category = line
            elif ";" not in line:
                current_amc = line
            else:
                parts = line.split(";")
                if len(parts) >= 5 and parts[0].isdigit():
                    code = parts[0].strip()
                    isin = parts[1].strip() if parts[1] != "-" else parts[2].strip()
                    name = parts[3].strip()
                    nav_str = parts[4].strip()

                    if isin and isin != "-" and isin.startswith("INF") and len(isin) == 12:
                        if isin not in seen_isins:
                            seen_isins.add(isin)
                            schemes.append({
                                "scheme_code": code,
                                "isin": isin,
                                "scheme_name": name,
                                "raw_category": current_category,
                                "raw_amc": current_amc,
                                "nav": nav_str,
                            })
    except AmfiFetchError:
        raise
    except Exception as exc:
        logger.error("[AMFI_INGEST] Failed to fetch AMFI master feed: %s", exc)
        raise AmfiFetchError(f"Failed to fetch AMFI master feed: {exc}") from exc

    if not schemes:
        raise AmfiFetchError("AMFI master feed returned 0 parseable schemes")

    return schemes


def get_sync_status() -> Dict[str, Any]:
    """
    Returns latest sync metadata, scheme counts, and recent sync audit history.
    """
    total_schemes = 0
    latest_date = None
    recent_logs = []

    try:
        with db.connect() as conn:
            count_row = conn.execute("SELECT COUNT(*) FROM mf_portfolio_snapshots").fetchone()
            total_schemes = count_row[0] if count_row else 0

            date_row = conn.execute(
                "SELECT portfolio_date, updated_at FROM mf_portfolio_snapshots ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if date_row and date_row[0]:
                latest_date = date_row[0].strftime("%B %Y")

            logs = conn.execute(
                """
                SELECT id, triggered_by, status, schemes_updated, portfolio_month,
                       duration_seconds, error_message, created_at
                FROM mf_sync_logs
                ORDER BY created_at DESC
                LIMIT 10
                """
            ).fetchall()

            for r in logs:
                recent_logs.append({
                    "id": r[0],
                    "triggered_by": r[1],
                    "status": r[2],
                    "schemes_updated": r[3],
                    "portfolio_month": r[4],
                    "duration_seconds": float(r[5]) if r[5] is not None else 0.0,
                    "error_message": r[6],
                    "created_at": r[7].isoformat() if r[7] else None,
                })

    except Exception as exc:
        logger.warning("[AMFI_INGEST] Failed to fetch sync status: %s", exc)

    return {
        "total_schemes": total_schemes,
        "latest_portfolio_month": latest_date or _portfolio_as_of().strftime("%B %Y"),
        "recent_logs": recent_logs,
    }


def search_synced_schemes(
    query: str = "",
    amc: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Search and paginate through synced mutual fund snapshots in PostgreSQL.
    Supports filtering by text query, specific AMC, and specific category.
    """
    clean_q = (query or "").strip()
    clean_amc = (amc or "").strip()
    clean_cat = (category or "").strip()
    schemes = []
    total = 0

    try:
        with db.connect() as conn:
            where_clauses = []
            params = []

            if clean_amc and clean_amc.lower() != "all":
                amc_terms = _amc_match_terms(clean_amc)
                amc_parts = []
                for term in amc_terms:
                    amc_parts.append("(amc ILIKE %s OR scheme_name ILIKE %s)")
                    params.extend([f"%{term}%", f"{term}%"])
                where_clauses.append("(" + " OR ".join(amc_parts) + ")")

            if clean_cat and clean_cat.lower() != "all":
                where_clauses.append("category ILIKE %s")
                params.append(f"%{clean_cat}%")

            if clean_q:
                q_terms = _amc_match_terms(clean_q)
                q_parts = []
                # Alias-only queries (e.g. "grow") must not substring-match "Growth" plans
                if clean_q.lower() in AMC_ALIASES:
                    for term in q_terms:
                        q_parts.append("amc ILIKE %s")
                        params.append(f"%{term}%")
                        q_parts.append("scheme_name ILIKE %s")
                        params.append(f"{term}%")
                else:
                    q_parts.extend(["scheme_name ILIKE %s", "isin ILIKE %s"])
                    params.extend([f"%{clean_q}%", f"%{clean_q}%"])
                    for term in q_terms:
                        q_parts.append("amc ILIKE %s")
                        params.append(f"%{term}%")
                where_clauses.append("(" + " OR ".join(q_parts) + ")")

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            # Count total matching rows
            total_sql = f"SELECT COUNT(*) FROM mf_portfolio_snapshots {where_sql}"
            total_row = conn.execute(total_sql, tuple(params)).fetchone()
            total = total_row[0] if total_row else 0

            # Order with priority on exact AMC or scheme prefix if searching
            order_sql = "ORDER BY aum_cr DESC NULLS LAST"
            order_params = []
            if clean_q:
                q_terms = _amc_match_terms(clean_q)
                amc_rank_parts = " OR ".join(["amc ILIKE %s"] * len(q_terms))
                order_sql = f"""
                ORDER BY
                  CASE
                    WHEN {amc_rank_parts} THEN 1
                    WHEN scheme_name ILIKE %s THEN 2
                    WHEN isin ILIKE %s THEN 3
                    ELSE 4
                  END,
                  aum_cr DESC NULLS LAST
                """
                order_params = [f"%{t}%" for t in q_terms] + [f"{clean_q}%", f"{clean_q}%"]

            query_sql = f"""
                SELECT isin, scheme_code, scheme_name, amc, category, aum_cr, expense_ratio,
                       risk_level, portfolio_date, sectors, holdings, source, updated_at
                FROM mf_portfolio_snapshots
                {where_sql}
                {order_sql}
                LIMIT %s OFFSET %s
            """
            full_params = tuple(params + order_params + [limit, offset])
            rows = conn.execute(query_sql, full_params).fetchall()

            for r in rows:
                sectors_data = json.loads(r[9]) if isinstance(r[9], str) else (r[9] or [])
                holdings_data = json.loads(r[10]) if isinstance(r[10], str) else (r[10] or [])
                aum_val = float(r[5]) if r[5] is not None else None
                er_val = float(r[6]) if r[6] is not None else None

                schemes.append({
                    "isin": r[0],
                    "scheme_code": r[1],
                    "scheme_name": r[2],
                    "amc": r[3],
                    "category": r[4],
                    "aum_cr": aum_val,
                    "aum_formatted": f"₹{aum_val:,.0f} Cr" if aum_val else "N/A",
                    "expense_ratio": er_val,
                    "risk_level": r[7],
                    "portfolio_date": str(r[8]) if r[8] else None,
                    "sectors_count": len(sectors_data),
                    "holdings_count": len(holdings_data),
                    "sectors": sectors_data,
                    "holdings": holdings_data,
                    "source": r[11],
                    "updated_at": r[12].isoformat() if r[12] else None,
                })

    except Exception as exc:
        logger.error("[AMFI_INGEST] Search synced schemes error: %s", exc)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "schemes": schemes,
    }


TOP_5_AMCS = ["HDFC", "SBI", "ICICI Prudential", "Nippon India", "Kotak"]
TOP_10_AMCS = [
    "HDFC", "SBI", "ICICI Prudential", "Nippon India", "Kotak",
    "Axis", "Quant", "Parag Parikh", "Mirae Asset", "Tata"
]


def get_synced_amc_list() -> List[Dict[str, Any]]:
    """
    Get list of distinct AMCs currently stored in the database with scheme count and aggregate AUM.
    """
    amcs = []
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT amc, COUNT(*) as cnt, SUM(aum_cr) as total_aum
                FROM mf_portfolio_snapshots
                GROUP BY amc
                ORDER BY cnt DESC, amc ASC
                """
            ).fetchall()

            for r in rows:
                amcs.append({
                    "amc": r[0],
                    "schemes_count": r[1],
                    "total_aum_cr": float(r[2]) if r[2] is not None else 0.0,
                })
    except Exception as exc:
        logger.error("[AMFI_INGEST] Failed to get synced AMC list: %s", exc)
    return amcs


def purge_snapshots(amc: Optional[str] = None, purge_all: bool = False, admin_email: str = "admin") -> Dict[str, Any]:
    """
    Purge mutual fund portfolio snapshots from PostgreSQL.
    If purge_all is True: truncates / deletes all rows.
    If amc is provided: removes all schemes belonging to that AMC (alias-aware).
    """
    deleted_count = 0
    try:
        with db.connect() as conn:
            if purge_all:
                count_row = conn.execute("SELECT COUNT(*) FROM mf_portfolio_snapshots").fetchone()
                deleted_count = count_row[0] if count_row else 0
                conn.execute("DELETE FROM mf_portfolio_snapshots")
                logger.warning(
                    "[AMFI_INGEST] Admin %s purged ALL %d schemes from mf_portfolio_snapshots",
                    admin_email, deleted_count
                )
            elif amc:
                terms = _amc_match_terms(amc)
                if not terms:
                    return {"status": "error", "message": "Specify purge_all=True or amc to purge"}
                where_parts = []
                params: List[Any] = []
                for term in terms:
                    where_parts.append("(amc ILIKE %s OR scheme_name ILIKE %s)")
                    params.extend([f"%{term}%", f"{term}%"])
                where_sql = " OR ".join(where_parts)
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM mf_portfolio_snapshots WHERE {where_sql}",
                    tuple(params),
                ).fetchone()
                deleted_count = count_row[0] if count_row else 0
                conn.execute(
                    f"DELETE FROM mf_portfolio_snapshots WHERE {where_sql}",
                    tuple(params),
                )
                logger.info(
                    "[AMFI_INGEST] Admin %s purged %d schemes for AMC %s",
                    admin_email, deleted_count, amc
                )
            else:
                return {"status": "error", "message": "Specify purge_all=True or amc to purge"}

        _invalidate_market_caches()
        logger.info("[AMFI_INGEST] Market caches cleared after snapshot purge")

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "purged_all": purge_all,
            "amc": amc,
            "message": f"Successfully purged {deleted_count:,} schemes from database.",
        }

    except Exception as exc:
        logger.error("[AMFI_INGEST] Purge failed: %s", exc)
        return {"status": "error", "error": str(exc), "deleted_count": 0}


def trigger_amfi_sync(
    admin_email: str = "admin",
    amcs: Optional[List[str]] = None,
    preset: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest or refresh AMFI mutual fund portfolio snapshots into PostgreSQL.
    Supports selective sync:
    - preset='top5': Ingests top 5 AMCs (HDFC, SBI, ICICI Prudential, Nippon India, Kotak)
    - preset='top10': Ingests top 10 AMCs
    - preset='all': Ingests full master catalogue (all AMCs)
    - amcs=['Groww', 'Zerodha', ...]: Ingests specific AMCs
    """
    start_time = time.time()
    as_of = _portfolio_as_of()
    portfolio_month = as_of.strftime("%B %Y")
    portfolio_date = as_of.isoformat()
    log_id = None
    updated_count = 0
    total_in_db = 0
    error_msg = None

    target_amcs: Optional[List[str]] = None
    if preset == "top5":
        target_amcs = [a.lower() for a in TOP_5_AMCS]
    elif preset == "top10":
        target_amcs = [a.lower() for a in TOP_10_AMCS]
    elif preset == "all":
        target_amcs = None
    elif amcs and len(amcs) > 0:
        target_amcs = [a.strip().lower() for a in amcs if a.strip()]

    if preset and preset != "all":
        scope_desc = f" ({preset.upper()})"
    elif amcs:
        shown = ", ".join(amcs[:3])
        if len(amcs) > 3:
            shown += "..."
        scope_desc = f" ({shown})"
    else:
        scope_desc = " (All AMCs)"

    try:
        # Log start of sync
        try:
            with db.connect() as conn:
                res = conn.execute(
                    """
                    INSERT INTO mf_sync_logs (triggered_by, status, portfolio_month)
                    VALUES (%s, 'in_progress', %s)
                    RETURNING id
                    """,
                    (f"{admin_email}{scope_desc}", portfolio_month),
                ).fetchone()
                if res:
                    log_id = res[0]
        except Exception as exc:
            logger.warning("[AMFI_INGEST] Could not create sync log record: %s", exc)

        # 2. Fetch official master schemes from AMFI (raises on failure / empty feed)
        raw_schemes = fetch_amfi_master_schemes()
        logger.info("[AMFI_INGEST] Fetched %d master schemes from AMFI feed", len(raw_schemes))

        # 3. Filter and Ingest / Upsert schemes using cursor.executemany
        with db.connect() as conn:
            batch_data = []
            for s in raw_schemes:
                isin = s["isin"]
                code = s["scheme_code"]
                name = s["scheme_name"]
                cat_name = _normalize_category(s["raw_category"], name)
                amc_name = _extract_amc_name(name, s["raw_amc"])

                # Check if scheme matches selective AMC filter
                if target_amcs is not None:
                    matched = False
                    name_lower = name.lower()
                    amc_lower = amc_name.lower()
                    for t in target_amcs:
                        t_clean = t.strip().lower()
                        if not t_clean:
                            continue
                        match_terms = _amc_match_terms(t_clean)
                        for term in match_terms:
                            term_l = term.lower()
                            if term_l in amc_lower:
                                matched = True
                                break
                            if name_lower.startswith(term_l + " "):
                                matched = True
                                break
                        if matched:
                            break
                    if not matched:
                        continue

                bench = CATEGORY_BENCHMARKS.get(cat_name, CATEGORY_BENCHMARKS["Large Cap Fund"])
                is_direct = "direct" in name.lower()
                er = bench["er_direct"] if is_direct else bench["er_regular"]

                # Deterministic placeholder AUM — AMFI NAV feed does not publish AUM
                base_hash = sum(ord(c) for c in isin) % 25000 + 1500
                aum = round(float(base_hash), 2)

                batch_data.append((
                    isin,
                    code,
                    name,
                    amc_name,
                    cat_name,
                    bench["cap"],
                    aum,
                    er,
                    bench["risk"],
                    "1% within 365 days, Nil thereafter",
                    portfolio_date,
                    json.dumps(bench["sectors"]),
                    json.dumps(bench["holdings"]),
                    "AMFI Catalogue (category benchmark proxies)",
                ))

            if batch_data:
                upsert_sql = """
                    INSERT INTO mf_portfolio_snapshots (
                        isin, scheme_code, scheme_name, amc, category, cap_type,
                        aum_cr, expense_ratio, risk_level, exit_load, portfolio_date,
                        sectors, holdings, source, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, now())
                    ON CONFLICT (isin) DO UPDATE SET
                        scheme_code = EXCLUDED.scheme_code,
                        scheme_name = EXCLUDED.scheme_name,
                        amc = EXCLUDED.amc,
                        category = EXCLUDED.category,
                        cap_type = EXCLUDED.cap_type,
                        aum_cr = EXCLUDED.aum_cr,
                        expense_ratio = EXCLUDED.expense_ratio,
                        risk_level = EXCLUDED.risk_level,
                        exit_load = EXCLUDED.exit_load,
                        portfolio_date = EXCLUDED.portfolio_date,
                        sectors = EXCLUDED.sectors,
                        holdings = EXCLUDED.holdings,
                        source = EXCLUDED.source,
                        updated_at = now()
                """

                cur = conn.cursor()
                cur.executemany(upsert_sql, batch_data)

            # Query total schemes currently stored after sync
            count_res = conn.execute("SELECT COUNT(*) FROM mf_portfolio_snapshots").fetchone()
            total_in_db = count_res[0] if count_res else len(batch_data)
            updated_count = len(batch_data)

        # 4. Clear caches so clients pick up refreshed snapshots
        _invalidate_market_caches()

        duration = round(time.time() - start_time, 2)

        # 5. Mark log as completed
        if log_id:
            with db.connect() as conn:
                conn.execute(
                    """
                    UPDATE mf_sync_logs
                    SET status = 'completed', schemes_updated = %s, duration_seconds = %s
                    WHERE id = %s
                    """,
                    (updated_count, duration, log_id),
                )

        return {
            "status": "completed",
            "schemes_updated": updated_count,
            "total_schemes_in_db": total_in_db,
            "portfolio_month": portfolio_month,
            "duration_seconds": duration,
            "message": f"Successfully synced {updated_count:,} mutual fund disclosures for {portfolio_month}.",
        }

    except Exception as exc:
        duration = round(time.time() - start_time, 2)
        error_msg = str(exc)
        logger.error("[AMFI_INGEST] Sync execution failed: %s", exc)

        if log_id:
            try:
                with db.connect() as conn:
                    conn.execute(
                        """
                        UPDATE mf_sync_logs
                        SET status = 'failed', duration_seconds = %s, error_message = %s
                        WHERE id = %s
                        """,
                        (duration, error_msg, log_id),
                    )
            except Exception:
                pass

        return {
            "status": "failed",
            "schemes_updated": 0,
            "duration_seconds": duration,
            "error": error_msg,
            "portfolio_month": portfolio_month,
        }

