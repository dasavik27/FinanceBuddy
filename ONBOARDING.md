# Onboarding

Everything needed to run Finance Buddy locally and deploy it.

Read ARCHITECTURE.md for design, BUDGET_ANALYSIS.md for Budget domain, SECURITY.md for threat model.

---

## Prerequisites

| Need | Min Version |
|---|---|
| Python | 3.10+ |
| Node.js | 18+ |
| PostgreSQL | 11+ |
| Supabase account | — |
| Google Cloud | — |

---

## Part 1: Supabase & Google OAuth

### 1.1 Create Supabase project
supabase.com/dashboard → New → note Project URL and Publishable key

### 1.2 Get callback URL
Authentication → Providers → Google → copy Callback URL

### 1.3 Create Google OAuth client
console.cloud.google.com:
- OAuth consent screen → External
- Credentials → Web application
- Origins: localhost:5173 + Vercel URL
- Redirects: Supabase callback URL

### 1.4 Connect to Supabase
Providers → Google → paste credentials → Enable

### 1.5 Configure redirects
URL Configuration:
- Site URL: http://localhost:5173
- Redirect: http://localhost:5173/dashboard

---

## Part 2: Local Setup

### 2.1 Dependencies
```
python -m venv venv_finance
source venv_finance/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

### 2.2 Databases
```
createdb financebuddy
createdb financebuddy_test
```

### 2.3 Encryption key
```
python -c "import base64,os;print('k1:'+base64.b64encode(os.urandom(32)).decode())"
```

### 2.4 backend/.env
```
DATABASE_URL=postgresql://postgres:pwd@localhost:5432/financebuddy
FINANCEBUDDY_ENCRYPTION_KEYS=k1:YOUR_KEY
SUPABASE_URL=https://your-ref.supabase.co
```

### 2.5 frontend/.env.local
```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-ref.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_...
```

### 2.6 Migrations
```
cd backend && python -m migrations.migrate
```

### 2.7 Run
```
npm run dev
```

---

## Database Schema

| Migration | What |
|---|---|
| 0001 | Core (users, sessions, payloads) |
| 0002 | Tax payloads |
| 0003 | Equity support |
| 0004 | Budget payloads (Aug 2, 2026) |
| 0005 | Budget rules (Aug 2, 2026) |

---

## Deployment

### Render (Backend)
- Build: pip install -r backend/requirements.txt
- Start: uvicorn main:app --host 0.0.0.0 --port $PORT
- Working dir: backend
- Env: DATABASE_URL, FINANCEBUDDY_ENCRYPTION_KEYS, SUPABASE_URL, FINANCEBUDDY_ALLOWED_ORIGINS

### Vercel (Frontend)
- Framework: Vite
- Build: npm run build
- Output: dist
- Env: VITE_API_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY

---

## Environment Variables

Backend:
- DATABASE_URL: PostgreSQL connection string
- FINANCEBUDDY_ENCRYPTION_KEYS: k1:base64key (required)
- SUPABASE_URL: Supabase project URL
- FINANCEBUDDY_ALLOWED_ORIGINS: CORS whitelist
- FINANCEBUDDY_SLOW_REQUEST_MS: Log threshold (1500 default)
- FINANCEBUDDY_SYNC_CONCURRENCY: Thread cap (8 default)

Frontend:
- VITE_API_URL: Backend API URL
- VITE_SUPABASE_URL: Supabase URL
- VITE_SUPABASE_ANON_KEY: Public key

---

## Verification

```
cd backend
python -m pytest tests/test_sql_is_valid_postgres.py -v
python -m pytest tests/test_only_shared_db_opens_connections.py -v
python backend/scripts/verify_setup.py
```

See VERIFICATION.md for complete checks.
