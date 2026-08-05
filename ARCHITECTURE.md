# Finance Buddy — Architecture

**Single source of truth** for how Finance Buddy is built and how its four domains
work end-to-end. This describes the system as it is.

Companion docs (operations only — not architecture duplicates):

| Doc | Role |
|---|---|
| [ONBOARDING.md](ONBOARDING.md) | Local + production setup |
| [API.md](API.md) | How to call APIs & pass Bearer tokens (`/auth` catalog) |
| [VERIFICATION.md](VERIFICATION.md) | Setup / deploy checks |
| [MIGRATION.md](MIGRATION.md) | Moving off Supabase Auth, DB, or both |

---

## 1. System overview

Finance Buddy is a personal finance analytics platform with **four independent
domains** plus shared infrastructure:

| Domain | Job |
|---|---|
| **Budget Analyzer** | Bank-statement cash-flow intelligence (50/30/20, categories, insights) |
| **Mutual Funds** | CAS portfolio analytics (XIRR, allocation, peers, rebalance, tax-harvest) |
| **Equity** | Direct stock holdings, P&L, sectors, stock research analyzer |
| **Tax Expert** | AIS-driven income-tax computation, regime compare, broker reconcile |

```mermaid
flowchart TB
  subgraph clients [Clients]
    SPA[React SPA - Vite MUI Zustand]
  end

  subgraph edge [Edge]
    AuthIdP[Supabase Auth - JWT IdP]
  end

  subgraph api [FastAPI Backend - single uvicorn worker]
    MW[IdentityMiddleware - JWKS verify + users.resolve]
    SharedR["/auth /market /accounts /history /admin"]
    BudgetR["/budget/*"]
    MFR["/mutual-funds/*"]
    EqR["/equity/*"]
    TaxR["/tax-expert/*"]
  end

  subgraph data [Data plane]
    PG[(PostgreSQL - encrypted payloads)]
    Mem[Resident LRU sessions - MF Equity Tax]
    Cache[MarketCache L1 + disk]
  end

  subgraph ext [External market data]
    AMFI[AMFI NAV TER catalogue]
    MFAPI[mfapi.in NAV history]
    YF[Yahoo Finance]
    NSE[NSE disclosures]
    BSE[BSE VWAP]
    Kite[Zerodha Kite optional]
  end

  SPA -->|Bearer JWT| MW
  AuthIdP -->|issue JWT| SPA
  MW --> SharedR
  MW --> BudgetR
  MW --> MFR
  MW --> EqR
  MW --> TaxR

  BudgetR --> PG
  MFR --> Mem
  MFR --> PG
  EqR --> Mem
  EqR --> PG
  TaxR --> Mem
  TaxR --> PG
  SharedR --> PG

  MFR --> AMFI
  MFR --> MFAPI
  MFR --> YF
  EqR --> YF
  EqR --> NSE
  EqR --> BSE
  EqR --> Kite
  SharedR --> AMFI
  SharedR --> Cache
  Mem --> Cache
```

### Design constraint

Domains must stay **independently removable**. Cross-domain fan-out goes through
registries (`janitor`, `session_stores`), not hardcoded import lists. Unusual
choices usually exist because of that constraint — do not “clean them up” without
removing the constraint first.

---

## 2. API prefixes & frontend routes

### API

| Domain | Prefix | Routers | Example |
|---|---|---|---|
| Infrastructure | `/auth` `/market` `/accounts` `/history` `/admin` | shared | `GET /auth/me` |
| Budget | `/budget/{portfolio,analytics,rules,accounts,insights}` | 5 | `POST /budget/portfolio/upload` |
| Mutual Funds | `/mutual-funds/*` | 9 | `GET /mutual-funds/overview/{sid}/summary` |
| Equity | `/equity/*` | 6 | `GET /equity/overview/{sid}/summary` |
| Tax Expert | `/tax-expert` | 6 | `GET /tax-expert/{sid}/tax/summary` |

Full `/auth` method catalog: **[API.md](API.md)**.

### Frontend

| Path | Renders |
|---|---|
| `/` | Landing (out) · → `/dashboard` (in) |
| `/dashboard` | Domain hub |
| `/mutual-funds/*` | MF tabs |
| `/equity/*` | Equity tabs |
| `/tax-expert/*` | Tax Expert |
| `/budget/*` | Budget Analyzer |
| `/accounts` | Export / purge |
| `/profile` | Profile + PAN |
| `/admin` | Admin Console (`role=admin`) |

