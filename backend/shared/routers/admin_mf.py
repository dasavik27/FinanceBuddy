"""
shared/routers/admin_mf.py
Administrative endpoints for managing and syncing AMFI Mutual Fund Portfolio Snapshots.
Strictly requires authenticated admin access.
"""

import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query
from shared import db, identity, users
from shared.services import amfi_ingest

logger = logging.getLogger(__name__)

router = APIRouter()


class SyncTriggerRequest(BaseModel):
    amcs: Optional[List[str]] = None
    preset: Optional[str] = None


def _assert_admin_caller(caller: Optional[identity.Caller]) -> str:
    """
    Ensure the caller is an authenticated administrator.
    Returns the resolved email of the admin.
    """
    if caller is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to access admin operations.",
        )

    # 1. Direct role check
    if getattr(caller, "role", None) == "admin":
        with db.connect() as conn:
            row = conn.execute(
                "SELECT email FROM identities WHERE user_id = %s",
                (caller.user_id,),
            ).fetchone()
            if row and row[0]:
                return row[0].strip().lower()
        return f"admin_{caller.user_id[:8]}"

    # 2. Email allowlist check
    admin_emails = users._admin_emails()
    if not admin_emails:
        raise HTTPException(
            status_code=403,
            detail="Forbidden. No administrator emails configured.",
        )

    with db.connect() as conn:
        row = conn.execute(
            "SELECT email FROM identities WHERE user_id = %s",
            (caller.user_id,),
        ).fetchone()
        user_email = (row[0] or "").strip().lower() if row else ""
        if user_email not in admin_emails:
            raise HTTPException(
                status_code=403,
                detail="Forbidden. Only authorized administrators can trigger market data syncs.",
            )
        return user_email


@router.get("/status")
def get_mf_sync_status():
    """
    Get current AMFI snapshot status, total scheme counts, and recent sync audit history.
    """
    caller = identity.current_caller()
    _assert_admin_caller(caller)
    return amfi_ingest.get_sync_status()


@router.get("/amcs")
def get_synced_amcs():
    """
    Get distinct AMCs currently stored in the database with scheme counts.
    """
    caller = identity.current_caller()
    _assert_admin_caller(caller)
    return {"amcs": amfi_ingest.get_synced_amc_list()}


@router.post("/trigger")
def trigger_mf_sync(body: Optional[SyncTriggerRequest] = None):
    """
    Manually trigger an AMFI snapshot refresh and cache purge.
    Supports selective sync by preset ('top5', 'top10', 'all') or custom AMC list.
    """
    caller = identity.current_caller()
    admin_email = _assert_admin_caller(caller)
    
    amcs = body.amcs if body else None
    preset = body.preset if body else None
    
    logger.info(
        "[ADMIN_MF] AMFI sync triggered by admin %s (preset=%s, amcs=%s)",
        admin_email, preset, amcs
    )
    result = amfi_ingest.trigger_amfi_sync(admin_email, amcs=amcs, preset=preset)
    
    if result.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Sync execution failed: {result.get('error', 'Unknown error')}",
        )
        
    return result


@router.delete("/purge")
def purge_mf_snapshots(
    amc: Optional[str] = Query(None, description="AMC name to selectively delete"),
    purge_all: bool = Query(False, description="Purge all snapshots from database"),
):
    """
    Delete mutual fund snapshots from PostgreSQL database to free storage.
    """
    caller = identity.current_caller()
    admin_email = _assert_admin_caller(caller)

    if not purge_all and not amc:
        raise HTTPException(
            status_code=400,
            detail="Must specify either 'purge_all=true' or 'amc=AMC_NAME' to delete snapshots.",
        )

    logger.warning(
        "[ADMIN_MF] Snapshot purge initiated by %s (purge_all=%s, amc=%s)",
        admin_email, purge_all, amc
    )
    result = amfi_ingest.purge_snapshots(amc=amc, purge_all=purge_all, admin_email=admin_email)
    return result


@router.get("/schemes")
def list_synced_schemes(
    q: Optional[str] = Query("", description="Search term for fund name or ISIN"),
    amc: Optional[str] = Query(None, description="Filter by specific AMC name"),
    category: Optional[str] = Query(None, description="Filter by specific category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Search and inspect mutual fund portfolio disclosures stored in PostgreSQL.
    """
    caller = identity.current_caller()
    _assert_admin_caller(caller)
    return amfi_ingest.search_synced_schemes(
        query=q or "", amc=amc, category=category, limit=limit, offset=offset
    )
