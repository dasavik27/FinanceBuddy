"""
Phase 2 regression tests for the Tax Expert domain.

Covers the three behaviours the Phase 2 refactor is responsible for:
  1. /tax/capital-gains and /tax/summary agree on ltcg_equity (they did not before).
  2. compute_tax is memoized, and mutations invalidate the memo.
  3. /tax/summary no longer ships bulk detail lists, and /tax/details serves them.
"""

import pytest
from fastapi.testclient import TestClient

import main
from domains.tax_expert import computation_cache, tax_sessions


# A syntactically valid PAN: the identity middleware rejects malformed ones, so the
# fixture's owner and the client's asserted identity have to be a real PAN shape.
TEST_PAN = "ABCDE1234F"


@pytest.fixture
def client():
    # Sessions below are owned by TEST_PAN, and reading an owned session now requires
    # asserting that identity - the same header the frontend's axios interceptor sends.
    return TestClient(main.app, headers={"X-User-PAN": TEST_PAN})


@pytest.fixture
def session_id():
    """A session whose capital gains exercise grandfathering, Sec 50AA and B/F losses.

    Each of these is a rule the old duplicated aggregation in capital_gains.py
    ignored, so a naive sum(gain) diverges from the engine on this data.
    """
    ais = {
        "fy": "2025-26",
        "personal": {"pan": TEST_PAN, "name": "Phase Two Test"},
        "salary": {"gross": 1_800_000, "tds_deducted": 150_000, "employer": "Acme", "quarterly": [
            {"quarter": "Q1", "amount": 450_000, "tds": 37_500},
            {"quarter": "Q2", "amount": 450_000, "tds": 37_500},
        ]},
        "dividends": [{"sr": 1, "amount": 25_000}, {"sr": 2, "amount": 15_000}],
        "interest_savings": [{"sr": 1, "amount": 12_000}],
        "interest_deposits": [{"sr": 1, "amount": 48_000}],
        "interest_others": [{"sr": 1, "amount": 3_000}],
        "misc_income": [{"sr": 1, "amount": 7_500}],
        "capital_gains_equity": [
            # Pre-2018 lot carrying an FMV -> grandfathering must reduce the gain.
            {
                "sr": 1, "security": "RELIANCE", "type": "LTCG",
                "quantity": 100, "consideration": 500_000, "cost": 100_000,
                "gain": 400_000,
                "fmv_31jan2018": 300_000, "acquired_date": "2015-06-01",
            },
            {"sr": 2, "security": "TCS", "type": "STCG",
             "quantity": 50, "consideration": 200_000, "cost": 150_000, "gain": 50_000},
        ],
        "capital_gains_mf_equity": [
            {"sr": 1, "security": "AXIS BLUECHIP", "type": "LTCG",
             "quantity": 500, "consideration": 300_000, "cost": 200_000, "gain": 100_000},
        ],
        "capital_gains_mf_other": [
            # Sec 50AA specified fund: slab-taxed, must NOT land in ltcg_other.
            {"sr": 1, "security": "HDFC DEBT FUND", "type": "LTCG",
             "quantity": 100, "consideration": 150_000, "cost": 100_000, "gain": 50_000,
             "is_debt": True, "acquired_date": "2023-09-01"},
        ],
        "cg_real_estate": [], "cg_unlisted": [], "cg_bonds_gold": [],
        "refunds": [{"sr": 1, "amount": 5_000, "financial_year": "2024-25"}],
    }
    sid = tax_sessions.create_tax_session(ais, pan_id=TEST_PAN)
    # Brought-forward losses: another rule the old aggregation skipped.
    tax_sessions.update_overrides(sid, {"bf_losses": {"ltcl": 50_000, "stcl": 10_000}})
    yield sid
    tax_sessions.delete_tax_session(sid)


def test_capital_gains_matches_summary(client, session_id):
    """The divergence bug: both endpoints must report identical capital gains."""
    summary = client.get(f"/tax-expert/{session_id}/tax/summary?regime=new").json()
    cg = client.get(f"/tax-expert/{session_id}/tax/capital-gains").json()

    engine_cg = summary["income_heads"]["capital_gains"]
    for field in ("ltcg_equity", "stcg_equity", "ltcg_other", "stcg_other",
                  "ltcg_equity_taxable", "ltcg_equity_exemption"):
        assert cg["summary"][field] == engine_cg[field], (
            f"{field} diverges: capital-gains={cg['summary'][field]} "
            f"summary={engine_cg[field]}"
        )


def test_engine_rules_are_actually_applied(client, session_id):
    """Guards the test data itself: a naive sum would give a different answer.

    Without this, test_capital_gains_matches_summary could pass trivially on data
    where grandfathering/50AA/B-F losses happen to be no-ops.
    """
    cg = client.get(f"/tax-expert/{session_id}/tax/capital-gains").json()["summary"]

    naive_ltcg_equity = 400_000 + 100_000          # raw gains, no grandfathering
    assert cg["ltcg_equity"] != naive_ltcg_equity, "grandfathering/B-F losses not applied"
    assert cg["grandfather_benefit"] > 0, "expected grandfathering to reduce the gain"
    # The Sec 50AA debt fund must be excluded from ltcg_other and slab-taxed instead.
    assert cg["ltcg_other"] == 0, f"Sec 50AA fund leaked into ltcg_other: {cg['ltcg_other']}"
    assert cg["slab_taxed_cg"] == 50_000


def test_income_totals_match_engine(client, session_id):
    summary = client.get(f"/tax-expert/{session_id}/tax/summary").json()
    income = client.get(f"/tax-expert/{session_id}/tax/income").json()

    other = summary["income_heads"]["other_sources"]
    assert income["total_dividends"] == other["dividends"]
    assert income["total_savings_interest"] == other["savings_interest"]
    assert income["total_fd_interest"] == other["fd_interest"]
    assert income["total_other_interest"] == other["other_interest"]
    assert income["total_misc_income"] == summary["income_heads"]["misc_income"]["total"]


