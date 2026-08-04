# Migrating off Supabase (OIDC + open source)

Future plan to leave Supabase Auth (and optionally Supabase-hosted Postgres)
without rewriting FinanceBuddy. Auth *today* is documented in
[API.md](API.md) and [ARCHITECTURE.md](ARCHITECTURE.md) → *Authentication &
access control*.

**North star:** FinanceBuddy = **Postgres app + OIDC client**. Supabase is a
convenient IdP + DB today; the OSS target is **any Postgres 15+** and **any
OIDC IdP**, with Keycloak or Zitadel as the reference self-hosted choice.

---

## Goal

Keep the app model the same:

- Postgres owns accounts, allowlist, PAN, and domain data
- API stays `Authorization: Bearer <access_token JWT>` verified via JWKS
- Frontend stays SPA + token interceptor (`authClient` / Axios)

Replace only the **identity provider**, and optionally **where Postgres is
hosted**. Prefer self-hostable / open-source stacks to avoid vendor lock-in.

---

## Target architecture (OSS-first)

| Layer | Today (Supabase) | Target (OSS-friendly) |
|---|---|---|
| Auth IdP | Supabase Auth | **Keycloak**, **Zitadel**, or **Authentik** (OIDC + Google + email/password) |
| App DB | Supabase Postgres | Same schema on **any Postgres 15+** (Render, Fly, Railway, self-hosted, RDS, …) |
| API | FastAPI (e.g. Render) | Same app; host can change |
| Frontend | SPA (e.g. Vercel) | Same; only auth client + env change |
| Email | Supabase invite SMTP | IdP SMTP **or** app-owned mail (Postmark / SES) for invites |

**Recommended default for OSS:** Keycloak (mature OIDC, Google IdP, invite/reset,
admin API) or Zitadel (lighter, modern DX). Do **not** invent app-owned password
crypto.

**Split of responsibility (keep this):**

| System | Owns |
|---|---|
| IdP | Credentials, sessions, MFA, invite/reset email |
| App DB (`users`, `identities`, `profiles`, …) | Authorization, PAN, portfolios |

Do not make the app DB the source of truth for passwords. Mapping stays
`identities(issuer, subject)` → `users.id`.

---

## Design principles

1. **IdP-agnostic boundary** — one module owns verify / invite / ban; routers
   never call a vendor Admin API directly.
2. **Stable app user id** — keep `users.id` (UUID). Map the new IdP subject via
   `identities`.
3. **Issuer is config** — `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE` (no
   hardcoded `*.supabase.co` in logic).
4. **Invite = allowlist + IdP user create** — approve still writes
   `access_requests`, then calls the IdP invite/create + email API.
5. **PAN is never auth** — profile data only (CAS / AIS).
6. **Self-host path for contributors** — docker-compose for IdP + Postgres (+ API).

---

## Phases

### Phase 0 — Prep (while still on Supabase)

Inventory every Supabase touchpoint:

- Frontend: `frontend/src/shared/auth/authClient.ts` (OAuth, password, session,
  `updatePassword`, `getAccessToken`)
- Backend: JWKS verify (`shared/oidc.py`), Admin invite / ban / email-by-subject
  (`shared/routers/auth.py`, `shared/users.py`)
- Env: `SUPABASE_*`, `VITE_SUPABASE_*`

Introduce a thin **`AuthProvider` interface** (even with one implementation):

- `verify_access_token(jwt) -> claims`
- `invite_user(email, redirect_url)`
- `disable_user(subject)` / `delete_auth_user(subject)`
- `lookup_email(subject)` (optional)

Move Supabase Admin calls behind that interface. Keep Swagger **Authorize** as
“paste Bearer JWT” ([API.md](API.md)). Add CI smoke: mint token → `GET /auth/me`.

**Exit:** swapping IdP is a new adapter + env, not a rewrite of Admin Console.

### Phase 1 — Choose and stand up OSS IdP

- Deploy Keycloak or Zitadel (dev / staging first).
- Configure:
  - Realm/project for FinanceBuddy
  - Google IdP (same Google OAuth client; new redirect URIs)
  - Email/password
  - SMTP for invite / reset
  - SPA public client (PKCE) and API audience / resource
- Prefer JWT access tokens validated via JWKS (avoid opaque tokens + introspect
  unless required).

**Exit:** IdP admin works; JWKS URL serves keys; a test user can obtain a JWT.

### Phase 2 — Dual-run verify (no user migration yet)

- Backend accepts **either** Supabase issuer **or** new IdP issuer (temporary
  composite verifier).
- Staging frontend points at the new IdP.
- Keep allowlist / `users.resolve()` unchanged.
- Test end-to-end: invite → set password → PAN → `/auth/me` → one domain API →
  admin suspend / delete.

