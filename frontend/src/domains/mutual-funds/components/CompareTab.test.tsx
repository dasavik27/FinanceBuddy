import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import CompareTab from './CompareTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getHoldings: vi.fn(),
    getPerformance: vi.fn(),
    getBenchmarkHistory: vi.fn(),
    getRollingReturns: vi.fn(),
    searchTicker: vi.fn(),
  },
}))

describe('CompareTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      mfSessionId: 'sid-compare',
      activeModule: 'mutual_funds',
      compareFunds: { 'sid-compare': ['Quant Small Cap Fund', 'Parag Parikh Flexi Cap Fund'] },
    })
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        { Fund: 'Quant Small Cap Fund', ISIN: 'INF966L01AA3', 'Market Value': 400000 },
        { Fund: 'Parag Parikh Flexi Cap Fund', ISIN: 'INF879O01019', 'Market Value': 600000 },
      ],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      funds: [
        {
          fund: 'Quant Small Cap Fund',
          isin: 'INF966L01AA3',
          alpha: 12.5,
          sharpe: 1.8,
          sortino: 2.1,
          beta: 1.15,
          vol: 16.5,
          consistency: 9,
          fund_xi: 32.4,
          verdict: 'Strong',
          er: 0.75,
        },
        {
          fund: 'Parag Parikh Flexi Cap Fund',
          isin: 'INF879O01019',
          alpha: 6.2,
          sharpe: 1.4,
          sortino: 1.7,
          beta: 0.85,
          vol: 11.2,
          consistency: 8,
          fund_xi: 21.0,
          verdict: 'Strong',
          er: 0.65,
        },
      ],
      benchmark_stats: { alpha: 0, beta: 1.0, sharpe: 1.1, sortino: 1.3, volatility: 13.0, max_drawdown: -15.0 },
    } as any)
    vi.mocked(apiClient.getBenchmarkHistory).mockResolvedValue({
      dates: ['2023-01-01', '2023-06-01', '2023-12-31'],
      values: [100, 115, 130],
    } as any)
  })

  it('renders section header, portfolio assets autocomplete, and matrix tabs', async () => {
    renderWithProviders(<CompareTab />)

    expect(screen.getByRole('heading', { name: 'Compare Funds' })).toBeInTheDocument()
    expect(screen.getByText('PORTFOLIO ASSETS')).toBeInTheDocument()
    expect(screen.getByText('MARKET COMPARATOR & PEERS')).toBeInTheDocument()

    // Loaded table
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()
    expect(screen.getByText('Matrix Overview')).toBeInTheDocument()
    expect(screen.getByText('Deep Technicals')).toBeInTheDocument()
    expect(screen.getByText('Trend Analysis')).toBeInTheDocument()
  })

  it('handles error state gracefully', async () => {
    vi.mocked(apiClient.getPerformance).mockRejectedValue(new Error('Fetch failed'))
    renderWithProviders(<CompareTab />)

    expect(await screen.findByText('Data Pipeline Interrupted')).toBeInTheDocument()
  })
})
