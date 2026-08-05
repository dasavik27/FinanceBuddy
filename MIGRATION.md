# Migrating off Supabase (Auth, Database, or Both)

How to leave Supabase **Auth**, **Postgres**, or **both**, without rewriting
FinanceBuddy. Auth *today* is documented in [API.md](API.md) and
[ARCHITECTURE.md](ARCHITECTURE.md) → *Authentication & access control*.

**North star:** FinanceBuddy = **Postgres app + OIDC client**. Supabase is a
convenient IdP + DB today. You can move the layers independently:

| Path | What moves | What stays | Effort |
|---|---|---|---|
| **A. Database only** | App Postgres → Render / Fly / Railway / RDS / self-hosted | Supabase Auth | Low (env + dump/restore) |
| **B. Auth only** | IdP → Keycloak / Zitadel / Authentik (OIDC) | Supabase Postgres (or wherever DB already is) | Medium–high (code + cutover) |
| **C. Both** | Auth + Postgres off Supabase | Nothing on Supabase | Do A then B (or B then A) |

---

## Split of responsibility (keep this)

| System | Owns |
|---|---|
| **IdP (Auth)** | Credentials, sessions, MFA, invite/reset email, JWT issuance |
| **App DB** | `users`, `identities`, `profiles`, allowlist, PAN, portfolios, domain data |

Do **not** make the app DB the source of truth for passwords. Mapping stays
`identities(issuer, subject)` → `users.id`.

```
┌─────────────────────┐     Bearer JWT      ┌─────────────────────┐
│  IdP (Supabase Auth │ ──────────────────► │  FastAPI backend    │
│  or Keycloak/…)     │     JWKS verify     │  (Render / …)       │
└─────────────────────┘                     └──────────┬──────────┘
                                                       │ DATABASE_URL
                                                       ▼
                                            ┌─────────────────────┐
                                            │  App Postgres       │
                                            │  (Supabase DB or    │
                                            │   Render / …)       │
                                            └─────────────────────┘
```

---

# Path A — Move database only (keep Supabase Auth)

Use this when you want cheaper/owned Postgres (e.g. **Render PostgreSQL**) but
are happy to keep Google OAuth / invites on Supabase.

## Impact

| Area | Impact |
|---|---|
| App source code | **None** — `backend/shared/db.py` already reads `DATABASE_URL` |
| Auth / login | **None** — Supabase Auth unchanged |
| Features | **None** if dump/restore is complete |
| Downtime | Short cutover while switching `DATABASE_URL` |

## Properties / env to change

### Required

| Property | Where | Action |
|---|---|---|
| `DATABASE_URL` | Backend host (e.g. Render Web Service) + local `backend/.env` if needed | Point at **new** Postgres (Render URI) |

Example:
```text
postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

Use Render **Internal** URL when API and DB are in the same Render region;
**External** URL for local tools / `pg_dump` from your machine.

### Optional (connection tuning)

| Property | Default | Notes |
|---|---|---|
| `FINANCEBUDDY_DB_POOL_MIN` | `1` | Keep small on free/starter plans |
| `FINANCEBUDDY_DB_POOL_MAX` | `6` | Lower if the Render plan allows few connections |
| `FINANCEBUDDY_DB_STATEMENT_TIMEOUT_MS` | `15000` | Usually leave as-is |

### Do **not** change for Path A

| Property | Why |
|---|---|
| `SUPABASE_URL` | Still used for JWKS / Auth Admin API |
| `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SERVICE_KEY` | Invites, ban, admin |
| `FINANCEBUDDY_ENCRYPTION_KEYS` | **Must match** old DB or encrypted columns will not decrypt |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | Frontend Auth client |
| `VITE_API_URL` | Only if the API host itself changes |

## Code files to change

**None.** No Python/TS edits for a pure DB host move.

Relevant readers (for reference only):

| File | Role |
|---|---|
| `backend/shared/db.py` | Pool from `DATABASE_URL` |
| `backend/migrations/migrate.py` | Schema migrations against `DATABASE_URL` |

## Ops steps

1. Create Postgres on the new host (e.g. Render PostgreSQL).
2. Export from Supabase: `pg_dump` (schema + data).
3. Restore into the new DB (`pg_restore` / `psql`).
4. Or: empty new DB → `cd backend && python -m migrations.migrate` → restore data.
5. Set backend `DATABASE_URL` to the new URI; restart / redeploy API.
6. Smoke-test: sign-in (Supabase) → `/auth/me` → load a portfolio → admin console.
7. Keep the Supabase **project** alive for Auth; only the DB usage goes away.
8. After a retention window, drop the old Supabase Postgres (optional); do **not**
   delete the project if Auth still runs there.

## Critical gotchas

1. **`FINANCEBUDDY_ENCRYPTION_KEYS` must stay identical** across the move.
2. Migrate **full** data, not schema-only, or users lose sessions/portfolios.
3. Watch connection limits on small Render plans vs `FINANCEBUDDY_DB_POOL_MAX`.
4. Prefer `sslmode=require` (usually already in the provider connection string).

**Exit:** API uses non-Supabase Postgres; Supabase Auth still issues JWTs.

---

## Database Reset & Sequence Re-initialization

When resetting staging/test data, preparing a fresh environment, or clearing out old records while keeping all schemas, tables, indexes, and RLS policies intact, use this one-liner or SQL script:

### 1. One-Liner Reset Command (Terminal)

Executes in-memory without saving temporary scripts to the repository:

```bash
python3 -c "
import psycopg, os
from dotenv import load_dotenv