Legacy `/dashboard/<domain>` rewrites to `/<domain>` (`routes.test.ts`).

---

## 3. Repository layout

```
backend/
├── main.py                     # middleware, router mount, lifespan
├── migrations/                 # 0001–0010 SQL
├── shared/
│   ├── db.py                   # psycopg 3 pool
│   ├── crypto.py               # AES-256-GCM
│   ├── identity.py / users.py / oidc.py
│   ├── janitor.py              # periodic sweep registry
│   ├── session_stores.py       # resident-state registry
│   ├── storage.py              # MF/Equity payload codec + dedup
│   ├── reference/              # statutory facts (capital gains, …)
│   ├── services/               # market_data, amfi_ingest, cache, returns
│   └── routers/                # auth, market, accounts, history, admin_mf
└── domains/
    ├── budget/
    ├── mutual_funds/
    ├── equity/
    └── tax_expert/

frontend/src/
├── domains/{budget,mutual-funds,equity,tax-expert}/
└── shared/{auth,api,components/admin,store}/
```

### Domain independence

| Registry | Domains register | Consumed by |
|---|---|---|
| `shared/janitor.py` | periodic `purge_expired` | lifespan thread (~10 min) |
| `shared/session_stores.py` | `evict_user` / `forget_session` / `clear_all` | logout, purge, cache clear |

Rules:

- **No domain imports another domain** (backend or frontend).
- **`shared/` must not import `domains/`** — exception: `history.py` uses MF
  `compute_xirr` for `/history/compare`.
- **Statutory facts** live in `shared/reference/` (shared by MF + Tax).

---

## 4. Overall request lifecycle

```mermaid
sequenceDiagram
  participant U as Browser SPA
  participant S as Supabase Auth
  participant API as FastAPI
  participant DB as Postgres

  U->>S: Sign-in Google / password
  S-->>U: access_token JWT
  U->>API: API call + Authorization Bearer
  API->>API: JWKS verify + users.resolve
  alt not allowlisted
    API-->>U: 403 not_authorized
  else pending or suspended
    API-->>U: block except /auth/me logout
  else active
    API->>DB: domain read/write encrypted payloads
    API-->>U: JSON no-store
  end
```

**Logout order:** `POST /auth/logout` (await — evicts resident stores) →
Supabase `signOut` → clear Zustand.

---

## 5. Database migrations

```bash
cd backend && python -m migrations.migrate
```

| # | What |
|---|---|
| 0001 | `users`, `identities`, `profiles`, `sessions`, `session_payloads`, `tax_payloads`, `app_settings` |
| 0002 | RLS deny-all backstop |
| 0003 | Application-encrypted PII columns |
| 0004–0007 | Budget tables / hardening / accounts |
| 0008 | `access_requests` |
| 0009 | `users.status`, `users.role` |
| 0010 | `mf_portfolio_snapshots`, `mf_sync_logs` |

---

## 6. Budget Analyzer

Converts Indian bank statements into cash-flow intelligence — **no open banking**,
no third-party scraping.

```mermaid
flowchart TD
  A[Statement PDF CSV XLSX] --> B[parser.py bank detect]
  B --> C[categorizer + user rules]
  C --> D[(budget_payloads encrypted)]
  D --> E[pipeline.py BudgetContext]
  E --> F[analytics + insights]
  F --> G[BudgetDashboard UI]
```

### Pipeline

1. **Upload** — `POST /budget/portfolio/upload`
2. **Parse** — `parser.py` + `bank_config.json` → unified txn schema
3. **Enrich** — categories, payment modes, merchant aliases
4. **Persist** — encrypted `budget_payloads`; content-hash dedup
5. **Analyze** — overview, categories, velocity, 50/30/20, insights
6. **UI** — single `/budget` dashboard with tabs

### Key modules

| Path | Role |
|---|---|
| `domains/budget/parser.py` | Multi-bank PDF/CSV/XLSX |
| `domains/budget/categorizer.py` / `rules_safety.py` | Rules engine |
| `domains/budget/sessions.py` | Encrypted persistence + ownership |
| `domains/budget/pipeline.py` | Session → analysable frame |
| `domains/budget/insights.py` | Recurring, anomalies, forecast, envelopes, Sankey |
| `domains/budget/transfers.py` | Internal transfer pairing |

### API surface

