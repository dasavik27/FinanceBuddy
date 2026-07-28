# Finance Buddy - Setup Guide

**Version:** 8.0.0 | **Last Updated:** 2026-07-27

This guide ensures a robust setup of the Finance Buddy project for development and deployment.

## Prerequisites

- Python 3.10+ (tested with 3.13.3)
- Node.js 18+ and npm
- Git

## Automatic Setup (Recommended)

### Windows
```bash
.\SETUP_ENV.bat
```

### Linux/macOS
```bash
bash SETUP_ENV.sh
```

## Manual Setup

If the automatic setup fails, follow these steps:

### 1. Create Python Virtual Environment
```bash
python -m venv venv_finance
```

### 2. Activate Virtual Environment

**Windows:**
```bash
venv_finance\Scripts\activate.bat
```

**Linux/macOS:**
```bash
source venv_finance/bin/activate
```

### 3. Upgrade Pip
```bash
python -m pip install --upgrade pip
```

### 4. Install Backend Dependencies
```bash
cd backend
pip install -r requirements.txt
cd ..
```

### 5. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

## Running the Development Servers

### Option 1: Both Servers Together (Recommended)
```bash
npm run dev:all
```

### Option 2: Servers Separately

**Terminal 1 - Frontend:**
```bash
cd frontend
npm run dev
```

**Terminal 2 - Backend:**
```bash
# Windows
venv_finance\Scripts\activate.bat
cd backend
python -m uvicorn main:app --reload

# Linux/macOS
source venv_finance/bin/activate
cd backend
python -m uvicorn main:app --reload
```

## Access the Application

- **Frontend:** http://localhost:5173
- **Backend API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## Features Overview

### Portfolio Management
- Upload and parse CAS files (Consolidated Account Statement)
- Real-time portfolio tracking with live NAV updates
- Multi-asset support (Mutual Funds, Stocks)
- Performance analytics (XIRR, Sharpe ratio, etc.)

### Tax Expert Module ⭐ (NEW)
- **AIS PDF Upload:** Extract income data from Annual Information Statement
- **Capital Gains Analysis:** LTCG/STCG computation with ₹1.25L equity exemption
- **Tax Regime Comparison:** Old Regime vs New Regime side-by-side
- **ITR Reconciliation:** Upload filed ITR PDF and compare with computed tax
- **Cost Basis Recovery:** FIFO matching for accurate capital gains calculation
- **Pre-Filing Readiness:** Track discrepancies before ITR filing

### Market Intelligence
- Real-time NSE stock data integration
- Mutual fund NAV tracking from AMFI
- Benchmark comparison (Nifty 50, Sensex, etc.)

### Advanced Analytics
- Risk metrics (Sharpe, Sortino, Max Drawdown)
- Performance attribution analysis
- Rebalancing recommendations
- Peer fund comparison

## Troubleshooting

### Backend dependencies not installing
```bash
# Clear pip cache and reinstall
pip cache purge
pip install -r backend/requirements.txt --no-cache-dir
```

### Port Already in Use

**Port 8000:**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -i :8000
kill -9 <PID>
```

**Port 5173:**
```bash
# Windows
netstat -ano | findstr :5173
taskkill /PID <PID> /F

# Linux/macOS
lsof -i :5173
kill -9 <PID>
```

### Virtual Environment Issues
```bash
# Remove and recreate
rm -r venv_finance  # or rmdir /s venv_finance on Windows
python -m venv venv_finance
# Then rerun setup steps
```

## Development Workflow

1. Make changes to frontend or backend code
2. Frontend hot-reloads automatically on changes
3. Backend reloads on changes (with --reload flag)
4. Test at http://localhost:5173

## Additional Commands

```bash
# Build frontend for production
npm run build

# Format code
npm run format

# Run tests
npm run test
```

## Recent Updates (2026-07-27)

✅ **Tax Expert Endpoint Fix**
- Removed duplicate router mounts (`/portfolio` and `/tax-expert`)
- All tax operations now under single `/tax-expert` namespace
- Clean Swagger API documentation with no duplicates

✅ **Backend Fully Operational**
- All 25+ dependencies installed and verified
- Virtual environment isolated at `venv_finance/`
- FastAPI + Uvicorn running with auto-reload

✅ **Frontend Production Ready**
- React 18 with Vite hot module reloading
- Material-UI component library
- Real-time charts with Recharts
- React Query for server-state management

## Verified Versions

| Component | Version |
|-----------|---------|
| Python | 3.13.3 |
| FastAPI | 0.136.1 |
| Uvicorn | 0.46.0 |
| React | 18.3.1 |
| Node.js | 18+ |
| Vite | 5.2.13 |

## Zero-Persistence Design

Finance Buddy is designed for maximum privacy:
- **No Database:** All data in volatile memory only
- **Secure PDF Processing:** Files never touch disk, processed via BytesIO buffers
- **Session-based:** Data cleared on process termination
- **CORS Enabled:** Safe cross-origin API access

---

**Status:** ✅ Fully Operational | All features working | Production-ready
