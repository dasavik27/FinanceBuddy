import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiClient, api } from './client'
import authClient from '../auth/authClient'
import { useAppStore } from '../store/appStore'

describe('apiClient & Interceptors', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAppStore.getState().clearIdentity()
  })

  describe('Interceptors', () => {
    it('request interceptor attaches Bearer token when available', async () => {
      vi.spyOn(authClient, 'getAccessToken').mockResolvedValue('jwt-test-123')
      const config = { headers: {} as Record<string, string> }
      
      const requestHandler = (api.interceptors.request as any).handlers[0].fulfilled
      const result = await requestHandler(config)

      expect(result.headers['Authorization']).toBe('Bearer jwt-test-123')
    })

    it('request interceptor skips Bearer header when token is null', async () => {
      vi.spyOn(authClient, 'getAccessToken').mockResolvedValue(null)
      const config = { headers: {} as Record<string, string> }

      const requestHandler = (api.interceptors.request as any).handlers[0].fulfilled
      const result = await requestHandler(config)

      expect(result.headers['Authorization']).toBeUndefined()
    })

    it('response interceptor passes through successful responses', () => {
      const response = { status: 200, data: { ok: true } }
      const responseHandler = (api.interceptors.response as any).handlers[0].fulfilled
      expect(responseHandler(response)).toBe(response)
    })

    it('response interceptor handles 401 error by signing out and clearing store identity', async () => {
      useAppStore.getState().setIdentity({ userId: 'u1', email: 'test@example.com', status: 'active' })
      const signOutSpy = vi.spyOn(authClient, 'signOut').mockResolvedValue()

      const errorHandler = (api.interceptors.response as any).handlers[0].rejected
      const error401 = { response: { status: 401, data: { detail: 'Unauthorized' } } }

      await expect(errorHandler(error401)).rejects.toBe(error401)
      expect(signOutSpy).toHaveBeenCalled()
      expect(useAppStore.getState().userId).toBeNull()
    })

    it('response interceptor handles 401 error when signOut throws without unhandled crash', async () => {
      useAppStore.getState().setIdentity({ userId: 'u1', email: 'test@example.com', status: 'active' })
      vi.spyOn(authClient, 'signOut').mockRejectedValue(new Error('Network failure during signOut'))

      const errorHandler = (api.interceptors.response as any).handlers[0].rejected
      const error401 = { response: { status: 401 } }

      await expect(errorHandler(error401)).rejects.toBe(error401)
    })

    it('response interceptor passes through non-401 errors', async () => {
      const errorHandler = (api.interceptors.response as any).handlers[0].rejected
      const error500 = { response: { status: 500, data: { detail: 'Server Error' } } }

      await expect(errorHandler(error500)).rejects.toBe(error500)
    })
  })

  describe('API Methods', () => {
    beforeEach(() => {
      vi.spyOn(api, 'get').mockResolvedValue({ data: { success: true } })
      vi.spyOn(api, 'post').mockResolvedValue({ data: { success: true } })
      vi.spyOn(api, 'put').mockResolvedValue({ data: { success: true } })
      vi.spyOn(api, 'patch').mockResolvedValue({ data: { success: true } })
      vi.spyOn(api, 'delete').mockResolvedValue({ data: { success: true } })
    })

    it('Mutual funds endpoints', async () => {
      const file = new File(['test'], 'cas.pdf')
      await apiClient.parseFile(file, 'pass123')
      expect(api.post).toHaveBeenCalledWith('/mutual-funds/portfolio/parse', expect.any(FormData), expect.any(Object))

      await apiClient.getHistory('mutual_funds')
      expect(api.get).toHaveBeenCalledWith('/history/', expect.any(Object))

      await apiClient.getSummary('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/overview/sid-1/summary', expect.any(Object))

      await apiClient.syncPortfolio('sid-1')
      expect(api.post).toHaveBeenCalledWith('/mutual-funds/portfolio/sid-1/sync')

      await apiClient.getOverview('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/overview/sid-1/overview', expect.any(Object))

      await apiClient.getBenchmarkOverlay('sid-1', { period: '1Y', benchmarks: 'NIFTY50' })
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/overview/sid-1/benchmark-overlay', expect.any(Object))

      await apiClient.getHoldings('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/holdings/sid-1/holdings', expect.any(Object))

      await apiClient.getAllocation('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/overview/sid-1/allocation', expect.any(Object))

      await apiClient.getPerformance('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/performance/sid-1/performance', expect.any(Object))

      await apiClient.getRebalancePlan('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/rebalance/sid-1/plan', expect.any(Object))

      await apiClient.getTaxHarvest('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/planning/sid-1/tax-harvest')

      await apiClient.getSipProjection('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/planning/sid-1/sip-projection', expect.any(Object))

      await apiClient.getXirrByFy('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/planning/sid-1/xirr-by-fy')

      await apiClient.getSipAttribution('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/planning/sid-1/sip-attribution')

      await apiClient.getWhatIf('sid-1', { years: 5 })
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/planning/sid-1/what-if', expect.any(Object))

      await apiClient.getMandateOverlap('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/planning/sid-1/mandate-overlap')

      await apiClient.getInsights('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/insights/sid-1/insights', expect.any(Object))

      await apiClient.getJourney('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/journey/sid-1')

      await apiClient.getFundInsights('sid-1', 'INF179K01BE2')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/holdings/sid-1/fund-insights/INF179K01BE2', expect.any(Object))

      await apiClient.getTransactions('sid-1')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/holdings/sid-1/transactions', expect.any(Object))

      await apiClient.getCategoryPeers('Large Cap')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/compare/peers', expect.any(Object))

      await apiClient.searchTicker('HDFC')
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/compare/search', expect.any(Object))

      await apiClient.getBenchmarkHistory('NIFTY50', 180)
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/compare/history', expect.any(Object))

      await apiClient.getRollingReturns('sid-1', 'INF179K01BE2', 5)
      expect(api.get).toHaveBeenCalledWith('/mutual-funds/performance/sid-1/rolling/INF179K01BE2', expect.any(Object))

      await apiClient.getMarketSummary()
      expect(api.get).toHaveBeenCalledWith('/market/summary')

      await apiClient.getMarketConfig()
      expect(api.get).toHaveBeenCalledWith('/market/config')

      await apiClient.updateMarketConfig(600)
      expect(api.post).toHaveBeenCalledWith('/market/config?ttl=600')
    })

    it('Equity endpoints', async () => {
      const file = new File(['eq'], 'eq.csv')
      const tradebook = new File(['tb'], 'tb.csv')
      await apiClient.parseEquityCsv(file, tradebook)
      expect(api.post).toHaveBeenCalledWith('/equity/portfolio/parse', expect.any(FormData))

      await apiClient.getKiteLoginUrl()
      expect(api.get).toHaveBeenCalledWith('/equity/portfolio/kite/login-url')

      await apiClient.connectKite('token-123', 'state-abc')
      expect(api.post).toHaveBeenCalledWith('/equity/portfolio/kite/connect', expect.any(FormData))

      await apiClient.syncEquity('eq-1')
      expect(api.post).toHaveBeenCalledWith('/equity/portfolio/eq-1/sync')

      await apiClient.getEquitySummary('eq-1')
      expect(api.get).toHaveBeenCalledWith('/equity/overview/eq-1/summary')

      await apiClient.getEquityAllocation('eq-1')
      expect(api.get).toHaveBeenCalledWith('/equity/overview/eq-1/allocation')

      await apiClient.getEquityHoldings('eq-1')
      expect(api.get).toHaveBeenCalledWith('/equity/holdings/eq-1/holdings', expect.any(Object))

      await apiClient.getEquityPnl('eq-1')
      expect(api.get).toHaveBeenCalledWith('/equity/holdings/eq-1/pnl')

      await apiClient.getEquityPerformance('eq-1')
      expect(api.get).toHaveBeenCalledWith('/equity/performance/eq-1/performance', expect.any(Object))

      await apiClient.getEquityInsights('eq-1')
      expect(api.get).toHaveBeenCalledWith('/equity/insights/eq-1/insights')

      await apiClient.getMarketIndices()
      expect(api.get).toHaveBeenCalledWith('/equity/analyzer/indices')

      await apiClient.searchStocks('RELIANCE')
      expect(api.get).toHaveBeenCalledWith('/equity/analyzer/search', expect.any(Object))

      await apiClient.analyzeStock('TCS')
      expect(api.get).toHaveBeenCalledWith('/equity/analyzer/analyze/TCS')

      await apiClient.stockPortfolioImpact('TCS', 50000, 'eq-1')
      expect(api.post).toHaveBeenCalledWith('/equity/analyzer/impact', { symbol: 'TCS', amount: 50000, session_id: 'eq-1' })

      await apiClient.getEquityHistory()
      expect(api.get).toHaveBeenCalledWith('/history/', { headers: { 'x-upload-type': 'equity' } })

      await apiClient.deleteHistorySession('eq-1')
      expect(api.delete).toHaveBeenCalledWith('/history/eq-1')
    })

    it('Budget endpoints', async () => {
      const file = new File(['csv'], 'statement.csv')
      await apiClient.uploadBudgetStatement(file, 'HDFC', 'savings')
      expect(api.post).toHaveBeenCalledWith('/budget/portfolio/upload', expect.any(FormData))

      await apiClient.getBudgetOverview('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/analytics/b-1/overview', expect.any(Object))

      await apiClient.getBudgetCategories('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/analytics/b-1/categories', expect.any(Object))

      vi.mocked(api.get).mockResolvedValueOnce({ data: { transactions: [{ id: '1' }], total: 1, limit: 10, offset: 0, has_more: false } })
      const tx = await apiClient.getBudgetTransactions('b-1')
      expect(tx.total).toBe(1)
      expect(api.get).toHaveBeenCalledWith('/budget/analytics/b-1/transactions', expect.any(Object))

      vi.mocked(api.get).mockResolvedValueOnce({ data: {} })
      const txEmpty = await apiClient.getBudgetTransactions('b-1')
      expect(txEmpty.total).toBe(0)

      await apiClient.updateBudgetTransactions([{ id: 'tx-1', category: 'Dining' } as any])
      expect(api.put).toHaveBeenCalledWith('/budget/analytics/transactions/update', expect.any(Array))

      vi.mocked(api.get).mockResolvedValueOnce({ data: { sessions: [{ id: 'b-1' }] } })
      const sessions = await apiClient.getBudgetSessions()
      expect(sessions.length).toBe(1)

      vi.mocked(api.get).mockResolvedValueOnce({ data: {} })
      const sessionsEmpty = await apiClient.getBudgetSessions()
      expect(sessionsEmpty.length).toBe(0)

      await apiClient.getBudgetAccounts('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/accounts', expect.any(Object))

      await apiClient.updateBudgetAccount('HDFC:savings:1234', { label: 'My Acc' })
      expect(api.put).toHaveBeenCalledWith('/budget/accounts/HDFC%3Asavings%3A1234', { label: 'My Acc' })

      await apiClient.getBudgetTransfers('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/insights/b-1/transfers')

      await apiClient.flagBudgetTransfer('tx-1', 'exclude')
      expect(api.post).toHaveBeenCalledWith('/budget/insights/transfers/flag', { txn_id: 'tx-1', flag: 'exclude' })

      await apiClient.getBudgetRecurring('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/insights/b-1/recurring')

      await apiClient.getBudgetForecast('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/insights/b-1/forecast')

      await apiClient.getBudgetAnomalies('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/insights/b-1/anomalies')

      await apiClient.getBudgetReconciliation('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/insights/b-1/reconciliation')

      await apiClient.getBudgetCoverage('b-1')
      expect(api.get).toHaveBeenCalledWith('/budget/insights/b-1/coverage')

      vi.mocked(api.get).mockResolvedValueOnce({ data: { nodes: [{ name: 'Income' }], links: [] } })
      const sankey = await apiClient.getBudgetSankey('b-1')
      expect(sankey.nodes.length).toBe(1)

      vi.mocked(api.get).mockResolvedValueOnce({ data: {} })
      const sankeyEmpty = await apiClient.getBudgetSankey('b-1')
      expect(sankeyEmpty.nodes.length).toBe(0)

      vi.mocked(api.get).mockResolvedValueOnce({ data: { envelopes: [{ category: 'Food' }] } })
      const env = await apiClient.getBudgetEnvelopes('b-1')
      expect(env.length).toBe(1)

      vi.mocked(api.get).mockResolvedValueOnce({ data: {} })
      const envEmpty = await apiClient.getBudgetEnvelopes('b-1')
      expect(envEmpty.length).toBe(0)

      await apiClient.setBudgetEnvelope('Dining', 15000)
      expect(api.put).toHaveBeenCalledWith('/budget/insights/envelopes', { category: 'Dining', monthly_cap: 15000 })

      await apiClient.renameBudgetMerchant('SWIGGY BANGALORE', 'Swiggy')
      expect(api.put).toHaveBeenCalledWith('/budget/insights/merchants/alias', { description: 'SWIGGY BANGALORE', display_name: 'Swiggy' })

      await apiClient.deleteBudgetSession('b-1')
      expect(api.delete).toHaveBeenCalledWith('/budget/portfolio/sessions/b-1')

      await apiClient.getBudgetRules()
      expect(api.get).toHaveBeenCalledWith('/budget/rules')

      await apiClient.createBudgetRule({ pattern: 'UBER', category: 'Travel', match_type: 'contains' })
      expect(api.post).toHaveBeenCalledWith('/budget/rules', { pattern: 'UBER', category: 'Travel', match_type: 'contains' })

      await apiClient.deleteBudgetRule('r-1')
      expect(api.delete).toHaveBeenCalledWith('/budget/rules/r-1')

      await apiClient.applyBudgetRules()
      expect(api.post).toHaveBeenCalledWith('/budget/rules/apply-all')

      await apiClient.testBudgetRule({ pattern: 'UBER', category: 'Travel', match_type: 'contains' }, 'UBER TRIP')
      expect(api.post).toHaveBeenCalledWith('/budget/rules/test', { pattern: 'UBER', category: 'Travel', match_type: 'contains' }, { params: { description: 'UBER TRIP' } })

      await apiClient.getBudgetMatchTypes()
      expect(api.get).toHaveBeenCalledWith('/budget/rules/match-types')
    })

    it('Tax Expert endpoints', async () => {
      const file = new File(['ais'], 'ais.pdf')
      await apiClient.parseAIS(file)
      expect(api.post).toHaveBeenCalledWith('/tax-expert/parse-ais', expect.any(FormData))

      const brokerFile = new File(['broker'], 'broker.xlsx')
      await apiClient.reconcileBrokerFile('tax-1', brokerFile)
      expect(api.post).toHaveBeenCalledWith('/tax-expert/tax-1/tax/reconcile-broker', expect.any(FormData))

      await apiClient.getTaxHistory(50, 10)
      expect(api.get).toHaveBeenCalledWith('/tax-expert/tax-history', { params: { limit: 50, offset: 10 } })

      await apiClient.deleteTaxSession('tax-1')
      expect(api.delete).toHaveBeenCalledWith('/tax-expert/tax-history/tax-1')

      await apiClient.uploadITR('tax-1', file)
      expect(api.post).toHaveBeenCalledWith('/tax-expert/tax-1/tax/itr', expect.any(FormData))

      vi.mocked(api.get).mockResolvedValueOnce({ data: { itr_data: { gross: 1200000 } } })
      const itrData = await apiClient.getITRData('tax-1')
      expect(itrData.gross).toBe(1200000)

      await apiClient.getTaxExpertSummary('tax-1', 'new')
      expect(api.get).toHaveBeenCalledWith('/tax-expert/tax-1/tax/summary', { params: { regime: 'new' } })

      await apiClient.getTaxExpertIncome('tax-1')
      expect(api.get).toHaveBeenCalledWith('/tax-expert/tax-1/tax/income')

      await apiClient.getTaxExpertCapitalGains('tax-1')
      expect(api.get).toHaveBeenCalledWith('/tax-expert/tax-1/tax/capital-gains')

      await apiClient.updateTransactionCost('tax-1', 'equity_shares', 1, 2500)
      expect(api.post).toHaveBeenCalledWith('/tax-expert/tax-1/tax/capital-gains/transaction', { category: 'equity_shares', sr: 1, new_cost: 2500 })

      await apiClient.postTaxOverrides('tax-1', { deductions: { '80c': 150000 } }, 'old')
      expect(api.post).toHaveBeenCalledWith('/tax-expert/tax-1/tax/recalculate?regime=old', { deductions: { '80c': 150000 } })

      await apiClient.postTaxOverrides('tax-1', { deductions: { '80c': 150000 } })
      expect(api.post).toHaveBeenCalledWith('/tax-expert/tax-1/tax/recalculate', { deductions: { '80c': 150000 } })

      await apiClient.compareTaxRegimes('tax-1')
      expect(api.get).toHaveBeenCalledWith('/tax-expert/tax-1/tax/compare-regimes')

      await apiClient.getTaxRules()
      expect(api.get).toHaveBeenCalledWith('/tax-expert/rules')

      await apiClient.getTaxDetails('tax-1', 'salary', 0, 100)
      expect(api.get).toHaveBeenCalledWith('/tax-expert/tax-1/tax/details/salary', { params: { offset: 0, limit: 100 } })
    })

    it('Accounts, Profile & Admin endpoints', async () => {
      await apiClient.getAccountsSummary()
      expect(api.get).toHaveBeenCalledWith('/accounts/summary')

      await apiClient.purgeAccount()
      expect(api.delete).toHaveBeenCalledWith('/accounts/me')

      await apiClient.exportAccount()
      expect(api.get).toHaveBeenCalledWith('/accounts/me/export')

      await apiClient.clearSystemCaches()
      expect(api.post).toHaveBeenCalledWith('/accounts/clear_caches')

      await apiClient.getMe()
      expect(api.get).toHaveBeenCalledWith('/auth/me')

      await apiClient.updateProfile({ display_name: 'Rahul' })
      expect(api.put).toHaveBeenCalledWith('/auth/profile', { display_name: 'Rahul' })

      await apiClient.setProfilePan('ABCDE1234F')
      expect(api.put).toHaveBeenCalledWith('/auth/profile/pan', { pan: 'ABCDE1234F' })

      await apiClient.getAccessRequests()
      expect(api.get).toHaveBeenCalledWith('/auth/access-requests')

      await apiClient.approveAccessRequest('req-1', { method: 'invite' })
      expect(api.post).toHaveBeenCalledWith('/auth/access-requests/req-1/approve', { method: 'invite' })

      await apiClient.rejectAccessRequest('req-1')
      expect(api.post).toHaveBeenCalledWith('/auth/access-requests/req-1/reject')

      await apiClient.inviteUser({ email: 'u@test.com', name: 'User' })
      expect(api.post).toHaveBeenCalledWith('/auth/invites', { email: 'u@test.com', name: 'User' })

      await apiClient.suspendUser('u@test.com')
      expect(api.post).toHaveBeenCalledWith('/auth/users/suspend', { email: 'u@test.com' })

      await apiClient.getAppUsers()
      expect(api.get).toHaveBeenCalledWith('/auth/users')

      await apiClient.updateAppUser('u-1', { status: 'active', role: 'admin' })
      expect(api.patch).toHaveBeenCalledWith('/auth/users/u-1', { status: 'active', role: 'admin' })

      await apiClient.deleteAppUser('u-1')
      expect(api.delete).toHaveBeenCalledWith('/auth/users/u-1')

      await apiClient.getMfSyncStatus()
      expect(api.get).toHaveBeenCalledWith('/admin/mf-sync/status')

      await apiClient.getSyncedAmcs()
      expect(api.get).toHaveBeenCalledWith('/admin/mf-sync/amcs')

      await apiClient.triggerMfSync({ amcs: ['HDFC'] })
      expect(api.post).toHaveBeenCalledWith('/admin/mf-sync/trigger', { amcs: ['HDFC'] })

      await apiClient.triggerMfSync()
      expect(api.post).toHaveBeenCalledWith('/admin/mf-sync/trigger', {})

      await apiClient.purgeMfSnapshots({ amc: 'HDFC' })
      expect(api.delete).toHaveBeenCalledWith('/admin/mf-sync/purge', { params: { amc: 'HDFC' } })

      await apiClient.searchMfSchemes('HDFC Top 100', 25, 0, 'HDFC Mutual Fund', 'Equity')
      expect(api.get).toHaveBeenCalledWith('/admin/mf-sync/schemes', {
        params: { q: 'HDFC Top 100', limit: 25, offset: 0, amc: 'HDFC Mutual Fund', category: 'Equity' },
      })
    })
  })
})
