import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { createWrapper } from '../../../test/utils'
import {
  toQueryParams,
  budgetErrorDetail,
  budgetErrorStatus,
  useBudgetSessions,
  useBudgetOverview,
  useBudgetCategories,
  useBudgetTransactions,
  useBudgetAccounts,
  useBudgetTransfers,
  useBudgetRecurring,
  useBudgetForecast,
  useBudgetAnomalies,
  useBudgetReconciliation,
  useBudgetCoverage,
  useBudgetSankey,
  useBudgetEnvelopes,
  useUploadStatement,
  useDeleteBudgetSession,
  useUpdateBudgetAccount,
  useSetBudgetEnvelope,
} from './useBudget'
import { apiClient } from '../../../shared/api/client'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getBudgetSessions: vi.fn(),
    getBudgetOverview: vi.fn(),
    getBudgetCategories: vi.fn(),
    getBudgetTransactions: vi.fn(),
    getBudgetAccounts: vi.fn(),
    updateBudgetAccount: vi.fn(),
    getBudgetTransfers: vi.fn(),
    getBudgetRecurring: vi.fn(),
    getBudgetForecast: vi.fn(),
    getBudgetAnomalies: vi.fn(),
    getBudgetReconciliation: vi.fn(),
    getBudgetCoverage: vi.fn(),
    getBudgetSankey: vi.fn(),
    getBudgetEnvelopes: vi.fn(),
    setBudgetEnvelope: vi.fn(),
    uploadBudgetStatement: vi.fn(),
    deleteBudgetSession: vi.fn(),
  },
}))

describe('useBudget utilities and hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('toQueryParams', () => {
    it('serializes filters to valid query parameters', () => {
      const filters = {
        bank: 'HDFC',
        accountType: 'savings',
        txnType: 'all',
        dateRange: 'custom',
        amountBracket: 'all',
        paymentMode: 'UPI',
        category: 'Food',
        flow: 'debit',
        fromDate: '2026-01-01',
        toDate: '2026-01-31',
        search: 'Swiggy',
      }
      const params = toQueryParams(filters)
      expect(params).toEqual({
        bank: 'HDFC',
        account_type: 'savings',
        date_range: 'custom',
        payment_mode: 'UPI',
        category: 'Food',
        flow: 'debit',
        from_date: '2026-01-01',
        to_date: '2026-01-31',
        search: 'Swiggy',
      })
    })

    it('returns empty object if no filters provided', () => {
      expect(toQueryParams(undefined)).toEqual({})
    })
  })

  describe('budgetErrorDetail & budgetErrorStatus', () => {
    it('extracts detail and status from error objects', () => {
      const error = {
        response: {
          status: 404,
          data: { detail: 'Session not found' },
        },
      }
      expect(budgetErrorDetail(error, 'Fallback')).toBe('Session not found')
      expect(budgetErrorStatus(error)).toBe(404)

      expect(budgetErrorDetail(new Error('Network error'), 'Fallback')).toBe('Network error')
      expect(budgetErrorDetail({}, 'Fallback')).toBe('Fallback')
      expect(budgetErrorStatus(null)).toBeUndefined()
    })
  })

  describe('useBudget hooks', () => {
    it('useBudgetSessions queries sessions', async () => {
      const mockSessions = [{ session_id: 's1', filename: 'bank.pdf', total_txns: 10 }]
      vi.mocked(apiClient.getBudgetSessions).mockResolvedValue(mockSessions as any)

      const { result } = renderHook(() => useBudgetSessions(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toEqual(mockSessions)
    })

    it('useBudgetOverview queries overview data', async () => {
      const mockOverview = { total_income: 100000, total_expenses: 60000, net_savings: 40000 }
      vi.mocked(apiClient.getBudgetOverview).mockResolvedValue(mockOverview as any)

      const { result } = renderHook(() => useBudgetOverview('s1', { bank: 'HDFC' }), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toEqual(mockOverview)
      expect(apiClient.getBudgetOverview).toHaveBeenCalledWith('s1', { bank: 'HDFC' })
    })

    it('useBudgetCategories queries category breakdown', async () => {
      const mockCategories = { categories: [{ name: 'Food', amount: 15000, percentage: 25 }] }
      vi.mocked(apiClient.getBudgetCategories).mockResolvedValue(mockCategories as any)

      const { result } = renderHook(() => useBudgetCategories('s1', {}), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toEqual(mockCategories)
    })

    it('useBudgetTransactions queries paginated transactions', async () => {
      const mockTxns = { items: [{ id: 'tx1', description: 'Groceries', amount: 500 }], total: 1, page: 1, total_pages: 1 }
      vi.mocked(apiClient.getBudgetTransactions).mockResolvedValue(mockTxns as any)

      const { result } = renderHook(() => useBudgetTransactions('s1', {}, 20), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toEqual(mockTxns)
    })

    it('useBudgetAccounts and mutations function correctly', async () => {
      const mockAccounts = { accounts: [{ account_id: 'acc1', bank: 'HDFC' }] }
      vi.mocked(apiClient.getBudgetAccounts).mockResolvedValue(mockAccounts as any)
      vi.mocked(apiClient.updateBudgetAccount).mockResolvedValue({ status: 'ok' } as any)

      const { result } = renderHook(
        () => ({
          accounts: useBudgetAccounts('s1'),
          updateAccount: useUpdateBudgetAccount(),
        }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => expect(result.current.accounts.isSuccess).toBe(true))
      expect(result.current.accounts.data).toEqual(mockAccounts)

      await act(async () => {
        await result.current.updateAccount.mutateAsync({
          accountKey: 'acc1',
          patch: { account_type: 'savings' } as any,
        })
      })

      expect(apiClient.updateBudgetAccount).toHaveBeenCalledWith('acc1', { account_type: 'savings' })
    })

    it('useBudgetEnvelopes queries and mutates envelopes', async () => {
      const mockEnvelopes = [{ category: 'Dining', budgeted_amount: 5000 }]
      vi.mocked(apiClient.getBudgetEnvelopes).mockResolvedValue(mockEnvelopes as any)
      vi.mocked(apiClient.setBudgetEnvelope).mockResolvedValue({ status: 'ok' } as any)

      const { result } = renderHook(
        () => ({
          envelopes: useBudgetEnvelopes('s1'),
          setEnvelope: useSetBudgetEnvelope(),
        }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => expect(result.current.envelopes.isSuccess).toBe(true))
      expect(result.current.envelopes.data).toEqual(mockEnvelopes)

      await act(async () => {
        await result.current.setEnvelope.mutateAsync({
          category: 'Dining',
          monthlyCap: 6000,
        })
      })

      expect(apiClient.setBudgetEnvelope).toHaveBeenCalledWith('Dining', 6000)
    })
  })
})
