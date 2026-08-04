# Onboarding

Everything needed to run Finance Buddy locally and deploy it.

Read ARCHITECTURE.md for system design, domain architecture, and security model.

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
- Redirect URLs: `http://localhost:5173/` and `http://localhost:5173/dashboard`
  (Google OAuth returns to `/` so unregistered users see access-request messaging)

### 1.6 Lock down sign-up (required for admin-controlled access)

Finance Buddy is invite/approve-only. Random visitors must not be able to create
Auth users in Supabase.

In the Supabase dashboard:

1. **Authentication → Providers → Email** — turn **off** “Allow new users to sign up”
   (or the project-level equivalent that disables public sign-up). Keep email
   password sign-in enabled so invited users can set a password from the invite
   link and sign in afterwards.
2. Keep the Google provider enabled for users who already have a Supabase Auth
   account (created by Admin invite / approve).
3. Copy the **service_role** key (Project Settings → API) into backend `.env` as
   `SUPABASE_SERVICE_ROLE_KEY`. Used to:
   - send Supabase **invite emails** (users set their own password)
   - resolve email for Google OAuth when the JWT omits the email claim
   Without it, approve/invite fails, and some Google sign-ins may look “not authorized”
   even for approved emails.

Also set `FINANCEBUDDY_ADMIN_EMAILS` in backend `.env` to a comma-separated list
of bootstrap admin emails. Those accounts get `role=admin` on first sign-in, and
admin API routes deny everyone else when this list is empty and the caller is
not already `role=admin`.

### 1.7 Access & onboarding flow

There are two layers: **Supabase Auth** (can this person sign in?) and the **app
account** (`users` + `identities` in Postgres — can they use Finance Buddy?).

```mermaid
flowchart LR
  A[Prospect] -->|Request access| B[access_requests pending]
  A -->|Admin invite| C[access_requests approved]
  B -->|Admin approve| C
  C -->|Supabase invite email| D[Supabase Auth user]
  D -->|First sign-in| E[users row created]
  E -->|status active| F[PAN prompt then dashboard]
  E -->|status pending| G[PendingAccess screen]
  G -->|Admin activates| F
```

**Step by step:**

1. **Request or invite** — Prospect submits **Request access** on the landing page,
   or an admin uses **Invite user** in the Admin Console (`/admin`).
2. **Admin approve / invite** — Backend sends a Supabase **invite email** (user
   sets their own password), then sets `access_requests.status = 'approved'` and
   promotes any existing `users` row from `pending` → `active` for that email.
   If the invite fails, the request stays pending / is not allowlisted.
3. **First sign-in** — The `users` table row is **not** created at approval time.
   It is inserted on the user's **first authenticated API request** when
   `users.resolve()` runs in middleware, but only if the email is allowlisted
   (approved access request, pending access request, or admin email).
   - Approved at first sign-in → `users.status = active`
   - Pending request at first sign-in → `users.status = pending` (wait screen)
4. **Unapproved sign-in** — No `users` row is created; middleware returns
   `403 not_authorized`. The landing page calls `POST /auth/access-status` to
   show “already submitted” vs “raise request”.
5. **After active** — User completes mandatory PAN if missing, then reaches the
   dashboard. Admins see **Admin Console** in the profile menu (`role=admin`).

**Admin Console** (`/admin`, visible when `GET /auth/me` returns `role: admin`):

| Section | Purpose |
|---|---|
| Access requests | Review leads, approve (invite email), reject |
| Invite user | Direct allowlist + Supabase invite without a prior request |
| Suspend user | Set `users.status = suspended` and ban in Supabase when configured |
| User accounts | List accounts; set status/role; permanent delete |

API catalog and Bearer token usage: **[API.md](API.md)**.  
Auth design / middleware: ARCHITECTURE.md → *Authentication & access control*.

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
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
FINANCEBUDDY_ADMIN_EMAILS=you@example.com
FINANCEBUDDY_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
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
cd frontend && npm run dev:all
```
Starts Vite on 5173 and uvicorn on 8000 together. `npm run dev` alone is
frontend-only, and there is no package.json at the repo root.

---

## Database Schema

| Migration | What |
|---|---|
| 0001 | Core (`users`, `identities`, `profiles`, `sessions`, payloads) |
| 0002 | Row-level security (deny-all backstop) |
| 0003 | Application-level encryption for sensitive columns |
| 0004 | Budget payloads |
| 0005 | Budget rules |
| 0006 | Budget hardening |
| 0007 | Budget accounts metadata |
| 0008 | `access_requests` (invite-only early access) |
| 0009 | `users.status`, `users.role` (pending / active / suspended; user / admin) |

Full migration descriptions are in ARCHITECTURE.md.

---

## Deployment

### Render (Backend)

The repo `Procfile` already sets:

- **release:** `cd backend && python -m migrations.migrate` (runs before each deploy)
- **web:** uvicorn with **`--workers 1`** (required: in-process rate limits and caches
  are per worker)

Configure:

- Build: `pip install -r backend/requirements.txt`
- Working dir: repo root (Procfile `cd`s into `backend`) or set root to `backend`
  and adjust the Procfile commands accordingly
- Env (required for production):
  - `DATABASE_URL`
  - `FINANCEBUDDY_ENCRYPTION_KEYS` (**different** from local)
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `FINANCEBUDDY_ADMIN_EMAILS`
  - `FINANCEBUDDY_ALLOWED_ORIGINS` — **must** include your Vercel URL  
    (e.g. `https://your-app.vercel.app`). If unset, CORS defaults to **localhost
    only** and the production frontend cannot call the API.

