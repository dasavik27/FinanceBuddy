# Exchange-First Stock Data Architecture

## Problem Statement

All valuation tiles (P/E, EPS, Market Cap, VWAP, Beta, Dividend Yield) currently depend
solely on `yfinance.Ticker.info` (`.NS` ticker). This endpoint returns HTTP 404 for many
Indian tickers (TATAMOTORS, ZOMATO, LTIM) and is rate-limited unpredictably, causing
blank `-` tiles in the Key Statistics & Valuation section.

**Root cause confirmed via live diagnostic:**
- `TATAMOTORS.NS` → Yahoo 404 (broken) | `TATAMOTORS.BO` → 164 info keys (works!)
- `LTIM.NS` → Yahoo 404 (broken)       | `LTIM.BO` → 164 info keys (works!)
- `ZOMATO.NS` → Yahoo partial           | `ZOMATO.BO` → 153 info keys (works!)

---

## Approved Sourcing Matrix

| UI Metric | Primary Source | Fallback Source |
|:---|:---|:---|
| Real-Time Price (LTP) | Yahoo Finance `.NS` | Yahoo Finance `.BO` cascade |
| Previous Close & Day Range | Yahoo Finance `.NS` | Yahoo Finance `.BO` cascade |
| Market Cap (Rs Cr) | Yahoo Finance `.NS` | Yahoo Finance `.BO` cascade |
| P/E Ratio | Yahoo Finance `.NS` | Yahoo Finance `.BO` / Derived (Price / TTM EPS) |
| EPS (TTM) | Yahoo Finance `.NS` | Yahoo Finance `.BO` / Sum of last 4 quarters |
| P/B Ratio | Yahoo Finance `priceToBook` | Derived (Market Cap / Stockholders Equity) |
| **Dividend Yield (%)** | **NSE Corporate Actions (Official Filings)** | Yahoo Finance `dividendYield` |
| **VWAP** | **BSE Official API** (`StockTrading.WAP`) | Self-Calculated (Sum P x V / Sum V, trailing 30 sessions) |
| **Beta** | **Self-Calculated Math Engine** (covariance vs Nifty 50 `^NSEI`) | Yahoo Finance `beta` |
| Interactive Charts (1D-5Y) | Yahoo Finance `yf.download` OHLCV | BSE Historical Graph API |
| Corporate Actions (Splits/Dividends) | NSE India Disclosures `corporateActions` | Yahoo Dividends |
| Quarterly Financial Statements | Yahoo Finance Statements | NSE `integrated-filing-results` |

---

## Architecture: Pragmatic Hybrid

Two approaches were evaluated. **Pragmatic Hybrid** was selected:

```
Approach                              Complexity   Reliability   Benefit
------------------------------------------------------------------------
Full BSE-First (every metric)         High         Medium        High
                                                   (BSE API undocumented)
Yahoo .BO Cascade + BSE VWAP only     Low          High          High
+ Math Beta  <-- SELECTED
```

---

## Implementation Plan

### Change 1 — Yahoo Finance `.NS → .BO` Auto-Cascade

**File**: `backend/domains/equity/stock_analyzer.py`

```python
def _fetch_yf_info(ticker_ns: str) -> tuple[dict, str]:
    """Try .NS first; if info is empty or missing, fall back to .BO."""
    import yfinance as yf
    for suffix in (".NS", ".BO"):
        sym = ticker_ns.replace(".NS", suffix)
        try:
            info = yf.Ticker(sym).info or {}
            if len(info) > 10:           # real payload, not an error stub
                return info, sym
        except Exception:
            continue
    return {}, ticker_ns
```

**Why this fixes most blank tiles**: TATAMOTORS.BO, LTIM.BO, ZOMATO.BO all return 150+
key payloads with P/E, EPS, Market Cap, Beta, Dividend Yield fields.

---

### Change 2 — BSE Official API for VWAP Only

**File**: `backend/domains/equity/bse_client.py` (new, lightweight)

BSE is the only source that publishes intraday VWAP (`WAP` field).
Yahoo Finance does not expose VWAP at all.

