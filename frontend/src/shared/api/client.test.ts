import { describe, it, expect, beforeEach, vi } from 'vitest'
import api, { apiClient } from './client'
import authClient from '../auth/authClient'
import { useAppStore } from '../store/appStore'

describe('apiClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useAppStore.getState().clearIdentity()
  })

  it('attaches auth token in request interceptor when available', async () => {
    vi.spyOn(authClient, 'getAccessToken').mockResolvedValue('test-bearer-token')
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { status: 'ok' } })

    await apiClient.syncPortfolio('session-123')
    expect(postSpy).toHaveBeenCalledWith('/mutual-funds/portfolio/session-123/sync')
  })

  it('calls mutual funds endpoints correctly', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ data: { success: true } })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { success: true } })
    const deleteSpy = vi.spyOn(api, 'delete').mockResolvedValue({ data: { success: true } })

    const dummyFile = new File(['content'], 'statement.pdf', { type: 'application/pdf' })
    await apiClient.parseFile(dummyFile, 'secret123')
    expect(postSpy).toHaveBeenCalledWith(
      '/mutual-funds/portfolio/parse',
      expect.any(FormData),
      expect.objectContaining({ headers: { 'X-Upload-Type': 'mutual_funds' } })
    )

    await apiClient.getSummary('sid-1', { benchmark: 'Nifty 50' })
    expect(getSpy).toHaveBeenLastCalledWith('/mutual-funds/overview/sid-1/summary', {
      params: { benchmark: 'Nifty 50' },
    })

    await apiClient.getOverview('sid-1', { period: '1Y' })
    expect(getSpy).toHaveBeenLastCalledWith('/mutual-funds/overview/sid-1/overview', {
      params: { period: '1Y' },
    })

    await apiClient.getHoldings('sid-1', { category: 'Equity' })
    expect(getSpy).toHaveBeenLastCalledWith('/mutual-funds/holdings/sid-1/holdings', {
      params: { category: 'Equity' },
    })

    await apiClient.deleteHistorySession('sid-1')
    expect(deleteSpy).toHaveBeenCalledWith('/history/sid-1')
  })

  it('calls equity endpoints correctly', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ data: { equity: true } })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { equity: true } })

    await apiClient.getEquitySummary('eq-1')
    expect(getSpy).toHaveBeenLastCalledWith('/equity/overview/eq-1/summary')

    await apiClient.getEquityAllocation('eq-1')
    expect(getSpy).toHaveBeenLastCalledWith('/equity/overview/eq-1/allocation')

    await apiClient.getEquityHoldings('eq-1', { sort_by: 'current_value' })
    expect(getSpy).toHaveBeenLastCalledWith('/equity/holdings/eq-1/holdings', {
      params: { sort_by: 'current_value' },
    })

    await apiClient.searchStocks('TCS')
    expect(getSpy).toHaveBeenLastCalledWith('/equity/analyzer/search', { params: { q: 'TCS' } })

    await apiClient.analyzeStock('INFY')
    expect(getSpy).toHaveBeenLastCalledWith('/equity/analyzer/analyze/INFY')

    await apiClient.stockPortfolioImpact('RELIANCE', 50000, 'eq-1')
    expect(postSpy).toHaveBeenLastCalledWith('/equity/analyzer/impact', {
      symbol: 'RELIANCE',
      amount: 50000,
      session_id: 'eq-1',
    })
  })

  it('calls budget endpoints correctly', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({
      data: { transactions: [{ id: 'txn-1' }], total: 1, limit: 10, offset: 0, has_more: false },
    })
    const putSpy = vi.spyOn(api, 'put').mockResolvedValue({ data: { status: 'ok' } })

    await apiClient.getBudgetOverview('b-1', { month: '2026-03' })
    expect(getSpy).toHaveBeenLastCalledWith('/budget/analytics/b-1/overview', {
      params: { month: '2026-03' },
    })

    const res = await apiClient.getBudgetTransactions('b-1', { limit: 20 })
    expect(getSpy).toHaveBeenLastCalledWith('/budget/analytics/b-1/transactions', {
      params: { limit: 20 },
    })
    expect(res.transactions).toHaveLength(1)

    await apiClient.updateBudgetTransactions([{ id: 'txn-10', category: 'Dining' } as any])
    expect(putSpy).toHaveBeenLastCalledWith('/budget/analytics/transactions/update', [
      { id: 'txn-10', category: 'Dining' },
    ])
  })

  it('calls tax expert endpoints correctly', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ data: { tax: true } })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValue({ data: { tax: true } })

    await apiClient.getTaxExpertSummary('tax-1', 'new')
    expect(getSpy).toHaveBeenLastCalledWith('/tax-expert/tax-1/tax/summary', {
      params: { regime: 'new' },
    })

    await apiClient.compareTaxRegimes('tax-1')
    expect(getSpy).toHaveBeenLastCalledWith('/tax-expert/tax-1/tax/compare-regimes')

    await apiClient.getTaxRules()
    expect(getSpy).toHaveBeenLastCalledWith('/tax-expert/rules')

    await apiClient.postTaxOverrides('tax-1', { section_80c: 150000 })
    expect(postSpy).toHaveBeenLastCalledWith('/tax-expert/tax-1/tax/recalculate', {
      section_80c: 150000,
    })
  })

  it('calls admin and user endpoints correctly', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValue({ data: { user: true } })
    const putSpy = vi.spyOn(api, 'put').mockResolvedValue({ data: { user: true } })
    const patchSpy = vi.spyOn(api, 'patch').mockResolvedValue({ data: { user: true } })

    await apiClient.getMe()
    expect(getSpy).toHaveBeenLastCalledWith('/auth/me')

    await apiClient.setProfilePan('ABCDE1234F')
    expect(putSpy).toHaveBeenLastCalledWith('/auth/profile/pan', { pan: 'ABCDE1234F' })

    await apiClient.getMfSyncStatus()
    expect(getSpy).toHaveBeenLastCalledWith('/admin/mf-sync/status')

    await apiClient.updateAppUser('u-1', { status: 'active' })
    expect(patchSpy).toHaveBeenLastCalledWith('/auth/users/u-1', { status: 'active' })
  })
})