| Prefix | Purpose |
|---|---|
| `/budget/portfolio` | Upload, list/delete sessions |
| `/budget/analytics` | Overview, transactions, categories |
| `/budget/insights` | Transfers, recurring, forecast, anomalies, envelopes, Sankey, coverage |
| `/budget/accounts` | Account meta / utilisation |
| `/budget/rules` | CRUD, test, apply-all |

`session_id` may be a specific upload or literal `overall`.

### Storage

- **DB-only** — not registered in `session_stores` (no resident LRU).
- Tables: `budget_payloads`, `budget_rules`, `budget_account_meta`,
  `budget_envelopes`, `budget_merchant_aliases`, `budget_txn_flags`.

### Engines (summary)

- **50/30/20 health** — Needs / Wants / Investments scoring.
- **Category & merchant drilldown** — debit/credit toggles, ranked payees.
- **Velocity & burn** — net savings rate, runway, MoM shifts.
- **Rules** — priority keyword/regex; batch re-tag.

### Frontend

`BudgetDashboard.tsx` · `TransactionsTab` · `AccountsTab` · `InsightsTab` ·
`RulesTab` · `BudgetHealth503020Card` · `MoneyFlowCard` · `UploadStatementModal` ·
`hooks/useBudget.ts`.

### External sources

**None** — user uploads only.

---

## 7. Mutual Funds

CAS-based portfolio analytics with live NAV enrichment and factsheet insights.

```mermaid
flowchart TD
  A[CAS PDF] --> B[parser.py casparser]
  B --> C[Portfolio model + AMFI NAV]
  C --> D[Encrypted session_payloads]
  D --> E[Resident LRU Portfolio]
  E --> F[finance.py XIRR risk]
  F --> G[MF Dashboard tabs]
  H[AMFI sync admin] --> I[(mf_portfolio_snapshots)]
  I --> J[fund-insights Tier1]
  K[Yahoo] --> J
```

### Pipeline

1. **Upload** — `POST /mutual-funds/portfolio/parse` (CAS + password)
2. **Parse** — holdings, full txn ledger, SIPs; PDF deleted
3. **Enrich** — AMFI live NAVs/TER; categories; fund insights
4. **Persist** — compressed encrypted blob in `session_payloads`
5. **Analyze** — XIRR, allocation, peers, rebalance, tax-harvest, journey
6. **UI** — URL tabs under `/mutual-funds/*`

### Key modules

| Path | Role |
|---|---|
| `domains/mutual_funds/parser.py` | CAMS/KFintech CAS |
| `domains/mutual_funds/sessions.py` | LRU resident + rehydrate |
| `domains/mutual_funds/models.py` | `Portfolio` |
| `domains/mutual_funds/finance.py` | XIRR, simulation, drawdown, SIP |
| `domains/mutual_funds/tax_lots.py` | FIFO lots / harvest |
| `domains/mutual_funds/portfolio_discovery.py` | Factsheet cascade |
| `shared/services/market_data.py` | AMFI NAV/TER, mfapi history |
| `shared/services/amfi_ingest.py` | Admin catalogue sync |

### Insights cascade

| Tier | Source |
|---|---|
| 1 | `mf_portfolio_snapshots` (AMFI admin sync / seed) |
| 2 | Yahoo Finance |
| — | Blank (no synthetic heuristics) |

### API surface (selected)

| Prefix | Purpose |
|---|---|
| `/mutual-funds/portfolio` | Parse, sync |
| `/mutual-funds/overview` | Summary, allocation, benchmark overlay |
| `/mutual-funds/holdings` | Holdings, txns, fund-insights |
| `/mutual-funds/performance` | Trailing/rolling/drawdown/SIP |
| `/mutual-funds/compare` | Peer search & metrics |
| `/mutual-funds/insights` `/rebalance` `/journey` `/planning` | Insights suite |
| `/admin/mf-sync` | Catalogue sync / purge / explorer |
| `/market` | Live NAV / config |

### Storage

- Resident LRU: **3** sessions, ~4h idle TTL; janitor + `session_stores`.
- Postgres: `sessions` + encrypted `session_payloads`.
- Admin: `mf_portfolio_snapshots`, `mf_sync_logs` (migration 0010).

### AMFI admin pipeline (brief)

`NAVAll.txt` → parse/ISIN dedup → AMC filter → upsert snapshots → Admin Explorer.
Known limits: snapshot AUM is placeholder; sectors/holdings are category templates
until real PDF disclosures are wired.

