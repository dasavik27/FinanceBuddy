"""Capital gains router — unit and integration tests."""

import io
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from domains.tax_expert import tax_sessions
from domains.tax_expert.routers import capital_gains
from shared import identity
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="tax@test.com", pan="ABCDE1234F")
TEST_PAN = "ABCDE1234F"
OWNER_USER_ID = "00000000-0000-0000-0000-0000000000ff"
OWNER_CALLER = Caller(
    user_id=OWNER_USER_ID, pan=TEST_PAN, status="active", role="user", email="tax@example.test"
)


@pytest.fixture(autouse=True)
def _clean_tax_sessions():
    from domains.tax_expert import computation_cache

    computation_cache.clear_all()
    tax_sessions.clear_all()
    yield
    computation_cache.clear_all()
    tax_sessions.clear_all()


def _sample_ais():
    return {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F", "name": "Test User"},
        "salary": {"gross": 1_200_000, "tds_deducted": 100_000},
        "capital_gains_equity": [
            {"sr": 1, "security": "RELIANCE", "type": "LTCG", "gain": 300_000,
             "consideration": 500_000, "cost": 200_000},
        ],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
    }


@pytest.fixture
def client(signed_in):
    return TestClient(main.app, headers=signed_in)


@pytest.fixture
def sample_ais():
    return {
        "fy": "2025-26",
        "personal": {"pan": TEST_PAN, "name": "Phase Two Test"},
        "salary": {
            "gross": 1_800_000,
            "tds_deducted": 150_000,
            "employer": "Acme",
            "quarterly": [
                {"quarter": "Q1", "amount": 450_000, "tds": 37_500},
                {"quarter": "Q2", "amount": 450_000, "tds": 37_500},
            ],
        },
        "dividends": [{"sr": 1, "amount": 25_000}, {"sr": 2, "amount": 15_000}],
        "interest_savings": [{"sr": 1, "amount": 12_000}],
        "interest_deposits": [{"sr": 1, "amount": 48_000}],
        "interest_others": [{"sr": 1, "amount": 3_000}],
        "misc_income": [{"sr": 1, "amount": 7_500}],
        "capital_gains_equity": [
            {
                "sr": 1, "security": "RELIANCE", "type": "LTCG",
                "quantity": 100, "consideration": 500_000, "cost": 100_000,
                "gain": 400_000, "fmv_31jan2018": 300_000, "acquired_date": "2015-06-01",
            },
            {
                "sr": 2, "security": "TCS", "type": "STCG",
                "quantity": 50, "consideration": 200_000, "cost": 150_000, "gain": 50_000,
            },
        ],
        "capital_gains_mf_equity": [
            {
                "sr": 1, "security": "AXIS BLUECHIP", "type": "LTCG",
                "quantity": 500, "consideration": 300_000, "cost": 200_000, "gain": 100_000,
            },
        ],
        "capital_gains_mf_other": [
            {
                "sr": 1, "security": "HDFC DEBT FUND", "type": "LTCG",
                "quantity": 100, "consideration": 150_000, "cost": 100_000, "gain": 50_000,
                "is_debt": True, "acquired_date": "2023-09-01",
            },
        ],
        "cg_real_estate": [], "cg_unlisted": [], "cg_bonds_gold": [],
        "refunds": [{"sr": 1, "amount": 5_000, "financial_year": "2024-25"}],
    }


@pytest.fixture
def tax_session_id(sample_ais):
    with identity.identity_scope(OWNER_CALLER):
        sid = tax_sessions.create_tax_session(sample_ais)
        tax_sessions.update_overrides(sid, {"bf_losses": {"ltcl": 50_000, "stcl": 10_000}})
    return sid


def test_capital_gains_router_list_and_errors(monkeypatch):
    from domains.tax_expert.routers.capital_gains import get_capital_gains

    with pytest.raises(HTTPException):
        get_capital_gains("missing", regime="new")

    with identity_scope(CALLER):
        sid = tax_sessions.create_tax_session(_sample_ais())
        monkeypatch.setattr(
            "domains.tax_expert.routers.capital_gains.get_computation",
            lambda session_id, session, regime: {
                "income_heads": {"capital_gains": {"ltcg_equity": 100000, "stcg_equity": 0}},
            },
        )
        payload = get_capital_gains(sid, regime="new")
        assert "summary" in payload
        assert payload["equity_shares_count"] >= 1

def test_capital_gains_router_update_cost(monkeypatch):
    ais = _sample_ais()
    ais["capital_gains_equity"] = [
        {"sr": 1, "security": "RELIANCE", "type": "LTCG", "gain": 300_000, "consideration": 500_000, "cost": 200_000},
    ]
    with identity_scope(CALLER):
        sid = tax_sessions.create_tax_session(ais)
        out = capital_gains.update_transaction_cost(
            sid,
            capital_gains.TransactionCostUpdate(category="capital_gains_equity", sr=1, new_cost=150_000),
        )
    assert out["status"] == "success"
    assert out["transaction"]["cost"] == 150_000
    assert out["transaction"]["patched"] is True

def test_capital_gains_matches_summary_mocked(client, tax_session_id):
    """Endpoints /tax/summary and /tax/capital-gains must agree on capital gains breakdown."""
    summary = client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=new").json()
    cg = client.get(f"/tax-expert/{tax_session_id}/tax/capital-gains").json()

    engine_cg = summary["income_heads"]["capital_gains"]
    for field in ("ltcg_equity", "stcg_equity", "ltcg_other", "stcg_other",
                  "ltcg_equity_taxable", "ltcg_equity_exemption"):
        assert cg["summary"][field] == engine_cg[field], (
            f"{field} diverges: capital-gains={cg['summary'][field]} summary={engine_cg[field]}"
        )

def test_engine_rules_applied_mocked(client, tax_session_id):
    """Ensure grandfathering, Sec 50AA slab taxation and B/F losses are applied."""
    cg = client.get(f"/tax-expert/{tax_session_id}/tax/capital-gains").json()["summary"]

    naive_ltcg_equity = 400_000 + 100_000
    assert cg["ltcg_equity"] != naive_ltcg_equity
    assert cg["grandfather_benefit"] > 0
    assert cg["ltcg_other"] == 0
    assert cg["slab_taxed_cg"] == 50_000

