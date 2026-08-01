# Onboarding

Everything needed to run Finance Buddy locally and to deploy it, in the order it has
to happen.

Read **ARCHITECTURE.md** for how the system works and **SECURITY.md** for the threat
model. This document is only "what to add, and what to do".

---

## What you are setting up

| Piece | Runs on | Why |
|---|---|---|
| Backend API | Render (or any host reading a `Procfile`) | FastAPI, one worker |
| Frontend | Vercel | Static Vite build |
| Database | Supabase, Neon, RDS — anything Postgres 11+ | Nothing is vendor-specific but the connection string |
| Sign-in | Supabase Auth in front of Google | Any OIDC provider works; this is the configured one |

Two things are **required** and the app refuses to run without them, by design:

- **A database.** There is no file-backed fallback. SQLite was removed because it
  cannot keep user data across restarts on an ephemeral container.
- **An encryption key.** PAN, salary and holdings are encrypted before they reach the
  database. Unconfigured, the app raises rather than writing them in plaintext —
  encryption that silently no-ops is worse than none, because the deployment then
  reports itself as secure and is not.

There is also **no anonymous mode and no PAN login**. Without a working identity
provider every request is anonymous and the app is unusable — including locally. That
is why external services are set up before local development below, not after.

---

## Part 0 — Accounts and tools

| Need | For |
|---|---|
| Python 3.10+ (tested 3.13) | Backend |
| Node.js 18+ and npm | Frontend |
| PostgreSQL 11+ locally | Local development |
| Supabase account | Auth, and hosted Postgres if you want one |
| Google Cloud account | The OAuth client |
| Render account | Backend hosting |
| Vercel account | Frontend hosting |

---

## Part 1 — Supabase and Google

Do this first. Local development needs it too, and the two consoles reference each
other, so the order matters.

### 1.1 Create the Supabase project

