# AMFI Mutual Fund Portfolio Pipeline — Technical Reference

> **FinanceBuddy v6.0** · Last Updated: August 2026

This document covers the full architecture, database schema, API surface, and operational runbook for the AMFI-backed mutual fund data engine introduced in FinanceBuddy v6.

---

## 1. Overview

The pipeline fetches the **official AMFI master scheme catalogue** (~14,000+ schemes) from `amfiindia.com`, normalises and filters it, then upserts institutional-grade portfolio disclosures into a PostgreSQL database. The Admin Console lets authorised admins control exactly which AMCs are synced and can purge stale data.

```
AMFI Feed (NAVAll.txt)
        │
        ▼
fetch_amfi_master_schemes()        ← HTTP fetch, line parser, ISIN dedup
        │
        ▼
_normalize_category()              ← Maps raw SEBI category string → standard label
_extract_amc_name()                ← Normalises AMC name from header line
        │
        ▼
AMC / Scheme Filter                ← Selective ingestion by preset or custom list
        │
        ▼
mf_portfolio_snapshots (PostgreSQL) ← Upsert via ON CONFLICT (isin) DO UPDATE
        │
        ▼
Admin Explorer / Fund Factsheet API ← Served to frontend via REST
```

---

## 2. Database Tables (2 Total)

Created by migration: `backend/migrations/0010_mf_portfolio_snapshots.sql`

---

### Table 1 — `mf_portfolio_snapshots`

Primary store for all synced mutual fund scheme data.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `isin` | `text` | NOT NULL | **Primary Key** — ISIN code (e.g. `INF879O01027`) |
| `scheme_code` | `text` | NULL | AMFI numeric scheme code |
| `scheme_name` | `text` | NOT NULL | Full name including plan & option |
| `amc` | `text` | NOT NULL | Asset Management Company name |
| `category` | `text` | NOT NULL | SEBI category (e.g. `Large Cap Fund`) |
| `cap_type` | `text` | NOT NULL | Market cap segment (e.g. `Large Cap`) |
| `aum_cr` | `numeric(14,2)` | NULL | AUM in ₹ Crores |
| `expense_ratio` | `numeric(5,2)` | NULL | Annual expense ratio (%) |
| `risk_level` | `text` | NOT NULL | SEBI Riskometer (e.g. `VERY HIGH`) |
| `exit_load` | `text` | NOT NULL | Exit load conditions text |
| `portfolio_date` | `date` | NOT NULL | Disclosure date (default `2026-07-31`) |
| `sectors` | `jsonb` | NOT NULL | `[{sector: string, value: number}]` top allocations |
| `holdings` | `jsonb` | NOT NULL | `[{name: string, pct: number}]` top 10 holdings |
| `source` | `text` | NOT NULL | Data source label |
| `updated_at` | `timestamptz` | NOT NULL | Last upsert timestamp |

**Indexes:**
```sql
idx_mf_snapshots_code      ON scheme_code
idx_mf_snapshots_name      ON scheme_name
idx_mf_snapshots_category  ON category
```

**Upsert key:** `isin` (primary key) — re-syncing updates rows in-place, never duplicates.

---

### Table 2 — `mf_sync_logs`

Audit trail for every admin-triggered sync operation.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `bigserial` | NOT NULL | **Primary Key** — auto-incrementing |
| `triggered_by` | `text` | NOT NULL | Admin email + scope (e.g. `admin@co.in (TOP10)`) |
| `status` | `text` | NOT NULL | `in_progress` → `completed` or `failed` |
| `schemes_updated` | `int` | NOT NULL | Count of schemes upserted |
| `portfolio_month` | `text` | NOT NULL | Disclosure month label (e.g. `July 2026`) |
| `duration_seconds` | `numeric(6,2)` | NOT NULL | How long the sync ran |
| `error_message` | `text` | NULL | Error detail if `status = failed` |
| `created_at` | `timestamptz` | NOT NULL | When the sync was triggered |

**Index:**
```sql
idx_mf_sync_logs_created  ON created_at DESC
```

---

### Seed Data (8 Funds, Pre-loaded on Migration)

| Fund Name | AMC | Category | AUM (₹ Cr) |
|---|---|---|---|
| Parag Parikh Flexi Cap Fund — Direct Growth | PPFAS | Flexi Cap | 78,450 |
| HDFC Top 100 Fund — Direct Growth | HDFC | Large Cap | 34,890 |
| ICICI Prudential Bluechip Fund — Direct Growth | ICICI Prudential | Large Cap | 58,200 |
| Nippon India Small Cap Fund — Direct Growth | Nippon India | Small Cap | 56,340 |
| SBI Small Cap Fund — Direct Growth | SBI | Small Cap | 31,250 |
| UTI Nifty 50 Index Fund — Direct Growth | UTI | Index Fund | 18,450 |
| Mirae Asset Large & Midcap Fund — Direct Growth | Mirae Asset | Large & Mid Cap | 38,900 |
| Quant Small Cap Fund — Direct Growth | Quant | Small Cap | 24,100 |