### Frontend

`MutualFundsDashboard` · Overview / Holdings / Performance / Compare / Journey /
Insights · `MFUploadPanel` · `hooks/useData.ts`.

### External sources

AMFI · mfapi.in · Yahoo (tier-2 factsheets).

---

## 8. Equity (Indian Stocks)

Broker holdings + tradebook analytics, plus a standalone Stock Analyzer.

```mermaid
flowchart TD
  A[CSV XLSX or Kite sync] --> B[parser.py]
  B --> C[EquityPortfolio + sector_map]
  C --> D[quotes.py live LTP]
  D --> E[Encrypted session_payloads]
  E --> F[Resident LRU]
  F --> G[Overview Holdings PnL Sectors]
  H[Stock Analyzer] --> I[Yahoo NS then BO]
  H --> J[NSE corporate actions]
  H --> K[BSE VWAP]
  H --> L[Math beta]
  I --> M[StockAnalyzerTab + sources icons]
  J --> M
  K --> M
  L --> M
```

### Pipeline (portfolio)

1. **Upload / Kite** — `POST /equity/portfolio/parse` or Kite OAuth sync
2. **Parse** — holdings + tradebook; `sector_map.py`
3. **Price** — batched `quotes.py`
4. **Persist** — encrypted payload + resident LRU
5. **Analyze** — summary, P&L (STCG/LTCG), sectors, performance, insights
6. **UI** — `/equity/*` tabs

Stock Analyzer (`/equity/analyzer`) works **without** a portfolio session.

### Equity data sourcing (analyzer)

| Metric | Primary | Fallback |
|---|---|---|
| LTP, day range, Market Cap, P/E, EPS, P/B | Yahoo `.NS` | Yahoo `.BO` |
| Dividend yield | NSE corporate actions | Yahoo |
| VWAP | BSE `StockTrading.WAP` | — |
| Beta | Math vs Nifty 50 | Yahoo |
| Charts | Yahoo OHLCV | — |
| Corporate actions / filings | NSE | Yahoo / — |

Payload includes `source`, per-field `sources`, and `as_of`. UI shows info-icon
tooltips per card. Cache key: `equity_analysis_v3`. Degraded responses
(P/E + mcap + EPS all null) use a short TTL (~30s).

### Key modules

| Path | Role |
|---|---|
| `domains/equity/parser.py` | Zerodha/Groww/NSDL/generic |
| `domains/equity/sessions.py` | LRU + encrypt |
| `domains/equity/models.py` | `EquityPortfolio` |
| `domains/equity/quotes.py` | Batched LTP |
| `domains/equity/stock_analyzer.py` | Research engine + sources |
| `domains/equity/bse_client.py` | VWAP |
| `domains/equity/nse_corporate.py` | Actions / events / announcements |
| `domains/equity/kite_client.py` | Optional broker sync |

### API surface

| Prefix | Purpose |
|---|---|
| `/equity/portfolio` | Parse, Kite login/connect, sync |
| `/equity/overview` | Summary, allocation |
| `/equity/holdings` | Holdings, P&L |
| `/equity/performance` | Performance series |
| `/equity/insights` | Concentration / harvest nudges |
| `/equity/analyzer` | Search, analyze, indices, corporate, impact |

### Storage

- Resident LRU: **3** sessions, ~4h TTL; janitor + `session_stores`.
- Same `sessions` / `session_payloads` pattern as MF.

### Frontend

`EquityDashboard` · Overview / Holdings / P&L / Sectors / Performance / Analyzer /
Insights · `EquityUploadPanel` · `hooks/useEquityData.ts`.

### External sources

Yahoo · NSE · BSE · Zerodha Kite (optional) · Nifty for beta.

---

## 9. Tax Expert

AIS-driven tax computation for Indian resident individuals — old vs new regime,
capital gains, broker reconciliation, filed-ITR compare.

```mermaid
flowchart TD
  A[AIS PDF] --> B[ais_parser.py]
  B --> C{Broker P and L?}
  C -->|yes| D[broker_parser + reconciliation]
  C -->|no| E[tax_sessions encrypt]
  D --> E
  E --> F[(tax_payloads)]
  F --> G[Resident LRU]
  G --> H[tax_engine.py regimes]
  H --> I[computation_cache]
  I --> J[TaxStrategyTab UI]
  K[ITR PDF optional] --> L[itr_parser]
  L --> J
```

