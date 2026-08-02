"""
shared/reference/statutory.py - capital-gains constants, owned by no domain.

Why this exists
---------------
These numbers used to live in domains/tax_expert/tax_rules.json, and shared/config.py
reached across into that domain's package directory to read them:

    _TAX_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "domains",
                                   "tax_expert", "tax_rules.json")

Mutual Funds then consumed the result as shared.config.TAX_RATES - so the MF tax-lot
engine could not run without the Tax Expert domain's files present, through a
dependency that was invisible from either domain's imports. Both domains are equally
entitled consumers of Indian capital-gains law, and neither owns it, so it lives here.

Note the split: LTCG rates, holding periods and the Section 50AA cutoff are statutory
and shared. Slabs, deductions, rebates, surcharge and cess stay in tax_rules.json,
because only the Tax Expert's ITR engine computes those.

Editing
-------
One file to change when the Budget moves a rate. Both consumers pick it up:
  - domains/tax_expert/tax_engine.py  (merges this back in as TAX_RULES["capital_gains"])
  - shared/config.py                  (re-exports the MF-facing TAX_RATES view)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

_PATH = os.path.join(os.path.dirname(__file__), "capital_gains.json")

# Values of record if the file is unreadable. Kept deliberately: a malformed JSON file
# should degrade one number, not stop the process from booting - but it is logged at
# ERROR rather than swallowed, because silently computing tax at a stale rate is worse
# than a loud startup complaint. These mirror capital_gains.json as of FY 2024-25.
_FALLBACK: Dict[str, Any] = {
    "ltcg_equity_rate": 0.125,
    "stcg_equity_rate": 0.20,
    "ltcg_other_rate": 0.125,
    "ltcg_equity_exemption": 125000,
    "stcg_debt_rate": 0.30,
    "equity_ltcg_days": 365,
    # 24 months, not 36. Finance (No. 2) Act 2024 set a single 24-month long-term
    # threshold for every non-equity capital asset from 23-Jul-2024; the old 36-month
    # figure taxed genuinely long-term debt gains as short-term.
    "debt_ltcg_days": 730,
    # Gold/commodity and international funds: non-equity, so 24 months, but NOT
    # Section 50AA specified funds, so they keep an LTCG concept.
    "other_ltcg_days": 730,
    "elss_lockin_days": 1095,
    "debt_regime_cutoff": "2023-04-01",
    "grandfather_date": "2018-01-31",
}


def _load() -> Dict[str, Any]:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception as e:
        logger.error("[STATUTORY] cannot read %s (%s); using built-in fallback rates", _PATH, e)
        return dict(_FALLBACK)

    # Fill rather than replace: a file missing one key should not lose the other ten.
    merged = dict(_FALLBACK)
    merged.update(loaded)
    missing = [k for k in _FALLBACK if k not in loaded]
    if missing:
        logger.warning("[STATUTORY] capital_gains.json missing %s; defaulted", missing)
    return merged


#: The raw statutory block, in the same shape tax_rules.json used to carry.
CAPITAL_GAINS: Dict[str, Any] = _load()


#: The Mutual Funds-facing view, under the UPPER_SNAKE names that domain already uses.
#: A projection rather than a second source: change a number in capital_gains.json and
#: both this and CAPITAL_GAINS move together.
TAX_RATES: Dict[str, Any] = {
    "LTCG_EQUITY":        CAPITAL_GAINS["ltcg_equity_rate"],
    "STCG_EQUITY":        CAPITAL_GAINS["stcg_equity_rate"],
    "LTCG_EXEMPTION":     CAPITAL_GAINS["ltcg_equity_exemption"],
    "STCG_DEBT":          CAPITAL_GAINS["stcg_debt_rate"],
    "EQUITY_LTCG_DAYS":   CAPITAL_GAINS["equity_ltcg_days"],
    "DEBT_LTCG_DAYS":     CAPITAL_GAINS["debt_ltcg_days"],
    "OTHER_LTCG_DAYS":    CAPITAL_GAINS["other_ltcg_days"],
    "ELSS_LOCKIN_DAYS":   CAPITAL_GAINS["elss_lockin_days"],
    "DEBT_REGIME_CUTOFF": CAPITAL_GAINS["debt_regime_cutoff"],
}
