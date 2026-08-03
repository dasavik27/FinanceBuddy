// Equity API response types.
//
// The equity client methods were all `Promise<any>`, so nothing on the boundary was
// checked and every tab held `useState<any>`. That is how `summary.total_value` came to
// be read off a `{}` (the backend returns an empty object for an empty portfolio) and
// rendered as "₹NaN" and "+undefined% absolute return".
//
// Fields the backend may omit are optional here rather than assumed present, which
// pushes the null handling to the call site where it belongs.

export interface EquitySummary {
  total_value?: number
  total_invested?: number
  unrealized_pnl?: number
  pnl_pct?: number
  day_change?: number
  num_stocks?: number
  source?: string
  has_trades?: boolean
}

export interface EquityHolding {
  symbol: string
  name?: string
  isin?: string | null
  exchange?: string
  sector?: string
  industry?: string
  quantity: number
  avg_price: number
  ltp: number
  current_value: number
  invested: number
  unrealized_pnl: number
  pnl_pct: number
  day_change?: number
  day_change_pct?: number
  weight_pct?: number
  broker?: string
}

export interface EquityHoldingsResponse {
  holdings: EquityHolding[]
  total: number
}

export interface AllocationSlice {
  label?: string
  sector?: string
  industry?: string
  value: number
  pct: number
}

export interface EquityAllocation {
  by_sector: AllocationSlice[]
  by_industry: AllocationSlice[]
}

export interface GainLossRow {
  symbol: string
  unrealized_pnl: number
  pnl_pct: number
}

/** Realised gains for one financial year. */
export interface RealisedYear {
  stcg: number
  ltcg: number
}

export interface EquityPnl {
  unrealized_pnl?: number
  total_gainers?: number
  total_losers?: number
  gainers_value?: number
  losers_value?: number
  /** Financial year the headline STCG/LTCG figures belong to, e.g. "2026-27". */
  financial_year?: string
  stcg_estimate?: number
  ltcg_estimate?: number
  stcg_tax_estimate?: number
  ltcg_tax_estimate?: number
  realised_by_year?: Record<string, RealisedYear>
  lifetime_stcg?: number
  lifetime_ltcg?: number
  /** Quantity sold with no matching buy lot — the tradebook does not reach back far enough. */
  unmatched_sell_qty?: number
  has_tradebook?: boolean
  top_gainers?: GainLossRow[]
  top_losers?: GainLossRow[]
}

export interface EquityPerformance {
  dates: string[]
  portfolio: number[]
  benchmark: number[]
  benchmark_name?: string
  period?: string
  /** How many holdings the provider had history for, vs how many were asked about. */
  priced_symbols?: number
  total_symbols?: number
}

export interface ConcentratedPosition {
  symbol: string
  weight_pct: number
  sector?: string
}

export interface EquityInsights {
  top_gainers?: GainLossRow[]
  top_losers?: GainLossRow[]
  concentrated_positions?: ConcentratedPosition[]
  tax_loss_harvest?: GainLossRow[]
  diversification_score?: number
}

export interface StockSearchResult {
  symbol: string
  name: string
}

export interface MarketIndex {
  symbol: string
  name: string
  price: number
  change: number
  p_change: number
}

export interface PeerStock {
  symbol: string
  name: string
  current_price?: number | null
  change?: number | null
  p_change?: number | null
  pe_ratio?: number | null
  market_cap_cr?: number | null
  sector?: string
}

export interface IncomeStatementItem {
  period: string
  date: string
  revenue_cr?: number | null
  operating_expense_cr?: number | null
  net_income_cr?: number | null
  net_margin_pct?: number | null
  eps?: number | null
  ebitda_cr?: number | null
  effective_tax_rate_pct?: number | null
}

export interface BalanceSheetItem {
  period: string
  date: string
  cash_and_equivalents_cr?: number | null
  total_assets_cr?: number | null
  total_liabilities_cr?: number | null
  total_equity_cr?: number | null
  shares_outstanding?: number | null
  /** Total assets / equity. Was misnamed `price_to_book`; there is no price term. */
  equity_multiplier?: number | null
  return_on_assets_pct?: number | null
}