load_dotenv('backend/.env')
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    raise RuntimeError('DATABASE_URL not found in backend/.env')

sql = '''
DO \$\$ 
DECLARE 
    r RECORD;
    s RECORD;
BEGIN 
    -- 1. Truncate all tables and reset primary key identity counters
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP 
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE;';
    END LOOP; 

    -- 2. Reset all standalone sequence counters to 1
    FOR s IN (SELECT sequencename FROM pg_sequences WHERE schemaname = 'public') LOOP 
        EXECUTE 'ALTER SEQUENCE public.' || quote_ident(s.sequencename) || ' RESTART WITH 1;';
    END LOOP;
END \$\$;
'''

with psycopg.connect(db_url, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
print('✅ All tables truncated and sequences reset to 1.')
"
```

### 2. Pure SQL Script (psql / Database Console)

```sql
DO $$ 
DECLARE 
    r RECORD;
    s RECORD;
BEGIN 
    -- 1. Truncate all public tables and restart primary keys
    FOR r IN (
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public'
    ) LOOP 
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE;';
    END LOOP; 

    -- 2. Reset all sequence generators to 1
    FOR s IN (
        SELECT sequencename 
        FROM pg_sequences 
        WHERE schemaname = 'public'
    ) LOOP 
        EXECUTE 'ALTER SEQUENCE public.' || quote_ident(s.sequencename) || ' RESTART WITH 1;';
    END LOOP;
END $$;
```

---

# Path B — Move Auth only (OIDC; keep current Postgres)

Leave Supabase Auth for Keycloak, Zitadel, Authentik, or another OIDC IdP.
Postgres stays wherever it already is (`DATABASE_URL` unchanged).

## Target architecture (Auth)

| Layer | Today | Target |
|---|---|---|
| Auth IdP | Supabase Auth | **Keycloak**, **Zitadel**, or **Authentik** |
| App DB | Current Postgres | Unchanged |
| API | FastAPI | Same; JWKS issuer/audience via env |
| Frontend | `supabase-js` | Generic OIDC SPA client |
| Email | Supabase invite SMTP | IdP SMTP or app-owned mail |

**Recommended OSS defaults:** Keycloak or Zitadel. Do **not** invent app-owned
password crypto.

## Design principles

1. **IdP-agnostic boundary** — one module owns verify / invite / ban.
2. **Stable app user id** — keep `users.id`; map new IdP subject via `identities`.
3. **Issuer is config** — `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE`.
4. **Invite = allowlist + IdP user create**.
5. **PAN is never auth**.
6. **Self-host path** — docker-compose for IdP + Postgres (+ API).

## Properties / env (Auth cutover)

| Property | Role |
|---|---|
| `AUTH_ISSUER` | New IdP issuer (replaces default derived from `SUPABASE_URL`) |
| `AUTH_JWKS_URL` | JWKS endpoint |
| `AUTH_AUDIENCE` | API / SPA audience |
| Frontend OIDC client id / redirect URLs | SPA env (replaces `VITE_SUPABASE_*` at cutover) |
| IdP admin / service credentials | Backend invite/ban adapter |

Until cutover, keep `SUPABASE_*` for dual-run. After cutover, remove them.

## Code / workstreams (Auth)

| Area | Work |
|---|---|
| `shared/auth_provider/` | Protocol + `supabase.py` + later Keycloak/generic OIDC |
| `shared/oidc.py` | Env-driven issuer; multi-issuer only during dual-run |
| `frontend/src/shared/auth/` | Replace `supabase-js` with OIDC SPA client; keep same outward API |
| Admin invite / suspend / delete | Call `AuthProvider` only |
| Docs / tests | Update [API.md](API.md) token minting; keep fake JWT issuer in pytest |

## Phases (Auth)

### Phase 0 — Prep

Inventory touchpoints:

- Frontend: `frontend/src/shared/auth/authClient.ts`
- Backend: `shared/oidc.py`, `shared/routers/auth.py`, `shared/users.py`
- Env: `SUPABASE_*`, `VITE_SUPABASE_*`

Introduce `AuthProvider`: `verify_access_token`, `invite_user`, `disable_user`,
`delete_auth_user`, `lookup_email`.

**Exit:** swapping IdP is a new adapter + env, not an Admin Console rewrite.

### Phase 1 — Stand up OSS IdP

Deploy Keycloak/Zitadel; configure Google IdP, email/password, SMTP, SPA client
(PKCE), JWT access tokens via JWKS.

### Phase 2 — Dual-run verify

Backend accepts Supabase **or** new issuer temporarily. Staging frontend on new
IdP. Production still on Supabase Auth.

### Phase 3 — User / identity cutover

| Strategy | When |
|---|---|
| **A. Re-invite everyone** | Small allowlist (cleanest) |
| **B. Just-in-time link** | Same email → attach new `(issuer, subject)` to existing `user_id` |
| **C. Password hash export** | Skip — Supabase hashes are not portable |

**Recommended:** A + B.

### Phase 4 — Cleanup (Auth)

Remove Supabase Auth adapter and `SUPABASE_*` / `VITE_SUPABASE_*`. Single issuer
in `oidc.py`.

**Exit:** no production traffic depends on Supabase Auth. DB may still be on
Supabase until Path A is done.

---

# Path C — Move both Auth and Database

Do **Path A** and **Path B** in either order:

| Order | When to prefer |
|---|---|
| **A then B** | Want cheaper DB now; Auth migration can wait |
| **B then A** | Want off Supabase Auth first; DB move later |
| **Same window** | Full exit; coordinate dump/restore + IdP cutover |

Final state:

| Layer | Host |
|---|---|
| IdP | Keycloak / Zitadel / Authentik (or managed OIDC) |
| App DB | Render / Fly / Railway / RDS / self-hosted Postgres 15+ |
| API | Render / Fly / … |
| Frontend | Vercel / Cloudflare / static |

**Exit:** zero Supabase services in production.

---

## Hosting notes

- **API:** Render / Fly / Railway / VPS — keep `--workers 1` if in-process rate
  limits / caches remain.
- **Frontend:** update OAuth/OIDC redirect URLs when Auth moves.
- **IdP:** same region as API when possible; pin versions; backup realm config.
- **Secrets:** never commit IdP admin or service-role keys.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Encrypted data unreadable after DB move | Keep `FINANCEBUDDY_ENCRYPTION_KEYS` unchanged |
| Orphaned portfolios after Auth switch | Link by email to existing `user_id` |
| Google OAuth redirect breakage | Update Google Console + IdP + frontend in one window |
| Dual-issuer confusion | Time-box Auth Phase 2; remove Supabase issuer after cutover |
| Connection exhaustion on small DB plans | Lower `FINANCEBUDDY_DB_POOL_MAX` |

---

## Suggested timeline

| When | What |
|---|---|
| Anytime (cheap) | Path A — DB to Render (env + dump/restore) |
| Anytime (cheap) | Auth Phase 0 — `AuthProvider` interface |
| Migration week | Auth Phases 1–2 on staging |
| Cutover window | Auth Phase 3 — re-invite / JIT link |
| Follow-up | Path C cleanup — remove all Supabase |

---

## Related docs

| Doc | Role |
|---|---|
| [API.md](API.md) | Bearer tokens; minting tokens for Swagger |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Allowlist, status/role, middleware |
| [ONBOARDING.md](ONBOARDING.md) | Env vars and deploy checklist |
| [VERIFICATION.md](VERIFICATION.md) | Pre-deploy checks |

---

## How to use this file

This is the **single** migration guide. Use **Path A** for database-only,
**Path B** for Auth/OIDC, and **Path C** for both.
