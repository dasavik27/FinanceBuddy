#!/usr/bin/env python
"""
Verify Finance Buddy setup is complete and correct.

Run: python scripts/verify_setup.py
"""
import os
import sys
from pathlib import Path

def check(name, condition, details=""):
    status = "✓" if condition else "✗"
    msg = f"{status} {name}"
    if details:
        msg += f" — {details}"
    print(msg)
    return condition

def main():
    all_ok = True
    
    print("\n=== Environment ===")
    all_ok &= check("DATABASE_URL", bool(os.getenv("DATABASE_URL")))
    all_ok &= check("FINANCEBUDDY_ENCRYPTION_KEYS", bool(os.getenv("FINANCEBUDDY_ENCRYPTION_KEYS")))
    all_ok &= check("SUPABASE_URL", bool(os.getenv("SUPABASE_URL")))
    check("FINANCEBUDDY_ADMIN_EMAILS (recommended)", bool(os.getenv("FINANCEBUDDY_ADMIN_EMAILS")))
    check("SUPABASE_SERVICE_ROLE_KEY (recommended for invites)", bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
    
    print("\n=== Database Connection ===")
    try:
        from shared import db
        pool = db.get_pool()
        with pool.connection() as conn:
            version = conn.execute("SELECT version()").fetchone()[0]
            all_ok &= check("PostgreSQL", "Postgres" in version, version.split(",")[0])
            
            # Check all required tables
            tables = ["users", "identities", "profiles", "sessions", 
                     "session_payloads", "tax_payloads", "budget_payloads", "budget_rules",
                     "access_requests"]
            result = conn.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """).fetchall()
            existing = {row[0] for row in result}
            
            for table in tables:
                all_ok &= check(f"  {table}", table in existing)
            
    except Exception as e:
        all_ok = False
        print(f"✗ Database check failed: {e}")
    
    print("\n=== Files ===")
    all_ok &= check("backend/.env", Path(".env").exists())
    all_ok &= check("domains/budget/", Path("domains/budget").is_dir())
    all_ok &= check("domains/mutual_funds/", Path("domains/mutual_funds").is_dir())
    all_ok &= check("domains/equity/", Path("domains/equity").is_dir())
    all_ok &= check("domains/tax_expert/", Path("domains/tax_expert").is_dir())
    
    print("\n=== Migrations ===")
    try:
        from migrations import migrate
        status = migrate.get_status()
        for mig_num, applied in status:
            all_ok &= check(f"  Migration {mig_num:04d}", applied)
    except Exception as e:
        print(f"✗ Migration check failed: {e}")
    
    print("\n" + ("="*50))
    if all_ok:
        print("✓ All checks passed! Setup is complete.")
        return 0
    else:
        print("✗ Some checks failed. See above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
