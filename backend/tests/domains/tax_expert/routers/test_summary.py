"""Tax summary router and computation caching."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from domains.tax_expert import computation_cache, tax_sessions
from domains.tax_expert.routers import summary as summary_router
from shared import identity
from shared.identity import Caller, identity_scope

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


def test_summary_cache_stats():
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            summary_router.get_cache_stats()
        assert exc.value.status_code == 401

    with identity_scope(CALLER):
        stats = summary_router.get_cache_stats()
        assert "hits" in stats
        assert "misses" in stats

def test_summary_details_pagination(tax_session_id):
    body = summary_router.get_detail_rows(tax_session_id, "dividends", offset=0, limit=1)
    assert body["total"] == 1
    assert len(body["rows"]) == 1

    quarterly = summary_router.get_detail_rows(tax_session_id, "salary_quarterly", offset=0, limit=200)
    assert quarterly["total"] == 1

    with pytest.raises(HTTPException) as exc:
        summary_router.get_detail_rows(tax_session_id, "not-a-bucket", offset=0, limit=200)
    assert exc.value.status_code == 400

def test_summary_response_helper():
    result = _sample_computation()
    session = {"overrides": {"x": 1}, "reconciliation_flags": {"flag": True}}

    payload = summary_router.summary_response(result, session)
    assert "dividends_detail" not in payload
    assert "salary_quarterly" not in payload
    assert payload["overrides"] == {"x": 1}
    assert payload["reconciliation_flags"] == {"flag": True}
    assert payload["refunds"] == SAMPLE_AIS["refunds"]

    no_flags = summary_router.summary_response(result, session, include_flags=False)
    assert "reconciliation_flags" not in no_flags

def test_summary_router_endpoints(monkeypatch, tax_session_id):
    monkeypatch.setattr(
        summary_router, "get_computation",
        lambda sid, sess, regime: {**_sample_computation(), "total_tax": 200_000 if regime == "new" else 220_000},
    )
    monkeypatch.setattr(summary_router, "update_overrides", MagicMock())

    summary = summary_router.get_tax_summary(tax_session_id)
    assert summary["total_tax"] == 200_000
    assert "overrides" in summary

    recalc = summary_router.recalculate_tax(
        tax_session_id,
        summary_router.RecalculateInput(deductions={"80c": 150_000}),
    )
    assert recalc["total_tax"] == 200_000
    assert "reconciliation_flags" not in recalc
    summary_router.update_overrides.assert_called_once()

    compare = summary_router.compare_regimes(tax_session_id)
    assert compare["recommended"] in ("new", "old")
    assert compare["savings"] == 20_000

def test_summary_router_not_found():
    with pytest.raises(HTTPException) as exc:
        summary_router.get_tax_summary("missing")
    assert exc.value.status_code == 404

def test_compare_regimes_reuses_cache_mocked(client, tax_session_id_integration):
    sid = tax_session_id_integration
    computation_cache.clear_all()

    client.get(f"/tax-expert/{sid}/tax/summary?regime=new")
    client.get(f"/tax-expert/{sid}/tax/summary?regime=old")
    misses_before = computation_cache.cache_stats()["misses"]

    client.get(f"/tax-expert/{sid}/tax/compare-regimes")
    assert computation_cache.cache_stats()["misses"] == misses_before

def test_computation_is_memoized_mocked(client, tax_session_id_integration):
    sid = tax_session_id_integration
    computation_cache.clear_all()

    client.get(f"/tax-expert/{sid}/tax/summary?regime=new")
    after_first = computation_cache.cache_stats()["misses"]

    client.get(f"/tax-expert/{sid}/tax/summary?regime=new")
    assert computation_cache.cache_stats()["misses"] == after_first
    assert computation_cache.cache_stats()["hits"] >= 1

def test_details_endpoint_pagination_mocked(client, tax_session_id_integration):
    sid = tax_session_id_integration
    resp = client.get(f"/tax-expert/{sid}/tax/details/dividends")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 2

    paged = client.get(f"/tax-expert/{sid}/tax/details/dividends?offset=1&limit=1").json()
    assert paged["total"] == 2
    assert len(paged["rows"]) == 1

    assert client.get(f"/tax-expert/{sid}/tax/details/nonsense").status_code == 400

def test_mutation_invalidates_cache_mocked(client, tax_session_id_integration):
    sid = tax_session_id_integration
    before = client.get(f"/tax-expert/{sid}/tax/summary?regime=old").json()

    client.post(
        f"/tax-expert/{sid}/tax/recalculate?regime=old",
        json={"deductions": {"80c": 150_000}},
    )
    after = client.get(f"/tax-expert/{sid}/tax/summary?regime=old").json()

    assert after["total_deductions"] != before["total_deductions"]
    assert after["total_tax"] < before["total_tax"]

def test_summary_payload_structure_mocked(client, tax_session_id_integration):
    sid = tax_session_id_integration
    summary = client.get(f"/tax-expert/{sid}/tax/summary").json()

    for stripped in ("dividends_detail", "cg_equity_detail", "cg_mf_equity_detail",
                     "interest_deposits_detail", "salary_quarterly"):
        assert stripped not in summary

    assert "refunds" in summary
    assert "reconciliation_flags" in summary
    assert "overrides" in summary
    assert summary["income_heads"]["salary"]["gross"] == 1_800_000

