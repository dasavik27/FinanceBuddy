# Deployment

## The start command

```
release: cd backend && python -m migrations.migrate
web:     cd backend && python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
```

Both are in `Procfile` (Render, Railway, Heroku read it directly). Platforms that ask
for the commands in dashboard fields want the same strings. Python 3.13 — see
`.python-version`.

The release command applies pending migrations before the new version serves
traffic. It is safe to run concurrently and repeatedly: it takes an advisory lock,
applies each file in its own transaction, and skips anything already recorded in
`schema_migrations`.

## Database

PostgreSQL, via psycopg 3. SQLite is gone — the app now keeps user data across
restarts, and a file on an ephemeral container cannot.

Nothing here is tied to a hosting provider. Supabase, Neon, RDS, Railway and a local
server are the same code behind one connection string; no vendor SDK is imported and
no table references a provider-managed one.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | **yes** | Postgres DSN. |
| `TEST_DATABASE_URL` | for tests | A *separate* database. The suite creates and drops schemas, so never point this at production. Unset, the database-backed tests skip. |
| `FINANCEBUDDY_DB_POOL_MIN` | no (1) | Idle connections held. |
| `FINANCEBUDDY_DB_POOL_MAX` | no (6) | Ceiling. Keep at or below `FINANCEBUDDY_SYNC_CONCURRENCY` — that cap is the real limit on concurrent handlers, so extra connections only consume the server's allowance. |
| `FINANCEBUDDY_DB_STATEMENT_TIMEOUT_MS` | no (15000) | A query past this is not going to help the request that started it. |

**Use the transaction pooler, not the direct connection.** On Supabase that is port
`6543` (`...pooler.supabase.com`), not `5432` on `db.<ref>.supabase.co` — the direct
host is IPv6-only on newer projects, which fails from IPv4-only networks. The pool
disables prepared statements (`prepare_threshold=None`) because a transaction-mode
pooler multiplexes one backend across clients per transaction and a prepared
statement does not survive that; the failure only appears under concurrency.

**Put the database in the same region as the app.** This is the single largest
latency lever and it is free. Cross-region is ~90 ms per query; a page issuing ten
becomes a second of waiting.

## Authentication

OIDC ID tokens, verified locally against the provider's JWKS. There is no PAN-based
sign-in and no fallback header — **without these set, every request is anonymous and
the app is unusable**, by design: there is nothing to fall back to.

| Variable | Required | Purpose |
|---|---|---|
| `SUPABASE_URL` | **yes** | Your Supabase project URL. Also derives `AUTH_ISSUER` and `AUTH_JWKS_URL` (as `<url>/auth/v1` and `<url>/auth/v1/.well-known/jwks.json`) and defaults `AUTH_AUDIENCE` to `authenticated`, so this one variable is enough for a Supabase-fronted deployment. |
| `AUTH_JWKS_URL` | no | Override, for a non-Supabase OIDC provider. |
| `AUTH_ISSUER` | no | Override. Expected `iss` claim. |
| `AUTH_AUDIENCE` | no | Override. Expected `aud` claim. |

Provider-agnostic by construction: swapping Google/Supabase for Auth0 or Cognito is
three environment variables, not a code change — see `shared/oidc.py`.

## `--workers 1` is not a default, it is a requirement

The caching architecture assumes exactly one worker, and several parts of it are
incorrect without that. Before raising it, understand what breaks:

- **In-process caches stop being shared caches.** `ProcessCache` (L1) lives in
  process memory. With N workers you get N independent copies: N× the resident
  memory, and a cache hit rate that falls because each worker has to warm its own.
- **Single-flight stops working across workers.** `get_or_compute` collapses N
  concurrent misses into one computation *within* a process. With 4 workers, 4
  simultaneous requests for the same uncached AMFI bundle become 4 downloads again —
  the exact behaviour the caching work removed.
- **512 MB is a hard ceiling.** Baseline is roughly 50 MB per process before any
  portfolio is loaded, and the L1 budgets (32 MB market + 24 MB derived) are
  per-process. Four workers exceeds the box.
- **The resident-session caps are per-process.** `MAX_RESIDENT_SESSIONS=3` and
  `MAX_TAX_SESSIONS=8` become 12 and 32 in aggregate.