```python
class BSEClient:
    BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
    _scrip_map: dict[str, str] = {}   # {scrip_id (NSE symbol): bse_scrip_code}

    def resolve_scrip_code(self, symbol: str) -> str | None:
        """NSE symbol -> BSE scrip code via lazy-loaded master list."""
        ...

    def get_vwap(self, symbol: str) -> float | None:
        """Returns WAP (Volume Weighted Avg Price) from BSE StockTrading endpoint."""
        code = self.resolve_scrip_code(symbol)
        if not code:
            return None
        url = f"{self.BSE_API}/StockTrading/w?flag=&scripcode={code}"
        r = requests.get(url, headers=BSE_HEADERS, timeout=5)
        if r.status_code == 200:
            raw = r.json().get("WAP", "").replace(",", "")
            return float(raw) if raw else None
        return None

bse_client = BSEClient()
```

Scope deliberately limited to VWAP only — avoids depending on undocumented BSE endpoints
for fields Yahoo already covers via `.BO` cascade.

---

### Change 3 — Math Engine as Primary for Beta

**File**: `backend/domains/equity/stock_analyzer.py`

```python
def _compute_beta(stock_hist: pd.DataFrame) -> float | None:
    """
    Compute 250-day beta of stock vs Nifty 50 from daily log returns.
    Primary source for Beta — Yahoo's beta is the fallback when < 60 trading
    days of data exist for the stock.
    """
    nifty = _nifty_close_series()       # already cached process-wide
    if len(nifty) < 60 or stock_hist.empty:
        return None
    stock_returns = stock_hist["Close"].pct_change().dropna()
    nifty_series  = pd.Series(nifty).pct_change().dropna()
    aligned = pd.concat([stock_returns, nifty_series], axis=1).dropna()
    if len(aligned) < 60:
        return None
    cov = aligned.cov().iloc[0, 1]
    var = aligned.iloc[:, 1].var()
    return round(cov / var, 3) if var else None
```

Result merge: `beta = math_beta or _f("beta")` (math wins, Yahoo is the fallback).

---

### Change 4 — NSE Dividend Yield as Primary

**File**: `backend/domains/equity/stock_analyzer.py`

```python
def _nse_dividend_yield(actions: list[dict], current_price: float) -> float | None:
    """
    Sum all cash dividend amounts paid in the trailing 12 months from NSE
    corporate actions. Divide by current price to get yield percentage.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    total_div = 0.0
    for a in actions:
        if a.get("purpose", "").upper().startswith("DIV"):
            try:
                amount = float(str(a.get("amount", "0")).replace(",", ""))
                ex_date = pd.to_datetime(a.get("exDate"), errors="coerce")
                if ex_date and ex_date.tz_localize("UTC") >= cutoff:
                    total_div += amount
            except Exception:
                continue
    if total_div > 0 and current_price > 0:
        return round((total_div / current_price) * 100, 2)
    return None
```

Result merge: `dividend_yield = nse_yield or _dividend_yield_pct(info)`.

---

### Change 5 — Smart Negative Cache

**File**: `backend/domains/equity/stock_analyzer.py`

```python
is_degraded = (
    result["pe_ratio"] is None
    and result["market_cap_cr"] is None
    and result["eps"] is None
)
cache_ttl = 30 if is_degraded else 3600  # 30s retry vs 60min normal
```

---

## Files Changed

| File | Action | Scope |
|:---|:---|:---|
| `backend/domains/equity/stock_analyzer.py` | Modify | .NS-.BO cascade, Math Beta, NSE Div Yield, Negative Cache |
| `backend/domains/equity/bse_client.py` | New | Lightweight BSE client for VWAP only |
| `backend/domains/equity/nse_corporate.py` | Read only | `corporate_actions()` already fetches dividend data |

No frontend changes required. The output JSON contract remains identical.

---

## Verification

```bash
cd backend
./venv/bin/python -c "
from domains.equity.stock_analyzer import analyze_stock
for sym in ['RELIANCE', 'TCS', 'TATAMOTORS', 'ZOMATO', 'LTIM', 'SWIGGY']:
    r = analyze_stock(sym)
    ok = any(r.get(f) is not None for f in ['pe_ratio','market_cap_cr','eps'])
    print(sym,
          '| source:', r['source'],
          '| pe:', r['pe_ratio'],
          '| eps:', r['eps'],
          '| vwap:', r['vwap'],
          '| beta:', r['beta'],
          '| yield:', r['dividend_yield'],
          '| OK:', ok)
"
```

**Success criteria**: All 6 symbols show `OK: True`.
