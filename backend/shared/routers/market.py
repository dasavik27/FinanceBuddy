"""
routers/market.py
Live market indices and global clock.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from shared.services.cache import get_cache_headers
from shared.services.market_indices import fetch_live_market_summary
from datetime import datetime

router = APIRouter()

@router.get("/summary")
def get_market_summary():
    """
    Live market indices and server time.

    Index levels are user-independent market data, so this is one of the few
    responses that may legitimately be shared-cacheable. The header lets the browser
    absorb the frontend's 60-second poll instead of every tick reaching the server.
    """
    summary = fetch_live_market_summary()
    body = {
        **summary,
        "server_time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d %b, %Y")
    }
    return JSONResponse(content=body, headers=get_cache_headers("market_quote"))
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

# A TTL of 0 or less disabled every cache tier, turning each request into a full
# upstream fan-out - including the AMFI downloads. On ~0.1 vCPU that is a trivial
# denial of service, and it is persisted so it survives a restart. Floored so
# the endpoint can tune caching but not switch it off.
MIN_CACHE_TTL_MINUTES = 1


@router.post("/config")
def update_market_config(ttl: int):
    """
    Tune the market-data cache TTL.

    Requires a signed-in caller. It writes a persisted, deployment-wide setting, so
    while the floor above stops anyone disabling caching outright, an anonymous
    caller could still drive the TTL to the minimum and multiply upstream load for
    every user. Not per-user data, so any authenticated caller is enough - this is a
    rate-limiting concern, not an ownership one.
    """
    from shared import config, db, identity

    if not identity.current_user_id():
        raise HTTPException(status_code=401, detail="Authentication required.")

    ttl = max(MIN_CACHE_TTL_MINUTES, ttl)
    config.CACHE_TTL_MINUTES = ttl

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES ('cache_ttl', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (str(ttl),)
        )
        
    return {"status": "ok", "cache_ttl": config.CACHE_TTL_MINUTES}
