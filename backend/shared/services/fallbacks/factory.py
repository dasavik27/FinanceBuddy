from services.fallbacks.base import InsightFallbackStrategy
from services.fallbacks.deterministic import DeterministicFallback

def get_fallback_engine() -> InsightFallbackStrategy:
    """
    Resolves the active fallback engine for fund metadata estimation.
    Currently defaults to the DeterministicFallback engine, but acts as the precise
    injection point for replacing the fallback methodology in the future.
    """
    return DeterministicFallback()
