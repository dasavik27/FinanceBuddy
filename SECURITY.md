# Security & privacy posture

This file records decisions, including the ones that are still open. The point is
that a reader can tell the difference between "handled" and "accepted for now" —
several things below are the latter, and writing them down is what stops them being
mistaken for done.

## Authentication

One credential: `Authorization: Bearer <OIDC id token>`, verified against the
provider's JWKS in `shared/oidc.py`. There is no PAN-based sign-in and no PAN header
accepted anywhere — `POST /auth/login`, `users.resolve_legacy_pan` and the
middleware's PAN branch were removed rather than deprecated, since there is no
existing session or stored login to keep working.

Verification: signature against a cached JWKS, pinned asymmetric algorithms, and
required `exp` / `iss` / `aud`. Each of those is a live attack if omitted, and each
has a test (`tests/test_oidc_verifier.py`). Provider-agnostic — a JWKS URL, an issuer
and an audience — so Google, Supabase, Auth0 and Cognito are configuration, not code.

An account with no token cannot reach anything: every route below the middleware
either 401s on an anonymous caller or treats the request as unowned data with nobody
to protect (`identity.owns_record`).

### PAN is no longer identity

Ownership is `users.id`, a uuid this application issues. PAN moved to `profiles.pan`
— still the CAS PDF password default and the AIS matching key, set once by the user
after signing in via `PUT /auth/profile/pan` — but it decides nothing about access.

The consequence worth stating plainly: **two accounts may hold the same PAN and
cannot see each other's data.** `test_pan_is_not_identity` pins it.

| | Status |
|---|---|
| One user reading another's session by holding a `session_id` | Closed |
| `/accounts/summary` enumerating every user on the deployment | Closed |
| Purging another user's data | Closed — `DELETE /accounts/me` takes no target |
| A caller who knows a PAN impersonating its owner | Closed — there is no PAN credential to present |

## Storage is durable, and that is the current open item

User data now persists in Postgres. This is a deliberate change and it moved risk
rather than removing it: sessions hold holdings, capital gains, income and PAN, and
they no longer evaporate when the container restarts.

| | Status |
|---|---|
| Retention is user-controlled, not a timer | Closed — the 24h sweep is gone; `DELETE /accounts/me` and `DELETE /history/{id}` |
| Logout destroying stored history | Closed — logout evicts memory only |
| Access / portability (DPDP) | Closed — `GET /accounts/me/export` |
| Erasure (DPDP) | Closed — one `DELETE`, cascading to every child table |
| RLS as a backstop | Closed — enabled with no permissive policy (migration 0002) |
| **Encryption at rest for PAN and income columns** | **Open** |
| **Operational: backups, and who can read them** | **Open** |

The last two are the real remaining exposure. Volume-level encryption is whatever the
host provides; it does not protect against a leaked connection string, and neither
does RLS, because the application connects as the table owner. Column-level
encryption (pgcrypto, or application-side envelope encryption) is the honest fix and
has not been done.

Handling Indian financial data makes the DPDP Act 2023 applicable. Access, erasure
and portability are implemented above; consent capture and breach notification are
process, not code, and are not addressed here.

### Why enforcement lives in the data layer

Ownership is checked inside `sessions.get_session()` and
`tax_sessions.get_tax_session()`, not on individual routes. A `Depends()` on each of
~26 routes is one forgotten decorator away from a hole; there is no way to reach a
portfolio without going through those two functions.

`identity.owns_record()` distinguishes three states, and the distinction matters:

- **not in a request** — an in-process caller (GC daemon, migration, test suite).
  Trusted, because it did not arrive over HTTP.
- **in a request, no valid PAN** — anonymous HTTP caller. Denied any owned record.
- **in a request with a PAN** — allowed on exact match only.

The first rule is safe *only* because `IdentityMiddleware` wraps every HTTP request,
so no request can observe that state. `tests/test_authorization.py` asserts the
middleware is installed, so removing it fails the suite rather than silently opening
every route.

Denials return **404, not 403**. A 403 confirms the record exists, which is the one
piece of information an id-guessing caller wants.

## Retention

