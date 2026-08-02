import uuid
import logging
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from shared import identity
from domains.budget.parser import parse_bank_statement
from domains.budget.categorizer import categorize_transactions
from domains.budget.sessions import save_budget_session, list_budget_sessions, delete_budget_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["budget"])

@router.post("/upload")
async def upload_bank_statement(
    file: UploadFile = File(...),
    bank: str = Form("HDFC"),
    account_type: str = Form("Savings Account")
):
    """Parses a bank/credit card CSV or XLSX and stores it as a budget session."""
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
        
    raw_bytes = await file.read()
    
    df, err = parse_bank_statement(raw_bytes, file.filename, bank, account_type)
    if err or df.empty:
        raise HTTPException(400, detail=err or "No transactions found in file.")
        
    df = categorize_transactions(df, user_id)
    
    session_id = str(uuid.uuid4())
    accounts_meta = {
        "filename": file.filename, 
        "rows": len(df), 
        "account_type": account_type,
        "bank": bank.upper()
    }
    
    save_budget_session(session_id, user_id, df, accounts_meta)
    
    return {"session_id": session_id}

@router.get("/sessions")
async def get_budget_history():
    """Lists all budget upload sessions for the authenticated user."""
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    identity.owns_record(user_id)
    return {"sessions": list_budget_sessions(user_id)}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Deletes a budget upload session."""
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    identity.owns_record(user_id)
    delete_budget_session(user_id, session_id)
    return {"status": "deleted"}
