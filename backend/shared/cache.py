import json
import os
import time
from typing import Any, Optional
from shared.config import CACHE_DIR, CACHE_TTL_MINUTES
import logging
logger = logging.getLogger(__name__)


class MarketCache:
    """
    MarketCache: Persistent JSON cache for institutional data.
    Ensures high-fidelity audits are performant while allowing on-demand refreshes.
    """
    
    @staticmethod
    def _get_path(key: str) -> str:
        # Sanitize key for filesystem
        safe_key = "".join([c if c.isalnum() else "_" for c in key])
        return os.path.join(CACHE_DIR, f"{safe_key}.json")

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Retrieve verified data from cache if not expired."""
        if CACHE_TTL_MINUTES <= 0:
            return None
            
        path = cls._get_path(key)
        if not os.path.exists(path):
            return None
            
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                
            # Expiry check
            timestamp = data.get("_timestamp", 0)
            if (time.time() - timestamp) > (CACHE_TTL_MINUTES * 60):
                return None
                
            return data.get("payload")
        except Exception:
            return None

    @classmethod
    def set(cls, key: str, value: Any):
        """Persist verified data to cache."""
        path = cls._get_path(key)
        try:
            data = {
                "_timestamp": time.time(),
                "payload": value
            }
            with open(path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"[CACHE ERROR] Failed to persist {key}: {e}")

    @classmethod
    def invalidate(cls, key_pattern: str = ""):
        """Clear specific cache or all data."""
        try:
            for f in os.listdir(CACHE_DIR):
                if not key_pattern or key_pattern in f:
                    os.remove(os.path.join(CACHE_DIR, f))
        except Exception:
            pass
