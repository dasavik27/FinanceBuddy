import axios from 'axios'
import { useAppStore } from '../store/appStore'
import authClient from '../auth/authClient'
import type {
  ParseResponse, Summary, OverviewData, Holding, FundResult,
  PerformanceData, AllocationData, InsightsData,
} from './types'
import type {
  EquityAllocation, EquityHoldingsResponse, EquityInsights, EquityPerformance,
  EquityPnl, EquitySummary, EquityUploadResult, MarketIndex, StockAnalysis, StockSearchResult,
} from '../../domains/equity/types'
import type {
  BudgetCategoriesResponse, BudgetMatchTypes, BudgetOverview, BudgetRule,
  BudgetRuleDraft, BudgetRuleTestResult, BudgetSessionMeta, BudgetTransaction,
  BudgetTransactionsPage, BudgetTransactionUpdate, BudgetUploadResult,
  BudgetAccountsResponse, BudgetAccountMetaUpdate, BudgetTransfersResponse,
  BudgetRecurringResponse, BudgetForecast, BudgetAnomaliesResponse,
  BudgetReconciliationResponse, BudgetCoverageResponse, BudgetSankey,
  BudgetEnvelope,
} from '../../domains/budget/types'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' })

/**
 * Attach the signed-in user's bearer token.
 *
 * Async because the token comes from the auth client's getSession(), which
 * refreshes it when it is close to expiry - caching it here would reintroduce the
 * expired-token logout. There is no PAN fallback: Google is the only credential.
 */
api.interceptors.request.use(async (config) => {
  const token = await authClient.getAccessToken()
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

/**
 * A 401 means the credential is gone or no longer valid, so clear local state
 * rather than leaving the UI showing a signed-in shell over failing requests.
 */
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      const store = useAppStore.getState()
      if (store.pan || store.userId) {
        store.clearIdentity()
      }
    }
    return Promise.reject(error)
  },
)

