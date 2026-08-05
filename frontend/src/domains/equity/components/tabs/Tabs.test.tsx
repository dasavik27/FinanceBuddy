import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
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
        unrealized_pnl_pct: 25.0,
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
            unrealized_pnl_pct: 16.0,
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
  })

  describe('InsightsTab', () => {
    it('renders diversification score and concentration risks', async () => {
      vi.mocked(apiClient.getEquityInsights).mockResolvedValue({
        diversification_score: 85,
        concentrated_positions: [
          { symbol: 'HDFCBANK', sector: 'Financials', weight_pct: 18.5 },
        ],
        tax_loss_harvest: [
          { symbol: 'TATAMOTORS', unrealized_loss: 12000 },
        ],
      } as any)

      renderWithProviders(<InsightsTab />)

      expect(await screen.findByText('Portfolio Diversification Score')).toBeInTheDocument()
      expect(screen.getByText('85')).toBeInTheDocument()
      expect(screen.getByText('Concentration Risk')).toBeInTheDocument()
      expect(screen.getByText('HDFCBANK')).toBeInTheDocument()
      expect(screen.getByText('18.5% Weight')).toBeInTheDocument()
    })
  })
})
