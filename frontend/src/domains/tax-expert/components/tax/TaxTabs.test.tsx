import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, within } from '@testing-library/react'
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
  mockSummaryNew,
  mockSummaryOld,
  mockSummaryMinimal,
  mockSummarySurcharge25,
  mockSummaryNegativeRefund,
  mockSummaryZeroTds,
  mockIncome,
  mockTaxRules,
  mockCapitalGains,
  mockCompareNew,
  mockCompareOld,
  mockItr,
  mockItrDue,
  mockItrNegativeDiff,
  mockItrZero,
  mockItrDifference,
  mockItrMissingBeforeRebate,
} = vi.hoisted(() => ({
  mockSummaryNew: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-2',
    gross_income: 1500000,
    total_tax: 180000,
    total_tax_paid: 185000,
    tds_paid: 170000,
    refund_or_due: 5000, // Refund
    income_heads: {
      salary: { gross: 1200000, net: 1100000, std_deduction: 50000, sec10_hra: 20000, sec10_lta: 10000, sec10_other: 5000, sec16_ptax: 2500, employer: 'Acme Corp (Section 192)' },
      business: { total_profit: 50000 },
      capital_gains: { total: 100000, total_special_rate: 80000, grandfather_benefit: 15000, slab_taxed_cg: 10000, stcg_other: 5000, stcg_equity: 50000, ltcg_equity: 30000, ltcg_equity_taxable: 20000, ltcg_other: 10000 },
      other_sources: { total: 50000 },
      crypto: { gains: 20000, tax: 6000 },
      gaming: { gains: 10000, tax: 3000 },
      misc_income: { total: 10000 },
    },
    deductions: { '80c': 150000, '80ccc': 10000, '80ccd1': 10000, '80ccd1b': 50000, '80ccd2': 20000, '80d': 25000, '80dd': 10000, '80u': 10000, '24b': 50000, '80e': 20000, '80tta': 10000, '80g': 5000, '80gga': 2000, '80ggc': 3000, other: 1000 },
    chapter_via_deductions_total: 350000,
    total_deductions: 350000,
    taxable_normal_income: 1200000,
    tax_on_normal_income: 100000,
    tax_on_capital_gains: { ltcg_equity: 10000, stcg_equity: 5000, ltcg_other: 2000, total: 17000 },
    rebate_87a: 12500,
    rebate_87a_on_cg: 2500,
    surcharge: 5000,
    surcharge_detail: { rate: 0.25, cg_rate: 0.15, marginal_relief: 1000 },
    cess: 7200,
    advance_tax: 10000,
    manual_tax_paid: 5000,
    interest_234_total: 2000,
    interest_234a: 500,
    interest_234b: 1000,
    interest_234c: 500,
    aggregate_liability: 182000,
    refunds: [{ fy: '2023-24', amount: 12000, date: '12-Oct-2024' }],
    overrides: {
      deductions: { '80c': 150000, '80ccc': 10000, '80ccd1': 10000, '80ccd1b': 50000, '80ccd2': 20000, '80d': 25000, '80dd': 10000, '80u': 10000, '80e': 20000, '80g': 5000, '80gga': 2000, '80ggc': 3000, hra: 20000, lta: 10000, sec10_other: 5000, ptax: 2500, '24b': 50000 },
      manual_taxes: 5000,
      foreign_interest: 50000,
      business_income: { revenue_44ada: 200000, revenue_44ad: 300000 },
      crypto_income: 20000,
      gaming_income: 10000,
    },
    reconciliation_flags: {
      zero_cost: [{ security: 'RELIANCE', suggestion: 'Override with broker cost' }],
      cost_mismatch: [{ security: 'TCS', ais_cost: 100000, broker_cost: 150000 }],
      duplicates_removed: 2,
    },
  },
  mockSummaryOld: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-2',
    gross_income: 1500000,
    total_tax: 210000,
    total_tax_paid: 185000,
    tds_paid: 170000,
    refund_or_due: -25000, // Due
    income_heads: {
      salary: { gross: 1200000, net: 1100000, std_deduction: 50000, sec10_hra: 20000, sec10_lta: 10000, sec10_other: 5000, sec16_ptax: 2500, employer: 'Acme Corp' },
      business: { total_profit: 50000 },
      capital_gains: { total: 100000, total_special_rate: 80000, grandfather_benefit: 15000, slab_taxed_cg: 10000, stcg_other: 5000, stcg_equity: 50000, ltcg_equity: 30000, ltcg_equity_taxable: 20000, ltcg_other: 10000 },
      other_sources: { total: 50000 },
      crypto: { gains: 20000, tax: 6000 },
      gaming: { gains: 10000, tax: 3000 },
      misc_income: { total: 10000 },
    },
    deductions: { '80c': 150000, '80ttb': 50000 },
    chapter_via_deductions_total: 200000,
    total_deductions: 200000,
    taxable_normal_income: 1100000,
    tax_on_normal_income: 120000,
    tax_on_capital_gains: { ltcg_equity: 10000, stcg_equity: 5000, ltcg_other: 2000, total: 17000 },
    rebate_87a: 0,
    rebate_87a_on_cg: 0,
    surcharge: 0,
    cess: 8000,
    advance_tax: 10000,
    manual_tax_paid: 5000,
    interest_234_total: 0,
    refunds: [],
    overrides: {
      deductions: { '80c': 150000, '80ccc': 10000, '80ccd1': 10000, '80ccd1b': 50000, '80ccd2': 20000, '80d': 25000, '80dd': 10000, '80u': 10000, '80e': 20000, '80g': 5000, '80gga': 2000, '80ggc': 3000, hra: 20000, lta: 10000, sec10_other: 5000, ptax: 2500, '24b': 50000, '80ttb': 50000 },
      manual_taxes: 5000,
    },
    reconciliation_flags: {},
  },
  mockSummaryZeroTds: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-1',
    gross_income: 500000,
    total_tax: 0,
    total_tax_paid: 0,
    tds_paid: 0,
    refund_or_due: 0,
    income_heads: {
      salary: { gross: 500000, net: 450000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0, employer: null },
      business: { total_profit: 0 },
      capital_gains: { total: 0 },
      other_sources: { total: 0 },
      crypto: { gains: 0, tax: 0 },
      gaming: { gains: 0, tax: 0 },
      misc_income: { total: 0 },
    },
    deductions: { '80c': 0, '80tta': 0 },
    total_deductions: 0,
    taxable_normal_income: 450000,
    tax_on_normal_income: 0,
    tax_on_capital_gains: { total: 0 },
    rebate_87a: 0,
    rebate_87a_on_cg: 0,
    surcharge: 0,
    cess: 0,
    advance_tax: 0,
    manual_tax_paid: 0,
    interest_234_total: 0,
    refunds: [],
    overrides: {
      deductions: {},
      manual_taxes: 0,
    },
    reconciliation_flags: null,
  },
  mockSummaryMinimal: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-1',
    gross_income: 800000,
    total_tax: 0,
    total_tax_paid: 10000,
    tds_paid: 10000,
    refund_or_due: 10000,
    income_heads: {
      salary: { gross: 800000, net: 750000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0, employer: null },
      business: { total_profit: 0 },
      capital_gains: { total: 0, ltcg_equity: 0, stcg_equity: 0, ltcg_other: 0 },
      other_sources: { total: 0 },
      crypto: { gains: 0, tax: 0 },
      gaming: { gains: 0, tax: 0 },
      misc_income: { total: 0 },
    },
    deductions: { '80c': 0 },
    total_deductions: 0,
    taxable_normal_income: 750000,
    tax_on_normal_income: 0,
    tax_on_capital_gains: { total: 0 },
    rebate_87a: 0,
    rebate_87a_on_cg: 0,
    surcharge: 0,
    cess: 0,
    advance_tax: 0,
    manual_tax_paid: 0,
    interest_234_total: 0,
    refunds: [],
    overrides: null,
    reconciliation_flags: null,
  },
  mockSummarySurcharge25: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-2',
    gross_income: 6000000,
    total_tax: 2000000,
    total_tax_paid: 1900000,
    tds_paid: 1800000,
    refund_or_due: 100000,
    income_heads: {
      salary: { gross: 5500000, net: 5400000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0 },
      business: { total_profit: 0 },
      capital_gains: { total: 500000, grandfather_benefit: 20000, slab_taxed_cg: 30000 },
      other_sources: { total: 0 },
      crypto: { gains: 0, tax: 0 },
      gaming: { gains: 0, tax: 0 },
      misc_income: { total: 0 },
    },
    deductions: { '80c': 150000 },
    chapter_via_deductions_total: 150000,
    total_deductions: 150000,
    taxable_normal_income: 5350000,
    tax_on_normal_income: 1500000,
    tax_on_capital_gains: { ltcg_equity: 50000, total: 50000 },
    rebate_87a: 0,
    rebate_87a_on_cg: 0,
    surcharge: 250000,
    surcharge_detail: { rate: 0.25, cg_rate: 0.15, marginal_relief: 0 },
    cess: 70000,
    advance_tax: 100000,
    manual_tax_paid: 0,
    interest_234_total: 10000,
    aggregate_liability: null,
    refunds: [],
    overrides: null,
    reconciliation_flags: null,
  },
  mockSummaryNegativeRefund: {
    ay: '2025-26',
    fy: '2024-25',
    itr_type: 'ITR-2',
    gross_income: 2000000,
    total_tax: 300000,
    total_tax_paid: 250000,
    tds_paid: 200000,
    refund_or_due: -50000,
    income_heads: {
      salary: { gross: 2000000, net: 1950000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0 },
      business: { total_profit: 0 },
      capital_gains: { total: 0 },
      other_sources: { total: 0 },
      crypto: { gains: 0, tax: 0 },
      gaming: { gains: 0, tax: 0 },
      misc_income: { total: 0 },
    },
    deductions: { '80c': 0 },
    total_deductions: 0,
    taxable_normal_income: 1950000,
    tax_on_normal_income: 300000,
    tax_on_capital_gains: { total: 0 },
    rebate_87a: 0,
    rebate_87a_on_cg: 0,
    surcharge: 0,
    cess: 12000,
    advance_tax: 50000,
    manual_tax_paid: 0,
    interest_234_total: 0,
    refunds: [],
    overrides: null,
    reconciliation_flags: null,
  },
  mockIncome: {
    personal: { dob: '01/01/1985' },
    salary: {
      gross: 1200000,
      employer: 'Section 192) Acme Corp (HQ)',
      tds_deducted: 150000,
      quarterly: [{ amount_paid: 100000 }, { amount_paid: 50 }],
    },
    business: {},
    total_savings_interest: 10000,
    total_fd_interest: 5000,
    total_misc_income: 20000,
    total_dividends: 15000,
    total_other_interest: 8000,
    interest_savings: [{ bank: 'HDFC BANK LIMITED', amount: 10000 }],
    interest_deposits: [{ bank: 'ICICI BANK LTD', amount: 5000 }],
    interest_others: [{ source: 'NABARD BONDS LTD', type: 'Bond Interest', amount: 8000 }],
    dividends: [{ source: 'INFOSYS LIMITED', amount: 15000 }],
    misc_income: [{ source: 'FREELANCE HUB PVT LTD', type: 'Professional', code: '194J', amount: 20000 }],
  },
  mockTaxRules: {
    deductions: { limit_80tta: 10000 },
    ui_tooltips: {
      section_16_ia: { text: 'Standard deduction\nu/s 16(ia)' },
      section_44ada: { text: 'Presumptive professional' },
      section_44ad: { text: 'Presumptive business' },
      misc_income: { text: 'Misc income' },
      section_80tta: { text: 'Savings interest' },
      section_80ttb: { text: 'Senior interest' },
      other_interest: { text: 'Other interest' },
      dividend: { text: 'Dividend' },
      foreign_interest: { text: 'Foreign interest' },
      crypto_vda: { text: 'Crypto VDA' },
      gaming_lottery: { text: 'Gaming lottery' },
    },
  },
  mockCapitalGains: {
    bf_losses: { stcl: 5000, ltcl: 10000 },
    equity_shares: [
      { sr: '1', date: '2024-05-10', quantity: '100', type: 'STCG', security: 'INFY', consideration: 100000, cost: 80000, gain: 20000, is_zero_cost: false, patched: true },
      { sr: '2', date: '2024-06-15', quantity: '50', type: 'LTCG', security: 'TCS', consideration: 200000, cost: 150000, gain: 50000, is_zero_cost: false, patched: false },
    ],
    equity_shares_count: 2,
    equity_mf: [
      { sr: '3', date: '2024-07-20', quantity: '200', type: 'STCG', fund: 'HDFC Midcap', consideration: 50000, cost: 40000, gain: 10000, is_zero_cost: false, patched: false },
      { sr: '4', date: '2024-08-25', quantity: '300', type: 'LTCG', fund: 'Axis Bluechip', consideration: 80000, cost: 60000, gain: 20000, is_zero_cost: false, patched: false },
    ],
    equity_mf_count: 2,
    real_estate: [
      { sr: '5', date: '2024-09-10', quantity: '1', type: 'LTCG', security: 'Plot in Bangalore', consideration: 5000000, cost: 3500000, gain: 1500000, is_zero_cost: false, patched: false },
    ],
    real_estate_count: 1,
    bonds_gold: [
      { sr: '6', date: '2024-10-05', quantity: '10', type: 'LTCG', security: 'SGB Bond', consideration: 60000, cost: 50000, gain: 10000, is_zero_cost: false, patched: false }
    ],
    bonds_gold_count: 1,
    unlisted: [
      { sr: '7', date: '2024-11-12', quantity: '500', type: 'STCG', security: 'US Tech Stock', consideration: 120000, cost: 100000, gain: 20000, is_zero_cost: false, patched: false }
    ],
    unlisted_count: 1,
    other_mf: [
      { sr: '8', date: '2024-12-01', quantity: '100', type: 'STCG', fund: 'Liquid Debt Fund', consideration: 25000, cost: 24000, gain: 1000, is_zero_cost: false, patched: false }
    ],
    other_mf_count: 1,
  },
  mockCompareNew: {
    recommended: 'new',
    new_regime: { total_tax: 180000 },
    old_regime: { total_tax: 210000 },
  },
  mockCompareOld: {
    recommended: 'old',
    new_regime: { total_tax: 220000 },
    old_regime: { total_tax: 190000 },
  },
  mockItr: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-2',
    assessment_year: '2025-26',
    income: {
      salary_gross: 1200000,
      salary: 1100000,
      salary_exemptions: 35000,
      house_property: 0,
      business: 50000,
      capital_gains: 100000,
      other_sources: 50000,
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
      rebate_87a: 12500,
      surcharge: 5000,
      cess: 7200,
      total_tax_liability: 180000,
      tds_paid: 170000,
      advance_tax: 10000,
      total_taxes_paid: 185000,
      interest_234_total: 2000,
      interest_234a: 500,
      interest_234b: 1000,
      interest_234c: 500,
    },
  },
  mockItrMissingBeforeRebate: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-2',
    assessment_year: '2025-26',
    income: {
      salary_gross: 1200000,
      salary: 1100000,
      salary_exemptions: 0,
      house_property: 0,
      business: 0,
      capital_gains: 0,
      other_sources: 0,
      gross_total: 1200000,
    },
    deductions: { total: 0 },
    tax: {
      refund_or_due: 5000,
      taxable_income: 1200000,
      tax_at_slab_rates: null,
      tax_on_income: 100000,
      tax_at_special_rate: 0,
      tax_before_rebate: null, // Tests fallback to tax_on_income
      rebate_87a: 12500,
      surcharge: 0,
      cess: 4000,
      total_tax_liability: 104000,
      tds_paid: 109000,
      advance_tax: 0,
      total_taxes_paid: 109000,
      interest_234_total: 0,
    },
  },
  mockItrDifference: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-2',
    assessment_year: '2025-26',
    income: {
      salary_gross: 1300000, // Higher than FB
      salary: 1200000,
      salary_exemptions: 20000,
      house_property: 10000,
      business: 40000,
      capital_gains: 80000,
      other_sources: 40000,
      gross_total: 1400000,
    },
    deductions: { total: 100000 },
    tax: {
      refund_or_due: 1000, // Difference with FB (5000 vs 1000 => +4000)
      taxable_income: 1300000,
      tax_at_slab_rates: 90000,
      tax_on_income: 90000,
      tax_at_special_rate: 10000,
      tax_before_rebate: 100000,
      rebate_87a: 0,
      surcharge: 0,
      cess: 4000,
      total_tax_liability: 104000,
      tds_paid: 100000,
      advance_tax: 5000,
      total_taxes_paid: 105000,
      interest_234_total: 1000,
      interest_234a: 200,
      interest_234b: 500,
      interest_234c: 300,
    },
  },
  mockItrNegativeDiff: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-2',
    assessment_year: '2025-26',
    income: {
      salary_gross: 1100000, // Lower than FB (1200000 vs 1100000)
      salary: 1000000,
      salary_exemptions: 0,
      house_property: 0,
      business: 0,
      capital_gains: 0,
      other_sources: 0,
      gross_total: 1100000,
    },
    deductions: { total: 50000 },
    tax: {
      refund_or_due: 10000, // ITR refund is 10000, FB refund is 5000 => diff = -5000
      taxable_income: 1050000,
      tax_at_slab_rates: 80000,
      tax_on_income: 80000,
      tax_at_special_rate: 0,
      tax_before_rebate: 80000,
      rebate_87a: 0,
      surcharge: 0,
      cess: 3200,
      total_tax_liability: 83200,
      tds_paid: 90000,
      advance_tax: 3200,
      total_taxes_paid: 93200,
      interest_234_total: 0,
    },
  },
  mockItrDue: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-2',
    assessment_year: '2025-26',
    income: {
      salary_gross: 1000000,
      salary: 950000,
      salary_exemptions: 0,
      house_property: 0,
      business: 0,
      capital_gains: 0,
      other_sources: 0,
      gross_total: 1000000,
    },
    deductions: { total: 0 },
    tax: {
      refund_or_due: -15000, // Due
      taxable_income: 1000000,
      tax_at_slab_rates: 110000,
      tax_on_income: 110000,
      tax_at_special_rate: 0,
      tax_before_rebate: 110000,
      rebate_87a: 0,
      surcharge: 0,
      cess: 4400,
      total_tax_liability: 114400,
      tds_paid: 90000,
      advance_tax: 0,
      total_taxes_paid: 90000,
      interest_234_total: 0,
    },
  },
  mockItrZero: {
    name: 'Rahul Sharma',
    pan: 'ABCDE1234F',
    itr_type: 'ITR-1',
    assessment_year: '2025-26',
    income: {
      salary_gross: 500000,
      salary: 450000,
      salary_exemptions: 0,
      house_property: 0,
      business: 0,
      capital_gains: 0,
      other_sources: 0,
      gross_total: 500000,
    },
    deductions: { total: 0 },
    tax: {
      refund_or_due: 0, // Exactly zero
      taxable_income: 450000,
      tax_at_slab_rates: 0,
      tax_on_income: 0,
      tax_at_special_rate: 0,
      tax_before_rebate: 0,
      rebate_87a: 0,
      surcharge: 0,
      cess: 0,
      total_tax_liability: 0,
      tds_paid: 0,
      advance_tax: 0,
      total_taxes_paid: 0,
      interest_234_total: 0,
    },
  },
}))