def test_computation_is_memoized(client, session_id):
    """A repeat request must not re-run the engine."""
    computation_cache.clear_all()

    client.get(f"/tax-expert/{session_id}/tax/summary?regime=new")
    after_first = computation_cache.cache_stats()["misses"]

    client.get(f"/tax-expert/{session_id}/tax/summary?regime=new")
    assert computation_cache.cache_stats()["misses"] == after_first, "second call re-ran engine"
    assert computation_cache.cache_stats()["hits"] >= 1


def test_compare_regimes_reuses_cached_results(client, session_id):
    """compare-regimes used to run the engine twice unconditionally."""
    computation_cache.clear_all()

    client.get(f"/tax-expert/{session_id}/tax/summary?regime=new")
    client.get(f"/tax-expert/{session_id}/tax/summary?regime=old")
    misses_before = computation_cache.cache_stats()["misses"]

    client.get(f"/tax-expert/{session_id}/tax/compare-regimes")
    assert computation_cache.cache_stats()["misses"] == misses_before, (
        "compare-regimes recomputed instead of reusing both cached regimes"
    )


def test_mutation_invalidates_cache(client, session_id):
    """Stale memoization would be worse than no memoization — prove writes bust it."""
    before = client.get(f"/tax-expert/{session_id}/tax/summary?regime=old").json()

    client.post(
        f"/tax-expert/{session_id}/tax/recalculate?regime=old",
        json={"deductions": {"80c": 150_000}},
    )
    after = client.get(f"/tax-expert/{session_id}/tax/summary?regime=old").json()

    assert after["total_deductions"] != before["total_deductions"], "cache served stale result"
    assert after["total_tax"] < before["total_tax"], "80C deduction did not reduce old-regime tax"


def test_summary_omits_bulk_details_but_keeps_refunds(client, session_id):
    summary = client.get(f"/tax-expert/{session_id}/tax/summary").json()

    for stripped in ("dividends_detail", "cg_equity_detail", "cg_mf_equity_detail",
                     "interest_deposits_detail", "salary_quarterly"):
        assert stripped not in summary, f"{stripped} still in summary payload"

    # Fields the UI reads must survive.
    assert "refunds" in summary
    assert "reconciliation_flags" in summary
    assert "overrides" in summary
    assert summary["income_heads"]["salary"]["gross"] == 1_800_000


def test_details_endpoint_serves_stripped_lists(client, session_id):
    resp = client.get(f"/tax-expert/{session_id}/tax/details/dividends")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 2

    paged = client.get(f"/tax-expert/{session_id}/tax/details/dividends?offset=1&limit=1").json()
    assert paged["total"] == 2
    assert len(paged["rows"]) == 1

    assert client.get(f"/tax-expert/{session_id}/tax/details/nonsense").status_code == 400


def test_session_version_bumps_on_mutation(session_id):
    v0 = tax_sessions.get_session_version(session_id)
    tax_sessions.update_overrides(session_id, {"manual_tds": 1234})
    assert tax_sessions.get_session_version(session_id) > v0


def test_lru_bound_caps_resident_sessions(monkeypatch):
    """The store must not grow without bound — that was the 512 MB failure mode."""
    monkeypatch.setattr(tax_sessions, "MAX_SESSIONS", 3)
    created = [
        tax_sessions.create_tax_session({"personal": {"pan": f"BOUND{i}"}}, pan_id=f"BOUND{i}")
        for i in range(6)
    ]
    # Only the cap's worth stay in memory...
    assert len(tax_sessions.list_sessions()) <= 3
    # ...and the most recent is one of them.
    assert tax_sessions.get_tax_session(created[-1]) is not None
    for sid in created:
        tax_sessions.delete_tax_session(sid)


def test_eviction_is_not_data_loss(monkeypatch):
    """
    An LRU-evicted session must still be retrievable.

    Eviction used to delete the SQLite row as well, which made it destructive: the
    row was the only durable copy, so the user's uploaded AIS was simply gone and
    they had to re-upload. This asserts the rehydration path that makes a small
    resident cap safe.
    """
    monkeypatch.setattr(tax_sessions, "MAX_SESSIONS", 2)
    first = tax_sessions.create_tax_session(
        {"personal": {"pan": "EVICT0"}, "fy": "2025-26"}, pan_id="EVICT0"
    )
    later = [
        tax_sessions.create_tax_session({"personal": {"pan": f"EVICT{i}"}}, pan_id=f"EVICT{i}")
        for i in range(1, 4)
    ]

    resident_ids = {sid for sid, _ in tax_sessions.list_sessions()}
    assert first not in resident_ids, "expected the oldest session to be evicted from memory"

    restored = tax_sessions.get_tax_session(first)
    assert restored is not None, "evicted session was destroyed instead of rehydrated"
    assert restored["ais_data"]["fy"] == "2025-26"

    for sid in [first, *later]:
        tax_sessions.delete_tax_session(sid)


def test_clear_all_does_not_brick_the_store():
    """
    clear_all() left _sessions_loaded True, so _ensure_loaded() never reloaded and
    every session 404'd until the process restarted - even with rows intact on disk.
    """
    sid = tax_sessions.create_tax_session(
        {"personal": {"pan": "CLEARME"}, "fy": "2025-26"}, pan_id="CLEARME"
    )
    tax_sessions.clear_all()
    assert tax_sessions.get_tax_session(sid) is not None, "store did not recover after clear_all()"
    tax_sessions.delete_tax_session(sid)
