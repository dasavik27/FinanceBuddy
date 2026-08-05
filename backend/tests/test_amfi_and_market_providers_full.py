import datetime
import json
from unittest.mock import MagicMock
import pandas as pd
import pytest
from fastapi.testclient import TestClient


from main import app
from shared import db, identity
from shared.identity import Caller
from shared.services import amfi_ingest
from shared.services.providers import amfi_db, factory, mfapi, yahoo


class FakeDbCursor:
    def __init__(self, fetch_val=None, fetchall_val=None, rowcount=1):
        self._fetch_val = fetch_val
        self._fetchall_val = fetchall_val or []
        self.rowcount = rowcount
        self.executemany_calls = []

    def fetchone(self):
        return self._fetch_val

    def fetchall(self):
        return self._fetchall_val

    def executemany(self, sql, params_seq):
        self.executemany_calls.append((sql, params_seq))


class FakeDbConn:
    def __init__(self):
        self.executed = []
        self._cursor_queue = []

    def queue_result(self, fetchone=None, fetchall=None, rowcount=1):
        self._cursor_queue.append(FakeDbCursor(fetchone, fetchall, rowcount))

    def cursor(self):
        return self

    def executemany(self, sql, params_seq):
        self.executed.append((sql, params_seq))

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._cursor_queue:
            return self._cursor_queue.pop(0)
        return FakeDbCursor()

    def commit(self):
        pass


    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def auth_client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Ingest helpers and normalization
# ---------------------------------------------------------------------------

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
    assert amfi_ingest._normalize_category("", "Parag Parikh Flexi Cap Fund") == "Flexi Cap Fund"


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

def test_market_data_providers(monkeypatch):
    # 1. Provider Factory is a singleton
    p1 = factory.get_provider()
    p2 = factory.get_provider()
    assert p1 is p2
    assert isinstance(p1, mfapi.MFApiProvider)

    # 2. MFApiProvider: NAV series + metadata
    provider = mfapi.MFApiProvider()

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def raise_for_status(self):
            pass
        def json(self):
            return self._data

    nav_json = {
        "meta": {
            "scheme_name": "Test Fund",
            "fund_house": "Test AMC",
            "scheme_type": "Open Ended",
            "scheme_category": "Large Cap",
        },
        "data": [
            {"date": "01-01-2026", "nav": "100.50"},
            {"date": "02-01-2026", "nav": "101.20"},
            {"date": "02-01-2026", "nav": "101.20"},  # duplicate → kept once
            {"date": "invalid-date", "nav": "102.00"},  # bad date → dropped
        ],
    }
    monkeypatch.setattr(provider.session, "get", lambda *a, **k: FakeResp(nav_json))

    s = provider.fetch_nav_series("119062", days=30)
    assert len(s) == 2
    assert s.iloc[-1] == 101.20

    meta = provider.fetch_fund_meta("119062")
    assert meta["scheme_name"] == "Test Fund"
    assert meta["fund_house"] == "Test AMC"

    # Error path: non-raising exception → empty series / dict
    monkeypatch.setattr(
        provider.session,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("network down")),
    )
    s_err = provider.fetch_nav_series("bad", days=30)
    assert s_err.empty
    meta_err = provider.fetch_fund_meta("bad")
    assert meta_err == {}

    # 3. YahooMetadataProvider
    yp = yahoo.YahooMetadataProvider()
    monkeypatch.setattr(
        "requests.get",
        lambda url, **k: FakeResp(
            {"quotes": [{"symbol": "0P0000XWNE.BO", "typeDisp": "Mutual Fund"}]}
        ),
    )
    sym = yp.resolve_yahoo_symbol("INF179K01BE2", "HDFC Top 100")
    assert sym == "0P0000XWNE.BO"

    # No results → None
    monkeypatch.setattr("requests.get", lambda url, **k: FakeResp({"quotes": []}))
    assert yp.resolve_yahoo_symbol("INVALID", "") is None

    # 4. AMFIDatabaseProvider
    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    now = datetime.datetime.now(datetime.timezone.utc)

    conn.queue_result(fetchone=(
        "INF179K01BE2",
        119062,
        "HDFC Top 100 Fund",
        50000.0,   # aum_cr
        0.85,      # expense_ratio
        "VERY HIGH",
        "1%",      # exit_load
        json.dumps([{"sector": "Financial Services", "value": 35.0}]),
        json.dumps([{"name": "HDFC Bank", "pct": 9.5}]),
        "AMFI Official Disclosure",
        now,       # portfolio_date
    ))
    db_prov = amfi_db.AMFIDatabaseProvider()
    result = db_prov.fetch_insights(isin="INF179K01BE2")
    assert result["risk"] == "VERY HIGH"
    assert result["sectors"][0]["sector"] == "Financial Services"
    assert result["holdings"][0]["name"] == "HDFC Bank"

    # Empty ISIN → empty result
    empty = db_prov.fetch_insights(isin="", fund_name="")
    assert empty["sectors"] == []


