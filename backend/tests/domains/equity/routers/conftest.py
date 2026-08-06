"""Router tests stub quote/network calls."""

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _no_quotes_network(monkeypatch):
    import domains.equity.quotes as eq_quotes

    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: pd.DataFrame())
    monkeypatch.setattr(eq_quotes, "fetch_quotes", lambda symbols, refresh=False: {})
