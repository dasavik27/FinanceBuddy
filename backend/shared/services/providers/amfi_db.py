"""
shared/services/providers/amfi_db.py
Tier 1 Metadata Provider: PostgreSQL-backed AMFI portfolio snapshots.

Rows may be curated seed data or sync-time category benchmarks (AUM/sectors/holdings
are not always live per-fund AMFI PDF disclosures — see ARCHITECTURE.md → Mutual Funds).
"""

import json
import logging
from typing import Dict

from shared import db
from shared.services.providers.base import BaseMetadataProvider

logger = logging.getLogger(__name__)


class AMFIDatabaseProvider(BaseMetadataProvider):
    """
    Tier 1 Provider: Reads from PostgreSQL `mf_portfolio_snapshots` table.
    Serves cached scheme metadata for Indian mutual funds (seed and/or sync ingest).
    """

    def fetch_insights(self, isin: str, fund_name: str = "", category: str = "") -> Dict:
        """
        Query PostgreSQL for a portfolio snapshot by ISIN or scheme name.
        """
        clean_isin = (isin or "").strip().upper()
        clean_name = (fund_name or "").strip()

        if not clean_isin and not clean_name:
            return self._get_empty_result()

        try:
            with db.connect() as conn:
                row = None
                if clean_isin and clean_isin != "N/A":
                    row = conn.execute(
                        """
                        SELECT isin, scheme_code, scheme_name, aum_cr, expense_ratio,
                               risk_level, exit_load, sectors, holdings, source, portfolio_date
                        FROM mf_portfolio_snapshots
                        WHERE isin = %s
                        LIMIT 1
                        """,
                        (clean_isin,),
                    ).fetchone()

                # Secondary fallback: Match by scheme name if ISIN lookup missed
                if not row and clean_name:
                    row = conn.execute(
                        """
                        SELECT isin, scheme_code, scheme_name, aum_cr, expense_ratio,
                               risk_level, exit_load, sectors, holdings, source, portfolio_date
                        FROM mf_portfolio_snapshots
                        WHERE scheme_name ILIKE %s
                        ORDER BY length(scheme_name) ASC
                        LIMIT 1
                        """,
                        (f"%{clean_name[:25]}%",),
                    ).fetchone()

                if row:
                    (
                        r_isin,
                        r_code,
                        r_name,
                        aum_cr,
                        expense_ratio,
                        risk_level,
                        exit_load,
                        sectors_raw,
                        holdings_raw,
                        source,
                        portfolio_date,
                    ) = row

                    # Parse JSONB fields if needed
                    sectors = (
                        json.loads(sectors_raw)
                        if isinstance(sectors_raw, str)
                        else (sectors_raw or [])
                    )
                    holdings = (
                        json.loads(holdings_raw)
                        if isinstance(holdings_raw, str)
                        else (holdings_raw or [])
                    )

                    aum_str = None
                    if aum_cr is not None:
                        aum_val = float(aum_cr)
                        aum_str = f"₹{aum_val:,.0f} Cr" if aum_val >= 1 else f"₹{aum_val:.2f} Cr"

                    er_float = float(expense_ratio) if expense_ratio is not None else None
                    resolved_source = source or "AMFI Official Disclosure"
                    # Sync ingest stores category-benchmark proxies, not live PDF allocations
                    is_proxy = "benchmark" in resolved_source.lower() or "prox" in resolved_source.lower()

                    return {
                        "source": resolved_source,
                        "sectors": sectors,
                        "holdings": holdings,
                        "risk": (risk_level or "VERY HIGH").upper(),
                        "exit_load": exit_load or "See Factsheet",
                        "expense_ratio": er_float,
                        "aum": aum_str,
                        "aum_fallback": is_proxy,
                        "risk_fallback": is_proxy,
                        "exit_load_fallback": is_proxy,
                        "expense_ratio_fallback": is_proxy,
                    }

        except Exception as exc:
            logger.debug("[AMFI_DB] DB lookup failed or DB offline for %s: %s", clean_isin, exc)

        return self._get_empty_result()
