# Verification Checklist

Complete setup validation for Finance Buddy. Run after ONBOARDING.md Part 2, before deployment.

---

## Quick Check (5 min)

```bash
# 1. Check files
test -f backend/.env && echo "✓ backend/.env" || echo "✗ backend/.env"
test -f frontend/.env.local && echo "✓ frontend/.env.local" || echo "✗ frontend/.env.local"

# 2. Check Python/Node
python --version
node --version
npm --version

# 3. Check databases
psql -l | grep financebuddy && echo "✓ Databases" || echo "✗ No databases"

# 4. Check venv
test -d venv_finance && echo "✓ venv" || echo "✗ venv"
```

---

## Environment Variables

```bash
# Backend checks
cd backend
echo "DATABASE_URL is set: $(test -n "$DATABASE_URL" && echo Yes || echo No)"
echo "FINANCEBUDDY_ENCRYPTION_KEYS is set: $(test -n "$FINANCEBUDDY_ENCRYPTION_KEYS" && echo Yes || echo No)"
echo "SUPABASE_URL=$SUPABASE_URL"

# Frontend checks
cd ../frontend
echo "VITE_API_URL=$VITE_API_URL"
echo "VITE_SUPABASE_URL=$VITE_SUPABASE_URL"
echo "VITE_SUPABASE_ANON_KEY is set: $(test -n "$VITE_SUPABASE_ANON_KEY" && echo Yes || echo No)"
```

---

## Database Connection

```bash
cd backend
python << 'PYEOF'
from shared import db
try:
    pool = db.get_pool()
    with pool.connection() as conn:
        result = conn.execute("SELECT version()").fetchone()
        print(f"✓ PostgreSQL: {result[0].split(',')[0]}")
except Exception as e:
    print(f"✗ Connection failed: {e}")
PYEOF
```

---

## Schema Validation

```bash
cd backend
python << 'PYEOF'
from shared import db

tables = ["users", "identities", "profiles", "sessions", 
          "session_payloads", "tax_payloads", "budget_payloads", "budget_rules"]

try:
    with db.get_pool().connection() as conn:
        result = conn.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """).fetchall()
        existing = {row[0] for row in result}
        
        print(f"Found {len(existing)} tables:")
        for t in tables:
            status = "✓" if t in existing else "✗"
            print(f"  {status} {t}")
            
except Exception as e:
    print(f"✗ Schema check failed: {e}")
PYEOF
```

---

## Migrations

```bash
cd backend
python -m migrations.migrate --status

# Expected: all 5 migrations applied
# 0001: Core schema
# 0002: Tax payloads
# 0003: Equity support
# 0004: Budget payloads (Aug 2, 2026)
# 0005: Budget rules (Aug 2, 2026)
```

---

## Code Quality

```bash
cd backend

# SQL validation
python -m pytest tests/test_sql_is_valid_postgres.py -v

# Connection pool validation
python -m pytest tests/test_only_shared_db_opens_connections.py -v

# Budget domain tests
python -m pytest tests/ -k budget -v
```

---

## Setup Verification Script

Create `backend/scripts/verify_setup.py`:

```python
#!/usr/bin/env python
import os
from pathlib import Path

def check(name, ok):
    print(f"{'✓' if ok else '✗'} {name}")
    return ok

def main():
    print("\n=== Environment ===")
    all_ok = True
    all_ok &= check("DATABASE_URL", bool(os.getenv("DATABASE_URL")))
    all_ok &= check("FINANCEBUDDY_ENCRYPTION_KEYS", bool(os.getenv("FINANCEBUDDY_ENCRYPTION_KEYS")))
    all_ok &= check("SUPABASE_URL", bool(os.getenv("SUPABASE_URL")))
    
    print("\n=== Database ===")
    try:
        from shared import db
        with db.get_pool().connection() as conn:
            conn.execute("SELECT 1")
            all_ok &= check("PostgreSQL connection", True)
            
            result = conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'public'
            """).fetchone()
            all_ok &= check(f"Tables ({result[0]} found)", result[0] >= 8)
    except Exception as e:
        all_ok = False
        print(f"✗ Database: {e}")
    
    print("\n=== Files ===")
    all_ok &= check("backend/.env", Path("backend/.env").exists())
    all_ok &= check("frontend/.env.local", Path("frontend/.env.local").exists())
    all_ok &= check("domains/budget/", Path("domains/budget").is_dir())
    
    print("\n" + "="*40)
    print(f"{'✓ Ready!' if all_ok else '✗ Setup incomplete'}")
    return 0 if all_ok else 1

if __name__ == "__main__":
    exit(main())
```

Run: `python scripts/verify_setup.py`

---

## Frontend Build

```bash
cd frontend
npm run build
test -d dist && echo "✓ Build successful" || echo "✗ Build failed"
```

---

## Full Test Suite

```bash
cd backend
export TEST_DATABASE_URL=postgresql://postgres:pwd@localhost:5432/financebuddy_test
python -m pytest tests/ -q

# Expected: 687 tests, all passing.
# Without TEST_DATABASE_URL, 111 of them skip instead.
```

---

## Pre-Deployment

### Render Backend
- [ ] DATABASE_URL points to production Postgres
- [ ] FINANCEBUDDY_ENCRYPTION_KEYS is production key (different from local)
- [ ] FINANCEBUDDY_ALLOWED_ORIGINS includes Vercel URL
- [ ] Health check: `curl https://your-app.onrender.com/health`

### Vercel Frontend
- [ ] VITE_API_URL points to production Render URL
- [ ] Build succeeds
- [ ] Sign-in works with Google

### Supabase
- [ ] URL Configuration has production Vercel URL
- [ ] Redirect URLs include `/dashboard`
- [ ] Google OAuth still configured

---

## Budget Domain Checks

```bash
cd backend
python << 'PYEOF'
from pathlib import Path
from shared import db

# Check files
files = ["domains/budget/parser.py", "domains/budget/categorizer.py", 
         "domains/budget/sessions.py"]
for f in files:
    ok = Path(f).exists()
    print(f"{'✓' if ok else '✗'} {f}")

# Check tables
try:
    with db.get_pool().connection() as conn:
        result = conn.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_name LIKE 'budget%'
        """).fetchall()
        print(f"✓ Budget tables: {len(result)} found")
except:
    print("✗ Budget table check failed")
PYEOF
```

---

See ONBOARDING.md for setup, ARCHITECTURE.md for design, domain architecture, and security.

Last updated: 2026-08-02
