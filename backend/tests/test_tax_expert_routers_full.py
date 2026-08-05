"""
test_tax_expert_routers_full.py

Comprehensive tests for Tax Expert routers:
- domains.tax_expert.routers.session (AIS upload, byte bounds, auth requirement)
- domains.tax_expert.routers.rules (active statutory tax rules)
- domains.tax_expert.routers.itr (ITR PDF upload endpoint)
"""

import io
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from domains.tax_expert.routers import session as session_router
from domains.tax_expert import tax_sessions, ais_schemas
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-0000000000ff"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="tax-user@example.test")


@pytest.fixture
def client():
    return TestClient(app)


def test_require_caller_unauthenticated():
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            session_router._require_caller()
        assert exc.value.status_code == 401


def test_require_caller_authenticated():
    with identity_scope(CALLER):
        caller_id = session_router._require_caller()
        assert caller_id == USER_ID


def test_read_upload_bounds():
    # Empty file raises 422
    with pytest.raises(HTTPException) as exc:
        session_router._read_upload(io.BytesIO(b""), "Empty PDF")
    assert exc.value.status_code == 422
    assert "empty" in exc.value.detail.lower()

    # Oversized file (> 8MB) raises 422
    oversized = io.BytesIO(b"0" * (8 * 1024 * 1024 + 100))
    with pytest.raises(HTTPException) as exc:
        session_router._read_upload(oversized, "Large PDF")
    assert exc.value.status_code == 422
    assert "larger than" in exc.value.detail.lower()


def test_parse_ais_endpoint_requires_auth(client):
    file_payload = {"file": ("ais.pdf", b"%PDF-1.4 sample", "application/pdf")}
    res = client.post("/tax-expert/parse-ais", files=file_payload)
    assert res.status_code == 401


def test_parse_ais_endpoint_success(client, signed_in, monkeypatch):
    mock_ais_data = {
        "personal": {"pan": "ABCDE1234F", "name": "Taxpayer"},
        "fy": "2025-26",
        "salary": {"gross": 1000000},
    }
    monkeypatch.setattr(session_router, "parse_ais_pdf", lambda raw: mock_ais_data)

    file_payload = {"file": ("ais.pdf", b"%PDF-1.4 sample content", "application/pdf")}
    res = client.post("/tax-expert/parse-ais", headers=signed_in, files=file_payload)
    assert res.status_code == 200
    body = res.json()
    assert "session_id" in body
    assert body["personal"]["pan"] == "ABCDE1234F"


def test_parse_ais_endpoint_unknown_code_error(client, signed_in, monkeypatch):
    def raise_unknown(raw):
        raise ais_schemas.AISUnknownCodeError("999_TEST", "Test")

    monkeypatch.setattr(session_router, "parse_ais_pdf", raise_unknown)
    file_payload = {"file": ("ais.pdf", b"%PDF-1.4 sample content", "application/pdf")}
    res = client.post("/tax-expert/parse-ais", headers=signed_in, files=file_payload)
    assert res.status_code == 422
    assert "999_TEST" in str(res.json())


def test_tax_rules_endpoint(client):
    res = client.get("/tax-expert/rules")
    assert res.status_code == 200
    body = res.json()
    assert "capital_gains" in body
    assert "deductions" in body