### Vercel (Frontend)
- Framework: Vite
- Build: `npm run build`
- Output: `dist`
- Env (all required — there is no usable default in production):
  - `VITE_API_URL` — Render backend origin, e.g. `https://your-app.onrender.com`
  - `VITE_SUPABASE_URL`
  - `VITE_SUPABASE_ANON_KEY`

`VITE_API_URL` must be the **backend origin**, not `/api`. If unset, the client
falls back to `/api`, which Vercel does not proxy. Public auth helpers
(`access-status`, `request-access`) call the backend directly.

Also set Supabase Auth redirect URLs to the production Vercel origin (`/` and
`/dashboard`). Keep public email sign-up **off**.

---

## Environment Variables

Backend — required:
- DATABASE_URL: PostgreSQL connection string
- FINANCEBUDDY_ENCRYPTION_KEYS: `k1:base64key`. No plaintext fallback — the app raises
  rather than writing sensitive columns unencrypted
- SUPABASE_URL: Supabase project URL
- FINANCEBUDDY_ADMIN_EMAILS: comma-separated bootstrap admin emails (also used to
  authorize Admin Console APIs). Alias: `ADMIN_EMAILS`

Backend — required in production (defaults are local-only or incomplete):
- FINANCEBUDDY_ALLOWED_ORIGINS: CORS whitelist. Defaults to
  `http://localhost:5173,http://127.0.0.1:5173` — **must** list the Vercel URL in prod
- SUPABASE_SERVICE_ROLE_KEY: service_role secret for invites + Google email lookup
  (never expose to the frontend). Alias: `SUPABASE_SERVICE_KEY`

JWT verification uses Supabase JWKS only (`SUPABASE_URL` → asymmetric ES256/RS256).
No JWT secret env var is used.

Backend — optional OIDC overrides (normally derived from `SUPABASE_URL`):
- AUTH_JWKS_URL / SUPABASE_JWKS_URL
- AUTH_ISSUER (default `{SUPABASE_URL}/auth/v1`)
- AUTH_AUDIENCE (default `authenticated`)

Backend — optional, defaults tuned for a single worker on ~512 MB:
- FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY: which key id to encrypt *new* data with, when
  rotating. Decryption always tries every key in FINANCEBUDDY_ENCRYPTION_KEYS
- FINANCEBUDDY_SLOW_REQUEST_MS: slow-request log threshold (1500)
- FINANCEBUDDY_SYNC_CONCURRENCY: anyio threadpool cap for sync handlers (8)
- FINANCEBUDDY_DB_POOL_MIN / FINANCEBUDDY_DB_POOL_MAX: connection pool bounds
- FINANCEBUDDY_DB_STATEMENT_TIMEOUT_MS: per-statement timeout
- FINANCEBUDDY_MAX_RESIDENT_SESSIONS: resident mutual-fund portfolios (3)
- FINANCEBUDDY_MAX_RESIDENT_EQUITY_SESSIONS: resident equity portfolios (3)
- FINANCEBUDDY_MAX_TAX_SESSIONS: resident tax sessions (8)
- FINANCEBUDDY_TAX_SESSION_TTL: tax session idle timeout, seconds (86400)
- FINANCEBUDDY_CACHE_DIR / FINANCEBUDDY_CACHE_TTL / FINANCEBUDDY_DISK_CACHE_MB:
  market-data disk cache location, freshness and size budget
- MARKET_DATA_PROVIDER: market data backend (default `mfapi`)
- ZERODHA_API_KEY / ZERODHA_API_SECRET: only for Zerodha Kite live sync

The resident-session caps bound memory, not retention: an evicted session is rehydrated
from Postgres on next access, so lowering them costs a read, never data.
Public `/auth` rate limits are in-process (20/min per IP+email) — keep `--workers 1`
or accept weaker limits across workers.

Frontend:
- VITE_API_URL: Backend API URL (required in production)
- VITE_SUPABASE_URL: Supabase URL
- VITE_SUPABASE_ANON_KEY: Public anon key

---

## Verification

```
cd backend
python -m pytest tests/test_sql_is_valid_postgres.py -v
python -m pytest tests/test_only_shared_db_opens_connections.py -v
python scripts/verify_setup.py
```

See VERIFICATION.md for complete checks. API calling / Bearer tokens: [API.md](API.md).