export interface CashFlowItem {
  period: string
  date: string
  net_income_cr?: number | null
  cash_from_operations_cr?: number | null
  cash_from_investing_cr?: number | null
  cash_from_financing_cr?: number | null
  net_change_in_cash_cr?: number | null
  free_cash_flow_cr?: number | null
  change_in_inventories_cr?: number | null
  gain_loss_on_sale_assets_cr?: number | null
}

export interface FinancialStatementsPeriod {
  income_statement: IncomeStatementItem[]
  balance_sheet: BalanceSheetItem[]
  cash_flow: CashFlowItem[]
}

export interface FinancialStatements {
  quarterly: FinancialStatementsPeriod
  annual: FinancialStatementsPeriod
}

/**
 * A *reported* quarter. The estimate fields are always null today: Yahoo publishes no
 * historical consensus for NSE names, and these used to be back-computed from the
 * actual (`reported_eps * 0.97`), which made every quarter beat by exactly +3.09%.
 * Forward consensus lives in `Consensus`, and is never mixed into reported history.
 */
export interface EarningsHistoryItem {
  period: string
  date: string
  reported_eps?: number | null
  estimated_eps?: number | null
  surprise_pct?: number | null
  eps_surprise_type?: 'beat' | 'miss' | null
  reported_revenue_cr?: number | null
  estimated_revenue_cr?: number | null
  revenue_surprise_pct?: number | null
  revenue_surprise_type?: 'beat' | 'miss' | null
}

export interface EarningsSummary {
  last_report_date?: string | null
  financial_period?: string | null
  reported_eps?: number | null
  reported_revenue_cr?: number | null
  history?: EarningsHistoryItem[]
}

export type CorporateActionType =
  | 'dividend' | 'bonus' | 'split' | 'rights' | 'buyback' | 'demerger' | 'other'

export interface CorporateAction {
  symbol: string
  type: CorporateActionType
  subject: string
  /** "4:1" for a bonus, "2:1" for a face-value split. Null for dividends. */
  ratio?: string | null
  ex_date?: string | null
  record_date?: string | null
  isin?: string | null
  face_value?: string | number | null
}

/**
 * The company's own most recent quarterly filing, parsed from its XBRL. Kept separate
 * from the yfinance statements rather than merged: it states its own basis
 * (consolidated vs standalone) and audit status, which yfinance does not.
 */
export interface LatestFiling {
  symbol: string
  source: string
  quarter_end: string
  basis?: string
  audited?: string
  filed_at?: string | null
  filing_url?: string
  revenue_cr?: number | null
  total_income_cr?: number | null
  total_expenses_cr?: number | null
  pbt_cr?: number | null
  tax_expense_cr?: number | null
  net_income_cr?: number | null
  net_margin_pct?: number | null
  eps_basic?: number | null
  eps_diluted?: number | null
  face_value?: number | null
}

export interface Announcement {
  symbol: string
  subject: string
  detail?: string | null
  broadcast_at?: string | null
  attachment?: string | null
}

export interface CorporateEvent {
  symbol: string
  company: string
  purpose: string
  date?: string | null
  details?: string | null
}

/** Forward analyst consensus. Absent entirely when no broker covers the name. */
export interface ConsensusEstimate {
  avg?: number | null
  low?: number | null
  high?: number | null
  analysts: number
}

export interface Consensus {
  eps?: Record<string, ConsensusEstimate>
  revenue_cr?: Record<string, { avg?: number | null; analysts: number }>
  price_target?: { low?: number; high?: number; mean?: number; median?: number }
  analyst_count?: number
  recommendation?: string
  recommendation_mean?: number
}

export interface QuarterlyFinancial {
  quarter: string
  date: string
  revenue_cr: number
  net_income_cr: number
  operating_income_cr: number
  net_margin_pct: number
}

export interface QuarterlyEarnings {
  date: string
  quarter: string
  reported_eps?: number | null
  estimated_eps?: number | null
  surprise_pct?: number | null
}

export interface TimeframeSlice {
  dates: string[]
  prices: number[]
  start_price: number
  end_price: number
  change: number
  p_change: number
}