Each seed row includes 7–11 sector allocations and top 10 stock holdings with percentage weights.

---

## 3. Backend Service: `amfi_ingest.py`

**Path:** `backend/shared/services/amfi_ingest.py`

### 3.1 Constants

```python
AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

TOP_5_AMCS  = ["HDFC", "SBI", "ICICI Prudential", "Nippon India", "Kotak"]
TOP_10_AMCS = ["HDFC", "SBI", "ICICI Prudential", "Nippon India", "Kotak",
               "Axis", "Quant", "Parag Parikh", "Mirae Asset", "Tata"]
```

`CATEGORY_BENCHMARKS` — dict keyed by SEBI category string, each containing:
- `sectors` — representative sector allocation list
- `holdings` — representative top 10 stock list
- `er_direct` / `er_regular` — typical expense ratios

Categories covered: `Large Cap`, `Mid Cap`, `Small Cap`, `Flexi Cap`,
`Large & Mid Cap`, `ELSS`, `Debt Fund`, `Liquid Fund`, `Index Fund`.

### 3.2 Public Functions

| Function | Signature | Purpose |
|---|---|---|
| `fetch_amfi_master_schemes` | `() → List[Dict]` | Fetches NAVAll.txt, parses ~14k lines, deduplicates by ISIN |
| `trigger_amfi_sync` | `(admin_email, amcs, preset) → Dict` | Main sync — fetches, filters, upserts, writes audit log |
| `search_synced_schemes` | `(query, amc, category, limit, offset) → Dict` | Paginated SQL search with ranked results |
| `get_synced_amc_list` | `() → List[Dict]` | Distinct AMCs in DB with scheme count and total AUM |
| `get_sync_status` | `() → Dict` | Total count, latest date, last 10 sync log rows |
| `purge_snapshots` | `(amc, purge_all, admin_email) → Dict` | Selective or full delete of snapshot rows |

### 3.3 AMC Filter Logic (Strict Matching)

The ingestion filter uses **two rules** to avoid matching the word "Growth" in plan names:

```python
# Rule 1 — AMC name match ("groww" inside "Groww Mutual Fund")
if t_clean in amc_name.lower():
    matched = True

# Rule 2 — Scheme name must START with the brand prefix
# "Groww Nifty 50 Index Fund..." starts with "groww "
if name_lower.startswith(t_clean + " "):
    matched = True
```

> Without this, selecting "Grow" would match `"Nippon India Growth Fund"`, `"SBI Magnum Midcap Growth"`, etc. from other AMCs — because "grow" is a substring of "Growth".

### 3.4 Search Ranking (SQL CASE)

```sql
ORDER BY
  CASE
    WHEN amc ILIKE '%query%' OR amc ILIKE '%alias%' THEN 1   -- AMC name hit
    WHEN scheme_name ILIKE 'query%'                THEN 2   -- Name starts with
    WHEN isin ILIKE 'query%'                       THEN 3   -- ISIN match
    ELSE 4
  END,
  aum_cr DESC NULLS LAST
```

---

## 4. REST API Endpoints (5 Total)

**Router:** `backend/shared/routers/admin_mf.py`  
**Base path:** `/admin/mf-sync`  
**Auth:** Admin email allowlist

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/mf-sync/status` | Sync status, total scheme count, recent audit log |
| `GET` | `/admin/mf-sync/amcs` | Distinct AMCs in DB with scheme count |
| `GET` | `/admin/mf-sync/schemes` | Paginated scheme explorer with filters |
| `POST` | `/admin/mf-sync/trigger` | Trigger a full or selective sync |
| `DELETE` | `/admin/mf-sync/purge` | Delete schemes for one AMC or all |

### `POST /trigger` Request Body

```json
{
  "preset": "top10",             // "top5" | "top10" | "all" — optional
  "amcs": ["Groww", "Zerodha"]   // custom list — optional
}
```

If neither `preset` nor `amcs` is provided → syncs **all ~14,000 schemes**.

### `GET /schemes` Query Params

| Param | Default | Description |
|---|---|---|
| `q` | `""` | Full-text search across scheme name and ISIN |
| `amc` | — | Filter strictly by AMC name (`WHERE amc ILIKE '%X%'`) |
| `category` | — | Filter strictly by SEBI category |
| `limit` | 50 | Results per page (max 200) |
| `offset` | 0 | Pagination offset |

`amc` and `category` are independent AND-able filters. Text `q` is applied on top of them.

### `DELETE /purge` Query Params

| Param | Effect |
|---|---|
| `amc=HDFC` | Deletes all schemes where `amc ILIKE '%HDFC%'` |
| `purge_all=true` | Deletes ALL rows from `mf_portfolio_snapshots` |

---

## 5. Frontend — Admin Console

**Path:** `frontend/src/shared/components/admin/AdminConsole.tsx`

### Sync Panel Features
- **Preset chips:** TOP 5, TOP 10, All
- **Custom AMC chips (22 built-in):** HDFC, SBI, ICICI Prudential, Nippon India, Kotak, Axis, Quant, Parag Parikh, Mirae Asset, Tata, **Groww**, **Zerodha**, DSP, Bandhan, Canara Robeco, UTI, Motilal Oswal, Franklin Templeton, Aditya Birla Sun Life, Edelweiss, HSBC, Invesco
- **Add AMC input:** Type any AMC name → added as a chip for the current session
- **Purge controls:** Per-AMC or full database purge

### Explorer Panel Features
- **AMC filter chips:** All, Groww, SBI, HDFC, ICICI Prudential, Nippon India, Kotak, Axis, Quant, Parag Parikh, Mirae Asset, Tata, Zerodha, DSP
- **Category filter chips:** All standard SEBI categories
- **Text search:** Debounced, searches scheme name + ISIN, preserves AMC/category filters
- **Results table:** Scheme name, ISIN, AMC, Category, AUM, ER, Risk, Coverage
- **Pagination:** 50 results/page with Load More

---

## 6. Data Flow Diagram

```
Admin: "Sync Groww"
       │
       ▼