# ---------------------------------------------------------------------------
# Admin MF router + market router
# ---------------------------------------------------------------------------

def test_admin_mf_and_market_routes(auth_client, signed_in, monkeypatch):
    admin_caller = Caller(
        user_id="00000000-0000-0000-0000-0000000000ff",
        role="admin",
        email="admin@test.com",
        status="active",
    )

    # 1. Non-admin caller → 403
    resp_denied = auth_client.get("/admin/mf-sync/status", headers=signed_in)
    assert resp_denied.status_code == 403

    # Elevate to admin
    monkeypatch.setattr("shared.identity.current_caller", lambda: admin_caller)

    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    # 2. GET /admin/mf-sync/status
    conn.queue_result(fetchone=("admin@test.com",))  # identities lookup
    monkeypatch.setattr(amfi_ingest, "get_sync_status", lambda: {"total_schemes": 250})
    resp_status = auth_client.get("/admin/mf-sync/status", headers=signed_in)
    assert resp_status.status_code == 200
    assert resp_status.json()["total_schemes"] == 250

    # 3. GET /admin/mf-sync/amcs
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest, "get_synced_amc_list",
        lambda: [{"amc": "HDFC Mutual Fund", "schemes_count": 80}]
    )
    resp_amcs = auth_client.get("/admin/mf-sync/amcs", headers=signed_in)
    assert resp_amcs.status_code == 200
    assert len(resp_amcs.json()["amcs"]) == 1

    # 4. POST /admin/mf-sync/trigger
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest, "trigger_amfi_sync",
        lambda *a, **k: {"status": "success", "synced_count": 80}
    )
    resp_trig = auth_client.post("/admin/mf-sync/trigger", json={"preset": "top5"}, headers=signed_in)
    assert resp_trig.status_code == 200
    assert resp_trig.json()["status"] == "success"

    # 5. DELETE /admin/mf-sync/purge without params → 400
    conn.queue_result(fetchone=("admin@test.com",))
    resp_purge_bad = auth_client.delete("/admin/mf-sync/purge", headers=signed_in)
    assert resp_purge_bad.status_code == 400

    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest, "purge_snapshots",
        lambda *a, **k: {"status": "success", "deleted_count": 50}
    )
    resp_purge_ok = auth_client.delete("/admin/mf-sync/purge?purge_all=true", headers=signed_in)
    assert resp_purge_ok.status_code == 200
    assert resp_purge_ok.json()["deleted_count"] == 50

    # 6. GET /admin/mf-sync/schemes
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest, "search_synced_schemes",
        lambda **k: {"total": 1, "schemes": [{"scheme_name": "Fund 1"}]}
    )
    resp_schemes = auth_client.get("/admin/mf-sync/schemes?q=Fund", headers=signed_in)
    assert resp_schemes.status_code == 200
    assert resp_schemes.json()["total"] == 1

    # 7. GET /market/summary (public)
    resp_mkt = auth_client.get("/market/summary")
    assert resp_mkt.status_code == 200
    assert "server_time" in resp_mkt.json()

    # 8. GET /market/nav/{isin}
    monkeypatch.setattr(
        "shared.services.market_data.fetch_live_navs",
        lambda: {"INF179K01BE2": 982.45}
    )
    resp_nav = auth_client.get("/market/nav/INF179K01BE2")
    assert resp_nav.status_code == 200
    assert resp_nav.json()["nav"] == 982.45

    # 9. GET /market/config
    resp_cfg = auth_client.get("/market/config")
    assert resp_cfg.status_code == 200
    assert "cache_ttl" in resp_cfg.json()

    # 10. POST /market/config (requires auth)
    conn.queue_result(fetchone=None)
    resp_cfg_post = auth_client.post("/market/config?ttl=15", headers=signed_in)
    assert resp_cfg_post.status_code == 200
    assert resp_cfg_post.json()["cache_ttl"] == 15


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

