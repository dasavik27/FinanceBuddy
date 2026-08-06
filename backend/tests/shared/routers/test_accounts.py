"""Router tests for shared/routers/accounts.py."""

import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from shared import crypto, session_stores, storage, users
from tests.helpers import FakeDbConn


@pytest.fixture
def auth_client():
    return TestClient(app)


def test_accounts_router_endpoints(auth_client, signed_in, monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(storage, "_connect", lambda **kw: conn)
    monkeypatch.setattr("shared.db.connect", lambda **kw: conn)

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. GET /accounts/summary
    conn.queue_result(fetchall=[{
        "session_id": "sess-summary-1",
        "upload_type": "mutual_funds",
        "created_at": now,
    }])
    
    resp_sum = auth_client.get("/accounts/summary", headers=signed_in)
    assert resp_sum.status_code == 200
    data = resp_sum.json()
    assert data["status"] == "ok"
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["sessions"][0]["session_id"] == "sess-summary-1"

    # 2. GET /accounts/me/export
    uid = "00000000-0000-0000-0000-0000000000ff"
    conn.queue_result(fetchone={
        "id": uid,
        "created_at": now,
        "last_seen_at": now,
        "pan_encrypted": None,
        "display_name": "Test Exporter",
    })
    conn.queue_result(fetchall=[{
        "issuer": "https://example-test-issuer.invalid/auth/v1",
        "email": "exporter@test.com",
        "created_at": now,
    }])
    
    # Encrypted mock blobs
    enc_metrics = crypto.encrypt_json({"total_value": 100000.0}, aad="s-tax")
    enc_tax = crypto.encrypt_json({"gross_salary": 500000.0}, aad="s-tax")
    
    enc_budget_metrics = crypto.encrypt_json({"net_spend": 25000.0}, aad="s-budget")
    from domains.budget.sessions import _compress_frame
    df_budget_tx = pd.DataFrame({"Amount": [100.0], "Date": pd.to_datetime(["2024-01-01"])})
    b_txns = crypto.encrypt(_compress_frame(df_budget_tx), aad="s-budget")
    b_accs = {"acc1": {}}

    enc_mf_metrics = crypto.encrypt_json({"total_value": 200000.0}, aad="s-mf")
    mf_payload = storage.encode_payload(
        pd.DataFrame({"Fund": ["F1"], "Market Value": [200000.0], "Invested": [150000.0]}),
        pd.DataFrame({"Fund": ["F1"], "Amount": [150000.0], "Date": pd.to_datetime(["2024-01-01"]), "Units": [100.0], "Type": ["Purchase"]}),
        pd.DataFrame({"Fund": ["F1"], "SIP Amount": [5000.0]})
    )
    enc_h = crypto.encrypt(mf_payload["holdings"], aad="s-mf")
    enc_t = crypto.encrypt(mf_payload["transactions"], aad="s-mf")
    enc_s = crypto.encrypt(mf_payload["sips"], aad="s-mf")

    conn.queue_result(fetchall=[
        {
            "session_id": "s-tax", "upload_type": "tax_expert", "created_at": now, "statement_period": "2024-25",
            "metrics": enc_metrics, "holdings": None, "transactions": None, "sips": None, "meta": None,
            "tax_data": enc_tax, "budget_txns": None, "budget_accounts": None,
        },
        {
            "session_id": "s-budget", "upload_type": "budget", "created_at": now, "statement_period": "2024-01",
            "metrics": enc_budget_metrics, "holdings": None, "transactions": None, "sips": None, "meta": None,
            "tax_data": None, "budget_txns": b_txns, "budget_accounts": b_accs,
        },
        {
            "session_id": "s-mf", "upload_type": "mutual_funds", "created_at": now, "statement_period": "2024-01",
            "metrics": enc_mf_metrics, "holdings": enc_h, "transactions": enc_t, "sips": enc_s, "meta": mf_payload["meta"],
            "tax_data": None, "budget_txns": None, "budget_accounts": None,
        },
        {
            "session_id": "s-corrupt", "upload_type": "mutual_funds", "created_at": now, "statement_period": "2024-01",
            "metrics": b"corrupt-data", "holdings": b"corrupt", "transactions": b"corrupt", "sips": b"corrupt", "meta": {},
            "tax_data": None, "budget_txns": None, "budget_accounts": None,
        }
    ])

    resp_exp = auth_client.get("/accounts/me/export", headers=signed_in)
    assert resp_exp.status_code == 200
    exp_data = resp_exp.json()
    assert len(exp_data["sessions"]) == 4

    # 3. DELETE /accounts/me
    monkeypatch.setattr(session_stores, "evict_user", lambda uid: None)
    monkeypatch.setattr(storage, "delete_all_for_user", lambda uid: 3)
    monkeypatch.setattr(users, "invalidate", lambda uid: None)
    
    resp_purge = auth_client.delete("/accounts/me", headers=signed_in)
    assert resp_purge.status_code == 200
    assert resp_purge.json()["deleted_count"] == 3

    # 4. POST /accounts/clear_caches
    resp_clear = auth_client.post("/accounts/clear_caches", headers=signed_in)
    assert resp_clear.status_code == 200

    # Cache clear exception
    monkeypatch.setattr(session_stores, "clear_all", lambda: (_ for _ in ()).throw(RuntimeError("Cache lock failed")))
    resp_clear_err = auth_client.post("/accounts/clear_caches", headers=signed_in)
    assert resp_clear_err.status_code == 500

def test_accounts_router_unauthorized(auth_client):
    assert auth_client.get("/accounts/summary").status_code == 401
    assert auth_client.get("/accounts/me/export").status_code == 401
    assert auth_client.delete("/accounts/me").status_code == 401

