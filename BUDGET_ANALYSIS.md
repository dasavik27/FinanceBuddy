# Budget Analyzer & Multi-Account Cash Flow Intelligence

> **Comprehensive Technical Architecture, Computational Engines, API Reference, and User Guide for FinanceBuddy's Budget Analyzer.**

---

## 📑 Table of Contents
1. [Overview & Value Proposition](#overview--value-proposition)
2. [High-Level Architecture](#high-level-architecture)
3. [Bank Statement Ingestion Pipeline](#bank-statement-ingestion-pipeline)
4. [Computational Engines & Financial Intelligence](#computational-engines--financial-intelligence)
   - [50 / 30 / 20 Budget Health Evaluation Suite](#1-50--30--20-budget-health-evaluation-suite)
   - [Category Spend Analytics & Payee Drilldown](#2-category-spend-analytics--payee-drilldown)
   - [Cash Flow Velocity, Burn Rate & Liquidity Projections](#3-cash-flow-velocity-burn-rate--liquidity-projections)
   - [Rule-Based Categorization Engine](#4-rule-based-categorization-engine)
5. [Multi-Level Dynamic Filtering System](#multi-level-dynamic-filtering-system)
6. [API Reference](#api-reference)
7. [Frontend Component Architecture](#frontend-component-architecture)
8. [Adding Support for New Bank Formats](#adding-support-for-new-bank-formats)
9. [Security, Data Encryption & Privacy](#security-data-encryption--privacy)

---

## Overview & Value Proposition

The **Budget Analyzer** is a multi-bank personal finance engine built for Indian bank statements and transaction ledgers. It converts raw PDF, CSV, and Excel statements into actionable cash flow intelligence without requiring open banking credentials or screen scraping.

### Core Capabilities:
- **Multi-Bank Ingestion**: Native auto-detection and parsing for HDFC, ICICI, SBI, Axis, Kotak, IndusInd, PNB, and standard CSV formats.
- **Multi-Account Aggregation**: View single accounts in isolation or all accounts combined in a unified "Overall" master ledger.
- **50 / 30 / 20 Budget Health Evaluation**: Real-time adherence scoring, bucket cushion calculations, and AI recommendations.
- **Contextual In-Card Filters**: Card-level toggles (debit/credit, payment modes, min amount thresholds, direct category chips) that don't reset the rest of your dashboard.
- **Deep Payee & Merchant Drilldown**: Instant sub-allocation breakdown of any category showing transaction counts, ticket sizes, and ranked merchants.
- **Customizable Rule Engine**: Regex and keyword rules that automatically categorize future uploads.

---

## High-Level Architecture

```mermaid
graph TD
    A[Bank Statement PDF / CSV / XLSX] --> B[Statement Parser & Bank Detector]
    B --> C[Merchant Normalizer]
    C --> D[Categorizer & Rules Engine]
    D --> E[(Encrypted Storage & Session Ledger)]
    E --> F[Analytics Engine - analytics.py]
    F --> G[50/30/20 Health Suite]
    F --> H[Category Spend & Drilldown]
    F --> I[Monthly Velocity & Cash Flows]
    F --> J[Transactions Ledger Tab]
    G --> K[React 18 MUI UI Dashboard]
    H --> K
    I --> K
    J --> K
```

### Data Pipeline Lifecycle:
1. **Upload**: User uploads a statement file via `UploadStatementModal.tsx`.
2. **Extraction**: `parser.py` parses tables, normalizes dates (`YYYY-MM-DD`), splits debit/credit amounts, and extracts descriptions.
3. **Enrichment**: `categorizer.py` matches keywords and custom rules to assign categories and payment modes (`UPI`, `NetBanking`, `Card`, `ATM`, `Cheque`).
4. **Persistence**: `sessions.py` persists encrypted session records in SQLite / Postgres and updates the user's aggregated master ledger.
5. **Analytics**: `analytics.py` executes vectorized pandas aggregations to deliver sub-millisecond KPI computations.

---

## Bank Statement Ingestion Pipeline

### Parser Engine (`backend/domains/budget/parser.py`)
The parser handles differences in statement formats across Indian financial institutions:
- **Password Protection**: Supports encrypted PDFs (e.g. DOB, PAN, Account number combinations).
- **Format Normalization**: Standardizes multi-column schemas into a unified transaction schema:
  - `date`: Transaction posting date (`YYYY-MM-DD`).
  - `narration`: Cleaned bank transaction description.
  - `merchant`: Extracted merchant/payee entity name.
  - `amount`: Absolute numeric transaction value.
  - `txn_type`: `debit` or `credit`.
  - `category`: Primary budget category.
  - `payment_mode`: Payment channel (`UPI`, `NetBanking`, `Card`, `ATM`, `Cheque`, etc.).
  - `balance`: Post-transaction balance (if provided).

### Supported Banks (`backend/domains/budget/bank_config.json`)
- **HDFC Bank**: Savings & Current Account statements.
- **ICICI Bank**: Detailed transaction ledgers & Credit Card statements.
- **State Bank of India (SBI)**: Standard savings passbooks & e-statements.
- **Axis Bank**: Multi-column monthly statements.
- **Kotak Mahindra Bank**: NetBanking exports & PDF statements.
- **IndusInd & PNB**: Tabular statements.
- **Generic CSV**: User-defined CSV/XLSX ledgers.

---

## Computational Engines & Financial Intelligence

### 1. 50 / 30 / 20 Budget Health Evaluation Suite
Implements the macro-financial framework:
- **Needs ($\le 50\%$)**: Fixed living obligations (Rent, Utilities, Groceries, EMI, Insurance, Healthcare, Education).
- **Wants ($\le 30\%$)**: Discretionary lifestyle spending (Dining, Shopping, Entertainment, Travel, Electronics, Hobbies).
- **Investments / Savings ($\ge 20\%$)**: Wealth generation & debt payoff (Mutual Funds, Equity, SIP, PPF, FD, RD, Gold, Crypto).

#### Health Scoring Algorithm:
$$\text{Health Score} = \max\left(0, \min\left(100, 100 - (\text{Needs Penalty} \times 1.2) - (\text{Wants Penalty} \times 1.0) - (\text{Invest Gap} \times 1.5)\right)\right)$$
- **Score $\ge 80$**: 🟢 *Excellent* (Prudent financial allocation)
- **Score $65 - 79$**: 🟡 *Good* (Balanced with slight lifestyle drift)
- **Score $50 - 64$**: 🟠 *Moderate* (Wants or fixed costs exceeding baseline)
- **Score $< 50$**: 🔴 *Needs Attention* (Under-investing or critical overspending)

#### Real-Time Bucket Metrics:
- **Actual ₹ Spend & \% Allocation**
- **Target Budget Thresholds**
- **Cushion vs Over-Budget Status**
- **AI-Powered Recommended Actions**: Specific ₹ amounts to adjust to reach the 20% investment baseline.

---

### 2. Category Spend Analytics & Payee Drilldown
- **Dynamic Category Chips**: Populates direct category badges based on transaction data with live spend totals (`Uncategorized • ₹12.3L`, `Shopping • ₹45.2k`).
- **Debits (Outflows) vs Credits (Inflows)**: Dual-mode toggle.
- **Deep Drilldown**: Clicking any category transitions the card into a deep drilldown mode with:
  - **Category Volume & Average Ticket Size**
  - **Payee / Merchant Donut Chart**
  - **Ranked Merchant Breakdown with Progress Bars**

---

### 3. Cash Flow Velocity, Burn Rate & Liquidity Projections
- **Net Savings Rate**: $(\text{Inflows} - \text{Outflows}) / \text{Inflows} \times 100$.
- **Monthly Velocity**: Side-by-side debit vs credit bar charts over time.
- **Cash Flow Balance Trend**: Cumulative liquid balance progression line chart.
- **Burn Rate**: Average daily outflow and projected runway under existing cash balances.
- **Biggest Spending Shift**: Detects highest month-over-month category expansion.

---

### 4. Rule-Based Categorization Engine (`backend/domains/budget/categorizer.py`, `rules_safety.py`)
- **Pattern Matching**: Evaluates user-defined rules in priority order.
- **Regex & Keyword Support**: Matches merchant names and raw narration text.
- **Batch Re-Categorization**: Updates category tags across past and future transactions.

---

## Multi-Level Dynamic Filtering System

The Budget Analyzer uses **Contextual In-Card Filters** to eliminate global clutter:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🌍 Global Filter Bar: Session (All vs Account) • Bank • Date Range          │
└─────────────────────────────────────────────────────────────────────────────┘
      │
      ├─── 💳 Cash Flow Trends Card
      │     └─ Local: [3M | 6M | 1Y | All] Range Toggle
      │
      ├─── 🏷️ Category Spend Analytics Card
      │     └─ Local: [Debits / Credits] • Min Amount Filter • Direct Category Chips
      │
      ├─── 🏪 Top Merchants Card
      │     └─ Local: [Outflows / Inflows] • Search Merchant • Sort By [₹ / Count]
      │
      └─── 📋 Transactions Tab
            └─ Local: Multi-column Filter Bar • Category Tagger • Full-text Search
```

---

## API Reference

Generated from the mounted routes. The live OpenAPI schema at `GET /docs` is the
source of truth — this table exists so the shape is visible without booting the app.

An earlier version of this section documented `/api/budget/upload`,
`/api/budget/overview`, `/api/budget/category_breakdown` and `/api/budget/categorize`
with invented response bodies. None of those paths have ever existed; the prefix is
`/budget`, and the analytics endpoints are session-scoped. Response shapes are
deliberately not reproduced here — they drifted precisely because they were copied
by hand.

Every endpoint requires an authenticated caller. Ownership is enforced inside
`domains/budget/sessions.py`, so a session id belonging to someone else answers 404,
never a row.

### `/budget/accounts` — Bank & card accounts

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/budget/accounts` | Every account seen across the user's statements, with balances and card utilisation. |
| `PUT` | `/budget/accounts/{account_key}` | Write the fields a statement cannot supply. |

### `/budget/analytics` — Overview, categories, transactions

| Method | Path | Purpose |
|---|---|---|
| `PUT` | `/budget/analytics/transactions/update` |  |
| `GET` | `/budget/analytics/{session_id}/categories` |  |
| `GET` | `/budget/analytics/{session_id}/overview` | The dashboard's headline aggregation, memoized on the frame and the filter set. |
| `GET` | `/budget/analytics/{session_id}/transactions` | Filtered transactions, paginated. |

### `/budget/insights` — Transfers, recurring, forecast, anomalies, envelopes

| Method | Path | Purpose |
|---|---|---|
| `PUT` | `/budget/insights/envelopes` | Set or clear one category's monthly cap. |
| `PUT` | `/budget/insights/merchants/alias` | Remember a merchant rename, so the user only corrects it once. |
| `POST` | `/budget/insights/transfers/flag` | Override the pairing heuristic for one transaction. |
| `GET` | `/budget/insights/{session_id}/anomalies` | Duplicate charges, category spikes and unusually large first-time merchants. |
| `GET` | `/budget/insights/{session_id}/coverage` | Which months each account has statements for, and which are missing. |
| `GET` | `/budget/insights/{session_id}/envelopes` | Spend against each monthly category cap, with a pace verdict. |
| `GET` | `/budget/insights/{session_id}/forecast` | Month-end projection and a daily safe-to-spend figure. |
| `GET` | `/budget/insights/{session_id}/reconciliation` | Whether each statement's printed balances agree with its own transactions. |
| `GET` | `/budget/insights/{session_id}/recurring` | Subscriptions and standing charges, with price changes and annualised cost. |
| `GET` | `/budget/insights/{session_id}/sankey` | Nodes and links for the income -> nature -> category flow diagram. |
| `GET` | `/budget/insights/{session_id}/transfers` | Movements between the user's own accounts, netted out of income and expense. |

### `/budget/portfolio` — Upload & sessions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/budget/portfolio/sessions` | List the caller's budget uploads. |
| `DELETE` | `/budget/portfolio/sessions/{session_id}` | Delete one budget upload. 404s if it is not the caller's. |
| `POST` | `/budget/portfolio/upload` | Parse a bank or credit-card statement (CSV / XLS / XLSX) into a budget session. |

### `/budget/rules` — Categorisation rules

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/budget/rules` |  |
| `POST` | `/budget/rules` |  |
| `POST` | `/budget/rules/apply-all` |  |
| `GET` | `/budget/rules/match-types` | The match types the UI may offer, so it cannot drift from what the server accepts. |
| `POST` | `/budget/rules/test` | Check a pattern against one description without storing it. |
| `DELETE` | `/budget/rules/{rule_id}` |  |

`session_id` accepts a specific upload or the literal `overall`, which aggregates
every statement the user owns with overlapping periods merged.

---

## Frontend Component Architecture

All Budget components reside in `frontend/src/domains/budget/`:

| Component | Path | Responsibility |
|---|---|---|
| **BudgetDashboard** | `components/BudgetDashboard.tsx` | Master view: KPIs, charts, tab routing, and the shared filter state. |
| **BudgetHealth503020Card** | `components/BudgetHealth503020Card.tsx` | Health score, three bucket cards, macro allocation strip, recommendations. |
| **TransactionsTab** | `components/TransactionsTab.tsx` | Transaction grid, client-paginated at 50 rows, with inline category tagger and CSV export. |
| **AccountsTab** | `components/AccountsTab.tsx` | Per-account balances, card utilisation, editable account metadata. |
| **InsightsTab** | `components/InsightsTab.tsx` | Recurring charges, anomalies, envelope budgets, coverage gaps. |
| **MoneyFlowCard** | `components/MoneyFlowCard.tsx` | Income → nature → category Sankey. |
| **TransfersExcludedCard** | `components/TransfersExcludedCard.tsx` | Why the totals are lower than the raw statement sum; lists the matched pairs. |
| **RulesTab** | `components/RulesTab.tsx` | Auto-categorization rule editor (create, edit, delete, priority reorder). |
| **UploadStatementModal** | `components/UploadStatementModal.tsx` | Multi-bank file uploader with password unlock support. |
| **BudgetSessionsModal** | `components/BudgetSessionsModal.tsx` | Account management modal for switching and deleting uploaded statements. |
| **useBudget** | `hooks/useBudget.ts` | Query hooks, cache keys, and invalidation for every budget endpoint. |
| **types** | `types.ts` | Response contracts for the budget API surface. |

Tabs 2–4 mount only when selected, and each domain resolves to its own lazily
fetched chunk (`Dashboard.tsx`).

---

## Adding Support for New Bank Formats

To add support for a new bank or custom statement schema:
1. Open `backend/domains/budget/bank_config.json`.
2. Add a new configuration entry matching your bank's table header signatures:
```json
{
  "bank_name": "NewBank",
  "signatures": ["Txn Date", "Value Date", "Description", "Ref No", "Debit", "Credit", "Balance"],
  "date_col": "Txn Date",
  "date_formats": ["%d/%m/%Y", "%d-%m-%Y"],
  "narration_col": "Description",
  "debit_col": "Debit",
  "credit_col": "Credit",
  "balance_col": "Balance"
}
```
3. `parser.py` will automatically match uploaded files against the new configuration signature.

---

## Security, Data Encryption & Privacy

- **Zero Third-Party Scraping**: Statements are parsed locally on your server without sharing credentials with aggregation aggregators.
- **Envelope Encryption**: Persisted session records are encrypted at rest using AES-GCM via `backend/shared/storage.py`.
- **Tenant Isolation**: Every database query verifies `user_id` ownership using verified Supabase JWT claims.
- **Session Privacy**: Users can permanently purge individual statements or their entire budget database at any time.
