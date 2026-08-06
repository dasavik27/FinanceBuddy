import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { createWrapper } from '../../../test/utils'
import {
  useTaxExpertOverrides,
  useUploadITR,
  useITRData,
  useTaxExpertTransactionCost,
  useTaxExpertSummary,
  useTaxExpertIncome,
  useTaxExpertCapitalGains,
  useTaxRegimeComparison,
  useTaxRules,
} from './useTaxExpert'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    postTaxOverrides: vi.fn(),
    uploadITR: vi.fn(),
    getITRData: vi.fn(),
    updateTransactionCost: vi.fn(),
    getTaxExpertSummary: vi.fn(),
    getTaxExpertIncome: vi.fn(),
    getTaxExpertCapitalGains: vi.fn(),
    compareTaxRegimes: vi.fn(),
    getTaxRules: vi.fn(),
  },
}))

describe('useTaxExpert hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert' })
  })

  it('useTaxExpertSummary fetches summary for a regime', async () => {
    const mockSummary = { ay: '2025-26', total_tax: 120000 }
    vi.mocked(apiClient.getTaxExpertSummary).mockResolvedValue(mockSummary as any)

    const { result } = renderHook(() => useTaxExpertSummary('new'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockSummary)
    expect(apiClient.getTaxExpertSummary).toHaveBeenCalledWith('tax-sid-1', 'new')
  })

  it('useTaxExpertIncome fetches income breakdown', async () => {
    const mockIncome = { salary: { gross: 1500000 }, total_savings_interest: 8000 }
    vi.mocked(apiClient.getTaxExpertIncome).mockResolvedValue(mockIncome as any)

    const { result } = renderHook(() => useTaxExpertIncome(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockIncome)
  })

  it('useTaxExpertCapitalGains fetches capital gains data', async () => {
    const mockCg = { equity_shares: [], bf_losses: { stcl: 0, ltcl: 0 } }
    vi.mocked(apiClient.getTaxExpertCapitalGains).mockResolvedValue(mockCg as any)

    const { result } = renderHook(() => useTaxExpertCapitalGains(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockCg)
  })

  it('useTaxRegimeComparison compares regimes', async () => {
    const mockCompare = { recommended: 'new', new_regime: { total_tax: 100000 }, old_regime: { total_tax: 120000 } }
    vi.mocked(apiClient.compareTaxRegimes).mockResolvedValue(mockCompare as any)

    const { result } = renderHook(() => useTaxRegimeComparison(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockCompare)
  })

  it('useTaxRules fetches display rules (session-independent)', async () => {
    const mockRules = { deductions: { limit_80tta: 10000 } }
    vi.mocked(apiClient.getTaxRules).mockResolvedValue(mockRules as any)

    const { result } = renderHook(() => useTaxRules(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockRules)
  })

  it('useITRData fetches uploaded ITR data', async () => {
    const mockItr = { pan: 'ABCDE1234F', itr_type: 'ITR-2', tax: { refund_or_due: 5000 } }
    vi.mocked(apiClient.getITRData).mockResolvedValue(mockItr as any)

    const { result } = renderHook(() => useITRData(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockItr)
  })

  it('useTaxExpertOverrides posts overrides for the active session', async () => {
    vi.mocked(apiClient.postTaxOverrides).mockResolvedValue({ status: 'ok' } as any)

    const { result } = renderHook(() => useTaxExpertOverrides(), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.mutateAsync({ manual_tds: 50000 })
    })

    expect(apiClient.postTaxOverrides).toHaveBeenCalledWith('tax-sid-1', { manual_tds: 50000 })
  })

  it('useUploadITR uploads file and invalidates ITR query', async () => {
    const file = new File(['itr'], 'itr.pdf', { type: 'application/pdf' })
    vi.mocked(apiClient.uploadITR).mockResolvedValue({ status: 'parsed' } as any)

    const { result } = renderHook(() => useUploadITR(), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.mutateAsync(file)
    })

    expect(apiClient.uploadITR).toHaveBeenCalledWith('tax-sid-1', file)
  })

  it('useTaxExpertTransactionCost updates transaction cost', async () => {
    vi.mocked(apiClient.updateTransactionCost).mockResolvedValue({ status: 'ok' } as any)

    const { result } = renderHook(() => useTaxExpertTransactionCost(), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.mutateAsync({ category: 'equity_shares', sr: 1, new_cost: 75000 })
    })

    expect(apiClient.updateTransactionCost).toHaveBeenCalledWith('tax-sid-1', 'equity_shares', 1, 75000)
  })

  it('queries stay disabled when no tax session id', async () => {
    useAppStore.setState({ taxSessionId: null })
    vi.mocked(apiClient.getTaxExpertSummary).mockResolvedValue({} as any)

    const { result } = renderHook(() => useTaxExpertSummary('new'), {
      wrapper: createWrapper(),
    })

    expect(result.current.fetchStatus).toBe('idle')
    expect(apiClient.getTaxExpertSummary).not.toHaveBeenCalled()
  })
})
