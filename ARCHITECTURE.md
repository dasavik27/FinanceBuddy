# Finance Buddy — Architecture

Complete personal finance analytics platform with four independent domains: Budget Analyzer (cash-flow analysis), Mutual Funds (portfolio analytics), Equity (direct stock tracking), and Tax Expert (income-tax computation).

This describes the system as it is. Where a design looks unusual, the reason is stated — most of the unusual choices trace back to one constraint (below) and are wrong to "clean up" without removing that constraint first.

Companion documents: **ONBOARDING.md** (setup instructions), **SECURITY.md** (threat model), **BUDGET_ANALYSIS.md** (Budget deep dive), and **VERIFICATION.md** (setup validation).

---

## API prefixes by domain

| Domain | Prefix | Routers | API Example |
|---|---|---|---|
| Infrastructure | `/auth` `/market` `/accounts` `/history` | 4 routers | `GET /accounts/summary` |
| **Budget Analyzer** | `/budget/{portfolio,analytics,rules,accounts,insights}` | 5 routers | `POST /budget/portfolio/upload` |
| **Mutual Funds** | `/mutual-funds/*` | 9 routers | `GET /mutual-funds/overview/{sid}/summary` |
| **Tax Expert** | `/tax-expert` | 6 routers | `GET /tax-expert/{sid}/tax/summary` |
| **Equity** | `/equity/*` | 6 routers | `GET /equity/overview/{sid}/summary` |

---

## Frontend routes

Each domain owns a top-level path. `/dashboard` is the hub — the grid of the four
domains, and the way back out from inside one.

| Path | Renders |
|---|---|
| `/` | Landing (signed out) · redirects to `/dashboard` (signed in) |
| `/dashboard` | Domain hub |
| `/mutual-funds/*` | Mutual Funds (tabs: overview, holdings, performance, compare, journey, insights, history) |
| `/equity/*` | Indian Stocks |
| `/tax-expert/*` | Tax Expert |
| `/budget/*` | Budget Analyzer |
| `/accounts` | Account settings, export, purge |

Domains previously sat under `/dashboard/<domain>`. Those URLs still resolve —
`Dashboard.tsx` rewrites `/dashboard/<rest>` to `/<rest>`, preserving query and hash —
but new links should use the top-level form. The redirect and the ranking of
`dashboard` against `dashboard/*` are covered by `routes.test.ts`.

OAuth redirect URLs point at `/dashboard` and are unaffected.

---

## Backend structure

```
backend/
├── main.py                     # middleware, router mounting, lifespan
├── migrations/                 # 0001-0007 numbered SQL migrations
├── shared/
│   ├── db.py                   # single psycopg 3 connection pool
│   ├── crypto.py               # AES-256-GCM encryption
│   ├── identity.py             # user auth, ownership checks
│   ├── janitor.py              # periodic sweep registry (see below)
│   ├── session_stores.py       # resident-state registry (see below)
│   ├── reference/              # statutory data owned by no domain
│   │   └── capital_gains.json  # LTCG/STCG rates, holding periods
│   ├── services/
│   │   ├── returns.py          # trailing returns on any price/NAV series
│   │   ├── market_data.py      # AMFI / mfapi NAV bundles
│   │   ├── market_indices.py   # benchmark index series
│   │   └── cache.py            # in-process TTL cache
│   └── routers/                # /auth, /market, /accounts, /history
└── domains/
    ├── budget/                 # transaction parsing, categorization, rules
    ├── mutual_funds/           # XIRR, allocation, peer comparison
    ├── tax_expert/             # capital gains, regime comparison
    └── equity/                 # holdings sync, sector analysis, P&L
```

### Keeping the domains independent

A domain must be removable without breaking the others. Two registries exist so
that cross-domain fan-out is not written as a hardcoded list of imports:

| Registry | Domains register | Consumed by |
|---|---|---|
| `shared/janitor.py` | a periodic sweep (`purge_expired`) | `main.py` lifespan starts one thread |
| `shared/session_stores.py` | `evict_user` / `forget_session` / `clear_all` | logout, account purge, cache clear, history delete |

Both are populated as an import side effect of each domain's session module, and
`main.py` logs the resulting roster at startup — a store that fails to register would
otherwise mean a purge silently evicts nothing.

Rules that hold today and are worth keeping:

- **No domain imports another domain.** Currently zero, backend and frontend.
- **`shared/` must not import from `domains/`.** One exception remains:
  `shared/routers/history.py` pulls `compute_xirr` for its mutual-funds-specific
  `/compare` handler, which belongs in that domain.
- **Statutory facts go in `shared/reference/`,** not in the domain that happens to
  need them first — capital-gains rates live there because Mutual Funds and Tax
  Expert are equally entitled to them.

---

## Database migrations

All migrations are idempotent and advisory-locked. Run with:

```bash
cd backend && python -m migrations.migrate
```

| # | What |
|---|---|
| 0001 | `users`, `identities`, `profiles`, `sessions`, `session_payloads`, `tax_payloads`, `app_settings` |
| 0002 | Row-level security, deny-all — a backstop behind the application's own authorization, not a replacement for it |
| 0003 | Move PII into application-encrypted columns (PAN, metrics, payloads) |
| 0004 | Budget: `budget_payloads`, `budget_rules` |
| 0005 | Budget rule versioning |
| 0006 | Budget hardening — brings the budget tables up to the schema conventions the rest already follow |
| 0007 | Budget accounts: `budget_account_meta`, `budget_envelopes`, `budget_merchant_aliases`, `budget_txn_flags` |

All are Postgres-validated by `test_sql_is_valid_postgres`.

---

## Frontend structure

```
frontend/src/
├── domains/
│   ├── budget/                 # BudgetDashboard, upload, sessions
│   ├── mutual-funds/           # MF portfolio, holdings, insights
│   ├── tax-expert/             # Tax computation, ITR comparison
│   └── equity/                 # Stock holdings, sector allocation
└── shared/
    ├── auth/authClient.ts      # Supabase OAuth gateway
    ├── api/client.ts           # Axios + Bearer interceptor
    └── store/appStore.ts       # Zustand session store
```

---

## Stack

FastAPI · PostgreSQL 11+ · pandas · React 18 · Vite · MUI · Zustand

Single uvicorn worker, ~512 MB RAM. See ONBOARDING.md for full setup and VERIFICATION.md to validate deployment.
