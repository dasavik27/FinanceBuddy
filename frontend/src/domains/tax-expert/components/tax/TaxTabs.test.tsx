import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../../test/utils'
import TaxOverviewTab from './TaxOverviewTab'
import TaxIncomeTab from './TaxIncomeTab'
import TaxSavingsTab from './TaxSavingsTab'
import TaxCapitalGainsTab from './TaxCapitalGainsTab'
import TaxITRCompareTab from './TaxITRCompareTab'
import TaxHistoryTab from './TaxHistoryTab'
import TaxAuditorFindings from './TaxAuditorFindings'
import { useAppStore } from '../../../../shared/store/appStore'
import { apiClient } from '../../../../shared/api/client'
import {
  useTaxExpertSummary,
  useTaxExpertIncome,
  useTaxExpertCapitalGains,
  useTaxRegimeComparison,
  useTaxRules,
  useTaxExpertOverrides,
  useTaxExpertTransactionCost,
  useITRData,
  useUploadITR,
} from '../../hooks/useTaxExpert'

const {
  mockSummary,
  mockIncome,
  mockTaxRules,
  mockCapitalGains,
  mockCompare,
  mockItr,
} = vi.hoisted(() => ({
  mockSummary: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-2',
    gross_income: 1500000,
    total_tax: 180000,
    total_tax_paid: 185000,
    tds_paid: 170000,
    refund_or_due: -5000,
    income_heads: {
      salary: { gross: 1200000, net: 1100000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0, employer: 'Acme Corp' },
      business: { total_profit: 0 },
      capital_gains: { total: 100000, total_special_rate: 80000, grandfather_benefit: 0, slab_taxed_cg: 0, stcg_other: 0, stcg_equity: 50000, ltcg_equity: 30000, ltcg_other: 0 },
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
    tax_on_capital_gains: { ltcg_equity: 10000, stcg_equity: 5000, ltcg_other: 0, total: 15000 },
    rebate_87a: 0,
    rebate_87a_on_cg: 0,
    surcharge: 0,
    cess: 7200,
    advance_tax: 0,
    manual_tax_paid: 0,
    overrides: { deductions: { '80c': 150000 }, manual_taxes: 0 },
    reconciliation_flags: {
      zero_cost: [{ security: 'RELIANCE', suggestion: 'Override with broker cost' }],
      cost_mismatch: [],
    },
  },
  mockIncome: {
    personal: { dob: '01/01/1985' },
    salary: {
      gross: 1200000,
      employer: 'Acme Corp (Section 192)',
      tds_deducted: 150000,
      quarterly: [{ amount_paid: 100000 }],
    },
    business: {},
    total_savings_interest: 10000,
    total_fd_interest: 5000,
    total_misc_income: 20000,
    total_dividends: 0,
    total_other_interest: 0,
    interest_savings: [],
    interest_deposits: [],
    interest_others: [],
    dividends: [],
  },
  mockTaxRules: {
    deductions: { limit_80tta: 10000 },
    ui_tooltips: {
      section_16_ia: { text: 'Standard deduction under Section 16(ia)' },
      section_44ada: { text: 'Presumptive professional income' },
      section_44ad: { text: 'Presumptive business income' },
      misc_income: { text: 'Miscellaneous income' },
      section_80tta: { text: 'Savings interest deduction' },
      section_80ttb: { text: 'Senior citizen interest deduction' },
      other_interest: { text: 'Other interest income' },
      dividend: { text: 'Dividend income' },
      foreign_interest: { text: 'Foreign interest' },
      crypto_vda: { text: 'Virtual digital assets' },
      gaming_lottery: { text: 'Gaming and lottery' },
    },
  },
  mockCapitalGains: {
    bf_losses: { stcl: 0, ltcl: 0 },
    equity_shares: [{ type: 'STCG', security: 'INFY', consideration: 100000, cost: 80000, gain: 20000 }],
    equity_shares_count: 1,
    equity_mf: [],
    equity_mf_count: 0,
    debt_mf: [],
    real_estate: [],
  },
  mockCompare: {
    recommended: 'new',
    new_regime: { total_tax: 180000 },
    old_regime: { total_tax: 200000 },
  },
  mockItr: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-2',
    assessment_year: '2025-26',
    income: {
      salary_gross: 1200000,
      salary: 1100000,
      capital_gains: 100000,
      gross_total: 1500000,
    },
    deductions: { total: 150000 },
    tax: {
      refund_or_due: 5000,
      taxable_income: 1350000,
      tax_at_slab_rates: 100000,
      tax_on_income: 100000,
      tax_at_special_rate: 15000,
      tax_before_rebate: 115000,
      rebate_87a: 0,
      surcharge: 0,
      cess: 7200,
      total_tax_liability: 180000,
      tds_paid: 170000,
      advance_tax: 0,
      total_taxes_paid: 185000,
    },
  },
}))

