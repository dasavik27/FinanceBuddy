import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import TaxExpertDashboard from './TaxExpertDashboard'
import { useAppStore } from '../../../shared/store/appStore'
import { apiClient } from '../../../shared/api/client'

const { mockSummary } = vi.hoisted(() => ({
  mockSummary: {
  ay: '2025-26',
  fy: '2024-25',
  itr_type: 'ITR-2',
  gross_income: 1500000,
  total_tax: 180000,
  income_heads: {
    salary: { gross: 1200000, net: 1100000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0 },
    business: { total_profit: 0 },
    capital_gains: { total: 100000, total_special_rate: 80000 },
    other_sources: { total: 50000 },
    crypto: { gains: 0, tax: 0 },
    gaming: { gains: 0, tax: 0 },
    misc_income: { total: 0 },
  },
  deductions: { '80c': 150000 },
  chapter_via_deductions_total: 150000,
  total_deductions: 150000,
  taxable_normal_income: 1200000,
  tax_on_normal_income: 100000,
  tax_on_capital_gains: { ltcg_equity: 10000, stcg_equity: 5000, ltcg_other: 0 },
  rebate_87a: 0,
  rebate_87a_on_cg: 0,
  reconciliation_flags: {},
  },
}))

vi.mock('../hooks/useTaxExpert', () => ({
  useTaxExpertSummary: vi.fn(() => ({
    data: mockSummary,
    isLoading: false,
    error: null,
  })),
}))

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getTaxExpertSummary: vi.fn(),
    compareTaxRegimes: vi.fn(),
    getTaxExpertIncome: vi.fn(),
    getTaxExpertCapitalGains: vi.fn(),
    getTaxHistory: vi.fn(),
    parseAIS: vi.fn(),
  },
}))

describe('TaxExpertDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.getTaxExpertSummary).mockResolvedValue(mockSummary as any)
    vi.mocked(apiClient.compareTaxRegimes).mockResolvedValue({
      recommended: 'new',
      new_regime: { total_tax: 180000 },
      old_regime: { total_tax: 200000 },
    } as any)
    vi.mocked(apiClient.getTaxExpertIncome).mockResolvedValue({ salary: { gross: 1200000 } } as any)
    vi.mocked(apiClient.getTaxExpertCapitalGains).mockResolvedValue({ equity_shares: [] } as any)
    vi.mocked(apiClient.getTaxHistory).mockResolvedValue({ sessions: [] } as any)
  })

  it('renders TaxUploadPanel when no session is active', () => {
    useAppStore.setState({ taxSessionId: null, activeModule: 'tax_expert', userId: 'u1' })
    renderWithProviders(<TaxExpertDashboard />)

    expect(screen.getByText(/Import Your Annual Information Statement/i)).toBeInTheDocument()
    expect(screen.getByText(/Upload AIS PDF/i)).toBeInTheDocument()
  })

  it('renders dashboard header and strategy tabs when session is active', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert', userId: 'u1' })
    renderWithProviders(<TaxExpertDashboard />, { initialEntries: ['/'] })

    expect(await screen.findByText('TAX EXPERT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Export Report/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Switch AIS session/i })).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: /Tax Summary/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Income Sources/i })).toBeInTheDocument()
  })

  it('exports tax report when Export Report is clicked', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert', userId: 'u1' })

    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderWithProviders(<TaxExpertDashboard />, { initialEntries: ['/'] })
    await screen.findByText('TAX EXPERT')

    await userEvent.click(screen.getByRole('button', { name: /Export Report/i }))

    await waitFor(() => {
      expect(apiClient.getTaxExpertSummary).toHaveBeenCalledWith('tax-sid-1', 'new')
      expect(apiClient.getTaxExpertSummary).toHaveBeenCalledWith('tax-sid-1', 'old')
      expect(apiClient.compareTaxRegimes).toHaveBeenCalledWith('tax-sid-1')
    })

    clickSpy.mockRestore()
    vi.unstubAllGlobals()
  })
})
