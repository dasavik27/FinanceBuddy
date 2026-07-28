@echo off
REM Finance Buddy - Complete Robust Setup Script (Windows)
REM Installs all dependencies with progress tracking and error handling

setlocal enabledelayedexpansion

echo.
echo ====== Finance Buddy - Complete Setup ======
echo.

REM Step 1: Create Python virtual environment
echo [1/5] Creating Python virtual environment...
python -m venv venv_finance
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    exit /b 1
)
echo ✅ Virtual environment created

REM Step 2: Upgrade pip
echo.
echo [2/5] Upgrading pip...
call venv_finance\Scripts\pip.exe install --upgrade pip setuptools wheel --quiet
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip
    exit /b 1
)
echo ✅ Pip upgraded

REM Step 3: Install backend dependencies in groups
echo.
echo [3/5] Installing backend dependencies (this may take 5-15 minutes)...
cd backend

REM Core packages
echo Installing core packages...
call ..\venv_finance\Scripts\pip.exe install fastapi uvicorn python-multipart pydantic requests --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some core packages failed

REM Data processing packages
echo Installing data processing packages...
call ..\venv_finance\Scripts\pip.exe install pandas numpy pyxirr yfinance --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some data packages failed

REM File parsing packages
echo Installing file parsing packages...
call ..\venv_finance\Scripts\pip.exe install casparser pdfplumber pypdf openpyxl xlrd --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some file packages failed

REM NSE market data packages
echo Installing market data packages...
call ..\venv_finance\Scripts\pip.exe install nsepython nselib --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some market packages failed

REM Text processing packages
echo Installing text processing packages...
call ..\venv_finance\Scripts\pip.exe install fuzzywuzzy python-Levenshtein python-dateutil --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some text packages failed

REM Advanced data packages
echo Installing advanced data packages...
call ..\venv_finance\Scripts\pip.exe install pyarrow fastparquet camelot-py --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some advanced packages failed

REM Vision/processing packages
echo Installing processing packages...
call ..\venv_finance\Scripts\pip.exe install opencv-python-headless pytest --quiet --no-cache-dir
if errorlevel 1 echo WARNING: Some processing packages failed

cd ..
echo ✅ Backend dependencies installed

REM Step 4: Install frontend dependencies
echo.
echo [4/5] Installing frontend dependencies...
cd frontend
call npm install --silent
if errorlevel 1 (
    echo WARNING: Some npm packages may have failed
)
cd ..
echo ✅ Frontend dependencies installed

REM Step 5: Verify installation
echo.
echo [5/5] Verifying installation...
call venv_finance\Scripts\python.exe -c "import fastapi, uvicorn, pandas, pyxirr, casparser; print('✅ All critical packages installed')"
if errorlevel 1 (
    echo WARNING: Some packages may be missing
    echo Please check the output above for any errors
)

echo.
echo ====== ✅ Setup Complete! ======
echo.
echo To start both servers (frontend + backend):
echo   npm run dev:all
echo.
echo Frontend:  http://localhost:5173
echo Backend:   http://localhost:8000
echo API Docs:  http://localhost:8000/docs
echo.
pause
