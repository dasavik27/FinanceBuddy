"""
test_shared_session_stores_full_coverage.py

Comprehensive unit tests for shared/session_stores.py:
- register (new registration, replacement of duplicate name)
- registered() name list
- evict_user (stores with integer counts, stores with None returns, stores without hook)
- forget_session (stores with and without hook)
- clear_all (stores with and without hook)
"""

from unittest.mock import MagicMock
import pytest

from shared import session_stores
from shared.session_stores import SessionStore


def test_session_stores_full_lifecycle():
    # Clear existing stores for deterministic test
    session_stores._stores.clear()

    # 1. Register stores
    mock_evict_1 = MagicMock(return_value=3)
    mock_forget_1 = MagicMock()
    mock_clear_1 = MagicMock(return_value={"cleared": 3})

    store1 = SessionStore(
        name="domain_1",
        evict_user=mock_evict_1,
        forget_session=mock_forget_1,
        clear_all=mock_clear_1,
    )
    store2_empty = SessionStore(name="domain_empty")  # all hooks None

    session_stores.register(store1)
    session_stores.register(store2_empty)

    assert "domain_1" in session_stores.registered()
    assert "domain_empty" in session_stores.registered()

    # Duplicate replace
    mock_evict_replaced = MagicMock(return_value=5)
    store1_v2 = SessionStore(name="domain_1", evict_user=mock_evict_replaced)
    session_stores.register(store1_v2)
    assert session_stores.registered().count("domain_1") == 1

    # 2. evict_user
    total = session_stores.evict_user("user-123")
    assert total == 5
    mock_evict_replaced.assert_called_once_with("user-123")

    # 3. forget_session
    mock_forget_v2 = MagicMock()
    store3 = SessionStore(name="domain_3", forget_session=mock_forget_v2)
    session_stores.register(store3)
    session_stores.forget_session("sess-456")
    mock_forget_v2.assert_called_once_with("sess-456")

    # 4. clear_all
    store4 = SessionStore(name="domain_4", clear_all=lambda: "cleared_4")
    session_stores.register(store4)
    res_clear = session_stores.clear_all()
    assert res_clear["domain_4"] == "cleared_4"