const mockMutateOverrides = vi.fn()
const mockMutateTxCost = vi.fn()
const mockMutateUploadItr = vi.fn()

vi.mock('../../hooks/useTaxExpert', () => ({
  useTaxExpertSummary: vi.fn((regime) => ({
    data: regime === 'old' ? mockSummaryOld : mockSummaryNew,
    isLoading: false,
    error: null,
  })),
  useTaxExpertIncome: vi.fn(() => ({ data: mockIncome, isLoading: false, error: null })),
  useTaxExpertCapitalGains: vi.fn(() => ({ data: mockCapitalGains, isLoading: false, error: null })),
  useTaxRegimeComparison: vi.fn(() => ({ data: mockCompareNew, isLoading: false, error: null })),
  useTaxRules: vi.fn(() => ({ data: mockTaxRules, isLoading: false, error: null })),
  useTaxExpertOverrides: vi.fn(() => ({ mutate: mockMutateOverrides, mutateAsync: vi.fn(), isPending: false })),
  useTaxExpertTransactionCost: vi.fn(() => ({ mutate: mockMutateTxCost, mutateAsync: vi.fn(), isPending: false })),
  useITRData: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  useUploadITR: vi.fn(() => ({ mutate: mockMutateUploadItr, isPending: false, isError: false })),
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

    vi.mocked(useTaxExpertSummary).mockImplementation((regime) => ({
      data: regime === 'old' ? mockSummaryOld : mockSummaryNew,
      isLoading: false,
      error: null,
    } as any))
    vi.mocked(useTaxExpertIncome).mockReturnValue({ data: mockIncome, isLoading: false, error: null } as any)
    vi.mocked(useTaxExpertCapitalGains).mockReturnValue({ data: mockCapitalGains, isLoading: false, error: null } as any)
    vi.mocked(useTaxRegimeComparison).mockReturnValue({ data: mockCompareNew, isLoading: false, error: null } as any)
    vi.mocked(useTaxRules).mockReturnValue({ data: mockTaxRules, isLoading: false, error: null } as any)
    vi.mocked(useITRData).mockReturnValue({ data: null, isLoading: false, error: null } as any)
    vi.mocked(apiClient.getTaxHistory).mockResolvedValue({ sessions: [] } as any)
    vi.mocked(apiClient.deleteTaxSession).mockResolvedValue({ status: 'deleted' } as any)
    vi.mocked(apiClient.reconcileBrokerFile).mockResolvedValue({ success: true } as any)
  })

  // ────────────────────────────────────────────────────────────────
  // 1. TaxAuditorFindings
  // ────────────────────────────────────────────────────────────────
  describe('TaxAuditorFindings', () => {
    it('renders zero-cost and cost-mismatch findings', () => {
      renderWithProviders(
        <TaxAuditorFindings
          flags={{
            zero_cost: [{ security: 'RELIANCE', suggestion: 'Set broker cost' }],
            cost_mismatch: [{ security: 'TCS', ais_cost: 100000, broker_cost: 150000 }],
          }}
        />
      )

      expect(screen.getByText('TAX AUDITOR FINDINGS')).toBeInTheDocument()
      expect(screen.getByText('Missing Cost Basis (Zero Cost Warning)')).toBeInTheDocument()
      expect(screen.getByText('RELIANCE')).toBeInTheDocument()
      expect(screen.getByText('Grandfathering / Cost Mismatch')).toBeInTheDocument()
      expect(screen.getByText('TCS')).toBeInTheDocument()
    })

    it('returns null when flags is undefined or empty', () => {
      const { container: c1 } = renderWithProviders(<TaxAuditorFindings flags={undefined} />)
      expect(c1).toBeEmptyDOMElement()

      const { container: c2 } = renderWithProviders(<TaxAuditorFindings flags={{ zero_cost: [], cost_mismatch: [] }} />)
      expect(c2).toBeEmptyDOMElement()
    })
  })

  // ────────────────────────────────────────────────────────────────
  // 2. TaxOverviewTab
  // ────────────────────────────────────────────────────────────────
  describe('TaxOverviewTab', () => {
    it('renders loading skeleton when summaries are loading', () => {
      vi.mocked(useTaxExpertSummary).mockReturnValue({ data: null, isLoading: true, error: null } as any)
      const { container } = renderWithProviders(<TaxOverviewTab />)
      expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    })

    it('renders side-by-side comparison with all deduction and exemption steps', async () => {
      renderWithProviders(<TaxOverviewTab />)

      expect(await screen.findByText('Tax Summary')).toBeInTheDocument()
      expect(screen.getByText('Choose the')).toBeInTheDocument()
      expect(screen.getByText('Gross Total Income (GTI)')).toBeInTheDocument()
      expect(screen.getByText('Chapter VI-A Deductions')).toBeInTheDocument()
      expect(screen.getByText('Net Taxable Income')).toBeInTheDocument()
      expect(screen.getByText('Tax Calculation')).toBeInTheDocument()
      expect(screen.getByText('Final Settlement')).toBeInTheDocument()
    })

    it('renders Old Regime recommendation correctly and handles fallback without 80ttb', async () => {
      vi.mocked(useTaxRegimeComparison).mockReturnValue({ data: mockCompareOld, isLoading: false, error: null } as any)
      vi.mocked(useTaxExpertSummary).mockImplementation((regime) => ({
        data: {
          ...(regime === 'old' ? mockSummaryOld : mockSummaryNew),
          deductions: { '80tta': 10000 },
          income_heads: {
            ...mockSummaryNew.income_heads,
            salary: { gross: 1000000, net: 950000, std_deduction: 50000, sec10_hra: 0, sec10_lta: 0, sec10_other: 0, sec16_ptax: 0 },
            capital_gains: { total: 0, grandfather_benefit: 0, slab_taxed_cg: 0 },
          },
          rebate_87a: 0,
          rebate_87a_on_cg: 0,
          surcharge: 0,
          interest_234_total: 0,
        },
        isLoading: false,
        error: null,
      } as any))

      renderWithProviders(<TaxOverviewTab />)

      expect(await screen.findByText('Tax Summary')).toBeInTheDocument()
      expect(screen.getByText('Old Regime')).toBeInTheDocument()
      expect(screen.getByText(/Sec 80TTA \(Savings Interest\)/i)).toBeInTheDocument()
    })

    it('renders surcharge details with rate different from 0.25 and marginal relief', async () => {
      vi.mocked(useTaxExpertSummary).mockImplementation((regime) => ({
        data: {
          ...(regime === 'old' ? mockSummaryOld : mockSummaryNew),
          surcharge: 10000,
          surcharge_detail: { rate: 0.15, cg_rate: 0.15, marginal_relief: 500 },
          rebate_87a: 5000,
          rebate_87a_on_cg: 1000,
          interest_234_total: 1000,
          aggregate_liability: 181000,
        },
        isLoading: false,
        error: null,
      } as any))

      renderWithProviders(<TaxOverviewTab />)
      expect(await screen.findByText(/marginal relief applied/i)).toBeInTheDocument()
    })

    it('renders old regime rebate with new regime zero rebate, and old regime marginal relief', async () => {
      vi.mocked(useTaxExpertSummary).mockImplementation((regime) => ({
        data: {
          ...(regime === 'old' ? mockSummaryOld : mockSummaryNew),
          rebate_87a: regime === 'old' ? 12500 : 0,
          rebate_87a_on_cg: 0,
          surcharge: regime === 'old' ? 5000 : 0,
          surcharge_detail: regime === 'old' ? { rate: 0.10, cg_rate: 0.10, marginal_relief: 500 } : null,
          interest_234_total: 1500,
          aggregate_liability: null,
        },
        isLoading: false,
        error: null,
      } as any))

      renderWithProviders(<TaxOverviewTab />)
      expect(await screen.findByText(/Tax after rebate/i)).toBeInTheDocument()
      expect(screen.getByText(/marginal relief applied/i)).toBeInTheDocument()
      expect(screen.getByText(/Aggregate Liability \(Tax \+ Interest\)/i)).toBeInTheDocument()
    })

    it('renders surcharge capped at 25% and negative refund (due) branch', async () => {
      vi.mocked(useTaxExpertSummary).mockImplementation((regime) => ({
        data: regime === 'new' ? mockSummarySurcharge25 : mockSummaryNegativeRefund,
        isLoading: false,
        error: null,
      } as any))

      renderWithProviders(<TaxOverviewTab />)
      expect(await screen.findByText(/New Regime surcharge capped at 25%/i)).toBeInTheDocument()
      expect(screen.getByText(/DUE: ₹50,000/i)).toBeInTheDocument()
    })
  })

  // ────────────────────────────────────────────────────────────────
  // 3. TaxIncomeTab
  // ────────────────────────────────────────────────────────────────
  describe('TaxIncomeTab', () => {
    it('renders loading skeleton when income data is loading', () => {
      vi.mocked(useTaxExpertIncome).mockReturnValue({ data: null, isLoading: true, error: null } as any)
      const { container } = renderWithProviders(<TaxIncomeTab />)
      expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    })

    it('toggles categories and updates income overrides via input fields', async () => {
      renderWithProviders(<TaxIncomeTab />)
      expect(await screen.findByText('Income Sources')).toBeInTheDocument()

      // Toggle Core category off and on
      await userEvent.click(screen.getByText('Core Income'))
      await userEvent.click(screen.getByText('Core Income'))

      // Toggle Salary card off and on
      await userEvent.click(screen.getByText('Salary Income'))
      await userEvent.click(screen.getByText('Salary Income'))

      // Toggle Misc Income card
      await userEvent.click(screen.getByText(/Misc\. Income \(Freelance, Rent, etc\.\)/i))
      await userEvent.click(screen.getByText(/Misc\. Income \(Freelance, Rent, etc\.\)/i))

      // Toggle Interest category
      await userEvent.click(screen.getByText('Interest & Dividends'))
      expect(screen.getByText('Savings Bank Interest')).toBeInTheDocument()

      // Toggle Other Interest Income card
      await userEvent.click(screen.getByText('Other Interest Income'))
      await userEvent.click(screen.getByText('Other Interest Income'))

      // Toggle Special category
      await userEvent.click(screen.getByText('Special Rates'))
      expect(screen.getByText('Crypto Income (VDA)')).toBeInTheDocument()

      // Expand Crypto card and type in field, then collapse
      await userEvent.click(screen.getByText('Crypto Income (VDA)'))
      const cryptoInput = screen.getByPlaceholderText('Total Crypto Gains (₹)')
      await userEvent.clear(cryptoInput)
      await userEvent.type(cryptoInput, '25000')
      fireEvent.blur(cryptoInput)
      expect(mockMutateOverrides).toHaveBeenCalledWith({ crypto_income: 25000 })
      await userEvent.click(screen.getByText('Crypto Income (VDA)'))

      // Expand Gaming card and type in field, then collapse
      await userEvent.click(screen.getByText('Gaming & Lottery (115BB)'))
      const gamingInput = screen.getByPlaceholderText('Net Winnings (₹)')
      await userEvent.clear(gamingInput)
      await userEvent.type(gamingInput, '15000')
      fireEvent.blur(gamingInput)
      expect(mockMutateOverrides).toHaveBeenCalledWith({ gaming_income: 15000 })
      await userEvent.click(screen.getByText('Gaming & Lottery (115BB)'))

      // Switch back to Core category
      await userEvent.click(screen.getByText('Core Income'))

      // Expand 44ADA card, type, and collapse
      await userEvent.click(screen.getByText('Professional Income (44ADA)'))
      const adaInput = screen.getByPlaceholderText('Gross Receipts (₹)')
      await userEvent.clear(adaInput)
      await userEvent.type(adaInput, '250000')
      fireEvent.blur(adaInput)
      expect(mockMutateOverrides).toHaveBeenCalledWith({ business_income: expect.objectContaining({ revenue_44ada: 250000 }) })
      await userEvent.click(screen.getByText('Professional Income (44ADA)'))

      // Expand 44AD card, type, and collapse
      await userEvent.click(screen.getByText('Business Income (44AD)'))
      const adInput = screen.getByPlaceholderText('Gross Turnover (₹)')
      await userEvent.clear(adInput)
      await userEvent.type(adInput, '400000')
      fireEvent.blur(adInput)
      expect(mockMutateOverrides).toHaveBeenCalledWith({ business_income: expect.objectContaining({ revenue_44ad: 400000 }) })
      await userEvent.click(screen.getByText('Business Income (44AD)'))

      // Expand Misc income card and collapse
      await userEvent.click(screen.getByText('Misc. Income (Freelance, Rent, etc.)'))
      expect(screen.getByText(/FREELANCE HUB/i)).toBeInTheDocument()
      await userEvent.click(screen.getByText('Misc. Income (Freelance, Rent, etc.)'))
    })

    it('handles senior citizen calculation and empty lists in interest cards', async () => {
      useAppStore.setState({ taxRegime: 'old' })
      vi.mocked(useTaxExpertIncome).mockReturnValue({
        data: {
          ...mockIncome,
          personal: { dob: '01/01/1950' }, // Senior citizen (76 years old)
          interest_savings: [],
          interest_deposits: [],
          interest_others: [],
          dividends: [],
          misc_income: [],
        },
        isLoading: false,
        error: null,
      } as any)

      renderWithProviders(<TaxIncomeTab />)
      await screen.findByText('Income Sources')

      // Open Interest category
      await userEvent.click(screen.getByText('Interest & Dividends'))
      expect(await screen.findByText('No savings interest reported in AIS')).toBeInTheDocument()

      // Open Savings card and collapse
      await userEvent.click(screen.getByText('Savings Bank Interest'))
      await userEvent.click(screen.getByText('Savings Bank Interest'))

      // Open Term deposit card and collapse (tests senior citizen old regime branch!)
      await userEvent.click(screen.getByText('Term Deposit Interest'))
      expect(screen.getByText('No deposit interest reported in AIS')).toBeInTheDocument()
      expect(screen.getByText('Exempt u/s 80TTB (Shared with Savings)')).toBeInTheDocument()
      await userEvent.click(screen.getByText('Term Deposit Interest'))

      // Open Other interest card and collapse
      await userEvent.click(screen.getByText('Other Interest Income'))
      expect(screen.getByText('No P2P, Bond, or other interest reported in AIS')).toBeInTheDocument()
      await userEvent.click(screen.getByText('Other Interest Income'))

      // Open Dividend card and collapse
      await userEvent.click(screen.getByText('Dividend Income'))
      expect(screen.getByText('No dividend income reported in AIS')).toBeInTheDocument()
      await userEvent.click(screen.getByText('Dividend Income'))

      // Open Foreign interest card, type, blur and collapse
      await userEvent.click(screen.getByText('Foreign Interest / Dividends'))
      const foreignInput = screen.getByPlaceholderText('Enter amount (₹)')
      await userEvent.clear(foreignInput)
      await userEvent.type(foreignInput, '75000')
      fireEvent.blur(foreignInput)
      expect(mockMutateOverrides).toHaveBeenCalledWith({ foreign_interest: 75000 })
      await userEvent.click(screen.getByText('Foreign Interest / Dividends'))
    })

    it('handles non-senior citizen in old regime and missing dob', async () => {
      useAppStore.setState({ taxRegime: 'old' })
      vi.mocked(useTaxExpertIncome).mockReturnValue({
        data: {
          ...mockIncome,
          personal: { dob: null },
          salary: {
            gross: 0,
            employer: 'General Employer',
            tds_deducted: 0,
            quarterly: [],
          },
        },
        isLoading: false,
        error: null,
      } as any)

      renderWithProviders(<TaxIncomeTab />)
      expect(await screen.findByText('Income Sources')).toBeInTheDocument()
    })
  })

  // ────────────────────────────────────────────────────────────────
  // 4. TaxSavingsTab
  // ────────────────────────────────────────────────────────────────
  describe('TaxSavingsTab', () => {
    it('renders all deduction categories, toggles them, and updates deduction amounts', async () => {
      renderWithProviders(<TaxSavingsTab />)
      expect(await screen.findByText('Tax Savings & TDS')).toBeInTheDocument()

      // 1. Popular category - toggle off and on
      await userEvent.click(screen.getByText(/Popular Tax Saving Investments/i))
      await userEvent.click(screen.getByText(/Popular Tax Saving Investments/i))

      // 80C
      const item80c = screen.getByText(/80C - PPF, ELSS/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80c).getByText('₹1,50,000'))
      const input80c = await screen.findByDisplayValue('150000')
      await userEvent.clear(input80c)
      await userEvent.type(input80c, '140000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80c': 140000 })
      }))

      // 80CCC
      const item80ccc = screen.getByText(/80CCC - Pension/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80ccc).getByText('₹10,000'))
      const input80ccc = await screen.findByDisplayValue('10000')
      await userEvent.clear(input80ccc)
      await userEvent.type(input80ccc, '15000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80ccc': 15000 })
      }))

      // 80CCD(1)
      const item80ccd1 = screen.getByText(/80CCD \(1\) - Employee/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80ccd1).getByText('₹10,000'))
      const input80ccd1 = await screen.findByDisplayValue('10000')
      await userEvent.clear(input80ccd1)
      await userEvent.type(input80ccd1, '12000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80ccd1': 12000 })
      }))

      // 80CCD(1B)
      const item80ccd1b = screen.getByText(/80CCD \(1B\) - Additional/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80ccd1b).getByText('₹50,000'))
      const input80ccd1b = await screen.findByDisplayValue('50000')
      await userEvent.clear(input80ccd1b)
      await userEvent.type(input80ccd1b, '45000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80ccd1b': 45000 })
      }))

      // 80CCD(2)
      const item80ccd2 = screen.getByText(/80CCD\(2\) - Employer/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80ccd2).getByText('₹20,000'))
      const input80ccd2 = await screen.findByDisplayValue('20000')
      await userEvent.clear(input80ccd2)
      await userEvent.type(input80ccd2, '25000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80ccd2': 25000 })
      }))

      // 2. Medical category - toggle on, then off, then on
      await userEvent.click(screen.getByText(/Medical Insurance, Health Check-ups, Disabilities/i))
      expect(screen.getByText(/80D - Medical Insurance/i)).toBeInTheDocument()
      await userEvent.click(screen.getByText(/Medical Insurance, Health Check-ups, Disabilities/i))
      await userEvent.click(screen.getByText(/Medical Insurance, Health Check-ups, Disabilities/i))

      // 80D
      const item80d = screen.getByText(/80D - Medical Insurance/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80d).getByText('₹25,000'))
      const input80d = await screen.findByDisplayValue('25000')
      await userEvent.clear(input80d)
      await userEvent.type(input80d, '30000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80d': 30000 })
      }))

      // 80DD
      const item80dd = screen.getByText(/80DD - Deduction for Disabled/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80dd).getByText('₹10,000'))
      const input80dd = await screen.findByDisplayValue('10000')
      await userEvent.clear(input80dd)
      await userEvent.type(input80dd, '15000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80dd': 15000 })
      }))

      // 80U
      const item80u = screen.getByText(/80U - Deduction for Self Disability/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80u).getByText('₹10,000'))
      const input80u = await screen.findByDisplayValue('10000')
      await userEvent.clear(input80u)
      await userEvent.type(input80u, '20000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80u': 20000 })
      }))

      // 3. Donations category - toggle on, then off, then on
      await userEvent.click(screen.getByText(/Donations \/ Contributions/i))
      expect(screen.getByText(/80G - Donations to charitable organizations/i)).toBeInTheDocument()
      await userEvent.click(screen.getByText(/Donations \/ Contributions/i))
      await userEvent.click(screen.getByText(/Donations \/ Contributions/i))

      // 80G
      const item80g = screen.getByText(/80G - Donations to charitable/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80g).getByText('₹5,000'))
      const input80g = await screen.findByDisplayValue('5000')
      await userEvent.clear(input80g)
      await userEvent.type(input80g, '6000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80g': 6000 })
      }))

      // 80GGA
      const item80gga = screen.getByText(/80GGA - Donations for Research/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80gga).getByText('₹2,000'))
      const input80gga = await screen.findByDisplayValue('2000')
      await userEvent.clear(input80gga)
      await userEvent.type(input80gga, '3000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80gga': 3000 })
      }))

      // 80GGC
      const item80ggc = screen.getByText(/80GGC - Contribution to political/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80ggc).getByText('₹3,000'))
      const input80ggc = await screen.findByDisplayValue('3000')
      await userEvent.clear(input80ggc)
      await userEvent.type(input80ggc, '4000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80ggc': 4000 })
      }))

      // 4. Loans category - toggle on, then off, then on
      await userEvent.click(screen.getByText(/^Loans$/i))
      expect(screen.getByText(/Section 24\(b\) - Home Loan Interest/i)).toBeInTheDocument()
      await userEvent.click(screen.getByText(/^Loans$/i))
      await userEvent.click(screen.getByText(/^Loans$/i))

      // 24(b)
      const item24b = screen.getByText(/Section 24\(b\)/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item24b).getByText('₹50,000'))
      const input24b = await screen.findByDisplayValue('50000')
      await userEvent.clear(input24b)
      await userEvent.type(input24b, '60000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '24b': 60000 })
      }))

      // 80E
      const item80e = screen.getByText(/Section 80E - Education Loan/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(item80e).getByText('₹20,000'))
      const input80e = await screen.findByDisplayValue('20000')
      await userEvent.clear(input80e)
      await userEvent.type(input80e, '22000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ '80e': 22000 })
      }))

      // 5. Salary Exemptions category - toggle on, then off, then on
      await userEvent.click(screen.getByText(/Salary Exemptions \(Section 10\)/i))
      expect(screen.getByText(/House Rent Allowance \(HRA\)/i)).toBeInTheDocument()
      await userEvent.click(screen.getByText(/Salary Exemptions \(Section 10\)/i))
      await userEvent.click(screen.getByText(/Salary Exemptions \(Section 10\)/i))

      // HRA
      const itemHra = screen.getByText(/House Rent Allowance \(HRA\)/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(itemHra).getByText('₹20,000'))
      const inputHra = await screen.findByDisplayValue('20000')
      await userEvent.clear(inputHra)
      await userEvent.type(inputHra, '25000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ hra: 25000 })
      }))

      // LTA
      const itemLta = screen.getByText(/Leave Travel Allowance \(LTA\)/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(itemLta).getByText('₹10,000'))
      const inputLta = await screen.findByDisplayValue('10000')
      await userEvent.clear(inputLta)
      await userEvent.type(inputLta, '12000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ lta: 12000 })
      }))

      // Other Allowances
      const itemOther = screen.getByText(/^Other Allowances$/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(itemOther).getByText('₹5,000'))
      const inputOther = await screen.findByDisplayValue('5000')
      await userEvent.clear(inputOther)
      await userEvent.type(inputOther, '7000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ sec10_other: 7000 })
      }))

      // Professional Tax
      const itemPtax = screen.getByText(/Professional Tax/i).closest('.MuiPaper-root') as HTMLElement
      await userEvent.click(within(itemPtax).getByText('₹2,500'))
      const inputPtax = await screen.findByDisplayValue('2500')
      await userEvent.clear(inputPtax)
      await userEvent.type(inputPtax, '2500{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        deductions: expect.objectContaining({ ptax: 2500 })
      }))

      // 6. TDS category - toggle on, then off, then on
      await userEvent.click(screen.getByText('TDS & Taxes Paid'))
      expect(screen.getByText('TDS on Salary (Sec 192)')).toBeInTheDocument()
      expect(screen.getByText('PREVIOUS REFUNDS')).toBeInTheDocument()
      await userEvent.click(screen.getByText('TDS & Taxes Paid'))
      await userEvent.click(screen.getByText('TDS & Taxes Paid'))

      // Edit Self Tax Payments / Challans
      const challanHeading = screen.getByText('Self Tax Payments / Challans')
      const challanContainer = challanHeading.closest('.MuiPaper-root') || challanHeading.parentElement?.parentElement
      const valManualTax = within(challanContainer as HTMLElement).getByText('₹5,000')
      await userEvent.click(valManualTax)
      const inputManualTax = screen.getByDisplayValue('5000')
      await userEvent.clear(inputManualTax)
      await userEvent.type(inputManualTax, '8000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith(expect.objectContaining({
        manual_taxes: 8000
      }))
    })

    it('renders with zero TDS amounts, empty overrides and empty refunds', async () => {
      vi.mocked(useTaxExpertSummary).mockImplementation(() => ({
        data: mockSummaryZeroTds,
        isLoading: false,
        error: null,
      } as any))

      renderWithProviders(<TaxSavingsTab />)
      expect(await screen.findByText('Tax Savings & TDS')).toBeInTheDocument()
      await userEvent.click(screen.getByText('TDS & Taxes Paid'))
      expect(screen.getByText('Deducted by employer')).toBeInTheDocument()
    })
  })

  // ────────────────────────────────────────────────────────────────
  // 5. TaxCapitalGainsTab
  // ────────────────────────────────────────────────────────────────
  describe('TaxCapitalGainsTab', () => {
    it('renders loading skeleton when capital gains is loading', () => {
      vi.mocked(useTaxExpertCapitalGains).mockReturnValue({ data: null, isLoading: true, error: null } as any)
      const { container } = renderWithProviders(<TaxCapitalGainsTab />)
      expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    })

    it('renders capital gains breakdown with reconciliation banner, toggles accordions and edits transaction costs', async () => {
      renderWithProviders(<TaxCapitalGainsTab />)
      expect(await screen.findByText('Capital Gains')).toBeInTheDocument()
      expect(screen.getByText('Reconciliation Successful')).toBeInTheDocument()

      // Edit transaction cost in equity shares (already open by default)
      const infyLabel = await screen.findByText('INFY')
      const infyRow = infyLabel.closest('.MuiBox-root')?.parentElement
      const costEls = within(infyRow as HTMLElement).getAllByText('₹80,000')
      await userEvent.click(costEls[1])
      const costInput = await screen.findByDisplayValue('80000')
      await userEvent.clear(costInput)
      await userEvent.type(costInput, '85000{Enter}')
      expect(mockMutateTxCost).toHaveBeenCalledWith(expect.objectContaining({
        category: 'capital_gains_equity',
        new_cost: 85000,
        sr: '1'
      }))

      // Toggle Equity category closed and open
      await userEvent.click(screen.getByText('Equity & Equity Mutual Funds'))
      await userEvent.click(screen.getByText('Equity & Equity Mutual Funds'))

      // Toggle Other Capital Assets
      await userEvent.click(screen.getByText('Other Capital Assets'))
      expect(screen.getByText(/Real Estate \(Land & Building\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Gold & Bonds/i)).toBeInTheDocument()
      expect(screen.getByText(/Foreign Assets & Unlisted Equity/i)).toBeInTheDocument()
      expect(screen.getByText(/Debt \/ Other Funds/i)).toBeInTheDocument()
      await userEvent.click(screen.getByText('Other Capital Assets'))
      await userEvent.click(screen.getByText('Other Capital Assets'))

      // Toggle Brought forward losses and edit them
      await userEvent.click(screen.getByText('Brought Forward Losses'))
      const stclHeading = screen.getByText(/B\/F Short-Term Capital Loss \(STCL\)/i)
      const stclContainer = stclHeading.parentElement?.parentElement || stclHeading.closest('.MuiPaper-root')
      const stclEl = within(stclContainer as HTMLElement).getByText('₹5,000')
      await userEvent.click(stclEl)
      const stclInput = await screen.findByDisplayValue('5000')
      await userEvent.clear(stclInput)
      await userEvent.type(stclInput, '6000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith({
        bf_losses: expect.objectContaining({ stcl: 6000 })
      })

      const ltclHeading = screen.getByText(/B\/F Long-Term Capital Loss \(LTCL\)/i)
      const ltclContainer = ltclHeading.parentElement?.parentElement || ltclHeading.closest('.MuiPaper-root')
      const ltclEl = within(ltclContainer as HTMLElement).getByText('₹10,000')
      await userEvent.click(ltclEl)
      const ltclInput = await screen.findByDisplayValue('10000')
      await userEvent.clear(ltclInput)
      await userEvent.type(ltclInput, '12000{Enter}')
      expect(mockMutateOverrides).toHaveBeenCalledWith({
        bf_losses: expect.objectContaining({ ltcl: 12000 })
      })
      await userEvent.click(screen.getByText('Brought Forward Losses'))
    })

    it('shows zero cost warning dropzone and handles broker file upload success and error', async () => {
      const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {})
      vi.mocked(useTaxExpertCapitalGains).mockReturnValue({
        data: {
          bf_losses: { stcl: 0, ltcl: 0 },
          equity_shares: [{ sr: '10', date: '2024-05-01', quantity: null, type: 'STCG', security: null, consideration: 50000, cost: 0, gain: -5000, is_zero_cost: true, is_patched: false }],
          equity_shares_count: 1,
          equity_mf: [],
          equity_mf_count: 0,
          debt_mf: [],
          real_estate: [],
          bonds_gold: [],
          unlisted: [],
          other_mf: [],
        },
        isLoading: false,
        error: null,
      } as any)
      vi.mocked(useTaxExpertSummary).mockReturnValue({
        data: {
          ...mockSummaryNew,
          reconciliation_flags: { duplicates_removed: 0 },
        },
        isLoading: false,
        error: null,
      } as any)

      const { unmount } = renderWithProviders(<TaxCapitalGainsTab />)
      expect(await screen.findByText('Missing Cost Basis Detected')).toBeInTheDocument()

      const brokerFile = new File(['broker pnl xlsx'], 'pnl.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

      await userEvent.upload(fileInput, brokerFile)
      await waitFor(() => {
        expect(apiClient.reconcileBrokerFile).toHaveBeenCalledWith('tax-sid-1', brokerFile)
      })

      // Test error path for upload
      unmount()
      vi.mocked(apiClient.reconcileBrokerFile).mockRejectedValueOnce(new Error('Broker parse error'))
      renderWithProviders(<TaxCapitalGainsTab />)
      const fileInput2 = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(fileInput2, brokerFile)
      await waitFor(() => {
        expect(alertMock).toHaveBeenCalledWith('Failed to process broker file.')
      })
      alertMock.mockRestore()
    })

    it('renders empty table when no transactions exist in a category', async () => {
      vi.mocked(useTaxExpertCapitalGains).mockReturnValue({
        data: {
          bf_losses: { stcl: 0, ltcl: 0 },
          equity_shares: [],
          equity_shares_count: 1,
          equity_mf: [],
          equity_mf_count: 0,
          debt_mf: [],
          real_estate: [],
          bonds_gold: [],
          unlisted: [],
          other_mf: [],
        },
        isLoading: false,
        error: null,
      } as any)

      renderWithProviders(<TaxCapitalGainsTab />)
      expect(await screen.findByText('No transactions found')).toBeInTheDocument()
    })
  })

  // ────────────────────────────────────────────────────────────────
  // 6. TaxITRCompareTab
  // ────────────────────────────────────────────────────────────────
  describe('TaxITRCompareTab', () => {
    it('renders loading spinner when ITR data or summary is loading', () => {
      vi.mocked(useITRData).mockReturnValue({ data: null, isLoading: true, error: null } as any)
      const { container } = renderWithProviders(<TaxITRCompareTab />)
      expect(container.querySelector('.MuiCircularProgress-root')).toBeInTheDocument()
    })

    it('renders upload prompt when no ITR is uploaded and handles upload and error state', async () => {
      vi.mocked(useUploadITR).mockReturnValue({ mutate: mockMutateUploadItr, isPending: false, isError: true } as any)
      renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText(/Compare ITR vs Finance Buddy/i)).toBeInTheDocument()
      expect(screen.getByText('Failed to parse ITR PDF.')).toBeInTheDocument()

      const itrFile = new File(['%PDF-itr'], 'my_itr.pdf', { type: 'application/pdf' })
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(fileInput, itrFile)

      expect(mockMutateUploadItr).toHaveBeenCalledWith(itrFile)
    })

    it('renders upload pending state', () => {
      vi.mocked(useUploadITR).mockReturnValue({ mutate: mockMutateUploadItr, isPending: true, isError: false } as any)
      renderWithProviders(<TaxITRCompareTab />)
      expect(screen.getByText('Parsing ITR Document...')).toBeInTheDocument()
    })

    it('renders reconciliation summary with match indicators when ITR data matches', async () => {
      vi.mocked(useITRData).mockReturnValue({ data: mockItr, isLoading: false, error: null } as any)

      renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
      expect(screen.getByText(/Rahul Sharma/i)).toBeInTheDocument()
      expect(screen.getByText('Gross Total Income')).toBeInTheDocument()
      expect(screen.getAllByText('Net Tax Liability').length).toBeGreaterThan(0)
      expect(screen.getByText('Final Settlement')).toBeInTheDocument()

      // Toggle regime
      const oldRegimeBtn = screen.getByRole('button', { name: /Old Regime/i })
      await userEvent.click(oldRegimeBtn)
      expect(useAppStore.getState().taxRegime).toBe('old')

      // Toggle regime with null
      await userEvent.click(oldRegimeBtn)
    })

    it('renders reconciliation fallback when tax_before_rebate is missing', async () => {
      vi.mocked(useITRData).mockReturnValue({ data: mockItrMissingBeforeRebate, isLoading: false, error: null } as any)

      renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
    })

    it('renders reconciliation with differences, positive diffs, and marginal relief string', async () => {
      vi.mocked(useITRData).mockReturnValue({ data: mockItrDifference, isLoading: false, error: null } as any)

      renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
      expect(screen.getByText(/marginal relief/i)).toBeInTheDocument()
    })

    it('renders negative difference where ITR value is higher than FB value', async () => {
      vi.mocked(useITRData).mockReturnValue({ data: mockItrNegativeDiff, isLoading: false, error: null } as any)

      renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
    })

    it('renders reconciliation with differences, tax due state, and zero refund', async () => {
      useAppStore.setState({ taxRegime: 'old' })
      vi.mocked(useITRData).mockReturnValue({ data: mockItrDue, isLoading: false, error: null } as any)

      const { rerender } = renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
      expect(screen.getByText('Final Settlement')).toBeInTheDocument()

      // Rerender with zero refund
      vi.mocked(useITRData).mockReturnValue({ data: mockItrZero, isLoading: false, error: null } as any)
      rerender(<TaxITRCompareTab />)
      expect(screen.getAllByText('₹0').length).toBeGreaterThan(0)
    })

    it('renders replace ITR upload pending button and handles minimal summary', () => {
      vi.mocked(useTaxExpertSummary).mockReturnValue({ data: mockSummaryMinimal, isLoading: false, error: null } as any)
      vi.mocked(useITRData).mockReturnValue({ data: mockItr, isLoading: false, error: null } as any)
      vi.mocked(useUploadITR).mockReturnValue({ mutate: mockMutateUploadItr, isPending: true, isError: false } as any)

      const { container } = renderWithProviders(<TaxITRCompareTab />)
      expect(container.querySelector('.MuiCircularProgress-root')).toBeInTheDocument()
    })

    it('renders fallback calculation when chapter_via_deductions_total and total_special_rate are undefined', async () => {
      vi.mocked(useTaxExpertSummary).mockReturnValue({
        data: {
          ...mockSummaryNew,
          chapter_via_deductions_total: undefined,
          income_heads: {
            ...mockSummaryNew.income_heads,
            capital_gains: {
              ...mockSummaryNew.income_heads.capital_gains,
              total_special_rate: undefined,
              ltcg_equity: 10000,
              stcg_equity: 5000,
              ltcg_other: 2000,
            },
          },
          surcharge: 5000,
          surcharge_detail: { rate: 0, cg_rate: 0, marginal_relief: 0 },
        },
        isLoading: false,
        error: null,
      } as any)
      vi.mocked(useITRData).mockReturnValue({ data: mockItr, isLoading: false, error: null } as any)

      renderWithProviders(<TaxITRCompareTab />)
      expect(await screen.findByText('ITR Reconciliation Summary')).toBeInTheDocument()
      expect(screen.getByText(/Rate 0% · capital gains capped at 0%/i)).toBeInTheDocument()
    })
  })

  // ────────────────────────────────────────────────────────────────
  // 7. TaxHistoryTab
  // ────────────────────────────────────────────────────────────────
  describe('TaxHistoryTab', () => {
    it('shows loading spinner when fetching history', () => {
      vi.mocked(apiClient.getTaxHistory).mockImplementation(() => new Promise(() => {}))
      const { container } = renderWithProviders(<TaxHistoryTab />)
      expect(container.querySelector('.MuiCircularProgress-root')).toBeInTheDocument()
    })

    it('shows error alert when history fails to load (with detail and without detail)', async () => {
      vi.mocked(apiClient.getTaxHistory).mockRejectedValueOnce({
        response: { data: { detail: 'Database unreachable' } },
      })

      const { unmount } = renderWithProviders(<TaxHistoryTab />)
      expect(await screen.findByText('Database unreachable')).toBeInTheDocument()

      unmount()
      vi.mocked(apiClient.getTaxHistory).mockRejectedValueOnce(new Error('Network error'))
      renderWithProviders(<TaxHistoryTab />)
      expect(await screen.findByText('Could not load your saved filings.')).toBeInTheDocument()
    })

    it('shows empty state when no sessions exist or data is null', async () => {
      vi.mocked(apiClient.getTaxHistory).mockResolvedValueOnce({ sessions: [] } as any)
      const { unmount } = renderWithProviders(<TaxHistoryTab />)
      expect(await screen.findByText('No saved filings yet')).toBeInTheDocument()

      unmount()
      vi.mocked(apiClient.getTaxHistory).mockResolvedValueOnce(null as any)
      renderWithProviders(<TaxHistoryTab />)
      expect(await screen.findByText('No saved filings yet')).toBeInTheDocument()
    })

    it('renders single session with singular filing text', async () => {
      vi.mocked(apiClient.getTaxHistory).mockResolvedValueOnce({
        sessions: [
          {
            session_id: 'tax-single',
            fy: '',
            name: '',
            gross_salary: 0,
            created_at: null,
          },
        ],
      } as any)

      renderWithProviders(<TaxHistoryTab />)
      expect(await screen.findByText('1 saved filing. These are kept until you delete them.')).toBeInTheDocument()
      expect(screen.getByText('FY —')).toBeInTheDocument()
      expect(screen.getByText(/Unnamed · uploaded Unknown date/i)).toBeInTheDocument()
    })

    it('lists history sessions, restores session, and confirms deletion with error handling', async () => {
      vi.mocked(apiClient.getTaxHistory).mockResolvedValue({
        sessions: [
          {
            session_id: 'tax-sid-1',
            fy: '2024-25',
            name: 'Rahul Sharma',
            gross_salary: 1800000,
            created_at: '2025-01-15T10:00:00.000Z',
          },
          {
            session_id: 'tax-sid-2',
            fy: '2023-24',
            name: 'Priya Nair',
            gross_salary: 1400000,
            created_at: 'invalid-date',
          },
        ],
      } as any)

      renderWithProviders(<TaxHistoryTab />)
      expect(await screen.findByText('2 saved filings. These are kept until you delete them.')).toBeInTheDocument()
      expect(screen.getByText('FY 2024-25')).toBeInTheDocument()
      expect(screen.getByText('ACTIVE')).toBeInTheDocument()
      expect(screen.getByText('FY 2023-24')).toBeInTheDocument()
      expect(screen.getByText(/Unknown date/i)).toBeInTheDocument()

      // Restore second session
      await userEvent.click(screen.getByRole('button', { name: /^Restore$/i }))
      expect(useAppStore.getState().taxSessionId).toBe('tax-sid-2')

      // Delete first session (shows error with response detail first)
      vi.mocked(apiClient.deleteTaxSession).mockRejectedValueOnce({
        response: { data: { detail: 'Delete operation failed on remote server' } },
      })

      const deleteBtns = screen.getAllByRole('button', { name: /^Delete$/i })
      await userEvent.click(deleteBtns[0])

      expect(await screen.findByText('Delete this filing?')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /^Delete permanently$/i }))

      expect(await screen.findByText('Delete operation failed on remote server')).toBeInTheDocument()

      // Open and close via backdrop click (triggers Dialog onClose callback)
      await userEvent.click(deleteBtns[0])
      const backdrop = document.querySelector('.MuiBackdrop-root')
      if (backdrop) fireEvent.click(backdrop)
      await waitFor(() => {
        expect(screen.queryByText('Delete this filing?')).not.toBeInTheDocument()
      })

      // Test generic error fallback on delete
      vi.mocked(apiClient.deleteTaxSession).mockRejectedValueOnce(new Error('Network error'))
      await userEvent.click(deleteBtns[0])
      await userEvent.click(screen.getByRole('button', { name: /^Delete permanently$/i }))
      expect(await screen.findByText('Failed to delete filing session.')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /^Cancel$/i }))

      // Open delete dialog again and confirm delete successfully on active session
      useAppStore.setState({ taxSessionId: 'tax-sid-1' })
      vi.mocked(apiClient.deleteTaxSession).mockResolvedValueOnce({ status: 'deleted' } as any)
      await userEvent.click(deleteBtns[0])
      await userEvent.click(screen.getByRole('button', { name: /^Delete permanently$/i }))

      await waitFor(() => {
        expect(apiClient.deleteTaxSession).toHaveBeenCalledWith('tax-sid-1')
      })
      expect(useAppStore.getState().taxSessionId).toBeNull()
    })
  })
})