### Pipeline

1. **Upload** — `POST /tax-expert/parse-ais` (+ optional broker Excel)
2. **Parse AIS** — income, TDS, CG buckets, deduction structure
3. **Reconcile** — optional Zerodha Tax P&L cross-check
4. **Persist** — encrypted `tax_payloads`; PAN match vs profile
5. **Compute** — old/new regime; cache by `(session, version, regime)`
6. **UI** — overview, income, savings, CG, ITR compare, history

### Key modules

| Path | Role |
|---|---|
| `domains/tax_expert/ais_parser.py` | AIS PDF tables |
| `domains/tax_expert/tax_sessions.py` | LRU + encrypt |
| `domains/tax_expert/tax_engine.py` | Regime computation |
| `domains/tax_expert/computation_cache.py` | Memoize `compute_tax` |
| `domains/tax_expert/reconciliation.py` | AIS vs broker |
| `domains/tax_expert/broker_parser.py` | Zerodha Tax P&L |
| `domains/tax_expert/itr_parser.py` | Filed ITR PDF |
| `shared/reference/capital_gains.json` | Statutory CG rates |

### API surface

| Area | Endpoints |
|---|---|
| Session | `POST /parse-ais`, reconcile-broker, tax-history |
| Compute | `GET .../summary`, compare-regimes, recalculate |
| Detail | income, capital-gains, ITR upload/get |
| Rules | `GET /rules` |

### Storage

- Resident LRU: **8** sessions, ~24h idle; lazy eviction (**no** janitor sweep).
- Registers in `session_stores` (clears computation cache on `clear_all`).
- Postgres: `tax_payloads`.

### Frontend

`TaxExpertDashboard` / `TaxStrategyTab` · Overview · Income · Savings · Capital
Gains · ITR Compare · History · `TaxUploadPanel` · `hooks/useTaxExpert.ts`.

### External sources

**None at runtime** — user documents + local statutory JSON.

---

## 10. Shared infrastructure

### Auth & access control

| Layer | Store | Purpose |
|---|---|---|
| Auth | Supabase Auth | Sign-in (Google / email-password) |
| App account | `users` + `identities` + `profiles` | Authorization, PAN, ownership |

Provisioning allowlist: `FINANCEBUDDY_ADMIN_EMAILS`, approved/pending
`access_requests`. Bootstrap admins → `active` + `admin` on first provision.

| `status` | Effect |
|---|---|
| `pending` / `suspended` | Only `/auth/me`, `/auth/logout` |
| `active` | Full API (frontend may still require PAN) |

Admin UI: `/admin` · API admin routes under `/auth/*` (see API.md).

### Security & privacy

- **JWT**: JWKS via `shared/oidc.py` (`exp`, `iss`, `aud`).
- **Encryption**: AES-256-GCM (`shared/crypto.py`); AAD binds `session_id` /
  `user_id`; fatal without `FINANCEBUDDY_ENCRYPTION_KEYS`.
- **Authz**: fail closed — unowned resources → **404** (not 403).
- **Cache-Control**: default `no-store`; public only for user-independent market data.
- **No third-party statement scraping** — parse in-process; temp files deleted.

### Market data (shared)

| Source | Consumers |
|---|---|
| AMFI NAV / TER | MF valuation, `/market` |
| mfapi.in | MF NAV history |
| Yahoo | Equity quotes/analyzer; MF factsheet tier-2 |
| NSE / BSE | Equity analyzer |
| Indices | Benchmarks (MF + Equity) |

`MarketCache` (L1 + disk) + optional refresh sweep via janitor.

### Resident session caps (defaults)

| Domain | Cap | TTL | Janitor |
|---|---|---|---|
| Mutual Funds | 3 | ~4h | yes |
| Equity | 3 | ~4h | yes |
| Tax Expert | 8 | ~24h | lazy only |
| Budget | — | DB-only | — |

---

## 11. Stack

FastAPI · PostgreSQL 11+ (psycopg 3, no ORM) · pandas · React 18 · Vite · MUI ·
Zustand · Supabase Auth (IdP).

Single uvicorn worker, ~512 MB RAM typical. Setup: [ONBOARDING.md](ONBOARDING.md).
Validate: [VERIFICATION.md](VERIFICATION.md). Leave Supabase: [MIGRATION.md](MIGRATION.md).
