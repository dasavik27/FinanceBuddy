"""
routers/income.py

Tax Expert - Income Breakdown
=============================
Detailed income breakdown (salary, dividends, interest, misc) from parsed AIS data.
"""

from fastapi import APIRouter, HTTPException

from domains.tax_expert.tax_sessions import get_tax_session

router = APIRouter()


@router.get("/{session_id}/tax/income")
def get_tax_income(session_id: str):
    """Get detailed income breakdown from AIS data."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    ais = session["ais_data"]
    salary = ais.get("salary", {})

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
        "total_dividends": sum(d.get("amount", 0) for d in ais.get("dividends", [])),
        "total_savings_interest": sum(i.get("amount", 0) for i in ais.get("interest_savings", [])),
        "total_fd_interest": sum(i.get("amount", 0) for i in ais.get("interest_deposits", [])),
        "total_other_interest": sum(i.get("amount", 0) for i in ais.get("interest_others", [])),
        "total_misc_income": sum(i.get("amount", 0) for i in ais.get("misc_income", [])),
    }
