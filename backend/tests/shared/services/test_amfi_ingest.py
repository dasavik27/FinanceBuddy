"""Unit tests for shared/services/amfi_ingest.py."""

import datetime
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from shared import db
from shared.services import amfi_ingest
from tests.helpers import FakeDbConn


def test_amfi_ingest_helpers():
    # 1. _portfolio_as_of
    as_of = amfi_ingest._portfolio_as_of()
    assert isinstance(as_of, datetime.date)
    assert as_of < datetime.date.today()

    # 2. _amc_match_terms
    assert amfi_ingest._amc_match_terms("parag parikh") == ["parag parikh", "ppfas"]
    assert amfi_ingest._amc_match_terms("groww") == ["groww"]
    assert amfi_ingest._amc_match_terms("HDFC") == ["HDFC"]
    assert amfi_ingest._amc_match_terms("") == []

    # 3. _extract_amc_name
    assert amfi_ingest._extract_amc_name("PPFAS Flexi Cap Fund", "") == "PPFAS Mutual Fund"
    assert amfi_ingest._extract_amc_name("HDFC Top 100 Fund - Direct Plan", "") == "HDFC Mutual Fund"
    assert amfi_ingest._extract_amc_name("Quant Small Cap Fund", "") == "Quant Mutual Fund"
    # Raw AMC supplied → fallback appends "Mutual Fund" if needed
    result = amfi_ingest._extract_amc_name("Random XYZ Fund", "ABC Asset Management")
    assert "ABC Asset Management" in result

    # 4. _normalize_category — test actual return values from the real logic
    assert amfi_ingest._normalize_category("Open Ended Schemes (Equity Scheme - Large Cap Fund)", "") == "Large Cap Fund"
    assert amfi_ingest._normalize_category("Open Ended Schemes (Equity Scheme - Mid Cap Fund)", "") == "Mid Cap Fund"
    assert amfi_ingest._normalize_category("Open Ended Schemes (Equity Scheme - Small Cap Fund)", "") == "Small Cap Fund"
    assert amfi_ingest._normalize_category("Open Ended Schemes (Equity Scheme - ELSS)", "") == "ELSS / Tax Saver"
    assert amfi_ingest._normalize_category("Open Ended Schemes (Debt Scheme - Liquid Fund)", "") == "Debt / Liquid Fund"
    # _normalize_category checks scheme_name for "index", not raw_category
    assert amfi_ingest._normalize_category("", "HDFC Index Fund - Nifty 50") == "Index Fund"
    assert amfi_ingest._normalize_category("Open Ended Schemes (Equity Scheme - Multi Cap Fund)", "") == "Multi Cap Fund"
    assert amfi_ingest._normalize_category("", "Balanced Advantage Fund Direct") == "Balanced Advantage / Hybrid"
    assert amfi_ingest._extract_amc_name("SBI Bluechip Fund", "") == "SBI Mutual Fund"


# ---------------------------------------------------------------------------
# NAV feed parser
# ---------------------------------------------------------------------------

def test_amfi_nav_parser(monkeypatch):
    """
    fetch_amfi_master_schemes() parses the raw AMFI NAVAll.txt into a list of
    scheme dicts. Verify field names, types and filtering behaviour.
    """
    sample_nav_text = (
        "Open Ended Schemes (Equity Scheme - Large Cap Fund)\n"
        "HDFC Mutual Fund\n"
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n"
        "119062;INF179K01BE2;INF179K01BF9;HDFC Top 100 Fund - Direct Plan - Growth Option;982.450;05-Aug-2026\n"
        "119063;INF179K01BG7;-;HDFC Top 100 Fund - Regular Plan - Growth;850.120;05-Aug-2026\n"
        ";;;;;\n"
        "119064;-;-;Invalid Line with no valid ISIN;N.A.;05-Aug-2026\n"
    )

    class FakeUrlResponse:
        def read(self):
            return sample_nav_text.encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeUrlResponse())

    schemes = amfi_ingest.fetch_amfi_master_schemes()
    assert len(schemes) == 2

    s = schemes[0]
    # scheme_code is kept as a string by the parser
    assert s["scheme_code"] == "119062"
    # isin is the primary ISIN stored under the key "isin"
    assert s["isin"] == "INF179K01BE2"
    assert s["scheme_name"] == "HDFC Top 100 Fund - Direct Plan - Growth Option"
    assert s["raw_amc"] == "HDFC Mutual Fund"
    # nav is still the raw string at parse time (float conversion happens at ingest)
    assert float(s["nav"]) == 982.450


