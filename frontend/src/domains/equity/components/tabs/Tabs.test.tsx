import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../../test/utils'
import OverviewTab from './OverviewTab'
import HoldingsTab from './HoldingsTab'
import PLTab from './PLTab'
import SectorTab from './SectorTab'
import PerformanceTab from './PerformanceTab'
import InsightsTab from './InsightsTab'
import { apiClient } from '../../../../shared/api/client'
import { useAppStore } from '../../../../shared/store/appStore'

vi.mock('../../../../shared/api/client', () => ({
  apiClient: {
    getEquitySummary: vi.fn(),
    getEquityAllocation: vi.fn(),
    getEquityHoldings: vi.fn(),
    getEquityPnl: vi.fn(),
    getEquityPerformance: vi.fn(),
    getEquityInsights: vi.fn(),
    syncEquity: vi.fn(),
  },
}))

vi.mock('recharts', () => {
  const { createElement, useEffect } = require('react')
  const Passthrough = ({ children }: any) => createElement('div', { 'data-testid': 'chart' }, children)
  const Invoke = (props: Record<string, unknown>) => {
    useEffect(() => {
      const tick = props.tickFormatter as ((v: any) => unknown) | undefined
      if (typeof tick === 'function') {
        tick('2026-01-15')
        tick('not-a-date')
        tick(150000)
      }
      const formatter = props.formatter as ((v: any, name?: string) => unknown) | undefined
      if (typeof formatter === 'function') {
        formatter(100000, 'portfolio')
        formatter(100000, 'benchmark')
      }
    }, [])
    return createElement('div', { 'data-testid': 'axis-or-tip' })
  }
  return {
    ResponsiveContainer: Passthrough,
    PieChart: Passthrough,
    Pie: ({ children }: any) => createElement('div', null, children),
    Cell: () => createElement('div'),
    BarChart: Passthrough,
    Bar: () => createElement('div'),
    AreaChart: Passthrough,
    Area: () => createElement('div'),
    XAxis: Invoke,
    YAxis: Invoke,
    CartesianGrid: () => createElement('div'),
    Tooltip: Invoke,
  }
})

