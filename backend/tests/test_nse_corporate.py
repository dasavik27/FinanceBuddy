"""
tests/test_nse_corporate.py

Cover for NSE corporate-action parsing.

This exists because yfinance is wrong here in two specific ways, and these parses are
what replaces it:

  * it reports Indian **bonus issues as splits**, indistinguishably - all four of
    RELIANCE's yfinance "splits" are 1:1 bonuses, and RIL has never split;
  * it gets **compound actions** wrong - BAJFINANCE's June 2025 1:2 split plus 4:1
    bonus is 10x, but yfinance reports `Stock Splits = 2.0` while back-adjusting prices
    by the full 10x.

The subject strings below are real NSE wording, not invented.

No network: every case here parses a literal payload.
"""

from __future__ import annotations

import pytest

from domains.equity.nse_corporate import (
    _parse_action,
    _parse_nse_date,
    adjustment_factor,
    classify_action,
)


class TestClassifyAction:
    @pytest.mark.parametrize("subject,expected", [
        ("Bonus 1:1", "bonus"),
        ("Bonus 4:1", "bonus"),
        ("Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share", "split"),
        ("Face Value Split From Rs.10/- to Rs.2/-", "split"),
        ("Dividend - Rs 44 Per Share", "dividend"),
        ("Special Dividend - Rs 12 Per Share", "dividend"),
        ("Interim Dividend", "dividend"),
        ("Rights Issue 1:4", "rights"),
        ("Buy Back of Shares", "buyback"),
        ("Buy-Back", "buyback"),
        ("Scheme of Arrangement", "demerger"),
        ("Annual General Meeting", "other"),
    ])
    def test_classification(self, subject, expected):
        assert classify_action(subject) == expected

    def test_bonus_wins_over_dividend_in_a_combined_subject(self):
        # Mislabelling a bonus as a dividend is the error that corrupts cost basis: a
        # bonus share carries zero cost, a dividend does not change share count at all.
        assert classify_action("Bonus issue and dividend") == "bonus"

    @pytest.mark.parametrize("subject", ["", None])
    def test_empty_subject_does_not_raise(self, subject):
        assert classify_action(subject) == "other"


class TestRatioParsing:
    def test_face_value_split_stated_without_a_ratio(self):
        # The case that silently turned a 10x compound action into 5x: NSE states most
        # splits as a face-value change, so the "a:b" parse finds nothing.
        a = _parse_action({"subject": "Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share"})
        assert a["type"] == "split"
        assert a["ratio"] == "2:1"

    def test_face_value_split_with_decimals(self):
        a = _parse_action({"subject": "Face Value Split From Rs 1/- to Re 0.50"})
        assert a["ratio"] == "1:0.5"

    def test_face_value_ten_to_two_is_not_mangled(self):
        # A naive trailing-zero strip turns "10" into "1".
        a = _parse_action({"subject": "Face Value Split From Rs.10/- to Rs.2/-"})
        assert a["ratio"] == "10:2"

    def test_bonus_ratio(self):
        assert _parse_action({"subject": "Bonus 4:1"})["ratio"] == "4:1"

    def test_dividend_has_no_ratio(self):
        # "Rs 44 Per Share" must not be read as a ratio.
        assert _parse_action({"subject": "Dividend - Rs 44 Per Share"})["ratio"] is None

    def test_symbol_and_isin_are_normalised(self):
        a = _parse_action({"subject": "Bonus 1:1", "symbol": " tcs ", "isin": " INE467B01029 "})
        assert a["symbol"] == "TCS"
        assert a["isin"] == "INE467B01029"


class TestAdjustmentFactor:
    def test_bajfinance_compound_action(self):
        # 4:1 bonus = 5x, 1:2 face-value split = 2x, together 10x.
        actions = [
            _parse_action({"subject": "Bonus 4:1"}),
            _parse_action({"subject": "Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share"}),
        ]
        assert adjustment_factor(actions) == 10.0

    def test_one_for_one_bonus_doubles_share_count(self):
        assert adjustment_factor([_parse_action({"subject": "Bonus 1:1"})]) == 2.0

    def test_four_for_one_bonus_is_five_x_not_four(self):
        # 4 new shares *for every 1 held* leaves you holding 5.
        assert adjustment_factor([_parse_action({"subject": "Bonus 4:1"})]) == 5.0

    def test_two_successive_one_for_one_bonuses_compound(self):
        b = _parse_action({"subject": "Bonus 1:1"})
        assert adjustment_factor([b, b]) == 4.0

    def test_dividends_do_not_change_share_count(self):
        actions = [
            _parse_action({"subject": "Dividend - Rs 44 Per Share"}),
            _parse_action({"subject": "Special Dividend - Rs 12 Per Share"}),
        ]
        assert adjustment_factor(actions) == 1.0

    def test_no_actions_is_identity(self):
        assert adjustment_factor([]) == 1.0

    def test_malformed_ratio_is_skipped_not_fatal(self):
        assert adjustment_factor([{"type": "bonus", "ratio": "banana"}]) == 1.0

    def test_zero_denominator_is_skipped(self):
        assert adjustment_factor([{"type": "split", "ratio": "1:0"}]) == 1.0


class TestDateParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("28-Oct-2024", "2024-10-28"),
        ("16-Jun-2025", "2025-06-16"),
        ("2026-07-22", "2026-07-22"),
        ("31-Jul-2026 18:03:58", "2026-07-31"),
    ])
    def test_known_formats(self, raw, expected):
        assert _parse_nse_date(raw) == expected

    @pytest.mark.parametrize("raw", ["", "-", "NA", None, "not a date"])
    def test_junk_is_none_not_an_exception(self, raw):
        assert _parse_nse_date(raw) is None
