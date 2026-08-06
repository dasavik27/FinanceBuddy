"""ITR upload router."""

import io
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from domains.tax_expert import tax_sessions
from domains.tax_expert.routers import itr
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="tax@test.com", pan="ABCDE1234F")


@pytest.fixture(autouse=True)
def _clean_tax_sessions():
    tax_sessions.clear_all()
    yield
    tax_sessions.clear_all()


def _sample_ais():
    return {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F", "name": "Test User"},
        "salary": {"gross": 1_200_000, "tds_deducted": 100_000},
        "capital_gains_equity": [],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
    }


def test_itr_router_not_found_paths():
    with pytest.raises(HTTPException) as exc:
        itr.get_itr("missing")
    assert exc.value.status_code == 404

    with identity_scope(CALLER):
        sid = tax_sessions.create_tax_session(_sample_ais())
        with pytest.raises(HTTPException) as exc2:
            itr.get_itr(sid)
        assert exc2.value.status_code == 404

def test_itr_router_parse_failure(monkeypatch):
    with identity_scope(CALLER):
        sid = tax_sessions.create_tax_session(_sample_ais())

    monkeypatch.setattr(itr, "parse_itr_pdf", MagicMock(side_effect=RuntimeError("bad pdf")))
    upload = UploadFile(filename="itr.pdf", file=io.BytesIO(b"pdf bytes"))
    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            itr.upload_itr(sid, upload)
        assert exc.value.status_code == 422

def test_itr_router_upload_and_get(monkeypatch):
    ais = _sample_ais()
    with identity_scope(CALLER):
        sid = tax_sessions.create_tax_session(ais)

    monkeypatch.setattr(itr, "parse_itr_pdf", lambda raw: {"itr_type": "ITR-2", "total_tax": 100000})
    upload = UploadFile(filename="itr.pdf", file=io.BytesIO(b"pdf bytes"))

    with identity_scope(CALLER):
        up = itr.upload_itr(sid, upload)
        assert up["status"] == "success"
        got = itr.get_itr(sid)
        assert got["itr_data"]["itr_type"] == "ITR-2"



def test_itr_router_upload_missing_session(monkeypatch):
    monkeypatch.setattr(itr, "get_tax_session", lambda sid: None)
    upload = UploadFile(filename="itr.pdf", file=io.BytesIO(b"x"))
    with pytest.raises(HTTPException):
        itr.upload_itr("missing", upload)
