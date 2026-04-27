# FolioIQ - Refactored Architecture

## Overview

The application has been refactored from a single 3000+ line file into a modular, maintainable architecture with clear separation of concerns.

## Project Structure

```
FolioIQ/
├── app_refactored.py          # Main entry point (simplified)
├── config.py                  # Constants & configuration
├── utils/                     # Business logic layer
│   ├── __init__.py
│   ├── formatting.py          # Currency & display formatting
│   ├── parsers.py             # CAS PDF parsing & fund detection
│   └── calculations.py        # Financial analytics engine
└── ui/                        # User interface layer
    ├── __init__.py
    ├── styles.py              # CSS theming & styling
    └── components.py          # Reusable UI components
```

## Module Responsibilities

### Core Files

#### `config.py` - Configuration & Constants

- Benchmark definitions and TRI mappings
- Time period configurations
- Color schemes and styling constants
- Risk tiers and category mappings
- Expense ratio tables
- Goal timeline definitions
- Sector detection keywords

**Why**: Centralizes all "magic numbers" and configuration, making it easy to adjust colors, benchmarks, or risk parameters without touching code logic.

#### `app_refactored.py` - Application Entry Point

- Streamlit page setup and configuration
- Session state initialization
- Sidebar UI and filters
- Main dashboard layout and workflow
- Key metrics display

**Why**: Orchestrates the entire app flow - imports from utils and ui modules, keeping it simple and readable.

---

### Utils Layer (Business Logic)

#### `utils/formatting.py` - Formatting Utilities

Functions:

- `fmt_inr()` - Format numbers in Indian numbering system (₹1,00,000)
- `fmt_percentage()` - Format percentages with +/- signs
- `fmt_decimal()` - Format decimal values with specified precision
- `color_positive_negative()` - Return CSS color class for pos/neg values

**Why**: Keeps presentation logic separate from business logic. Easy to change currency format or precision globally.

#### `utils/parsers.py` - CAS Parsing & Fund Detection

Functions:

- `parse_cas()` - Main CAS PDF parser using casparser library
- `detect_category()` - Classify fund by category (Equity, Debt, ELSS, etc.)
- `detect_cap_type()` - Determine capitalization type (Large/Mid/Small Cap)
- `detect_amc()` - Identify AMC from fund name
- `estimate_invested()` - Calculate invested amount from transactions

**Why**: All CAS-related logic in one place. Easy to add new detection rules or fix parsing issues.

#### `utils/calculations.py` - Financial Analytics Engine

Functions:

- `fetch_benchmark()` - Fetch benchmark data from yfinance
- `compute_xirr()` - Portfolio XIRR from transaction ledger
- `compute_benchmark_xirr()` - Simulate benchmark investment
- `compute_period_comparison()` - Compare portfolio vs benchmark for periods
- `compute_rolling_returns()` - Calculate rolling returns
- `estimate_expense_drag()` - Annual ER drag estimation
- `expense_leakage_20yr()` - 20-year opportunity cost analysis
- `elss_lock_in_analysis()` - ELSS lock-in status tracking
- `detect_sector()` - Classify funds by sector
- `compute_portfolio_score()` - Generate 0-100 portfolio health score

**Why**: All complex financial logic in one module. Easy to unit test, modify algorithms, or add new calculations.

---

### UI Layer (Presentation)

#### `ui/styles.py` - Theming & Styling

Functions:

- `apply_theme()` - Apply complete design system (imports CSS)
- `show_alert()` - Display alert boxes
- `show_metric_card()` - Display formatted metric cards
- `show_badge()` - Display category/status badges

**Why**: All CSS and styling in one place. Easy to rebrand or adjust UI colors/fonts globally. Design system is self-contained.

#### `ui/components.py` - Reusable UI Components

Functions:

- `render_header()` - Page title with subtitle
- `render_section_header()` - Section title with description
- `render_metric_row()` - Row of metrics in columns
- `render_holdings_table()` - Formatted holdings table
- `render_category_distribution()` - Category breakdown summary
- `show_onboarding_screen()` - Welcome/setup screen
- `show_footer()` - App footer

**Why**: Reusable components eliminate code duplication. Easy to add new dashboard sections or pages. Components are testable.

---

## Benefits of Refactoring

### 1. **Maintainability**

- Each module has a single responsibility
- Easy to find and fix bugs
- Reduced cognitive load when reading code

### 2. **Reusability**

- UI components can be imported into multiple pages
- Calculation functions can be used by different views
- Formatting utilities consistent across app

### 3. **Testability**

- Business logic separated from Streamlit
- Easy to unit test calculations and parsing
- Mock data and edge cases easier to handle

### 4. **Scalability**

- Easy to add new pages (finance, tax, recommendations)
- Easy to add new calculations or analyses
- Multi-page app becomes manageable

### 5. **Collaboration**

- Team members can work on different modules in parallel
- Clear interfaces between modules
- Reduced merge conflicts

### 6. **Configuration**

- All constants in one file
- Easy to adjust without touching code
- Feature flags and settings centralized

---

## Usage

### Running the App

**Refactored version (recommended):**

```bash
streamlit run app_refactored.py
```

**Original monolithic app:**

```bash
streamlit run app.py  # (Still works, but not recommended)
```

### Adding New Features

#### Add a new calculation:

1. Add function to `utils/calculations.py`
2. Import in `app_refactored.py`
3. Use in main app flow

#### Change styling:

1. Modify CSS in `ui/styles.py`
2. No need to edit any other files

#### Add a reusable UI component:

1. Add function to `ui/components.py`
2. Import where needed
3. Use throughout app

#### Add new constant:

1. Add to `config.py`
2. Import in relevant modules

---

## Migration Notes

- `app_refactored.py` is the new recommended entry point
- Original `app.py` remains unchanged for reference
- All modular code is backward compatible
- Gradual migration: can add more pages without refactoring existing code

---

## Future Improvements

1. **Multi-page app**: Add `pages/` folder for dedicated sections
   - pages/overview.py
   - pages/tax_analysis.py
   - pages/recommendations.py
   - pages/compare_funds.py

2. **Data persistence**: Cache analyzed portfolios
   - Store CAS analysis results
   - Enable comparative analysis over time

3. **Database integration**: Store portfolio snapshots
   - Track portfolio evolution
   - Provide historical insights

4. **Testing**: Add test suite
   - Unit tests for calculations
   - Integration tests for parser
   - UI component tests

5. **Logging**: Add structured logging
   - Error tracking
   - Usage analytics
   - Performance monitoring

---

## Module Dependency Graph

```
app_refactored.py
├── config.py
├── utils/formatting.py
├── utils/parsers.py
├── utils/calculations.py
└── ui/styles.py
└── ui/components.py
```

**No circular dependencies** - Clean one-way dependency flow from presentation to business logic to configuration.

---

## Questions & Support

For questions about the architecture or specific modules, refer to the docstrings in each file or the README.md comments.
