import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import HoldingsTab from './HoldingsTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getHoldings: vi.fn(),
    getFundInsights: vi.fn(),
    getTransactions: vi.fn(),
  },
}))

describe('HoldingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-holdings', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        {
          Fund: 'HDFC Mid-Cap Opportunities Fund',
          Category: 'Equity',
          'Cap Type': 'Mid Cap',
          'Market Value': 500000,
          Gain: 120000,
          'Gain%': 31.5,
          'Weight%': 35.0,
          'Day Chg.': 2500,
          TER: '0.85',
          TER_fallback: false,
          ISIN: 'INF179K01BE2',
        },
        {
          Fund: 'Parag Parikh Flexi Cap Fund',
          Category: 'Equity',
          'Cap Type': 'Flexi Cap',
          'Market Value': 300000,
          Gain: 45000,
          'Gain%': 17.6,
          'Weight%': 21.0,
          'Day Chg.': -500,
          TER: '0.65',
          TER_fallback: false,
          ISIN: 'INF879O01019',
        },
      ],
      cap_types: ['Mid Cap', 'Flexi Cap', 'Large Cap'],
    } as any)
    vi.mocked(apiClient.getFundInsights).mockResolvedValue({} as any)
    vi.mocked(apiClient.getTransactions).mockResolvedValue([] as any)
  })

  it('renders search input, concentration risk warning, and holding cards', async () => {
    renderWithProviders(<HoldingsTab />)

    expect(screen.getByRole('heading', { name: 'Holdings Explorer' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Search Asset Ledger/i)).toBeInTheDocument()

    // Concentration alert for >25% weight
    expect(await screen.findByText(/CONCENTRATION RISK AUDIT/i)).toBeInTheDocument()
    expect(screen.getByText('HDFC Mid-Cap Opportunities Fund')).toBeInTheDocument()
    expect(screen.getByText('Parag Parikh Flexi Cap Fund')).toBeInTheDocument()

    // Click card to open drawer
    await userEvent.click(screen.getByText('HDFC Mid-Cap Opportunities Fund'))
    expect(screen.getByText(/MID CAP/i)).toBeInTheDocument()
  })
})
