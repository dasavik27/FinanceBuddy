import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import OverviewTab from './OverviewTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getSummary: vi.fn(),
    getOverview: vi.fn(),
    getBenchmarkOverlay: vi.fn(),
    getHoldings: vi.fn(),
    getAllocation: vi.fn(),
    getPerformance: vi.fn(),
  },
}))

describe('OverviewTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-overview', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getSummary).mockResolvedValue({
      total_value: 1250000,
      total_invested: 1000000,
      total_gain: 250000,
      gain_pct: 25,
      portfolio_xirr: 18.5,
      alpha: 4.2,
      is_absolute: false,
    } as any)
    vi.mocked(apiClient.getOverview).mockResolvedValue({
      chart: {
        dates: ['2025-01-01', '2026-01-01'],
        portfolio: [1000000, 1250000],
        benchmark: [1000000, 1150000],
      },
      port_pct: 25,
      bench_pct: 15,
    } as any)
    vi.mocked(apiClient.getBenchmarkOverlay).mockResolvedValue({ series: {} } as any)
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        { Fund: 'Quant Small Cap Fund', 'Gain%': 38.5, 'Market Value': 400000 },
        { Fund: 'Parag Parikh Flexi Cap', 'Gain%': 22.1, 'Market Value': 600000 },
      ],
    } as any)
    vi.mocked(apiClient.getAllocation).mockResolvedValue({
      broad: [
        { label: 'Equity', pct: 85 },
        { label: 'Debt', pct: 15 },
      ],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      benchmark_price_index_blend: false,
    } as any)
  })

  it('renders section header, KPI cards, and asset allocation sidebar', async () => {
    renderWithProviders(<OverviewTab />)

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(await screen.findByText('₹12.50 L')).toBeInTheDocument()
    expect(screen.getByText('₹2.50 L')).toBeInTheDocument()
    expect(screen.getByText('+18.50%')).toBeInTheDocument()
    expect(screen.getByText('PORTFOLIO HEALTH')).toBeInTheDocument()
    expect(screen.getByText('TOP ATTRIBUTION')).toBeInTheDocument()
    expect(screen.getByText('QUANT SMALL CAP FUND')).toBeInTheDocument()
    expect(screen.getByText(/Macro Asset Spectrum & Risk Parity/i)).toBeInTheDocument()
  })
})