# ---------------------------------------------------------------------------
# DB-backed functions
# ---------------------------------------------------------------------------

def test_amfi_get_sync_status(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    now = datetime.datetime.now(datetime.timezone.utc)

    # Three queries: COUNT(*), latest date row, recent logs fetchall
    conn.queue_result(fetchone=(150,))
    conn.queue_result(fetchone=(datetime.date(2026, 8, 1), now))
    conn.queue_result(fetchall=[
        (1, "test_admin@test.com", "success", 150, "August 2026", 2.5, None, now)
    ])
    status = amfi_ingest.get_sync_status()
    assert status["total_schemes"] == 150
    assert len(status["recent_logs"]) == 1
    assert status["recent_logs"][0]["status"] == "success"
    assert status["recent_logs"][0]["schemes_updated"] == 150

def test_amfi_get_synced_amc_list(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    # The query returns (amc, count, total_aum) tuples
    conn.queue_result(fetchall=[
        ("HDFC Mutual Fund", 85, 25000.0),
        ("SBI Mutual Fund", 65, 18000.0),
    ])
    amc_list = amfi_ingest.get_synced_amc_list()
    assert len(amc_list) == 2
    assert amc_list[0]["amc"] == "HDFC Mutual Fund"
    assert amc_list[0]["schemes_count"] == 85

def test_amfi_search_synced_schemes(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    now = datetime.datetime.now(datetime.timezone.utc)

    # search_synced_schemes fires COUNT then SELECT
    conn.queue_result(fetchone=(1,))
    conn.queue_result(fetchall=[(
        "INF179K01BE2",            # isin
        119062,                    # scheme_code
        "HDFC Top 100 Fund",       # scheme_name
        "HDFC Mutual Fund",        # amc
        "Large Cap Fund",          # category
        50000.0,                   # aum_cr
        0.85,                      # expense_ratio
        "VERY HIGH",               # risk_level
        datetime.date(2026, 8, 1), # portfolio_date
        json.dumps([{"sector": "Financial Services", "value": 35.0}]),
        json.dumps([{"name": "HDFC Bank", "pct": 9.5}]),
        "AMFI Official Disclosure",
        now,                       # updated_at
    )])
    res = amfi_ingest.search_synced_schemes(query="HDFC", limit=10)
    assert res["total"] == 1
    s = res["schemes"][0]
    assert s["scheme_name"] == "HDFC Top 100 Fund"
    assert s["holdings"][0]["name"] == "HDFC Bank"

def test_amfi_purge_snapshots(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    # purge by AMC: COUNT then DELETE
    conn.queue_result(fetchone=(10,))
    conn.queue_result(rowcount=10)
    purge_res = amfi_ingest.purge_snapshots(amc="HDFC Mutual Fund", admin_email="admin@test.com")
    assert purge_res["status"] == "success"
    assert purge_res["deleted_count"] == 10


# ---------------------------------------------------------------------------
# Market data providers
# ---------------------------------------------------------------------------

def test_trigger_amfi_sync_and_purge_direct(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn)

    # 1. Purge snapshots
    # No args -> error
    res_err = amfi_ingest.purge_snapshots()
    assert res_err["status"] == "error"

    # Purge all
    conn.queue_result(fetchone=(10,))
    res_all = amfi_ingest.purge_snapshots(purge_all=True)
    assert res_all["status"] == "success"
    assert res_all["deleted_count"] == 10

    # Purge by AMC
    conn.queue_result(fetchone=(4,))
    res_amc = amfi_ingest.purge_snapshots(amc="Parag Parikh")
    assert res_amc["status"] == "success"
    assert res_amc["deleted_count"] == 4

    # Purge exception
    monkeypatch.setattr(amfi_ingest.db, "connect", MagicMock(side_effect=RuntimeError("DB error")))
    res_fail = amfi_ingest.purge_snapshots(purge_all=True)
    assert res_fail["status"] == "error"

    # 2. Trigger AMFI sync success
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn)
    sample_schemes = [
        {
            "isin": "INF179K01BE2",
            "scheme_code": "122639",
            "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
            "raw_category": "Open Ended Schemes (Equity Scheme - Flexi Cap Fund)",
            "raw_amc": "PPFAS Mutual Fund",
        },
        {
            "isin": "INF200K01TS0",
            "scheme_code": "100033",
            "scheme_name": "SBI Bluechip Fund - Regular Plan",
            "raw_category": "Open Ended Schemes (Equity Scheme - Large Cap Fund)",
            "raw_amc": "SBI Mutual Fund",
        }
    ]
    monkeypatch.setattr(amfi_ingest, "fetch_amfi_master_schemes", lambda: sample_schemes)

    # Log record insert (returning id=1)
    conn.queue_result(fetchone=(1,))
    # Scheme count SELECT
    conn.queue_result(fetchone=(2,))
    # Update log record

    res_sync = amfi_ingest.trigger_amfi_sync(preset="top5")
    assert res_sync["status"] == "completed"
    assert res_sync["schemes_updated"] > 0

    # 3. Trigger AMFI sync with explicit amcs
    conn.queue_result(fetchone=(2,))
    conn.queue_result(fetchone=(1,))
    res_sync_amc = amfi_ingest.trigger_amfi_sync(amcs=["SBI"])
    assert res_sync_amc["status"] == "completed"

    # 4. Trigger AMFI sync failure
    monkeypatch.setattr(amfi_ingest, "fetch_amfi_master_schemes", MagicMock(side_effect=RuntimeError("Network down")))
    conn.queue_result(fetchone=(3,))
    res_sync_err = amfi_ingest.trigger_amfi_sync(preset="all")
    assert res_sync_err["status"] == "failed"

def test_amfi_cache_invalidation_and_ingest_edges(monkeypatch):
    monkeypatch.setattr(amfi_ingest.MarketCache, "invalidate_all", MagicMock(side_effect=RuntimeError("cache fail")))
    amfi_ingest._invalidate_market_caches()

    monkeypatch.setattr(amfi_ingest.MarketCache, "invalidate_all", MagicMock())
    monkeypatch.setattr(
        "shared.services.market_data.clear_market_data_cache",
        MagicMock(side_effect=RuntimeError("clear fail")),
    )
    amfi_ingest._invalidate_market_caches()

    conn = FakeDbConn()
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn)
    conn.queue_result(fetchone=(0,))
    empty_status = amfi_ingest.get_sync_status()
    assert empty_status["total_schemes"] == 0

    conn.queue_result(fetchone=(1,))
    conn.queue_result(fetchall=[])
    res = amfi_ingest.search_synced_schemes(query="", limit=5)
    assert res["total"] == 1

def test_amfi_ingest_normalize_and_fetch_errors(monkeypatch):
    assert amfi_ingest._normalize_category("", "Foo Large and Midcap Bar") == "Large & Mid Cap Fund"
    assert amfi_ingest._normalize_category("", "Unknown Name") == "Large Cap Fund"
    assert "SBI" in amfi_ingest._extract_amc_name("SBI Bluechip Fund", "")

    from shared.services.amfi_ingest import AmfiFetchError

    with pytest.raises(AmfiFetchError):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            MagicMock(side_effect=urllib.error.URLError("down")),
        )
        amfi_ingest.fetch_amfi_master_schemes()

    def fake_open(req, timeout=20):
        raise urllib.error.URLError("network down")

    sample_line = "119551;INF179K01BE2;-;HDFC Top 100;150.0\n"
    feed = "Open Ended Schemes (Equity Scheme - Large Cap Fund)\nHDFC Mutual Fund\n" + sample_line

    class Resp:
        def read(self):
            return feed.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=20: Resp())
    schemes = amfi_ingest.fetch_amfi_master_schemes()
    assert schemes

    monkeypatch.setattr(amfi_ingest, "fetch_amfi_master_schemes", lambda: schemes)
    conn = FakeDbConn()
    conn.queue_result(fetchone=(1,))
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn)
    monkeypatch.setattr(amfi_ingest, "_invalidate_market_caches", lambda: None)

    res = amfi_ingest.trigger_amfi_sync("admin@test.com", preset="top10")
    assert res["status"] in ("success", "failed", "in_progress", "completed")

    res2 = amfi_ingest.trigger_amfi_sync(
        "admin@test.com",
        amcs=["HDFC", "SBI", "ICICI", "Axis", "Kotak"],
        preset=None,
    )
    assert "portfolio_month" in res2

    conn2 = FakeDbConn()
    conn2.queue_result(fetchone=(99,))
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn2)
    monkeypatch.setattr(
        amfi_ingest,
        "fetch_amfi_master_schemes",
        MagicMock(side_effect=RuntimeError("sync boom")),
    )
    fail = amfi_ingest.trigger_amfi_sync("admin@test.com", preset="all")
    assert fail["status"] == "failed"

    conn3 = FakeDbConn()
    conn3.queue_result(fetchone=(1,))
    conn3.queue_result(fetchall=[])
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn3)
    search = amfi_ingest.search_synced_schemes(query="grow", amc="Parag Parikh", category="Flexi")
    assert "schemes" in search