vi.mock('../../hooks/useTaxExpert', () => ({
  useTaxExpertSummary: vi.fn(() => ({ data: mockSummary, isLoading: false, error: null })),
  useTaxExpertIncome: vi.fn(() => ({ data: mockIncome, isLoading: false, error: null })),
  useTaxExpertCapitalGains: vi.fn(() => ({ data: mockCapitalGains, isLoading: false, error: null })),
  useTaxRegimeComparison: vi.fn(() => ({ data: mockCompare, isLoading: false, error: null })),
  useTaxRules: vi.fn(() => ({ data: mockTaxRules, isLoading: false, error: null })),
  useTaxExpertOverrides: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })),
  useTaxExpertTransactionCost: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })),
  useITRData: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  useUploadITR: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isError: false })),
}))

vi.mock('../../../../shared/api/client', () => ({
  apiClient: {
    getTaxHistory: vi.fn(),
    deleteTaxSession: vi.fn(),
    reconcileBrokerFile: vi.fn(),
  },
}))

describe('Tax tab components', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert', taxRegime: 'new', userId: 'u1' })

    vi.mocked(useTaxExpertSummary).mockReturnValue({ data: mockSummary, isLoading: false, error: null } as any)
    vi.mocked(useTaxExpertIncome).mockReturnValue({ data: mockIncome, isLoading: false, error: null } as any)
    vi.mocked(useTaxExpertCapitalGains).mockReturnValue({ data: mockCapitalGains, isLoading: false, error: null } as any)
    vi.mocked(useTaxRegimeComparison).mockReturnValue({ data: mockCompare, isLoading: false, error: null } as any)
    vi.mocked(useTaxRules).mockReturnValue({ data: mockTaxRules, isLoading: false, error: null } as any)
    vi.mocked(useITRData).mockReturnValue({ data: null, isLoading: false, error: null } as any)
    vi.mocked(apiClient.getTaxHistory).mockResolvedValue({ sessions: [] } as any)
    vi.mocked(apiClient.deleteTaxSession).mockResolvedValue({ status: 'deleted' } as any)
  })

  describe('TaxOverviewTab', () => {
    it('renders tax summary with regime comparison', async () => {
      renderWithProviders(<TaxOverviewTab />)

      expect(await screen.findByText('Tax Summary')).toBeInTheDocument()
      expect(screen.getByText(/Side-by-side comparison/i)).toBeInTheDocument()
      expect(screen.getByText('Gross Total Income (GTI)')).toBeInTheDocument()
      expect(screen.getByText('ITR-2')).toBeInTheDocument()
    })
  })

  describe('TaxIncomeTab', () => {
    it('renders income sources with core income section', async () => {
      renderWithProviders(<TaxIncomeTab />)

      expect(await screen.findByText('Income Sources')).toBeInTheDocument()
      expect(screen.getByText('Core Income')).toBeInTheDocument()
      expect(screen.getByText('Salary Income')).toBeInTheDocument()
      expect(screen.getAllByText(/AIS Auto-filled/i).length).toBeGreaterThan(0)
    })

    it('expands core income category on click', async () => {
      renderWithProviders(<TaxIncomeTab />)
      await screen.findByText('Core Income')

      await userEvent.click(screen.getByText('Core Income'))
      expect(screen.getByText(/Salary Income/i)).toBeInTheDocument()
    })
  })

  describe('TaxSavingsTab', () => {
    it('renders TDS and deductions sections', async () => {
      renderWithProviders(<TaxSavingsTab />)

      expect(await screen.findByText('Tax Savings & TDS')).toBeInTheDocument()
      expect(screen.getByText('TDS & Taxes Paid')).toBeInTheDocument()
    })

    it('shows popular tax saving investments by default', async () => {
      renderWithProviders(<TaxSavingsTab />)
      await screen.findByText('Tax Savings & TDS')

      expect(screen.getByText(/80C - PPF/i)).toBeInTheDocument()
    })
  })

  describe('TaxCapitalGainsTab', () => {
    it('renders capital gains with equity transactions', async () => {
      renderWithProviders(<TaxCapitalGainsTab />)

      expect(await screen.findByText('Capital Gains')).toBeInTheDocument()
      expect(await screen.findByText('Equity Shares')).toBeInTheDocument()
    })
  })

  describe('TaxITRCompareTab', () => {
    it('shows upload prompt when no ITR is loaded', async () => {
      renderWithProviders(<TaxITRCompareTab />)

      expect(await screen.findByText(/Compare ITR vs Finance Buddy/i)).toBeInTheDocument()
      expect(screen.getByText(/Drag & Drop your ITR PDF here/i)).toBeInTheDocument()
    })

    it('renders reconciliation summary when ITR data exists', async () => {
      vi.mocked(useITRData).mockReturnValue({ data: mockItr, isLoading: false, error: null } as any)

      renderWithProviders(<TaxITRCompareTab />)

      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
      expect(screen.getByText(/Rahul Sharma/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Replace ITR/i })).toBeInTheDocument()
    })
  })

  describe('TaxHistoryTab', () => {
    it('shows empty state when no filings exist', async () => {
      renderWithProviders(<TaxHistoryTab />)

      expect(await screen.findByText(/No saved filings yet/i)).toBeInTheDocument()
    })

    it('lists saved filings and supports restore/delete', async () => {
      vi.mocked(apiClient.getTaxHistory).mockResolvedValue({
        sessions: [{
          session_id: 'tax-sess-2',
          fy: '2023-24',
          name: 'Priya Nair',
          gross_salary: 1400000,
          created_at: '2024-06-01T08:00:00.000Z',
        }],
      } as any)

      renderWithProviders(<TaxHistoryTab />)

      expect(await screen.findByText('FY 2023-24')).toBeInTheDocument()
      expect(await screen.findByText(/Priya Nair/i)).toBeInTheDocument()

      await userEvent.click(screen.getByRole('button', { name: /^Restore$/i }))
      expect(useAppStore.getState().taxSessionId).toBe('tax-sess-2')

      await userEvent.click(screen.getByRole('button', { name: /^Delete$/i }))
      expect(await screen.findByText('Delete this filing?')).toBeInTheDocument()
    })
  })

  describe('TaxAuditorFindings', () => {
    it('renders zero-cost warnings when flags are present', () => {
      renderWithProviders(
        <TaxAuditorFindings flags={{ zero_cost: [{ security: 'RELIANCE', suggestion: 'Set broker cost' }] }} />
      )

      expect(screen.getByText('TAX AUDITOR FINDINGS')).toBeInTheDocument()
      expect(screen.getByText('Missing Cost Basis (Zero Cost Warning)')).toBeInTheDocument()
      expect(screen.getByText('RELIANCE')).toBeInTheDocument()
    })

    it('returns null when no findings', () => {
      const { container } = renderWithProviders(<TaxAuditorFindings flags={{}} />)
      expect(container).toBeEmptyDOMElement()
    })
  })
})
