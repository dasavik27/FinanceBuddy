# 🚀 Finance Buddy Installation: Deploying AlphaTrack Pro (v8.1)

Finance Buddy is an institutional-grade Mutual Fund Intelligence platform. This guide walks you through the deployment of the analytical backend and the high-fidelity frontend cockpit.

---

## 🏗️ Technical Architecture
Finance Buddy is structured into two primary high-performance modules:

```
Finance Buddy/
├── backend/            ← FastAPI Analytical Engine (RAM-Backed & Live Data Gateway)
└── frontend/           ← React 18 "Pro Cockpit" (Vite / MUI v5 / Recharts)
```

---

## 🐍 Phase 1: Deploying the Analytical Engine
The backend requires **Python 3.10+** and specialized financial arithmetic libraries.

1.  **Environment Initialization**:
    ```bash
    cd backend
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```

2.  **Installing Precision Libraries**:
    ```bash
    # Installs PyXirr (SEC-Compliant) and Casparser (Institutional Grade)
    pip install -r requirements.txt
    ```

3.  **Bootstrapping the Server**:
    ```bash
    # Launches the engine on port 8000 with auto-reload enabled
    uvicorn main:app --reload --port 8000
    ```

Verification: `http://localhost:8000/health` → `{"status":"ok","version":"8.0.0"}`

---

## ⚛️ Phase 2: Launching the Pro Dashboard
The frontend uses **Vite** for near-instant compilation and **React 18** for kinetic UI transitions.

1.  **Installing UI Tokens**:
    ```bash
    cd frontend
    npm install
    ```

2.  **Spinning Up the Cockpit**:
    ```bash
    npm run dev
    ```

The dashboard will be active at: **http://localhost:5173**

---

## 🗺️ 1:1 Tab Routing Alignment
The platform implements strict 1:1 modular routing between frontend UI tabs and backend micro-services:
*   `/overview` ↔ `routers/tabs/overview.py` (Executive Summary & Chart Attribution)
*   `/holdings` ↔ `routers/tabs/holdings.py` (Asset Concentration & Categorization)
*   `/performance` ↔ `routers/tabs/performance.py` (Quantitative Risk & Alpha Audit)
*   `/compare` ↔ `routers/tabs/compare.py` (Head-to-Head Instrument Benchmarking)
*   `/tax-strategy` ↔ `routers/tabs/tax_strategy.py` (FY Harvest & Capital Gains Simulation)
*   `/insights` ↔ `routers/tabs/insights.py` (AI Allocation Drift Diagnostics)
*   `/rebalance` ↔ `routers/tabs/rebalance.py` (Step-by-Step Rebalancing Roadmap)

---

## 📊 Deployment Checklist: First Run
1.  **Obtain Institutional CAS**: Download your **Detailed CAS** (Consolidated Account Statement) from MFCentral or CAMS.
2.  **Upload & Decrypt**: Securely upload your statement. Use your password/PAN to unlock the in-memory parsing stream.
3.  **Real-Time Data Sync**: The platform automatically queries `mfapi.in`, AMFI, and NSE/Yahoo Finance for live NAV curves. You can force an unconditional live sync at any time via the cockpit header.

---

## 🛡️ Zero-Persistence Mandate
Finance Buddy is designed for the highest level of financial privacy:
*   **RAM Isolation**: All data exists in volatile memory only. No database is utilized.
*   **Encrypted Streams**: PDF processing occurs via `io.BytesIO` buffers; raw files never touch the disk.
*   **Session Purge**: Data is permanently cleared upon process termination or session timeout.

---
*Finance Buddy v8.1.0 · Institutional-Grade Analytics · Built for Absolute Privacy*