export interface StockTechnicals {
  sma_50?: number | null
  sma_200?: number | null
  above_50_dma?: boolean | null
  above_200_dma?: boolean | null
  rsi_14?: number | null
  rsi_status?: 'Oversold' | 'Overbought' | 'Neutral' | string
  trend?: string
  dist_52w_high_pct?: number | null
  dist_52w_low_pct?: number | null
}

export interface StockAnalysis {
  /** Which upstream actually served this — "NSE" or "Yahoo Finance", not a fixed label. */
  source?: string
  /** ISO-8601 UTC timestamp of when the payload was built, for the staleness chip. */
  as_of?: string
  /**
   * Currency the *statement* figures are reported in before conversion. Yahoo reports
   * some NSE companies (INFY) in USD while quoting them in INR; the `_cr` fields are
   * converted, and this records what they were converted from.
   */
  financial_currency?: string
  symbol: string
  name?: string
  sector?: string
  industry?: string
  ticker?: string
  isin?: string
  series?: string
  current_price?: number
  day_open?: number | null
  day_high?: number | null
  day_low?: number | null
  market_cap?: number | null
  market_cap_cr?: number | null
  pe_ratio?: number | null
  sector_pe?: number | null
  forward_pe?: number | null
  peg_ratio?: number | null
  pb_ratio?: number | null
  price_to_sales?: number | null
  eps?: number | null
  dividend_yield?: number | null
  roe?: number | null
  profit_margins?: number | null
  operating_margins?: number | null
  debt_to_equity?: number | null
  free_cash_flow_cr?: number | null
  week52_high?: number | null
  week52_low?: number | null
  vwap?: number | null
  delivery_pct?: number | null
  avg_volume?: number | null
  volume?: number | null
  beta?: number | null
  year_return?: number
  technicals?: StockTechnicals
  peers?: PeerStock[]
  financials?: QuarterlyFinancial[]
  financial_statements?: FinancialStatements
  earnings?: QuarterlyEarnings[]
  earnings_summary?: EarningsSummary
  consensus?: Consensus
  /**
   * From NSE, which is authoritative here where Yahoo is not: yfinance reports Indian
   * bonus issues as splits indistinguishably and mis-scales compound actions. Empty
   * when NSE is unreachable (it blocks datacenter IPs).
   */
  corporate_actions?: CorporateAction[]
  upcoming_events?: CorporateEvent[]
  latest_filing?: LatestFiling | null
  /**
   * Per-company exchange filings. Preferred over a media news feed: the newswire RSS
   * options are category-level only, so per-company relevance would mean matching
   * names against a firehose, and "Tata" alone matches five listed companies. These
   * are authoritative and already tagged with the symbol.
   */
  announcements?: Announcement[]
  /** True when served past its freshness window while a refresh runs in background. */
  stale?: boolean
  description?: string
  chart?: {
    dates: string[]
    prices: number[]
    /** Per-point moving averages, aligned to `dates`. Null before the window fills. */
    sma_50?: (number | null)[]
    sma_200?: (number | null)[]
    /** Real NIFTY 50 closes aligned to `dates`; null on days the index has no print. */
    benchmark?: (number | null)[]
    /**
     * Daily traded volume aligned to `dates`. Columnar rather than an array of
     * objects with a repeated date per row — that shape, plus an OHLC series nothing
     * rendered, was 13.1 KB of a 58 KB payload.
     */
    volume?: number[]
  }
  timeframes?: Record<string, TimeframeSlice>
}

export interface EquityUploadResult {
  session_id: string
  stock_count: number
  broker: string
  has_tradebook?: boolean
  zerodha_user?: string
  symbols: string[]
}

export const EQUITY_SORTABLE_COLUMNS = [
  'symbol', 'name', 'sector', 'industry', 'quantity', 'avg_price', 'ltp',
  'current_value', 'invested', 'unrealized_pnl', 'pnl_pct', 'day_change',
  'day_change_pct', 'weight_pct',
] as const

export type EquitySortColumn = (typeof EQUITY_SORTABLE_COLUMNS)[number]
