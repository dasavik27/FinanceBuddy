from abc import ABC, abstractmethod
from typing import Dict

class InsightFallbackStrategy(ABC):
    """
    Abstract contract for the Insights Fallback Engine.
    Guarantees a rigid, future-proof structure for estimating missing fund metadata.
    """
    
    @abstractmethod
    def generate_fallbacks(self, isin: str, category: str, fund_name: str, current_result: Dict) -> Dict:
        """
        Injects fallback estimations (AUM, Risk, Exit Load, ER) into the current result payload.
        
        Args:
            isin (str): The fund ISIN.
            category (str): The fund's asset category (e.g., "Large Cap").
            fund_name (str): The full name of the fund.
            current_result (Dict): The existing dictionary containing any successfully fetched metadata.
            
        Returns:
            Dict: The enriched dictionary with deterministic fallback values and boolean flags.
        """
        pass  # pragma: no cover — abstract contract