// ── API calls ────────────────────────────────────────────────────────────────
export const apiClient = {
  /** Parses CAS PDF statement and initializes a portfolio session. */
  parseFile: async (file: File, password: string, uploadType: string = 'mutual_funds'): Promise<ParseResponse> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', password)
    const { data } = await api.post<ParseResponse>('/mutual-funds/portfolio/parse', fd, {
      headers: {
        'X-Upload-Type': uploadType
      }
    })
    return data
  },

  getHistory: async (uploadType: string = 'mutual_funds'): Promise<any> => {
    const { data } = await api.get('/history/', {
      headers: {
        'X-Upload-Type': uploadType
      }
    })
    return data
  },

  /** Fetches high-level executive summary metrics (XIRR, Total Value). */
  getSummary: async (sid: string, params: Record<string, any> = {}): Promise<Summary> => {
    const { data } = await api.get<Summary>(`/mutual-funds/overview/${sid}/summary`, { params })
    return data
  },

  syncPortfolio: async (sid: string): Promise<any> => {
    const { data } = await api.post(`/mutual-funds/portfolio/${sid}/sync`)
    return data
  },

  /** Retrieves core time-series charting data for the overview dashboard. */
  getOverview: async (sid: string, params: Record<string, any> = {}): Promise<OverviewData> => {
    const { data } = await api.get<OverviewData>(`/mutual-funds/overview/${sid}/overview`, { params })
    return data
  },

  getBenchmarkOverlay: async (sid: string, params: { period: string; benchmarks: string }): Promise<{ dates: string[]; series: Record<string, number[]> }> => {
    const { data } = await api.get<{ dates: string[]; series: Record<string, number[]> }>(`/mutual-funds/overview/${sid}/benchmark-overlay`, { params })
    return data
  },

  getHoldings: async (sid: string, params: Record<string, any> = {}): Promise<{ holdings: Holding[]; total: number; cap_types: string[] }> => {
    const { data } = await api.get(`/mutual-funds/holdings/${sid}/holdings`, { params })
    return data
  },

  getAllocation: async (sid: string, params: Record<string, any> = {}): Promise<AllocationData> => {
    const { data } = await api.get<AllocationData>(`/mutual-funds/overview/${sid}/allocation`, { params })
    return data
  },

  /** Executes multi-metric peer comparison and calculates Portfolio Health Score. */
  getPerformance: async (sid: string, params: Record<string, any> = {}): Promise<PerformanceData> => {
    const { data } = await api.get<PerformanceData>(`/mutual-funds/performance/${sid}/performance`, { params })
    return data
  },

  getRebalancePlan: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/rebalance/${sid}/plan`, { params })
    return data
  },

  getTaxHarvest: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/tax-harvest`)
    return data
  },

  getSipProjection: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/sip-projection`, { params })
    return data
  },

  getXirrByFy: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/xirr-by-fy`)
    return data
  },

  getSipAttribution: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/sip-attribution`)
    return data
  },

  getWhatIf: async (sid: string, params: Record<string, any>): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/what-if`, { params })
    return data
  },

  getMandateOverlap: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/mandate-overlap`)
    return data
  },


  getInsights: async (sid: string, params: Record<string, any> = {}): Promise<InsightsData> => {
    const { data } = await api.get<InsightsData>(`/mutual-funds/insights/${sid}/insights`, { params })
    return data
  },

  getJourney: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/journey/${sid}`)
    return data
  },

  getFundInsights: async (sid: string, isin: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/holdings/${sid}/fund-insights/${isin}`, { params })
    return data
  },

  getTransactions: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/holdings/${sid}/transactions`, { params })
    return data
  },


  getCategoryPeers: async (category: string): Promise<{ peers: any[], fallback_triggered?: boolean }> => {
    const { data } = await api.get('/mutual-funds/compare/peers', { params: { category } })
    return data
  },

  searchTicker: async (q: string): Promise<any> => {
    const { data } = await api.get('/mutual-funds/compare/search', { params: { q } })
    return data
  },

  getBenchmarkHistory: async (ticker: string, days = 365): Promise<any> => {
    const { data } = await api.get('/mutual-funds/compare/history', { params: { ticker, days } })
    return data
  },

  getRollingReturns: async (sid: string, isin: string, window = 3): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/performance/${sid}/rolling/${isin}`, { params: { window } })
    return data
  },

  getMarketSummary: async (): Promise<any> => {
    const { data } = await api.get('/market/summary')
    return data
  },

  getMarketConfig: async (): Promise<{ cache_ttl: number }> => {
    const { data } = await api.get('/market/config')
    return data
  },

  updateMarketConfig: async (ttl: number): Promise<any> => {
    const { data } = await api.post(`/market/config?ttl=${ttl}`)
    return data
  },

  // ── Tax Expert API ──────────────────────────────────────────────────────

  /** Parse AIS PDF and create a tax computation session. */
  parseAIS: async (file: File): Promise<any> => {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post('/tax-expert/parse-ais', fd)
    return data
  },

  reconcileBrokerFile: async (sessionId: string, file: File): Promise<any> => {
    const fd = new FormData()
    fd.append('broker_file', file)
    const res = await api.post(`/tax-expert/${sessionId}/tax/reconcile-broker`, fd)
    return res.data
  },
  
  // ── Accounts / Vault Manager ───────────────────────────────────────────────
  getAccountsSummary: async (): Promise<any> => {
    const res = await api.get('/accounts/summary')
    return res.data
  },
  
  /** Permanently delete the signed-in account. Takes no target - see DELETE /accounts/me. */
  purgeAccount: async (): Promise<any> => {
    const res = await api.delete('/accounts/me')
    return res.data
  },

  /** Everything the server holds about the caller, as one JSON document. */
  exportAccount: async (): Promise<any> => {
    const res = await api.get('/accounts/me/export')
    return res.data
  },

  // limit is explicit and set to the server's maximum. The endpoint is paginated
  // (it AES-decrypts one metrics blob per row, so an unbounded read got slower for
  // the life of the account) and defaults to 50 — but nothing here has paging UI, so
  // relying on that default would silently hide a user's 51st tax session. Asking for
  // the cap keeps the previous behaviour for any realistic history while the server
  // stays bounded. `has_more` is returned; wire it to a "load more" if that ever trips.
  getTaxHistory: async (
    limit = 200, offset = 0,
  ): Promise<{ sessions: any[]; has_more?: boolean; limit?: number; offset?: number }> => {
    const { data } = await api.get('/tax-expert/tax-history', { params: { limit, offset } })
    return data
  },

  deleteTaxSession: async (sid: string): Promise<any> => {
    const { data } = await api.delete(`/tax-expert/tax-history/${sid}`)
    return data
  },

  /** The signed-in account, or 401. */
  getMe: async (): Promise<{ user_id: string; pan: string | null }> => {
    const { data } = await api.get('/auth/me')
    return data
  },

  /** Attach a PAN after signing in - still needed for the CAS password default. */
  setProfilePan: async (pan: string): Promise<any> => {
    const { data } = await api.put('/auth/profile/pan', { pan })
    return data
  },

  clearSystemCaches: async (): Promise<any> => {
    const res = await api.post('/accounts/clear_caches')
    return res.data
  },

  uploadITR: async (sid: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post(`/tax-expert/${sid}/tax/itr`, fd)
    return data
  },

  getITRData: async (sid: string) => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/itr`)
    return data.itr_data
  },

  /** Get complete tax computation summary for a given regime. */
  getTaxExpertSummary: async (sid: string, regime: string = 'new'): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/summary`, { params: { regime } })
    return data
  },

  /** Get detailed income breakdown from AIS data. */
  getTaxExpertIncome: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/income`)
    return data
  },

  /** Get detailed capital gains breakdown. */
  getTaxExpertCapitalGains: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/capital-gains`)
    return data
  },

  updateTransactionCost: async (sid: string, category: string, sr: number, new_cost: number): Promise<any> => {
    const { data } = await api.post(`/tax-expert/${sid}/tax/capital-gains/transaction`, { category, sr, new_cost })
    return data
  },

  postTaxOverrides: async (sid: string, overrides: any, regime?: string): Promise<any> => {
    const url = regime ? `/tax-expert/${sid}/tax/recalculate?regime=${regime}` : `/tax-expert/${sid}/tax/recalculate`
    const { data } = await api.post(url, overrides)
    return data
  },

  /** Compare Old vs New regime side-by-side. */
  compareTaxRegimes: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/compare-regimes`)
    return data
  },

  /**
   * Display-only tax rules and tooltip copy.
   *
   * Replaces the frontend's own copy of tax_rules.json, which was byte-identical
   * to the backend's with no sync mechanism. Session-independent and static per
   * deployment, so it is cached indefinitely.
   */
  getTaxRules: async (): Promise<any> => {
    const { data } = await api.get('/tax-expert/rules')
    return data
  },

  /** Paginated access to a detail list no longer inlined in /tax/summary. */
  getTaxDetails: async (sid: string, bucket: string, offset = 0, limit = 200): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/details/${bucket}`, {
      params: { offset, limit },
    })
    return data
  },

  // ── Equity API ──────────────────────────────────────────────────────────────

  /** Upload a Zerodha/Groww Holdings CSV (and optionally a Tradebook CSV). */
  parseEquityCsv: async (holdingsFile: File, tradebookFile?: File): Promise<EquityUploadResult> => {
    const fd = new FormData()
    fd.append('file', holdingsFile)
    if (tradebookFile) fd.append('tradebook', tradebookFile)
    const { data } = await api.post('/equity/portfolio/parse', fd)
    return data
  },

  /**
   * Get Zerodha OAuth login URL, plus the `state` that binds the return leg to this
   * browser. Stash the state and hand it back to connectKite.
   */
  getKiteLoginUrl: async (): Promise<{ login_url: string; state: string }> => {
    const { data } = await api.get('/equity/portfolio/kite/login-url')
    return data
  },

  /**
   * Exchange Zerodha request_token for an access_token and sync holdings.
   *
   * `state` is required: without it the endpoint accepts any request_token from
   * anybody, so a victim induced to submit an attacker's token would ingest the
   * attacker's holdings into their own account.
   */
  connectKite: async (requestToken: string, state: string): Promise<EquityUploadResult> => {
    const fd = new FormData()
    fd.append('request_token', requestToken)
    fd.append('state', state)
    const { data } = await api.post('/equity/portfolio/kite/connect', fd)
    return data
  },

  /** Re-fetch live prices for all equity holdings. */
  syncEquity: async (sid: string): Promise<any> => {
    const { data } = await api.post(`/equity/portfolio/${sid}/sync`)
    return data
  },

  /** Equity portfolio summary KPIs. */
  getEquitySummary: async (sid: string): Promise<EquitySummary> => {
    const { data } = await api.get(`/equity/overview/${sid}/summary`)
    return data
  },

  /** Equity sector allocation. */
  getEquityAllocation: async (sid: string): Promise<EquityAllocation> => {
    const { data } = await api.get(`/equity/overview/${sid}/allocation`)
    return data
  },

  /** Equity holdings table. */
  getEquityHoldings: async (sid: string, params: Record<string, any> = {}): Promise<EquityHoldingsResponse> => {
    const { data } = await api.get(`/equity/holdings/${sid}/holdings`, { params })
    return data
  },

  /** Equity P&L analysis (STCG/LTCG). */
  getEquityPnl: async (sid: string): Promise<EquityPnl> => {
    const { data } = await api.get(`/equity/holdings/${sid}/pnl`)
    return data
  },

  /** Portfolio vs benchmark performance over time. */
  getEquityPerformance: async (sid: string, params: Record<string, any> = {}): Promise<EquityPerformance> => {
    const { data } = await api.get(`/equity/performance/${sid}/performance`, { params })
    return data
  },

  /** Smart insights: top movers, concentrated positions, tax-loss harvest. */
  getEquityInsights: async (sid: string): Promise<EquityInsights> => {
    const { data } = await api.get(`/equity/insights/${sid}/insights`)
    return data
  },

  /** Fetch live benchmark indices (NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT). */
  getMarketIndices: async (): Promise<{ indices: MarketIndex[] }> => {
    const { data } = await api.get('/equity/analyzer/indices')
    return data
  },

  /** Search NSE stocks by symbol or name. */
  searchStocks: async (q: string): Promise<{ results: StockSearchResult[] }> => {
    const { data } = await api.get('/equity/analyzer/search', { params: { q } })
    return data
  },

  /** Full fundamental + technical analysis for a stock. */
  analyzeStock: async (symbol: string): Promise<StockAnalysis> => {
    const { data } = await api.get(`/equity/analyzer/analyze/${symbol}`)
    return data
  },

  /** Simulate portfolio impact of buying a stock. */
  stockPortfolioImpact: async (symbol: string, amount: number, sessionId?: string): Promise<any> => {
    const { data } = await api.post('/equity/analyzer/impact', { symbol, amount, session_id: sessionId })
    return data
  },

  getEquityHistory: async (): Promise<any> => {
    const { data } = await api.get('/history/', { headers: { 'x-upload-type': 'equity' } })
    return data
  },

  deleteHistorySession: async (sid: string): Promise<any> => {
    const { data } = await api.delete(`/history/${sid}`)
    return data
  },

  // ── Budget API ──────────────────────────────────────────────────────────────

  /**
   * Upload a bank / credit-card statement (CSV, XLS, XLSX).
   *
   * Returns the parse report alongside the session id: `skipped` and `truncated` are
   * how the caller learns that only part of the file made it in.
   */
  uploadBudgetStatement: async (
    file: File,
    bank: string = 'auto',
    accountType: string = 'auto',
  ): Promise<BudgetUploadResult> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('bank', bank)
    fd.append('account_type', accountType)
    const { data } = await api.post<BudgetUploadResult>('/budget/portfolio/upload', fd)
    return data
  },

  /** Headline cash-flow KPIs, trends and the 50/30/20 evaluation. */
  getBudgetOverview: async (sid: string, params: Record<string, any> = {}): Promise<BudgetOverview> => {
    const { data } = await api.get<BudgetOverview>(`/budget/analytics/${sid}/overview`, { params })
    return data
  },

  /** Category breakdown, or a single-category drilldown when `category` is set. */
  getBudgetCategories: async (sid: string, params: Record<string, any> = {}): Promise<BudgetCategoriesResponse> => {
    const { data } = await api.get<BudgetCategoriesResponse>(`/budget/analytics/${sid}/categories`, { params })
    return data
  },

  /**
   * A page of transactions.
   *
   * Returns the whole envelope rather than just the rows: the endpoint is paginated,
   * and a caller that drops `total` cannot tell a complete result from a truncated
   * one. Discarding it would silently show the first page as if it were everything.
   */
  getBudgetTransactions: async (
    sid: string, params: Record<string, any> = {},
  ): Promise<BudgetTransactionsPage> => {
    const { data } = await api.get<BudgetTransactionsPage>(
      `/budget/analytics/${sid}/transactions`, { params },
    )
    return {
      transactions: data.transactions ?? [],
      total: data.total ?? (data.transactions?.length ?? 0),
      limit: data.limit ?? 0,
      offset: data.offset ?? 0,
      has_more: data.has_more ?? false,
    }
  },

  updateBudgetTransactions: async (updates: BudgetTransactionUpdate[]): Promise<any> => {
    // The router is mounted at /budget/analytics, so the route is
    // /budget/analytics/transactions/update. This was '/budget/transactions/update'
    // from the day the domain landed - a 404 on every call, which is why editing a
    // category or running a bulk re-categorization never actually persisted.
    const { data } = await api.put('/budget/analytics/transactions/update', updates)
    return data
  },

  getBudgetSessions: async (): Promise<BudgetSessionMeta[]> => {
    const { data } = await api.get<{ sessions: BudgetSessionMeta[] }>('/budget/portfolio/sessions')
    return data.sessions ?? []
  },

  // ── Accounts and cards ─────────────────────────────────────────────────────

  getBudgetAccounts: async (sid = 'overall'): Promise<BudgetAccountsResponse> => {
    const { data } = await api.get<BudgetAccountsResponse>('/budget/accounts', {
      params: { session_id: sid },
    })
    return data
  },

  /** Writes only what a statement cannot say: limit, statement/due day, label. */
  updateBudgetAccount: async (
    accountKey: string, patch: BudgetAccountMetaUpdate,
  ): Promise<{ status: string; account_key: string }> => {
    // encodeURIComponent because account_key contains colons ("HDFC:savings:1234").
    const { data } = await api.put(`/budget/accounts/${encodeURIComponent(accountKey)}`, patch)
    return data
  },

  // ── Insights ───────────────────────────────────────────────────────────────

  getBudgetTransfers: async (sid: string): Promise<BudgetTransfersResponse> => {
    const { data } = await api.get<BudgetTransfersResponse>(`/budget/insights/${sid}/transfers`)
    return data
  },

  flagBudgetTransfer: async (txnId: string, flag: string | null): Promise<any> => {
    const { data } = await api.post('/budget/insights/transfers/flag', { txn_id: txnId, flag })
    return data
  },

  getBudgetRecurring: async (sid: string): Promise<BudgetRecurringResponse> => {
    const { data } = await api.get<BudgetRecurringResponse>(`/budget/insights/${sid}/recurring`)
    return data
  },

  getBudgetForecast: async (sid: string): Promise<BudgetForecast> => {
    const { data } = await api.get<BudgetForecast>(`/budget/insights/${sid}/forecast`)
    return data
  },

  getBudgetAnomalies: async (sid: string): Promise<BudgetAnomaliesResponse> => {
    const { data } = await api.get<BudgetAnomaliesResponse>(`/budget/insights/${sid}/anomalies`)
    return data
  },

  getBudgetReconciliation: async (sid: string): Promise<BudgetReconciliationResponse> => {
    const { data } = await api.get<BudgetReconciliationResponse>(
      `/budget/insights/${sid}/reconciliation`,
    )
    return data
  },

  getBudgetCoverage: async (sid: string): Promise<BudgetCoverageResponse> => {
    const { data } = await api.get<BudgetCoverageResponse>(`/budget/insights/${sid}/coverage`)
    return data
  },

  getBudgetSankey: async (sid: string): Promise<BudgetSankey> => {
    const { data } = await api.get<BudgetSankey>(`/budget/insights/${sid}/sankey`)
    return { nodes: data.nodes ?? [], links: data.links ?? [] }
  },

  getBudgetEnvelopes: async (sid: string): Promise<BudgetEnvelope[]> => {
    const { data } = await api.get<{ envelopes: BudgetEnvelope[] }>(
      `/budget/insights/${sid}/envelopes`,
    )
    return data.envelopes ?? []
  },

  /** A null cap clears the envelope rather than setting it to zero. */
  setBudgetEnvelope: async (category: string, monthlyCap: number | null): Promise<any> => {
    const { data } = await api.put('/budget/insights/envelopes', {
      category, monthly_cap: monthlyCap,
    })
    return data
  },

  renameBudgetMerchant: async (description: string, displayName: string): Promise<any> => {
    const { data } = await api.put('/budget/insights/merchants/alias', {
      description, display_name: displayName,
    })
    return data
  },

  deleteBudgetSession: async (sid: string): Promise<any> => {
    const { data } = await api.delete(`/budget/portfolio/sessions/${sid}`)
    return data
  },

  getBudgetRules: async (): Promise<BudgetRule[]> => {
    const { data } = await api.get<BudgetRule[]>('/budget/rules')
    return data
  },

  createBudgetRule: async (rule: BudgetRuleDraft): Promise<BudgetRule> => {
    const { data } = await api.post<BudgetRule>('/budget/rules', rule)
    return data
  },

  deleteBudgetRule: async (ruleId: string): Promise<any> => {
    const { data } = await api.delete(`/budget/rules/${ruleId}`)
    return data
  },

  applyBudgetRules: async (): Promise<{ transactions_recalculated: number }> => {
    const { data } = await api.post('/budget/rules/apply-all')
    return data
  },

  /**
   * Check one pattern against one description without storing it.
   *
   * Server-side on purpose: compiling user regexes in the browser is where a saved
   * `(a+)+$` froze the rules tab on every keystroke.
   */
  testBudgetRule: async (rule: BudgetRuleDraft, description: string): Promise<BudgetRuleTestResult> => {
    const { data } = await api.post<BudgetRuleTestResult>('/budget/rules/test', rule, {
      params: { description },
    })
    return data
  },

  /** The match types the server accepts, so the dropdown cannot drift from them. */
  getBudgetMatchTypes: async (): Promise<BudgetMatchTypes> => {
    const { data } = await api.get<BudgetMatchTypes>('/budget/rules/match-types')
    return data
  },
}

export default api