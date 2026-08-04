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
          "session_payloads", "tax_payloads", "budget_payloads", "budget_rules",
          "access_requests"]

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

# Expected: all 9 migrations applied
# 0001: Core schema
# 0002: Row-level security
# 0003: Column encryption
# 0004–0007: Budget module
# 0008: access_requests
# 0009: users.status, users.role
```

---

## Code Quality

```bash
cd backend

# SQL validation
python -m pytest tests/test_sql_is_valid_postgres.py -v

# Connection pool validation
python -m pytest tests/test_only_shared_db_opens_connections.py -v

# Auth & access-control tests (requires TEST_DATABASE_URL)
python -m pytest tests/test_user_status_role.py -v
```

---

## Setup Verification Script

The live script is `backend/scripts/verify_setup.py`. It checks required env vars,
Postgres tables (including `access_requests`), migrations 0001–0009, and warns on
missing service role, admin emails, and CORS origins.

```bash
cd backend
python scripts/verify_setup.py
```

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

# Expected: ~875 tests collected; all passing with TEST_DATABASE_URL set.
# Without TEST_DATABASE_URL, database-backed tests skip instead.
# Auth rate-limit unit: tests/test_user_status_role.py::test_public_auth_rate_limit_enforced
```

---

## Pre-Deployment

### Render Backend
- [ ] DATABASE_URL points to production Postgres
- [ ] FINANCEBUDDY_ENCRYPTION_KEYS is production key (different from local)
- [ ] SUPABASE_URL set (JWKS token verification)
- [ ] SUPABASE_SERVICE_ROLE_KEY set (invites + Google email lookup)
- [ ] FINANCEBUDDY_ADMIN_EMAILS set with at least one bootstrap admin
- [ ] FINANCEBUDDY_ALLOWED_ORIGINS includes the production Vercel URL (not localhost-only)
- [ ] Procfile release hook migrates schema; web uses `--workers 1`
- [ ] Health check: `curl https://your-app.onrender.com/health`

### Vercel Frontend
- [ ] VITE_API_URL is the Render origin (not `/api`, not the Vercel URL)
- [ ] VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY set
- [ ] Build succeeds
- [ ] Sign-in works with Google / email after invite

### Supabase
- [ ] URL Configuration has production Vercel URL
- [ ] Redirect URLs include `/` and `/dashboard`
- [ ] Google OAuth still configured
- [ ] Public email sign-up disabled (invite/approve-only)
### Auth & Admin Console
- [ ] Bootstrap admin can sign in and open `/admin`
- [ ] Non-admin visiting `/admin` is redirected to `/dashboard`
- [ ] Approve/invite sends Supabase invite email; only then marks `access_requests` approved
- [ ] Approved user sign-in creates `users` row with `status = active`
- [ ] Unapproved email receives `403 not_authorized` on sign-in
- [ ] `GET /auth/users` with Bearer token lists accounts (admin only) — see [API.md](API.md)
- [ ] From the production site, `POST /auth/access-status` works (CORS smoke)

```bash
# Smoke: replace ACCESS_TOKEN with a Supabase session access_token for an admin
curl -s https://your-app.onrender.com/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -s -X POST https://your-app.onrender.com/auth/access-status \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"you@example.com\"}"
```

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

See ONBOARDING.md for setup, ARCHITECTURE.md for design, domain architecture, auth, and security.

Last updated: 2026-08-04
