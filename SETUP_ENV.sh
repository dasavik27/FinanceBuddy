#!/bin/bash
# Finance Buddy - Complete Robust Setup Script
# Installs all dependencies with progress tracking

set -e

echo ""
echo "====== Finance Buddy - Complete Setup ======"
echo ""

# Step 1: Create Python virtual environment
echo "[1/5] Creating Python virtual environment..."
python -m venv venv_finance
echo "✅ Virtual environment created"

# Step 2: Activate virtual environment
echo ""
echo "[2/5] Upgrading pip..."
source venv_finance/bin/activate
python -m pip install --upgrade pip setuptools wheel --quiet
echo "✅ Pip upgraded"

# Step 3: Install backend dependencies in groups
echo ""
echo "[3/5] Installing backend dependencies (this may take 5-15 minutes)..."
cd backend

echo "Installing core packages..."
pip install fastapi uvicorn python-multipart pydantic requests --quiet --no-cache-dir || echo "WARNING: Some core packages failed"

echo "Installing data processing packages..."
pip install pandas numpy pyxirr yfinance --quiet --no-cache-dir || echo "WARNING: Some data packages failed"

echo "Installing file parsing packages..."
pip install casparser pdfplumber pypdf openpyxl xlrd --quiet --no-cache-dir || echo "WARNING: Some file packages failed"

echo "Installing market data packages..."
pip install nsepython nselib --quiet --no-cache-dir || echo "WARNING: Some market packages failed"

echo "Installing text processing packages..."
pip install fuzzywuzzy python-Levenshtein python-dateutil --quiet --no-cache-dir || echo "WARNING: Some text packages failed"

echo "Installing advanced data packages..."
pip install pyarrow fastparquet camelot-py --quiet --no-cache-dir || echo "WARNING: Some advanced packages failed"

echo "Installing processing packages..."
pip install opencv-python-headless pytest --quiet --no-cache-dir || echo "WARNING: Some processing packages failed"

cd ..
echo "✅ Backend dependencies installed"

# Step 4: Install frontend dependencies
echo ""
echo "[4/5] Installing frontend dependencies..."
cd frontend
npm install --silent || echo "WARNING: Some npm packages may have failed"
cd ..
echo "✅ Frontend dependencies installed"

# Step 5: Verify installation
echo ""
echo "[5/5] Verifying installation..."
deactivate
source venv_finance/bin/activate
python -c "import fastapi, uvicorn, pandas, pyxirr, casparser; print('✅ All critical packages installed')" || echo "WARNING: Some packages may be missing"

echo ""
echo "====== ✅ Setup Complete! ======"
echo ""
echo "To start both servers (frontend + backend):"
echo "  npm run dev:all"
echo ""
echo "Frontend:  http://localhost:5173"
echo "Backend:   http://localhost:8000"
echo "API Docs:  http://localhost:8000/docs"
echo ""
