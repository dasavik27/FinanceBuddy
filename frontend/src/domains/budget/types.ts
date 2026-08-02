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

// ── Accounts and cards ───────────────────────────────────────────────────────

export type BudgetAccountKind = 'savings' | 'current' | 'salary' | 'credit_card'
export type UtilisationStatus = 'healthy' | 'warning' | 'critical'

/**
 * One account, derived from the statements plus whatever metadata the user supplied.
 *
 * `balance` and `outstanding` are deliberately nullable and mutually exclusive: a
 * deposit account has a balance and no outstanding, a card has an outstanding and no
 * balance. A zero would read as "nothing owed" rather than "not applicable", so the
 * UI must branch on `is_card` instead of falling back to 0.
 */
export interface BudgetAccount {
  account_key: string
  bank: string
  kind: BudgetAccountKind
  label: string
  last4: string | null
  is_card: boolean
  credit_limit: number | null
  statement_day: number | null
  due_day: number | null
  opening_balance: number | null
  balance: number | null
  outstanding: number | null
  utilisation: number | null
  utilisation_status: UtilisationStatus | null
  inflow: number
  outflow: number
  txn_count: number
  first_txn: string | null
  last_txn: string | null
  months_covered: string[]
}

export interface BudgetAccountsResponse {
  accounts: BudgetAccount[]
  totals: {
    deposit_balance: number
    card_outstanding: number
    account_count: number
    card_count: number
  }
  utilisation_warnings: {
    account_key: string
    label: string
    utilisation: number
    status: UtilisationStatus
  }[]
  /** Cards with no limit set - utilisation cannot be computed, so prompt for it. */
  cards_missing_limit: string[]
}

/** PUT /budget/accounts/{key}. Omitted fields are preserved; explicit null clears. */
export interface BudgetAccountMetaUpdate {
  label?: string
  last4?: string | null
  credit_limit?: number | null
  statement_day?: number | null
  due_day?: number | null
  opening_balance?: number | null
}

// ── Transfers ────────────────────────────────────────────────────────────────

export interface BudgetTransferPair {
  debit_txn_id: string
  credit_txn_id: string
  from_account: string
  to_account: string
  amount: number
  debit_date: string
  credit_date: string
  lag_days: number
  confidence: 'high' | 'medium' | 'low'
  is_card_payment: boolean
}

export interface BudgetTransfersResponse {
  pairs: BudgetTransferPair[]
  count: number
  total_amount: number
  card_payment_total: number
  excluded_from_income: number
  excluded_from_expense: number
}

// ── Recurring ────────────────────────────────────────────────────────────────

export interface BudgetPriceChange {
  date: string
  from: number
  to: number
  change_pct: number
}

export interface BudgetRecurring {
  merchant: string
  category: string
  account_key: string
  cadence: string
  interval_days: number
  typical_amount: number
  last_amount: number
  last_seen: string
  next_expected: string | null
  occurrences: number
  total_paid: number
  annualised_cost: number
  regularity: number
  status: 'active' | 'lapsed'
  price_changes: BudgetPriceChange[]
}

export interface BudgetRecurringResponse {
  subscriptions: BudgetRecurring[]
  active_count: number
  lapsed_count: number
  monthly_commitment: number
  annual_commitment: number
  price_increases: (BudgetPriceChange & { merchant: string })[]
}

// ── Forecast ─────────────────────────────────────────────────────────────────

export interface BudgetForecast {
  as_of: string | null
  month: string | null
  days_elapsed: number
  days_remaining: number
  spent_this_month: number
  received_this_month: number
  typical_monthly_spend: number
  typical_monthly_income: number
  income_still_expected: number
  committed_upcoming_total: number
  committed_upcoming: {
    merchant: string
    amount: number
    due: string
    category: string
    cadence: string
  }[]
  projected_month_end_spend: number
  projected_month_end_net: number
  available_balance: number | null
  safe_to_spend_total: number
  safe_to_spend_daily: number
  /** "low" means one month of history or less - the UI must say so, not imply rigour. */
  confidence: 'low' | 'medium' | 'high'
}

// ── Anomalies ────────────────────────────────────────────────────────────────

export interface BudgetAnomaly {
  type: 'duplicate_charge' | 'category_spike' | 'large_new_merchant'
  severity: 'high' | 'medium' | 'low'
  title: string
  detail: string
  amount: number
  date: string
  merchant?: string | null
  category?: string
  baseline?: number
  txn_ids?: string[]
}

export interface BudgetAnomaliesResponse {
  anomalies: BudgetAnomaly[]
  count: number
  high_severity_count: number
}

// ── Reconciliation and coverage ──────────────────────────────────────────────

export interface BudgetReconciliationAccount {
  account_key: string
  rows_checked: number
  breaks: { date: string; expected_balance: number; actual_balance: number; drift: number }[]
  break_count: number
  opening_balance: number
  closing_balance: number
  status: 'reconciled' | 'gaps_found'
  unexplained_total: number
}

export interface BudgetReconciliationResponse {
  accounts: BudgetReconciliationAccount[]
  checked: number
  reconciled: number
  status: 'reconciled' | 'gaps_found' | 'no_balance_data'
  /** Accounts whose export carried no balance column and so could not be checked. */
  unverifiable_accounts: string[]
}

export interface BudgetCoverageAccount {
  account_key: string
  label: string
  months_covered: string[]
  missing_months: string[]
  first_txn: string | null
  last_txn: string | null
  complete: boolean
}

export interface BudgetCoverageResponse {
  accounts: BudgetCoverageAccount[]
  complete: boolean
  total_missing_months: number
}

// ── Sankey and net worth ─────────────────────────────────────────────────────

export interface BudgetSankey {
  nodes: { name: string; group: string }[]
  links: { source: number; target: number; value: number }[]
}

// BudgetNetWorth was removed with the cross-domain net-worth endpoint. It was the only
// budget type that named other domains (`domain: 'mutual_funds' | 'equity' | ...`,
// `unavailable_domains`). Deposit and card totals come from BudgetAccountsResponse.

// ── Envelopes ────────────────────────────────────────────────────────────────

export interface BudgetEnvelope {
  category: string
  monthly_cap: number
  spent: number
  remaining: number
  used_pct: number
  month_progress_pct: number
  status: 'on_track' | 'slightly_ahead' | 'ahead_of_pace' | 'over'
  daily_allowance: number
  projected_month_end: number
}
