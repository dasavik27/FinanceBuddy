
"""Equity sector/industry mapping."""

from domains.equity.sector_map import (
    DEFAULT_INDUSTRY,
    DEFAULT_SECTOR,
    get_all_sectors,
    get_sector,
)


class TestSectorMap:
    def test_get_sector_known(self):
        assert get_sector("RELIANCE") == ("Energy", "Oil & Gas")
        assert get_sector("tcs-eq") == ("Information Technology", "IT Services")

    def test_get_sector_unknown(self):
        assert get_sector("NOTINMAP") == (DEFAULT_SECTOR, DEFAULT_INDUSTRY)

    def test_get_all_sectors(self):
        sectors = get_all_sectors()
        assert "Energy" in sectors
        assert "Financials" in sectors
        assert sectors == sorted(sectors)

