
"""Budget merchant normalisation and aliases."""

import pandas as pd
import pytest

from domains.budget.merchants import apply_aliases, clean_merchant_name, load_aliases, normalise_key, set_alias
from domains.budget.natures import nature_of


def test_merchants_clean_and_aliases(monkeypatch):
    assert clean_merchant_name(None) == "Unknown Payee"
    assert clean_merchant_name("nan") == "Unknown Payee"
    assert "Swiggy" in clean_merchant_name("UPI/DR/1234/SWIGGY BANGALORE")
    assert clean_merchant_name("!!!!!!")

    assert load_aliases(None) == {}

    class FakeConn:
        def execute(self, sql, params=None):
            if "SELECT" in sql:
                class Result:
                    def fetchall(self_inner):
                        return [("swiggy", "Swiggy Food")]
                return Result()
            return None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shared.db.connect", lambda: FakeConn())
    aliases = load_aliases("user-1")
    assert aliases
    key = set_alias("user-1", "UPI SWIGGY", "Swiggy Food")
    assert "swiggy" in key
    assert apply_aliases("UPI SWIGGY", {normalise_key("UPI SWIGGY"): "Swiggy Food"}) == "Swiggy Food"

def test_natures_and_merchants_edge_cases():
    assert nature_of("") == "wants"
    assert nature_of("   ") == "wants"
    assert nature_of("salary/income") == "income"
    long_name = "UPI/DR/1234/" + ("SWIGGY " * 20)
    cleaned = clean_merchant_name(long_name)
    assert cleaned.endswith("…") or len(cleaned) <= 64
    assert "NASA" in clean_merchant_name("payment to NASA research lab")



def test_clean_merchant_name_truncates_long_names():
    long_name = "MERCHANT " + ("X" * 100)
    assert len(clean_merchant_name(long_name)) <= 60

def test_merchant_clean_name_noise_fallback():
    name = clean_merchant_name("*** ### @@@")
    assert name

