"""routers/sip.py — SIP calculator endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from logic_adapter import stepup_sip_projection

router = APIRouter()


class SipInput(BaseModel):
    monthly_sip:   float = 10000
    years:         int   = 10
    annual_return: float = 12.0
    stepup_pct:    float = 10.0


@router.post("/projection")
def sip_projection(body: SipInput):
    result = stepup_sip_projection(
        body.monthly_sip,
        body.years,
        body.annual_return,
        body.stepup_pct,
    )
    return result


@router.get("/{session_id}/activity")
def sip_activity(session_id: str):
    """SIP transaction history grouped by month."""
    from routers.portfolio import _get_session, _df_to_records
    s    = _get_session(session_id)
    df_s = s["df_sips"]
    if df_s.empty:
        return {"monthly": [], "total_sips": 0, "total_invested": 0}

    df_s = df_s.copy()
    df_s["YearMonth"] = df_s["Date"].dt.strftime("%Y-%m")
    monthly = (
        df_s.groupby("YearMonth")
        .agg(amount=("Amount", "sum"), count=("Amount", "count"))
        .reset_index()
        .sort_values("YearMonth")
    )
    return {
        "monthly":        _df_to_records(monthly),
        "total_sips":     int(len(df_s)),
        "total_invested": float(df_s["Amount"].abs().sum()),
    }