**Exit:** staging fully on new IdP; production still on Supabase Auth.

### Phase 3 — User / identity cutover

| Strategy | When | Tradeoff |
|---|---|---|
| **A. Re-invite everyone** | Small allowlist | Cleanest; users set password again |
| **B. Just-in-time link** | Same email signs in on new IdP | Attach new `(issuer, subject)` to existing `user_id` by email |
| **C. Password hash export** | Almost never | Supabase hashes are not portable; skip |

**Recommended:** **A + B** — re-invite active users; JIT-link on first login if
email already maps to an app `users` row so portfolios are not orphaned.

Steps:

1. Export allowlisted emails + `user_id` map from app DB.
2. Create / invite users in the new IdP.
3. On first login, insert new `identities` row; keep the same `user_id`.
4. Stop issuing Supabase tokens; remove old identity rows after a soak period.

**Exit:** no production traffic depends on Supabase Auth.

### Phase 4 — Move Postgres (optional; same day or later)

- `pg_dump` / restore (or provider migration tooling).
- Point `DATABASE_URL` at the new host.
- Greenfield: run SQL migrations. Move: restore first, then continue migrations.
- Retire Supabase DB after backup retention window.

**Exit:** zero Supabase services in production (if IdP also moved).

### Phase 5 — Cleanup

- Delete Supabase adapter and env vars; scrub docs.
- Single issuer in `oidc.py`.
- OSS repo: `docker-compose` with `api` + `postgres` + `keycloak` (or Zitadel).
- Contributor path: start stack → create admin in IdP → set
  `FINANCEBUDDY_ADMIN_EMAILS` → open app.

---

## Repo-shaped workstreams

1. **`shared/auth_provider/`** — protocol + `supabase.py` + later
   `keycloak.py` / generic OIDC admin adapter
2. **`shared/oidc.py`** — keep JWKS verification; env-driven issuer/audience;
   multi-issuer only during Phase 2
3. **`frontend/src/shared/auth/`** — replace `supabase-js` with a generic OIDC
   SPA client (e.g. `oidc-client-ts`) or the IdP’s OSS SDK; keep the same
   outward API (`signIn*`, `getAccessToken`, `updatePassword`, `signOut`)
4. **Admin invite / suspend / delete Auth user** — call `AuthProvider` only
5. **Docs** — self-host compose, env table, “mint token for Swagger” against the
   new IdP token endpoint (update [API.md](API.md) at cutover)
6. **Tests** — keep fake JWT issuer in pytest; add contract tests for invite
   adapter with a mocked IdP

---

## Hosting (independent of IdP choice)

- **API:** Render / Fly / Railway / VPS — same Docker/uvicorn. Keep
  `--workers 1` if in-process rate limits / caches remain.
- **Frontend:** Vercel / Cloudflare Pages / static Nginx — update OIDC redirect
  URLs and env only.
- **IdP:** same region as API when possible; pin versions; export/backup realm
  config.
- **Secrets:** never commit IdP admin or “service role” equivalents.

---

## Open-source product decisions

- License the app clearly (e.g. MIT/Apache) and treat the IdP as a
  **dependency**, not a fork of FinanceBuddy.
- Ship **compose for local** development; do not require a SaaS account.
- Keep **invite-only** as the default (finance data); document how a fork can
  open signup if desired.
- Prefer **standard OIDC** so forks can swap Keycloak ↔ Authentik ↔ a managed
  OIDC SaaS without rewriting domain code.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Orphaned portfolios after IdP switch | Link by email to existing `user_id`; never create a second app user for the same email |
| Google OAuth redirect breakage | Update Google Console + IdP + frontend redirects in one change window |
| Invite email deliverability | Configure IdP SMTP early; test approve path on staging |
| Dual-issuer confusion | Time-box Phase 2; feature-flag; remove Supabase issuer quickly after cutover |
| Self-host IdP ops burden | Managed Keycloak/Zitadel is fine in prod; keep the adapter so the vendor is swappable |

---

## Suggested timeline (when executing)

| When | What |
|---|---|
| Anytime (cheap) | Phase 0 — `AuthProvider` interface + env cleanup |
| Migration week | Phases 1–2 on staging |
| Cutover window | Phase 3 — re-invite / JIT link |
| Optional follow-up | Phase 4 — DB move; Phase 5 — remove Supabase |

---

## Related docs

| Doc | Role |
|---|---|
| [API.md](API.md) | How callers pass Bearer tokens; minting tokens for Swagger |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Allowlist, status/role, middleware |
| [ONBOARDING.md](ONBOARDING.md) | Env vars and deploy checklist (update at cutover) |
| [VERIFICATION.md](VERIFICATION.md) | Pre-deploy checks (add IdP smoke at cutover) |
