// Budget API response types.
//
// The budget client calls were the only ones in the app that reached past the typed
// `apiClient` facade and used the raw axios instance directly, so nothing on this
// boundary was checked. Fields the backend may omit are optional here rather than
// assumed present, which pushes the null handling to the call site.

/** Filters the analytics endpoints accept. All of them treat "all" as unset. */
export interface BudgetFilters {
  bank?: string
  accountType?: string
  txnType?: string
  dateRange?: string
  fromDate?: string
  toDate?: string
  amountBracket?: string
  paymentMode?: string
  category?: string
  search?: string
  flow?: string
}

/**
 * What POST /budget/portfolio/upload returns.
 *
 * `skipped` / `reasons` / `truncated` are the parse report. A statement that only
 * half-parsed has to say so, otherwise the dashboard describes part of the user's
 * spending as if it were all of it.
 */
export interface BudgetUploadResult {
  session_id: string
  bank?: string
  account_type?: string
  parsed?: number
  skipped?: number
  reasons?: Record<string, number>
  truncated?: boolean
}

export interface BudgetTransaction {
  txn_id: string
  session_id: string
  date?: string
  description?: string
  category?: string
  notes?: string
  amount?: number
  type?: string
  source_bank?: string
  account_type?: string
}

/**
 * One page of transactions.
 *
 * `/budget/analytics/{id}/transactions` is paginated - for the consolidated view it
 * would otherwise serialise every transaction across every uploaded statement into a
 * single response. `total` is the count *before* paging, so the UI can say how much it
 * is not showing.
 */
export interface BudgetTransactionsPage {
  transactions: BudgetTransaction[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface BudgetSessionMeta {
  session_id: string
  filename?: string
  bank?: string
  account_type?: string
  created_at?: string
  rows?: number
  total_income?: number
  total_expense?: number
}

export interface BudgetCategorySlice {
  category: string
  amount: number
  count?: number
  nature?: string
  top_merchants?: { name: string; amount?: number }[]
}

export interface BudgetCategoriesResponse {
  categories: BudgetCategorySlice[]
  nature_summary?: Record<string, number>
  all_categories?: string[]
  is_drilldown?: boolean
  category_stats?: any
}

/**
 * GET /budget/analytics/{sid}/overview.
 *
 * The four headline scalars are always present; everything the dashboard renders
 * conditionally is optional, so the conditionals are type-checked rather than
 * decorative.
 */
export interface BudgetOverview {
  total_income: number
  total_expense: number
  net_savings: number
  savings_rate: number
  banks?: string[]
  account_types?: string[]
  categories?: string[]
  health_metrics?: Record<string, any>
  top_merchants?: any[]
  top_inflows?: any[]
  bank_breakdown?: any[]
  cumulative_trend?: any[]
  monthly_trend?: any[]
  day_of_week_spend?: any[]
  biggest_change?: any
  recurring_charges?: any[]
  budget_50_30_20?: any
}

export interface BudgetRule {
  rule_id: string
  pattern: string
  category: string
  match_type: string
  match_count?: number
}

export interface BudgetRuleDraft {
  pattern: string
  category: string
  match_type: string
}

/** GET /budget/rules/match-types - the UI offers exactly what the server accepts. */
export interface BudgetMatchTypes {
  match_types: string[]
  max_pattern_length: number
  max_rules: number
}

/**
 * POST /budget/rules/test. `valid: false` carries the reason in `error`; the endpoint
 * answers 200 in that case because an un-compilable draft pattern is normal while the
 * user is still typing it.
 */
export interface BudgetRuleTestResult {
  valid: boolean
  matches: boolean
  error: string | null
}

export interface BudgetTransactionUpdate {
  txn_id: string
  session_id: string
  category: string
  notes?: string
}
