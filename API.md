# Finance Buddy — API guide

**Canonical API reference for callers.** Request/response schemas: interactive OpenAPI at
`GET /docs` (local: http://localhost:8000/docs).

Auth *design* (allowlist, status/role, middleware) lives in
[ARCHITECTURE.md](ARCHITECTURE.md) → *Authentication & access control*.
Setup lives in [ONBOARDING.md](ONBOARDING.md).

---

## Base URL

| Environment | Base URL |
|---|---|
| Local | `http://localhost:8000` |
| Production | Your Render URL (same value as frontend `VITE_API_URL`) |

Do **not** use the Vercel origin or `/api` as the API base in production — the
browser must call the backend origin directly.

---

## How to pass the token

Almost every route expects:

```http
Authorization: Bearer <supabase_access_token>
```

### Which token

Use the Supabase session **`access_token`** (JWT), not a refresh token and not a
custom API key / service role key.

| Client | How to get it |
|---|---|
| Web app | `authClient.getAccessToken()` → Axios interceptor sets the header |
| curl / Postman | Mint via Supabase password grant (below), or copy from a signed-in browser |
| Swagger (`/docs`) | **Authorize** → paste the JWT (no `Bearer ` prefix) |

The backend verifies the JWT against Supabase JWKS (`shared/oidc.py`; asymmetric
ES256/RS256), then resolves or creates the app account via `users.resolve()`.

The account email must be **allowlisted** (approved invite / access request, or
admin email). A valid JWT for an unknown email returns `403 not_authorized`.

---

## How to generate a token (API-only testing)

There is no FinanceBuddy “login” endpoint that returns a JWT. Tokens come from
**Supabase Auth**. Use an invitee account that already has a password.

### 1) Password grant (recommended for curl / Swagger)

Use your Supabase project URL and the **anon / publishable** key
(`VITE_SUPABASE_ANON_KEY` — never the service role key in the browser or docs examples):

```bash
# Windows PowerShell: $env:SUPABASE_URL, $env:SUPABASE_ANON_KEY
export SUPABASE_URL="https://YOUR_REF.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key"

curl -s "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}'
```

Response includes:

```json
{
  "access_token": "eyJhbGciOi…",
  "refresh_token": "…",
  "expires_in": 3600,
  "token_type": "bearer"
}
```

Copy **`access_token`** only:

```bash
export ACCESS_TOKEN="eyJhbGciOi…"   # paste access_token value
```

Tokens expire (`expires_in`, often ~1 hour). Mint a new one when calls start
returning `401`.

### 2) From a signed-in browser session

1. Sign in to the web app with the same allowlisted user.
2. DevTools → Application → Local Storage → key like `sb-<ref>-auth-token`.
3. Open the JSON and copy `access_token`.

Or in the browser console on the app origin (if the client is loaded):

```js
const raw = localStorage.getItem(
  Object.keys(localStorage).find((k) => k.includes('-auth-token'))
)
JSON.parse(raw).access_token
```

### 3) Use the token in Swagger

1. Open `http://localhost:8000/docs` (or your Render `/docs`).
2. Click **Authorize**.
3. Paste the **access_token** JWT only (Swagger adds `Bearer `).
4. **Try it out** on e.g. `GET /auth/me`.

### 4) Use the token with curl

```bash
curl -s http://localhost:8000/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Example response:

```json
{
  "user_id": "…",
  "email": "you@example.com",
  "pan": "ABCDE1234F",
  "display_name": null,
  "status": "active",
  "role": "admin"
}
```

Domain example:

```bash
curl -s "http://localhost:8000/mutual-funds/overview/$SESSION_ID/summary" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Public routes (no token)

These work **without** `Authorization`:

- `POST /auth/access-status`
- `POST /auth/request-access`
- `GET /health`

### Common status codes

| Code | Meaning |
|---|---|
| `401` | Missing/invalid JWT, or not signed in |
| `403` | Valid JWT but not allowlisted (`not_authorized`), or `pending` / `suspended`, or not admin |
| `404` | Missing resource **or** not owned (ownership fails closed as 404) |
| `429` | Public auth rate limit exceeded |

---

## Auth API (`/auth`) — full catalog

This table is the **only** place endpoints are listed in full. Other docs link here.

| Access | Method | Path | Purpose |
|---|---|---|---|
| Public | `POST` | `/auth/access-status` | Lookup access-request status by email (landing messaging). Rate limit: **20/min** per **IP+email** key → `429` (in-process; keep `--workers 1`) |
| Public | `POST` | `/auth/request-access` | Submit early-access form. Same rate limit as above |
| Signed-in | `GET` | `/auth/me` | Current `user_id`, `email`, PAN, `display_name`, `status`, `role` |
| Signed-in | `POST` | `/auth/logout` | Evict resident in-memory sessions. Frontend **awaits** this before Supabase `signOut` |
| Signed-in, **active** | `PUT` | `/auth/profile` | Update profile fields (`{"display_name":"…"}`; empty string clears). Password is client-side via Supabase |
| Signed-in, **active** | `PUT` | `/auth/profile/pan` | Attach/update PAN (`{"pan":"ABCDE1234F"}`). Blocked when pending/suspended. Idempotent if unchanged |
| Admin | `GET` | `/auth/access-requests` | List access requests |
| Admin | `POST` | `/auth/access-requests/{id}/approve` | Send Supabase **invite** email, then mark approved. Body: `{"method":"invite"}`. `method=create` is rejected |
| Admin | `POST` | `/auth/access-requests/{id}/reject` | Reject and delete the request row |
| Admin | `DELETE` | `/auth/access-requests/{id}` | Same as reject |
| Admin | `POST` | `/auth/invites` | Direct invite (allowlist + invite email). Invite-only; no admin-set password |
| Admin | `POST` | `/auth/users/suspend` | Suspend app account by email (+ best-effort Supabase ban) |
| Admin | `GET` | `/auth/users` | List app accounts |
| Admin | `PATCH` | `/auth/users/{user_id}` | Update `status` and/or `role` |
| Admin | `DELETE` | `/auth/users/{user_id}` | Permanently delete app user + cascaded data (+ best-effort Supabase Auth delete) |

**Admin** means `users.role = admin` or email on `FINANCEBUDDY_ADMIN_EMAILS`.
Admin routes return `403` if neither applies.

**Approve / invite:** the access request is marked `approved` only after the
Supabase invite succeeds (or the Auth user already exists). Failures return `502`
and leave the request pending / not allowlisted.

---

## Infrastructure (brief)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness |
| `GET` | `/accounts/me/export` | Signed-in | Export account data |
| `DELETE` | `/accounts/me` | Signed-in | Purge account data |
| `GET` | `/history/` | Signed-in | Upload history (`X-Upload-Type` header) |
| `DELETE` | `/history/{id}` | Signed-in | Delete one history row |

`/market/*` — market data helpers (see OpenAPI).

---

## Domain APIs

Prefixes only — full contracts are in OpenAPI `/docs`:

| Domain | Prefix |
|---|---|
| Budget | `/budget/*` |
| Mutual Funds | `/mutual-funds/*` |
| Tax Expert | `/tax-expert/*` |
| Equity | `/equity/*` |

Budget route overview is also summarized in ARCHITECTURE.md → *Budget Domain API
Reference* (design notes); OpenAPI remains authoritative for schemas.

---

## Frontend wiring (reference)

1. User signs in via Supabase (`authClient`).
2. Every Axios call gets `Authorization: Bearer <access_token>` from the interceptor.
3. First authenticated request runs `users.resolve()` on the backend.
4. `GET /auth/me` drives pending / suspended / PAN / display name / admin UI gates.

There is no PAN-based API authentication.

### Password vs PAN (account setup & profile)

| Concern | How it works | Notes |
|---|---|---|
| **Password** | Supabase client only — `supabase.auth.updateUser({ password })` via `authClient.updatePassword` | **No backend `/auth` password endpoint.** Used after invite/recovery links and on **Profile** (`/profile`). Min 8 chars. |
| **Display name** | `PUT /auth/profile` with Bearer token | Optional; shown on the topbar badge. Empty string clears. |
| **PAN** | `PUT /auth/profile/pan` with Bearer token | Stored encrypted in `profiles`. Required for CAS unlock / AIS match. Middleware allows this only when `status=active` (not pending/suspended). Edited on **Profile** (`/profile`) after onboarding — there is no separate PAN dialog in the badge menu. |

First-time setup (`AccountSetupPrompt`) is **one panel**: password only, PAN only, or both when the account is active and both are still missing. Later edits use the Profile page (badge → **Profile**). Data export / delete stay on `/accounts` (Data vault).
