# Security & privacy posture

This file records decisions, including the ones that are still open. The point is
that a reader can tell the difference between "handled" and "accepted for now" —
several things below are the latter, and writing them down is what stops them being
mistaken for done.

## Authentication: PAN is an identifier, not a credential

`POST /auth/login` accepts any syntactically valid PAN and returns success. The
frontend then sends it as `X-User-PAN` on every request, and the backend treats it as
the caller's identity (`shared/identity.py`).

**PAN is printed on documents. It is not a secret.** Anyone who knows a user's PAN can
present it and read that user's data. This is the largest open item in this file.

What the identity layer does buy, and what it does not:

| | Status |
|---|---|
| One user reading another's session by holding a `session_id` | Closed |
| `/accounts/summary` enumerating every PAN on the deployment | Closed |
| Purging another user's data via `DELETE /accounts/{pan}` | Closed |
| A caller who knows a PAN impersonating its owner | **Open** |
| Brute-forcing the PAN space (10 chars, structured) | **Open** |

Closing the open rows needs a real credential — a signed token issued after
authenticating something the user can keep secret. That is a product decision about
onboarding, not a bug fix, which is why it is documented rather than patched.

Until then: do not deploy this with real customer data on a public origin without
putting an authenticating proxy in front of it.

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
| Mutual-fund session in memory | 4 h idle | `sessions.SESSION_TTL_HOURS` |
| Mutual-fund rows in SQLite | 24 h | GC sweep, every 10 min |
| Tax session in memory | 24 h idle, LRU cap 8 | `tax_sessions._evict_locked` |
| Tax session rows in SQLite | 24 h | `purge_expired_from_disk`, on the same sweep |
| `users.pan_id` | Until purge | `DELETE /accounts/{pan}` |

Two corrections worth noting, because both were previously wrong in a way that
mattered:

- **Tax-session eviction used to delete the SQLite row**, which made LRU eviction
  destructive — the user's uploaded AIS was gone and they had to re-upload. Eviction
  is now memory-only and `_rehydrate()` restores from disk, with the disk sweep
  providing the bound instead.
- **`users` rows were never deleted**, including by the endpoint whose docstring says
  it "permanently deletes all data" for a PAN. `delete_all_for_pan` now removes the
  user row too.

`ARCHITECTURE.md` describes the product as having "zero-persistence privacy". That is
not accurate as written — data persists for up to 24 hours by design, because dedup,
upload history and session rehydration all need it. The accurate claim is: *the
uploaded document is never retained, and derived data is purged within 24 hours.*

## Data at rest is not encrypted

`tax_sessions.data` is plaintext JSON containing salary, capital gains, deductions and
PAN. `mf_holdings` / `mf_transactions` hold the portfolio in cleartext.

This is currently acceptable **because the deployment disk is ephemeral** — it is wiped
on restart and spin-down, and the file is gitignored. That is a property of the
hosting tier, not of the code.

**Attaching a persistent volume or enabling backups turns this into a data-at-rest
finding.** If you do either, encrypt the `data` blob with a key from the environment
first. See `DEPLOYMENT.md`.

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

1. **PAN-only authentication** (above). Largest item, and the one that gates using
   this with real data on a public origin.
2. **`POST /market/config` is still unauthenticated.** It can no longer disable
   caching outright — the TTL is floored at 1 minute — but any caller can still lower
   it and increase upstream load. It should require whatever credential item 1
   introduces.
3. **`/health/cache` and `/tax-expert/tax/cache-stats` are unauthenticated.** They leak
   no user data — counters only — but do reveal activity volume.

Closed during the pre-production pass, listed so the history is visible: the
`"empty_ledger"` shared dedup hash, unscoped `/accounts/summary`, unauthenticated
account purge, `Cache-Control: public` on portfolio data, the unlocked tax session
store, destructive tax-session eviction, unpurged `users` rows, unmasked PAN logging,
and the `auth.py` first-login migration that claimed orphaned sessions for whoever
logged in first after a restart.
