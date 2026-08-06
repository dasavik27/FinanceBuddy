"""Mutual fund portfolio router."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.models import Portfolio
from domains.mutual_funds import sessions
from domains.mutual_funds.routers import portfolio


def test_portfolio_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    # parse_cas: file oversized
    oversized = UploadFile(filename="big.pdf", file=io.BytesIO(b"0" * (8 * 1024 * 1024 + 10)))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=oversized)
    assert exc.value.status_code == 422

    # parse_cas: empty file
    empty_f = UploadFile(filename="empty.pdf", file=io.BytesIO(b""))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=empty_f)
    assert exc.value.status_code == 422

    # parse_cas: missing password and no profile pan
    monkeypatch.setattr("shared.identity.current_pan", lambda: None)
    valid_f = UploadFile(filename="stmt.pdf", file=io.BytesIO(b"dummy pdf content"))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=valid_f, password=None)
    assert exc.value.status_code == 400

    # parse_cas: parse error
    monkeypatch.setattr(portfolio, "parse_cas_file", lambda raw, pw: (None, None, None, "Invalid PDF", False, None))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=valid_f, password="ABCDE1234F")
    assert exc.value.status_code == 422

    # parse_cas: empty holdings
    monkeypatch.setattr(portfolio, "parse_cas_file", lambda raw, pw: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, False, None))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=valid_f, password="ABCDE1234F")
    assert exc.value.status_code == 422

    # parse_cas: success (fresh UploadFile — prior cases already consumed valid_f)
    caller_mock = MagicMock(user_id="u1", pan="OLD_PAN")
    monkeypatch.setattr("shared.identity.current_caller", lambda: caller_mock)
    pan_saved = []
    monkeypatch.setattr("shared.users.set_pan", lambda uid, pan: pan_saved.append((uid, pan)))
    monkeypatch.setattr(portfolio, "parse_cas_file", lambda raw, pw: (p.df_h, p.df_t, p.df_s, None, False, "2023-2024"))
    monkeypatch.setattr(portfolio, "create_session", lambda *args, **kwargs: "new_session_999")

    success_f = UploadFile(filename="stmt.pdf", file=io.BytesIO(b"dummy pdf content"))
    res_parse = portfolio.parse_cas(file=success_f, password="NEW_PAN_1234F")
    assert res_parse["session_id"] == "new_session_999"
    assert ("u1", "NEW_PAN_1234F") in pan_saved

    # sync_portfolio
    monkeypatch.setattr("shared.services.market_data.resolve_scheme_code_from_isin", lambda isin: "12345")
    res_sync = portfolio.sync_portfolio(sid)
    assert res_sync["status"] == "ok"
    assert res_sync["cleared"] > 0

    # sync_portfolio on empty
    from datetime import datetime
    empty_p = Portfolio(df_h=pd.DataFrame(), df_t=pd.DataFrame(), df_s=pd.DataFrame())
    sessions._SESSIONS["empty_sid"] = {
        "portfolio": empty_p,
        "last_accessed": datetime.now(),
        "owner": None,
    }
    assert portfolio.sync_portfolio("empty_sid") == {"status": "ok", "cleared": 0}

