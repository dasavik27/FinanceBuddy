from abc import ABC, abstractmethod
from typing import Dict

class BaseMetadataProvider(ABC):
    """
    Abstract base class for all Mutual Fund metadata providers.
    Follows the Adapter pattern to allow seamless swapping between Yahoo, Groww, Upstox, etc.
    """
    
    @abstractmethod
    def fetch_insights(self, isin: str, fund_name: str, category: str) -> Dict:
        """
        Fetch institutional insights for a specific fund.
        
        Args:
            isin (str): The ISIN of the mutual fund.
            fund_name (str): The name of the fund (used for resolving if ISIN fails).
            category (str): The category of the fund (e.g. Equity, Debt).
            
        Returns:
            Dict: A standard dictionary conforming to the unified schema:
                {
                    "source": str | None,
                    "sectors": list,
                    "holdings": list,
                    "risk": str | None,
                    "exit_load": str | None,
                    "expense_ratio": float | None,
                    "aum": str | None,
                    # Fallback flags (always initialized to False, FallbackEngine will set to True if needed)
                    "aum_fallback": bool,
                    "risk_fallback": bool,
                    "exit_load_fallback": bool,
                    "expense_ratio_fallback": bool,
                }
        """
        pass
    
    def _get_empty_result(self) -> Dict:
        """Returns the base empty result template."""
        return {
            "source": None,
            "sectors": [],
            "holdings": [],
            "risk": None,
            "exit_load": None,
            "expense_ratio": None,
            "aum": None,
            "aum_fallback": False,
            "risk_fallback": False,
            "exit_load_fallback": False,
            "expense_ratio_fallback": False,
        }

import pandas as pd
from typing import List, Any

class MarketDataProvider(ABC):
    """
    Abstract base class for all historical market data providers (e.g. NAV fetching).
    """
    
    @abstractmethod
    def fetch_nav_series(self, scheme_code: str, days: int) -> pd.Series:
        """Fetch NAV history and return it as a pandas Series."""
        pass
        
    @abstractmethod
    def fetch_fund_meta(self, scheme_code: str) -> Dict[str, Any]:
        """Fetch fund metadata (name, house, type)."""
        pass
        
    @abstractmethod
    def search_funds(self, query: str) -> List[Dict[str, Any]]:
        """Search the provider's registry."""
        pass
