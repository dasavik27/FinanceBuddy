"""
routers/income.py

Tax Expert - Income Breakdown
=============================
Detailed income breakdown (salary, dividends, interest, misc) from parsed AIS data.
"""

from fastapi import APIRouter, HTTPException

from domains.tax_expert.computation_cache import get_computation
from domains.tax_expert.tax_sessions import get_tax_session

router = APIRouter()


@router.get("/{session_id}/tax/income")
def get_tax_income(session_id: str, regime: str = "new"):
    """Get detailed income breakdown from AIS data.

    Totals are projected from the tax engine's `other_sources` block rather than
    re-summed here. The five sums below duplicated tax_engine.py:372-388 exactly,
    so every dashboard load computed them twice over the same lists.
    """
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    ais = session["ais_data"]
    salary = ais.get("salary", {})

    # Memoized — a cache hit alongside the dashboard's /tax/summary request.
    other = get_computation(session_id, session, regime)["income_heads"]["other_sources"]
    misc = get_computation(session_id, session, regime)["income_heads"]["misc_income"]

    return {
        "personal": ais.get("personal", {}),
        "salary": {
            "gross": salary.get("gross", 0),
            "employer": salary.get("employer", ""),
            "tds_deducted": salary.get("tds_deducted", 0),
            "quarterly": salary.get("quarterly", []),
        },
        "dividends": ais.get("dividends", []),
        "interest_savings": ais.get("interest_savings", []),
        "interest_deposits": ais.get("interest_deposits", []),
        "interest_others": ais.get("interest_others", []),
        "misc_income": ais.get("misc_income", []),
        "total_dividends": other["dividends"],
        "total_savings_interest": other["savings_interest"],
        "total_fd_interest": other["fd_interest"],
        "total_other_interest": other["other_interest"],
        "total_misc_income": misc["total"],
    }
