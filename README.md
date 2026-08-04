# Finance Buddy

**Complete Personal Finance Analytics Platform** — mutual-fund portfolio analytics, Indian income-tax computation, cash-flow budgeting, and equity portfolio management, all from the documents you already have.

## Four Integrated Domains

- **Budget Analyzer** — Multi-bank statement ingestion (HDFC, ICICI, SBI, Axis, Kotak, IndusInd, PNB, CSV), 50/30/20 financial health evaluation, multi-account aggregation, burn rate analysis, rule-based categorization, and deep category/payee drilldowns
- **Mutual Funds** — XIRR returns, FIFO cost basis, allocation drift detection, peer comparison, rebalancing plans, rolling returns, tax-harvest opportunities, and SIP journey tracking
- **Tax Expert** — AIS parsing, capital-gains computation with grandfathering and Section 50AA relief, old-vs-new regime comparison, broker reconciliation, filed-ITR matching, and detailed income breakdown
- **Equity** — CSV/XLSX uploads (Zerodha/Groww formats natively detected), direct live sync via Zerodha Kite API, portfolio allocation, sector analysis, P&L tracking with STCG/LTCG, and individual stock analysis

Upload a statement, get analytics. Sign-in is Google or email/password via Supabase;
access is **invite/approve-only** — admins provision users through the Admin Console.
Your data persists to your own Postgres and is encrypted before it gets there.

---

## Documentation

| Document | What it covers |
|---|---|
| **[ONBOARDING.md](ONBOARDING.md)** | Setting it up — locally and in production. Every key, every console, in order. **Start here.** |
| **[API.md](API.md)** | How to call the API, pass the Bearer token, and the full `/auth` endpoint catalog. |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System design, domain architecture (including Budget Analyzer), **authentication & access control**, security & privacy model, and design constraints. |
| **[VERIFICATION.md](VERIFICATION.md)** | Verification checklist, environment validation, database schema checks, auth/admin deploy checks, and deployment verification scripts. |
| **[HOW_TO_VERIFY_DOCUMENTATION.md](HOW_TO_VERIFY_DOCUMENTATION.md)** | Quick checklist to confirm documentation is complete and up to date. |

---

## Quick start

Assumes Postgres running locally and a Supabase project for sign-in — see
[ONBOARDING.md](ONBOARDING.md) for both, since there is no anonymous mode.

```bash
# 1. Dependencies
python -m venv venv_finance && source venv_finance/bin/activate   # or .\venv_finance\Scripts\activate
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 2. Database
createdb financebuddy && createdb financebuddy_test

# 3. Encryption key — required, no plaintext fallback
python -c "import base64,os;print('k1:'+base64.b64encode(os.urandom(32)).decode())"

# 4. backend/.env and frontend/.env.local — see ONBOARDING.md

# 5. Schema
cd backend && python -m migrations.migrate && cd ..

# 6. Run — frontend and backend together
cd frontend && npm run dev:all
```

App on http://localhost:5173. OpenAPI try-it-out on http://localhost:8000/docs.
How to authenticate requests: [API.md](API.md).
`npm run dev` alone starts only the frontend.

## Tests

```bash
# Backend — ~875 tests
cd backend
TEST_DATABASE_URL=postgresql://postgres:pw@localhost:5432/financebuddy_test \
  python -m pytest tests/ -q

# Frontend — vitest
cd frontend && npm test
```

Without `TEST_DATABASE_URL` the database-backed tests skip rather than fail — fine
for a quick check, not a full pass. Auth/access-control coverage lives in
`tests/test_user_status_role.py` (requires `TEST_DATABASE_URL`).

## Verification

After setup, run the verification checklist:

```bash
python -m pytest backend/tests/test_sql_is_valid_postgres.py -v
python -m pytest backend/tests/test_only_shared_db_opens_connections.py -v
cd backend && python scripts/verify_setup.py
```

See [VERIFICATION.md](VERIFICATION.md) for complete verification procedures.

## Stack

FastAPI · PostgreSQL (psycopg 3, no ORM) · pandas · React 18 · Vite · MUI · Zustand

Deploys to Render (backend, `Procfile`) and Vercel (frontend). The database is any
Postgres 11+ — nothing is vendor-specific beyond the connection string.
