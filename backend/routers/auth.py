from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import sqlite3
import re
from core.storage import DB_PATH

router = APIRouter()

class LoginRequest(BaseModel):
    pan: str

@router.post("/login")
def login_with_pan(req: LoginRequest):
    pan = req.pan.strip().upper()
    
    # Basic PAN validation (5 letters, 4 numbers, 1 letter)
    # Some users might have slightly different PANs, but this is standard.
    if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan):
        raise HTTPException(status_code=400, detail="Invalid PAN format. Must be 10 characters (e.g. ABCDE1234F).")
        
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT pan_id FROM users WHERE pan_id = ?", (pan,))
        user = cursor.fetchone()
        
        if not user:
            # Create the user profile
            conn.execute("INSERT INTO users (pan_id) VALUES (?)", (pan,))
            
            # MIGRATION STRATEGY: Attach orphaned sessions to the FIRST user created.
            # This ensures the user doesn't lose their existing CAS files after this update.
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            if user_count == 1:
                print(f"[AUTH] First user {pan} created. Migrating orphaned sessions...")
                conn.execute("UPDATE sessions SET pan_id = ? WHERE pan_id IS NULL", (pan,))
                
            conn.commit()
            print(f"[AUTH] New user profile created for PAN: {pan}")
        else:
            print(f"[AUTH] Existing user logged in: {pan}")
            
    return {"status": "success", "pan": pan}

@router.post("/logout")
def logout_user(req: LoginRequest):
    pan = req.pan.strip().upper()
    from core.tax_sessions import get_sessions_by_pan, delete_tax_session
    sessions = get_sessions_by_pan(pan)
    for s in sessions:
        delete_tax_session(s["session_id"])
    print(f"[AUTH] Logged out {pan} and cleared {len(sessions)} tax sessions from memory and disk.")
    return {"status": "success"}
