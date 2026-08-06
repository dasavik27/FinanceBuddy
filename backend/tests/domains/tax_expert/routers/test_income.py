"""Tax income router."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from domains.tax_expert import computation_cache, tax_sessions
from domains.tax_expert.routers import income as income_router
from shared import identity
from shared.identity import Caller

USER_ID = "00000000-0000-0000-0000-0000000000ff"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="tax@test.com")
TEST_PAN = "ABCDE1234F"
OWNER_CALLER = Caller(
    user_id=USER_ID, pan=TEST_PAN, status="active", role="user", email="tax@example.test"
)

SAMPLE_AIS = {
    "fy": "2025-26",
    "personal": {"pan": "ABCDE1234F", "name": "Test User"},
    "salary": {
        "gross": 1_800_000,
        "employer": "Acme",
        "tds_deducted": 150_000,
        "quarterly": [{"quarter": "Q1", "amount": 450_000}],
    },
    "dividends": [{"sr": 1, "amount": 25_000}],
    "interest_savings": [{"sr": 1, "amount": 12_000}],
    "interest_deposits": [{"sr": 1, "amount": 48_000}],
    "interest_others": [{"sr": 1, "amount": 3_000}],
    "misc_income": [{"sr": 1, "amount": 7_500}],
    "refunds": [{"sr": 1, "amount": 5_000}],
    "capital_gains_equity": [],
}


def _sample_computation():
    return {
        "total_tax": 250_000,
        "taxable_normal_income": 1_500_000,
        "refund_or_due": -10_000,
        "total_deductions": 200_000,
        "income_heads": {
            "salary": {"gross": 1_800_000, "std_deduction": 75_000},
            "other_sources": {
                "dividends": 25_000,
                "savings_interest": 12_000,
                "fd_interest": 48_000,
                "other_interest": 3_000,
            },
            "misc_income": {"total": 7_500},
            "capital_gains": {},
        },
        "dividends_detail": [{"sr": 1, "amount": 25_000}],
        "interest_deposits_detail": [{"sr": 1, "amount": 48_000}],
        "salary_quarterly": SAMPLE_AIS["salary"]["quarterly"],
        "refunds": SAMPLE_AIS["refunds"],
    }


@pytest.fixture(autouse=True)
def clean_tax_state():
    computation_cache.clear_all()
    tax_sessions.clear_all()
    tax_sessions._sessions_loaded = True
    yield
    computation_cache.clear_all()
    tax_sessions.clear_all()


@pytest.fixture
def tax_session_id():
    sid = "sess-tax-1"
    tax_sessions._tax_sessions[sid] = {
        "user_id": USER_ID,
        "ais_data": SAMPLE_AIS,
        "overrides": {"manual_tds": 1000},
        "reconciliation_flags": {"zero_cost": []},
    }
    return sid


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
def tax_session_id_integration(sample_ais):
    with identity.identity_scope(OWNER_CALLER):
        sid = tax_sessions.create_tax_session(sample_ais)
        tax_sessions.update_overrides(sid, {"bf_losses": {"ltcl": 50_000, "stcl": 10_000}})
    return sid


def test_income_router_not_found():
    with pytest.raises(HTTPException) as exc:
        income_router.get_tax_income("missing")
    assert exc.value.status_code == 404

def test_income_router_success(monkeypatch, tax_session_id):
    monkeypatch.setattr(
        income_router, "get_computation",
        lambda sid, sess, regime: _sample_computation(),
    )

    body = income_router.get_tax_income(tax_session_id, regime="new")
    assert body["salary"]["gross"] == 1_800_000
    assert body["total_dividends"] == 25_000
    assert body["total_savings_interest"] == 12_000
    assert body["total_fd_interest"] == 48_000
    assert body["total_misc_income"] == 7_500
    assert body["personal"]["pan"] == "ABCDE1234F"

def test_income_totals_match_engine_mocked(client, tax_session_id_integration):
    sid = tax_session_id_integration
    summary = client.get(f"/tax-expert/{sid}/tax/summary").json()
    income = client.get(f"/tax-expert/{sid}/tax/income").json()

    other = summary["income_heads"]["other_sources"]
    assert income["total_dividends"] == other["dividends"]
    assert income["total_savings_interest"] == other["savings_interest"]
    assert income["total_fd_interest"] == other["fd_interest"]
    assert income["total_other_interest"] == other["other_interest"]
    assert income["total_misc_income"] == summary["income_heads"]["misc_income"]["total"]

