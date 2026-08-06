
"""Budget amount parsing."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domains.budget.amounts import Money, direction_from, parse_amount


def test_amounts_edge_cases():
    assert parse_amount("(1,234.56)") is not None
    assert parse_amount("(1,234.56)").negative is True
    assert parse_amount("1,234,567") is not None
    assert parse_amount("not-a-number") is None
    money = parse_amount("500.00")
    assert direction_from(money, column_direction="debit") == "debit"

def test_amounts_remaining_branches():
    assert parse_amount("12,3456") is None  # tail > 3 digits
    assert parse_amount("1.2.3abc") is None  # non-digit after separators
    money = parse_amount(".50")
    assert money is not None and money.magnitude == 0.5
    assert direction_from(None, column_direction="credit") == "credit"
    assert direction_from(Money(100.0), type_hint="Dr") == "debit"
    assert direction_from(Money(100.0), type_hint="Withdrawal") == "debit"
    assert direction_from(Money(100.0), type_hint="d") == "debit"
    assert parse_amount(Decimal("nan")) is None
    assert parse_amount(True) is None



def test_budget_amounts_invalid_decimal():
    from domains.budget.amounts import _resolve_decimal, parse_amount

    assert _resolve_decimal("not-an-amount") is None
    assert parse_amount(True) is None
    assert parse_amount(float("nan")) is None


def test_budget_amounts_decimal_invalid_operation(monkeypatch):
    from decimal import InvalidOperation
    from domains.budget import amounts

    monkeypatch.setattr(amounts, "Decimal", MagicMock(side_effect=InvalidOperation("bad")))
    assert amounts._resolve_decimal("100") is None
    assert amounts.parse_amount(123) is None

def test_amounts_negative_numeric():
    from domains.budget.amounts import parse_amount

    money = parse_amount(-250.0)
    assert money is not None
    assert money.negative is True