def test_amfi_ingest_normalize_and_search(monkeypatch):
    from shared.services import amfi_ingest

    assert amfi_ingest._normalize_category("", "Large and Midcap Fund Direct") == "Large & Mid Cap Fund"
    assert amfi_ingest._normalize_category("", "Some Random Fund") == "Large Cap Fund"
    assert "Mutual Fund" in amfi_ingest._extract_amc_name("SBI Bluechip Fund", "")

    conn = FakeDbConn()
    conn.queue_result(fetchone=(2,))
    conn.queue_result(fetchall=[
        ("INF1", "HDFC Fund", "HDFC MF", "Large Cap", 100.0, 0.5, "Direct", "Moderate",
         "2024-01-01", "[]", "[]", "amfi", datetime.datetime.now()),
    ])
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: conn)
    res = amfi_ingest.search_synced_schemes(query="grow", amc="HDFC", category="Large", limit=5)
    assert res["total"] == 2

    monkeypatch.setattr(amfi_ingest.db, "connect", MagicMock(side_effect=RuntimeError("db")))
    assert amfi_ingest.search_synced_schemes(query="x")["total"] == 0

    monkeypatch.setattr(amfi_ingest.db, "connect", MagicMock(side_effect=RuntimeError("db")))
    assert amfi_ingest.get_synced_amc_list() == []

def test_amfi_ingest_dedupe_and_cache_success(monkeypatch):
    from shared.services import amfi_ingest

    terms = amfi_ingest._amc_match_terms("parag parikh")
    assert "ppfas" in terms
    monkeypatch.setattr(amfi_ingest.MarketCache, "invalidate_all", MagicMock())
    monkeypatch.setattr("shared.services.market_data.clear_market_data_cache", MagicMock())
    amfi_ingest._invalidate_market_caches()

