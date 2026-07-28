"""
routers/market.py
Live market indices and global clock.
"""

from fastapi import APIRouter
from shared.services.market_indices import fetch_live_market_summary
from datetime import datetime

router = APIRouter()

@router.get("/summary")
def get_market_summary():
    """Returns live market indices and server time."""
    summary = fetch_live_market_summary()
    return {
        **summary,
        "server_time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d %b, %Y")
    }
@router.get("/nav/{isin}")
def get_live_nav(isin: str):
    """Fetch live NAV for a specific fund by ISIN."""
    from shared.services.market_data import fetch_live_navs
    live_map = fetch_live_navs()
    nav = live_map.get(isin.upper())
    return {"isin": isin, "nav": nav}

@router.get("/config")
def get_market_config():
    from shared import config
    return {"cache_ttl": config.CACHE_TTL_MINUTES}

@router.post("/config")
def update_market_config(ttl: int):
    from shared import config
    from shared.storage import DB_PATH
    import sqlite3
    
    config.CACHE_TTL_MINUTES = ttl
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('cache_ttl', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(ttl),)
        )
        conn.commit()
        
    return {"status": "ok", "cache_ttl": config.CACHE_TTL_MINUTES}
