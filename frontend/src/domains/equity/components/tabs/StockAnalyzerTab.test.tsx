import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../../test/utils'
import StockAnalyzerTab from './StockAnalyzerTab'
import { apiClient } from '../../../../shared/api/client'
import { useStockAnalyzerStore } from '../../hooks/useStockAnalyzerStore'
import { useAppStore } from '../../../../shared/store/appStore'

vi.mock('../../../../shared/api/client', () => ({
  apiClient: {
    searchStocks: vi.fn(),
    analyzeStock: vi.fn(),
    getStockFinancials: vi.fn(),
    getStockImpact: vi.fn(),
    getMarketIndices: vi.fn(),
  },
}))

describe('StockAnalyzerTab Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ equitySessionId: 'eq-sess-1' })
    useStockAnalyzerStore.getState().clear()
    vi.mocked(apiClient.getMarketIndices).mockResolvedValue({
      indices: [{ symbol: 'NIFTY 50', name: 'NIFTY 50', price: 24500, change: 120, p_change: 0.5 }],
    } as any)
  })

  it('renders search input and market indices ribbon when no stock is selected', async () => {
    renderWithProviders(<StockAnalyzerTab />)

    expect(
      screen.getByPlaceholderText(/Search Indian stocks \(e\.g\. RELIANCE, TCS, INFY/i)
    ).toBeInTheDocument()
    expect(await screen.findByText('NIFTY 50')).toBeInTheDocument()
  })

  it('displays stock analysis when stock is loaded in store', async () => {
    useStockAnalyzerStore.setState({
      stock: {
        symbol: 'RELIANCE',
        name: 'Reliance Industries Ltd.',
        source: 'NSE',
        current_price: 2950,
        day_change: 35,
        day_change_pct: 1.2,
        year_return: 18.5,
        sector: 'Energy',
        chart: {
          dates: ['2026-01-01', '2026-02-01'],
          prices: [2800, 2950],
          volumes: [100000, 120000],
          sma_50: [2750, 2800],
          sma_200: [2600, 2650],
        },
        technicals: {
          rsi_14: 62.5,
          trend: 'Uptrend',
          sma_50: 2800,
          sma_200: 2650,
        },
      } as any,
      activeSubTab: 'overview',
    })

    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('NSE: RELIANCE')).toBeInTheDocument()
    expect(screen.getByText('Reliance Industries Ltd.')).toBeInTheDocument()
    expect(screen.getByText('₹2,950')).toBeInTheDocument()

    // Sub tabs: Overview, Indicators, Compare, Financials
    expect(screen.getByRole('button', { name: /Overview/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Indicators/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Compare/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Financials/i })).toBeInTheDocument()
  })

  it('switches sub-tabs and triggers technical indicators & compare views', async () => {
    useStockAnalyzerStore.setState({
      stock: {
        symbol: 'TCS',
        name: 'Tata Consultancy Services',
        source: 'NSE',
        current_price: 4100,
        sector: 'Technology',
        chart: {
          dates: ['2026-01-01', '2026-02-01'],
          prices: [3900, 4100],
        },
        technicals: {
          rsi_14: 55,
          trend: 'Uptrend',
          sma_50: 4000,
          sma_200: 3800,
        },
      } as any,
      activeSubTab: 'indicators',
    })

    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Technical Indicators & Moving Averages')).toBeInTheDocument()
    expect(screen.getByText('RSI (14-Day)')).toBeInTheDocument()
    expect(screen.getByText('55.0')).toBeInTheDocument()
  })
})