If you genuinely need more concurrency, the correct order is: move L1 to a shared
store (Redis) first, re-verify the memory budget, *then* add workers. Adding workers
alone trades a latency problem for an OOM.

There is no Redis today because with one worker it would cost resident memory and
buy nothing.

## Concurrency inside the single worker

51 of 54 endpoints are sync `def`, which FastAPI runs in anyio's worker threadpool.
That pool defaults to **40**, which on ~0.1 shared vCPU means up to 40 GIL-bound
pandas handlers thrashing against each other, each holding its own intermediate
DataFrames.

`main.py` caps it at 8 (`FINANCEBUDDY_SYNC_CONCURRENCY`). Excess requests queue
instead of thrash. Raise it only alongside more CPU.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Set by the platform. |
| `FINANCEBUDDY_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | **Must** be set to the deployed frontend origin. Comma-separated. |
| `FINANCEBUDDY_SYNC_CONCURRENCY` | `8` | anyio threadpool cap. See above. |
| `FINANCEBUDDY_SLOW_REQUEST_MS` | `1500` | Requests slower than this are logged with their path. |
| `FINANCEBUDDY_MAX_RESIDENT_SESSIONS` | `3` | Resident mutual-fund portfolios. Overflow rehydrates from SQLite. |
| `FINANCEBUDDY_MAX_TAX_SESSIONS` | `8` | Resident tax sessions. Overflow rehydrates from SQLite. |
| `FINANCEBUDDY_TAX_SESSION_TTL` | `86400` | Tax session idle TTL, seconds. |

## Storage is durable now, and that changes the threat model

User data lives in Postgres and survives restarts. That was the point of the
migration, and it converts a previously-accepted risk into an open one.

Sessions hold holdings, capital gains, PAN and income. That was tolerable when the
disk evaporated on every deploy; it is not now. **Encryption at rest, a retention
policy and a user-facing export are requirements rather than nice-to-haves** —
`SECURITY.md` is the tracking place, and its threat model still needs rewriting to
match: it is written as though the filesystem were ephemeral.

What did *not* survive the migration, deliberately:

- **The 24-hour sweep is gone.** It deleted every session older than a day, which
  made sense when nothing survived a deploy anyway. Deleting a user's statements on
  a timer is now data loss, not housekeeping. Retention belongs to the user:
  `DELETE /accounts/me` removes the account and everything under it (one statement —
  every child table cascades), `DELETE /history/{id}` removes one statement.
- **Logout no longer deletes anything.** It evicts the caller's sessions from memory;
  the stored copies stay and are rehydrated on next access.
- **Schema drift is no longer possible.** The `mf_*` tables had no DDL and absorbed
  parser changes via runtime `ALTER TABLE` using identifiers taken from the uploaded
  PDF. They are replaced by one compressed payload row per session, which has no
  schema to drift from.

The L2 disk cache (`backend/.cache`) is still ephemeral and still fine — it holds
regenerable market data, and putting it in Postgres would spend the connection and
IO budget on something a refetch replaces for free.

## Storage budget

A 20k-row ledger is ~3 MB as JSON and ~0.8 MB compressed (zlib level 1, applied in
the application rather than left to TOAST — TOAST decompresses server-side, so doing
it here saves the wire bytes too). On Supabase's 500 MB free tier that is roughly 600
snapshots before it matters.

## Health checks

- `GET /health` — liveness. Cheap, no I/O.
- `GET /health/cache` — live L1 hit/miss/eviction counters per tier. Use it to answer
  "is the cache actually working" after a deploy rather than assuming.

Point the platform's health check at `/health`. Note that a blocking upload used to
be able to starve it; the endpoints that caused that are now sync `def` and run in
the threadpool.

## Frontend

Static build, deployed separately (Vercel). `frontend/vercel.json` handles SPA
routing. Set `VITE_API_URL` to the backend origin at build time; it falls back to
`/api`, which only works when something is proxying.

The checked-in `frontend/dist/` is a stale artifact — its `index.html` references an
asset bundle that is not in the repo. It is not used by any build and should be
deleted.