[supabase.com/dashboard](https://supabase.com/dashboard) → **New project**. Pick the
region closest to where Render will run — cross-region adds ~90 ms to every query, and
a page issuing ten of them becomes a second of waiting.

Note two values:

- **Project URL** — `https://<ref>.supabase.co` (Settings → API)
- **Publishable/anon key** — starts `sb_publishable_` or `eyJ…`. Safe in the browser
  by design. **Never** use the `sb_secret_` / service-role key in the frontend.

### 1.2 Get Supabase's OAuth callback URL

Authentication → **Providers** → **Google**. There is a greyed-out **Callback URL**
field with a copy button. It is not editable — it is Supabase's own endpoint, and you
paste it *into Google*. Copy it; it looks like:

```
https://<ref>.supabase.co/auth/v1/callback
```

Leave this page open.

### 1.3 Create the Google OAuth client

[console.cloud.google.com](https://console.cloud.google.com) → create or pick a
project.

**First, the consent screen** (Google will not let you create a client without it):
APIs & Services → **OAuth consent screen** → External → fill in app name and support
email. Default scopes are enough. If it stays in *Testing*, add your own email under
**Test users** or you will not be able to sign in.

**Then the client:** APIs & Services → Credentials → **Create Credentials** → **OAuth
client ID** → **Web application**.

| Field | Value |
|---|---|
| **Authorized JavaScript origins** | `http://localhost:5173` and your Vercel URL |
| **Authorized redirect URIs** | The Supabase callback URL from 1.2 — **not** your own app's URL |

That last row is the one people get wrong. The redirect goes to Supabase, which then
sends the user back to your app.

Save, and copy the **Client ID** and **Client Secret**.

### 1.4 Give Google's credentials to Supabase

Back on Authentication → Providers → Google: paste the Client ID and Client Secret,
toggle **Enabled**, **Save**.

They live only here. Nothing goes into your code or `.env` — Supabase performs the
OAuth exchange server-side, so your app never handles the client secret.

### 1.5 Allow your app's redirect targets

Authentication → **URL Configuration** (a different page from Providers):

| Field | Value |
|---|---|
| **Site URL** | `http://localhost:5173` for now; your Vercel URL once deployed |
| **Redirect URLs** | `http://localhost:5173/dashboard` and `https://<your-vercel-app>/dashboard` |

The app requests a redirect to `/dashboard` after sign-in. If it is not on this
allow-list Supabase silently ignores it and falls back to Site URL, which looks like
sign-in "not working".

---

## Part 2 — Local development

### 2.1 Install dependencies

```bash
# Backend
python -m venv venv_finance
venv_finance\Scripts\activate      # Windows
source venv_finance/bin/activate   # macOS / Linux
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install
```

`SETUP_ENV.bat` (Windows) and `SETUP_ENV.sh` do the same in one step.

### 2.2 Create two databases

```sql
CREATE DATABASE financebuddy;
CREATE DATABASE financebuddy_test;
```

Two on purpose. The test suite creates and drops schemas, so it must never point at
the database holding your uploads.

### 2.3 Generate an encryption key

```bash
python -c "import base64,os;print('k1:'+base64.b64encode(os.urandom(32)).decode())"
```

Use a **different** key locally than in production. If they match, a leaked local key
reads production data.

> **Losing this key loses the data.** That is the design — the database alone is not
> enough to read it. Keep it wherever your other secrets live, and *not* beside the
> database backups.

### 2.4 Write `backend/.env`

```ini
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/financebuddy
FINANCEBUDDY_ENCRYPTION_KEYS=k1:<key from 2.3>
SUPABASE_URL=https://<ref>.supabase.co
```

`SUPABASE_URL` alone is enough for auth — the issuer, JWKS URL and audience are
derived from it.

### 2.5 Write `frontend/.env.local`

```ini
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<publishable key from 1.1>
```

Both files are gitignored. Keep it that way — they hold a database password and an
encryption key.

### 2.6 Apply migrations

```bash
cd backend && python -m migrations.migrate
```

Expect `applied 3 migration(s)`. Idempotent, advisory-locked, and safe to re-run;
`--status` shows what would happen without changing anything.

### 2.7 Run it

```bash
npm run dev                # both servers, from the repo root
```

Or separately:

```bash
cd backend && python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

- App: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### 2.8 Run the tests

```bash
cd backend
TEST_DATABASE_URL=postgresql://postgres:<password>@localhost:5432/financebuddy_test \
  python -m pytest tests/ -q
```

Expect **362 passed**. Without `TEST_DATABASE_URL` the database-backed tests skip
instead of failing — 264 pass, 92 skip. Useful for a quick check; not a full pass.

---

## Part 3 — Production

### 3.1 Get the production database URL

Supabase → Settings → Database → Connection string → **URI**.

**Use the transaction pooler, port 6543** — the one whose host contains
`pooler.supabase.com`:

```
postgresql://postgres.<ref>:<password>@aws-1-<region>.pooler.supabase.com:6543/postgres
```

Not `db.<ref>.supabase.co:5432`. That direct host is IPv6-only on newer projects and
fails from IPv4-only networks. The pool is already configured for a transaction-mode
pooler (prepared statements disabled), which is required — otherwise you get
"prepared statement does not exist" only under concurrency, i.e. only in production.

### 3.2 Render — backend

New **Web Service** from the repo. It reads `Procfile`, so the build and start
commands come from there:

```
release: cd backend && python -m migrations.migrate
web:     cd backend && python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
```

The `release` command applies migrations before the new version takes traffic.

**Region:** the same one as Supabase. This is the single largest latency lever and it
is free.

**Environment variables — four:**

| Variable | Value |
|---|---|
| `DATABASE_URL` | The pooler URI from 3.1 |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `FINANCEBUDDY_ENCRYPTION_KEYS` | `k1:<a NEW key, not your local one>` |
| `FINANCEBUDDY_ALLOWED_ORIGINS` | Your Vercel URL, e.g. `https://financebuddy.vercel.app` |

`FINANCEBUDDY_ALLOWED_ORIGINS` must be set or the browser blocks every request on
CORS. Comma-separated for more than one.

**Do not raise `--workers` above 1.** ARCHITECTURE.md explains what breaks; the short
version is that the in-process caches stop being shared and 512 MB stops being enough.

### 3.3 Vercel — frontend

Import the repo, root directory `frontend`. Vite is detected automatically;
`frontend/vercel.json` handles SPA routing.

**Environment variables — three:**

| Variable | Value |
|---|---|
| `VITE_API_URL` | Your Render URL, e.g. `https://financebuddy-api.onrender.com` |
| `VITE_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | The publishable key — never the secret one |

These are compile-time. Changing one needs a redeploy, not just a restart.

### 3.4 Point the two consoles at production

Now that the URLs exist, go back and add them:

- **Google Console** → Authorized JavaScript origins → add your Vercel URL
- **Supabase** → URL Configuration → Site URL = Vercel URL; Redirect URLs → add
  `https://<your-vercel-app>/dashboard`

Skipping this is the most common reason sign-in works locally and not in production.

---

## Part 4 — Verify

In order, because each step depends on the previous one working:

1. **Migrations ran.** Render's release log shows `applied 3 migration(s)`. On a
   redeploy, `nothing to do`.
2. **API is up.** `GET /health` → `{"status":"ok"}`.
3. **Database is connected.** Render's startup log shows `[DB] pool ready`. If it says
   `database pool unavailable`, `DATABASE_URL` is wrong or the region blocks it.
4. **Encryption is configured.** Startup log shows `[CRYPTO] keyring loaded`. If it
   raises on the first write, the key is missing or malformed.
5. **Sign-in works.** Open the app → Continue with Google → you land on `/dashboard`.
6. **Identity resolves.** `GET /auth/me` returns a `user_id`. A 401 means the token is
   not being verified — check `SUPABASE_URL` on Render.
7. **An upload round-trips.** Upload a CAS, then reload the page. The portfolio should
   still be there — that is the whole point of the migration.
8. **Data is actually encrypted.** In Supabase's SQL editor:
   ```sql
   SELECT session_id, metrics FROM sessions LIMIT 1;
   ```
   `metrics` should be unreadable bytes beginning `\x46424531` (`FBE1`). If you can
   read numbers, encryption is not on.

---

## Every variable, in one place

### Backend

| Variable | Required | Local | Production |
|---|---|---|---|
| `DATABASE_URL` | **yes** | `postgresql://postgres:pw@localhost:5432/financebuddy` | Supabase pooler URI, port 6543 |
| `FINANCEBUDDY_ENCRYPTION_KEYS` | **yes** | `k1:<local key>` | `k1:<different key>` |
| `SUPABASE_URL` | **yes** | Same project both | Same |
| `FINANCEBUDDY_ALLOWED_ORIGINS` | production | defaults to localhost:5173 | Vercel URL |
| `TEST_DATABASE_URL` | tests only | `…/financebuddy_test` | never set |
| `FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY` | only with >1 key | — | during rotation |
| `AUTH_ISSUER` / `AUTH_JWKS_URL` / `AUTH_AUDIENCE` | no | — | only for a non-Supabase provider |
| `FINANCEBUDDY_DB_POOL_MAX` | no (6) | — | keep ≤ `SYNC_CONCURRENCY` |
| `FINANCEBUDDY_SYNC_CONCURRENCY` | no (8) | — | raise only with more CPU |
| `FINANCEBUDDY_SLOW_REQUEST_MS` | no (1500) | — | requests slower than this get logged |
| `FINANCEBUDDY_MAX_RESIDENT_SESSIONS` | no (3) | — | memory cache size |
| `FINANCEBUDDY_MAX_TAX_SESSIONS` | no (8) | — | memory cache size |
| `ZERODHA_API_KEY` | no | — | only for Kite live sync |
| `ZERODHA_API_SECRET` | no | — | only for Kite live sync |

### Frontend

| Variable | Required | Notes |
|---|---|---|
| `VITE_API_URL` | **yes** | Backend origin. Falls back to `/api`, which only works behind a proxy |
| `VITE_SUPABASE_URL` | **yes** | |
| `VITE_SUPABASE_ANON_KEY` | **yes** | Publishable key only |

### Set in a console, never in a file

| Value | Where |
|---|---|
| Google Client ID + Secret | Supabase → Auth → Providers → Google |
| Supabase database password | Inside `DATABASE_URL` |

---

## When it goes wrong

| Symptom | Cause |
|---|---|
| `couldn't get a connection after 10.00 sec` | Database unreachable. Wrong `DATABASE_URL`, or a firewall blocking the Postgres protocol — corporate networks commonly do, and it looks like a timeout rather than a refusal. |
| `FINANCEBUDDY_ENCRYPTION_KEYS is not set` | Working as intended. See 2.3. |
| `function gen_random_uuid() does not exist` | Postgres < 13 without pgcrypto. Migration 0001 creates it — you have not run migrations. |
| `prepared statement does not exist`, only under load | Using the direct connection, not the transaction pooler. See 3.1. |
| Sign-in redirects to `/` instead of `/dashboard` | `/dashboard` missing from Supabase's Redirect URLs. See 1.5. |
| `redirect_uri_mismatch` from Google | Google's Authorized redirect URI is not Supabase's callback. See 1.3. |
| Every request fails CORS | `FINANCEBUDDY_ALLOWED_ORIGINS` unset or wrong on Render. |
| `GET /auth/me` → 401 while signed in | Backend cannot verify the token — `SUPABASE_URL` wrong or unset. |
| Dashboard empty after a working upload | Check the log for `cannot decrypt` — usually a changed or missing encryption key. |
| Tests skip instead of running | `TEST_DATABASE_URL` unset. |
| First request after idle takes ~30 s | Render free tier spun the container down. Not a bug. |

---

## Day-two operations

### Adding a migration

Create `backend/migrations/000N_description.sql`. Never edit an applied one — the
runner checksums them and refuses to proceed if one changed, because an edited
migration means environments have silently diverged.

### Rotating the encryption key

Additive, no downtime:

1. Generate a new key.
2. Set `FINANCEBUDDY_ENCRYPTION_KEYS=k1:<old>,k2:<new>` and
   `FINANCEBUDDY_ENCRYPTION_ACTIVE_KEY=k2`.
3. Deploy. New writes use `k2`; rows written under `k1` still read, and re-encrypt as
   they are next written.
4. Only remove `k1` once nothing needs it. A row whose key is gone reports a
   decryption error rather than returning empty — loud, but still data loss.

### Rotating the database password

Supabase → Settings → Database → Reset password, then update `DATABASE_URL` on Render
and in your local `.env`. Do this if a connection string was ever pasted somewhere it
should not have been.

### Backups

Supabase takes them on paid plans. Two things to get right:

- **Store the encryption key separately from the backups.** A backup alongside its key
  is a backup with the lock and the key in the same box.
- **Test a restore** before you need one, including that the key still decrypts it.

### Storage budget

Supabase's free tier is 500 MB. A 20k-row ledger compresses to ~0.8 MB, so roughly
600 snapshots. Nothing expires on a timer — retention belongs to the user
(`DELETE /accounts/me`), so this grows until they delete or you upgrade.

### Where to look when something is slow

- `GET /health/cache` (authenticated) — live hit/miss/eviction counters per tier.
  Answers "is the cache working" rather than assuming.
- Requests over `FINANCEBUDDY_SLOW_REQUEST_MS` are logged with their path.
- `Server-Timing` header on every response carries handler time.
