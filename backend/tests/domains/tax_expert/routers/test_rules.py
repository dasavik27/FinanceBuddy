"""Tax rules projection router."""

from domains.tax_expert import tax_engine
from domains.tax_expert.routers import rules


def test_rules_router_projection():
    payload = rules.get_client_tax_rules()
    assert "capital_gains" in payload
    assert "deductions" in payload
    assert "ui_tooltips" in payload
    assert payload["capital_gains"]["ltcg_equity_rate"] == tax_engine.TAX_RULES["capital_gains"]["ltcg_equity_rate"]