| Data | Lives | Enforced by |
|---|---|---|
| Uploaded PDF (CAS / AIS / ITR) | Never retained | Parser deletes its temp file in a `finally` |
| Mutual-fund session in memory | 4 h idle, resident cap 3 | `sessions.SESSION_TTL_HOURS` |
| Tax session in memory | 24 h idle, LRU cap 8 | `tax_sessions._evict_locked` |
| Everything stored | **Until the user deletes it** | `DELETE /accounts/me`, `DELETE /history/{id}`, `DELETE /tax-expert/tax-history/{id}` |

The in-memory bounds are cache sizing, not retention: an evicted session is rehydrated
from the database on next access. Nothing expires on a timer.

That is a change. Rows used to be swept after 24 hours, which was reasonable when the
filesystem was wiped on every deploy — the sweep bounded a table that could not
outlive a restart anyway. Against durable storage the same sweep is a scheduled
deletion of the user's own statements, so it is gone and retention is theirs.

`ARCHITECTURE.md` describes the product as having "zero-persistence privacy". That was
never accurate and is now clearly wrong. The accurate claim is: *the uploaded document
is never retained; derived data persists until the user deletes it.*

## Data at rest is not encrypted

`tax_payloads.data` is jsonb containing salary, capital gains, deductions and PAN.
`session_payloads` holds the portfolio as compressed JSON — compressed, which is not
encrypted and should not be mistaken for it.

This used to be recorded as acceptable *because the deployment disk was ephemeral*.
**That premise is gone.** Data now persists indefinitely, so this is a live data-at-rest
finding rather than a deferred one.

Volume-level encryption is whatever the host provides and does not protect against a
leaked connection string. Row-level security (migration 0002) does not either — the
application connects as the table owner. The honest fix is column-level encryption of
the sensitive fields, either with pgcrypto or application-side with a key from the
environment. Not done.

## Logging

PAN is masked to its last four characters (`identity.mask_pan`) wherever it is
logged. Hosted platforms retain stdout indefinitely, so an unmasked PAN in a log line
is durable personal data sitting outside the 24-hour retention everything else
honours.

Do not log the AIS `personal` block, parsed ITR contents, or holdings. Log keys or
counts instead of values.

## Response caching

Every response **from a route** gets `Cache-Control: no-store` unless the route sets
something else (`DefaultCacheControlMiddleware`). This is deliberately the opposite
default from HTTP's: absent a header, RFC 9111 §4.2.2 lets a shared cache store a
200 GET heuristically, and almost every route here returns per-user financial data.

Two documented gaps, both bodiless and therefore not leaks: CORS preflight (`OPTIONS`)
responses are generated outside this middleware, as are `ServerErrorMiddleware`'s
fallback 500s.

`public` is reserved for genuinely user-independent market data. The policy table in
`shared/services/cache.py` fails closed for unknown types, and
`tests/test_cache_headers_routes.py` asserts on the headers routes actually emit —
because the one leak found in review was not a bad policy but a router labelling a
user-derived payload with a market-data type.

## Known-open items

1. **Data at rest is not encrypted** (above). The largest remaining item, because
   storage became durable. Gates using this with real data.
2. **`POST /market/config` is still unauthenticated.** It can no longer disable
   caching outright — the TTL is floored at 1 minute — but any caller can still lower
   it and increase upstream load. It should require a signed-in caller.
3. **`/health/cache` and `/tax-expert/tax/cache-stats` are unauthenticated.** They leak
   no user data — counters only — but do reveal activity volume.

Closed during the pre-production pass, listed so the history is visible: the
`"empty_ledger"` shared dedup hash, unscoped `/accounts/summary`, unauthenticated
account purge, `Cache-Control: public` on portfolio data, the unlocked tax session
store, destructive tax-session eviction, unpurged `users` rows, unmasked PAN logging,
the `auth.py` first-login migration that claimed orphaned sessions for whoever logged
in first after a restart, the body-supplied PAN on `POST /auth/logout` that let anyone
destroy a named user's tax sessions, PAN itself being the owner column, and — once
Google sign-in was in place — the `X-User-PAN` header and `POST /auth/login` entirely.
