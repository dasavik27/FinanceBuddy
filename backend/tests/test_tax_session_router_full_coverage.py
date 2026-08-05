"""
test_tax_session_router_full_coverage.py

Comprehensive tests for domains/tax_expert/routers/session.py:
- _require_caller & _read_upload
- parse_ais (success, broker integration, broker parse error, AISUnknownCodeError, AISStructureChangedError, general error, no income)
- reconcile_broker (not found, broker parse error, zero cost auto-correction, cost mismatch auto-correction, duplicate trade drop)
- get_tax_history
- delete_tax_history_entry (not logged in, registry error 503, not found 404, memory fallback, success)
"""

import io
from unittest.mock import MagicMock
from fastapi import HTTPException, UploadFile
import pytest

from domains.tax_expert.ais_schemas import AISStructureChangedError, AISUnknownCodeError
from domains.tax_expert.routers import session as session_router
from domains.tax_expert import tax_sessions
from shared import storage
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="user@test.com")


def _make_upload_file(data: bytes, filename: str = "doc.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def test_tax_session_router_auth_and_upload_helpers():
    # 1. _require_caller unauthenticated -> 401
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            session_router._require_caller()
        assert exc.value.status_code == 401

    # Authenticated -> returns user_id
    with identity_scope(CALLER):
        assert session_router._require_caller() == USER_ID

    # 2. _read_upload empty -> 422
    with pytest.raises(HTTPException) as exc:
        session_router._read_upload(io.BytesIO(b""), "Doc")
    assert exc.value.status_code == 422
    assert "empty" in exc.value.detail

    # Oversized -> 422
    big_data = io.BytesIO(b"A" * (8 * 1024 * 1024 + 10))
    with pytest.raises(HTTPException) as exc:
        session_router._read_upload(big_data, "Doc")
    assert exc.value.status_code == 422
    assert "larger than 8 MB" in exc.value.detail

    # Valid -> returns bytes
    assert session_router._read_upload(io.BytesIO(b"valid content"), "Doc") == b"valid content"


def test_tax_session_router_parse_ais_errors(monkeypatch):
    with identity_scope(CALLER):
        # 1. AISUnknownCodeError -> 422
        monkeypatch.setattr(
            session_router, "parse_ais_pdf",
            MagicMock(side_effect=AISUnknownCodeError("UNK_CODE", "Unknown code")),
        )
        with pytest.raises(HTTPException) as exc:
            session_router.parse_ais(_make_upload_file(b"test pdf"))
        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "AIS_UNKNOWN_CODE"

        # 2. AISStructureChangedError -> 422
        monkeypatch.setattr(
            session_router, "parse_ais_pdf",
            MagicMock(side_effect=AISStructureChangedError({"diff": "mismatch"})),
        )
        with pytest.raises(HTTPException) as exc:
            session_router.parse_ais(_make_upload_file(b"test pdf"))
        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "AIS_STRUCTURE_CHANGED"

        # 3. Generic parse exception -> 422
        monkeypatch.setattr(
            session_router, "parse_ais_pdf",
            MagicMock(side_effect=RuntimeError("Corrupt")),
        )
        with pytest.raises(HTTPException) as exc:
            session_router.parse_ais(_make_upload_file(b"test pdf"))
        assert exc.value.status_code == 422
        assert "Could not read that AIS PDF" in exc.value.detail

        # 4. No income extracted -> 422
        monkeypatch.setattr(
            session_router, "parse_ais_pdf",
            lambda raw: {"personal": {"pan": "ABCDE1234F"}, "salary": {"gross": 0}},
        )
        with pytest.raises(HTTPException) as exc:
            session_router.parse_ais(_make_upload_file(b"test pdf"))
        assert exc.value.status_code == 422
        assert "Could not extract financial data" in exc.value.detail


def test_tax_session_router_parse_ais_success_and_broker_handling(monkeypatch):
    tax_sessions.clear_all()
    tax_sessions._sessions_loaded = True

    sample_ais = {
        "personal": {"pan": "ABCDE1234F", "name": "Avik Das"},
        "fy": "2025-26",
        "salary": {"gross": 1500000},
        "dividends": [{"amount": 10000}],
    }
    monkeypatch.setattr(session_router, "parse_ais_pdf", lambda raw: sample_ais)
    monkeypatch.setattr(
        session_router, "get_computation",
        lambda sid, sess, reg: {"itr_type": "ITR-2", "total_tax": 80000, "refund_or_due": 0},
    )

    with identity_scope(CALLER):
        # 1. Success without broker file
        res = session_router.parse_ais(_make_upload_file(b"valid pdf"), broker_file=None)
        assert "session_id" in res
        assert res["gross_salary"] == 1500000
        assert res["total_tax"] == 80000


        # 2. Success with failing broker file (recovers)
        monkeypatch.setattr(
            session_router, "parse_zerodha_tax_pnl",
            MagicMock(side_effect=RuntimeError("Bad broker sheet")),
        )
        res_broker_fail = session_router.parse_ais(
            _make_upload_file(b"valid pdf"),
            broker_file=_make_upload_file(b"bad broker", filename="broker.xlsx"),
        )
        assert res_broker_fail["total_tax"] == 80000

        # 3. Success with valid broker file
        monkeypatch.setattr(
            session_router, "parse_zerodha_tax_pnl",
            lambda raw: [{"security": "HDFC", "consideration": 50000}],
        )
        monkeypatch.setattr(
            session_router, "reconcile_trades",
            lambda ais, bt: {"zero_cost": []},
        )
        res_broker_ok = session_router.parse_ais(
            _make_upload_file(b"valid pdf"),
            broker_file=_make_upload_file(b"good broker", filename="broker.xlsx"),
        )
        assert res_broker_ok["gross_salary"] == 1500000


def test_tax_session_router_reconcile_broker_direct(monkeypatch):
    tax_sessions.clear_all()
    tax_sessions._sessions_loaded = True

    with identity_scope(CALLER):
        # 1. Session not found -> 404
        with pytest.raises(HTTPException) as exc:
            session_router.reconcile_broker("s-missing", _make_upload_file(b"broker", "b.xlsx"))
        assert exc.value.status_code == 404

        # 2. Broker parse error -> 422
        sid = "s-rec-1"
        tax_sessions._tax_sessions[sid] = {
            "user_id": USER_ID,
            "ais_data": {
                "personal": {"pan": "ABCDE1234F"},
                "salary": {"gross": 500000},
                "capital_gains_equity": [
                    {"security": "RELIANCE", "type": "LTCG", "cost": 0, "consideration": 100000},
                    {"security": "TCS", "type": "STCG", "cost": 20000, "consideration": 50000},
                    {"security": "TCS", "type": "STCG", "cost": 20000, "consideration": 50000}, # duplicate
                ],
            },
        }

        monkeypatch.setattr(
            session_router, "parse_zerodha_tax_pnl",
            MagicMock(side_effect=RuntimeError("Corrupt excel")),
        )
        with pytest.raises(HTTPException) as exc:
            session_router.reconcile_broker(sid, _make_upload_file(b"broker", "b.xlsx"))
        assert exc.value.status_code == 422
        assert "Could not read that broker file" in exc.value.detail

        # 3. Successful reconciliation with zero cost and mismatch auto-correction + duplicate drop
        broker_trades = [
            {"security": "RELIANCE", "type": "LTCG", "cost": 80000, "consideration": 100000},
            {"security": "TCS", "type": "STCG", "cost": 35000, "consideration": 50000},
            {"security": "HDFC Top 100", "type": "LTCG", "cost": 40000, "consideration": 50000},
        ]
        monkeypatch.setattr(session_router, "parse_zerodha_tax_pnl", lambda raw: broker_trades)

        sid2 = "s-rec-2"
        tax_sessions._tax_sessions[sid2] = {
            "user_id": USER_ID,
            "ais_data": {
                "personal": {"pan": "ABCDE1234F"},
                "salary": {"gross": 500000},
                "capital_gains_mf_equity": [
                    {"amc": "HDFC", "fund": "Top 100", "type": "LTCG", "cost": 0, "consideration": 50000},
                ],
            },
        }
        monkeypatch.setattr(
            session_router, "reconcile_trades",
            lambda ais, bt: {
                "zero_cost": [{"security": "HDFC Top 100", "type": "LTCG", "broker_cost": 40000}],
                "cost_mismatch": [],
            },
        )
        res_rec2 = session_router.reconcile_broker(sid2, _make_upload_file(b"broker", "b.xlsx"))
        assert res_rec2["status"] == "success"

        monkeypatch.setattr(
            session_router, "reconcile_trades",
            lambda ais, bt: {
                "zero_cost": [{"security": "RELIANCE", "type": "LTCG", "broker_cost": 80000}],
                "cost_mismatch": [{"security": "TCS", "type": "STCG", "broker_cost": 35000}],
            },
        )

        res_rec = session_router.reconcile_broker(sid, _make_upload_file(b"broker", "b.xlsx"))
        assert res_rec["status"] == "success"
        assert res_rec["corrected"] >= 1




def test_tax_session_router_history_endpoints(monkeypatch):
    tax_sessions.clear_all()
    tax_sessions._sessions_loaded = True

    # 1. get_tax_history
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            session_router.get_tax_history()
        assert exc.value.status_code == 401

    with identity_scope(CALLER):
        monkeypatch.setattr(
            session_router, "get_sessions_by_user",
            lambda uid, limit, offset: [{"session_id": "s1", "name": "Avik"}],
        )
        res_hist = session_router.get_tax_history(limit=50, offset=0)
        assert len(res_hist["sessions"]) == 1
        assert res_hist["has_more"] is False

    # 2. delete_tax_history_entry
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            session_router.delete_tax_history_entry("s1")
        assert exc.value.status_code == 401

    with identity_scope(CALLER):
        # Storage error -> 503
        monkeypatch.setattr(
            storage, "get_session_owner",
            MagicMock(side_effect=storage.OwnerLookupFailed("DB Down")),
        )
        with pytest.raises(HTTPException) as exc:
            session_router.delete_tax_history_entry("s1")
        assert exc.value.status_code == 503

        # Not found / not owned -> 404
        monkeypatch.setattr(storage, "get_session_owner", lambda sid: (False, None))
        with pytest.raises(HTTPException) as exc:
            session_router.delete_tax_history_entry("s-not-found")
        assert exc.value.status_code == 404

        # Memory hit fallback & success delete
        tax_sessions._tax_sessions["s-mem"] = {"user_id": USER_ID}
        monkeypatch.setattr(storage, "get_session_owner", lambda sid: (False, None))
        res_del = session_router.delete_tax_history_entry("s-mem")
        assert res_del["status"] == "success"
        assert res_del["deleted_session_id"] == "s-mem"
