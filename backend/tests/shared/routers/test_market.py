"""Router tests for shared/routers/market.py."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from shared import db
from shared.identity import Caller
from shared.services import amfi_ingest
from tests.helpers import FakeDbConn


@pytest.fixture
def auth_client():
    return TestClient(app)


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
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(amfi_ingest, "get_sync_status", lambda: {"total_schemes": 250})
    resp_status = auth_client.get("/admin/mf-sync/status", headers=signed_in)
    assert resp_status.status_code == 200
    assert resp_status.json()["total_schemes"] == 250

    # 3. GET /admin/mf-sync/amcs
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest,
        "get_synced_amc_list",
        lambda: [{"amc": "HDFC Mutual Fund", "schemes_count": 80}],
    )
    resp_amcs = auth_client.get("/admin/mf-sync/amcs", headers=signed_in)
    assert resp_amcs.status_code == 200
    assert len(resp_amcs.json()["amcs"]) == 1

    # 4. POST /admin/mf-sync/trigger
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest,
        "trigger_amfi_sync",
        lambda *a, **k: {"status": "success", "synced_count": 80},
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
        amfi_ingest,
        "purge_snapshots",
        lambda *a, **k: {"status": "success", "deleted_count": 50},
    )
    resp_purge_ok = auth_client.delete("/admin/mf-sync/purge?purge_all=true", headers=signed_in)
    assert resp_purge_ok.status_code == 200
    assert resp_purge_ok.json()["deleted_count"] == 50

    # 6. GET /admin/mf-sync/schemes
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        amfi_ingest,
        "search_synced_schemes",
        lambda **k: {"total": 1, "schemes": [{"scheme_name": "Fund 1"}]},
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
        lambda: {"INF179K01BE2": 982.45},
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


def test_market_cache_ttl_requires_auth():
    from shared.routers import market as market_router

    with pytest.raises(HTTPException) as exc:
        market_router.update_market_config(10)
    assert exc.value.status_code == 401
