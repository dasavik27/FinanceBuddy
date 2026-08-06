import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import TaxStrategyTab from './TaxStrategyTab'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('./tax/TaxOverviewTab', () => ({
  default: () => <div><h1>Tax Summary</h1><p>Side-by-side comparison</p></div>,
}))
vi.mock('./tax/TaxIncomeTab', () => ({
  default: () => <div><h1>Income Sources</h1><p>Core Income</p></div>,
}))
vi.mock('./tax/TaxSavingsTab', () => ({
  default: () => <div><h1>Tax Savings & TDS</h1><p>TDS & Taxes Paid</p></div>,
}))
vi.mock('./tax/TaxCapitalGainsTab', () => ({
  default: () => <div><h1>Capital Gains</h1><p>INFY</p></div>,
}))
vi.mock('./tax/TaxITRCompareTab', () => ({
  default: () => <div><h1>Compare ITR vs Finance Buddy</h1></div>,
}))
vi.mock('./tax/TaxHistoryTab', () => ({
  default: () => <div><p>No saved filings yet</p></div>,
}))

describe('TaxStrategyTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ taxSessionId: 'tax-sid-1', activeModule: 'tax_expert', taxRegime: 'new', userId: 'u1' })
  })

  it('renders all tax strategy tabs', () => {
    renderWithProviders(<TaxStrategyTab />)

    expect(screen.getByRole('tab', { name: /Tax Summary/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Income Sources/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Tax Savings/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Capital Gains/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Compare ITR/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Filing History/i })).toBeInTheDocument()
  })

  it('switches between tabs and loads lazy content', async () => {
    renderWithProviders(<TaxStrategyTab />)

    expect(await screen.findByRole('heading', { name: 'Tax Summary' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Income Sources/i }))
    expect(await screen.findByRole('heading', { name: 'Income Sources' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Tax Savings/i }))
    expect(await screen.findByRole('heading', { name: 'Tax Savings & TDS' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Capital Gains/i }))
    expect(await screen.findByRole('heading', { name: 'Capital Gains' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Compare ITR/i }))
    expect(await screen.findByText(/Compare ITR vs Finance Buddy/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /Filing History/i }))
    expect(await screen.findByText(/No saved filings yet/i)).toBeInTheDocument()
  })
})
