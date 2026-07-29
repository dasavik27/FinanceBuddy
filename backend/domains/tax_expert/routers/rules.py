"""
routers/rules.py

Tax Expert - Client Rules Feed
==============================
Serves the subset of tax_rules.json that the UI actually needs.

Why this exists
---------------
The frontend used to carry its own byte-identical copy of tax_rules.json with no
sync mechanism between the two, so a Budget change had to be remembered in two
places. Roughly 3.4 KB of that 5.5 KB file is server-only computation config
(slab tables, surcharge bands, cess, 234-interest rules) that the browser never
reads but downloaded anyway.

tax_rules.json in this package is now the single source of truth: the engine
imports it directly, shared/config.py reads the same path for the mutual-funds
domain, and the browser gets the display subset from here.
"""

from fastapi import APIRouter

from domains.tax_expert.tax_engine import TAX_RULES

router = APIRouter()


@router.get("/rules")
def get_client_tax_rules():
    """Display-only rules and tooltip copy for the UI.

    Deliberately a projection, not the whole file — the slab/surcharge/cess tables
    stay server-side because only the engine uses them, and shipping them invites
    the frontend to start recomputing tax independently (which is exactly how the
    capital-gains aggregation diverged before).

    Static for a given deployment, so the client caches it aggressively.
    """
    cg = TAX_RULES["capital_gains"]
    ded = TAX_RULES["deductions"]
    return {
        "capital_gains": {
            "ltcg_equity_rate": cg["ltcg_equity_rate"],
            "stcg_equity_rate": cg["stcg_equity_rate"],
            "ltcg_other_rate": cg["ltcg_other_rate"],
            "ltcg_equity_exemption": cg["ltcg_equity_exemption"],
            "stcg_debt_rate": cg["stcg_debt_rate"],
            "equity_ltcg_days": cg["equity_ltcg_days"],
            "debt_ltcg_days": cg["debt_ltcg_days"],
            "elss_lockin_days": cg["elss_lockin_days"],
        },
        "deductions": {
            "limit_80c": ded["limit_80c"],
            "limit_80ccd1b": ded["limit_80ccd1b"],
            "limit_80d_self": ded["limit_80d_self"],
            "limit_80d_self_senior": ded["limit_80d_self_senior"],
            "limit_80d_parents": ded["limit_80d_parents"],
            "limit_80tta": ded["limit_80tta"],
            "limit_80ttb": ded["limit_80ttb"],
            "std_deduction_new": ded["std_deduction_new"],
            "std_deduction_old": ded["std_deduction_old"],
        },
        "ui_tooltips": TAX_RULES["ui_tooltips"],
    }
