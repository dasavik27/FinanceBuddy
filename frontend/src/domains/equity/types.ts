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

export interface StockAnalysis {
  symbol: string
  name?: string
  sector?: string
  industry?: string
  ticker?: string
  current_price?: number
  market_cap?: number | null
  market_cap_cr?: number | null
  pe_ratio?: number | null
  pb_ratio?: number | null
  eps?: number | null
  dividend_yield?: number | null
  roe?: number | null
  debt_to_equity?: number | null
  week52_high?: number | null
  week52_low?: number | null
  avg_volume?: number | null
  beta?: number | null
  year_return?: number
  description?: string
  chart?: { dates: string[]; prices: number[] }
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
