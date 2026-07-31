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

Ownership is `users.id`, a uuid this application issues. PAN moved to `profiles.pan_encrypted`
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

## Storage is durable, and what that changed

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
| Encryption at rest for PAN, income, holdings and portfolio value | Closed — see below |
| **Operational: backups, and who holds the key** | **Open** |

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
- **in a request, no verified token** — anonymous HTTP caller. Denied any owned record.
- **in a request as a user** — allowed on exact `user_id` match only.

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

`ARCHITECTURE.md` used to describe the product as having "zero-persistence privacy"
and a "Zero-Database Architecture". Neither was ever accurate — SQLite was already
writing to disk — and both are now the opposite of true. Corrected there. The accurate
claim is: *the uploaded document is never retained; derived data persists until the
user deletes it.*

## Data at rest

Encrypted by the application before it reaches the database — AES-256-GCM in
`shared/crypto.py`, keyed from `FINANCEBUDDY_ENCRYPTION_KEYS`. Required, with no
plaintext fallback: unconfigured, the app raises rather than writing this data in the
clear, because encryption that silently no-ops is worse than none — the deployment
reports itself as encrypted and is not.

| Column | Holds |
|---|---|
| `profiles.pan_encrypted` | PAN |
| `sessions.metrics` | net worth, amount invested, fund count, tax summary incl. gross salary |
| `session_payloads.holdings/transactions/sips` | the full CAS portfolio and ledger |
| `tax_payloads.data` | the parsed AIS: salary, capital gains, deductions |

Deliberately left plaintext, because each is either non-reversible or needed for
queries the encryption would break: `sessions.data_hash` (a SHA-256 salted with
user_id, needed for dedup equality lookups), `created_at` and `upload_type` (every
WHERE and ORDER BY), `session_payloads.meta` (column names and datetime units —
schema, not data), and `identities.email` (already known to the identity provider).

Two properties worth stating because they are not automatic:

- **Randomised.** A fresh nonce per write, so equal plaintexts give different
  ciphertexts. A deterministic scheme would leak equality — an observer could tell
  which accounts share a PAN, or which sessions hold an identical portfolio, without
  decrypting anything.
- **Bound to its row.** Every ciphertext is authenticated against its `session_id` or
  `user_id` as GCM associated data. This closes an attack encryption alone does not:
  someone with write access but no key could otherwise copy one user's encrypted
  holdings into another user's row, and the application would decrypt and serve it.
  Covered by `test_a_payload_moved_to_another_session_will_not_decrypt`.

What this does **not** cover: an attacker who has compromised the running application
has the key by definition. It protects a leaked connection string, a stolen backup,
or read access at the hosting provider — precisely the cases volume encryption and
RLS leave open, because the database decrypts for anyone who authenticates and this
application connects as the table owner.

The remaining operational item is key custody: a backup taken alongside the key is a
backup with the lock and the key in the same box. See DEPLOYMENT.md.

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

1. **Key custody and backups.** The encryption key must not live where the database
   backups do, and losing it loses the data. This is process, not code.
2. **Consent capture and breach notification** (DPDP). Access, erasure and
   portability are implemented; these two are not, and are also process.

Closed during the pre-production pass, listed so the history is visible: the
`"empty_ledger"` shared dedup hash, unscoped `/accounts/summary`, unauthenticated
account purge, `Cache-Control: public` on portfolio data, the unlocked tax session
store, destructive tax-session eviction, unpurged `users` rows, unmasked PAN logging,
the `auth.py` first-login migration that claimed orphaned sessions for whoever logged
in first after a restart, the body-supplied PAN on `POST /auth/logout` that let anyone
destroy a named user's tax sessions, PAN itself being the owner column, the
`X-User-PAN` header and `POST /auth/login` entirely once Google sign-in was in place,
unauthenticated `POST /market/config` and cache-stats endpoints, and plaintext
storage of PAN, salary, holdings and portfolio value.
