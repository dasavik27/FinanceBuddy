"""
test_shared_reference_statutory_full.py

Comprehensive unit tests for shared/reference/statutory.py:
- _load() fallback handling when file is missing or invalid JSON
- _load() partial key defaulting when some keys are missing
- Validation of statutory TAX_RATES and CAPITAL_GAINS constants
"""

from unittest.mock import MagicMock
import json
import pytest

from shared.reference import statutory


def test_statutory_constants():
    assert statutory.TAX_RATES["LTCG_EQUITY"] == 0.125
    assert statutory.TAX_RATES["STCG_EQUITY"] == 0.20
    assert statutory.TAX_RATES["LTCG_EXEMPTION"] == 125000
    assert statutory.CAPITAL_GAINS["debt_ltcg_days"] == 730


def test_statutory_load_fallback_and_missing(monkeypatch, tmp_path):
    # 1. Missing / unreadable file falls back to _FALLBACK
    monkeypatch.setattr(statutory, "_PATH", str(tmp_path / "nonexistent.json"))
    res_fallback = statutory._load()
    assert res_fallback == statutory._FALLBACK

    # 2. Corrupt JSON file falls back to _FALLBACK
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{invalid_json")
    monkeypatch.setattr(statutory, "_PATH", str(bad_file))
    assert statutory._load() == statutory._FALLBACK

    # 3. Partial JSON file defaults missing keys
    partial_file = tmp_path / "partial.json"
    partial_file.write_text(json.dumps({"ltcg_equity_rate": 0.15}))
    monkeypatch.setattr(statutory, "_PATH", str(partial_file))
    res_partial = statutory._load()
    assert res_partial["ltcg_equity_rate"] == 0.15
    assert res_partial["stcg_equity_rate"] == statutory._FALLBACK["stcg_equity_rate"]
