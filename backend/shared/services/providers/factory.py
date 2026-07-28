"""
services/providers/factory.py
Factory pattern for instantiating market data providers.
"""

import os
from .base import MarketDataProvider
from .mfapi import MFApiProvider

# Cache the provider instance so we don't recreate sessions for every call
_PROVIDER_INSTANCE = None

def get_provider() -> MarketDataProvider:
    """
    Returns the configured MarketDataProvider.
    Future-proof: Reads from env variable or config to swap providers easily.
    """
    global _PROVIDER_INSTANCE
    
    if _PROVIDER_INSTANCE is not None:
        return _PROVIDER_INSTANCE

    # Hardcode for now, but could be dynamic based on os.getenv("MARKET_DATA_PROVIDER")
    provider_name = os.getenv("MARKET_DATA_PROVIDER", "mfapi").lower()
    
    if provider_name == "mfapi":
        _PROVIDER_INSTANCE = MFApiProvider()
    else:
        # Fallback to default
        _PROVIDER_INSTANCE = MFApiProvider()
        
    return _PROVIDER_INSTANCE
