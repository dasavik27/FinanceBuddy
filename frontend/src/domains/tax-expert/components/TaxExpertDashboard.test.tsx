import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import TaxExpertDashboard from './TaxExpertDashboard'
import { useAppStore } from '../../../shared/store/appStore'
import { apiClient } from '../../../shared/api/client'

const mockSummary = {
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
}

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getTaxExpertSummary: vi.fn(),
    compareTaxRegimes: vi.fn(),
    getTaxExpertIncome: vi.fn(),
    getTaxExpertCapitalGains: vi.fn(),
    getTaxHistory: vi.fn(),
    parseAIS: vi.fn(),
    getTaxRules: vi.fn(),
    getITRData: vi.fn(),
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
    vi.mocked(apiClient.getTaxRules).mockResolvedValue({} as any)
    vi.mocked(apiClient.getITRData).mockResolvedValue({} as any)
  })

  it('renders validating spinner when loading with active session', () => {
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert' })
    vi.mocked(apiClient.getTaxExpertSummary).mockReturnValue(new Promise(() => {}))

    renderWithProviders(<TaxExpertDashboard />)
    expect(screen.getByText('Restoring your session...')).toBeInTheDocument()
  })

  it('handles 404 error by clearing session and flagging expired', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert' })
    // Persist the rejection — react-query retries failed queries by default.
    vi.mocked(apiClient.getTaxExpertSummary).mockRejectedValue({ response: { status: 404 } })

    renderWithProviders(<TaxExpertDashboard />)
    await waitFor(() => {
      expect(useAppStore.getState().taxSessionId).toBeNull()
      expect(screen.getByText(/Your previous session was lost/i)).toBeInTheDocument()
    }, { timeout: 10000 })
  })

  it('renders TaxUploadPanel when no session is active and creates new session', async () => {
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

  it('handles onSessionCreated callback when new session is uploaded and analyzed', async () => {
    useAppStore.setState({ taxSessionId: null, activeModule: 'tax_expert', userId: 'u1' })
    renderWithProviders(<TaxExpertDashboard />)

    const file = new File(['%PDF-mock'], 'ais.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    vi.mocked(apiClient.parseAIS).mockResolvedValueOnce({
      session_id: 'new-tax-sid-99',
      financial_year: '2024-25',
      assessment_year: '2025-26',
    } as any)

    await userEvent.upload(fileInput, file)

    const computeBtn = await screen.findByRole('button', { name: /Compute My Taxes/i })
    await userEvent.click(computeBtn)

    await waitFor(() => {
      expect(useAppStore.getState().taxSessionId).toBe('new-tax-sid-99')
    })
  })

  it('exports tax report with partial API failures and fallback metadata values', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert', userId: 'u1' })
    vi.mocked(apiClient.getTaxExpertSummary).mockResolvedValueOnce({} as any) // missing ay, fy, itr_type
    vi.mocked(apiClient.compareTaxRegimes).mockRejectedValueOnce(new Error('Comparison service offline'))
    vi.mocked(apiClient.getTaxExpertIncome).mockRejectedValueOnce(new Error('Income service offline'))
    vi.mocked(apiClient.getTaxExpertCapitalGains).mockRejectedValueOnce(new Error('CG offline'))

    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderWithProviders(<TaxExpertDashboard />, { initialEntries: ['/'] })
    await screen.findByText('TAX EXPERT')

    await userEvent.click(screen.getByRole('button', { name: /Export Report/i }))

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalled()
    })

    clickSpy.mockRestore()
    vi.unstubAllGlobals()
  })

  it('handles export failure catch block gracefully', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert', userId: 'u1' })
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockImplementation(() => {
      throw new Error('Blob URL creation error')
    })

    renderWithProviders(<TaxExpertDashboard />, { initialEntries: ['/'] })
    await screen.findByText('TAX EXPERT')

    await userEvent.click(screen.getByRole('button', { name: /Export Report/i }))
    createObjectURLSpy.mockRestore()
  })
})
