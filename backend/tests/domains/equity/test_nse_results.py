"""
tests/test_nse_results.py

Cover for the quarterly-results XBRL parser.

This exists because yfinance leaves a specific hole: zero quarterly cash-flow columns
for RELIANCE, ETERNAL and SWIGGY, 2-3 irregular quarterly balance sheets, and no
consolidated-vs-standalone label. The exchange filing has the full income statement and
says which basis it is on.

The dangerous part is not the arithmetic, it is **picking the right period**. A filing
tags the quarter, the year to date and the prior year with the same element names,
distinguished only by `contextRef` - so choosing wrong reports a full year's revenue as
a quarter's, which looks entirely plausible.

No network: every case parses a literal document.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domains.equity import nse_results
from domains.equity.nse_results import parse_results_xbrl
from shared.services.cache import MARKET_CACHE


@pytest.fixture(autouse=True)
def _clear_market_cache():
    MARKET_CACHE.clear()
    yield
    MARKET_CACHE.clear()



def _doc(facts: str, contexts: str = "") -> str:
    default_ctx = """
    <xbrli:context id="Q"><xbrli:period>
      <xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
    </xbrli:period></xbrli:context>
    """
    return (
        '<?xml version="1.0"?><xbrli:xbrl '
        'xmlns:xbrli="http://www.xbrl.org/2003/instance" '
        'xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt">'
        + (contexts or default_ctx) + facts + "</xbrli:xbrl>"
    )


def _fact(name: str, value: str, ctx: str = "Q") -> str:
    return (f'<in-capmkt:{name} contextRef="{ctx}" decimals="-7" unitRef="INR">'
            f'{value}</in-capmkt:{name}>')


# Reliance Q1 FY27 consolidated, as actually filed.
_RELIANCE = _doc(
    _fact("RevenueFromOperations", "3118500000000")
    + _fact("OtherIncome", "65500000000")
    + _fact("Income", "3184000000000")
    + _fact("Expenses", "2877700000000")
    + _fact("ProfitBeforeTax", "306300000000")
    + _fact("TaxExpense", "76290000000")
    + _fact("ProfitLossForPeriod", "231960000000")
    + _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "15.48")
    + _fact("FaceValueOfEquityShareCapital", "10")
    + '<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="Q">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>'
    + '<in-capmkt:WhetherResultsAreAuditedOrUnaudited contextRef="Q">Unaudited</in-capmkt:WhetherResultsAreAuditedOrUnaudited>'
)


class TestRupeeScaling:
    def test_revenue_converts_to_crore(self):
        # 3,118,500,000,000 rupees = Rs 3,11,850 crore.
        assert parse_results_xbrl(_RELIANCE)["revenue_cr"] == 311850.0

    def test_profit_converts_to_crore(self):
        assert parse_results_xbrl(_RELIANCE)["net_income_cr"] == 23196.0

    def test_per_share_figures_are_not_scaled(self):
        # The bug this guards: EPS run through the crore divisor becomes 0.0.
        out = parse_results_xbrl(_RELIANCE)
        assert out["eps_basic"] == 15.48
        assert out["face_value"] == 10.0

    def test_net_margin_is_derived(self):
        assert parse_results_xbrl(_RELIANCE)["net_margin_pct"] == pytest.approx(7.44, abs=0.01)


class TestBasisAndAudit:
    def test_basis_and_audit_status_come_from_the_filing(self):
        out = parse_results_xbrl(_RELIANCE)
        assert out["basis"] == "Consolidated"
        assert out["audited"] == "Unaudited"

    def test_standalone_is_reported_as_such(self):
        doc = _doc(
            _fact("RevenueFromOperations", "1000000000")
            + '<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="Q">Standalone</in-capmkt:NatureOfReportStandaloneConsolidated>'
        )
        assert parse_results_xbrl(doc)["basis"] == "Standalone"


class TestPeriodSelection:
    """
    The quarter, the year to date and the prior year are all tagged with the same
    element names. Picking the wrong context reports a year as a quarter.
    """

    def test_quarter_is_chosen_over_year_to_date(self):
        contexts = """
        <xbrli:context id="Q"><xbrli:period>
          <xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
        </xbrli:period></xbrli:context>
        <xbrli:context id="FY"><xbrli:period>
          <xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
        </xbrli:period></xbrli:context>
        """
        doc = _doc(
            _fact("RevenueFromOperations", "1000000000", ctx="Q")
            + _fact("RevenueFromOperations", "9999000000", ctx="FY"),
            contexts=contexts,
        )
        assert parse_results_xbrl(doc)["revenue_cr"] == 100.0

    def test_instant_contexts_are_ignored(self):
        # A balance-sheet instant has no duration and is not a reporting period.
        contexts = """
        <xbrli:context id="AsAt"><xbrli:period>
          <xbrli:instant>2026-06-30</xbrli:instant>
        </xbrli:period></xbrli:context>
        <xbrli:context id="Q"><xbrli:period>
          <xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
        </xbrli:period></xbrli:context>
        """
        doc = _doc(_fact("RevenueFromOperations", "1000000000", ctx="Q"), contexts=contexts)
        assert parse_results_xbrl(doc)["revenue_cr"] == 100.0

    def test_no_usable_period_yields_none(self):
        contexts = """
        <xbrli:context id="X"><xbrli:period>
          <xbrli:instant>2026-06-30</xbrli:instant>
        </xbrli:period></xbrli:context>
        """
        assert parse_results_xbrl(_doc(_fact("RevenueFromOperations", "1", ctx="X"), contexts)) is None

    def test_annual_only_document_is_rejected(self):
        # A 365-day span is outside the quarter window and must not be read as one.
        contexts = """
        <xbrli:context id="A"><xbrli:period>
          <xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate>
        </xbrli:period></xbrli:context>
        """
        assert parse_results_xbrl(_doc(_fact("RevenueFromOperations", "1", ctx="A"), contexts)) is None


class TestEpsFallback:
    def test_continuing_operations_eps_used_when_combined_is_absent(self):
        doc = _doc(
            _fact("RevenueFromOperations", "1000000000")
            + _fact("BasicEarningsLossPerShareFromContinuingOperations", "12.5")
        )
        assert parse_results_xbrl(doc)["eps_basic"] == 12.5

    def test_combined_eps_wins_when_both_present(self):
        doc = _doc(
            _fact("RevenueFromOperations", "1000000000")
            + _fact("BasicEarningsLossPerShareFromContinuingOperations", "12.5")
            + _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "14.0")
        )
        assert parse_results_xbrl(doc)["eps_basic"] == 14.0


class TestLossMakingCompanies:
    def test_negative_figures_survive(self):
        # Swiggy Q1 FY27: a real loss. Must not be clamped, dropped or made positive.
        doc = _doc(
            _fact("RevenueFromOperations", "68120000000")
            + _fact("ProfitBeforeTax", "-7900000000")
            + _fact("ProfitLossForPeriod", "-7910000000")
            + _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "-2.96")
        )
        out = parse_results_xbrl(doc)
        assert out["net_income_cr"] == -791.0
        assert out["eps_basic"] == -2.96
        assert out["net_margin_pct"] < 0


class TestBankTemplate:
    """
    Banks and NBFCs file under a different SEBI template - `InterestEarned` rather than
    `RevenueFromOperations` - so the Ind-AS mapping matches nothing and the filing was
    skipped entirely. Financials are roughly a third of the Nifty.
    """

    _BANK = _doc(
        _fact("InterestEarned", "905753300000")
        + _fact("OtherIncome", "120000000000")
        + _fact("Income", "1025753300000")
        + _fact("ProfitLossFromOrdinaryActivitiesBeforeTax", "270000000000")
        + _fact("TaxExpense", "66173100000")
        + _fact("ProfitLossForThePeriod", "203826900000")
        + _fact("BasicEarningsPerShareAfterExtraordinaryItems", "12.5")
    )

    def test_interest_earned_maps_to_revenue(self):
        assert parse_results_xbrl(self._BANK)["revenue_cr"] == 90575.33

    def test_bank_profit_line_is_recognised(self):
        # "ProfitLossForThePeriod", not the Ind-AS "ProfitLossForPeriod".
        assert parse_results_xbrl(self._BANK)["net_income_cr"] == 20382.69

    def test_bank_eps_tag_is_recognised(self):
        assert parse_results_xbrl(self._BANK)["eps_basic"] == 12.5

    def test_template_is_reported(self):
        assert parse_results_xbrl(self._BANK)["template"] == "banking"
        assert parse_results_xbrl(_RELIANCE)["template"] == "ind-as"

    def test_npa_ratios_are_not_surfaced(self):
        # Filers disagree on the units: ICICI reports 0.0138 for gross NPA, HDFC Bank
        # reports 0.0 against a real ~1.4%. An absent number beats a wrong one.
        doc = _doc(
            _fact("InterestEarned", "1000000000")
            + _fact("PercentageOfGrossNpa", "0.0138")
            + _fact("CET1Ratio", "0.17")
        )
        out = parse_results_xbrl(doc)
        assert "gross_npa_pct" not in out
        assert "cet1_ratio" not in out


class TestSegmentContexts:
    def test_segment_context_is_not_mistaken_for_the_company(self):
        # Banks file a dozen segment contexts sharing the quarter's exact dates,
        # differing only by an xbrldi dimension. A shortest-duration tiebreak alone can
        # land on one business line and report it as the whole company.
        contexts = """
        <xbrli:context id="Seg1"><xbrli:period>
          <xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
        </xbrli:period>
        <xbrli:scenario><xbrldi:explicitMember dimension="d:Segment">d:Retail</xbrldi:explicitMember></xbrli:scenario>
        </xbrli:context>
        <xbrli:context id="Whole"><xbrli:period>
          <xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
        </xbrli:period></xbrli:context>
        """
        doc = _doc(
            _fact("RevenueFromOperations", "50000000", ctx="Seg1")
            + _fact("RevenueFromOperations", "1000000000", ctx="Whole"),
            contexts=contexts,
        )
        assert parse_results_xbrl(doc)["revenue_cr"] == 100.0

    def test_a_filing_with_only_segment_contexts_yields_none(self):
        contexts = """
        <xbrli:context id="Seg1"><xbrli:period>
          <xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>
        </xbrli:period>
        <xbrli:scenario><xbrldi:explicitMember dimension="d:Segment">d:Retail</xbrldi:explicitMember></xbrli:scenario>
        </xbrli:context>
        """
        assert parse_results_xbrl(_doc(_fact("RevenueFromOperations", "1", ctx="Seg1"), contexts)) is None


class TestRejectsNonResults:
    def test_governance_filing_yields_none(self):
        # Governance and related-party filings share the feed and the taxonomy but
        # carry no results; parsing one as results would report an empty quarter.
        doc = _doc('<in-capmkt:NameOfTheCompany contextRef="Q">Reliance</in-capmkt:NameOfTheCompany>')
        assert parse_results_xbrl(doc) is None

    @pytest.mark.parametrize("xml", ["", None, "<html>not xbrl</html>"])
    def test_junk_input_yields_none(self, xml):
        assert parse_results_xbrl(xml) is None

    def test_oversized_document_is_refused(self):
        assert parse_results_xbrl("<x/>" + "A" * (5 * 1024 * 1024)) is None

    def test_non_numeric_value_does_not_raise(self):
        doc = _doc(_fact("RevenueFromOperations", "not-a-number")
                   + _fact("ProfitLossForPeriod", "1000000000"))
        out = parse_results_xbrl(doc)
        assert out["revenue_cr"] is None
        assert out["net_income_cr"] == 100.0

    def test_zero_revenue_does_not_divide_by_zero(self):
        doc = _doc(_fact("RevenueFromOperations", "0") + _fact("ProfitLossForPeriod", "100"))
        assert parse_results_xbrl(doc)["net_margin_pct"] is None


def test_nse_results_parse_xbrl():
    xml = """
    <xbrli:context id="OneD">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    <in-capmkt:RevenueFromOperations contextRef="OneD">1000000000</in-capmkt:RevenueFromOperations>
    <in-capmkt:ProfitLossForPeriod contextRef="OneD">150000000</in-capmkt:ProfitLossForPeriod>
    <in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD">12.5</in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>
    <in-capmkt:WhetherResultsAreAuditedOrUnaudited>Unaudited</in-capmkt:WhetherResultsAreAuditedOrUnaudited>
    """
    parsed = nse_results.parse_results_xbrl(xml)
    assert parsed is not None
    assert parsed["template"] == "ind-as"
    assert parsed["revenue_cr"] == 100.0
    assert parsed["net_income_cr"] == 15.0
    assert parsed["eps_basic"] == 12.5
    assert parsed["audited"] == "Unaudited"

    bank_xml = """
    <xbrli:context id="BankQ">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    <in-capmkt:InterestEarned contextRef="BankQ">500000000</in-capmkt:InterestEarned>
    <in-capmkt:ProfitLossForThePeriod contextRef="BankQ">80000000</in-capmkt:ProfitLossForThePeriod>
    """
    bank = nse_results.parse_results_xbrl(bank_xml)
    assert bank is not None
    assert bank["template"] == "banking"

    assert nse_results.parse_results_xbrl("") is None
    assert nse_results.parse_results_xbrl("x" * (nse_results._MAX_XBRL_BYTES + 1)) is None

def test_nse_results_latest(monkeypatch):
    filing_list = {
        "data": [
            {
                "qe_Date": "31-Dec-2024",
                "consolidated": "Consolidated",
                "xbrl": "https://example.com/results.xbrl",
                "broadcast_Date": "01-Feb-2025",
            },
        ],
    }
    xbrl = """
    <xbrli:context id="Q1">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    <in-capmkt:RevenueFromOperations contextRef="Q1">2000000000</in-capmkt:RevenueFromOperations>
    <in-capmkt:ProfitLossForPeriod contextRef="Q1">200000000</in-capmkt:ProfitLossForPeriod>
    """

    class FakeResp:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if "integrated-filing-results" in url:
            return FakeResp(200, filing_list)
        return FakeResp(200, text=xbrl)

    monkeypatch.setattr(nse_results.requests, "get", fake_get)
    result = nse_results.latest_results("RELIANCE")
    assert result is not None
    assert result["symbol"] == "RELIANCE"
    assert result["revenue_cr"] == 200.0

    monkeypatch.setattr(nse_results.requests, "get", MagicMock(side_effect=RuntimeError("blocked")))
    MARKET_CACHE.clear()
    assert nse_results.latest_results("TCS") is None

def test_nse_results_helpers_and_fetch_edges(monkeypatch):
    assert nse_results._num("not-a-number") is None

    xml_no_ctx = "<xbrli:context id='x'><xbrli:startDate>2024-01-01</xbrli:startDate></xbrli:context>"
    assert nse_results._quarter_context(xml_no_ctx) is None

    seg_ctx = """
    <xbrli:context id="Seg">
      <xbrli:segment><xbrldi:explicitMember dimension="d">Bank</xbrldi:explicitMember></xbrli:segment>
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    """
    assert nse_results._quarter_context(seg_ctx) is None

    bad_date_ctx = """
    <xbrli:context id="Bad">
      <xbrli:startDate>not-a-date</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    """
    assert nse_results._quarter_context(bad_date_ctx) is None

    short_ctx = """
    <xbrli:context id="Short">
      <xbrli:startDate>2024-12-01</xbrli:startDate>
      <xbrli:endDate>2024-12-10</xbrli:endDate>
    </xbrli:context>
    """
    assert nse_results._quarter_context(short_ctx) is None

    gov_xml = """
    <xbrli:context id="Gov">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    <in-capmkt:OtherIncome contextRef="Gov">100</in-capmkt:OtherIncome>
    """
    assert nse_results.parse_results_xbrl(gov_xml) is None

    eps_xml = """
    <xbrli:context id="Eps">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    <in-capmkt:RevenueFromOperations contextRef="Eps">1000000000</in-capmkt:RevenueFromOperations>
    <in-capmkt:ProfitLossForPeriod contextRef="Eps">100000000</in-capmkt:ProfitLossForPeriod>
    <in-capmkt:BasicEarningsLossPerShareFromContinuingOperations contextRef="Eps">5.5</in-capmkt:BasicEarningsLossPerShareFromContinuingOperations>
    """
    eps = nse_results.parse_results_xbrl(eps_xml)
    assert eps is not None
    assert eps["eps_basic"] == 5.5

    class FakeResp:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    monkeypatch.setattr(
        nse_results.requests, "get",
        lambda url, **k: FakeResp(503),
    )
    assert nse_results._fetch_latest("RELIANCE") is None

    empty_rows = {"data": [{"qe_Date": "31-Dec-2024", "consolidated": "Other", "xbrl": ""}]}
    monkeypatch.setattr(
        nse_results.requests, "get",
        lambda url, **k: FakeResp(200, empty_rows),
    )
    assert nse_results._fetch_latest("RELIANCE") is None

    bad_date_rows = {
        "data": [{
            "qe_Date": "bad-date",
            "consolidated": "Consolidated",
            "xbrl": "https://example.com/x.xbrl",
            "broadcast_Date": "01-Jan-2025",
        }],
    }
    xbrl_ok = """
    <xbrli:context id="Q1">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    <in-capmkt:RevenueFromOperations contextRef="Q1">1000000000</in-capmkt:RevenueFromOperations>
    <in-capmkt:ProfitLossForPeriod contextRef="Q1">100000000</in-capmkt:ProfitLossForPeriod>
    """

    def mixed_get(url, **kwargs):
        if "integrated-filing-results" in url:
            return FakeResp(200, bad_date_rows)
        if kwargs.get("timeout"):
            return FakeResp(404)
        return FakeResp(200, text=xbrl_ok)

    monkeypatch.setattr(nse_results.requests, "get", mixed_get)
    assert nse_results._fetch_latest("RELIANCE") is None

    def xbrl_fail(url, **kwargs):
        if "integrated-filing-results" in url:
            return FakeResp(200, bad_date_rows)
        raise RuntimeError("xbrl down")

    monkeypatch.setattr(nse_results.requests, "get", xbrl_fail)
    assert nse_results._fetch_latest("RELIANCE") is None

    instant_ctx = """
    <xbrli:context id="Instant">
      <xbrli:instant>2024-12-31</xbrli:instant>
    </xbrli:context>
    """
    assert nse_results._quarter_context(instant_ctx) is None

    no_facts = """
    <xbrli:context id="EmptyQ">
      <xbrli:startDate>2024-10-01</xbrli:startDate>
      <xbrli:endDate>2024-12-31</xbrli:endDate>
    </xbrli:context>
    """
    assert nse_results.parse_results_xbrl(no_facts) is None

    no_ctx_xml = "<in-capmkt:RevenueFromOperations contextRef='Missing'>1</in-capmkt:RevenueFromOperations>"
    assert nse_results.parse_results_xbrl(no_ctx_xml) is None