POST /admin/mf-sync/trigger { amcs: ["Groww"] }
       │
       ▼
trigger_amfi_sync(amcs=["groww"])
  ├── INSERT mf_sync_logs status='in_progress'
  ├── fetch_amfi_master_schemes()
  │     └── GET https://amfiindia.com/spages/NAVAll.txt
  │           ~14,067 lines, deduplicated by ISIN → ~10k unique
  ├── For each scheme:
  │     ├── _normalize_category() → "Large Cap Fund"
  │     ├── _extract_amc_name()   → "Groww Mutual Fund"
  │     └── Filter check → kept only if:
  │           "groww" in amc_name  OR  name starts with "groww "
  │           → ~30–50 Groww schemes kept, all others discarded
  ├── Batch UPSERT → mf_portfolio_snapshots
  ├── MarketCache.invalidate_all()
  └── UPDATE mf_sync_logs status='completed', schemes_updated=N
```

---

## 7. Operational Runbook

### First-Time Setup
1. `python migrations/migrate.py` — creates both tables + seeds 8 funds
2. Open Admin Console → Market Data tab
3. Select AMC chips → **Sync Selected**

### Monthly Refresh (AMFI publishes new data ~5th of each month)
1. Admin Console → pick preset or custom AMCs → **Sync**
2. All existing schemes upserted in-place (no duplicates)
3. `mf_sync_logs` receives a new completed row

### Adding a Brand-New AMC
- Type the AMC name in the **"Add AMC"** input field → select it → **Sync Selected**
- The parser is fully dynamic: any new AMC header in the AMFI feed is automatically extracted. No code changes required.

### Removing an AMC from the DB
- Admin Console → Purge → select AMC → **Purge AMC Data**
- API: `DELETE /admin/mf-sync/purge?amc=AMC_NAME`

### Full Reset
- Admin Console → **Purge All Data**
- API: `DELETE /admin/mf-sync/purge?purge_all=true`
- ⚠️ This does NOT re-insert seed data. Re-trigger a sync afterward.

---

## 8. Key Files

| File | Purpose |
|---|---|
| `backend/shared/services/amfi_ingest.py` | Core engine — fetch, parse, filter, upsert, search, purge |
| `backend/shared/routers/admin_mf.py` | FastAPI router — 5 REST endpoints |
| `backend/migrations/0010_mf_portfolio_snapshots.sql` | Schema (2 tables + indexes + 8 seed rows) |
| `frontend/src/shared/components/admin/AdminConsole.tsx` | Admin UI — sync, explorer, purge |
| `frontend/src/shared/api/client.ts` | API client methods for all endpoints |

---

## 9. Limitations & Known Behaviours

| Behaviour | Detail |
|---|---|
| **AUM is simulated** | The AMFI NAV feed does not publish AUM. Values are derived from a deterministic ISIN hash to produce stable, realistic-looking numbers for UI purposes. |
| **Sectors & Holdings are category templates** | Real per-fund allocations require AMFI's monthly portfolio PDFs. The engine uses SEBI category-level benchmarks as representative proxies. |
| **~14,067 schemes in feed** | All open-ended, closed-ended, and interval schemes are in the feed. After ISIN deduplication, ~10,000–12,000 unique rows are produced. |
| **"grow" alias** | Typing or selecting `"grow"` automatically resolves to `"Groww Mutual Fund"` to prevent matching every fund ending in `"Growth Option"`. |
| **AMC + Category filter is AND** | Both filters apply together — results must match the selected AMC **and** the selected category. |
