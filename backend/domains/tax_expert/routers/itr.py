"""
routers/itr.py

Tax Expert - ITR Comparison
===========================
Upload a filed ITR PDF and retrieve its extracted summary for post-filing comparison.
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from domains.tax_expert.itr_parser import parse_itr_pdf
from domains.tax_expert.tax_sessions import get_tax_session, update_itr_data, get_itr_data

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{session_id}/tax/itr")
def upload_itr(session_id: str, file: UploadFile = File(...)):
    """Upload a filed ITR PDF and extract summary figures for comparison.

    Sync `def` on purpose: pdfplumber layout extraction plus ~50 full-document
    regex passes are blocking CPU work that must not run on the event loop.
    """
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    raw = file.file.read()
    try:
        itr_data = parse_itr_pdf(raw)
        update_itr_data(session_id, itr_data)
        return {"status": "success", "itr_data": itr_data}
    except Exception as e:
        logger.error(f"Failed to parse ITR PDF: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse ITR document: {str(e)}")


@router.get("/{session_id}/tax/itr")
def get_itr(session_id: str):
    """
    Retrieve previously uploaded ITR summary for comparison.

    Sync `def`: get_tax_session() can trigger _ensure_loaded(), which reads every
    stored session blob from SQLite and json.loads each one - blocking work that
    must not run on the event loop of a single-worker deployment.
    """
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    itr_data = get_itr_data(session_id)
    if not itr_data:
        raise HTTPException(status_code=404, detail="No ITR data uploaded for this session")

    return {"status": "success", "itr_data": itr_data}
