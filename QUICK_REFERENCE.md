# FolioIQ Refactored - Quick Reference

## File Structure at a Glance

| File                    | Purpose                   | Key Exports                                                 |
| ----------------------- | ------------------------- | ----------------------------------------------------------- |
| `config.py`             | Constants & configuration | BENCHMARKS, PERIOD_MAP, CATEGORY_COLORS, EXP_RATIOS         |
| `utils/formatting.py`   | Format numbers/text       | fmt_inr(), fmt_percentage(), fmt_decimal()                  |
| `utils/parsers.py`      | Parse CAS PDFs            | parse_cas(), detect_category(), detect_amc()                |
| `utils/calculations.py` | Financial math            | compute_xirr(), compute_benchmark_xirr(), fetch_benchmark() |
| `ui/styles.py`          | Styling & CSS             | apply_theme(), show_alert(), show_badge()                   |
| `ui/components.py`      | UI components             | render_header(), render_holdings_table()                    |
| `app_refactored.py`     | Main app                  | (Orchestrates all modules)                                  |

---

## Common Tasks

### Display a Metric

```python
from utils.formatting import fmt_inr
st.metric("Portfolio Value", fmt_inr(total_value), fmt_inr(gain))
```

### Format Currency

```python
from utils.formatting import fmt_inr, fmt_percentage
value_str = fmt_inr(12500000)  # "₹1,25,00,000"
pct_str = fmt_percentage(12.5)  # "+12.50%"
```

### Parse CAS File

```python
from utils.parsers import parse_cas
df_holdings, df_txns, df_sips, error, is_partial = parse_cas(
    file_bytes=uploaded_file.getvalue(),
    password="PAN"
)
```

### Calculate Portfolio XIRR

```python
from utils.calculations import compute_xirr
xirr_pct = compute_xirr(df_transactions, current_portfolio_value)
```

### Fetch Benchmark Data

```python
from utils.calculations import fetch_benchmark
from config import BENCHMARKS

ticker = BENCHMARKS["Nifty 50"]  # "^NSEI"
bench_series = fetch_benchmark(ticker, period_days=365)
```

### Compare Portfolio vs Benchmark

```python
from utils.calculations import compute_period_comparison

result = compute_period_comparison(
    df_t=df_transactions,
    total_value=portfolio_value,
    bench_series=benchmark_data,
    period_days=365
)
# Returns: port_pct, bench_pct, port_value, bench_value, use_xirr
```

### Apply Theming

```python
from ui.styles import apply_theme
apply_theme()  # Call once at app startup
```

### Show Alert

```python
from ui.styles import show_alert
show_alert("Something important!", alert_type="warn")
show_alert("Error occurred!", alert_type="danger")
show_alert("Success!", alert_type="success")
```

### Render Holdings Table

```python
from ui.components import render_holdings_table
render_holdings_table(df_holdings[['Fund', 'Category', 'Market Value']])
```

### Render Section Header

```python
from ui.components import render_header, render_section_header
render_header("Portfolio Analysis", "Updated today")
render_section_header("Holdings", "Detailed breakdown")
```

---

## Configuration Changes

### Change Benchmark

Edit `config.py`:

```python
BENCHMARKS = {
    "Nifty 50": "^NSEI",
    "My Custom Index": "CUSTOM_TICKER",  # Add here
}
```

### Change Colors

Edit `config.py`:

```python
CATEGORY_COLORS = {
    "Equity": "#3B82F6",  # Change hex values
    # ...
}
```

### Change Expense Ratios

Edit `config.py`:

```python
EXP_RATIOS = {
    "Equity": (0.50, 1.50),  # (Direct, Regular)
    # ...
}
```

### Change Risk Tiers

Edit `config.py`:

```python
RISK_TIERS = {
    "Equity": (17.0, 1.10, "High"),  # (Annual Vol%, Beta, Label)
    # ...
}
```

---

## Important Path Conversions

### Old code (monolithic app.py):

```python
fmt_inr(number)
parse_cas(file_bytes, password)
compute_xirr(df_t, value)
st.set_page_config(...)
```

### New code (modularized):

```python
from utils.formatting import fmt_inr
from utils.parsers import parse_cas
from utils.calculations import compute_xirr

fmt_inr(number)  # Same function, different import
parse_cas(file_bytes, password)  # Same function, different import
compute_xirr(df_t, value)  # Same function, different import
st.set_page_config(...)  # No change needed
```

---

## Import Cheat Sheet

```python
# Configuration
from config import BENCHMARKS, CATEGORY_COLORS, EXP_RATIOS, PERIOD_MAP

# Formatting
from utils.formatting import fmt_inr, fmt_percentage, fmt_decimal

# Parsing
from utils.parsers import parse_cas, detect_category, detect_amc

# Calculations
from utils.calculations import compute_xirr, fetch_benchmark, compute_period_comparison

# UI Styling
from ui.styles import apply_theme, show_alert, show_badge

# UI Components
from ui.components import render_header, render_holdings_table, show_onboarding_screen
```

---

## Debugging Tips

### Debugging CAS Parsing

```python
from utils.parsers import parse_cas
df_h, df_t, df_s, err, is_partial = parse_cas(file_bytes, password)
if err:
    print(f"Parsing error: {err}")
else:
    print(f"Holdings: {len(df_h)}, Transactions: {len(df_t)}")
```

### Debugging XIRR Calculation

```python
from utils.calculations import compute_xirr
xirr_result = compute_xirr(df_txns, portfolio_value)
print(f"XIRR: {xirr_result}%")
if xirr_result == 0.0:
    print("Check: Do you have buy AND sell transactions?")
```

### Debugging Benchmark Fetch

```python
from utils.calculations import fetch_benchmark
bench = fetch_benchmark("^NSEI", 365)
print(f"Benchmarks days available: {len(bench)}")
print(f"Date range: {bench.index[0]} to {bench.index[-1]}")
```

---

## Performance Notes

1. **Caching**: `parse_cas()` and `fetch_benchmark()` use `@st.cache_data()`
   - CAS parsing cached based on file bytes
   - Benchmark data cached for 1 hour

2. **DataFrames**: Large portfolios should be filtered before rendering
   - Apply filters before `render_holdings_table()`

3. **Calculations**: XIRR is computationally expensive
   - Cached at session level if possible

---

## Next Steps

1. **Test the refactored app**: `streamlit run app_refactored.py`
2. **Compare with original**: `streamlit run app.py` (for reference)
3. **Add new features** using the modular structure
4. **Consider adding pages** for tax analysis, recommendations, etc.
5. **Add unit tests** for calculations module

---

## Support Resources

- **REFACTORING_GUIDE.md** - Detailed architecture documentation
- **Docstrings** - Each function has documentation
- **Type hints** - Functions have input/output types (where possible)
- **Comments** - Key logic is commented for clarity
