import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import EquityDashboard from './EquityDashboard'
import IndianStocksDashboard from './IndianStocksDashboard'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getEquitySummary: vi.fn(),
    getEquityAllocation: vi.fn(),
    getEquityHoldings: vi.fn(),
    getEquityPnl: vi.fn(),
    getEquityPerformance: vi.fn(),
    getEquityInsights: vi.fn(),
    getEquityHistory: vi.fn(),
    getMarketIndices: vi.fn(),
  },
}))

describe('EquityDashboard & IndianStocksDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      equitySessionId: 'eq-sess-1',
      userId: 'test-user',
      activeModule: 'indian_stocks',
    })
    vi.mocked(apiClient.getEquityHistory).mockResolvedValue({ history: [] } as any)
    vi.mocked(apiClient.getMarketIndices).mockResolvedValue({ indices: [] } as any)
    vi.mocked(apiClient.getEquitySummary).mockResolvedValue({
      total_portfolio_value: 1000000,
      total_invested: 800000,
      total_unrealized_pnl: 200000,
      total_unrealized_pnl_pct: 25.0,
      total_realized_pnl: 50000,
      total_pnl: 250000,
      total_pnl_pct: 31.25,
      day_change: 12000,
      day_change_pct: 1.2,
      holdings_count: 10,
    } as any)
    vi.mocked(apiClient.getEquityAllocation).mockResolvedValue({
      by_sector: [{ sector: 'Technology', value: 400000, percentage: 40.0 }],
      by_market_cap: [{ market_cap: 'Large Cap', value: 600000, percentage: 60.0 }],
    } as any)
  })

  it('renders EquityDashboard with tabs and default overview tab', async () => {
    renderWithProviders(<EquityDashboard hasSession={true} />)

    expect(screen.getByRole('heading', { name: 'Equity Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Holdings' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'P&L Analysis' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Sector Allocation' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Performance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Stock Analyzer' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Insights' })).toBeInTheDocument()

    // Lazy overview content
    expect(await screen.findByText('Executive Summary')).toBeInTheDocument()
    expect(screen.getByText('Total Market Value')).toBeInTheDocument()
  })

  it('renders IndianStocksDashboard and sets activeModule', () => {
    renderWithProviders(<IndianStocksDashboard />)
    expect(useAppStore.getState().activeModule).toBe('indian_stocks')
    expect(screen.getByRole('heading', { name: 'Equity Dashboard' })).toBeInTheDocument()
  })

  it('renders upload panel when hasSession is false', async () => {
    renderWithProviders(<EquityDashboard hasSession={false} />)
    expect(await screen.findByText('Connect Your Broker')).toBeInTheDocument()
  })
})
