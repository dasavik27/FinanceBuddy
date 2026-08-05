"""
test_tax_expert_mocked.py

Mock-based equivalents of test_tax_expert_phase2.py and test_tax_sessions_concurrency.py.
Tests tax computation caching, capital-gains consistency, session concurrency,
details pagination, and regime comparison without requiring live Postgres.
"""

import threading
import uuid
import pytest
from fastapi.testclient import TestClient

import main
from domains.tax_expert import computation_cache, tax_sessions
from shared import identity
from shared.identity import Caller

TEST_PAN = "ABCDE1234F"
OWNER_USER_ID = "00000000-0000-0000-0000-0000000000ff"
OWNER_CALLER = Caller(
    user_id=OWNER_USER_ID, pan=TEST_PAN, status="active", role="user", email="tax@example.test"
)


@pytest.fixture(autouse=True)
def clean_tax_state():
    computation_cache.clear_all()
    tax_sessions.clear_all()
    yield
    computation_cache.clear_all()
    tax_sessions.clear_all()


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


def test_income_totals_match_engine_mocked(client, tax_session_id):
    summary = client.get(f"/tax-expert/{tax_session_id}/tax/summary").json()
    income = client.get(f"/tax-expert/{tax_session_id}/tax/income").json()

    other = summary["income_heads"]["other_sources"]
    assert income["total_dividends"] == other["dividends"]
    assert income["total_savings_interest"] == other["savings_interest"]
    assert income["total_fd_interest"] == other["fd_interest"]
    assert income["total_other_interest"] == other["other_interest"]
    assert income["total_misc_income"] == summary["income_heads"]["misc_income"]["total"]


def test_computation_is_memoized_mocked(client, tax_session_id):
    computation_cache.clear_all()

    client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=new")
    after_first = computation_cache.cache_stats()["misses"]

    client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=new")
    assert computation_cache.cache_stats()["misses"] == after_first
    assert computation_cache.cache_stats()["hits"] >= 1


def test_compare_regimes_reuses_cache_mocked(client, tax_session_id):
    computation_cache.clear_all()

    client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=new")
    client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=old")
    misses_before = computation_cache.cache_stats()["misses"]

    client.get(f"/tax-expert/{tax_session_id}/tax/compare-regimes")
    assert computation_cache.cache_stats()["misses"] == misses_before


def test_mutation_invalidates_cache_mocked(client, tax_session_id):
    before = client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=old").json()

    client.post(
        f"/tax-expert/{tax_session_id}/tax/recalculate?regime=old",
        json={"deductions": {"80c": 150_000}},
    )
    after = client.get(f"/tax-expert/{tax_session_id}/tax/summary?regime=old").json()

    assert after["total_deductions"] != before["total_deductions"]
    assert after["total_tax"] < before["total_tax"]


def test_summary_payload_structure_mocked(client, tax_session_id):
    summary = client.get(f"/tax-expert/{tax_session_id}/tax/summary").json()

    for stripped in ("dividends_detail", "cg_equity_detail", "cg_mf_equity_detail",
                     "interest_deposits_detail", "salary_quarterly"):
        assert stripped not in summary

    assert "refunds" in summary
    assert "reconciliation_flags" in summary
    assert "overrides" in summary
    assert summary["income_heads"]["salary"]["gross"] == 1_800_000


def test_details_endpoint_pagination_mocked(client, tax_session_id):
    resp = client.get(f"/tax-expert/{tax_session_id}/tax/details/dividends")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 2

    paged = client.get(f"/tax-expert/{tax_session_id}/tax/details/dividends?offset=1&limit=1").json()
    assert paged["total"] == 2
    assert len(paged["rows"]) == 1

    assert client.get(f"/tax-expert/{tax_session_id}/tax/details/nonsense").status_code == 400


def test_session_version_bumps_on_mutation_mocked(tax_session_id):
    v0 = tax_sessions.get_session_version(tax_session_id)
    tax_sessions.update_overrides(tax_session_id, {"manual_tds": 1234})
    assert tax_sessions.get_session_version(tax_session_id) > v0


def test_concurrent_tax_session_mutations():
    """
    Stress-test concurrent read/write on the tax session store
    to guarantee no RuntimeError: OrderedDict mutated during iteration.
    """
    errors = []
    stop = threading.Event()

    def writer():
        try:
            for i in range(20):
                with identity.identity_scope(OWNER_CALLER):
                    sid = tax_sessions.create_tax_session({
                        "personal": {"pan": f"PAN{i}"},
                        "fy": "2025-26",
                    })
                    tax_sessions.update_overrides(sid, {"manual_tds": i * 100})
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            while not stop.is_set():
                sessions = tax_sessions.list_sessions()
                for sid, _ in sessions:
                    tax_sessions.get_tax_session(sid)
        except Exception as e:
            errors.append(e)

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)

    t_reader.start()
    t_writer.start()

    t_writer.join(timeout=5)
    stop.set()
    t_reader.join(timeout=5)

    assert len(errors) == 0, f"Concurrent tax session mutations caused errors: {errors}"
