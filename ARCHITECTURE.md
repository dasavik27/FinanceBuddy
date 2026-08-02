# Finance Buddy — Architecture

Complete personal finance analytics platform with four independent domains: Budget Analyzer (cash-flow analysis), Mutual Funds (portfolio analytics), Equity (direct stock tracking), and Tax Expert (income-tax computation).

This describes the system as it is. Where a design looks unusual, the reason is stated — most of the unusual choices trace back to one constraint (below) and are wrong to "clean up" without removing that constraint first.

Companion documents: **ONBOARDING.md** (setup instructions), **SECURITY.md** (threat model), **BUDGET_ANALYSIS.md** (Budget deep dive), and **VERIFICATION.md** (setup validation).

---

## URL prefixes by domain

| Domain | Prefix | Routers | API Example |
|---|---|---|---|
| Infrastructure | `/auth` `/market` `/accounts` `/history` | 4 routers | `GET /accounts/summary` |
| **Budget Analyzer** | `/budget/{portfolio,analytics,rules}` | 3 routers | `POST /budget/portfolio/upload` |
| **Mutual Funds** | `/mutual-funds/*` | 9 routers | `GET /mutual-funds/overview/{sid}/summary` |
| **Tax Expert** | `/tax-expert` | 6 routers | `GET /tax-expert/{sid}/tax/summary` |
| **Equity** | `/equity/*` | 6 routers | `GET /equity/overview/{sid}/summary` |

---

## Backend structure

```
backend/
├── main.py                     # middleware, router mounting
├── migrations/                 # 0001-0005 numbered SQL migrations
├── shared/
│   ├── db.py                   # single psycopg 3 connection pool
│   ├── crypto.py               # AES-256-GCM encryption
│   ├── identity.py             # user auth, ownership checks
│   └── routers/                # /auth, /market, /accounts, /history
└── domains/
    ├── budget/                 # transaction parsing, categorization, rules
    ├── mutual_funds/           # XIRR, allocation, peer comparison
    ├── tax_expert/             # capital gains, regime comparison
    └── equity/                 # holdings sync, sector analysis, P&L
```

---

## Database migrations

All migrations are idempotent and advisory-locked. Run with:

```bash
cd backend && python -m migrations.migrate
```

| # | Created | What |
|---|---|---|
| 0001 | Initial | users, identities, profiles, sessions, session_payloads |
| 0002 | MF/Tax era | tax_payloads, indices |
| 0003 | Equity | equity support in sessions |
| 0004 | Budget (2026-08-02) | budget_payloads, budget_rules tables |
| 0005 | Budget rules | rule versioning and history |

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
