"""
domains/equity/nse_results.py

Latest quarterly results, parsed from the company's own XBRL filing.

This fills a specific hole rather than replacing yfinance. Measured against live data:
yfinance returns **zero quarterly cash-flow columns** for RELIANCE, ETERNAL and SWIGGY,
only 2-3 irregular quarterly balance sheets, and blends consolidated with standalone
into one unlabelled view. The exchange filing has the full income statement, states
whether it is consolidated or standalone, and says whether it was audited.

Scope is deliberately one quarter, not a backfill. The index endpoints return metadata
only, so every historical quarter costs another ~46 KB XBRL fetch and parse; twenty
quarters is twenty round trips per symbol. The freshness gap is what hurts, and that is
the newest filing. yfinance's *annual* statements are reliable over five years,
including pre-IPO years for recent listings, so the deep history is already covered.

Two endpoints exist because SEBI changed the filing regime in January 2025:

    corporates-financial-results   2005 -> Dec-2024, then frozen
    integrated-filing-results      Jan-2025 -> present

and they use different XBRL taxonomies (`in-bse-fin` vs SEBI's `in-capmkt`). Only the
current one is read here; the frozen archive is the backfill this module does not do.

Like everything NSE-sourced: fails soft to None. NSE blocks datacenter IPs, so on a
cloud host this returns nothing and the analyzer falls back to yfinance.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from shared.services.cache import MARKET_CACHE

logger = logging.getLogger(__name__)

_FILINGS_URL = "https://www.nseindia.com/api/integrated-filing-results"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/",
}

_TIMEOUT = 15

#: Results are a quarterly event. A day is generous during results season and free the
#: rest of the year, and the background sweep refreshes warm symbols anyway.
_TTL = 24 * 3600

#: Guard against a malformed or hostile response. A results XBRL is ~46 KB.
_MAX_XBRL_BYTES = 4 * 1024 * 1024

#: Facts carry the SEBI integrated-filing prefix. The hyphen matters: a `\w+` prefix
#: pattern silently matches only `xbrli`/`xbrldi` and finds no financial data at all.
_FACT_RE = re.compile(
    r'<in-capmkt:([A-Za-z0-9]+)\s+contextRef="([^"]+)"[^>]*>([^<]+)</in-capmkt:\1>'
)
_CONTEXT_RE = re.compile(
    r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', re.S
)
_START_RE = re.compile(r"<xbrli:startDate>([^<]+)</xbrli:startDate>")
_END_RE = re.compile(r"<xbrli:endDate>([^<]+)</xbrli:endDate>")

#: XBRL tag -> output field. Values are absolute rupees; `_cr` scales them.
#: Only the income statement is mapped: the quarterly filing is a results statement, so
#: it carries no balance sheet and no cash-flow statement to extract.
_INCOME_FIELDS: dict[str, str] = {
    "RevenueFromOperations": "revenue_cr",
    "OtherIncome": "other_income_cr",
    "Income": "total_income_cr",
    "CostOfMaterialsConsumed": "material_cost_cr",
    "EmployeeBenefitExpense": "employee_cost_cr",
    "FinanceCosts": "finance_cost_cr",
    "DepreciationDepletionAndAmortisationExpense": "depreciation_cr",
    "OtherExpenses": "other_expenses_cr",
    "Expenses": "total_expenses_cr",
    "ProfitBeforeExceptionalItemsAndTax": "pbt_before_exceptional_cr",
    "ProfitBeforeTax": "pbt_cr",
    "CurrentTax": "current_tax_cr",
    "DeferredTax": "deferred_tax_cr",
    "TaxExpense": "tax_expense_cr",
    "ProfitLossForPeriod": "net_income_cr",
    "ProfitOrLossAttributableToOwnersOfParent": "pat_owners_cr",
    "OtherComprehensiveIncomeNetOfTaxes": "other_comprehensive_income_cr",
    "ComprehensiveIncomeForThePeriod": "comprehensive_income_cr",
    "PaidUpValueOfEquityShareCapital": "paid_up_capital_cr",
}

#: Banks and NBFCs file under a different SEBI template with a different top line -
#: `InterestEarned` rather than `RevenueFromOperations` - so the mapping above matches
#: nothing for them and the filing was silently skipped. Financials are roughly a third
#: of the Nifty, so that is not an acceptable gap. Merged into the same output fields,
#: because "revenue" and "net profit" mean the same thing to a reader either way.
_BANK_INCOME_FIELDS: dict[str, str] = {
    "InterestEarned": "revenue_cr",
    "OtherIncome": "other_income_cr",
    "Income": "total_income_cr",
    "InterestExpended": "interest_expended_cr",
    "EmployeesCost": "employee_cost_cr",
    "OperatingExpenses": "operating_expenses_cr",
    "ExpenditureExcludingProvisionsAndContingencies": "total_expenses_cr",
    "OperatingProfitBeforeProvisionAndContingencies": "operating_profit_cr",
    "ProvisionsOtherThanTaxAndContingencies": "provisions_cr",
    "ProfitLossFromOrdinaryActivitiesBeforeTax": "pbt_cr",
    "TaxExpense": "tax_expense_cr",
    "ProfitLossForThePeriod": "net_income_cr",
    "GrossNonPerformingAssets": "gross_npa_cr",
    "PaidUpValueOfEquityShareCapital": "paid_up_capital_cr",
}

#: Bank per-share figures. Not scalable to crore.
#:
#: `PercentageOfGrossNpa`, `PercentageOfNetNpa` and `CET1Ratio` are deliberately NOT
#: mapped despite being present and interesting. Filers disagree on their units: ICICI
#: reports gross NPA as 0.0138 (a fraction, so 1.38%) while HDFC Bank reports 0.0 for
#: the same tag against a real figure of roughly 1.4%. Guessing a scale is how the
#: dividend-yield bug happened, and a wrong NPA is worse than an absent one.
#: `gross_npa_cr` above is an absolute amount and is unambiguous, so that is what is
#: surfaced.
_BANK_RAW_FIELDS: dict[str, str] = {
    "BasicEarningsPerShareAfterExtraordinaryItems": "eps_basic",
    "DilutedEarningsPerShareAfterExtraordinaryItems": "eps_diluted",
    "FaceValueOfEquityShareCapital": "face_value",
}

#: Per-share and ratio facts, which must NOT be scaled to crore.
_RAW_FIELDS: dict[str, str] = {
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "eps_basic",
    "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "eps_diluted",
    "FaceValueOfEquityShareCapital": "face_value",
    "DebtEquityRatio": "debt_equity_ratio",
}

#: Fallbacks for filers that only report the continuing-operations line.
_EPS_FALLBACK = {
    "eps_basic": "BasicEarningsLossPerShareFromContinuingOperations",
    "eps_diluted": "DilutedEarningsLossPerShareFromContinuingOperations",
}


def _cr(value: float | None) -> float | None:
    return None if value is None else round(value / 1e7, 2)


def _num(text: str) -> float | None:
    try:
        return float(text.strip())
    except (TypeError, ValueError):
        return None


def _quarter_context(xml: str) -> str | None:
    """
    The context id for the reporting quarter, at entity level.

    Two ways to get this wrong, both of which produce plausible-looking numbers:

      * A filing tags the quarter, the year to date and the prior year with the same
        element names, told apart only by `contextRef`. Choosing the wrong one reports
        a year's revenue as a quarter's, so the shortest qualifying duration wins
        rather than a hardcoded id.
      * Segment breakdowns share the quarter's exact dates and differ only by an
        `xbrldi:explicitMember` dimension. Banks file a dozen of these
        (`OneReportable11D`, `OneReportable12D`, ...), so a shortest-duration tiebreak
        alone can land on one business segment and report it as the whole company.
        Dimensioned contexts are therefore excluded outright.
    """
    from datetime import date

    best: tuple[int, str] | None = None
    for cid, block in _CONTEXT_RE.findall(xml):
        if "explicitMember" in block:
            continue  # a segment or other dimension, not the entity as a whole
        start, end = _START_RE.search(block), _END_RE.search(block)
        if not (start and end):
            continue  # instant contexts describe balances, not a period
        try:
            s = date.fromisoformat(start.group(1).strip())
            e = date.fromisoformat(end.group(1).strip())
        except ValueError:
            continue
        span = (e - s).days
        # A quarter is ~90 days. Under 20 is a stub, over 200 is annual or year-to-date.
        if not (20 <= span <= 200):
            continue
        if best is None or span < best[0]:
            best = (span, cid)
    return best[1] if best else None


def parse_results_xbrl(xml: str) -> dict[str, Any] | None:
    """
    Parse one results XBRL into a flat dict. Returns None when it holds no figures.

    Regex rather than an XML parser: these documents are machine-generated from a fixed
    SEBI template, and this avoids pulling lxml in for one call path on a 512 MB box.
    Every value is validated as numeric before use, and unknown tags are ignored, so a
    template change degrades to missing fields rather than to wrong ones.
    """
    if not xml or len(xml) > _MAX_XBRL_BYTES:
        return None

    ctx = _quarter_context(xml)
    if not ctx:
        return None

    facts: dict[str, str] = {}
    for name, context, value in _FACT_RE.findall(xml):
        if context == ctx and name not in facts:
            facts[name] = value

    # `InterestEarned` only appears in the banking template, and the two templates
    # disagree on the name of nearly every line, so the schema is chosen rather than
    # merged - applying both would let a non-bank tag win on a bank filing.
    is_bank = "InterestEarned" in facts
    income_map = _BANK_INCOME_FIELDS if is_bank else _INCOME_FIELDS
    raw_map = _BANK_RAW_FIELDS if is_bank else _RAW_FIELDS

    out: dict[str, Any] = {"template": "banking" if is_bank else "ind-as"}
    for tag, field in income_map.items():
        if tag in facts:
            out[field] = _cr(_num(facts[tag]))
    for tag, field in raw_map.items():
        if tag in facts:
            out[field] = _num(facts[tag])
    for field, fallback_tag in _EPS_FALLBACK.items():
        if out.get(field) is None and fallback_tag in facts:
            out[field] = _num(facts[fallback_tag])

    if out.get("revenue_cr") is None and out.get("net_income_cr") is None:
        # Governance and disclosure filings share the taxonomy but carry no results.
        return None

    # Descriptive fields, straight from the filing rather than inferred.
    for tag, field in (
        ("NatureOfReportStandaloneConsolidated", "basis"),
        ("WhetherResultsAreAuditedOrUnaudited", "audited"),
        ("DateOfEndOfReportingPeriod", "period_end"),
        ("DateOfStartOfReportingPeriod", "period_start"),
    ):
        raw = re.search(
            rf'<in-capmkt:{tag}[^>]*>([^<]+)</in-capmkt:{tag}>', xml
        )
        if raw:
            out[field] = raw.group(1).strip()

    rev, net = out.get("revenue_cr"), out.get("net_income_cr")
    out["net_margin_pct"] = round(net / rev * 100, 2) if (rev and net is not None) else None
    return out


def _fetch_latest(symbol: str) -> dict[str, Any] | None:
    """Fetch and parse the newest quarterly results filing. None on any failure."""
    try:
        resp = requests.get(
            _FILINGS_URL,
            params={"index": "equities", "symbol": symbol, "period": "Quarterly"},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        rows = (resp.json() or {}).get("data") or []
    except Exception as e:
        logger.warning("[nse_results] filing list failed for %s: %s", symbol, e)
        return None

    # Only rows that declare a basis are results filings; the rest are governance and
    # related-party disclosures sharing the same feed and taxonomy.
    results = [
        r for r in rows
        if isinstance(r, dict)
        and r.get("qe_Date")
        and (r.get("consolidated") or "").strip() in ("Consolidated", "Standalone")
        and (r.get("xbrl") or "").strip()
    ]
    if not results:
        return None

    def _sort_key(row: dict) -> tuple:
        from datetime import datetime
        try:
            qe = datetime.strptime(row["qe_Date"].strip(), "%d-%b-%Y").date()
        except ValueError:
            from datetime import date
            qe = date.min
        # Newest quarter first, and consolidated ahead of standalone within it:
        # consolidated is the group-level view most people mean by "the results".
        return (qe, row.get("consolidated") == "Consolidated")

    for row in sorted(results, key=_sort_key, reverse=True)[:3]:
        try:
            doc = requests.get(row["xbrl"], headers=_HEADERS, timeout=_TIMEOUT)
            if doc.status_code != 200:
                continue
            parsed = parse_results_xbrl(doc.text)
        except Exception as e:
            logger.warning("[nse_results] XBRL fetch failed for %s: %s", symbol, e)
            continue
        if parsed:
            parsed["symbol"] = symbol
            parsed["source"] = "NSE filing"
            parsed["quarter_end"] = row["qe_Date"]
            parsed["filed_at"] = row.get("broadcast_Date")
            parsed["filing_url"] = row["xbrl"]
            return parsed
    return None


def latest_results(symbol: str) -> dict[str, Any] | None:
    """
    Most recent quarterly results for one symbol, or None.

    None is the normal answer from a cloud host, and for any company whose filing does
    not parse. Callers must treat it as "no exchange data", not as an error.
    """
    sym = symbol.upper().strip()
    return MARKET_CACHE.get_or_compute(
        f"nse_results_v1:{sym}", lambda: _fetch_latest(sym), _TTL,
    )
