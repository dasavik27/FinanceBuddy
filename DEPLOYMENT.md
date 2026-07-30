# Deployment

## The start command

```
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
```

This is in `Procfile` (Render, Railway, Heroku read it directly). Platforms that ask
for the command in a dashboard field want the same string. Python 3.13 — see
`.python-version`.

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
| `GOOGLE_CLIENT_ID` | (none) | Google OAuth Client ID for authentication. |
| `GOOGLE_CLIENT_SECRET` | (none) | Google OAuth Client Secret. |
| `GOOGLE_REDIRECT_URI` | `http://localhost:5173/auth/callback` | **Must** match the environment's frontend domain. |
| `JWT_SECRET` | (dev-secret) | Secret key to sign access tokens. **Must** be changed in prod. |

## Environments (Local vs Production)

The codebase natively supports environment separation via environment variables. You do not need to change code to deploy to production.

### 1. Local Development (`.env`)
- **Backend**: Uses a `.env` file (which is ignored by git) loaded automatically by `main.py`.
- **Frontend**: By default, `VITE_API_URL` is empty, and Vite's proxy forwards `/api` to `localhost:8000`.
- **Google OAuth**: `GOOGLE_REDIRECT_URI` defaults to `http://localhost:5173/auth/callback`. You configure this exactly as-is in the Google Cloud Console.

### 2. Production (Render / Vercel)
- **Backend (e.g. Render)**: Do NOT upload `.env`. Instead, add the variables directly in the Render dashboard:
  - `FINANCEBUDDY_ALLOWED_ORIGINS=https://your-production-frontend.vercel.app`
  - `GOOGLE_REDIRECT_URI=https://your-production-frontend.vercel.app/auth/callback`
  - `JWT_SECRET=your_secure_random_string`
- **Frontend (e.g. Vercel)**: In your Vercel project settings, set:
  - `VITE_API_URL=https://your-production-backend.onrender.com`
- **Google OAuth**: In Google Cloud Console, add `https://your-production-frontend.vercel.app/auth/callback` to the list of Authorized redirect URIs for your Client ID (or create a completely separate "Production" Client ID for better security isolation).

## Storage is ephemeral, and the app is built for that

Free tiers give no persistent disk and spin down when idle. On restart, both the
SQLite database (`backend/data/metadata.sqlite3`) and the L2 disk cache
(`backend/.cache`) are gone.

This is handled rather than worked around: a missing session returns 404 and the UI
prompts for re-upload. Treat L2 as a warm-start optimisation, not storage.

Two consequences worth knowing:

- **Attaching a persistent volume changes the security posture.** Sessions hold
  holdings, capital gains, PAN and income as plaintext JSON and SQLite rows. Today
  that is acceptable largely *because* the disk evaporates. With a real volume or
  backups, encryption-at-rest becomes a requirement, not a nice-to-have.
- **Schema drift becomes reachable.** The `mf_*` tables have no explicit DDL — their
  schema is frozen from the first upload. `storage._align_frame_to_table` migrates
  additively so a parser change no longer hard-fails uploads, but on ephemeral disk
  this was previously masked entirely by the tables being recreated each deploy.

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