describe('Equity Tabs Test Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ equitySessionId: 'eq-sess-test' })
  })

  describe('OverviewTab', () => {
    it('renders overview metrics and sector breakdown', async () => {
      vi.mocked(apiClient.getEquitySummary).mockResolvedValue({
        total_value: 1500000,
        total_invested: 1200000,
        unrealized_pnl: 300000,
        pnl_pct: 25.0,
        day_change: 15000,
        day_change_pct: 1.0,
      } as any)
      vi.mocked(apiClient.getEquityAllocation).mockResolvedValue({
        by_sector: [{ label: 'Technology', value: 600000, pct: 40.0 }],
      } as any)

      renderWithProviders(<OverviewTab />)

      expect(await screen.findByText('Executive Summary')).toBeInTheDocument()
      expect(screen.getByText('Total Market Value')).toBeInTheDocument()
      expect(await screen.findByText('₹15,00,000')).toBeInTheDocument()
      expect(await screen.findByText('Technology')).toBeInTheDocument()
    })

    it('shows overview error state', async () => {
      vi.mocked(apiClient.getEquitySummary).mockRejectedValueOnce(new Error('overview boom'))
      vi.mocked(apiClient.getEquityAllocation).mockResolvedValueOnce({ by_sector: [] } as any)
      renderWithProviders(<OverviewTab />)
      expect(await screen.findByText(/Could not load overview/i)).toBeInTheDocument()
    })

    it('shows empty sectors, negative PnL, and sync success/failure', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getEquitySummary).mockResolvedValue({
        total_value: 100,
        total_invested: 200,
        unrealized_pnl: -50,
        pnl_pct: -25,
        day_change: 0,
      } as any)
      vi.mocked(apiClient.getEquityAllocation).mockResolvedValue({ by_sector: [] } as any)
      vi.mocked(apiClient.syncEquity).mockResolvedValue({} as any)
      renderWithProviders(<OverviewTab />)
      expect(await screen.findByText('No sector data available.')).toBeInTheDocument()
      expect(screen.getByText(/Live prices unavailable/i)).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /Live Sync LTP/i }))
      await waitFor(() => expect(apiClient.syncEquity).toHaveBeenCalledWith('eq-sess-test'))

      vi.mocked(apiClient.syncEquity).mockRejectedValueOnce(new Error('sync fail'))
      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      await user.click(screen.getByRole('button', { name: /Live Sync LTP/i }))
      await waitFor(() => expect(errSpy).toHaveBeenCalled())
      errSpy.mockRestore()
    })

    it('renders negative day change when prices are available', async () => {
      vi.mocked(apiClient.getEquitySummary).mockResolvedValue({
        total_value: 1,
        total_invested: 1,
        unrealized_pnl: 0,
        day_change: -10,
        pnl_pct: 0,
      } as any)
      vi.mocked(apiClient.getEquityAllocation).mockResolvedValue({
        by_sector: [{ label: 'Energy', value: 1, pct: 100 }],
      } as any)
      renderWithProviders(<OverviewTab />)
      expect(await screen.findByText('Executive Summary')).toBeInTheDocument()
      expect(await screen.findByText('1D Change')).toBeInTheDocument()
      expect(await screen.findByText('Energy')).toBeInTheDocument()
      expect(screen.queryByText(/Live prices unavailable/i)).not.toBeInTheDocument()
    })
  })

  describe('HoldingsTab', () => {
    it('renders holdings rows with symbol, qty, avg price, ltp, current value', async () => {
      vi.mocked(apiClient.getEquityHoldings).mockResolvedValue({
        holdings: [
          {
            symbol: 'RELIANCE',
            sector: 'Energy',
            quantity: 50,
            avg_price: 2500,
            ltp: 2900,
            current_value: 145000,
            unrealized_pnl: 20000,
            pnl_pct: 16.0,
            weight_pct: 15.0,
          },
        ],
        total: 145000,
      } as any)

      renderWithProviders(<HoldingsTab />)

      expect(await screen.findByText('RELIANCE')).toBeInTheDocument()
      expect(screen.getByText('Energy')).toBeInTheDocument()
      expect(screen.getByText('50.00')).toBeInTheDocument()
      expect(screen.getByText('₹2,900')).toBeInTheDocument()
      expect(screen.getByText('₹1,45,000')).toBeInTheDocument()
    })

    it('covers empty, error, sort toggles, and weight fallback', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getEquityHoldings).mockRejectedValueOnce(new Error('holdings fail'))
      renderWithProviders(<HoldingsTab />)
      expect(await screen.findByText(/Could not load holdings/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityHoldings).mockResolvedValueOnce({ holdings: [], total: 0 } as any)
      renderWithProviders(<HoldingsTab />)
      expect(await screen.findByText(/No holdings in this portfolio/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityHoldings).mockResolvedValue({
        holdings: [
          {
            symbol: 'INFY',
            quantity: 10,
            avg_price: 1000,
            ltp: 900,
            current_value: 9000,
            unrealized_pnl: -1000,
            pnl_pct: -10,
            // force client-side weight fallback
            weight_pct: undefined,
          },
          {
            symbol: 'TCS',
            sector: 'IT',
            quantity: 5,
            avg_price: 3000,
            ltp: 3500,
            current_value: 17500,
            unrealized_pnl: 2500,
            pnl_pct: 16.6,
            weight_pct: 66,
          },
        ],
        total: 26500,
      } as any)

      renderWithProviders(<HoldingsTab />)
      expect(await screen.findByText('INFY')).toBeInTheDocument()
      expect(screen.getAllByText(/weight/i).length).toBeGreaterThan(0)

      await user.click(screen.getByText('Symbol'))
      await waitFor(() => expect(apiClient.getEquityHoldings).toHaveBeenCalled())
      await user.click(screen.getByText('Symbol'))
      await user.click(screen.getByText('P&L'))
    })
  })

  describe('PLTab', () => {
    it('renders unrealized P&L summary and gainers/losers', async () => {
      vi.mocked(apiClient.getEquityPnl).mockResolvedValue({
        unrealized_pnl: 45000,
        total_gainers: 8,
        total_losers: 2,
        gainers_value: 60000,
        losers_value: 15000,
        top_gainers: [{ symbol: 'TCS', unrealized_pnl: 25000, pnl_pct: 12.5 }],
        top_losers: [{ symbol: 'WIPRO', unrealized_pnl: -5000, pnl_pct: -4.0 }],
        has_tradebook: false,
      } as any)

      renderWithProviders(<PLTab />)

      expect(await screen.findByText('Unrealized P&L Summary')).toBeInTheDocument()
      expect(screen.getByText(/Total Gainers \(8\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Total Losers \(2\)/i)).toBeInTheDocument()
      expect(screen.getByText('Top Gainers')).toBeInTheDocument()
      expect(screen.getByText('TCS')).toBeInTheDocument()
      expect(screen.getByText('Top Losers')).toBeInTheDocument()
      expect(screen.getByText('WIPRO')).toBeInTheDocument()
    })

    it('covers error, empty movers, tradebook tax years, and unmatched sells', async () => {
      vi.mocked(apiClient.getEquityPnl).mockRejectedValueOnce(new Error('pnl fail'))
      renderWithProviders(<PLTab />)
      expect(await screen.findByText(/Could not load P&L/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityPnl).mockResolvedValueOnce({
        unrealized_pnl: -1200,
        total_gainers: 0,
        total_losers: 1,
        gainers_value: 0,
        losers_value: 1200,
        top_gainers: [],
        top_losers: [],
        has_tradebook: true,
        financial_year: '2025-26',
        realised_by_year: {
          '2025-26': { stcg: 1000, ltcg: 2000 },
          '2024-25': { stcg: 500, ltcg: 800 },
          '2023-24': { stcg: 100, ltcg: 50 },
        },
        stcg_estimate: 1000,
        stcg_tax_estimate: 200,
        ltcg_estimate: 2000,
        ltcg_tax_estimate: 100,
        unmatched_sell_qty: 12,
      } as any)

      renderWithProviders(<PLTab />)
      expect(await screen.findByText(/Realised in FY 2025-26/i)).toBeInTheDocument()
      expect(screen.getByText(/Earlier years/i)).toBeInTheDocument()
      expect(screen.getByText(/shares sold without a matching purchase/i)).toBeInTheDocument()
      expect(screen.getAllByText(/No data available/i).length).toBeGreaterThan(0)
    })
  })

  describe('SectorTab', () => {
    it('renders sector and industry allocations', async () => {
      vi.mocked(apiClient.getEquityAllocation).mockResolvedValue({
        by_sector: [
          { label: 'Technology', value: 500000, pct: 50.0 },
          { label: 'Financials', value: 300000, pct: 30.0 },
        ],
        by_industry: [
          { industry: 'IT Services', value: 500000 },
          { industry: 'Private Banks', value: 300000 },
        ],
      } as any)

      renderWithProviders(<SectorTab />)

      expect(await screen.findByText('Sector Allocation')).toBeInTheDocument()
      expect(screen.getByText('Top Industries')).toBeInTheDocument()
      expect(screen.getByText('Technology')).toBeInTheDocument()
      expect(screen.getByText('Financials')).toBeInTheDocument()
    })

    it('covers error and empty allocation states', async () => {
      vi.mocked(apiClient.getEquityAllocation).mockRejectedValueOnce(new Error('alloc fail'))
      renderWithProviders(<SectorTab />)
      expect(await screen.findByText(/Could not load sector allocation/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityAllocation).mockResolvedValueOnce({ by_sector: [], by_industry: [] } as any)
      renderWithProviders(<SectorTab />)
      expect(await screen.findByText(/No allocation data for this portfolio/i)).toBeInTheDocument()
    })
  })

  describe('PerformanceTab', () => {
    it('renders performance benchmark comparison chart and period selectors', async () => {
      vi.mocked(apiClient.getEquityPerformance).mockResolvedValue({
        dates: ['2026-01-01', '2026-02-01', '2026-03-01'],
        portfolio: [100, 105, 110],
        benchmark: [100, 102, 107],
        priced_symbols: 10,
        total_symbols: 10,
      } as any)

      renderWithProviders(<PerformanceTab />)

      expect(await screen.findByText('Portfolio Performance')).toBeInTheDocument()
      expect(screen.getByText(/Mark-to-market comparison against Nifty 50/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '1Y' })).toBeInTheDocument()
    })

    it('covers error, empty history, partial pricing, and period changes', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getEquityPerformance).mockRejectedValueOnce(new Error('perf fail'))
      renderWithProviders(<PerformanceTab />)
      expect(await screen.findByText(/Could not load performance/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityPerformance).mockResolvedValue({
        dates: [],
        portfolio: [],
        benchmark: [],
        priced_symbols: 3,
        total_symbols: 10,
      } as any)
      renderWithProviders(<PerformanceTab />)
      expect(await screen.findByText(/Not enough historical data/i)).toBeInTheDocument()
      expect(screen.getByText(/3 of 10 holdings have price history/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityPerformance).mockResolvedValue({
        dates: ['2026-01-01', 'bad-date'],
        portfolio: [100, null],
        benchmark: [100],
        priced_symbols: 10,
        total_symbols: 10,
      } as any)
      renderWithProviders(<PerformanceTab />)
      expect(await screen.findByText('Portfolio Performance')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: '3M' }))
      await waitFor(() =>
        expect(apiClient.getEquityPerformance).toHaveBeenCalledWith(
          'eq-sess-test',
          expect.objectContaining({ period: '3M' }),
        ),
      )
    })
  })

  describe('InsightsTab', () => {
    it('renders diversification score and concentration risks', async () => {
      vi.mocked(apiClient.getEquityInsights).mockResolvedValue({
        diversification_score: 85,
        concentrated_positions: [
          { symbol: 'HDFCBANK', sector: 'Financials', weight_pct: 18.5 },
        ],
        tax_loss_harvest: [
          { symbol: 'TATAMOTORS', unrealized_loss: 12000, pnl_pct: -8.5 },
        ],
      } as any)

      renderWithProviders(<InsightsTab />)

      expect(await screen.findByText('Portfolio Diversification Score')).toBeInTheDocument()
      expect(screen.getByText('85')).toBeInTheDocument()
      expect(screen.getByText('Concentration Risk')).toBeInTheDocument()
      expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
      expect(screen.getByText('18.5% Weight')).toBeInTheDocument()
    })

    it('covers error, mid/low scores, and empty concentration/harvest states', async () => {
      vi.mocked(apiClient.getEquityInsights).mockRejectedValueOnce(new Error('insights fail'))
      renderWithProviders(<InsightsTab />)
      expect(await screen.findByText(/Could not load insights/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityInsights).mockResolvedValueOnce({
        diversification_score: 55,
        concentrated_positions: [],
        tax_loss_harvest: [],
      } as any)
      renderWithProviders(<InsightsTab />)
      expect(await screen.findByText('55')).toBeInTheDocument()
      expect(screen.getByText(/well diversified across stocks/i)).toBeInTheDocument()
      expect(screen.getByText(/No significant losses to harvest/i)).toBeInTheDocument()

      vi.mocked(apiClient.getEquityInsights).mockResolvedValueOnce({
        diversification_score: 20,
        concentrated_positions: [{ symbol: 'A', sector: 'X', weight_pct: 40 }],
        tax_loss_harvest: [{ symbol: 'B', unrealized_loss: 1, pnl_pct: -1 }],
      } as any)
      renderWithProviders(<InsightsTab />)
      expect(await screen.findByText('20')).toBeInTheDocument()
      expect(screen.getByText('A')).toBeInTheDocument()
    })
  })
})
