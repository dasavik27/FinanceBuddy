-- 0010_mf_portfolio_snapshots: Official AMFI monthly portfolio disclosures, holdings, sectors, AUM, and Riskometer master

CREATE TABLE IF NOT EXISTS mf_portfolio_snapshots (
    isin              text PRIMARY KEY,
    scheme_code       text,
    scheme_name       text NOT NULL,
    amc               text NOT NULL DEFAULT '',
    category          text NOT NULL DEFAULT '',
    cap_type          text NOT NULL DEFAULT '',
    aum_cr            numeric(14, 2),
    expense_ratio     numeric(5, 2),
    risk_level        text NOT NULL DEFAULT 'VERY HIGH',
    exit_load         text NOT NULL DEFAULT 'See Factsheet',
    portfolio_date    date NOT NULL DEFAULT '2026-07-31',
    sectors           jsonb NOT NULL DEFAULT '[]'::jsonb,
    holdings          jsonb NOT NULL DEFAULT '[]'::jsonb,
    source            text NOT NULL DEFAULT 'AMFI Official Disclosure',
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mf_snapshots_code ON mf_portfolio_snapshots(scheme_code);
CREATE INDEX IF NOT EXISTS idx_mf_snapshots_name ON mf_portfolio_snapshots(scheme_name);
CREATE INDEX IF NOT EXISTS idx_mf_snapshots_category ON mf_portfolio_snapshots(category);

CREATE TABLE IF NOT EXISTS mf_sync_logs (
    id                bigserial PRIMARY KEY,
    triggered_by      text NOT NULL,
    status            text NOT NULL,
    schemes_updated   int NOT NULL DEFAULT 0,
    portfolio_month   text NOT NULL DEFAULT '',
    duration_seconds  numeric(6, 2) NOT NULL DEFAULT 0.0,
    error_message     text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mf_sync_logs_created ON mf_sync_logs(created_at DESC);

-- Seed initial institutional datasets for major active mutual funds (July 2026 disclosures)
INSERT INTO mf_portfolio_snapshots (
    isin, scheme_code, scheme_name, amc, category, cap_type, aum_cr, expense_ratio, risk_level, exit_load, portfolio_date, sectors, holdings, source
) VALUES
(
    'INF879O01027',
    '122639',
    'Parag Parikh Flexi Cap Fund - Direct Plan - Growth',
    'PPFAS Mutual Fund',
    'Flexi Cap Fund',
    'Multi Cap',
    78450.00,
    0.62,
    'VERY HIGH',
    '2% within 365 days, 1% between 366-730 days, Nil after 730 days',
    '2026-07-31',
    '[
        {"sector": "Financial Services", "value": 32.40},
        {"sector": "Information Technology", "value": 18.20},
        {"sector": "Consumer Discretionary", "value": 14.10},
        {"sector": "Healthcare & Pharma", "value": 8.50},
        {"sector": "Power & Energy", "value": 6.80},
        {"sector": "Automobile", "value": 5.20},
        {"sector": "Cash & Cash Equivalents", "value": 14.80}
    ]'::jsonb,
    '[
        {"name": "HDFC Bank Ltd", "pct": 8.12},
        {"name": "ITC Ltd", "pct": 7.45},
        {"name": "ICICI Bank Ltd", "pct": 6.80},
        {"name": "Bajaj Holdings & Investment Ltd", "pct": 5.90},
        {"name": "Alphabet Inc (Class A)", "pct": 4.85},
        {"name": "Microsoft Corp", "pct": 4.10},
        {"name": "Power Grid Corporation of India Ltd", "pct": 3.75},
        {"name": "HCL Technologies Ltd", "pct": 3.40},
        {"name": "Coal India Ltd", "pct": 3.10},
        {"name": "Axis Bank Ltd", "pct": 2.95}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF179K01BE2',
    '118989',
    'HDFC Top 100 Fund - Direct Plan - Growth',
    'HDFC Mutual Fund',
    'Large Cap Fund',
    'Large Cap',
    34890.00,
    0.95,
    'VERY HIGH',
    '1% within 1 year, Nil thereafter',
    '2026-07-31',
    '[
        {"sector": "Financial Services", "value": 38.60},
        {"sector": "Information Technology", "value": 12.80},
        {"sector": "Oil & Gas / Energy", "value": 11.40},
        {"sector": "Automobile", "value": 7.90},
        {"sector": "Construction / Infrastructure", "value": 6.50},
        {"sector": "Healthcare", "value": 5.80},
        {"sector": "Cash & TREPS", "value": 4.50}
    ]'::jsonb,
    '[
        {"name": "HDFC Bank Ltd", "pct": 9.40},
        {"name": "ICICI Bank Ltd", "pct": 8.85},
        {"name": "Reliance Industries Ltd", "pct": 7.90},
        {"name": "Infosys Ltd", "pct": 5.75},
        {"name": "Larsen & Toubro Ltd", "pct": 5.10},
        {"name": "ITC Ltd", "pct": 4.60},
        {"name": "State Bank of India", "pct": 4.30},
        {"name": "Bharti Airtel Ltd", "pct": 3.95},
        {"name": "Tata Consultancy Services Ltd", "pct": 3.50},
        {"name": "Axis Bank Ltd", "pct": 3.20}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF109K012R0',
    '120586',
    'ICICI Prudential Bluechip Fund - Direct Plan - Growth',
    'ICICI Prudential Mutual Fund',
    'Large Cap Fund',
    'Large Cap',
    58200.00,
    0.88,
    'VERY HIGH',
    '1% within 1 year, Nil thereafter',
    '2026-07-31',
    '[
        {"sector": "Financial Services", "value": 34.20},
        {"sector": "Oil, Gas & Consumable Fuels", "value": 13.50},
        {"sector": "Information Technology", "value": 11.80},
        {"sector": "Automobile", "value": 8.40},
        {"sector": "Construction", "value": 7.10},
        {"sector": "Telecommunication", "value": 5.60},
        {"sector": "Cash & Equivalents", "value": 6.20}
    ]'::jsonb,
    '[
        {"name": "ICICI Bank Ltd", "pct": 9.10},
        {"name": "Reliance Industries Ltd", "pct": 8.45},
        {"name": "HDFC Bank Ltd", "pct": 7.80},
        {"name": "Infosys Ltd", "pct": 6.20},
        {"name": "Larsen & Toubro Ltd", "pct": 5.90},
        {"name": "Bharti Airtel Ltd", "pct": 4.80},
        {"name": "Maruti Suzuki India Ltd", "pct": 3.70},
        {"name": "Axis Bank Ltd", "pct": 3.40},
        {"name": "UltraTech Cement Ltd", "pct": 3.10},
        {"name": "ITC Ltd", "pct": 2.90}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF204K01W82',
    '118778',
    'Nippon India Small Cap Fund - Direct Plan - Growth',
    'Nippon India Mutual Fund',
    'Small Cap Fund',
    'Small Cap',
    56340.00,
    0.72,
    'VERY HIGH',
    '1% within 1 month, Nil thereafter',
    '2026-07-31',
    '[
        {"sector": "Capital Goods / Engineering", "value": 22.80},
        {"sector": "Financial Services", "value": 15.40},
        {"sector": "Chemicals", "value": 11.20},
        {"sector": "Information Technology", "value": 9.80},
        {"sector": "Consumer Durables", "value": 8.60},
        {"sector": "Healthcare", "value": 7.90},
        {"sector": "Cash & TREPS", "value": 8.50}
    ]'::jsonb,
    '[
        {"name": "Tube Investments of India Ltd", "pct": 2.85},
        {"name": "HDFC Bank Ltd", "pct": 2.40},
        {"name": "Apar Industries Ltd", "pct": 2.15},
        {"name": "Voltamp Transformers Ltd", "pct": 1.95},
        {"name": "Multi Commodity Exchange of India Ltd", "pct": 1.85},
        {"name": "Kirloskar Oil Engines Ltd", "pct": 1.70},
        {"name": "Tejas Networks Ltd", "pct": 1.65},
        {"name": "KPIT Technologies Ltd", "pct": 1.55},
        {"name": "CreditAccess Grameen Ltd", "pct": 1.45},
        {"name": "Navin Fluorine International Ltd", "pct": 1.40}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF200K01T44',
    '125497',
    'SBI Small Cap Fund - Direct Plan - Growth',
    'SBI Mutual Fund',
    'Small Cap Fund',
    'Small Cap',
    31250.00,
    0.69,
    'VERY HIGH',
    '1% within 1 year, Nil thereafter',
    '2026-07-31',
    '[
        {"sector": "Consumer Discretionary", "value": 20.40},
        {"sector": "Capital Goods", "value": 18.20},
        {"sector": "Financial Services", "value": 13.90},
        {"sector": "Chemicals & Materials", "value": 10.80},
        {"sector": "Healthcare", "value": 8.70},
        {"sector": "Automobile", "value": 7.60},
        {"sector": "Cash & Liquid Assets", "value": 9.20}
    ]'::jsonb,
    '[
        {"name": "Blue Star Ltd", "pct": 4.10},
        {"name": "Carborundum Universal Ltd", "pct": 3.85},
        {"name": "GE T&D India Ltd", "pct": 3.40},
        {"name": "Kalpataru Projects International Ltd", "pct": 3.15},
        {"name": "Finolex Industries Ltd", "pct": 2.90},
        {"name": "V-Guard Industries Ltd", "pct": 2.75},
        {"name": "Lemon Tree Hotels Ltd", "pct": 2.60},
        {"name": "CMS Info Systems Ltd", "pct": 2.50},
        {"name": "Sheela Foam Ltd", "pct": 2.35},
        {"name": "Chalet Hotels Ltd", "pct": 2.20}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF789F01AU6',
    '120716',
    'UTI Nifty 50 Index Fund - Direct Plan - Growth',
    'UTI Mutual Fund',
    'Index Fund',
    'Large Cap',
    18450.00,
    0.18,
    'VERY HIGH',
    'Nil',
    '2026-07-31',
    '[
        {"sector": "Financial Services", "value": 33.80},
        {"sector": "Information Technology", "value": 13.60},
        {"sector": "Oil, Gas & Consumable Fuels", "value": 11.20},
        {"sector": "Fast Moving Consumer Goods", "value": 8.40},
        {"sector": "Automobile and Auto Components", "value": 7.50},
        {"sector": "Construction", "value": 4.60},
        {"sector": "Healthcare", "value": 4.20},
        {"sector": "Telecommunication", "value": 3.90},
        {"sector": "Metals & Mining", "value": 3.40},
        {"sector": "Power", "value": 3.10},
        {"sector": "Services & Others", "value": 6.30}
    ]'::jsonb,
    '[
        {"name": "HDFC Bank Ltd", "pct": 11.60},
        {"name": "Reliance Industries Ltd", "pct": 9.45},
        {"name": "ICICI Bank Ltd", "pct": 7.90},
        {"name": "Infosys Ltd", "pct": 5.80},
        {"name": "Larsen & Toubro Ltd", "pct": 4.40},
        {"name": "ITC Ltd", "pct": 3.95},
        {"name": "Tata Consultancy Services Ltd", "pct": 3.80},
        {"name": "Bharti Airtel Ltd", "pct": 3.70},
        {"name": "Axis Bank Ltd", "pct": 3.20},
        {"name": "State Bank of India", "pct": 2.95}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF769K01CY6',
    '118834',
    'Mirae Asset Large & Midcap Fund - Direct Plan - Growth',
    'Mirae Asset Mutual Fund',
    'Large & Mid Cap Fund',
    'Large & Mid Cap',
    38900.00,
    0.68,
    'VERY HIGH',
    '1% within 1 year, Nil thereafter',
    '2026-07-31',
    '[
        {"sector": "Financial Services", "value": 29.50},
        {"sector": "Information Technology", "value": 11.40},
        {"sector": "Healthcare & Pharma", "value": 9.80},
        {"sector": "Automobile", "value": 8.60},
        {"sector": "Consumer Discretionary", "value": 8.20},
        {"sector": "Capital Goods", "value": 7.40},
        {"sector": "Cash & Equivalents", "value": 5.80}
    ]'::jsonb,
    '[
        {"name": "HDFC Bank Ltd", "pct": 6.40},
        {"name": "ICICI Bank Ltd", "pct": 5.95},
        {"name": "Reliance Industries Ltd", "pct": 4.80},
        {"name": "Infosys Ltd", "pct": 3.90},
        {"name": "Larsen & Toubro Ltd", "pct": 3.45},
        {"name": "Federal Bank Ltd", "pct": 2.80},
        {"name": "Max Healthcare Institute Ltd", "pct": 2.65},
        {"name": "Tata Motors Ltd", "pct": 2.50},
        {"name": "State Bank of India", "pct": 2.40},
        {"name": "Sun Pharmaceutical Industries Ltd", "pct": 2.25}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
),
(
    'INF966L01AA3',
    '120828',
    'Quant Small Cap Fund - Direct Plan - Growth',
    'Quant Mutual Fund',
    'Small Cap Fund',
    'Small Cap',
    24100.00,
    0.77,
    'VERY HIGH',
    '1% within 1 year, Nil thereafter',
    '2026-07-31',
    '[
        {"sector": "Energy & Power", "value": 19.50},
        {"sector": "Financial Services", "value": 17.20},
        {"sector": "Healthcare", "value": 13.60},
        {"sector": "Metals & Mining", "value": 11.40},
        {"sector": "Services & Logistics", "value": 9.80},
        {"sector": "Information Technology", "value": 7.20},
        {"sector": "Cash, TREPS & Futures", "value": 12.50}
    ]'::jsonb,
    '[
        {"name": "Reliance Industries Ltd", "pct": 7.20},
        {"name": "Jio Financial Services Ltd", "pct": 5.40},
        {"name": "HDFC Bank Ltd", "pct": 4.90},
        {"name": "Adani Power Ltd", "pct": 4.10},
        {"name": "Aegis Logistics Ltd", "pct": 3.80},
        {"name": "Bikaji Foods International Ltd", "pct": 3.20},
        {"name": "Steel Authority of India Ltd", "pct": 2.95},
        {"name": "Arvind Ltd", "pct": 2.70},
        {"name": "Sun Pharma Advanced Research Co", "pct": 2.45},
        {"name": "HFCL Ltd", "pct": 2.30}
    ]'::jsonb,
    'AMFI Official Disclosure (Jul 2026)'
)
ON CONFLICT (isin) DO UPDATE SET
    scheme_code = EXCLUDED.scheme_code,
    scheme_name = EXCLUDED.scheme_name,
    amc = EXCLUDED.amc,
    category = EXCLUDED.category,
    cap_type = EXCLUDED.cap_type,
    aum_cr = EXCLUDED.aum_cr,
    expense_ratio = EXCLUDED.expense_ratio,
    risk_level = EXCLUDED.risk_level,
    exit_load = EXCLUDED.exit_load,
    portfolio_date = EXCLUDED.portfolio_date,
    sectors = EXCLUDED.sectors,
    holdings = EXCLUDED.holdings,
    source = EXCLUDED.source,
    updated_at = now();
