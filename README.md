# Finance Buddy

Mutual-fund portfolio analytics and Indian income-tax computation, built from the
documents you already have — a CAS statement from CAMS/Karvy and an AIS from the
income-tax portal.

- **Budget Analyzer** — Multi-bank statement ingestion (HDFC, ICICI, SBI, Axis, Kotak, IndusInd, PNB, CSV), 50/30/20 financial health evaluation, multi-account aggregation, burn rate, and deep category/payee drilldowns
- **Mutual funds** — XIRR, FIFO cost basis, allocation drift, peer comparison,
  rebalancing plans, rolling returns, tax-harvest opportunities
- **Tax expert** — AIS parsing, capital-gains computation with grandfathering and
  Section 50AA, old-vs-new regime comparison, broker reconciliation, filed-ITR
- **Equity** — CSV/XLSX uploads (Zerodha/Groww formats natively detected), direct live sync via Zerodha Kite API, portfolio allocation, sector analysis, historical performance tracking

Upload a statement, get analytics. Sign-in is Google; your data persists to your own
Postgres and is encrypted before it gets there.

---

## Documentation

| Document | What it covers |
|---|---|
| **[ONBOARDING.md](ONBOARDING.md)** | Setting it up — locally and in production. Every key, every console, in order. **Start here.** |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | How it works and why. Diagrams, storage model, caching, the constraints the design follows from. |
| **[BUDGET_ANALYSIS.md](BUDGET_ANALYSIS.md)** | Comprehensive technical architecture, computational engines, and user guide for the Budget Analyzer. |
| **[SECURITY.md](SECURITY.md)** | Threat model, what is handled, and what is still open. |

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

# 6. Run
npm run dev
```

App on http://localhost:5173, API docs on http://localhost:8000/docs.

## Tests

```bash
cd backend
TEST_DATABASE_URL=postgresql://postgres:pw@localhost:5432/financebuddy_test \
  python -m pytest tests/ -q
```

362 tests. Without `TEST_DATABASE_URL` the database-backed ones skip rather than fail
— fine for a quick check, not a full pass.

## Stack

FastAPI · PostgreSQL (psycopg 3, no ORM) · pandas · React 18 · Vite · MUI · Zustand

Deploys to Render (backend, `Procfile`) and Vercel (frontend). The database is any
Postgres 11+ — nothing is vendor-specific beyond the connection string.
