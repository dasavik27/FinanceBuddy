# FolioIQ v6.0 — Setup Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        BROWSER                              │
│  React 18 + Vite · MUI v5 · Recharts · Framer Motion       │
│  Zustand (state) · TanStack Query (server state)            │
│                  localhost:5173                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / JSON  (Vite proxy)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                         │
│                     localhost:8000                          │
│                                                             │
│  /api/portfolio/parse       ← PDF upload + parse            │
│  /api/portfolio/{id}/summary                                │
│  /api/portfolio/{id}/overview                               │
│  /api/portfolio/{id}/holdings                               │
│  /api/portfolio/{id}/allocation                             │
│  /api/portfolio/{id}/performance                            │
│  /api/portfolio/{id}/tax                                    │
│  /api/portfolio/{id}/insights                               │
│  /api/portfolio/{id}/transactions                           │
│  /api/benchmark/search                                      │
│  /api/benchmark/history                                     │
│  /api/sip/projection                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ Python function calls
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               logic_adapter.py (thin shim)                  │
│  Stubs out streamlit · imports logic.py cleanly             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     logic.py  (UNCHANGED)                   │
│  parse_cas · compute_xirr · fetch_benchmark                 │
│  compute_rolling_returns · estimate_expense_drag            │
│  sip_consistency_score · stepup_sip_projection · …         │
└─────────────────────────────────────────────────────────────┘
```

---

## Final Folder Structure

```
folioiq/
├── backend/
│   ├── main.py                  ← FastAPI app + CORS
│   ├── logic_adapter.py         ← Streamlit shim + re-exports
│   ├── logic.py                 ← YOUR ORIGINAL FILE (copy here)
│   ├── requirements.txt
│   └── routers/
│       ├── __init__.py
│       ├── portfolio.py         ← All portfolio endpoints
│       ├── benchmark.py         ← Benchmark search + history
│       └── sip.py               ← SIP calculator
│
└── frontend/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx             ← React entry point
        ├── App.tsx              ← Router shell
        ├── api/
        │   ├── client.ts        ← Axios API client + types
        │   └── fmt.ts           ← Number/string formatters
        ├── store/
        │   └── appStore.ts      ← Zustand global state
        ├── hooks/
        │   └── useData.ts       ← TanStack Query hooks
        ├── theme/
        │   └── theme.ts         ← MUI MD3 Finance Noir theme
        └── components/
            ├── Landing.tsx      ← Upload / onboarding page
            ├── Layout.tsx       ← Dark sidebar + topbar
            ├── Dashboard.tsx    ← Tab router
            ├── ui.tsx           ← Shared atoms (MetricCard, etc.)
            └── tabs/
                ├── OverviewTab.tsx
                ├── PerformanceTab.tsx
                ├── HoldingsTab.tsx
                ├── CompareTab.tsx
                ├── TaxTab.tsx
                ├── InsightsTab.tsx
                └── SipTab.tsx
```

---

## Prerequisites

| Tool       | Version  | Install                          |
|------------|----------|----------------------------------|
| Python     | 3.10+    | python.org                       |
| Node.js    | 18+      | nodejs.org                       |
| npm        | 9+       | bundled with Node                |

---

## Step 1 — Copy your logic.py

```bash
cp /path/to/your/original/logic.py  folioiq/backend/logic.py
```

> `logic.py` is **NOT modified at all**. `logic_adapter.py` monkey-patches
> `streamlit.cache_data` before importing it, so all your existing functions
> work identically inside FastAPI.

---

## Step 2 — Backend setup

```bash
cd folioiq/backend

# Create virtual environment
python -m venv venv

# Activate
# macOS / Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Verify at: http://localhost:8000/api/health  
Interactive docs at: http://localhost:8000/docs

---

## Step 3 — Frontend setup

```bash
# Open a NEW terminal (keep backend running)
cd folioiq/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Open: **http://localhost:5173**

---

## Step 4 — Using the app

1. Get a **Detailed CAS** PDF from:
   - https://www.cams.com (Mailback → Detailed CAS)
   - https://www.kfintech.com
   - https://www.mfcentral.com

2. On the FolioIQ landing page:
   - Drag & drop your CAS PDF
   - Enter your **PAN in uppercase** as the password (e.g. `ABCDE1234F`)
   - Click **Analyze Portfolio**

3. Navigate using the **top tabs** or **sidebar navigation**.

---

## Production Build

```bash
# Build frontend
cd folioiq/frontend
npm run build
# Output: folioiq/frontend/dist/

# Run backend in production mode
cd folioiq/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

To serve the React build from FastAPI (optional — avoids CORS):

```python
# Add to backend/main.py
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="static")
```

Then add to requirements.txt:
```
aiofiles==23.2.1
```

---

## Environment Variables (optional)

Create `backend/.env`:

```env
# Allow additional origins
CORS_ORIGINS=http://localhost:5173,https://yourdomain.com

# Session timeout in seconds (default: no expiry within process)
SESSION_TTL=3600
```

---

## Common Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: casparser` | Run `pip install casparser` in the venv |
| `CORS error` in browser | Make sure backend is running on port 8000 and frontend on 5173 |
| `422 Unprocessable Entity` | Wrong PAN password or non-Detailed CAS file |
| Fonts not loading | Check internet connection — fonts load from Google Fonts |
| `npm install` fails | Ensure Node 18+: `node --version` |
| Holdings empty after parse | Use a **Detailed** CAS, not a simple statement |

---

## Tech Stack Summary

### Backend
| Library       | Purpose                              |
|---------------|--------------------------------------|
| FastAPI       | REST API framework                   |
| Uvicorn       | ASGI server                          |
| casparser     | CAS PDF parsing (your original dep)  |
| pandas        | DataFrame operations                 |
| pyxirr        | XIRR calculation                     |
| yfinance      | Benchmark price history              |
| pydantic v2   | Request/response validation          |

### Frontend
| Library             | Purpose                              |
|---------------------|--------------------------------------|
| React 18            | UI framework                         |
| Vite                | Build tool + dev server              |
| TypeScript          | Type safety                          |
| MUI v5              | Material Design component library    |
| Recharts            | Charts (Area, Bar, Line, Radar)      |
| Framer Motion       | Page + card animations               |
| TanStack Query v5   | Server state, caching, loading       |
| Zustand             | Global client state (filters, session)|
| React Router v6     | Tab + page routing                   |
| React Dropzone      | File upload UX                       |
| Axios               | HTTP client                          |

---

## Zero Data Retention Architecture

- The CAS PDF is sent to FastAPI via `multipart/form-data`
- It is parsed in memory using `casparser`
- The resulting DataFrames are stored in a **Python dict** keyed by `session_id` (UUID)
- **Nothing is written to disk, database, or logs**
- When the Python process restarts, all sessions are cleared
- The frontend stores only the `session_id` in Zustand (in-memory, not localStorage)
- Closing the browser tab clears the frontend state entirely

---

*FolioIQ v6.0 · SEBI CSCRF 2025 · Not SEBI registered · Not financial advice*
