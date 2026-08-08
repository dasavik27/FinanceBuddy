import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import FundDetailDrawer from './FundDetailDrawer'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getFundInsights: vi.fn(),
  },
}))

describe('FundDetailDrawer', () => {
  const mockFund = {
    Fund: 'Mirae Asset Large Cap Fund',
    Category: 'Equity Scheme - Large Cap Fund',
    'Cap Type': 'Large Cap',
    ISIN: 'INF209K01165',
    'Market Value': 450000,
    Invested: 350000,
    Gain: 100000,
    'Gain%': 28.57,
    'Weight%': 22.5,
    Units: 5000,
    NAV: 90.0,
    TER: '0.55',
    TER_fallback: false,
    'Folio No': '12345678/90',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-drawer', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getFundInsights).mockResolvedValue({
      aum: '35,000 Cr',
      expense_ratio: '0.55%',
      risk: 'Very High',
      sectors: [{ sector: 'Financials', value: 35 }],
      holdings: [{ name: 'HDFC Bank', pct: 9.5 }],
      source: 'Official AMFI Disclosure',
    } as any)
  })

  it('renders fund metadata, metrics, sectors and closes on close button click', async () => {
    const onClose = vi.fn()
    renderWithProviders(<FundDetailDrawer fund={mockFund} onClose={onClose} />)

    expect(screen.getByText('Mirae Asset Large Cap Fund')).toBeInTheDocument()
    expect(screen.getByText('Equity Scheme - Large Cap Fund')).toBeInTheDocument()
    expect(screen.getByText('₹4,50,000')).toBeInTheDocument()
    expect(screen.getByText('₹3,50,000')).toBeInTheDocument()
    expect(await screen.findByText('35,000 Cr')).toBeInTheDocument()
    expect(screen.getByText('0.55%')).toBeInTheDocument()
    expect(screen.getByText('VERY HIGH')).toBeInTheDocument()
    expect(screen.getByText('TAX INTELLIGENCE')).toBeInTheDocument()

    const closeBtn = screen.getByTestId('CloseIcon').closest('button')
    if (closeBtn) {
      await userEvent.click(closeBtn)
      expect(onClose).toHaveBeenCalled()
    }
  })

  it('renders tax profile for debt fund category', () => {
    const debtFund = {
      ...mockFund,
      Fund: 'HDFC Short Term Debt Fund',
      Category: 'Debt Scheme - Short Duration Fund',
      'Cap Type': 'Debt',
    }
    renderWithProviders(<FundDetailDrawer fund={debtFund} onClose={vi.fn()} />)

    expect(screen.getByText('HDFC Short Term Debt Fund')).toBeInTheDocument()
    expect(screen.getByText('Debt Scheme - Short Duration Fund')).toBeInTheDocument()
    expect(screen.getByText('TAX INTELLIGENCE')).toBeInTheDocument()
    expect(screen.getByText(/Post Apr 2023: all debt mutual fund gains/i)).toBeInTheDocument()
  })

  it('renders nothing meaningful when fund is null', () => {
    renderWithProviders(<FundDetailDrawer fund={null} onClose={vi.fn()} />)
    expect(screen.queryByText('TAX INTELLIGENCE')).not.toBeInTheDocument()
  })

  it('shows sector/holding insights and source attribution', async () => {
    renderWithProviders(<FundDetailDrawer fund={mockFund} onClose={vi.fn()} />)
    expect(await screen.findByText('SECTOR ALLOCATION')).toBeInTheDocument()
    expect(screen.getByText('TOP INSTRUMENTS')).toBeInTheDocument()
    expect(screen.getByText('HDFC BANK')).toBeInTheDocument()
    expect(screen.getByText(/Official AMFI Disclosure/i)).toBeInTheDocument()
  })

  it('handles missing insights gracefully', async () => {
    vi.mocked(apiClient.getFundInsights).mockRejectedValueOnce(new Error('insights down'))
    renderWithProviders(<FundDetailDrawer fund={mockFund} onClose={vi.fn()} />)
    expect(screen.getByText('Mirae Asset Large Cap Fund')).toBeInTheDocument()
    expect(screen.getByText('TAX INTELLIGENCE')).toBeInTheDocument()
  })

  it('renders hybrid/other category tax intelligence', () => {
    const hybrid = {
      ...mockFund,
      Fund: 'HDFC Balanced Advantage',
      Category: 'Hybrid Scheme - Balanced Advantage',
      'Cap Type': 'Hybrid',
    }
    renderWithProviders(<FundDetailDrawer fund={hybrid} onClose={vi.fn()} />)
    expect(screen.getByText('HDFC Balanced Advantage')).toBeInTheDocument()
    expect(screen.getByText('TAX INTELLIGENCE')).toBeInTheDocument()
  })
})
